"""Explicit own-work replay, never cross-direction context or a new discovery."""

import hashlib
import json
from pathlib import Path

from exp.phase4_run import reference


def load(path):return json.loads(Path(path).read_text())


def replay_text(name,row,fallback_wire):
    from harness.open_research import record_authored_text
    operations=row.get('operations',[dict(source=row['source'],response=row['response'],wire=row.get('wire',fallback_wire))])
    contents={}
    for operation in operations:
        for key in ('source','response','wire'):
            if reference(operation[key]['path'])!=operation[key]:raise ValueError('own replay operation changed')
        request=load(operation['source']['path']);response=load(operation['response']['path'])
        action=request['arguments']['action'];relative=Path(action['path'])
        if (action.get('kind') not in ('write_file','append_file') or action['path']!=name or
                relative.is_absolute() or '..' in relative.parts or relative.parts[0]!='scratch' or response.get('success') is not True):
            raise ValueError('replay only restores native-authored private scratch')
        wire=[json.loads(line)['message'] for line in Path(operation['wire']['path']).read_text().splitlines()]
        calls=[item for item in wire if item.get('method')=='item/tool/call' and item.get('params')==request]
        if len(calls)!=1 or sum(item.get('id')==calls[0]['id'] and item.get('result')==response for item in wire)!=1:
            raise ValueError('own replay operation lacks unique native authorship')
        answer=json.loads(response['contentItems'][0]['text'])
        record_authored_text(action,answer,contents)
    content=contents.get(name)
    if content is None or hashlib.sha256(content.encode()).hexdigest()!=row['sha256']:
        raise ValueError('own replay final content differs')
    return content


def own_replay(directory,work):
    directory=Path(directory).resolve();work=Path(work).resolve()
    wire=[json.loads(line)['message'] for line in (directory/'wire.jsonl').read_text().splitlines()]
    files={}
    manifest=load(directory/'manifest.json')
    if 'own_replay' in manifest:
        seed=manifest['own_replay'];verify_replay(seed,manifest['role'])
        for name,row in seed['files'].items():
            files[name]=dict(row,content=replay_text(name,row,seed['source_wire']),wire=row.get('wire',seed['source_wire']))
    for path in sorted(directory.glob('tools-*/action-*/request.json')):
        request=load(path);response=load(path.parent/'response.json');action=request['arguments']['action']
        if action.get('kind') not in ('write_file','append_file') or response.get('success') is not True:continue
        calls=[row for row in wire if row.get('method')=='item/tool/call' and row.get('params')==request]
        if len(calls)!=1 or sum(row.get('id')==calls[0]['id'] and row.get('result')==response for row in wire)!=1:
            raise ValueError('replayed write lacks a unique native call and feedback')
        name=Path(action['path']);content=action['content'].encode();operations=[]
        if action['kind']=='append_file':
            previous=files.get(name.as_posix())
            if previous is None or previous['sha256']!=action['expected_sha256']:
                raise ValueError('replayed append has no matching original source')
            content=previous['content'].encode()+content
            operations=list(previous.get('operations',[dict(source=previous['source'],response=previous['response'],wire=previous['wire'])]))
        answer=json.loads(response['contentItems'][0]['text']);digest=hashlib.sha256(content).hexdigest()
        if (name.is_absolute() or '..' in name.parts or name.parts[0]!='scratch' or
                answer.get('sha256')!=digest):raise ValueError('only native-authored scratch data may be replayed')
        operation=dict(source=reference(path),response=reference(path.parent/'response.json'),wire=reference(directory/'wire.jsonl'))
        files[name.as_posix()]=dict(content=content.decode(),sha256=digest,**operation,
            operations=operations+[operation])
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
        replay_text(name,row,replay['source_wire'])
        authored[name]=row['sha256']
    return authored
