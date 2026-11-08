"""Matched factorial diagnosis; no engine edits, sealed access, or promotion."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from controller.dev_campaign import check_phase_order
from controller.http_transport import sha_ids
from controller.paper_policy import POLICY, calibration_from_intervals, measurement_protocol_id
from controller.scored_forcing import checked_server, read_reference
from controller.scoring import NativeClient, server_arguments
from controller.stats import stratified_geomean_ci
from exp.confirmation import interval
from exp.dev_campaign import CapturedArm
from exp.generalization_audit import PHASES, cluster_groups, validate_session
from exp.generalization_run import build, event
from exp.p3_pair_run import Server, append_json, check_ports, clean_environment, gpu_lock, interrupted, run_round, wait_for_idle, write_json
from harness.baseline_validation import read_rows

CONDITIONS=(('natural',2048),('fixed',64),('fixed',256),('fixed',1024))
BASES=12
PROFILE_LIMIT=4*1024**3


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(path,data):
    if path.exists():
        raise FileExistsError('diagnostic reports are append-only')
    write_json(path,data)
    path.chmod(0o644)


def sampling(mode):
    if mode not in ('natural','fixed'):
        raise ValueError('unknown length policy')
    return dict(temperature=0.,top_k=1,**({'ignore_eos':True} if mode=='fixed' else {}))


def check_length(mode,length,budget,reason):
    sampling(mode)
    if not 0<length<=budget or reason not in ('stop','length'):
        raise ValueError('invalid actual output length or finish reason')
    if mode=='fixed' and (length!=budget or reason!='length'):
        raise ValueError('fixed-length intervention did not produce the actual budget')


def specifications():
    return [dict(base_id=f'card-{base:02d}',language=language,input_target=target,answer_style=style)
            for base in range(BASES) for language in ('zh','en') for target in (512,1536) for style in ('short','long')]


def encode(tokenizer,text):
    result=tokenizer.apply_chat_template([dict(role='user',content=text)],tokenize=True,
                                        add_generation_prompt=True,enable_thinking=True)
    return list(result if isinstance(result,list) else result['input_ids'])


def exact_prompt(tokenizer,prefix,suffix,target,language):
    filler=' 这是与问题无关的背景说明。' if language=='zh' else ' This background note is unrelated to the question.'
    lower,upper=0,target
    while lower<upper:
        middle=(lower+upper+1)//2
        if len(encode(tokenizer,prefix+filler*middle+suffix))<=target:
            lower=middle
        else:
            upper=middle-1
    padding=filler*lower
    for extra in range(100):
        text=prefix+padding+' x'*extra+suffix
        tokens=encode(tokenizer,text)
        if len(tokens)==target:
            return text,tokens
        if len(tokens)>target:
            break
    raise ValueError('cannot match complete input tokens without truncation')


def validate_dataset(dataset):
    expected={(row['base_id'],row['language'],row['input_target'],row['answer_style']) for row in specifications()}
    items=dataset['requests']
    actual=[(row['base_id'],row['language'],row['input_target'],row['answer_style']) for row in items]
    if len(items)!=96 or set(actual)!=expected or len(set(actual))!=len(actual) or len({row['id'] for row in items})!=96:
        raise ValueError('incomplete or repeated factorial inputs')
    for row in items:
        if len(row['input_ids'])!=row['input_target'] or sha_ids(row['input_ids'])!=row['input_sha256']:
            raise ValueError('input tokens are not exactly matched')
        if row['suite']!=row['language']+'-'+row['answer_style']:
            raise ValueError('factor label changed')


def prepare(private,public):
    from transformers import AutoTokenizer
    os.umask(0o077)
    private.mkdir(mode=0o700)
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True)
    rows=[]
    for spec in specifications():
        base=int(spec['base_id'].split('-')[-1])
        records=[(number,100+base*37+number*11,20+(base*13+number*17)%71) for number in range(1,7)]
        winner=max(records,key=lambda value:value[2])[0]
        if spec['language']=='zh':
            facts='\n'.join(f'条目{number}：编号{identifier}，分数{score}。' for number,identifier,score in records)
            prefix='根据事实卡回答问题。以下背景与判断无关，可以忽略。\n背景：'
            instruction=('只给出最高分条目的条目号，简短回答。' if spec['answer_style']=='short' else
                         '请详细解释每个条目的比较过程，逐项核对事实并讨论判断方法，至少写1200个汉字，最后给出最高分条目的条目号。')
            suffix='\n事实卡：\n'+facts+'\n问题：'+instruction
        else:
            facts='\n'.join(f'Entry {number}: identifier {identifier}, score {score}.' for number,identifier,score in records)
            prefix='Answer using the fact card. The background below is irrelevant and can be ignored.\nBackground:'
            instruction=('Give only the entry number with the highest score. Answer briefly.' if spec['answer_style']=='short' else
                         'Explain the comparisons in detail, check every entry and discuss the decision method in at least 600 words. End with the number of the highest-scoring entry.')
            suffix='\nFact card:\n'+facts+'\nQuestion: '+instruction
        prompt,tokens=exact_prompt(tokenizer,prefix,suffix,spec['input_target'],spec['language'])
        name=f'{spec["base_id"]}-{spec["language"]}-{spec["input_target"]}-{spec["answer_style"]}'
        rows.append(dict(spec,id=name,suite=spec['language']+'-'+spec['answer_style'],turn=0,
                         input_band='short' if spec['input_target']==512 else 'long',prompt=prompt,
                         input_ids=tokens,input_sha256=sha_ids(tokens),reference=str(winner)))
    dataset=dict(requests=rows,protocol='matched-factorial-v1',independent_cards=BASES,
                 conditions=[dict(mode=mode,budget=budget) for mode,budget in CONDITIONS])
    validate_dataset(dataset)
    for row in rows:
        if encode(tokenizer,row['prompt'])!=row['input_ids']:
            raise ValueError('independent retokenization differs')
    write_json(private/'dataset.json',dataset)
    publish(public/'preparation.json',dict(prepared=True,dataset_sha256=digest(private/'dataset.json'),
        natural_requests=96,fixed_requests_per_budget=48,independent_cards=12,input_tokens=[512,1536],
        conditions=dataset['conditions'],retokenization_passed=True,exact_input_matching_passed=True,
        limitations=['synthetic matched prompts, not a natural population','padding and translation not eliminated',
                     'fixed ignore-EOS output is diagnostic, not semantic task performance']))


def packet_validator(mode):
    def validate(sample,request,assignment,cap,directory,launch_protocol):
        packet=read_reference(sample['raw_evidence'],directory)
        checked_server(sample['generator'],directory)
        actual=server_arguments(read_reference(sample['generator']['evidence'],directory)['response'])
        expected=dict(launch_protocol,speculative_algorithm='DFLASH',speculative_num_draft_tokens=assignment['arm']['block'])
        if (sample['generator']['tree_sha']!=assignment['arm']['tree_sha']
                or any(actual.get(key)!=value for key,value in expected.items())):
            raise ValueError('diagnostic live launch differs from frozen identity')
        body,response=packet.get('request',{}),packet.get('response',{})
        if (packet.get('http_status')!=200 or body.get('input_ids')!=request['input_ids']
                or body.get('sampling_params')!=dict(sampling(mode),max_new_tokens=cap)
                or response.get('output_ids')!=sample['output_ids']
                or response.get('meta_info',{}).get('completion_tokens')!=sample['completion_tokens']
                or response['meta_info'].get('finish_reason',{}).get('type')!=sample['finish_reason']):
            raise ValueError('diagnostic row detached from original native HTTP or EOS policy')
        check_length(mode,sample['completion_tokens'],cap,sample['finish_reason'])
        if (sample['input_sha256']!=request['input_sha256'] or sample['gpu_uuid']!=assignment['gpu']['uuid']
                or sample['arm']!=assignment['arm']['name'] or sample['tree_sha']!=assignment['arm']['tree_sha']
                or sample['block']!=assignment['arm']['block'] or sample['max_new_tokens']!=cap
                or len(sample['output_ids'])!=sample['completion_tokens'] or sha_ids(sample['output_ids'])!=sample['output_sha256']):
            raise ValueError('diagnostic warmup/measurement identity mismatch')
        timing=sample.get('client_timing',{})
        values=[timing.get(key) for key in ('step_start_ns','http_open_start_ns','body_complete_ns','step_end_ns')]
        if (any(type(value) is not int for value in values) or values!=sorted(values) or values[-1]<=values[0]
                or timing.get('url')!=f'http://127.0.0.1:{assignment["port"]}/generate'
                or abs((values[-1]-values[0])/1e9-sample['latency_s'])>.005
                or abs(sample['tokens_per_s']*sample['latency_s']-sample['completion_tokens'])>1e-6):
            raise ValueError('diagnostic HTTP timing is inconsistent')
    return validate


def base_interval(pairs,requests_data,metric='latency'):
    cluster_groups(pairs,requests_data,metric)
    indexed={request['id']:request for request in requests_data}
    values=defaultdict(list)
    for pair in pairs:
        ratio=(pair['a']['latency_s']/pair['b']['latency_s'] if metric=='latency' else
               pair['b']['tokens_per_s']/pair['a']['tokens_per_s'])
        values[indexed[pair['id']]['base_id']].append(math.log(ratio))
    if len(values)!=BASES:
        raise ValueError('incomplete independent card coverage')
    return stratified_geomean_ci({'matched-cards':[statistics.mean(values[base]) for base in sorted(values)]})


def timing(directory,campaign,environment,public):
    directory.mkdir()
    write_json(directory/'manifest.json',campaign)
    mode=campaign['length_mode']
    for phase in PHASES:
        session=directory/phase
        session.mkdir()
        write_json(session/'manifest.json',campaign)
        arms=campaign['candidate_arms'] if phase=='candidate' else campaign['null_arms']
        for number in (0,1):
            event(public,'timing-start',mode=mode,budget=campaign['max_new_tokens'],session=phase,round=number+1)
            output=session/f'round-{number+1:02d}'
            def factory(name,url,**options):
                return CapturedArm(name,url,output_dir=output,sampling=sampling(mode),**options)
            check_ports(campaign['ports'])
            run_round(arms,campaign['gpus'],campaign['ports'],number,campaign['requests'],output,environment,
                campaign['max_new_tokens'],2,1200,stable_null=True,arm_factory=factory)
            wait_for_idle([0,1])
            event(public,'timing-round-complete',mode=mode,budget=campaign['max_new_tokens'],session=phase,round=number+1)
        checked,pairs=validate_session(session,campaign,packet_validator=packet_validator(mode))
        checked['interval']=base_interval(pairs,campaign['requests'],'throughput')
        checked['interval_unit']='independent fact card; language/input/style/physical rounds clustered'
        write_json(session/'session-validation.json',checked)
        event(public,'timing-session-validated',mode=mode,budget=campaign['max_new_tokens'],session=phase)


def contrasts(rows):
    indexed={(row['base_id'],row['language'],row['input_target'],row['budget']):row['ratio'] for row in rows}
    bases=sorted({row['base_id'] for row in rows})
    expected={(base,language,target,budget) for base in bases for language in ('zh','en')
              for target in (512,1536) for budget in (64,256,1024)}
    if len(bases)!=12 or set(indexed)!=expected or len(indexed)!=len(rows) or any(not math.isfinite(value) or value<=0 for value in indexed.values()):
        raise ValueError('missing/duplicate fixed factorial cells')
    values=defaultdict(list)
    for base in bases:
        def logarithm(language,target,budget): return math.log(indexed[base,language,target,budget])
        values['language-at-64'].append(statistics.mean(logarithm('zh',target,64)-logarithm('en',target,64) for target in (512,1536)))
        values['output-1024-over-64'].append(statistics.mean(logarithm(language,target,1024)-logarithm(language,target,64)
            for language in ('zh','en') for target in (512,1536)))
        values['input-1536-over-512'].append(statistics.mean(logarithm(language,1536,budget)-logarithm(language,512,budget)
            for language in ('zh','en') for budget in (64,256,1024)))
    return {name:dict(ordinary=interval(data,ratio=True),simultaneous=interval(data,simultaneous=True,ratio=True))
            for name,data in values.items()}


def summarize_trace(events):
    aliases={'prefill':'prefill','extend':'prefill','draft':'draft','draft_forward':'draft',
             'verify':'verify','target_verify':'verify','decode':'decode'}
    scopes=[]
    candidates=Counter()
    kernels=[]
    launches=defaultdict(list)
    for item in events:
        if item.get('ph')!='X' or not isinstance(item.get('dur'),(int,float)) or item['dur']<0:
            continue
        category=item.get('cat','')
        name=item.get('name','')
        if category in ('cpu_op','user_annotation','python_function'):
            normalized=name.lower().removeprefix('sglang::')
            if re.search('prefill|extend|draft|verify|decode',name,re.I): candidates[name]+=1
            if normalized in aliases:
                scopes.append(dict(item,stage=aliases[normalized]))
        if category=='kernel': kernels.append(item)
        if category=='cuda_runtime' and 'correlation' in item.get('args',{}):
            launches[item['args']['correlation']].append(item)
    overlapping=any(left.get('pid')==right.get('pid') and left.get('tid')==right.get('tid')
        and left['stage']!=right['stage'] and max(left['ts'],right['ts'])<min(left['ts']+left['dur'],right['ts']+right['dur'])
        for index,left in enumerate(scopes) for right in scopes[index+1:])
    attributed=defaultdict(float)
    for kernel in kernels:
        matching=launches.get(kernel.get('args',{}).get('correlation'),[])
        stages=set()
        if len(matching)==1:
            launch=matching[0]
            stages={scope['stage'] for scope in scopes if scope.get('pid')==launch.get('pid')
                and scope.get('tid')==launch.get('tid') and scope['ts']<=launch['ts']<=scope['ts']+scope['dur']}
        attributed[next(iter(stages)) if len(stages)==1 else 'unattributed']+=kernel['dur']
    total=sum(kernel['dur'] for kernel in kernels)
    return dict(kernel_events=len(kernels),kernel_total_us=total,unattributed_kernel_us=attributed['unattributed'],
        attributed_kernel_us=dict(attributed),stage_candidates=dict(candidates),
        inclusive_scope_us={stage:sum(scope['dur'] for scope in scopes if scope['stage']==stage) for stage in sorted({scope['stage'] for scope in scopes})},
        overlapping_stage_scopes=overlapping,stage_decomposition_available=total>0 and total>attributed['unattributed'],
        timing_scope='sum of kernel durations, not elapsed wall time; overlapping CPU scopes not additive')


def load_trace(path):
    opener=gzip.open if path.name.endswith('.gz') else open
    with opener(path,'rt') as source:
        document=json.load(source)
    return summarize_trace(document['traceEvents'] if isinstance(document,dict) else document)


def profile_body(client,output):
    schema=client.request('/openapi.json')
    operation=schema['paths']['/start_profile']['post']
    shape=operation.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
    def properties_of(value):
        if '$ref' in value:
            value=schema['components']['schemas'][value['$ref'].split('/')[-1]]
        properties=dict(value.get('properties',{}))
        for name in ('anyOf','allOf'):
            for branch in value.get(name,[]): properties.update(properties_of(branch))
        return properties
    properties=properties_of(shape)
    if 'output_dir' not in properties:
        raise ValueError('public profile API has no recognized output directory field')
    body={'output_dir':str(output)}
    if 'record_shapes' in properties: body['record_shapes']=True
    if 'with_stack' in properties: body['with_stack']=False
    return body


def profiles(private,root,dataset,environment,public):
    directory=private/'profiles'
    directory.mkdir()
    selected=[request for request in dataset['requests'] if request['base_id']=='card-00'
              and request['input_target']==512 and request['answer_style']=='short']
    records=[]
    for number in (0,1):
        output=directory/f'round-{number+1:02d}'
        output.mkdir()
        assigned=root['gpus'] if number==0 else list(reversed(root['gpus']))
        write_json(output/'deployment.json',dict(assignments=[dict(arm=arm,gpu=gpu,port=port)
            for arm,gpu,port in zip(root['candidate_arms'],assigned,root['ports'])]))
        with ExitStack() as resources:
            servers=[Server(arm,gpu,port,output,environment) for arm,gpu,port in zip(root['candidate_arms'],assigned,root['ports'])]
            for server in servers:
                resources.callback(server.stop)
                server.start()
            for server in servers: server.wait_ready(1200)
            for arm,gpu,port in zip(root['candidate_arms'],assigned,root['ports']):
                url=f'http://127.0.0.1:{port}'
                client=NativeClient(url,output/(arm['name']+'-api'))
                captured=CapturedArm(arm['name'],url,output_dir=output,block_size=arm['block'],tree_sha=arm['tree_sha'],
                    env=arm['env'],trace_timing=True,sampling=sampling('fixed'))
                captured.begin_session()
                for request in selected:
                    for budget in (1,64,1024):
                        captured.step(request['input_ids'],budget,rid='profile-warm-'+str(budget)+'-'+request['id'])
                    first=captured.step(request['input_ids'],1,rid='first-token-'+request['id'])
                    check_length('fixed',first['tokens'],1,first['finish_reason'])
                    records.append(dict(kind='first-token-proxy',round=number+1,arm=arm['name'],gpu_uuid=gpu['uuid'],
                        id=request['id'],language=request['language'],budget=1,result=first))
                    for budget in (64,1024):
                        trace_directory=output/(arm['name']+'-'+request['language']+'-'+str(budget))
                        trace_directory.mkdir()
                        record=dict(kind='torch-profile',round=number+1,arm=arm['name'],gpu_uuid=gpu['uuid'],
                            id=request['id'],language=request['language'],budget=budget,trace_directory=str(trace_directory))
                        try:
                            if sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())>=PROFILE_LIMIT:
                                raise ValueError('profile evidence budget reached')
                            body=profile_body(client,trace_directory)
                            client.post('/start_profile',body)
                            try:
                                record['result']=captured.step(request['input_ids'],budget,rid='profile-'+request['id'])
                                check_length('fixed',record['result']['tokens'],budget,record['result']['finish_reason'])
                            finally:
                                client.post('/stop_profile',{})
                            deadline=time.monotonic()+30
                            while True:
                                traces=[path for path in trace_directory.rglob('*') if path.is_file() and path.stat().st_size>0 and
                                        (path.name.endswith('.json') or path.name.endswith('.json.gz'))]
                                if traces or time.monotonic()>=deadline: break
                                time.sleep(1)
                            if not traces: raise ValueError('public profile API returned no readable trace')
                            record['traces']=[dict(path=str(path),sha256=digest(path),summary=load_trace(path)) for path in sorted(traces)]
                            record['status']='captured'
                        except Exception as error:
                            record.update(status='unavailable',error_type=type(error).__name__,reason=str(error))
                            try:
                                client.post('/stop_profile',{})
                            except Exception:
                                pass
                        records.append(record)
                        event(public,'profile-probe-complete',round=number+1,arm=arm['name'],language=request['language'],
                              budget=budget,status=record['status'])
        check_ports(root['ports'])
        wait_for_idle([0,1])
    write_json(directory/'records.json',records)


def run(private,data_path,public):
    os.umask(0o077)
    private.mkdir(mode=0o700)
    event(public,'execution-start')
    with (private/'runner.log').open('x') as log,redirect_stdout(log),redirect_stderr(log):
        environment=clean_environment()
        signal.signal(signal.SIGTERM,interrupted)
        try:
            with ExitStack() as resources:
                gpus=wait_for_idle([0,1])
                for gpu in gpus: resources.enter_context(gpu_lock(gpu))
                root=build(private,data_path,public,environment,gpus)
                root.update(diagnostic_protocol='matched-factorial-v1',suites=['zh-short','en-short','zh-long','en-long'],
                            conditions=[dict(mode=mode,budget=budget) for mode,budget in CONDITIONS])
                write_json(private/'manifest.json',root)
                dataset=json.loads(data_path.read_text())
                validate_dataset(dataset)
                for mode,budget in CONDITIONS:
                    requests_data=dataset['requests'] if mode=='natural' else [request for request in dataset['requests'] if request['answer_style']=='short']
                    campaign=dict(root,requests=requests_data,max_new_tokens=budget,length_mode=mode,
                        sampling=sampling(mode),suites=sorted({request['suite'] for request in requests_data}),
                        per_suite=24,condition_directory=str(private/f'{mode}-{budget}'))
                    campaign['protocol_id']=measurement_protocol_id(campaign)
                    timing(private/f'{mode}-{budget}',campaign,environment,public)
                write_json(private/'timing-cleanup.json',wait_for_idle([0,1]))
                write_json(private/'profile-start.json',dict(started_unix=time.time()))
                event(public,'all-timing-complete-profiling-start')
                profiles(private,root,dataset,environment,public)
                check_ports(root['ports'])
                write_json(private/'cleanup.json',wait_for_idle([0,1]))
                subprocess.run(['git','diff','--exit-code',root['source_pin'],'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
                publish(public/'gpu-complete.json',dict(gpu_work_complete=True,scientific_acceptance_complete=False,
                                                        source_pin=root['source_pin']))
                event(public,'gpu-work-complete-independent-replay-pending')
        except BaseException as error:
            traceback.print_exc()
            write_json(private/'failed.json',dict(error=repr(error),time_unix=time.time()))
            event(public,'execution-failed',error_type=type(error).__name__)
            try:
                write_json(private/'failure-cleanup.json',wait_for_idle([0,1]))
                check_ports(root['ports'])
            except Exception as cleanup:
                write_json(private/'failure-cleanup-error.json',dict(error=repr(cleanup)))
            return 1
    return 0


def metadata(request):
    return {key:request[key] for key in ('base_id','language','input_target','answer_style')}


def profile_report(private,root,dataset):
    records=json.loads((private/'profiles/records.json').read_text())
    expected={(number,arm,language,budget) for number in (1,2) for arm in ('stock','final')
              for language in ('zh','en') for budget in (1,64,1024)}
    actual=[(row['round'],row['arm'],row['language'],row['budget']) for row in records]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError('missing/duplicate declared profiling probes')
    requests_data={row['id']:row for row in dataset['requests']}
    summaries=[]
    first=[]
    for record in records:
        arms={arm['name']:arm for arm in root['candidate_arms']}
        arm=arms[record['arm']]
        assignments=json.loads((private/'profiles'/f'round-{record["round"]:02d}'/'deployment.json').read_text())['assignments']
        assigned=root['gpus'] if record['round']==1 else list(reversed(root['gpus']))
        expected_assignments=[dict(arm=spec,gpu=gpu,port=port) for spec,gpu,port in zip(root['candidate_arms'],assigned,root['ports'])]
        if assignments!=expected_assignments:
            raise ValueError('profiling physical GPU assignment changed')
        assignment=next(value for value in assignments if value['arm']['name']==record['arm'])
        if record['gpu_uuid']!=assignment['gpu']['uuid']:
            raise ValueError('profiling probe used wrong physical GPU')
        if 'result' in record:
            result=record['result']
            packet=read_reference(result['raw_evidence'],private)
            request=requests_data[record['id']]
            checked_server(result['generator'],private)
            actual_arguments=server_arguments(read_reference(result['generator']['evidence'],private)['response'])
            expected_arguments=dict(root['launch_protocol'],speculative_algorithm='DFLASH',speculative_num_draft_tokens=arm['block'])
            if (packet['request']['input_ids']!=request['input_ids'] or packet['response']['output_ids']!=result['output_ids']
                    or packet['request']['sampling_params']!=dict(sampling('fixed'),max_new_tokens=record['budget'])
                    or sha_ids(result['output_ids'])!=result['output_sha256']
                    or result['generator']['tree_sha']!=arm['tree_sha']
                    or any(actual_arguments.get(key)!=value for key,value in expected_arguments.items())
                    or result['client_timing']['started_unix']<json.loads((private/'profile-start.json').read_text())['started_unix']):
                raise ValueError('profile probe detached from original request/output')
            check_length('fixed',result['tokens'],record['budget'],result['finish_reason'])
        if record['kind']=='first-token-proxy':
            first.append({key:record[key] for key in ('round','arm','language') }|dict(latency_ms=record['result']['latency_ms']))
            continue
        traces=[]
        for trace in record.get('traces',[]):
            path=Path(trace['path'])
            if digest(path)!=trace['sha256'] or load_trace(path)!=trace['summary']:
                raise ValueError('profile trace changed on independent replay')
            traces.append(trace['summary'])
        summaries.append({key:record[key] for key in ('round','arm','language','budget','status')}|
                         dict(traces=traces,reason=record.get('reason')))
    return dict(first_token_proxy=first,profiles=summaries,
        captured=sum(row['status']=='captured' for row in summaries),unavailable=sum(row['status']!='captured' for row in summaries),
        limitation='profile times excluded from performance; first-token includes initial decoding and HTTP; no mathematical phase split')


def analyze(private,out):
    root=json.loads((private/'manifest.json').read_text())
    if root.get('diagnostic_protocol')!='matched-factorial-v1' or digest(root['dataset_path'])!=root['dataset_sha256']:
        raise ValueError('wrong protocol or changed diagnostic dataset')
    if digest(root['source_archive'])!=root['source_archive_sha256']:
        raise ValueError('frozen source archive changed')
    with tarfile.open(root['source_archive']) as archive:
        for name,checksum in root['source_sha256'].items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=checksum or digest(ROOT/name)!=checksum:
                raise ValueError('replay differs from frozen runtime source')
    dataset=json.loads(Path(root['dataset_path']).read_text())
    validate_dataset(dataset)
    previous=-math.inf
    results=[]
    fixed=[]
    curve_rows=[]
    for mode,budget in CONDITIONS:
        directory=private/f'{mode}-{budget}'
        campaign=json.loads((directory/'manifest.json').read_text())
        expected=dataset['requests'] if mode=='natural' else [row for row in dataset['requests'] if row['answer_style']=='short']
        if (campaign['requests']!=expected or campaign['sampling']!=sampling(mode)
                or campaign['source_sha256']!=root['source_sha256'] or campaign['source_pin']!=root['source_pin']):
            raise ValueError('diagnostic condition changed its factors, source or sampling')
        sessions=[validate_session(directory/phase,campaign,packet_validator=packet_validator(mode)) for phase in PHASES]
        check_phase_order([session[0] for session in sessions])
        for session in sessions:
            if session[0]['started_unix']<previous: raise ValueError('conditions overlap or are reordered')
            previous=session[0]['completed_unix']
        nulls=[dict(session_id=phase,protocol_id=campaign['protocol_id'],source_sha256=session[0]['source_sha256'],
                    interval=base_interval(session[1],expected,'throughput')) for phase,session in zip(PHASES,sessions) if phase!='candidate']
        calibration=calibration_from_intervals(nulls,declared_sessions=['null-pre','null-post'],
            protocol_id=campaign['protocol_id'],campaign_id=campaign['campaign_id'],policy=POLICY)
        pairs=sessions[1][1]
        cells=[]
        for language in ('zh','en'):
            for target in (512,1536):
                for style in (('short','long') if mode=='natural' else ('short',)):
                    selected=[row for row in expected if row['language']==language and row['input_target']==target and row['answer_style']==style]
                    subset=[pair for pair in pairs if pair['id'] in {row['id'] for row in selected}]
                    logs=cluster_groups(subset,selected,'latency')
                    data=[value for values in logs.values() for value in values]
                    outputs={}
                    for key,role in (('a','stock'),('b','final')):
                        values=[pair[key] for pair in subset]
                        outputs[role]=dict(mean_tokens=statistics.mean(row['completion_tokens'] for row in values),
                            median_tokens=statistics.median(row['completion_tokens'] for row in values),
                            mean_latency_ms=statistics.mean(row['latency_s'] for row in values)*1000,
                            stop=sum(row['finish_reason']=='stop' for row in values),length=sum(row['finish_reason']=='length' for row in values),
                            spec_verify_ct_mean=statistics.mean(row['spec_verify_ct'] for row in values),
                            counter_scope='native counter; final TLV interpretation not independently validated')
                    cells.append(dict(language=language,input_target=target,answer_style=style,latency=interval(data,ratio=True),outputs=outputs))
        for request in expected:
            selected=[pair for pair in pairs if pair['id']==request['id']]
            ratio=math.exp(statistics.mean(math.log(pair['a']['latency_s']/pair['b']['latency_s']) for pair in selected))
            if mode=='fixed':
                fixed.append(dict(metadata(request),budget=budget,ratio=ratio))
                for key,role in (('a','stock'),('b','final')):
                    curve_rows.append(dict(metadata(request),budget=budget,arm=role,
                                           mean_latency_ms=statistics.mean(pair[key]['latency_s'] for pair in selected)*1000))
        results.append(dict(mode=mode,budget=budget,independent_cards=12,requests=len(expected),noise=calibration['noise'],
                            nulls=nulls,cells=cells,latency=base_interval(pairs,expected)))
    if json.loads((private/'profile-start.json').read_text())['started_unix']<=previous:
        raise ValueError('profiling contaminated formal timing')
    cleanup=json.loads((private/'cleanup.json').read_text())
    if len(cleanup)!=2 or any(gpu['memory_used_mib']>256 or gpu['utilization']>10 for gpu in cleanup):
        raise ValueError('GPU cleanup not established')
    profile=profile_report(private,root,dataset)
    curves=[]
    for language in ('zh','en'):
        for target in (512,1536):
            for budget in (64,256,1024):
                for role in ('stock','final'):
                    values=[row['mean_latency_ms'] for row in curve_rows if row['language']==language
                            and row['input_target']==target and row['budget']==budget and row['arm']==role]
                    curves.append(dict(language=language,input_target=target,budget=budget,arm=role,
                                       independent_cards=12,latency_ms=interval(values)))
    result=dict(execution_complete=True,source_pin=root['source_pin'],dataset_sha256=root['dataset_sha256'],
        independent_cards=12,natural_requests=96,fixed_requests_per_budget=48,conditions=results,primary_contrasts=contrasts(fixed),
        latency_curve_aggregates=curves,profiling=profile,final_modified=False,sealed_read=False,promoted=False,ledger_eligible=False,
        limitations=['synthetic matched workload, not universal language causality','natural length instructions may not be obeyed',
            'ignore-EOS is an intervention, not completed semantic tasks','no new lossless or semantic noninferiority claim',
            'GPU profile scope coverage may be incomplete','final verify counter not independently normalized'])
    publish(out,result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','run','audit'])
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--public',type=Path)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare': prepare(args.private,args.public)
    elif args.mode=='run': raise SystemExit(run(args.private,args.dataset,args.public))
    else:
        if os.environ.get('CUDA_VISIBLE_DEVICES')!='': raise ValueError('replay must explicitly disable CUDA')
        result=analyze(args.private,args.out)
        print(json.dumps(dict(replay_complete=True,source_pin=result['source_pin'],profiles_captured=result['profiling']['captured'])))
