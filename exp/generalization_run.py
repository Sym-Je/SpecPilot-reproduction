"""Execute the frozen external audit; print only aggregate public status."""

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from controller.paper_policy import measurement_protocol_id
from controller.scored_forcing import calibrate_delta, calibrate_stock, judge_scored_forcing
from controller.scoring import NativeClient
from exp.dev_campaign import CapturedArm
from exp.generalization_audit import PHASES, PROTOCOL, analyze, validate_session
from exp.generalization_data import DOMAINS
from exp.generalization_quality import grade, run_code
from exp.p3_pair_run import append_json, arm_specs, check_ports, clean_environment, gpu_lock, interrupted, run_round, wait_for_idle, write_json
from exp.p5_real_run import Campaign, head_process, launch


def event(public, phase, **fields):
    with (public/'events.jsonl').open('a') as destination:
        append_json(destination,dict(time_unix=time.time(),phase=phase,**fields))
    (public/'events.jsonl').chmod(0o644)


def build(private, data_path, public, environment, gpus):
    expected=os.environ['GENERALIZATION_EXPECTED_COMMIT']
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if actual != expected:
        raise ValueError('checkout is not the frozen source')
    subprocess.run(['git','diff','--exit-code',expected,'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
    preparation=json.loads((public/'preparation.json').read_text())
    checksum=hashlib.sha256(data_path.read_bytes()).hexdigest()
    if checksum != preparation['dataset_sha256']:
        raise ValueError('prepared blind dataset changed')
    snapshot=Path(os.environ['GENERALIZATION_SOURCE_TAR'])
    snapshot_sha=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if snapshot_sha != os.environ['GENERALIZATION_SOURCE_SHA256']:
        raise ValueError('source archive changed')
    files=subprocess.check_output(['git','ls-files','--','controller','exp','harness'],cwd=ROOT,text=True).splitlines()
    sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files if Path(name).suffix in ('.py','.sh')}
    candidate,config=arm_specs(['stock','final'],environment)
    nulls,_=arm_specs(['stock-a','stock-b'],environment)
    target=environment['SP_TARGET']
    return dict(directory=str(private),campaign_id=private.name,campaign_protocol_version=PROTOCOL,
        source_pin=expected,source_sha256=sources,source_archive=str(snapshot),source_archive_sha256=snapshot_sha,
        started_unix=time.time(),dataset_path=str(data_path),dataset_sha256=checksum,
        suites=DOMAINS,rounds=2,warmup=2,full_scale_warmup=True,synchronized_start=True,raw_capture=True,
        ports=[30100,30110],sampling=dict(temperature=0.,top_k=1,enable_thinking=True),
        model_path=target,declared_models=config['models'],gpus=gpus,candidate_arms=candidate,null_arms=nulls,
        launch_protocol=dict(model_path=target,dtype='bfloat16',mem_fraction_static=.90,
            attention_backend='fa3',disable_radix_cache=True,random_seed=0,chunked_prefill_size=8192,
            enable_fp32_lm_head=False,speculative_draft_model_path=environment['SP_DRAFT'],
            mamba_ssm_dtype='float32',kv_cache_dtype='auto'))


def timing(directory,campaign,environment,public):
    directory.mkdir()
    write_json(directory/'manifest.json',campaign)
    for phase in PHASES:
        session=directory/phase
        session.mkdir()
        write_json(session/'manifest.json',campaign)
        arms=campaign['candidate_arms'] if phase == 'candidate' else campaign['null_arms']
        for number in (0,1):
            event(public,'timing-start',cap=campaign['max_new_tokens'],session=phase,round=number+1)
            root=session/f'round-{number+1:02d}'
            def factory(name,url,**options):
                return CapturedArm(name,url,output_dir=root,**options)
            check_ports(campaign['ports'])
            run_round(arms,campaign['gpus'],campaign['ports'],number,campaign['requests'],root,environment,
                      campaign['max_new_tokens'],2,1200,stable_null=True,arm_factory=factory)
            wait_for_idle([0,1])
            event(public,'timing-round-complete',cap=campaign['max_new_tokens'],session=phase,round=number+1)
        checked,_=validate_session(session,campaign)
        write_json(session/'session-validation.json',checked)
        event(public,'timing-session-validated',cap=campaign['max_new_tokens'],session=phase)


def scoring(private,root,campaigns,environment,public):
    directory=private/'scoring-servers'
    directory.mkdir()
    gpus=wait_for_idle([0,1])
    specifications,_=arm_specs(['ar'],environment)
    arm=specifications[0]
    with ExitStack() as resources:
        launch(arm,'scorer',gpus[1],directory,environment,resources)
        scorer=NativeClient('http://127.0.0.1:30130',private/'scorer-raw')
        scorer.scorer_identity(arm['tree_sha'])
        head_process('preflight',private/'head-preflight',private/'cap-2048',arm['tree_sha'])
        event(public,'fp32-head-preflight-complete')
        for campaign in campaigns:
            cap=campaign['max_new_tokens']
            condition=private/f'cap-{cap}'
            correctness=condition/'correctness'
            correctness.mkdir()
            bench=Campaign(correctness,scorer,evidence_root=private)
            event(public,'ar-calibration-start',cap=cap,requests=len(campaign['requests']))
            ar_directory=correctness/'ar-server'
            ar_directory.mkdir()
            with ExitStack() as generation:
                launch(arm,'ar',gpus[0],ar_directory,environment,generation)
                client=NativeClient('http://127.0.0.1:30120',correctness/'ar-raw')
                identity=client.server_identity(arm['tree_sha'])
                ar_paths,_,_=bench.generate('ar',campaign['requests'],client,identity,cap)
            check_ports([30120])
            wait_for_idle([0])
            event(public,'ar-calibration-complete',cap=cap)
            for number in (1,2):
                traces={}
                for role in ('stock','final'):
                    rows=[json.loads(line) for line in (condition/'candidate'/f'round-{number:02d}'/(role+'.jsonl')).read_text().splitlines()]
                    paths=[]
                    for row,request in zip(rows,campaign['requests']):
                        if row['id'] != request['id']:
                            raise ValueError('timed request order changed')
                        paths.append(bench.save_trace(f'round-{number:02d}-{role}',request,row['output_ids'],row['generator'],[row['raw_evidence']]))
                    traces[role]=paths
                delta=calibrate_delta(traces['stock'],ar_paths,evidence_root=private)
                baseline=calibrate_stock(traces['stock'],delta,evidence_root=private)
                audits=bench.audit(f'round-{number:02d}-final',traces['final'],delta['delta'])
                verdict=judge_scored_forcing(baseline,traces['final'],evidence_root=private,prefill_audits=audits)
                write_json(correctness/f'round-{number:02d}-delta.json',delta)
                write_json(correctness/f'round-{number:02d}-stock.json',baseline)
                write_json(correctness/f'round-{number:02d}-verdict.json',verdict)
                event(public,'forcing-round-complete',cap=cap,round=number)
    check_ports([30120,30130])
    write_json(private/'scoring-cleanup.json',wait_for_idle([0,1]))


def quality(private,dataset,campaigns,public):
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True)
    indexed={item['id']:item for item in dataset['items']}
    controls={}
    for item in dataset['items']:
        if item['metric'] == 'code':
            code=item['canonical'] if not item.get('entry_point') else item['code_prompt']+item['canonical']
            controls[item['id']]=run_code(code,item['tests'])['status']=='pass'
    write_json(private/'quality-controls.json',controls)
    for campaign in campaigns:
        cap=campaign['max_new_tokens']
        with (private/f'cap-{cap}'/'quality.jsonl').open('x') as destination:
            for number in (1,2):
                for role in ('stock','final'):
                    path=private/f'cap-{cap}'/'candidate'/f'round-{number:02d}'/(role+'.jsonl')
                    for row in (json.loads(line) for line in path.read_text().splitlines()):
                        item=indexed[row['id']]
                        text=tokenizer.decode(row['output_ids'],skip_special_tokens=False)
                        result=grade(item,text) if controls.get(item['id'],True) else dict(score=None,metric='code-control-failed',answered=None)
                        append_json(destination,dict(id=row['id'],suite=row['suite'],round=number,role=role,
                            output_sha256=row['output_sha256'],quality=result))
        event(public,'task-quality-complete',cap=cap,code_controls_passed=sum(controls.values()),code_controls_total=len(controls))


def finish(private,dataset,campaigns,public,defer_quality=False):
    if defer_quality:
        write_json(public/'gpu-complete.json',dict(gpu_work_complete=True,scientific_acceptance_complete=False,
                   quality_location='local-cpu-sandbox',source_pin=os.environ.get('GENERALIZATION_EXPECTED_COMMIT')))
        (public/'gpu-complete.json').chmod(0o644)
        event(public,'gpu-work-complete-local-quality-pending')
        return
    quality(private,dataset,campaigns,public)
    event(public,'independent-evidence-validation-start')
    result=analyze(private,public/'result.json')
    event(public,'execution-complete',conditions=len(result['caps']))


def run(private,data_path,public,defer_quality=False):
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
                root['quality_location']='local-cpu-sandbox' if defer_quality else 'same-job-sandbox'
                write_json(private/'manifest.json',root)
                dataset=json.loads(data_path.read_text())
                campaigns=[]
                for cap in (2048,256,4096):
                    requests=dataset['requests'] if cap==2048 else [request for request in dataset['requests'] if request['id'] in dataset['panel_ids']]
                    campaign=dict(root,requests=requests,max_new_tokens=cap,per_suite=20 if cap==2048 else 4,
                                  condition_directory=str(private/f'cap-{cap}'))
                    campaign['protocol_id']=measurement_protocol_id(campaign)
                    timing(private/f'cap-{cap}',campaign,environment,public)
                    campaigns.append(campaign)
                write_json(private/'timing-cleanup.json',wait_for_idle([0,1]))
                write_json(private/'score-start.json',dict(started_unix=time.time()))
                scoring(private,root,campaigns,environment,public)
                check_ports([30100,30110,30120,30130])
                write_json(private/'cleanup.json',wait_for_idle([0,1]))
                subprocess.run(['git','diff','--exit-code',root['source_pin'],'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
                finish(private,dataset,campaigns,public,defer_quality)
        except BaseException as error:
            traceback.print_exc()
            write_json(private/'failed.json',dict(error=repr(error),time_unix=time.time()))
            event(public,'execution-failed',error_type=type(error).__name__)
            try:
                check_ports([30100,30110,30120,30130])
                write_json(private/'failure-cleanup.json',wait_for_idle([0,1]))
                event(public,'failure-cleanup-complete')
            except Exception as cleanup:
                write_json(private/'failure-cleanup-error.json',dict(error=repr(cleanup)))
            return 1
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--public',type=Path,required=True)
    parser.add_argument('--defer-quality',action='store_true')
    args=parser.parse_args()
    raise SystemExit(run(args.private.resolve(),args.dataset.resolve(),args.public.resolve(),args.defer_quality))
