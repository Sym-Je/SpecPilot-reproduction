"""Replay only a logical role's own interrupted work, charging actual native calls."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from controller.phase4_final import trusted_metadata, validate_shutdown
from exp.phase4_run import reference
from harness.decision_evidence import verify
from harness.master_decisions import LIMITS
from harness.research_protocol import CPU_ACTIONS


def load(path):
    return json.loads(Path(path).read_text())


def count_actions(calls):
    return dict(actions=len(calls),cpu_runs=sum(action.get('kind') in CPU_ACTIONS and
        answer.get('reason')!='CPU run budget exhausted' for action,answer in calls))


def own_files(calls):
    result={}
    for action,answer in calls:
        if action.get('kind')!='write_file' or answer.get('status')!='completed':
            continue
        path=Path(action['path'])
        if (path.is_absolute() or path.parts[0]!='scratch' or '..' in path.parts or
                hashlib.sha256(action['content'].encode()).hexdigest()!=answer.get('sha256')):
            raise ValueError('recovered source must be a successful native scratch write')
        result[path.as_posix()]=action['content']
    return result


def interrupted(root):
    root=Path(root).resolve()
    if load(root/'manifest.json').get('recovery') is not None:
        raise ValueError('nested interrupted recovery requires an explicit cumulative audit')
    result=load(root/'result.json')
    if result.get('status')!='needs_attention' or result.get('error')!='RuntimeError: role did not complete':
        raise ValueError('only the recorded incomplete native role may be continued')
    verify(root)
    closure=load(root/'process-closure.json')
    if closure.get('role_processes_closed') is not True:
        raise ValueError('interrupted native processes are not closed')
    registry=trusted_metadata(closure['shutdown_registry'],(root/'process-closure.json').stat().st_uid)
    validate_shutdown(registry,broker_uid=(root/'process-closure.json').stat().st_uid,opened_unix=time.time())
    if registry['members']!=closure['process_members']:
        raise ValueError('interrupted process inventory differs')
    counts=Counter();roles={};sources=[]
    for directory in [root/'master',*sorted(root.glob('direction-*'))]:
        wire=load_wire(directory/'wire.jsonl')
        messages=[row['message'] for row in wire]
        calls=[]
        for path in sorted(directory.glob('tools-*/action-*/request.json')):
            request=load(path);response=load(path.parent/'response.json')
            matches=[row for row in messages if row.get('method')=='item/tool/call' and row.get('params')==request]
            if len(matches)!=1 or sum(row.get('id')==matches[0]['id'] and row.get('result')==response for row in messages)!=1:
                raise ValueError('interrupted tool call/feedback differs from native wire')
            calls.append((request['arguments']['action'],json.loads(response['contentItems'][0]['text'])))
            sources.extend((reference(path),reference(path.parent/'response.json')))
        if len(calls)!=sum(row.get('method')=='item/tool/call' for row in messages):
            raise ValueError('unrecorded interrupted tool call')
        actual=count_actions(calls)
        actual.update(model_turns=sum(row.get('method')=='turn/start' for row in messages),
            usage_updates=sum(row.get('method')=='thread/tokenUsage/updated' for row in messages))
        counts.update(actual)
        responses=[load(path) for path in sorted(directory.glob('turn-*-response.json'))]
        roles[directory.name]=dict(counters=actual,own_responses=responses,own_scratch=own_files(calls))
        sources.extend(reference(path) for path in sorted(directory.glob('turn-*-response.json')))
        sources.extend((reference(directory/'wire.jsonl'),reference(directory/'manifest.json')))
    if any(counts[key]>=LIMITS[key] for key in ('actions','cpu_runs','model_turns')):
        raise ValueError('no research allowance remains after charging interrupted calls')
    return dict(schema='cpu-decision-interruption-v1',prior_root=str(root),
        provenance='Maintainer engineering continuation; same logical roles replay their own work, not independent discovery.',
        charged_counters=dict(counts),started=result['started'],roles=roles,
        sources=sources+[reference(root/'result.json'),reference(root/'process-closure.json')],
        scientific_result_from_interruption=False)


def load_wire(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def role_context(recovery,label):
    if label=='master':
        return dict(provenance=recovery['provenance'],own_prior_responses=recovery['roles']['master']['own_responses'],
            interrupted_roles={key:dict(counters=value['counters'],authored_paths=sorted(value['own_scratch']))
                for key,value in recovery['roles'].items() if key!='master'},
            charged_counters=recovery['charged_counters'],limits=LIMITS,
            instruction='同一阶段的工程续接。沿用自己的研究判断，派回原方向并补足运行/修复额度；不必重读已有源码。没有科学反证。')
    own=recovery['roles'].get(label)
    if own is None:
        return dict(provenance=recovery['provenance'],own_prior_work=None)
    return dict(provenance=recovery['provenance'],own_prior_work=own,
        instruction='这是你自己被入口超时中断的代码。通过write_file原样重放或自行修复，再run_python；注明复用，不算新发现。只需必要阅读，搜索也消耗CPU额度。')
