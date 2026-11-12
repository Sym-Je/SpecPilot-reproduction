"""Independent replay of the broad-access campaign, never a scientific controller."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time

from controller.phase4_final import trusted_metadata,validate_shutdown
from exp import autonomy
from exp.master_open import LIMITS,validate_open_plan
from exp.phase4_run import reference
from exp.source_resource import feedback as source_feedback
from harness.decision_evidence import verify as verify_evidence
from harness.master_autonomy_audit import replay_tool
from harness.open_research import OpenAccess,record_authored_text
from harness.skill_rsi_audit import audit_role
from harness.gpu_autonomy import job_rows


def load(path):return json.loads(Path(path).read_text())


def require(condition,message):
    if not condition:raise ValueError(message)


def workspace_read(action,work,contents):
    content=contents.get(action['path'])
    if content is None:
        path=Path(work)/action['path'];content=path.read_text();digest=reference(path)['sha256']
    else:digest=hashlib.sha256(content.encode()).hexdigest()
    offset=action.get('offset',0);end=min(len(content),offset+12000)
    return dict(status='completed',content=content[offset:end],sha256=digest,
        offset=offset,total_chars=len(content),next_offset=end if end<len(content) else None)


def verify_export(index,parent,*,owner_thread=None):
    index=Path(index).resolve();parent=Path(parent).resolve();value=load(index)
    require(value['schema']=='authorized-runtime-export-v1','unknown execution export')
    source=parent/value['experiment']
    require(source.parent==parent and source.is_dir(),'export does not belong to authorized stage')
    request=load(source/'request.json')
    require(value.get('owner_thread')==request.get('role_thread'),'export ownership differs')
    if owner_thread is not None:
        require(request.get('role_thread')==owner_thread,'export crossed Direction ownership')
    seen=set()
    for row in value['files']:
        name=Path(row['path'])
        require(not name.is_absolute() and '..' not in name.parts and name.as_posix() not in seen,
            'export path is not unique and relative')
        seen.add(name.as_posix())
        require(reference(source/name)==row['source'] and
            reference(index.parent/name)['sha256']==row['source']['sha256'],'exported runtime evidence changed')
    return len(seen)


def audit_observability_stop(parent):
    from harness.source_replay import verify_replay,replay_text
    parent=Path(parent).resolve();original=audit(parent)
    root=parent/'observability-continuation';metadata=load(root/'continuation.json')
    pipeline=load(parent/'pipeline-result.json');result=load(root/'result.json')
    require(metadata['budget_reset'] is False and Path(metadata['original_budget']).resolve()==parent/'resource-state.json'
        and metadata['prior_counters']=={key:pipeline['counters'][key] for key in
            ('actions','cpu_runs','gpu_attempts','model_turns','usage_updates')},'continuation reset original budget or counters')
    require(result['status']=='completed' and result['resource_state']==pipeline['resource_state'] and
        not result['controller_accepted'] and not result['candidate_promoted'] and
        result['closed_role_processes']==[0] and result['immutable_role_inputs']==[True],
        'observability-only stop is not a clean unchanged scientific result')
    require(not list(root.glob('direction-*')) and not list(root.glob('*/request.json')),
        'stop-only audit cannot certify additional research or GPU execution')
    directory=root/'master';manifest=load(directory/'manifest.json');work=Path(manifest['work'])
    replay=manifest['own_replay'];verify_replay(replay,'Master')
    require(Path(replay['source_role']['path']).resolve()==parent/'master/manifest.json',
        'Master restored another role context')
    role,responses,_=audit_role(root,directory,allow_format_retries=True)
    final=load(root/'master-decision-01.json')
    require(final.get('decision')=='stop' and final==result['master_decision'] and
        any(row['value']==final for row in responses.values()),'stop is not the actual native Master answer')
    packet=load(work/'inputs/evidence.json')
    require(packet['original_master_plan']==load(parent/'master-plan.json') and
        packet['original_master_final']==pipeline['master_final'] and packet['original_stages']==pipeline['stages'],
        'original decisions or shared research changed during continuation')
    require(packet['own_previous_responses']==[load(path) for path in sorted((parent/'master').glob('turn-*-response.json'))],
        'own native Master history differs')
    contents={name:replay_text(name,row,replay['source_wire']) for name,row in replay['files'].items()}
    reads=0
    for path in sorted(directory.glob('tools-*/action-*/request.json')):
        action=load(path)['arguments']['action'];returned=load(path.parent/'response.json')
        if not returned['success']:continue
        answer=json.loads(returned['contentItems'][0]['text'])
        require(action['kind'] in ('help','read_file'),'stop-only replay has an unverified action')
        if action['kind']!='read_file':continue
        expected=workspace_read(action,work,contents)
        require(answer==expected,'authorized execution log read differs from actual native feedback')
        reads+=1
    exports=[verify_export(path,parent) for path in sorted((work/'inputs/authorized-runtime').glob('*/index.json'))]
    expected=dict(metadata['prior_counters'])
    for key in ('actions','cpu_runs','model_turns','usage_updates'):expected[key]+=role['counts'].get(key,0)
    require(expected==result['counters']==load(root/'counters.json'),'cumulative counters differ from independent native recount')
    registry=load(root/'process-closure.json')['shutdown_registry']
    processes=validate_shutdown(trusted_metadata(registry,Path(registry['path']).stat().st_uid),
        broker_uid=Path(registry['path']).stat().st_uid,opened_unix=time.time())
    return dict(original=original,observability_continuation=dict(normal_native_stop=True,
        runtime_exports_verified=len(exports),exported_files_verified=sum(exports),native_workspace_reads_verified=reads,
        counters=expected,new_gpu_jobs=0,process_exits_verified=processes,
        independent_discovery=False,controller_gate_jobs=0,sealed_used=False,candidate_promoted=False))


def audit(root):
    root=Path(root).resolve();manifest=load(root/'manifest.json')
    require(manifest['schema']=='broad-master-research-v1' and manifest['limits']==LIMITS,
        'campaign authorization or protocol differs')
    require(manifest['controller_immutable'] is True and manifest['sealed_authorized'] is False,
        'scientific boundary differs')
    modified=[]
    repository=Path(__file__).resolve().parents[1]
    for name,source in manifest['launch_sources'].items():
        require(reference(source['path'])==source,'launch source snapshot changed')
        if reference(repository/name)['sha256']!=source['sha256']:modified.append(name)
    verify_evidence(root)
    pipeline=load(root/'pipeline-result.json')
    require(pipeline['status']=='research_complete','native research has not completed normally')
    require(not pipeline['sealed_completed'] and not pipeline['promoted'],'unexpected sealed or promotion claim')
    resource=load(root/'resource-state.json')
    require(all(resource[key]==value for key,value in LIMITS.items()),'resource ceilings changed')
    require(all(row.get('terminated') and row.get('create_calls')==1 for row in resource['jobs']),
        'GPU jobs still active or submission uncertain')
    charged=sum(row['charged_gpu_seconds'] for row in resource['jobs'])
    require(charged<=LIMITS['gpu_seconds'],'GPU budget exceeded')
    require(pipeline['resource_state']==resource,'pipeline and actual resource state differ')
    roles=[];responses={};cpu_origins={};counts=dict(actions=0,cpu_runs=0,model_turns=0,usage_updates=0)
    tools_replayed=0
    for directory in [root/'master',*sorted(root.glob('direction-*')),root/'integration',root/'kernel']:
        if not directory.is_dir():continue
        role,values,origins=audit_role(root,directory,allow_format_retries=True)
        roles.append(role);responses.update(values);cpu_origins.update(origins)
        for key in counts:counts[key]+=role['counts'].get(key,0)
        own=load(directory/'manifest.json');work=Path(own['work']);contents={}
        for name,key in ((own['canary'],'canary_sha256'),(work/'inputs/rules.txt','rules_sha256'),
                (work/'inputs/evidence.json','evidence_sha256'),(Path(own['home'])/'config.toml','config_sha256')):
            require(reference(name)['sha256']==own[key],'immutable role input changed')
        evidence={'stock':root/'inputs/stock-profile.json'}
        evidence.update({path.stem:path for path in (root/'profile-evidence'/directory.name).glob('*.json')})
        access=OpenAccess(own['role'],evidence,root/'inputs/tools.json',root/'skill-cache',stock=autonomy.STOCK,
            baseline_loader=lambda:load(root/'inputs/baseline.json'))
        for path in sorted(directory.glob('tools-*/action-*/request.json')):
            action=load(path)['arguments']['action'];response=load(path.parent/'response.json')
            if not response['success']:continue
            answer=json.loads(response['contentItems'][0]['text']);kind=action['kind']
            if kind in ('read_stock','list_stock','search_stock'):
                require(answer==access.source_action(action),'authorized stock source result changed')
                tools_replayed+=1
            elif kind in ('search_public','read_public','get_baseline_stats','estimate_scenario'):
                replay_tool(action,answer,path.parent/'execution',access);tools_replayed+=1
            elif kind in ('write_file','append_file'):
                record_authored_text(action,answer,contents)
            elif kind=='read_file':
                expected=workspace_read(action,work,contents)
                require(answer==expected,'workspace read differs from original authored/input content')
                tools_replayed+=1
    plan=load(root/'master-plan.json');validate_open_plan(plan)
    require(any(row['value']==plan and row['role']=='master' for row in responses.values()),
        'opportunity plan is not the actual native Master answer')
    jobs=[];source_requests=[]
    for reservation in resource['jobs']:
        directory=root/reservation['name'];request=load(directory/'request.json')
        pending=load(directory/'pending.json');submitted=load(directory/'submitted.json')
        lifecycle=load(directory/'lifecycle-final.json')
        require(submitted['code']==200 and submitted['uuid']==reservation['uuid']==lifecycle['uuid'],
            'task UUID or service submission acknowledgement differs')
        require(lifecycle['conservative_gpu_seconds']==reservation['charged_gpu_seconds'] and
            lifecycle['pods'] and all('finished_at' in row for row in lifecycle['pods'].values()),
            'terminal process or resource accounting differs')
        matches=job_rows((directory/'post-submit-query.txt').read_text(),reservation['name'])
        require(len(matches)==1 and matches[0].get('name')==reservation['uuid'],'task has no unique exact lookup')
        require(pending['request_sha256']==reference(directory/'request.json')['sha256'] and
            pending['source_sha256']==reference(directory/'source.tar')['sha256'],'submitted execution identity changed')
        identity=load(directory/'source-identity.json')
        with tarfile.open(directory/'source.tar') as archive:
            for name,digest in identity['files'].items():
                require(hashlib.sha256(archive.extractfile(name).read()).hexdigest()==digest,'frozen execution source changed')
        admission=load(directory/'trusted-admission.json');displayed=load(directory/'admission-plan.json')
        require(admission==dict(approved=True,plan=displayed) and displayed['source']==reference(directory/'source.tar') and
            displayed['request']==reference(directory/'request.json'),'trusted admission does not bind actual source and request')
        feedback=load(directory/'feedback.json')
        if feedback.get('status')=='completed':
            if request.get('mode')=='stock-profile':
                from exp.profile_resource import feedback as profile_feedback
                replay=profile_feedback(directory/'remote',request)
            else:replay=source_feedback(directory/'remote',request)
            require(feedback==dict(replay,status='completed',uuid=reservation['uuid']),
                'GPU feedback differs from independent raw-result replay')
        jobs.append(dict(name=directory.name,uuid=reservation['uuid'],gpus=reservation['gpus'],
            mode=request['mode'],status=feedback['status'],gpu_seconds=reservation['charged_gpu_seconds']))
    for path in sorted(root.glob('*/request.json')):
        request=load(path)
        if request.get('mode')!='source-research':continue
        directory=path.parent;receipt=load(directory/'cpu-receipt.json');origin=cpu_origins.get(receipt['path'])
        require(origin is not None and origin['value']['exit_code']==0,'source request lacks successful native CPU origin')
        require(reference(receipt['path'])['sha256']==receipt['sha256'] and
            reference(directory/'patch.json')['sha256']==request['patch_sha256'] and
            reference(directory/'self-check.py')['sha256']==request['self_check_sha256'] and
            reference(directory/'cpu-receipt.json')['sha256']==request['cpu_receipt_sha256'],
            'scientific source or CPU receipt changed')
        action=request['action'];original=responses.get((request['role_thread'],request['role_turn']))
        require(original is not None and original['sha256']==request['role_response_sha256'] and
            original['value'].get('action')==action and origin['value']['code_sha256']==request['self_check_sha256'] and
            origin['value']['workspace_file_sha256'].get(action['patch'])==request['patch_sha256'],
            'scientific candidate is not bound to actual Direction authorship')
        source_requests.append(directory.name)
    profile_requests=load(root/'profile-requests.json') if (root/'profile-requests.json').exists() else []
    expected=dict(counts,actions=counts['actions']+len(source_requests)+len(profile_requests),
        gpu_attempts=len(source_requests),controller_jobs=sum(row['mode']=='source-controller' for row in jobs))
    require(pipeline['counters']==expected,'campaign counters differ from actual native actions and experiment requests')
    closure=load(root/'process-closure.json');record=closure['shutdown_registry']
    registry=trusted_metadata(record,Path(record['path']).stat().st_uid)
    processes=validate_shutdown(registry,broker_uid=Path(record['path']).stat().st_uid,opened_unix=time.time())
    policy={}
    if 'harness/master_review.py' in manifest['launch_sources']:
        from harness.master_review import verify_campaign_reviews
        policy['master_research_reviews']=verify_campaign_reviews(root)
    return dict(engineering_evidence_verified=True,normal_native_campaign_completed=True,
        master_comparison_delivered=True,opportunities=len(plan['assessment']['opportunities']),
        chosen_directions=[row['id'] for row in plan['directions']],roles=roles,counters=expected,
        evidence_tools_replayed=tools_replayed,jobs=jobs,gpu_seconds=charged,active_gpu_jobs=0,
        process_exits_verified=processes,post_launch_source_changes=sorted(modified),
        controller_gate_jobs=expected['controller_jobs'],sealed_used=False,candidate_promoted=False,
        complete_paper_rsi=False,paper_numbers_reproduced=False,**policy)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--include-observability-stop',action='store_true')
    args=parser.parse_args()
    print(json.dumps((audit_observability_stop if args.include_observability_stop else audit)(args.directory),ensure_ascii=False,sort_keys=True))
