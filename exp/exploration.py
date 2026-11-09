"""File-based bridge for real external agents with a bounded CPU evidence broker."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from agents.exploration import build_evidence,file_sha,object_sha,require_text,references,run_cpu_tool,sources,validate_direction,validate_master,validate_transport
from agents.exploration_prompts import MASTER,DIRECTION,SYNTHESIS


def read(path):
    return json.loads(Path(path).read_text())


def write(path,value):
    with Path(path).open('x') as output:
        json.dump(value,output,indent=2,ensure_ascii=False,allow_nan=False)
        output.write('\n')


def event(root,kind,**values):
    with (root/'events.jsonl').open('a') as output:
        output.write(json.dumps(dict(time_unix=time.time(),event=kind,**values),ensure_ascii=False)+'\n')


def prepare(root,archive):
    root.mkdir(mode=0o700,parents=True,exist_ok=False)
    pin=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','diff','--exit-code',pin,'--','agents','exp/exploration.py','harness/test_p13_exploration.py'],cwd=ROOT,check=True)
    manifest=dict(schema='real-agent-proposal-run-v1',source_pin=pin,source_sha256=sources(),
        source_archive=dict(path=str(archive),sha256=file_sha(archive)),gpu_submissions=0,
        backend='codex-subagent-tool',model_selection='inherited-default',resolved_model_id=None,
        model_identity_limit='exact resolved model and usage are not exposed by the backend',
        context_policy='fresh role prompts; no parent history, file access or direct tools requested; not a filesystem sandbox claim')
    for name in ('requests','responses','tools'):
        (root/name).mkdir()
    write(root/'manifest.json',manifest)
    write(root/'evidence.json',build_evidence(pin))
    event(root,'prepared',evidence_sha256=read(root/'evidence.json')['evidence_sha256'])


def tools_for(root,direction):
    return [read(path) for path in sorted((root/'tools').glob('*.json')) if read(path)['direction_id']==direction]


def make_request(root,name,role,direction_id=None):
    packet=read(root/'evidence.json')
    payload=dict(evidence=packet)
    if role=='master-plan':
        prompt=MASTER
    elif role in ('direction-requests','direction-result'):
        plans=read(root/'responses/master-plan.json')['parsed']['directions']
        matches=[row for row in plans if row['id']==direction_id]
        if len(matches)!=1:
            raise ValueError('direction was not independently selected by the master')
        payload['assigned_direction']=matches[0]
        payload['tool_results']=tools_for(root,direction_id) if role=='direction-result' else []
        if role=='direction-result':
            payload['phase']='return the final direction-result-v1 now; no further tests or implementation'
        prompt=DIRECTION
    elif role=='master-final':
        plan=read(root/'responses/master-plan.json')['parsed']
        payload.update(master_plan=plan,direction_results=[read(root/'responses'/f"{row['id']}-result.json")['parsed'] for row in plan['directions']],
                       tool_results=[read(path) for path in sorted((root/'tools').glob('*.json'))])
        prompt=SYNTHESIS
    else:
        raise ValueError('unknown proposal role')
    prompt+='\nINPUT_JSON:\n'+json.dumps(payload,ensure_ascii=False,sort_keys=True)
    request=dict(name=name,role=role,direction_id=direction_id,evidence_sha256=packet['evidence_sha256'],
        source_pin=read(root/'manifest.json')['source_pin'],prompt=prompt,model_selection='inherited-default')
    request['request_sha256']=object_sha(request)
    return request


def issue(root,name,role,direction_id=None):
    request=make_request(root,name,role,direction_id)
    write(root/'requests'/f'{name}.json',request)
    event(root,'request-issued',name=name,role=role,request_sha256=request['request_sha256'])
    return request


def checked_response(root,name,raw,receipt):
    request=read(root/'requests'/f'{name}.json')
    packet=read(root/'evidence.json')
    validate_transport(receipt,request['request_sha256'])
    completion=receipt['completion_receipt']['status'].get(receipt['agent_id'],{})
    if completion.get('completed')!=raw:
        raise ValueError('response differs from backend completion receipt')
    arguments=receipt['dispatch_arguments']
    if arguments.get('message')!=request['prompt']:
        raise ValueError('backend did not receive the frozen request prompt')
    if request['role'] in ('master-plan','direction-requests'):
        if (receipt['dispatch_tool']!='multi_agent_v1__spawn_agent' or arguments.get('fork_context') is not False or
                'model' in arguments or receipt['dispatch_receipt']['agent_id']!=receipt['agent_id']):
            raise ValueError('role did not start as a fresh inherited-model agent')
    else:
        if receipt['dispatch_tool']!='multi_agent_v1__send_input' or arguments.get('target')!=receipt['agent_id']:
            raise ValueError('followup did not continue the original role agent')
        prior='master-plan' if request['role']=='master-final' else request['direction_id']+'-requests'
        if read(root/'responses'/f'{prior}.json')['receipt']['agent_id']!=receipt['agent_id']:
            raise ValueError('role identity changed between rounds')
    parsed=json.loads(raw)
    role=request['role']
    if role=='master-plan':
        validate_master(parsed,packet)
    elif role=='direction-requests':
        if (parsed.get('schema')!='direction-requests-v1' or parsed.get('direction_id')!=request['direction_id'] or
                parsed.get('evidence_sha256')!=packet['evidence_sha256'] or not isinstance(parsed.get('tests'),list) or len(parsed['tests'])>2):
            raise ValueError('invalid/budget-exceeding direction requests')
        references(parsed['evidence_refs'],packet['evidence'])
        require_text(parsed['hypothesis'])
        require_text(parsed['why'])
    elif role=='direction-result':
        validate_direction(parsed,packet,request['direction_id'],tools_for(root,request['direction_id']))
    else:
        if (parsed.get('schema')!='master-final-v1' or parsed.get('evidence_sha256')!=packet['evidence_sha256'] or
                parsed.get('implementation_ready') is not False or parsed.get('disposition') not in
                ('proposal_pending_validation','closed_with_evidence','needs_more_evidence')):
            raise ValueError('invalid master final or attempted implementation authorization')
        plan=read(root/'responses/master-plan.json')['parsed']
        selected=parsed['selected_direction_ids']
        references(selected,{row['id'] for row in plan['directions']})
        references(parsed['evidence_refs'],packet['evidence'])
        references(parsed['tool_refs'],{read(path)['id'] for path in (root/'tools').glob('*.json')})
        for field in ('rationale','next_stage'):
            require_text(parsed[field])
        if parsed['disposition']=='proposal_pending_validation' and (not selected or any(
                read(root/'responses'/f'{direction}-result.json')['parsed']['proposal'] is None for direction in selected)):
            raise ValueError('master cannot invent a selected candidate proposal')
        if parsed['disposition']=='closed_with_evidence' and (not selected or any(
                read(root/'responses'/f'{direction}-result.json')['parsed']['status']!='closed' for direction in selected)):
            raise ValueError('master cannot close an untested direction')
    return parsed


def accept(root,name,raw_path,receipt_path):
    raw=Path(raw_path).read_text()
    receipt=read(receipt_path)
    parsed=checked_response(root,name,raw,receipt)
    write(root/'responses'/f'{name}.json',dict(raw=raw,parsed=parsed,receipt=receipt))
    event(root,'response-accepted',name=name,agent_id=receipt['agent_id'],raw_sha256=object_sha(raw))


def execute_tools(root,direction):
    response=read(root/'responses'/f'{direction}-requests.json')['parsed']
    if tools_for(root,direction):
        raise ValueError('tools for this direction already executed; no silent retries')
    packet=read(root/'evidence.json')
    for request in response['tests']:
        index=len(list((root/'tools').glob('*.json')))+1
        result=dict(id=f'T{index:03d}',direction_id=direction,request=request)
        try:
            result.update(status='completed',result=run_cpu_tool(packet,request))
        except ValueError as error:
            result.update(status='rejected',reason=str(error))
        write(root/'tools'/f"{result['id']}.json",result)
        event(root,'cpu-tool',id=result['id'],direction=direction,status=result['status'])


def audit(root):
    manifest=read(root/'manifest.json')
    if manifest['schema']!='real-agent-proposal-run-v1' or manifest['source_sha256']!=sources():
        raise ValueError('agent run source drift')
    archive=manifest['source_archive']
    if file_sha(archive['path'])!=archive['sha256']:
        raise ValueError('agent source archive drift')
    with tarfile.open(archive['path']) as snapshot:
        for name,checksum in manifest['source_sha256'].items():
            import hashlib
            if hashlib.sha256(snapshot.extractfile(name).read()).hexdigest()!=checksum:
                raise ValueError('agent execution source differs from frozen archive')
    packet=read(root/'evidence.json')
    if packet!=build_evidence(manifest['source_pin']):
        raise ValueError('agent evidence changed or was not constructed from approved sources')
    responses={}
    for path in sorted((root/'requests').glob('*.json')):
        request=read(path)
        if request!=make_request(root,path.stem,request['role'],request['direction_id']):
            raise ValueError('issued prompt differs from the neutral role/evidence contract')
        claimed=request.pop('request_sha256')
        if claimed!=object_sha(request) or request['evidence_sha256']!=packet['evidence_sha256']:
            raise ValueError('issued request hash changed')
        response=read(root/'responses'/path.name)
        if checked_response(root,path.stem,response['raw'],response['receipt'])!=response['parsed']:
            raise ValueError('parsed agent response was edited')
        responses[path.stem]=response
    plan=responses['master-plan']['parsed']
    direction_ids=[row['id'] for row in plan['directions']]
    expected={'master-plan','master-final'}|{direction+suffix for direction in direction_ids for suffix in ('-requests','-result')}
    if set(responses)!=expected:
        raise ValueError('incomplete or unexpected agent interaction')
    fresh_ids=[responses['master-plan']['receipt']['agent_id']]+[responses[direction+'-requests']['receipt']['agent_id'] for direction in direction_ids]
    if len(set(fresh_ids))!=len(fresh_ids):
        raise ValueError('master/direction contexts were not independently initialized')
    tools=[read(path) for path in sorted((root/'tools').glob('*.json'))]
    for direction in direction_ids:
        requested=responses[direction+'-requests']['parsed']['tests']
        actual=[row for row in tools if row['direction_id']==direction]
        if [row['request'] for row in actual]!=requested:
            raise ValueError('CPU tests differ from the agent-selected requests')
        for row in actual:
            try:
                recomputed=run_cpu_tool(packet,row['request'])
            except ValueError as error:
                if row['status']!='rejected' or row['reason']!=str(error):
                    raise ValueError('CPU rejection result drift')
            else:
                if row['status']!='completed' or row['result']!=recomputed:
                    raise ValueError('CPU experiment result drift')
    return dict(schema=manifest['schema'],source_pin=manifest['source_pin'],evidence_sha256=packet['evidence_sha256'],
        backend=manifest['backend'],model_selection=manifest['model_selection'],resolved_model_id=None,
        backend_identity_limit=manifest['model_identity_limit'],fresh_agents=len(fresh_ids),
        accepted_responses=len(responses),cpu_experiments=len(tools),gpu_submissions=0,
        master_plan=plan,directions=[responses[direction+'-result']['parsed'] for direction in direction_ids],
        master_final=responses['master-final']['parsed'],promoted=False,ledger_eligible=False,
        scope='one real external-agent proposal round; no implementation, performance, novelty or full RSI conclusion')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','issue','accept','tools','audit'))
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--name')
    parser.add_argument('--role')
    parser.add_argument('--direction')
    parser.add_argument('--raw',type=Path)
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    root=args.directory.absolute()
    if args.command=='prepare':prepare(root,args.archive.absolute())
    elif args.command=='issue':issue(root,args.name,args.role,args.direction)
    elif args.command=='accept':accept(root,args.name,args.raw,args.receipt)
    elif args.command=='tools':execute_tools(root,args.direction)
    else:
        result=audit(root)
        write(args.out,result)
        print(json.dumps(dict(audit_passed=True,disposition=result['master_final']['disposition'],gpu_submissions=0)))


if __name__=='__main__':
    main()
