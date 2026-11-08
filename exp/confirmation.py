"""Frozen counterexample confirmation; publish aggregates, never sample contents."""

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
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
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.dev_campaign import check_phase_order
from controller.http_transport import sha_ids
from controller.paper_policy import POLICY, calibration_from_intervals, measurement_protocol_id
from controller.stats import bootstrap_ci, stratified_geomean_ci
from exp.generalization_audit import PHASES, cluster_groups, rescore, validate_session, verify_quality
from exp.generalization_data import REVISIONS, SOURCES, duplicate, source_rows
from exp.generalization_quality import run_code
from exp.generalization_run import build, event, quality, scoring, timing
from exp.p3_pair_run import SUITES, check_ports, clean_environment, gpu_lock, interrupted, wait_for_idle, write_json
from harness.baseline_validation import read_rows

SEED = '261102501-confirmation-v1'
COUNTS = {'chinese-qa':60, 'summary':60, 'humaneval':40}
CAPS = (2048,4096)
OLD = ROOT/'logs/generalization-data-20261108-a04'
OLD_SHA = '7c179e5d0f84fb87b0ebcdb78a70248f15c01e51d9668ee1b72da5cdcb514486'
DIALOG_REV = '848cc8c05e0a04def79326539de827f1b28786a0'


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(path, value):
    write_json(path, value)
    path.chmod(0o644)


def choose(pool, excluded_prompts, excluded_ids, count):
    def key(row):
        return hashlib.sha256((SEED+'|'+row['suite']+'|'+row['source_id']).encode()).hexdigest()
    eligible = [row for row in pool if row['source_id'] not in excluded_ids
                and 0 < len(row['input_ids']) <= 8192 and not duplicate(row['prompt'],excluded_prompts)]
    eligible.sort(key=lambda row:(len(row['input_ids']),key(row)))
    selected = []
    for band, candidates in (('short',eligible[:len(eligible)//2]),('long',eligible[len(eligible)//2:])):
        chosen = []
        for row in sorted(candidates,key=key):
            if not duplicate(row['prompt'],[item['prompt'] for item in selected+chosen]):
                chosen.append(dict(row,input_band=band))
            if len(chosen)==count//2:
                break
        if len(chosen)!=count//2:
            raise ValueError('insufficient unique confirmation stratum')
        selected.extend(chosen)
    return selected


def condition_requests(requests,cap):
    if cap not in CAPS or any(row['suite'] not in COUNTS for row in requests):
        raise ValueError('unknown confirmation condition or domain')
    return [row for row in requests if (row['suite']=='humaneval')==(cap==4096)]


def interval(values,simultaneous=False,ratio=False):
    if len(values)<2 or any(not math.isfinite(value) for value in values):
        raise ValueError('at least two finite independent request clusters required')
    alpha=.05/(2*(3 if simultaneous else 1))
    mean,lower=bootstrap_ci(values,iters=20000,alpha=alpha,seed=261102501)
    _,negative=bootstrap_ci([-value for value in values],iters=20000,alpha=alpha,seed=261102501)
    transform=math.exp if ratio else float
    return dict(mean=transform(mean),lower=transform(lower),upper=transform(-negative),
                n=len(values),family_size=3 if simultaneous else 1,
                confidence=1-2*alpha,method='controller.stats request-cluster percentile bootstrap')


def outcome(bounds,boundary):
    if bounds['upper']<boundary:
        return 'confirmed-counterexample'
    if bounds['lower']>boundary:
        return 'opposite-direction-on-this-sample'
    return 'insufficient-evidence'


def exclusions():
    if checksum(OLD/'dataset.json')!=OLD_SHA:
        raise ValueError('previous audit identity changed')
    previous=json.loads((OLD/'dataset.json').read_text())
    originals=[json.loads(line) for suite in SUITES
               for line in (ROOT/'assets/upstream/dev'/(suite+'.jsonl')).read_text().splitlines() if line]
    if len(originals)!=100 or len(previous['items'])!=200:
        raise ValueError('incomplete prior exclusion sets')
    return originals,previous


def encode(tokenizer,prompt):
    result=tokenizer.apply_chat_template([dict(role='user',content=prompt)],add_generation_prompt=True,
                                         tokenize=True,enable_thinking=True)
    return list(result if isinstance(result,list) else result['input_ids'])


def summary_rows(rows):
    output=[]
    for row in rows:
        if not row.get('dialogue','').strip() or not row.get('summary1','').strip():
            raise ValueError('missing fixed first human-reference summary fields')
        output.append(dict(suite='summary',source_id=row['fname'],thinking_required=True,
            prompt='Summarize the following dialogue concisely, preserving the important facts.\n\n'+row['dialogue'],
            metric='rouge_l',answer=row['summary1'],reference_kind='human-authored-summary1'))
    return output


def prepare(private,public):
    from transformers import AutoTokenizer
    import requests
    os.umask(0o077)
    private.mkdir(mode=0o700)
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    originals,previous=exclusions()
    excluded=[row['turns'][0] for row in originals]+[row['prompt'] for row in previous['items']]
    tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True)
    cached={(source['repo'],source['filename']):source for source in previous['sources']}
    pools,sources={},[]
    for domain in ('chinese-qa','humaneval'):
        repo,filename,license_name=SOURCES[domain]
        source=cached[repo,filename]
        if source['revision']!=REVISIONS[repo] or checksum(source['path'])!=source['sha256']:
            raise ValueError('cached public source changed')
        content=Path(source['path']).read_bytes()
        destination=private/Path(source['path']).name
        destination.write_bytes(content)
        source=dict(source,path=str(destination),license=license_name)
        sources.append(source)
        decoded=gzip.decompress(content).decode() if filename.endswith('.gz') else content.decode()
        rows=[json.loads(line) for line in decoded.splitlines() if line] if '.jsonl' in filename else json.loads(decoded)
        pools[domain]=source_rows(domain,rows)
    repo='cylnlp/dialogsum'
    filename='DialogSum_Data/dialogsum.test.jsonl'
    url='https://raw.githubusercontent.com/'+repo+'/'+DIALOG_REV+'/'+filename
    session=requests.Session()
    session.trust_env=False
    session.proxies={'https':'http://10.51.6.1:6890'}
    response=session.get(url,timeout=180)
    response.raise_for_status()
    destination=private/'dialogsum.test.jsonl'
    destination.write_bytes(response.content)
    sources.append(dict(repo=repo,filename=filename,revision=DIALOG_REV,url=url,path=str(destination),
                        sha256=checksum(destination),bytes=len(response.content),license='consult pinned upstream data terms'))
    pools['summary']=summary_rows([json.loads(line) for line in response.text.splitlines() if line])
    items=[]
    counts={}
    for domain,count in COUNTS.items():
        for item in pools[domain]:
            item['input_ids']=encode(tokenizer,item['prompt'])
        old_ids={item['source_id'] for item in previous['items'] if item['suite']==domain and domain!='summary'}
        old_ids.update(str(row.get('task_id',row['id'].removeprefix(domain+'-')))
                       for row in originals if row['suite']==domain)
        selected=choose(pools[domain],excluded+[item['prompt'] for item in items],old_ids,count)
        for item in selected:
            item.update(id=domain+'-confirm-'+hashlib.sha256(item['source_id'].encode()).hexdigest()[:16],
                        input_sha256=sha_ids(item['input_ids']),turn=0)
        items.extend(selected)
        counts[domain]=dict(selected=count,pool=len(pools[domain]),short=count//2,long=count//2,
            min_prompt_tokens=min(len(item['input_ids']) for item in selected),
            max_prompt_tokens=max(len(item['input_ids']) for item in selected))
    requests_data=[{key:item[key] for key in ('id','suite','turn','input_ids','input_sha256','input_band')} for item in items]
    dataset=dict(items=items,requests=requests_data,seed=SEED,sources=sources,
                 excluded_author_dev=100,excluded_previous_audit=200,previous_dataset_sha256=OLD_SHA,
                 confirmation_kind='counterexamples-v1')
    write_json(private/'dataset.json',dataset)
    publish(public/'preparation.json',dict(prepared=True,unique_requests=160,domains=counts,seed=SEED,
        caps=list(CAPS),dataset_sha256=checksum(private/'dataset.json'),previous_dataset_sha256=OLD_SHA,
        author_dev_excluded=100,previous_audit_excluded=200,
        sources=[{key:value for key,value in source.items() if key!='path'} for source in sources],
        blindness='private evaluator only; agent reads aggregates; not independent-party secrecy',
        limitations=['public data may have been seen','DialogSum is not the previous Alpaca distribution',
                     'summary metric is a proxy, not semantic noninferiority','not original sealed']))
    publish(public/'preparation-validation.json',verify_prepared(private,public))


def verify_prepared(private,public):
    from transformers import AutoTokenizer
    originals,previous=exclusions()
    dataset=json.loads((private/'dataset.json').read_text())
    summary=json.loads((public/'preparation.json').read_text())
    if (checksum(private/'dataset.json')!=summary['dataset_sha256'] or dataset['seed']!=SEED
            or dataset['previous_dataset_sha256']!=OLD_SHA or len(dataset['items'])!=160
            or len(dataset['requests'])!=160 or len({item['id'] for item in dataset['items']})!=160):
        raise ValueError('changed or incomplete frozen confirmation data')
    tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True)
    seen=[row['turns'][0] for row in originals]+[row['prompt'] for row in previous['items']]
    for item,request in zip(dataset['items'],dataset['requests']):
        if duplicate(item['prompt'],seen):
            raise ValueError('known or internal near duplicate')
        seen.append(item['prompt'])
        excluded_ids={old['source_id'] for old in previous['items'] if old['suite']==item['suite'] and item['suite']!='summary'}
        excluded_ids.update(str(row.get('task_id',row['id'].removeprefix(item['suite']+'-')))
                            for row in originals if row['suite']==item['suite'])
        if item['source_id'] in excluded_ids:
            raise ValueError('known source identity reused')
        encoded=encode(tokenizer,item['prompt'])
        expected={key:item[key] for key in ('id','suite','turn','input_ids','input_sha256','input_band')}
        if request!=expected or encoded!=request['input_ids'] or sha_ids(encoded)!=request['input_sha256']:
            raise ValueError('independent request identity/retokenization mismatch')
    for domain,count in COUNTS.items():
        selected=[item for item in dataset['items'] if item['suite']==domain]
        if len(selected)!=count or any(sum(item['input_band']==band for item in selected)!=count//2 for band in ('short','long')):
            raise ValueError('wrong fixed domain/stratum counts')
    controls=[]
    for item in dataset['items']:
        if item['metric']=='code':
            controls.append(run_code(item['code_prompt']+item['canonical'],item['tests'])['status']=='pass')
    if len(controls)!=40 or not all(controls):
        raise ValueError('reference code sandbox control failed')
    for source in dataset['sources']:
        expected_revision=DIALOG_REV if source['repo']=='cylnlp/dialogsum' else REVISIONS[source['repo']]
        if source['revision']!=expected_revision or checksum(source['path'])!=source['sha256']:
            raise ValueError('frozen public source changed')
    return dict(passed=True,unique_requests=160,author_dev_excluded=100,previous_audit_excluded=200,
                exact_and_near_overlap=0,retokenization_passed=True,reference_code_passed=40,
                source_sha256_passed=True,dataset_sha256=summary['dataset_sha256'])


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
                for gpu in gpus:
                    resources.enter_context(gpu_lock(gpu))
                root=build(private,data_path,public,environment,gpus)
                root.update(confirmation_kind='counterexamples-v1',suites=list(COUNTS),
                            quality_location='local-cpu-sandbox',declared_caps=list(CAPS))
                write_json(private/'manifest.json',root)
                dataset=json.loads(data_path.read_text())
                if checksum(data_path)!=json.loads((public/'preparation-validation.json').read_text())['dataset_sha256']:
                    raise ValueError('independent preparation validation is stale')
                campaigns=[]
                for cap in CAPS:
                    requests_data=condition_requests(dataset['requests'],cap)
                    campaign=dict(root,requests=requests_data,max_new_tokens=cap,
                        suites=sorted({request['suite'] for request in requests_data}),
                        per_suite=60 if cap==2048 else 40,condition_directory=str(private/f'cap-{cap}'))
                    campaign['protocol_id']=measurement_protocol_id(campaign)
                    timing(private/f'cap-{cap}',campaign,environment,public)
                    campaigns.append(campaign)
                write_json(private/'timing-cleanup.json',wait_for_idle([0,1]))
                write_json(private/'score-start.json',dict(started_unix=time.time()))
                scoring(private,root,campaigns,environment,public)
                check_ports([30100,30110,30120,30130])
                write_json(private/'cleanup.json',wait_for_idle([0,1]))
                subprocess.run(['git','diff','--exit-code',root['source_pin'],'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
                publish(public/'gpu-complete.json',dict(gpu_work_complete=True,scientific_acceptance_complete=False,
                    source_pin=root['source_pin'],quality_location='local-cpu-sandbox'))
                event(public,'gpu-work-complete-local-quality-pending')
        except BaseException as error:
            traceback.print_exc()
            write_json(private/'failed.json',dict(error=repr(error),time_unix=time.time()))
            event(public,'execution-failed',error_type=type(error).__name__)
            try:
                write_json(private/'failure-cleanup.json',wait_for_idle([0,1]))
                check_ports([30100,30110,30120,30130])
            except Exception as cleanup:
                write_json(private/'failure-cleanup-error.json',dict(error=repr(cleanup)))
            return 1
    return 0


def quality_metrics(directory,requests_data):
    rows=read_rows(directory/'quality.jsonl')
    expected={(number,role,request['id']) for number in (1,2) for role in ('stock','final') for request in requests_data}
    actual=[(row['round'],row['role'],row['id']) for row in rows]
    if set(actual)!=expected or len(actual)!=len(expected):
        raise ValueError('missing or duplicate quality output')
    indexed={(row['round'],row['role'],row['id']):row for row in rows}
    for number in (1,2):
        for pair in read_rows(directory/'candidate'/f'round-{number:02d}'/'pairs.jsonl'):
            for key,role in (('a','stock'),('b','final')):
                if indexed[number,role,pair['id']]['output_sha256']!=pair[key]['output_sha256']:
                    raise ValueError('quality detached from actual measured output')
    result={}
    for domain in sorted({request['suite'] for request in requests_data}):
        selected=[request for request in requests_data if request['suite']==domain]
        means={role:[] for role in ('stock','final')}
        for request in selected:
            for role in means:
                scores=[indexed[number,role,request['id']]['quality']['score'] for number in (1,2)]
                if any(score is None or not math.isfinite(score) for score in scores):
                    raise ValueError('ungraded primary quality endpoint')
                means[role].append(statistics.mean(scores))
        differences=[final-stock for stock,final in zip(means['stock'],means['final'])]
        simultaneous=interval(differences,simultaneous=True)
        result[domain]=dict(n=len(selected),metric=indexed[1,'stock',selected[0]['id']]['quality']['metric'],
            stock_mean=statistics.mean(means['stock']),final_mean=statistics.mean(means['final']),
            paired_difference=interval(differences),simultaneous_difference=simultaneous,
            outcome=outcome(simultaneous,0),semantic_noninferiority_proven=False)
    return result


def analyze(private,out):
    root=json.loads((private/'manifest.json').read_text())
    data_path=Path(root['dataset_path'])
    if checksum(data_path)!=root['dataset_sha256'] or checksum(root['source_archive'])!=root['source_archive_sha256']:
        raise ValueError('frozen dataset or source archive changed')
    if root.get('confirmation_kind')!='counterexamples-v1' or root.get('declared_caps')!=list(CAPS):
        raise ValueError('wrong confirmation protocol')
    with tarfile.open(root['source_archive']) as archive:
        for name,digest in root['source_sha256'].items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=digest:
                raise ValueError('runtime source differs from frozen archive')
    dataset=json.loads(data_path.read_text())
    verify_quality(private,dataset,caps=CAPS)
    head=json.loads((private/'head-preflight/result.json').read_text())
    if (head.get('native_reverse_token_differences')!=0 or head.get('tokens')!=1
            or head.get('head_identity',{}).get('source_sha256')!=root['source_sha256']['controller/head_reference.py']
            or not head.get('checks') or any(not math.isfinite(check[key]) or check[key]>.001
                for check in head['checks'] for key in ('native_logprob_error','native_choice_margin','max_logit_difference'))):
        raise ValueError('independent FP32 head preflight failed')
    results=[]
    previous=-math.inf
    for cap in CAPS:
        directory=private/f'cap-{cap}'
        campaign=json.loads((directory/'manifest.json').read_text())
        requests_data=condition_requests(dataset['requests'],cap)
        if (campaign['requests']!=requests_data or campaign['source_pin']!=root['source_pin']
                or campaign['source_sha256']!=root['source_sha256']):
            raise ValueError('condition differs from frozen requests/source')
        sessions=[validate_session(directory/phase,campaign) for phase in PHASES]
        check_phase_order([session[0] for session in sessions])
        for session in sessions:
            if session[0]['started_unix']<previous:
                raise ValueError('timing conditions overlap or reordered')
            previous=session[0]['completed_unix']
        nulls=[dict(session_id=phase,protocol_id=campaign['protocol_id'],source_sha256=session[0]['source_sha256'],
                    interval=session[0]['interval']) for phase,session in zip(PHASES,sessions) if phase!='candidate']
        calibration=calibration_from_intervals(nulls,declared_sessions=['null-pre','null-post'],
            protocol_id=campaign['protocol_id'],campaign_id=campaign['campaign_id'],policy=POLICY)
        domains=sorted({request['suite'] for request in requests_data})
        correct,local=rescore(directory,campaign,requests_data,domains=domains)
        pairs=sessions[1][1]
        quality_result=quality_metrics(directory,requests_data)
        domain_result={}
        for domain in domains:
            selected=[request for request in requests_data if request['suite']==domain]
            subset=[pair for pair in pairs if pair['suite']==domain]
            throughput=cluster_groups(subset,selected)
            latency=cluster_groups(subset,selected,'latency')
            bounds=interval(latency[domain],simultaneous=True,ratio=True)
            outputs={}
            for key,role in (('a','stock'),('b','final')):
                values=[pair[key] for pair in subset]
                outputs[role]=dict(mean_tokens=statistics.mean(row['completion_tokens'] for row in values),
                    mean_latency_s=statistics.mean(row['latency_s'] for row in values),
                    stop=sum(row['finish_reason']=='stop' for row in values),
                    length=sum(row['finish_reason']=='length' for row in values))
            domain_result[domain]=dict(n=len(selected),throughput=stratified_geomean_ci(throughput),
                latency=stratified_geomean_ci(latency),simultaneous_latency=bounds,
                latency_outcome=outcome(bounds,1),quality=quality_result[domain],forcing=local[domain],outputs=outputs,
                round_latency=[math.exp(statistics.mean(math.log(pair['a']['latency_s']/pair['b']['latency_s'])
                    for pair in subset if pair['round']==number)) for number in (1,2)])
        results.append(dict(cap=cap,unique_requests=len(requests_data),noise=calibration['noise'],
            nulls=nulls,forcing_passed=correct['correctness_passed'],domains=domain_result))
    if json.loads((private/'score-start.json').read_text())['started_unix']<=previous:
        raise ValueError('scoring overlapped timing')
    cleanup=json.loads((private/'cleanup.json').read_text())
    if len(cleanup)!=2 or any(gpu['memory_used_mib']>256 or gpu['utilization']>10 for gpu in cleanup):
        raise ValueError('GPU cleanup not established')
    result=dict(execution_complete=True,source_pin=root['source_pin'],dataset_sha256=root['dataset_sha256'],
        unique_requests=160,caps=results,primary_endpoints={
            'chinese_latency':results[0]['domains']['chinese-qa']['latency_outcome'],
            'summary_rouge_l':results[0]['domains']['summary']['quality']['outcome'],
            'code_pass_rate':results[1]['domains']['humaneval']['quality']['outcome']},
        family_size=3,final_modified=False,sealed_read=False,promoted=False,ledger_eligible=False,
        limitations=['summary source changed: cannot refute old Alpaca alert',
            'proxies do not prove semantic quality or mathematical losslessness',
            'nonsignificance is not noninferiority','public data may have been seen',
            'confirmation, not causal profiling or autonomous discovery'])
    if out.exists():
        raise FileExistsError('confirmation report is append-only')
    publish(out,result)
    return result


def finalize(private,public):
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='':
        raise ValueError('local evaluator must explicitly disable CUDA')
    if (public/'exit-status').read_text().strip()!='0' or not (public/'gpu-complete.json').exists():
        raise ValueError('GPU execution not complete')
    root=json.loads((private/'manifest.json').read_text())
    if root['quality_location']!='local-cpu-sandbox':
        raise ValueError('quality location changed')
    for name,digest in root['source_sha256'].items():
        if checksum(ROOT/name)!=digest:
            raise ValueError('local evaluator differs from frozen GPU source')
    with (private/'local-quality.log').open('x') as log,redirect_stdout(log),redirect_stderr(log):
        dataset=json.loads(Path(root['dataset_path']).read_text())
        campaigns=[json.loads((private/f'cap-{cap}'/'manifest.json').read_text()) for cap in CAPS]
        quality(private,dataset,campaigns,public)
        analyze(private,public/'result.json')
        event(public,'scientific-evidence-validation-complete')
    print(json.dumps(dict(local_quality_complete=True,public_report=str(public/'result.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','verify','run','finalize','audit'])
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--public',type=Path)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare': prepare(args.private,args.public)
    elif args.mode=='verify': publish(args.out,verify_prepared(args.private,args.public))
    elif args.mode=='run': raise SystemExit(run(args.private,args.dataset,args.public))
    elif args.mode=='finalize': finalize(args.private,args.public)
    else:
        if os.environ.get('CUDA_VISIBLE_DEVICES')!='':
            raise ValueError('offline replay must explicitly disable CUDA')
        result=analyze(args.private,args.out)
        print(json.dumps(dict(replay_complete=True,primary_endpoints=result['primary_endpoints'])))
