"""Phase 0 adapter: existing bounded broker, separate explicit resource account."""

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
    bootstrap=ROOT/'exp/ceiling_remote.sh'
    cli=engine_command(request,source,output,name,deadline)
    cli[-1]=shlex.join(['env','SP_CEILING_BOOTSTRAP_SHA='+digest(bootstrap),
        'SP_CEILING_SOURCE_SHA='+digest(source),'SP_CEILING_REQUEST_SHA='+digest(request),
        'bash',str(bootstrap),str(request),str(source),str(output),str(deadline)])
    return cli


def feedback(output,record):
    from exp.ceiling_run import audit
    result=audit(output)
    if result!=json.loads((output/'result.json').read_text()):
        raise ValueError('independent Phase 0 replay differs from remote result')
    return result


def prepare(directory,inputs):
    if directory.exists():
        raise ValueError('new attempt required; existing evidence is immutable')
    directory.mkdir(mode=0o700,parents=True)
    packet=json.loads(Path(inputs).read_text())
    if (len(packet['requests'])!=10 or len({row['id'] for row in packet['requests']})!=10 or
            sorted(row['suite'] for row in packet['requests'])!=sorted(['gsm8k','math500','humaneval','mbpp','mt-bench']*2)):
        raise ValueError('frozen ten-request dev protocol required')
    names=subprocess.check_output(['git','ls-files','--','exp','harness','controller','costmodel',
        'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'],cwd=ROOT,text=True).splitlines()
    names += [path.relative_to(ROOT).as_posix() for prefix in ('exp','harness','costmodel')
        for pattern in ('ceiling*.py','ceiling*.sh','test_ceiling.py') for path in (ROOT/prefix).glob(pattern)]
    names=sorted(set(names))
    with tarfile.open(directory/'source.tar','w') as archive:
        for name in names:
            archive.add(ROOT/name,arcname=name,recursive=False)
    identity=dict(path=str(directory/'source.tar'),sha256=digest(directory/'source.tar'),
        files={name:digest(ROOT/name) for name in names})
    save(directory/'source-identity.json',identity)
    save(directory/'request.json',dict(mode='ceiling',source_pin=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_archive=identity,
        action=dict(per_suite=2,max_new_tokens=2048),stock_engine='/gpfs/users/jixinpeng/specpilot_data/work/engines/h100_c1_qwen38-27b_dflash2-stock',
        **packet))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','plan','execute','resume'))
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--inputs',type=Path)
    args=parser.parse_args()
    directory=args.directory.resolve()
    if args.command=='prepare':
        prepare(directory,args.inputs)
        print(json.dumps(dict(prepared=True,directory=str(directory),submitted=False)))
        return
    request=directory/'request.json'
    source=directory/'source.tar'
    budget=Budget(directory.parent/'resource-state.json',limits=dict(gpu_seconds=57600,wall_seconds=43200,concurrent_gpus=2))
    if args.command=='plan':
        print(json.dumps(dict(name=directory.name,nodes=1,gpus_per_node=2,total_gpus=2,
            image=IMAGE,gpu_type='H100',deadline_seconds=7200,project='WeaverDev',namespace='qiji',queue='qiji',
            mode='bash',memory_gib=256,command=shlex.join(command(request,source,directory/'remote',directory.name,7200))),indent=2))
    else:
        result=execute(directory,source,budget,resume_only=args.command=='resume',
            command_factory=command,feedback_loader=feedback,deadline=7200)
        print(json.dumps(dict(status=result['status'],uuid=result['uuid'],full_ceiling_completed=result.get('full_ceiling_completed',False))))


if __name__=='__main__':
    main()
