"""Explicit own-work replay, never cross-direction context or a new discovery."""

import hashlib
import json
from pathlib import Path

from exp.phase4_run import reference


def load(path):return json.loads(Path(path).read_text())


def own_replay(directory,work):
    directory=Path(directory).resolve();work=Path(work).resolve()
    wire=[json.loads(line)['message'] for line in (directory/'wire.jsonl').read_text().splitlines()]
    files={}
    manifest=load(directory/'manifest.json')
    if 'own_replay' in manifest:
        seed=manifest['own_replay'];verify_replay(seed,manifest['role'])
        for name,row in seed['files'].items():
            action=load(row['source']['path'])['arguments']['action']
            files[name]=dict(row,content=action['content'],wire=row.get('wire',seed['source_wire']))
    for path in sorted(directory.glob('tools-*/action-*/request.json')):
        request=load(path);response=load(path.parent/'response.json');action=request['arguments']['action']
        if action.get('kind')!='write_file' or response.get('success') is not True:continue
        calls=[row for row in wire if row.get('method')=='item/tool/call' and row.get('params')==request]
        if len(calls)!=1 or sum(row.get('id')==calls[0]['id'] and row.get('result')==response for row in wire)!=1:
            raise ValueError('replayed write lacks a unique native call and feedback')
        name=Path(action['path']);content=action['content'].encode()
        answer=json.loads(response['contentItems'][0]['text']);digest=hashlib.sha256(content).hexdigest()
        if (name.is_absolute() or '..' in name.parts or name.parts[0]!='scratch' or
                answer.get('sha256')!=digest):raise ValueError('only native-authored scratch data may be replayed')
        files[name.as_posix()]=dict(content=action['content'],sha256=digest,source=reference(path),response=reference(path.parent/'response.json'),wire=reference(directory/'wire.jsonl'))
    for name,row in files.items():
        target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(row['content'])
    return dict(source_role=reference(directory/'manifest.json'),source_wire=reference(directory/'wire.jsonl'),
        files={name:{key:value for key,value in row.items() if key!='content'} for name,row in files.items()},
        provenance='Same logical role own interrupted work replayed; not independent discovery.')


def verify_replay(replay,kind):
    manifest=load(replay['source_role']['path'])
    if reference(replay['source_role']['path'])!=replay['source_role'] or manifest['role']!=kind:
        raise ValueError('own replay crossed its source role')
    if reference(replay['source_wire']['path'])!=replay['source_wire']:
        raise ValueError('own replay source wire changed')
    wire=[json.loads(line)['message'] for line in Path(replay['source_wire']['path']).read_text().splitlines()]
    authored={}
    for name,row in replay['files'].items():
        if reference(row['source']['path'])!=row['source'] or reference(row['response']['path'])!=row['response']:
            raise ValueError('own replay source receipt changed')
        request=load(row['source']['path']);response=load(row['response']['path']);action=request['arguments']['action']
        file_wire=wire
        if row.get('wire') is not None:
            if reference(row['wire']['path'])!=row['wire']:raise ValueError('replayed file source wire changed')
            file_wire=[json.loads(line)['message'] for line in Path(row['wire']['path']).read_text().splitlines()]
        calls=[item for item in file_wire if item.get('method')=='item/tool/call' and item.get('params')==request]
        if (action.get('kind')!='write_file' or action.get('path')!=name or response.get('success') is not True or
                hashlib.sha256(action['content'].encode()).hexdigest()!=row['sha256'] or len(calls)!=1 or
                sum(item.get('id')==calls[0]['id'] and item.get('result')==response for item in file_wire)!=1):
            raise ValueError('own replay authorship differs from native evidence')
        authored[name]=row['sha256']
    return authored
