"""Trusted stock Phase 0 collection and independent evidence replay, never promotion."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from controller.dev_campaign import validate_packet
from controller.scored_forcing import read_reference
from costmodel.ceiling import coverage,profile_report
from exp.candidate_smoke import CapturedArm,CandidateServer
from exp.diagnosis import digest
from exp.diagnosis_profile import ProfileClient
from exp.p3_pair_run import Server,clean_environment,gpu_lock,interrupted,run_round,wait_for_idle,write_json
from exp.stock_profile import profile_request,ready_traces,read_trace,stop_profile,trace_bytes
from harness.candidate import expected_arguments
from harness.ceiling_build import STOCK_SHA,build,check_bundle
from harness.ceiling_replay import BUDGETS,replay_events
from harness.engine_research import save
from harness.step_replay import read_stream,replay_bound


PROFILE_STEPS=8192
PROFILE_LIMIT=8*1024**3


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def progress(directory,phase,**values):
    with (directory/'progress.jsonl').open('a') as output:
        output.write(json.dumps(dict(time_unix=time.time(),phase=phase,**values))+'\n')
    print(json.dumps(dict(phase=phase,**values)),flush=True)


def arm_spec(stock_spec,arms,name):
    selected=[arm for arm in arms if arm['name']==name]
    if len(selected)!=1:
        raise ValueError('one frozen arm identity required')
    return dict(stock_spec,stock_tree_sha=selected[0]['tree_sha'])


class CeilingServer(CandidateServer):
    def launch_spec(self):
        command,environment=Server.launch_spec(self)
        environment.pop('SPECPILOT_STEP_TRACE_DIR',None)
        environment.pop('SPECPILOT_CEILING_TRACE_DIR',None)
        if self.arm.get('observe'):
            destination=self.output_dir/'observer-events'
            destination.mkdir(mode=0o700)
            environment.update(SPECPILOT_STEP_TRACE_DIR=str(destination),SPECPILOT_CEILING_TRACE_DIR=str(destination))
        return command,environment


def source_identity(request):
    record=json.loads(Path(request).read_text())
    archive=record['source_archive']
    if digest(archive['path'])!=archive['sha256']:
        raise ValueError('execution archive changed')
    with tarfile.open(archive['path']) as source:
        for name,checksum in archive['files'].items():
            if hashlib.sha256(source.extractfile(name).read()).hexdigest()!=checksum:
                raise ValueError('frozen source member changed')
    return record


def run(request,directory):
    record=source_identity(request)
    for name,checksum in record['source_archive']['files'].items():
        if digest(ROOT/name)!=checksum:
            raise ValueError('runtime differs from frozen source')
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    signal.signal(signal.SIGTERM,interrupted)
    build(record['stock_engine'],directory/'bundle')
    built=check_bundle(directory/'bundle')
    environment=clean_environment()
    sessions=[]
    with ExitStack() as resources:
        gpus=wait_for_idle([0,1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        stock=dict(name='stock',launch_arm='stock',block=8,engine=record['stock_engine'],tree_sha=STOCK_SHA,env={})
        modes={mode:[stock,dict(stock,name='observer',engine=str(directory/'bundle/engine'),
            tree_sha=built['observer_tree_sha'],observe=mode=='enabled')] for mode in ('disabled','enabled')}
        manifest=dict(schema='phase0-ceiling-v1',request_path=str(request),request_sha256=digest(request),
            source_archive=record['source_archive'],stock_spec=record['stock_spec'],requests=record['requests'],
            gpus=gpus,ports=[30500,30510],modes=modes,profile_steps=PROFILE_STEPS,profile_limit=PROFILE_LIMIT,
            model_configs=record['model_configs'],started_unix=time.time())
        write_json(directory/'manifest.json',manifest)
        for mode,arms in modes.items():
            for number in (0,1):
                root=directory/mode/f'round-{number+1:02d}'
                def factory(name,url,**options):
                    return CapturedArm(name,url,directory=root,spec=arm_spec(record['stock_spec'],arms,name),**options)
                started=time.time()
                run_round(arms,gpus,manifest['ports'],number,record['requests'],root,environment,
                    2048,1,1200,server_factory=CeilingServer,arm_factory=factory,stable_null=True)
                references=[dict(path=str(path),sha256=digest(path)) for path in sorted((root/'observer-events').glob('*.jsonl'))]
                write_json(root/'streams.json',references)
                sessions.append(dict(mode=mode,round=number+1,start=started,end=time.time()))
                progress(directory,'timing-complete',mode=mode,round=number+1)
        write_json(directory/'timing-sessions.json',sessions)
        profiles=[]
        profile_started=time.time()
        for number,gpu in enumerate(gpus):
            root=directory/'profiles'/f'round-{number+1:02d}'
            root.mkdir(parents=True)
            with ExitStack() as servers:
                server=CeilingServer(stock,gpu,30520,root,environment)
                servers.callback(server.stop)
                server.start()
                server.wait_ready(1200)
                control=ProfileClient('http://127.0.0.1:30520',root/'control',timeout=600)
                schema=control.request('/openapi.json')
                client=CapturedArm('stock','http://127.0.0.1:30520',directory=root,spec=record['stock_spec'],
                    block_size=8,tree_sha=STOCK_SHA,env={})
                client.begin_session()
                warm=[]
                for index,item in enumerate(record['requests'][:1]+record['requests']):
                    warm.append(client.step(item['input_ids'],32 if index==0 else 2048,rid=f'profile-warm-{index}'))
                write_json(root/'warmup.json',warm)
                for index,item in enumerate(record['requests']):
                    if trace_bytes(directory/'profiles')>=PROFILE_LIMIT:
                        raise ValueError('predeclared 8GiB profile evidence cap reached')
                    output=root/f'trace-{index:02d}'
                    output.mkdir()
                    body=profile_request(schema,output)
                    body['num_steps']=PROFILE_STEPS
                    control.post('/start_profile',body)
                    sample=dict(round=number+1,id=item['id'],suite=item['suite'],gpu=gpu,
                        start_control=dict(control.last_evidence),profile_steps=PROFILE_STEPS)
                    try:
                        from exp.p3_pair_run import result_row
                        generated=client.step(item['input_ids'],2048,rid=f'profile-{number}-{index}')
                        sample['row']=result_row(generated,item,stock,gpu,number,2048)
                    finally:
                        inactive=stop_profile(control,root,sample)
                    if not inactive:
                        raise ValueError('profiler stop state uncertain')
                    sample['traces']=ready_traces(output,timeout=120)
                    profiles.append(sample)
                    save(directory/'profiles-partial.json',profiles)
                    progress(directory,'profile-complete',completed=len(profiles),expected=20)
            wait_for_idle([0,1])
        write_json(directory/'profiles.json',dict(started_unix=profile_started,records=profiles))
        write_json(directory/'cleanup.json',wait_for_idle([0,1]))
    result=audit(directory)
    write_json(directory/'result.json',result)
    return result


def audit(directory):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    request=Path(manifest['request_path'])
    if digest(request)!=manifest['request_sha256']:
        raise ValueError('frozen request changed')
    record=source_identity(request)
    if (manifest['schema']!='phase0-ceiling-v1' or manifest['requests']!=record['requests'] or
            manifest['source_archive']!=record['source_archive'] or manifest['profile_steps']!=PROFILE_STEPS or
            manifest['profile_limit']!=PROFILE_LIMIT or manifest['model_configs']!=record['model_configs']):
        raise ValueError('protocol drift')
    for path,checksum in record['model_configs'].items():
        if digest(path)!=checksum:
            raise ValueError('model config changed')
    built=check_bundle(directory/'bundle')
    replays=[]
    canonical={}
    processes=[]
    faults=0
    for mode in ('disabled','enabled'):
        arms=manifest['modes'][mode]
        if ([arm['name'] for arm in arms]!=['stock','observer'] or
                any(arm['block']!=8 or arm['env'] or arm['launch_arm']!='stock' for arm in arms) or
                arms[0]['engine']!=record['stock_engine'] or arms[0]['tree_sha']!=STOCK_SHA or
                arms[1]['engine']!=str(directory/'bundle/engine') or arms[1]['tree_sha']!=built['observer_tree_sha'] or
                arms[1]['observe']!=(mode=='enabled')):
            raise ValueError('stock/default-off/observer identity changed')
        for number in (0,1):
            root=directory/mode/f'round-{number+1:02d}'
            assignments=[dict(arm=arm,gpu=gpu,port=port) for arm,gpu,port in
                zip(arms,manifest['gpus'] if number==0 else list(reversed(manifest['gpus'])),manifest['ports'])]
            if json.loads((root/'deployment.json').read_text())!=dict(round=number+1,assignments=assignments):
                raise ValueError('physical swap changed')
            pairs=rows(root/'pairs.jsonl')
            if ([pair['id'] for pair in pairs]!=[item['id'] for item in record['requests']] or
                    json.loads((root/'complete.json').read_text())!=dict(round=number+1,pairs=10)):
                raise ValueError('missing timing request')
            stream_references=json.loads((root/'streams.json').read_text())
            grouped=defaultdict(list)
            if mode=='disabled' and (stream_references or (root/'observer-events').exists()):
                raise ValueError('disabled observer emitted observations')
            for reference in stream_references:
                for event in read_stream(reference,directory):
                    if event['tree_sha']!=built['observer_tree_sha']:
                        raise ValueError('step tree identity changed')
                    grouped[event['rid']].append(event)
            warm=rows(root/'warmup.jsonl')
            expected_warm=record['requests'][:1]+record['requests']
            if [row['id'] for row in warm]!=[item['id'] for item in expected_warm]:
                raise ValueError('full-scale warmup changed')
            events={row['event']:row['time_unix'] for row in rows(root/'events.jsonl')}
            if not events['warmup_complete']<=pairs[0]['started_unix']:
                raise ValueError('timing before warmup')
            for key,assignment in zip(('a','b'),assignments):
                name=assignment['arm']['name']
                process=json.loads((root/f'{name}.process.json').read_text())
                processes.append((process['pid'],process['start_ticks']))
                if json.loads((root/f'{name}.stopped.json').read_text())!=dict(stopped=True):
                    raise ValueError('server still active')
                if rows(root/f'{name}.jsonl')!=[pair[key] for pair in pairs]:
                    raise ValueError('arm/pair mismatch')
                for index,(sample,item) in enumerate(zip(warm,expected_warm)):
                    validate_packet(sample[key],item,assignment,32 if index==0 else 2048,directory,expected_arguments(record['stock_spec'],8))
                for sample,item in zip(pairs,record['requests']):
                    validate_packet(sample[key],item,assignment,2048,directory,expected_arguments(record['stock_spec'],8))
                    output=sample[key]['output_ids']
                    if sample['id'] in canonical and canonical[sample['id']]!=output:
                        raise ValueError('stock/observer output changed across modes or devices')
                    canonical[sample['id']]=output
            if mode=='enabled':
                for pair,item in zip(pairs,record['requests']):
                    generation=pair['b']['raw_evidence']
                    rid=read_reference(generation,directory)['request']['rid']
                    observations=grouped[rid]
                    replay_bound([row for row in observations if row['kind']!='lattice'],generation,root=directory)
                    replay=replay_events(observations,pair['b']['output_ids'])
                    replays.append(dict(id=item['id'],suite=item['suite'],round=number+1,**replay))
                    import copy
                    for fault in ('accepted','candidate','score','missing_lattice'):
                        altered=copy.deepcopy(observations)
                        verify=next(row for row in altered if row['kind']=='verify')
                        lattice=next(row for row in altered if row['kind']=='lattice')
                        if fault=='accepted':
                            verify['accepted']+=1
                        elif fault=='candidate':
                            lattice['candidate_ids'][0][0]=lattice['candidate_ids'][0][1]
                        elif fault=='score':
                            lattice['scores'][0][0][0]=float('nan')
                        else:
                            altered.remove(lattice)
                        try:
                            replay_events(altered,pair['b']['output_ids'])
                        except ValueError:
                            faults+=1
                        else:
                            raise ValueError('real-data fault escaped replay')
    if len(set(processes))!=8:
        raise ValueError('servers were not fresh')
    profiles=json.loads((directory/'profiles.json').read_text())
    sessions=json.loads((directory/'timing-sessions.json').read_text())
    if len(sessions)!=4 or profiles['started_unix']<max(row['end'] for row in sessions):
        raise ValueError('profiler overlapped unprofiled timing')
    expected=[(number,item['id']) for number in (1,2) for item in record['requests']]
    if [(sample['round'],sample['id']) for sample in profiles['records']]!=expected:
        raise ValueError('profile coverage changed')
    traces=[]
    for sample in profiles['records']:
        number=sample['round']
        item=next(item for item in record['requests'] if item['id']==sample['id'])
        root=directory/'profiles'/f'round-{number:02d}'
        assignment=dict(arm=manifest['modes']['disabled'][0],gpu=manifest['gpus'][number-1],port=30520)
        validate_packet(sample['row'],item,assignment,2048,directory,expected_arguments(record['stock_spec'],8))
        start=read_reference(sample['start_control'],directory)
        if (start['http_status']!=200 or start['request']['num_steps']!=PROFILE_STEPS or
                start['request']['record_shapes'] is not True or start['request']['detailed_annotations'] is not True or
                sample['row']['output_ids']!=canonical[item['id']]):
            raise ValueError('profile generation/control differs from matched stock')
        if json.loads((root/'stock.stopped.json').read_text())!=dict(stopped=True):
            raise ValueError('profile server still active')
        for reference in sample['traces']:
            path=Path(reference['path']).resolve()
            if not path.is_relative_to(directory/'profiles') or digest(path)!=reference['sha256']:
                raise ValueError('trace identity changed')
            report=profile_report(read_trace(path))
            traces.append(dict(id=item['id'],suite=item['suite'],round=number,**report))
    bytes_used=trace_bytes(directory/'profiles')
    if bytes_used>PROFILE_LIMIT:
        raise ValueError('profile cap exceeded')
    cleanup=json.loads((directory/'cleanup.json').read_text())
    if (len(cleanup)!=2 or any(row['memory_used_mib']!=0 or row['utilization']>10 for row in cleanup) or
            {row['uuid'] for row in cleanup}!={row['uuid'] for row in manifest['gpus']}):
        raise ValueError('GPU cleanup incomplete')
    conditional=dict(stock_tau=sum(row['stock_tau'] for row in replays)/len(replays),
        oracle_tau=sum(row['oracle_tau'] for row in replays)/len(replays),
        best_first_tau={str(budget):sum(row['best_first_tau'][str(budget)] for row in replays)/len(replays) for budget in BUDGETS},
        aggregation='equal weight per request, then equal repeat; eligible complete-continuation steps within request',
        eligible_steps=sum(row['eligible_steps'] for row in replays),tail_steps_excluded=sum(row['tail_steps_excluded'] for row in replays))
    total=sum(row['observation']['kernel_sum_us'] for row in traces)
    qualified=sum(row['observation']['nominal_matmul_floors']['observed_kernel_sum_us'] for row in traces)
    return dict(schema='phase0-ceiling-v1',collection_completed=True,independent_requests=10,
        paired_generations=40,arm_rows=80,output_regression_passed=True,real_lattice_replays=len(replays),
        replay_faults_rejected=faults,conditional_replay=conditional,replays=replays,
        profile_traces=len(traces),profile_bytes=bytes_used,profiles=traces,
        factor_coverage=coverage(conditional_replay=conditional,kernel_coverage=qualified/total if total else 0.),
        full_ceiling_completed=False,controller_accepted=False,promoted=False,ledger_eligible=False,
        warning='diagnostic only; profiled timings and observer timings are not uninstrumented step latencies; no best-runtime-budget tree, all-class floor or paper-number reproduction')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('run','audit'))
    parser.add_argument('--request',type=Path)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.request.resolve(),args.directory.resolve()) if args.command=='run' else audit(args.directory)
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':
    main()
