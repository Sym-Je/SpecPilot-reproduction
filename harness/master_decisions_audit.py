"""Independent replay of CPU research decisions, native roles and actual feedback."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time
import tempfile

from controller.phase4_final import trusted_metadata, validate_shutdown
from exp import autonomy
from exp.phase4_run import reference
from exp.source_resource import feedback as replay_source_feedback
from harness.decision_evidence import load, verify as verify_evidence
from harness.master_autonomy_audit import KINDS, replay_tool
from harness.master_decisions import DecisionState, LIMITS, MASTER_ALLOCATION
from harness.master_research import MasterAccess
from harness.research_protocol import CPU_ACTIONS
from harness import skill_rsi_audit as native


def require(condition,message):
    if not condition:
        raise ValueError(message)


def replay_journal(evidence,journal,response):
    state=DecisionState(evidence['initial'])
    for record in journal:
        kind=record['kind']
        if kind in ('decision','rejected'):
            action=response(record['response'])
            if kind=='decision':
                state.apply(action)
            else:
                try:
                    state.apply(action)
                except (ValueError,TypeError,KeyError) as error:
                    require(str(error)==record['reason'],'actual decision rejection reason differs')
                else:
                    raise ValueError('valid native decision falsely relabeled rejected')
        elif kind=='historical_feedback':
            require(bool(state.opportunities) and record['source']==evidence['feedback_source'],
                'historical feedback was invented, replaced or delivered before comparison')
            state.deliver('historical-feedback',evidence['historical_feedback'],source=record['source'])
        elif kind=='direction_feedback':
            require(response(record['response'])==record['value'],'CPU direction feedback differs from native answer')
            state.return_direction(record['id'],record['value'],record['used'])
        else:
            raise ValueError('unrecognized research journal event')
    return state


def role_action_limits(root,directory,journal):
    limits={}; allocated=MASTER_ALLOCATION['actions'] if directory.name=='master' else 0
    used=0; last=0
    if directory.name=='master':
        through=len(list(directory.glob('turn-*-native.json')))
        actions=[through]
    else:
        actions=[]
        for record in journal:
            if record['kind']=='decision':
                action=load(record['response']['path'])
                if action.get('kind') in ('dispatch','continue') and 'direction-'+action['id']==directory.name:
                    allocated+=action['allocation']['actions']
            if record['kind']=='direction_feedback' and 'direction-'+record['id']==directory.name:
                through=int(Path(record['response']['path']).name.split('-')[1])
                for number in range(last+1,through+1):
                    limits[number]=allocated-used
                    used+=len(list((directory/f'tools-{number:02d}').glob('action-*/request.json')))
                last=through
        return limits
    for number in range(1,actions[0]+1):
        limits[number]=allocated-used
        used+=len(list((directory/f'tools-{number:02d}').glob('action-*/request.json')))
    return limits


def verify_runtime_sources(root,manifest,repository):
    snapshot=root/'runtime-source'
    source=snapshot if snapshot.exists() else repository
    changed=[]
    for name,digest in manifest['source_sha256'].items():
        require(reference(source/name)['sha256']==digest,'loaded research source identity changed: '+name)
        if reference(repository/name)['sha256']!=digest:
            changed.append(name)
    return dict(launch_sources_verified=True,archived_launch_sources=source==snapshot,
        post_run_modified_sources=sorted(changed))


def verify_master_feedback(directory,turn,identity,packet):
    require(turn is not None,'feedback has no preceding native Master decision')
    prompt=load(directory/f'turn-{turn+1:02d}-request.json')['prompt']
    payload=json.JSONDecoder().raw_decode(prompt[prompt.index('{'):])[0]
    require(payload['evidence'].get(identity)==packet,
        'feedback was recorded but never delivered to the real Master: '+identity)


def audit(root):
    root=Path(root).resolve()
    manifest=load(root/'manifest.json')
    require(manifest['schema']=='cpu-master-decisions-v1' and manifest['gpu_budget']==0 and manifest['limits']==LIMITS,
        'CPU-only authorization/limits changed')
    require(reference(root/'evidence.json')==manifest['evidence'],'frozen public evidence packet changed')
    evidence=verify_evidence(root)
    from exp.gpu_autonomy import ROOT
    runtime_sources=verify_runtime_sources(root,manifest,ROOT)
    previous=Path(evidence['previous_request']['path'])
    replay=replay_source_feedback(previous.parent/'remote',load(previous))
    for key,value in replay.items():
        actual=evidence['historical_feedback']
        if key in actual:
            require(actual[key]==value,'historical measurement differs from independent controller replay')
    roles=[]; responses={}; totals=Counter(); tool_replays=Counter()
    journal=load(root/'journal.json')
    directories=[root/'master',*sorted(root.glob('direction-*'))]
    for directory in directories:
        role,values,origins=native.audit_role(root,directory,allow_format_retries=True,
            action_limits=role_action_limits(root,directory,journal))
        require(role['kind']==('Master' if directory.name=='master' else 'direction'),'unexpected scientific role')
        roles.append(role); totals.update(role['counts'])
        if directory.name=='master':
            packet=load(Path(load(directory/'manifest.json')['work'])/'inputs/evidence.json')
            require(packet.get('evidence')==evidence['initial'] and packet.get('gpu_budget')==0,
                'Master initial context contains unauthorized or prematurely revealed evidence')
        for ordinal,value in values.items():
            path=directory/f'turn-{ordinal[1]:02d}-response.json'
            responses[str(path)]=value
        access=MasterAccess(role['kind'],{'stock':root/'inputs/stock-profile.json'},root/'inputs/tools.json',root/'skill-cache',
            baseline_loader=lambda:load(root/'inputs/baseline.json'),stock=autonomy.STOCK)
        for path in sorted(directory.glob('tools-*/action-*/request.json')):
            action=load(path)['arguments']['action']; returned=load(path.parent/'response.json')
            if action.get('kind') in KINDS and returned['success']:
                answer=json.loads(returned['contentItems'][0]['text'])
                replay_tool(action,answer,path.parent/'execution',access)
                tool_replays[action['kind']]+=1
            if action.get('kind') in ('read_kernel_links','read_profile_shapes') and returned['success']:
                answer=json.loads(returned['contentItems'][0]['text'])
                require(load(path.parent/'execution/result.json')==answer,'recorded profile observation differs')
                with tempfile.TemporaryDirectory(prefix='stock-observation-audit-') as temporary:
                    expected=access.dispatch(Path(temporary),action,Path(temporary)/'execution')
                require(answer==expected,'profile observation differs from authorized trace replay')
                tool_replays[action['kind']]+=1
    require(len({role['thread'] for role in roles})==len(roles),'native thread crossed research roles')
    used_responses=set()
    def response(identity):
        path=Path(identity['path'])
        require(str(path) in responses and reference(path)==identity,'journal lacks exact native response provenance')
        require(str(path) not in used_responses,'native response reused for two decisions or feedbacks')
        used_responses.add(str(path))
        return responses[str(path)]['value']
    previous_master_turn=None; direction_returns=Counter()
    for index,record in enumerate(journal):
        if record['kind'] in ('decision','rejected','direction_feedback'):
            source=responses.get(record['response']['path'])
            expected='direction-'+record['id'] if record['kind']=='direction_feedback' else 'master'
            require(source is not None and source['role']==expected,'journal response crossed scientific roles')
            if expected=='master':
                previous_master_turn=int(Path(record['response']['path']).name.split('-')[1])
            if record['kind']=='decision' and source['value']['kind']=='dispatch':
                action=source['value']
                prior=replay_journal(evidence,journal[:index],lambda identity:responses[identity['path']]['value'])
                selected=set(action['based_on'])|set(prior.opportunities[action['id']]['evidence'])
                packet=dict(assignment=prior.opportunities[action['id']],brief=action['brief'],gpu_budget=0,
                    shared_evidence={key:prior.evidence[key] for key in sorted(selected)},
                    provenance='Master explicitly shared selected facts/results only; no other role private history')
                directory=root/('direction-'+action['id'])
                actual_packet=load(Path(load(directory/'manifest.json')['work'])/'inputs/evidence.json')
                budgeted_packet=dict(packet,allocation=action['allocation'],remaining=action['allocation'])
                require(actual_packet in (packet,budgeted_packet),'Direction received unauthorized assignment/evidence/context')
        if record['kind']=='historical_feedback':
            expected_packet=dict(value=evidence['historical_feedback'],source=evidence['feedback_source'],historical_reuse=True)
            verify_master_feedback(root/'master',previous_master_turn,'historical-feedback',expected_packet)
        elif record['kind']=='direction_feedback':
            direction_returns[record['id']]+=1
            identity='direction-'+record['id']+'-'+str(direction_returns[record['id']]).zfill(2)
            verify_master_feedback(root/'master',previous_master_turn,identity,
                dict(value=record['value'],historical_reuse=False))
    state=replay_journal(evidence,journal,response)
    require(state.snapshot()==load(root/'state.json'),'decision state differs from independent journal replay')
    require(used_responses==set(responses),'orphan native decision or direction return')
    result=load(root/'result.json'); counts=load(root/'counters.json')
    require(result['counters']==counts and all(counts[key]==totals[key] for key in counts),'actual native counters differ')
    require(all(type(counts[key]) is int and counts[key]<=LIMITS[key] for key in ('actions','cpu_runs','model_turns')) and
        counts['usage_updates']<=512,'stage budget exceeded')
    require(0<=result['finished']-result['started']<=LIMITS['wall_seconds'],'CPU stage exceeded wall limit')
    for role in roles:
        if role['kind']=='Master':
            allocation=MASTER_ALLOCATION
        else:
            direction=state.directions[role['name'].removeprefix('direction-')]
            allocation=direction['allocated']
            require(all(direction['used'][key]==role['counts'][key] for key in ('actions','cpu_runs')),
                'direction actual actions/CPU differ from its returned feedback')
        require(all(role['counts'][key]<=allocation[key] for key in ('actions','cpu_runs')),'role allocation reset or exceeded')
    closure=load(root/'process-closure.json'); owner=(root/'process-closure.json').stat().st_uid
    require(closure.get('role_processes_closed') is True,'research processes not closed')
    registry=trusted_metadata(closure['shutdown_registry'],owner)
    validate_shutdown(registry,broker_uid=owner,opened_unix=time.time())
    require(registry['members']==closure['process_members'],'actual process inventory changed')
    exits={}
    for member in registry['members']:
        birth=trusted_metadata(member['birth'],owner); ended=trusted_metadata(member['exit'],owner)
        require(ended['returncode']==0 and result['started']<=birth['observed_unix']<=ended['reaped_unix']<=
            registry['closed_unix']<=result['started']+LIMITS['wall_seconds'],'CPU process exit/chronology differs')
        exits[birth['identity']['pid']]=ended['returncode']
    recorded={Path(member[field]['path']).resolve() for member in registry['members'] for field in ('birth','exit')}
    actual={path.resolve() for pattern in ('birth-*.json','exit-*.json') for path in (root/'processes').rglob(pattern)}
    require(recorded==actual,'orphan or omitted CPU process receipt')
    require(set(result['role_processes'])=={role['name'] for role in roles} and all(
        exits.get(item['pid'])==item['exit_code']==0 for item in result['role_processes'].values()),'role exits lack actual wait receipts')
    require(result['gpu_submissions']==0 and result['scientific_optimization_completed'] is False and
        not list(root.glob('*/pending.json')) and not list(root.glob('*/submitted.json')),'CPU rehearsal claims GPU authority or optimization')
    require(result['status']=='research_stopped' and state.stopped,'CPU decision rehearsal has not stopped normally')
    priorities=[]
    for event in state.events:
        if event['kind']=='decision' and event['action']['kind'] in ('compare','revise'):
            priorities.append({card['id']:card['priority'] for card in event['action']['opportunities']})
    return dict(engineering_evidence_verified=True,native_roles=len(roles),native_turns=totals['model_turns'],
        tool_actions=totals['actions'],python_executions=totals['python_executions'],skill_calls=totals['skill_calls'],
        denied_tool_attempts=totals['budget_rejections'],
        historical_feedback_delivered='historical-feedback' in state.evidence,opportunity_comparisons=len(priorities),
        ranking_changed=len(priorities)>1 and priorities[0]!=priorities[-1],revisions=state.revisions,
        direction_returns=sum(value['returns'] for value in state.directions.values()),
        direction_continuations=sum(event['kind']=='decision' and event['action']['kind']=='continue' for event in state.events),
        verified_processes=len(registry['members']),tool_replays=dict(tool_replays),gpu_submissions=0,
        runtime_sources=runtime_sources,
        scientific_optimization_completed=False,scientific_decision_quality_not_automatically_certified=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.root),sort_keys=True,allow_nan=False))


if __name__=='__main__':
    main()
