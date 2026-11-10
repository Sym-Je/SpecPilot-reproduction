"""Default-off CPU metadata sampling outside compiled attention/model calls.

This is diagnostic instrumentation. It does not expose the selected device
tiling or prove device dependency/phase linkage; those fields stay unresolved.
"""
import functools
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import sys
import time

_armed=False
_step=0
_selected={}
_records=[]
_targets={
    'vllm_ascend.worker.model_runner_v1',
    'vllm_ascend.attention.dsa_v1',
    'vllm_ascend.profiler.torch_npu_profiler',
}


def cpu_lengths(value,limit=33):
    if value is None:return None
    device=getattr(value,'device',None)
    if device is not None and getattr(device,'type',None)!='cpu':return None
    shape=getattr(value,'shape',None)
    if shape is None or len(shape)!=1 or int(shape[0])>limit:return None
    values=value.tolist()
    if any(type(x) is not int or x<0 for x in values):return None
    return values


def observe(builder,common,result):
    if not _armed or _step<=0 or len(_records)>=4:return
    ratio=getattr(builder,'compressor_ratio',None)
    if ratio not in (4,128) or getattr(result,'num_prefills',0)<=0:return
    if _step not in _selected:
        if len(_selected)>=2:return
        _selected[_step]=set()
    if ratio in _selected[_step]:return
    _selected[_step].add(ratio)
    import torch.distributed as dist
    rank=dist.get_rank() if dist.is_initialized() else None
    _records.append({'rank':rank,'host_timestamp_ns':time.time_ns(),'target_scheduler_step':_step,
        'compressor_ratio':ratio,'num_reqs':getattr(common,'num_reqs',None),
        'num_actual_tokens':getattr(common,'num_actual_tokens',None),
        'num_input_tokens':getattr(common,'num_input_tokens',None),
        'num_prefills':getattr(result,'num_prefills',None),
        'num_decode_tokens':getattr(result,'num_decode_tokens',None),
        'query_start_loc_cpu':cpu_lengths(getattr(common,'query_start_loc_cpu',None)),
        'seq_lens_cpu':cpu_lengths(getattr(common,'_seq_lens_cpu',None)),
        'scope':'target scheduler metadata-build observation, not attention-kernel provenance',
        'layer_id':None,'device_task':None,'selected_tiling':None,'genuine_device_dependencies':None})


def flush():
    root=Path(os.environ['SPARSE_WORK_DIAG_DIR'])
    root.mkdir(parents=True,exist_ok=True)
    path=root/f'worker-{os.getpid()}.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'records':_records,'max_steps':2,'max_records':4,
        'tensor_values_captured':False,'device_to_host_copies_added':False,
        'scope':'diagnostic only; scheduling/IO perturbation unmeasured; no performance certification'},indent=2)+'\n')
    temporary.replace(path)


def patch_module(module):
    global _armed,_step
    if module.__name__.endswith('model_runner_v1'):
        original=module.NPUModelRunner._prepare_inputs
        @functools.wraps(original)
        def prepare(self,*args,**kwargs):
            global _step
            if _armed:_step+=1
            return original(self,*args,**kwargs)
        module.NPUModelRunner._prepare_inputs=prepare
    elif module.__name__.endswith('dsa_v1'):
        original=module.AscendDSAMetadataBuilder.build
        @functools.wraps(original)
        def build(self,*args,**kwargs):
            result=original(self,*args,**kwargs)
            if _armed:
                common=kwargs.get('common_attn_metadata',args[1] if len(args)>1 else None)
                if common is not None:observe(self,common,result)
            return result
        module.AscendDSAMetadataBuilder.build=build
    else:
        cls=module.TorchNPUProfilerWrapper
        start,stop=cls._start,cls._stop
        @functools.wraps(start)
        def begin(self):
            global _armed,_step
            result=start(self);_records.clear();_selected.clear();_step=0;_armed=True
            return result
        @functools.wraps(stop)
        def end(self):
            global _armed
            _armed=False
            try:return stop(self)
            finally:flush()
        cls._start,cls._stop=begin,end


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname not in _targets:return None
        spec=importlib.machinery.PathFinder.find_spec(fullname,path)
        if spec is None or spec.loader is None:return None
        delegate=spec.loader
        class Loader(importlib.abc.Loader):
            def create_module(self,spec):return delegate.create_module(spec)
            def exec_module(self,module):
                delegate.exec_module(module);patch_module(module)
        spec.loader=Loader()
        return spec


def install():
    if os.environ.get('SPARSE_WORK_DIAG_ENABLE')!='1':return False
    root=os.environ.get('SPARSE_WORK_DIAG_DIR')
    if not root or not Path(root).is_absolute():raise ValueError('Explicit absolute diagnostic output required')
    if any(name in sys.modules for name in _targets):raise RuntimeError('Install diagnostic before target module imports')
    sys.meta_path.insert(0,Finder())
    return True
