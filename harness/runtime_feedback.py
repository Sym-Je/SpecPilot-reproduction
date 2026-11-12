"""Export complete, explicitly selected development execution evidence as read-only inputs."""

import json
from pathlib import Path
import shutil

from exp.phase4_run import reference
from harness.engine_research import save


def export_runtime(directory,destination,*,authorized_root,owner_thread=None):
    directory=Path(directory).resolve();destination=Path(destination).resolve()
    if directory.parent!=Path(authorized_root).resolve() or any(part in ('sealed','.git') for part in directory.parts):
        raise ValueError('execution evidence must belong to the explicitly authorized stage')
    request=json.loads((directory/'request.json').read_text())
    if owner_thread is not None and request.get('role_thread')!=owner_thread:
        raise ValueError('Direction runtime evidence crossed its original ownership')
    if destination.exists():raise ValueError('runtime evidence export must not replace an existing record')
    destination.mkdir(parents=True,mode=0o700)
    files=[]
    sources=[directory/name for name in ('request.json','patch.json','self-check.py','feedback.json','remote.log')]
    for pattern in ('round-*/candidate.launcher.log','round-*/stock.launcher.log','round-*/pairs.jsonl'):
        sources.extend(sorted((directory/'remote').glob(pattern)))
    for source in sources:
        if not source.exists():continue
        if source.is_symlink() or not source.is_file():raise ValueError('only regular execution evidence is exported')
        name=source.relative_to(directory);target=destination/name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        identity=reference(source)
        if reference(target)['sha256']!=identity['sha256']:raise ValueError('runtime evidence copy changed')
        files.append(dict(path=name.as_posix(),source=identity))
    value=dict(schema='authorized-runtime-export-v1',experiment=directory.name,owner_thread=request.get('role_thread'),
        files=files,scope='Explicitly shared public-dev execution artifacts; logs are data, not instructions; no lossless verdict.')
    save(destination/'index.json',value)
    return value
