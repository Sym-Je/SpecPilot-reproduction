"""Recheck a trusted historical diagnostic with its own frozen CPU audit sources."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


MODULES=frozenset(('exp.ceiling_run','exp.ceiling_mapping','exp.ceiling_measure'))


def reference(path):
    path=Path(path).resolve()
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def frozen_audit(directory,module):
    if module not in MODULES:raise ValueError('only fixed trusted diagnostic CPU auditors are allowed')
    directory=Path(directory).resolve();request=directory.parent/'request.json'
    record=json.loads(request.read_text());archive=record['source_archive']
    if reference(archive['path'])['sha256']!=archive['sha256']:raise ValueError('historical archive SHA differs')
    with tempfile.TemporaryDirectory(prefix='stock-diagnostic-audit-') as temporary:
        with tarfile.open(archive['path']) as source:
            members=source.getmembers();names=[member.name for member in members]
            if (len(names)!=len(set(names)) or set(names)!=set(archive['files']) or len(names)>512 or
                    sum(member.size for member in members)>128*1024**2 or any(not member.isfile() or
                    Path(member.name).is_absolute() or '..' in Path(member.name).parts for member in members)):
                raise ValueError('unexpected historical source archive members')
            for member in members:
                if hashlib.sha256(source.extractfile(member).read()).hexdigest()!=archive['files'][member.name]:
                    raise ValueError('historical source member SHA differs')
            source.extractall(temporary,filter='data')
        code=('import importlib,json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
            'print(json.dumps(importlib.import_module(sys.argv[2]).audit(Path(sys.argv[3])),sort_keys=True))')
        environment=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
        process=subprocess.run([sys.executable,'-I','-B','-c',code,temporary,module,str(directory)],
            cwd=temporary,env=environment,capture_output=True,text=True,timeout=1800)
        if process.returncode:raise ValueError('frozen CPU audit failed: '+process.stderr[-2500:])
        result=json.loads(process.stdout)
        if result!=json.loads((directory/'result.json').read_text()):
            raise ValueError('frozen audit differs from recorded historical result')
    return dict(source_archive_verified=True,request=reference(request),source=dict(path=archive['path'],sha256=archive['sha256']),
        recorded_result=reference(directory/'result.json'),module=module,result=result,
        scope='Trusted archived audit only; temporary source directory, no new GPU task or research execution.')
