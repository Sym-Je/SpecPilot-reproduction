"""Stock-only measurement and bounded public profiling; no promotion authority."""

from __future__ import annotations

import argparse
import base64
from collections import Counter,defaultdict
from contextlib import ExitStack
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))

from controller.dev_campaign import validate_packet
from controller.scored_forcing import read_reference
from costmodel.observations import counter_observation,factor_coverage,trace_observation
from exp.candidate_smoke import CandidateServer,CapturedArm,FROZEN_STOCK_SHA,source_hashes as candidate_sources
from exp.diagnosis import digest,publish
from exp.diagnosis_profile import ProfileClient
from exp.p3_pair_run import Server,SETTING,SUITES,arm_specs,check_ports,clean_environment,gpu_lock,interrupted,load_requests,result_row,run_round,wait_for_idle,write_json
from harness.candidate import check_tree,expected_arguments


PROTOCOL='stock-observation-v1'
PROFILE_STEPS=128
PROFILE_LIMIT=4*1024**3


class StockServer(CandidateServer):
    def launch_spec(self):
        return Server.launch_spec(self)


def sampling():
    return dict(temperature=0.0,top_k=1,max_new_tokens=2048)


def profile_request(schema,directory):
    fields=schema.get('components',{}).get('schemas',{}).get('ProfileReq',{}).get('properties',{})
    if not {'output_dir','num_steps','record_shapes','detailed_annotations'}<=set(fields):
        raise ValueError('public API lacks bounded shape-annotated profiling')
    body=dict(output_dir=str(directory),num_steps=PROFILE_STEPS,record_shapes=True,detailed_annotations=True)
    if 'with_stack' in fields:
        body['with_stack']=False
    return body


def control_status(packet):
    payload=base64.b64decode(packet['response_bytes_base64'],validate=True)
    if hashlib.sha256(payload).hexdigest()!=packet['response_bytes_sha256']:
        raise ValueError('profile response bytes changed')
    text=payload.decode(errors='replace').lower()
    if '<html' in text or '<!doctype html' in text:
        raise ValueError('HTML is not a valid profile-control response')
    return dict(http_status=packet['http_status'],http_success=packet['http_status']==200,
        explicitly_not_running=packet['http_status'] in (400,409) and
            any(phrase in text for phrase in ('not running','not started','has not been started')),
        raw_response_bytes_verified=True)


def validate_order(rounds,*,profile_start):
    if len(rounds)!=2 or not math.isfinite(profile_start):
        raise ValueError('two timing rounds and separate profiling required')
    previous=-math.inf
    for row in rounds:
        if (any(type(row.get(key)) not in (int,float) or not math.isfinite(row[key]) for key in ('start','end'))
                or not previous<row['start']<row['end']):
            raise ValueError('timing rounds overlap or are incomplete')
        previous=row['end']
    if profile_start<previous:
        raise ValueError('profiler overlapped unprofiled timing')


def sources():
    result=candidate_sources()
    names=subprocess.check_output(['git','ls-files','--','costmodel'],cwd=ROOT,text=True).splitlines()
    names+=['costmodel/observations.py','exp/stock_profile.py','exp/stock_profile_remote.sh',
            'harness/test_p11_observations.py','harness/test_p11_stock_profile.py']
    result.update({name:digest(ROOT/name) for name in sorted(set(names)) if Path(name).suffix in ('.py','.sh')})
    return dict(sorted(result.items()))


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def event(public,phase,**values):
    destination=public/'events.jsonl'
    with destination.open('a') as output:
        output.write(json.dumps(dict(time_unix=time.time(),phase=phase,**values))+'\n')
        output.flush()
    destination.chmod(0o644)


def run_timings(directory,manifest,environment,*,server_factory=StockServer,after_round=None):
    timing=directory/'timing'
    timing.mkdir()
    sessions=[]
    for number in (0,1):
        started=time.time()
        root=timing/f'round-{number+1:02d}'
        def factory(name,url,**options):
            return CapturedArm(name,url,directory=root,spec=manifest['stock_spec'],**options)
        check_ports(manifest['ports'])
        run_round(manifest['arms'],manifest['gpus'],manifest['ports'],number,manifest['requests'],root,
                  environment,2048,2,1200,server_factory=server_factory,arm_factory=factory,stable_null=True)
        if after_round is not None:
            after_round()
        sessions.append(dict(start=started,end=time.time()))
    write_json(timing/'sessions.json',sessions)


def validate_timing_round(directory,manifest,number):
    root=directory/'timing'/f'round-{number+1:02d}'
    requests=manifest['requests']
    assigned=manifest['gpus'] if number==0 else list(reversed(manifest['gpus']))
    assignments=[dict(arm=arm,gpu=gpu,port=port) for arm,gpu,port in zip(manifest['arms'],assigned,manifest['ports'])]
    if json.loads((root/'deployment.json').read_text())!=dict(round=number+1,assignments=assignments):
        raise ValueError('stock physical assignment changed')
    if json.loads((root/'complete.json').read_text())!=dict(round=number+1,pairs=len(requests)):
        raise ValueError('incomplete timing round')
    pairs=rows(root/'pairs.jsonl')
    if len(pairs)!=len(requests) or [pair['id'] for pair in pairs]!=[request['id'] for request in requests]:
        raise ValueError('timing request coverage changed')
    events={row['event']:row['time_unix'] for row in rows(root/'events.jsonl')}
    if not events['servers_started']<=events['servers_ready']<=events['warmup_complete']<=pairs[0]['started_unix']:
        raise ValueError('timing began before warmup')
    warm=rows(root/'warmup.jsonl')
    expected_requests=requests[:2]+requests
    phases=['short']*2+['full']*len(requests)
    if [row['phase'] for row in warm]!=phases or [row['id'] for row in warm]!=[request['id'] for request in expected_requests]:
        raise ValueError('missing declared full-scale warmup')
    fingerprints=[]
    for key,assignment in zip(('a','b'),assignments):
        name=assignment['arm']['name']
        if rows(root/f'{name}.jsonl')!=[pair[key] for pair in pairs]:
            raise ValueError('timing arm rows differ from canonical pairs')
        process=json.loads((root/f'{name}.process.json').read_text())
        if any(type(process.get(key)) is not int or process[key]<=0 for key in ('pid','start_ticks')):
            raise ValueError('missing fresh process identity')
        fingerprints.append((process['pid'],process['start_ticks']))
        if json.loads((root/f'{name}.stopped.json').read_text())!=dict(stopped=True):
            raise ValueError('stock server did not stop')
        for row,request,phase in zip(warm,expected_requests,phases):
            validate_packet(row[key],request,assignment,32 if phase=='short' else 2048,directory,manifest['launch_protocol'])
        for pair,request in zip(pairs,requests):
            validate_packet(pair[key],request,assignment,2048,directory,manifest['launch_protocol'])
    return pairs,fingerprints


def trace_files(directory):
    return sorted(path for path in directory.rglob('*') if path.is_file() and
                  (path.name.endswith('.json') or path.name.endswith('.json.gz')) and path.stat().st_size>0)


def trace_bytes(directory):
    return sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())


def read_trace(path):
    opener=gzip.open if path.name.endswith('.gz') else open
    with opener(path,'rt') as source:
        document=json.load(source)
    return document['traceEvents'] if isinstance(document,dict) else document


def ready_traces(directory,timeout=30):
    deadline=time.monotonic()+timeout
    while True:
        found=trace_files(directory)
        try:
            observations=[]
            for path in found:
                before=digest(path)
                observation=trace_observation(read_trace(path))
                after=digest(path)
                if before!=after:
                    observations=[]
                    break
                observations.append(dict(path=str(path),sha256=after,observation=observation))
        except (json.JSONDecodeError,EOFError,OSError):
            observations=[]
        if observations:
            if any(row['observation']['kernel_sum_us']<=0 for row in observations):
                raise ValueError('profile contains no GPU kernel work')
            return observations
        if time.monotonic()>=deadline:
            raise ValueError('public profile API produced no complete readable trace')
        time.sleep(.1)


def run_profiles(directory,manifest,environment,public):
    profiles=directory/'profiles'
    profiles.mkdir()
    write_json(profiles/'started.json',dict(started_unix=time.time()))
    records=[]
    arm=dict(manifest['arms'][0],name='stock',launch_arm='stock')
    port=manifest['profile_port']
    for number,gpu in enumerate(manifest['gpus']):
        root=profiles/f'round-{number+1:02d}'
        root.mkdir()
        check_ports([port])
        with ExitStack() as resources:
            server=StockServer(arm,gpu,port,root,environment)
            resources.callback(server.stop)
            server.start()
            server.wait_ready(1200)
            control=ProfileClient(f'http://127.0.0.1:{port}',root/'control')
            schema=control.request('/openapi.json')
            schema_ref=dict(control.last_evidence)
            client=CapturedArm('stock',f'http://127.0.0.1:{port}',directory=root,spec=manifest['stock_spec'],
                block_size=8,tree_sha=arm['tree_sha'],env={})
            client.begin_session()
            warm=[]
            for request in manifest['requests'][:2]:
                generated=client.step(request['input_ids'],32,rid='profile-short-warm')
                warm.append(dict(phase='short',row=result_row(generated,request,arm,gpu,number,32)))
            for request in manifest['requests']:
                generated=client.step(request['input_ids'],2048,rid='profile-full-warm')
                warm.append(dict(phase='full',row=result_row(generated,request,arm,gpu,number,2048)))
            write_json(root/'warmup.json',warm)
            write_json(root/'warmup-complete.json',dict(completed_unix=time.time()))
            session_usable=True
            for index,request in enumerate(manifest['requests']):
                record=dict(round=number+1,gpu_uuid=gpu['uuid'],id=request['id'],suite=request['suite'],
                    schema=schema_ref,traces=[],status='unavailable')
                output=root/f'trace-{index:02d}'
                output.mkdir()
                if not session_usable:
                    record['reason']='probe skipped after uncertain profile-control state; server will be stopped'
                    records.append(record)
                    continue
                if trace_bytes(profiles)>=PROFILE_LIMIT:
                    record.update(status='skipped_budget',reason='predeclared 4GiB evidence budget reached')
                    records.append(record)
                    continue
                started=False
                try:
                    body=profile_request(schema,output)
                    control.post('/start_profile',body)
                    record['start_control']=dict(control.last_evidence)
                    started=True
                    try:
                        generated=client.step(request['input_ids'],2048,rid='profile-'+request['id'])
                        record['row']=result_row(generated,request,arm,gpu,number,2048)
                    finally:
                        try:
                            control.post('/stop_profile',{})
                        except Exception as error:
                            record['stop_error']=type(error).__name__
                        record['stop_control']=dict(control.last_evidence)
                    stop=control_status(read_reference(record['stop_control'],directory))
                    session_usable=(stop['http_success'] and 'stop_error' not in record) or stop['explicitly_not_running']
                    record['traces']=ready_traces(output)
                    record['status']='captured_with_control_error' if 'stop_error' in record else 'captured'
                except Exception as error:
                    record.update(reason=type(error).__name__+': '+str(error),start_attempted=started)
                    session_usable=False
                    if 'stop_control' in record:
                        try:
                            state=control_status(read_reference(record['stop_control'],directory))
                            session_usable=(state['http_success'] and 'stop_error' not in record) or state['explicitly_not_running']
                        except (KeyError,ValueError):
                            pass
                    if 'stop_control' not in record:
                        try:
                            control.post('/stop_profile',{})
                        except Exception as cleanup_error:
                            record['cleanup_error']=type(cleanup_error).__name__
                        record['cleanup_control']=dict(control.last_evidence)
                        try:
                            state=control_status(read_reference(record['cleanup_control'],directory))
                            session_usable=state['http_success'] or state['explicitly_not_running']
                        except (KeyError,ValueError):
                            session_usable=False
                records.append(record)
                event(public,'profile-progress',round=number+1,completed=len(records),expected=20,status=record['status'])
        wait_for_idle([0,1])
    write_json(profiles/'records.json',records)


def summarize_evidence(directory,manifest,records,timing_rows):
    timing=defaultdict(list)
    counters=[]
    for row in timing_rows:
        timing[row['suite']].append(row)
        metadata=read_reference(row['raw_evidence'],directory)['response']['meta_info']
        counters.append(dict(suite=row['suite'],**counter_observation(metadata)))
    observations=[]
    for record in records:
        if record['status'] not in ('captured','captured_with_control_error'):
            continue
        for trace in record['traces']:
            observations.append(dict(suite=record['suite'],observation=trace['observation'],
                full_request_completion_tokens=record['row']['completion_tokens'],
                full_request_reported_verify_ct=record['row']['spec_verify_ct'],
                captured_verify_annotation_count=trace['observation']['stages']['stage_annotation_counts'].get('VERIFY',0)))
    suites={}
    for suite in SUITES:
        samples=timing[suite]
        selected=[row for row in counters if row['suite']==suite]
        valid=[row for row in selected if row['algebra_consistent']]
        traces=[row['observation'] for row in observations if row['suite']==suite]
        suites[suite]=dict(independent_requests=2,timed_arm_rows=len(samples),
            latency_ms_median=statistics.median(row['latency_ms'] for row in samples),
            completion_tokens_mean=statistics.mean(row['completion_tokens'] for row in samples),
            stop_count=sum(row['finish_reason']=='stop' for row in samples),length_count=sum(row['finish_reason']=='length' for row in samples),
            algebra_consistent_counter_rows=len(valid),counter_rows=len(selected),
            reported_correct_drafts_per_verify_mean=statistics.mean(row['reported_correct_drafts_per_verify'] for row in valid) if valid else None,
            emitted_tokens_per_reported_verify_mean=statistics.mean(row['emitted_tokens_per_reported_verify'] for row in valid) if valid else None,
            native_correct_draft_histogram_work_counts=[sum(row['reported_correct_draft_histogram'][index] for row in valid) for index in range(8)] if valid else None,
            profile_traces=len(traces),kernel_sum_ms=sum(row['kernel_sum_us'] for row in traces)/1000,
            stage_kernel_sum_ms={stage:sum(row['stages']['kernel_us'].get(stage,0) for row in traces)/1000
                                 for stage in ('EXTEND','DRAFT','VERIFY','DECODE','UNATTRIBUTED')},
            shape_qualified_mm_ops=sum(row['nominal_matmul_floors']['eligible_ops'] for row in traces))
    usable=sum(record['status'] in ('captured','captured_with_control_error') for record in records)
    fractions=defaultdict(list)
    for record in records:
        if record['status'] not in ('captured','captured_with_control_error'):
            continue
        total=sum(trace['observation']['kernel_sum_us'] for trace in record['traces'])
        if total>0:
            for stage in ('EXTEND','DRAFT','VERIFY','DECODE','UNATTRIBUTED'):
                fractions[stage].append(sum(trace['observation']['stages']['kernel_us'].get(stage,0)
                                           for trace in record['traces'])/total)
    complete=usable==20
    return dict(protocol=PROTOCOL,source_pin=manifest['source_pin'],independent_requests=10,
        timing_pairs=len(timing_rows)//2,timing_arm_rows=len(timing_rows),profile_requests_expected=20,
        profile_requests_usable=usable,profile_capture_complete=complete,
        profile_control_errors=sum('stop_error' in record for record in records),
        profile_evidence_bytes=trace_bytes(directory/'profiles'),profile_evidence_limit=PROFILE_LIMIT,
        counter_rows_algebra_consistent=sum(row['algebra_consistent'] for row in counters),
        suites=suites,profile_window_gpu_work_share_equal_request={key:statistics.mean(value) for key,value in fractions.items()} if complete else None,
        per_trace_observations=observations,factor_coverage=factor_coverage(),
        promoted=False,ledger_eligible=False,
        scope='stock diagnostic and early profile-window GPU work; not headroom, end-to-end stage fractions, losslessness or a paper performance result')


def audit(directory):
    directory=Path(directory).absolute()
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest['protocol']!=PROTOCOL or manifest['source_sha256']!=sources() or manifest['tree_sha']!=FROZEN_STOCK_SHA:
        raise ValueError('stock observation source or protocol drift')
    if (manifest['profile_steps']!=PROFILE_STEPS or manifest['profile_limit']!=PROFILE_LIMIT or
            manifest['launch_protocol']!=expected_arguments(manifest['stock_spec'],8) or
            [arm['name'] for arm in manifest['arms']]!=['stock-a','stock-b'] or
            any(arm['block']!=8 or arm['tree_sha']!=FROZEN_STOCK_SHA or arm['env'] for arm in manifest['arms'])):
        raise ValueError('stock launch or profile-window contract changed')
    check_tree(manifest['arms'][0]['engine'],FROZEN_STOCK_SHA)
    for path,checksum in manifest['model_configs'].items():
        if digest(path)!=checksum:
            raise ValueError('model configuration changed')
    requests=manifest['requests']
    if (len(requests)!=10 or len({row['id'] for row in requests})!=10 or
            Counter(row['suite'] for row in requests)!=Counter({suite:2 for suite in SUITES})):
        raise ValueError('invalid ten-request suite coverage')
    archive=manifest['source_archive']
    if digest(archive['path'])!=archive['sha256']:
        raise ValueError('source archive changed')
    with tarfile.open(archive['path']) as snapshot:
        for name,expected in manifest['source_sha256'].items():
            if hashlib.sha256(snapshot.extractfile(name).read()).hexdigest()!=expected:
                raise ValueError('source snapshot differs from execution')
    timing_rows=[]
    fingerprints=[]
    for number in (0,1):
        pairs,processes=validate_timing_round(directory,manifest,number)
        fingerprints.extend(processes)
        timing_rows.extend(pair[key] for pair in pairs for key in ('a','b'))
    started=json.loads((directory/'profiles/started.json').read_text())['started_unix']
    validate_order(json.loads((directory/'timing/sessions.json').read_text()),profile_start=started)
    records=json.loads((directory/'profiles/records.json').read_text())
    expected=[(number,request['id']) for number in (1,2) for request in requests]
    if [(record['round'],record['id']) for record in records]!=expected:
        raise ValueError('profile request coverage changed')
    arm=dict(manifest['arms'][0],name='stock',launch_arm='stock')
    for number,gpu in enumerate(manifest['gpus']):
        root=directory/'profiles'/f'round-{number+1:02d}'
        process=json.loads((root/'stock.process.json').read_text())
        fingerprints.append((process['pid'],process['start_ticks']))
        if json.loads((root/'stock.stopped.json').read_text())!=dict(stopped=True):
            raise ValueError('profile server not stopped')
        assignment=dict(arm=arm,gpu=gpu,port=manifest['profile_port'])
        warm= json.loads((root/'warmup.json').read_text())
        warm_requests=requests[:2]+requests
        phases=['short']*2+['full']*len(requests)
        if [row['phase'] for row in warm]!=phases or [row['row']['id'] for row in warm]!=[request['id'] for request in warm_requests]:
            raise ValueError('profile warmup coverage changed')
        for row,request,phase in zip(warm,warm_requests,phases):
            validate_packet(row['row'],request,assignment,32 if phase=='short' else 2048,directory,manifest['launch_protocol'])
        warm_completed=json.loads((root/'warmup-complete.json').read_text())['completed_unix']
        selected=[record for record in records if record['round']==number+1]
        for record,request in zip(selected,requests):
            schema=read_reference(record['schema'],directory)['response']
            if 'row' in record:
                validate_packet(record['row'],request,assignment,2048,directory,manifest['launch_protocol'])
            if record['status'] in ('captured','captured_with_control_error'):
                start=read_reference(record['start_control'],directory)
                if (not start['url'].endswith('/start_profile') or start['http_status']!=200 or
                        start['request']!=profile_request(schema,start['request']['output_dir'])):
                    raise ValueError('profile start protocol changed')
                control_status(start)
                if (start['started_unix']<warm_completed or
                        record['row']['client_timing']['started_unix']<start['finished_unix']):
                    raise ValueError('profile request escaped warmup/start order')
                stop=read_reference(record['stop_control'],directory)
                if not stop['url'].endswith('/stop_profile') or stop['request']!={}:
                    raise ValueError('profile stop evidence came from a different endpoint')
                control_status(stop)
                if (stop['http_status']!=200)!=('stop_error' in record):
                    raise ValueError('profile stop HTTP error was hidden')
                if not record['traces']:
                    raise ValueError('profile marked captured without a trace')
            for trace in record['traces']:
                if digest(trace['path'])!=trace['sha256'] or trace_observation(read_trace(Path(trace['path'])))!=trace['observation']:
                    raise ValueError('profile evidence changed')
    if len(set(fingerprints))!=6:
        raise ValueError('stock servers were not fresh')
    cleanup=json.loads((directory/'cleanup.json').read_text())
    if ({gpu['uuid'] for gpu in cleanup}!={gpu['uuid'] for gpu in manifest['gpus']} or
            any(gpu['memory_used_mib']!=0 or gpu['utilization']>10 for gpu in cleanup)):
        raise ValueError('GPU cleanup failed')
    return summarize_evidence(directory,manifest,records,timing_rows)


def run(directory,public):
    from transformers import AutoTokenizer
    expected=os.environ['BOTTLENECK_EXPECTED_COMMIT']
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if actual!=expected:
        raise ValueError('live checkout is not frozen')
    subprocess.run(['git','diff','--exit-code',expected,'--','controller','exp','harness','costmodel','assets/upstream'],cwd=ROOT,check=True)
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    environment=clean_environment()
    signal.signal(signal.SIGTERM,interrupted)
    arms,config=arm_specs(['stock-a','stock-b'],environment)
    check_tree(arms[0]['engine'],FROZEN_STOCK_SHA)
    target=environment.get('SP_TARGET','/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B')
    draft=environment.get('SP_DRAFT','/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2')
    spec=dict(target=target,draft=draft,stock_tree_sha=FROZEN_STOCK_SHA)
    tokenizer=AutoTokenizer.from_pretrained(target,local_files_only=True)
    loaded=load_requests(2,SUITES,tokenizer)
    requests=[loaded[2*suite+index] for index in (0,1) for suite in range(5)]
    with ExitStack() as resources:
        gpus=wait_for_idle([0,1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        archive=Path(os.environ['BOTTLENECK_SOURCE_TAR'])
        if digest(archive)!=os.environ['BOTTLENECK_SOURCE_SHA256']:
            raise ValueError('source archive differs from declared digest')
        manifest=dict(protocol=PROTOCOL,source_pin=expected,source_sha256=sources(),
            source_archive=dict(path=str(archive),sha256=digest(archive)),requests=requests,
            arms=arms,gpus=gpus,ports=[30100,30110],profile_port=30120,tree_sha=FROZEN_STOCK_SHA,stock_spec=spec,
            launch_protocol=expected_arguments(spec,8),profile_steps=PROFILE_STEPS,profile_limit=PROFILE_LIMIT,
            declared_models=config['models'],model_configs={str(Path(path)/'config.json'):digest(Path(path)/'config.json')
                for path in (target,draft)})
        write_json(directory/'manifest.json',manifest)
        event(public,'timing-start')
        run_timings(directory,manifest,environment,after_round=lambda:wait_for_idle([0,1]))
        event(public,'timing-complete',pairs=20,arm_rows=40)
        write_json(directory/'timing-cleanup.json',wait_for_idle([0,1]))
        run_profiles(directory,manifest,environment,public)
        check_ports(manifest['ports']+[manifest['profile_port']])
        write_json(directory/'cleanup.json',wait_for_idle([0,1]))
        result=audit(directory)
        write_json(directory/'result.json',result)
        publish(public/'result.json',result)
        event(public,'gpu-work-complete',profile_requests_usable=result['profile_requests_usable'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    execute=commands.add_parser('run')
    execute.add_argument('--directory',type=Path,required=True)
    execute.add_argument('--public',type=Path,required=True)
    check=commands.add_parser('audit')
    check.add_argument('--directory',type=Path,required=True)
    check.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='run':
        run(args.directory.absolute(),args.public.absolute())
    else:
        result=audit(args.directory)
        publish(args.out,result)
        print(json.dumps(dict(replay_complete=True,profile_requests_usable=result['profile_requests_usable'],cost_model_complete=False)))


if __name__=='__main__':
    main()
