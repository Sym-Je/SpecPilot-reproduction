"""Auditable transport bridge for agent-owned CPU experiments; no GPU authority."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from agents.autonomy import LIMITS,validate_action,validate_budget,validate_plan
from agents.autonomy_prompts import MASTER,DIRECTION,REVIEW
from agents.exploration import build_evidence,file_sha,object_sha,references,require_text,validate_transport
from exp.exploration import read,write
from harness.candidate import check_tree
from harness.experiment_executor import execute_python,local_path

STOCK=Path('/gpfs/users/jixinpeng/specpilot_data/work/engines/h100_c1_qwen38-27b_dflash2-stock')
STOCK_SHA='e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff'
SOURCE_NAMES=('agents/autonomy.py','agents/autonomy_prompts.py','agents/exploration.py','exp/autonomy.py',
    'exp/exploration.py','harness/experiment_executor.py','harness/experiment_worker.py','harness/test_p15_autonomy.py',
    'controller/landlock.py','harness/candidate.py')


def sources():
    return {name:file_sha(ROOT/name) for name in SOURCE_NAMES}


def initial():
    return dict(tasks={},allocated=dict(actions=0,runs=0),used=dict(actions=0,runs=0),reviews=0,finished=False)


def save_state(root,state):
    (root/'state.json').write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')


def tool_rows(root):
    return [read(path) for path in sorted((root/'tools').glob('*.json'))]


def feedback_view(tools,direction=None):
    selected=[row for row in tools if direction is None or row['direction_id']==direction]
    result=[]
    for index,row in enumerate(selected):
        action={key:value for key,value in row['action'].items() if key!='content'} if isinstance(row['action'],dict) else row['action']
        feedback=dict(row['result'])
        if direction is None or index<len(selected)-2:
            feedback.pop('content',None)
        result.append(dict(row,action=action,result=feedback))
    return result


def prepare(root,archive):
    root.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name in ('requests','responses','tools','work','executions'):(root/name).mkdir()
    pin=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    check_tree(STOCK,STOCK_SHA)
    packet=build_evidence(pin)
    packet['evidence'].pop('E005')
    packet['scope']='CPU experiment autonomy smoke; no resumed collection or performance acceptance'
    packet['capabilities'].update(experiment_scripts_allowed=True,gpu_submission_allowed=False)
    packet.pop('evidence_sha256')
    packet['evidence_sha256']=object_sha(packet)
    write(root/'manifest.json',dict(schema='cpu-autonomy-v1',source_pin=pin,source_sha256=sources(),
        archive=dict(path=str(archive),sha256=file_sha(archive)),limits=LIMITS,gpu_budget=0,
        model_selection='inherited-default',resolved_model_id=None,stock=str(STOCK),stock_sha256=STOCK_SHA))
    write(root/'evidence.json',packet)
    save_state(root,initial())


def make_request(root,role,direction,state,tools,number):
    packet=read(root/'evidence.json')
    if state['finished']:raise ValueError('stage already stopped')
    payload=dict(evidence=packet,limits=LIMITS,gpu_budget=0)
    if role=='master-plan':
        if state['tasks']:raise ValueError('master plan already exists')
        prompt=MASTER
    elif role=='direction':
        task=state['tasks'][direction]
        if task['closed']:raise ValueError('direction is not active')
        payload.update(assigned_direction=task,
            feedback=feedback_view(tools,direction),
            files=sorted(task['files']))
        prompt=DIRECTION
    elif role=='master-review':
        if not state['tasks'] or not all(row['closed'] for row in state['tasks'].values()):
            raise ValueError('master review requires all assigned directions to return')
        if state['reviews']>=2:raise ValueError('master review ceiling reached')
        payload.update(state=state,feedback=feedback_view(tools),last_review=state['reviews']==1)
        prompt=REVIEW
    else:raise ValueError('unknown role')
    message=prompt+'\nINPUT_JSON:\n'+json.dumps(payload,ensure_ascii=False,sort_keys=True)
    request=dict(id=f'R{number:03d}',role=role,direction_id=direction,prompt=message,
        evidence_sha256=packet['evidence_sha256'],tool_count=len(tools),source_pin=read(root/'manifest.json')['source_pin'])
    request['request_sha256']=object_sha(request)
    return request


def issue(root,role,direction):
    requests=list((root/'requests').glob('*.json'))
    if len(requests)!=len(list((root/'responses').glob('*.json'))):raise ValueError('pending response exists')
    if requests:
        last=read(sorted(requests)[-1])
        if last['role']=='direction' and not any(row['response_id']==last['id'] for row in tool_rows(root)):
            raise ValueError('previous direction action must execute before another model turn')
    if len(requests)>=32:raise ValueError('model turn budget exhausted')
    request=make_request(root,role,direction,read(root/'state.json'),tool_rows(root),len(requests)+1)
    write(root/'requests'/f"{request['id']}.json",request)
    return request


def checked(root,request,raw,receipt,previous):
    validate_transport(receipt,request['request_sha256'])
    agent=receipt['agent_id']
    if receipt['completion_receipt']['status'].get(agent,{}).get('completed')!=raw:
        raise ValueError('raw response differs from actual completion')
    args=receipt['dispatch_arguments']
    if args.get('message')!=request['prompt'] or 'model' in args:raise ValueError('prompt or inherited model changed')
    key='master' if request['role'].startswith('master') else request['direction_id']
    if key in previous:
        if receipt['dispatch_tool']!='multi_agent_v1__send_input' or args.get('target')!=previous[key]:
            raise ValueError('role was not continued on its original agent')
    elif (receipt['dispatch_tool']!='multi_agent_v1__spawn_agent' or args.get('fork_context') is not False or
            receipt['dispatch_receipt']['agent_id']!=agent or agent in previous.values()):
        raise ValueError('role was not independently initialized')
    if key in previous and previous[key]!=agent:raise ValueError('role identity drift')
    parsed=json.loads(raw)
    if parsed.get('evidence_sha256')!=request['evidence_sha256']:raise ValueError('wrong evidence binding')
    if request['role']=='direction':
        if parsed.get('schema')!='autonomy-direction-v1' or parsed.get('direction_id')!=key:raise ValueError('wrong direction')
        require_text(parsed['hypothesis']);require_text(parsed['why'])
    elif request['role']=='master-plan':
        if parsed.get('schema')!='autonomy-master-plan-v1':raise ValueError('wrong plan schema')
        validate_plan(parsed,read(root/'evidence.json')['evidence'])
    elif parsed.get('schema')!='autonomy-master-review-v1':raise ValueError('wrong review schema')
    return parsed


def apply_master(state,role,parsed):
    if role=='master-plan':
        if state['tasks']:raise ValueError('duplicate master plan')
        for row in parsed['directions']:
            state['tasks'][row['id']]=dict(row,used=dict(actions=0,runs=0),files={},closed=False)
        state['allocated']={key:sum(row['budget'][key] for row in parsed['directions']) for key in LIMITS}
    else:
        decisions=parsed['decisions']
        if len(decisions)!=len(state['tasks']) or {row['direction_id'] for row in decisions}!=set(state['tasks']):
            raise ValueError('master must decide every assigned direction')
        for row in decisions:
            require_text(row['reason'])
            validate_budget(row['extra_budget'])
            task=state['tasks'][row['direction_id']]
            task['master_feedback']=row['reason']
            if row['decision']=='continue' and state['reviews']==0:
                for key in LIMITS:
                    state['allocated'][key]+=row['extra_budget'][key]
                    task['budget'][key]+=row['extra_budget'][key]
                task['closed']=False
            elif row['decision']=='stop' and not any(row['extra_budget'].values()):pass
            else:raise ValueError('invalid continuation or final review must stop')
        if any(state['allocated'][key]>limit for key,limit in LIMITS.items()):raise ValueError('master exceeded stage allocation')
        state['reviews']+=1
        state['finished']=all(row['closed'] for row in state['tasks'].values())


def accept(root,name,raw_path,receipt_path):
    request=read(root/'requests'/f'{name}.json')
    previous={}
    for path in sorted((root/'responses').glob('*.json')):
        row=read(path)
        req=read(root/'requests'/path.name)
        previous['master' if req['role'].startswith('master') else req['direction_id']]=row['receipt']['agent_id']
    raw=Path(raw_path).read_text()
    receipt=read(receipt_path)
    parsed=checked(root,request,raw,receipt,previous)
    state=read(root/'state.json')
    if request['role'].startswith('master'):apply_master(state,request['role'],parsed)
    write(root/'responses'/f'{name}.json',dict(raw=raw,parsed=parsed,receipt=receipt))
    if request['role']=='master-plan':
        for direction in state['tasks']:
            work=root/'work'/direction
            (work/'inputs').mkdir(parents=True)
            write(work/'inputs/evidence.json',read(root/'evidence.json'))
    save_state(root,state)


def run_action(root,direction,action,number):
    validate_action(action)
    work=root/'work'/direction
    kind=action['kind']
    if kind in ('read_file','write_file','run_python'):
        path=local_path(work,action['path'])
        if kind=='write_file':
            if Path(action['path']).parts[0]=='inputs' or path.suffix not in ('.py','.json','.txt'):
                raise ValueError('only experiment files may be written; inputs are immutable')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(action['content'])
            return dict(status='completed',sha256=file_sha(path),bytes=path.stat().st_size)
        if kind=='read_file':
            return dict(status='completed',content=path.read_text()[:12000],sha256=file_sha(path))
        return execute_python(work,action['path'],root/'executions'/f'T{number:03d}')
    if kind in ('list_stock','read_stock'):
        path=local_path(STOCK,action['prefix'] if kind=='list_stock' else action['path'])
        if kind=='list_stock':
            files=sorted(str(row.relative_to(STOCK)) for row in path.rglob('*.py') if row.is_file() and not row.is_symlink())
            return dict(status='completed',files=files[action['offset']:action['offset']+80],total=len(files))
        if path.suffix!='.py':raise ValueError('only stock Python source is exposed')
        content=path.read_text()
        return dict(status='completed',content=content[action['offset']:action['offset']+12000],total=len(content),sha256=file_sha(path))
    return dict(status='returned',disposition=action['disposition'])


def account(state,direction,action,result,tools):
    task=state['tasks'][direction]
    kind=action.get('kind') if isinstance(action,dict) else None
    if kind=='finish' and result['status']=='returned':
        references(action['tool_refs'],{row['id'] for row in tools if row['direction_id']==direction})
        task['closed']=True
        task['conclusion']=action
        return
    task['used']['actions']+=1;state['used']['actions']+=1
    if kind=='run_python' and result.get('code_sha256'):
        task['used']['runs']+=1;state['used']['runs']+=1
    if kind=='write_file' and result['status']=='completed':task['files'][action['path']]=result['sha256']
    if task['used']['actions']>=task['budget']['actions']:
        task['closed']=True
        task['conclusion']=dict(disposition='needs_evidence',observations='allocated action budget exhausted')


def execute(root,name):
    response=read(root/'responses'/f'{name}.json')
    request=read(root/'requests'/f'{name}.json')
    if request['role']!='direction':raise ValueError('only a direction can request experiment actions')
    tools=tool_rows(root)
    if any(row['response_id']==name for row in tools):raise ValueError('action already executed')
    state=read(root/'state.json');direction=request['direction_id'];task=state['tasks'][direction]
    action=response['parsed']['action']
    if task['closed']:raise ValueError('direction is not active')
    try:
        validate_action(action)
        if action['kind']!='finish' and task['used']['actions']>=task['budget']['actions']:raise ValueError('action budget exhausted')
        if action['kind']=='run_python' and task['used']['runs']>=task['budget']['runs']:raise ValueError('CPU run budget exhausted')
        if action['kind']=='finish':references(action['tool_refs'],{row['id'] for row in tools if row['direction_id']==direction})
        result=run_action(root,direction,action,len(tools)+1)
    except (ValueError,OSError) as error:
        result=dict(status='rejected',reason=str(error))
    account(state,direction,action,result,tools)
    record=dict(id=f'T{len(tools)+1:03d}',response_id=name,direction_id=direction,action=action,result=result)
    write(root/'tools'/f"{record['id']}.json",record)
    save_state(root,state)
    return record


def audit(root):
    manifest=read(root/'manifest.json')
    if manifest['source_sha256']!=sources() or manifest['limits']!=LIMITS or manifest['gpu_budget']!=0:
        raise ValueError('executor source or authorization drift')
    archive=manifest['archive']
    if file_sha(archive['path'])!=archive['sha256']:raise ValueError('source archive changed')
    with tarfile.open(archive['path']) as snapshot:
        for name,checksum in manifest['source_sha256'].items():
            if hashlib.sha256(snapshot.extractfile(name).read()).hexdigest()!=checksum:raise ValueError('archived source mismatch')
    check_tree(STOCK,STOCK_SHA)
    packet=read(root/'evidence.json')
    unhashed=dict(packet);unhashed.pop('evidence_sha256')
    if packet['evidence_sha256']!=object_sha(unhashed):raise ValueError('evidence checksum changed')
    state=initial();previous={};seen=[];runs=[];followups=0
    tools=tool_rows(root)
    paths=sorted((root/'responses').glob('*.json'))
    if len(paths)!=len(list((root/'requests').glob('*.json'))):raise ValueError('pending or missing model response')
    for number,path in enumerate(paths,1):
        response=read(path);request=read(root/'requests'/path.name)
        if path.stem!=f'R{number:03d}' or request['id']!=path.stem:raise ValueError('interaction sequence changed')
        if request!=make_request(root,request['role'],request['direction_id'],state,seen,number):raise ValueError('issued prompt changed')
        parsed=checked(root,request,response['raw'],response['receipt'],previous)
        if parsed!=response['parsed']:raise ValueError('edited parsed response')
        key='master' if request['role'].startswith('master') else request['direction_id']
        previous[key]=response['receipt']['agent_id']
        if request['role'].startswith('master'):apply_master(state,request['role'],parsed);continue
        direction=request['direction_id']
        if any(row['direction_id']==direction for row in runs):followups+=1
        matching=[row for row in tools if row['response_id']==request['id']]
        if len(matching)!=1:raise ValueError('missing or duplicate executed action')
        tool=matching[0]
        if tool['action']!=parsed['action'] or tool['direction_id']!=direction:raise ValueError('executor changed the agent action')
        action,result=tool['action'],tool['result']
        if not isinstance(action,dict):
            if result['status']!='rejected':raise ValueError('malformed action was executed')
            account(state,direction,action,result,seen);seen.append(tool);continue
        if action.get('kind') in ('read_stock','list_stock') and result['status']=='completed':
            if run_action(root,direction,action,0)!=result:raise ValueError('stock read feedback edited')
        if action.get('kind')=='write_file' and result['status']=='completed':
            if hashlib.sha256(action['content'].encode()).hexdigest()!=result['sha256']:raise ValueError('executor rewrote agent code')
        if action.get('kind')=='run_python' and result.get('code_sha256'):
            task=state['tasks'][direction]
            if task['used']['runs']>=task['budget']['runs'] or task['used']['actions']>=task['budget']['actions']:
                raise ValueError('direction exceeded its allocation')
            record=root/'executions'/tool['id']
            if result!=read(record/'result.json'):raise ValueError('execution feedback edited')
            for stream,checksum in result['output_sha256'].items():
                if file_sha(record/stream)!=checksum:raise ValueError('raw execution output edited')
                payload=(record/stream).read_bytes()
                text=payload.removeprefix(b'SP_ISOLATION_READY\n') if stream=='stderr' else payload
                if text[:12000].decode(errors='replace')!=result[stream] or len(payload)!=result['output_bytes'][stream]:
                    raise ValueError('output feedback differs from raw process bytes')
            if state['tasks'][direction]['files'].get(action['path'])!=result['code_sha256']:raise ValueError('executed code not authored by this direction')
            if not result['landlock_applied'] or not result['seccomp_applied']:raise ValueError('isolation did not apply')
            runs.append(dict(direction_id=direction,tool_id=tool['id'],exit_code=result['exit_code']))
        account(state,direction,action,result,seen);seen.append(tool)
        if any(state['used'][key]>limit for key,limit in LIMITS.items()):raise ValueError('stage exceeded execution ceiling')
    if len(seen)!=len(tools) or state!=read(root/'state.json') or not state['finished']:raise ValueError('incomplete or inconsistent stage')
    return dict(schema='autonomy-audit-v1',source_pin=manifest['source_pin'],
        engineering_loop_passed=bool(runs and followups and state['reviews']),real_cpu_runs=runs,
        direction_followups_after_execution=followups,master_reviews=state['reviews'],
        allocated=state['allocated'],used=state['used'],directions={key:row.get('conclusion') for key,row in state['tasks'].items()},
        actual_role_agents=previous,gpu_submissions=0,promoted=False,ledger_eligible=False,
        end_to_end_gain=None,model_selection='inherited-default',resolved_model_id=None,
        scope='agent-owned CPU experiment execution only; not GPU exploration, optimization discovery or paper reproduction')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','issue','accept','execute','audit','state'))
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--role',choices=('master-plan','direction','master-review'))
    parser.add_argument('--direction')
    parser.add_argument('--name')
    parser.add_argument('--raw',type=Path)
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();root=args.directory.absolute()
    if args.command=='prepare':prepare(root,args.archive.absolute())
    elif args.command=='issue':print(json.dumps(issue(root,args.role,args.direction),ensure_ascii=False))
    elif args.command=='accept':accept(root,args.name,args.raw,args.receipt)
    elif args.command=='execute':print(json.dumps(execute(root,args.name),ensure_ascii=False))
    elif args.command=='state':print(json.dumps(read(root/'state.json'),ensure_ascii=False))
    else:
        result=audit(root)
        if args.out:write(args.out,result)
        print(json.dumps(result,ensure_ascii=False))
