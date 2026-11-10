"""Default-off initialization metadata only; no request/device-value hooks.

This phase exports declarative cache plans and CPU manager geometry. It cannot
validate enabled prefix-cache state restoration, runtime hits or correctness.
"""
import functools
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import re
import sys

MAX_GROUPS=128
MAX_LAYERS=512
MAX_BYTES=256*1024
MAX_SNAPSHOTS=3
_emitted=0
_overflowed=False
_installed=False
TARGETS={'vllm_ascend.worker.model_runner_v1','vllm.v1.engine.core',
         'vllm.v1.core.kv_cache_manager'}
SPEC_FIELDS=('block_size','storage_block_size','tokens_per_state','num_kv_heads',
    'head_size','head_size_v','dtype','scale_dtype','scale_dim','sliding_window',
    'page_size_bytes','real_page_size_bytes','unpadded_page_size_bytes',
    'page_size_padded','prefix_cacheable','participates_in_prefix_caching',
    'non_causal','non_causal_multi_token_decode','extra_retained_tokens',
    'indexes_kv_by_block_stride','model_version','store_on_host')


def scalar(value):
    if value is None or type(value) in (bool,int):return value
    if type(value) is str and len(value)<=240:return value
    if type(value).__module__=='torch' and type(value).__name__=='dtype':return str(value)
    return None


def fields(obj,names):
    result={}
    for name in names:
        try:result[name]=scalar(getattr(obj,name,None))
        except Exception:result[name]=None
    return result


def class_name(obj):
    return type(obj).__module__+'.'+type(obj).__qualname__


def layer_names(values):
    if not isinstance(values,(list,tuple)):return [],True
    accepted=[x for x in values[:MAX_LAYERS] if type(x) is str and len(x)<=240
              and re.fullmatch(r'[A-Za-z0-9_.]+',x)]
    return accepted,len(values)>MAX_LAYERS or len(accepted)!=len(values)


def spec_plan(spec,depth=0):
    result={'class':class_name(spec),'fields':fields(spec,SPEC_FIELDS),'truncated':False}
    children=getattr(spec,'kv_cache_specs',None)
    if isinstance(children,dict):
        if depth>=2:result['truncated']=True
        else:
            result['layer_specs']=[]
            for name,child in list(children.items())[:MAX_LAYERS]:
                valid,bad=layer_names([name])
                if bad:result['truncated']=True;continue
                record=spec_plan(child,depth+1)
                result['layer_specs'].append({'layer':valid[0],'spec':record})
                result['truncated']|=record['truncated']
            result['truncated']|=len(children)>MAX_LAYERS
    return result


def cache_plan(config):
    groups=getattr(config,'kv_cache_groups',())
    if not isinstance(groups,(list,tuple)):raise TypeError('Expected metadata groups')
    result={'config':fields(config,('num_blocks','prefix_cache_retention_interval','kv_cache_layout')),
            'groups':[],'planned_backings':[],'truncated':len(groups)>MAX_GROUPS,
            'enabled_state_restoration_validated':False}
    for index,group in enumerate(groups[:MAX_GROUPS]):
        names,bad=layer_names(getattr(group,'layer_names',None))
        spec=spec_plan(group.kv_cache_spec)
        result['groups'].append({'group_index':index,'layers':names,'spec':spec,
            **fields(group,('is_eagle_group','host_resident','enable_kv_transfer'))})
        result['truncated']|=bad or spec['truncated']
    backings=getattr(config,'kv_cache_tensors',())
    if isinstance(backings,(list,tuple)):
        result['truncated']|=len(backings)>MAX_LAYERS
        for item in backings[:MAX_LAYERS]:
            names,bad=layer_names(getattr(item,'layers',None))
            result['planned_backings'].append({'layers':names,
                **fields(item,('size','offset','layer_stride','block_stride','host_resident'))})
            result['truncated']|=bad
    else:result['truncated']=True
    result['limitations']=['Planned backings are descriptors, not observed tensor shapes, unique physical allocations or residency.',
        'Missing/null fields remain unknown; neither group presence nor cacheability proves enabled-state recovery.',
        'No request telemetry, tensor values, device copies, synchronization, addresses or hashes are captured.']
    return result


def emit(stage,data):
    global _emitted,_overflowed
    if _overflowed:return
    root=Path(os.environ['PREFIX_CACHE_METADATA_DIR'])
    if not root.is_absolute():raise ValueError('Absolute output directory required')
    root.mkdir(parents=True,exist_ok=True)
    if _emitted>=MAX_SNAPSHOTS:
        _overflowed=True;stage='overflow';data={'truncated':True,'reason':'snapshot_bound'}
    row={'schema':'prefix-cache-init-metadata/v1','stage':stage,'pid':os.getpid(),
         'ordinal':_emitted,'enabled_state_restoration_validated':False,'data':data}
    encoded=json.dumps(row,ensure_ascii=False).encode()
    if len(encoded)>MAX_BYTES:
        row['data']={'truncated':True,'reason':'byte_bound'};encoded=json.dumps(row).encode()
    path=root/f'metadata-{os.getpid()}-{_emitted}.json';temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(encoded)
    temporary.replace(path);_emitted+=1


def vllm_config_fields(config):
    return {'cache':fields(getattr(config,'cache_config',None),('enable_prefix_caching','block_size','num_gpu_blocks')),
        'parallel':fields(getattr(config,'parallel_config',None),('rank','tensor_parallel_size','data_parallel_size','enable_expert_parallel')),
        'speculative':fields(getattr(config,'speculative_config',None),('method','num_speculative_tokens'))}


def capture_worker(runner):
    data=cache_plan(runner.kv_cache_config)
    data['effective_worker_config']=vllm_config_fields(runner.vllm_config)
    dist=sys.modules.get('torch.distributed')
    data['distributed_rank']=dist.get_rank() if dist and dist.is_initialized() else None
    data['distributed_world_size']=dist.get_world_size() if dist and dist.is_initialized() else None
    data['kernel_block_sizes']=None  # Nested geometry requires a separate validated schema.
    emit('worker_initialized',data)


def observe(stage,callback):
    try:callback()
    except Exception as error:
        try:emit(stage+'_observer_error',{'truncated':True,'error_type':type(error).__name__})
        except Exception:pass


def patch_module(module):
    if module.__name__=='vllm_ascend.worker.model_runner_v1':
        cls=module.NPUModelRunner;name='initialize_kv_cache'
        callback=lambda owner,args,kwargs,result:capture_worker(owner)
    elif module.__name__=='vllm.v1.engine.core':
        cls=module.EngineCore;name='_initialize_kv_caches'
        callback=lambda owner,args,kwargs,result:emit('core_initialized',
            {'plan':cache_plan(result),'effective_core_config':vllm_config_fields(owner.vllm_config)})
    else:
        cls=module.KVCacheManager;name='__init__'
        def callback(owner,args,kwargs,result):
            coordinator=owner.coordinator
            emit('manager_initialized',{'enable_caching':scalar(owner.enable_caching),
                'coordinator_class':class_name(coordinator),
                'geometry':fields(coordinator,('scheduler_block_size','hash_block_size','num_reprefillable_tokens')),
                'managers':[{'group_index':i,'class':class_name(m),
                    **fields(m,('block_size','max_num_blocks','use_eagle','num_speculative_blocks'))}
                    for i,m in enumerate(coordinator.single_type_managers[:MAX_GROUPS])],
                'group_count':len(coordinator.single_type_managers),
                'truncated':len(coordinator.single_type_managers)>MAX_GROUPS})
    original=getattr(cls,name)
    if getattr(original,'_prefix_cache_metadata_wrapped',False):return
    @functools.wraps(original)
    def wrapped(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        observe(name,lambda:callback(self,args,kwargs,result))
        return result
    wrapped._prefix_cache_metadata_wrapped=True
    setattr(cls,name,wrapped)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname not in TARGETS:return None
        spec=importlib.machinery.PathFinder.find_spec(fullname,path)
        if spec is None or spec.loader is None:return None
        delegate=spec.loader
        class Loader(importlib.abc.Loader):
            def create_module(self,spec):return delegate.create_module(spec)
            def exec_module(self,module):
                delegate.exec_module(module);patch_module(module)
        spec.loader=Loader();return spec


def install():
    global _installed
    if os.environ.get('PREFIX_CACHE_METADATA_ENABLE')!='1':return False
    if _installed:return True
    root=os.environ.get('PREFIX_CACHE_METADATA_DIR')
    if not root or not Path(root).is_absolute():raise ValueError('Explicit absolute output required')
    if any(name in sys.modules for name in TARGETS):raise RuntimeError('Early initialization required')
    sys.meta_path.insert(0,Finder());_installed=True;return True
