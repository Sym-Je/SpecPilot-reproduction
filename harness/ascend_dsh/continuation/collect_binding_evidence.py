"""Inspect loaded binaries and registration schemas without model/device execution."""
import importlib
import json
from pathlib import Path
import time

from prepare_baseline import ROOT, OUT, write, sha


def main():
    import torch
    import torch_npu
    from vllm_ascend.utils import bootstrap_custom_op_env
    before=torch.npu.is_initialized()
    bootstrap_custom_op_env(include_vendor_lib=True)
    extension=importlib.import_module('vllm_ascend.vllm_ascend_C')
    importlib.import_module('vllm_ascend.meta_registration')
    names=['_C_ascend::npu_hc_pre_v2','_C_ascend::npu_hc_post',
           '_C_ascend::npu_sparse_attn_sharedkv','npu::npu_dynamic_quant']
    schemas=[]
    for name in names:
        try:
            namespace,operator=name.split('::')
            packet=getattr(getattr(torch.ops,namespace),operator)
            schemas.append({'operator':name,'schemas':{k:str(v) for k,v in packet._schemas.items()},
                            'dispatch_registration':torch._C._dispatch_dump(name)})
        except Exception as exc:schemas.append({'operator':name,'error':repr(exc)})
    after=torch.npu.is_initialized()
    assert before is False and after is False, 'Schema inspection must not initialize an NPU context'
    loaded={}
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():continue
        try:
            comm=(folder/'comm').read_text().strip()
            if not comm.startswith('VLLM::Worker'):continue
            for line in (folder/'maps').read_text().splitlines():
                if 'vllm_ascend' not in line or '.so' not in line:continue
                parts=line.split(None,5)
                if len(parts)!=6:continue
                path=Path(parts[5]);entry=loaded.setdefault(str(path),{'worker_pids':set(),'mapped_inodes':set()})
                entry['worker_pids'].add(int(folder.name));entry['mapped_inodes'].add(int(parts[4]))
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
    for path,entry in loaded.items():
        p=Path(path);entry['worker_pids']=sorted(entry['worker_pids']);entry['mapped_inodes']=sorted(entry['mapped_inodes'])
        if p.is_file():
            entry['file_sha256']=sha(p);entry['on_disk_inode']=p.stat().st_ino
            entry['mapped_inode_matches_disk']=entry['mapped_inodes']==[p.stat().st_ino]
    result={'status':'complete','created_epoch':time.time(),'scope':'Registration inspection and passive /proc reads; no NPU tensor allocation, operator execution, model replay or server restart.',
        'npu_initialized_before':before,'npu_initialized_after':after,
        'inspected_extension':str(Path(extension.__file__).resolve()),'extension_sha256':sha(extension.__file__),
        'operator_registrations':schemas,'live_worker_libraries':loaded,
        'source_reference':{'tree':'binding_reference','scope':'Upstream stock source snapshot is reference evidence, not proof that it produced the loaded binary. Read its binding/host/meta source and compare runtime schemas; do not claim selected tiling or allocation behavior solely from this reference.'},
        'limitations':['Schemas establish declared alias/mutation contracts, not observed allocation/stride/pointer behavior.',
          'Runtime selected tiling, actual context values, graph IR and output coverage are not captured by this offline inspection.',
          'Do not infer loaded-source identity from filenames. Separate PR validation binaries differ from the serving extension.']}
    write(OUT/'research/operator-binding-evidence.json',result)
    print(json.dumps({'status':'complete','operators':len(schemas),'live_libraries':len(loaded),'npu_initialized':after}))


if __name__=='__main__':main()
