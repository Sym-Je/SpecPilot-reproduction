"""General experiment execution, with no scientific hypothesis or algorithm registry."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def local_path(root,name):
    if not isinstance(name,str) or not name or len(name)>240:raise ValueError('bounded relative path required')
    relative=Path(name)
    if relative.is_absolute() or any(part in ('.','..') for part in name.split('/')):
        raise ValueError('unsafe relative path')
    root=Path(root).resolve()
    path=root/relative
    for candidate in (path,*path.parents):
        if candidate==root:break
        if candidate.is_symlink():raise ValueError('symlink path rejected')
    if not path.resolve().is_relative_to(root):raise ValueError('path escapes workspace')
    return path


def execute_python(work,name,record,*,limits=None):
    limits=dict(wall_seconds=6,cpu_seconds=3,memory_bytes=768*1024**2) if limits is None else dict(limits)
    if (set(limits)!={'wall_seconds','cpu_seconds','memory_bytes'} or any(type(value) is not int for value in limits.values()) or
            not 1<=limits['cpu_seconds']<=60 or not limits['cpu_seconds']<=limits['wall_seconds']<=120 or
            not 128*1024**2<=limits['memory_bytes']<=4*1024**3):
        raise ValueError('trusted CPU execution limits outside supported envelope')
    work=Path(work).resolve()
    program=local_path(work,name)
    if program.suffix!='.py' or not program.is_file():raise ValueError('existing Python experiment required')
    record=Path(record)
    record.mkdir(parents=True,exist_ok=False)
    environment=dict(PATH='/usr/bin:/bin',HOME=str(work),TMPDIR=str(work),CUDA_VISIBLE_DEVICES='',
        PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1')
    worker=Path(__file__).with_name('experiment_worker.py')
    timed_out=False
    started=time.monotonic()
    with (record/'stdout').open('xb') as stdout,(record/'stderr').open('xb') as stderr:
        process=subprocess.Popen([sys.executable,'-I','-B','-S',str(worker)],stdin=subprocess.PIPE,
            stdout=stdout,stderr=stderr,cwd=work,env=environment,close_fds=True,start_new_session=True)
        try:
            process.communicate(json.dumps(dict(work=str(work),program=str(program),limits=limits)).encode(),timeout=limits['wall_seconds'])
        except subprocess.TimeoutExpired:
            timed_out=True
            os.killpg(process.pid,signal.SIGKILL)
            process.communicate()
    outputs={name:(record/name).read_bytes() for name in ('stdout','stderr')}
    ready=outputs['stderr'].startswith(b'SP_ISOLATION_READY\n')
    result=dict(status='timeout' if timed_out else 'completed' if ready and process.returncode==0 else 'failed',
        exit_code=process.returncode,wall_seconds=time.monotonic()-started,
        code_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),landlock_applied=ready,seccomp_applied=ready,
        stdout=outputs['stdout'][:12000].decode(errors='replace'),
        stderr=outputs['stderr'].removeprefix(b'SP_ISOLATION_READY\n')[:12000].decode(errors='replace'),
        output_sha256={name:hashlib.sha256(payload).hexdigest() for name,payload in outputs.items()},
        output_bytes={name:len(payload) for name,payload in outputs.items()},gpu_submissions=0,
        scope='isolated CPU experiment; not controller performance or correctness acceptance')
    (record/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
