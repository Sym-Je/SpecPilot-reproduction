"""Separate 8 GPU-hour sampling campaign using the existing trusted NorthJob broker."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from exp.engine_resource import command as engine_command,execute
from exp.gpu_autonomy import IMAGE
from harness.engine_research import Budget,save
from harness.gpu_autonomy import digest


def command(request,source,output,name,deadline):
    bootstrap=ROOT/'exp/sampling_remote.sh'
    result=engine_command(request,source,output,name,deadline)
    result[-1]=shlex.join(['env','SP_SAMPLING_BOOTSTRAP_SHA='+digest(bootstrap),
        'SP_SAMPLING_SOURCE_SHA='+digest(source),'SP_SAMPLING_REQUEST_SHA='+digest(request),
        'bash',str(bootstrap),str(request),str(source),str(output),str(deadline)])
    return result


def prepare(directory,phase,temperature,compatibility):
    if directory.exists():
        raise ValueError('new immutable attempt directory required')
    directory.mkdir(mode=0o700,parents=True)
    from exp.p3_pair_run import arm_specs,clean_environment
    arms,config=arm_specs(['stock','final'],clean_environment())
    code=('import json;from transformers import AutoTokenizer;from exp.p3_pair_run import load_requests,SUITES;'
        "tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True);"
        'print(json.dumps(load_requests(4,SUITES,tokenizer)))')
    process=subprocess.run(['/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python','-B','-c',code],
        cwd=ROOT,capture_output=True,text=True,timeout=180,check=True)
    requests=json.loads(process.stdout)
    if len(requests)!=20:
        raise ValueError('request freeze failed')
    proof=None
    if phase=='measure':
        if compatibility is None:
            raise ValueError('sampling compatibility evidence required')
        from exp.sampling_run import audit
        checked=audit(compatibility)
        if temperature>0 and str(temperature) not in checked['supported_temperatures']:
            raise ValueError('temperature did not pass compatibility probe')
        proof=dict(directory=str(compatibility.resolve()),result_sha256=digest(compatibility/'result.json'))
    names=subprocess.check_output(['git','ls-files','--','exp','harness','controller',
        'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'],cwd=ROOT,text=True).splitlines()
    names+=['exp/sampling_resource.py','exp/sampling_run.py','exp/sampling_remote.sh',
        'harness/sampling_protocol.py','harness/test_sampling_protocol.py']
    names=sorted(set(names))
    hashes={name:digest(ROOT/name) for name in names}
    with tarfile.open(directory/'source.tar','w') as archive:
        for name in names:
            archive.add(ROOT/name,arcname=name,recursive=False)
    if any(digest(ROOT/name)!=checksum for name,checksum in hashes.items()):
        raise ValueError('source changed during freeze')
    source=dict(path=str(directory/'source.tar'),sha256=digest(directory/'source.tar'),files=hashes)
    save(directory/'request.json',dict(mode='author-final-sampling-v1',phase=phase,temperature=temperature,
        action=dict(per_suite=4,max_new_tokens=2048),requests=requests,arms=arms,compatibility=proof,
        source_archive=source,source_pin=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        config=dict(path=str(ROOT/'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'),
            sha256=digest(ROOT/'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'))))


def feedback(output,record):
    from exp.sampling_run import audit
    result=audit(output)
    if result!=json.loads((output/'result.json').read_text()):
        raise ValueError('independent sampling audit differs')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','plan','execute','resume'))
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--phase',choices=('probe','measure'),default='probe')
    parser.add_argument('--temperature',type=float,choices=(0.,.7,1.),default=.7)
    parser.add_argument('--compatibility',type=Path)
    parser.add_argument('--deadline',type=int,default=1800)
    args=parser.parse_args()
    directory=args.directory.resolve()
    if args.command=='prepare':
        prepare(directory,args.phase,args.temperature,args.compatibility)
        print(json.dumps(dict(prepared=True,submitted=False)))
        return
    if not 600<=args.deadline<=7200:
        raise ValueError('unsupported task deadline')
    request,source=directory/'request.json',directory/'source.tar'
    if args.command=='plan':
        print(json.dumps(dict(name=directory.name,total_gpus=2,nodes=1,gpus_per_node=2,
            image=IMAGE,project='WeaverDev',namespace='qiji',queue='qiji',priority=3,
            deadline=args.deadline,command=shlex.join(command(request,source,directory/'remote',directory.name,args.deadline))),indent=2))
        return
    budget=Budget(directory.parent/'resource-state.json',limits=dict(gpu_seconds=28800,wall_seconds=21600,concurrent_gpus=2))
    result=execute(directory,source,budget,resume_only=args.command=='resume',
        command_factory=command,feedback_loader=feedback,deadline=args.deadline)
    print(json.dumps(dict(status=result['status'],uuid=result['uuid'],supported_temperatures=result.get('supported_temperatures'))))


if __name__=='__main__':
    main()
