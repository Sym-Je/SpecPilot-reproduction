"""Profile-only transport repair and auxiliary audits; never rerun formal timing."""

import argparse
import base64
from collections import defaultdict
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from controller.scoring import NativeClient
from exp import diagnosis
from exp.generalization_run import build,event
from exp.p3_pair_run import check_ports,clean_environment,gpu_lock,interrupted,wait_for_idle,write_json
from harness.baseline_validation import read_rows


def annotated_body(body,schema):
    output=dict(body)
    fields=schema.get('components',{}).get('schemas',{}).get('ProfileReq',{}).get('properties',{})
    if 'detailed_annotations' in fields:
        output['detailed_annotations']=True
    return output


class ProfileClient(NativeClient):
    def request(self,path,body=None):
        result=super().request(path,body)
        if path=='/openapi.json': self.public_schema=result
        return result

    def post(self,path,body):
        if path not in ('/start_profile','/stop_profile'):
            return super().post(path,body)
        self.sequence+=1
        if path=='/start_profile': body=annotated_body(body,getattr(self,'public_schema',{}))
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),
                                       headers={'Content-Type':'application/json'})
        started=time.time()
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response:
                payload,status,content_type=response.read(),response.status,response.headers.get('Content-Type','')
        except urllib.error.HTTPError as error:
            payload,status,content_type=error.read(),error.code,error.headers.get('Content-Type','')
        try:
            decoded=json.loads(payload)
        except (ValueError,UnicodeDecodeError):
            decoded=dict(text=payload.decode(errors='replace'))
        record=dict(url=self.url+path,request=body,response=decoded,http_status=status,content_type=content_type,
            response_bytes_base64=base64.b64encode(payload).decode(),response_bytes_sha256=hashlib.sha256(payload).hexdigest(),
            started_unix=started,finished_unix=time.time())
        destination=self.raw_dir/f'{self.sequence:06d}.json'
        with destination.open('x') as output: json.dump(record,output,allow_nan=False)
        self.last_evidence=dict(path=str(destination),sha256=diagnosis.digest(destination))
        if status!=200:
            raise RuntimeError(f'profile HTTP {status}; raw evidence: {destination}')
        if 'html' in content_type.lower():
            raise ValueError('unexpected HTML profile response')
        return decoded


def eos_summary(tokens,eos_ids):
    first=next((index for index,token in enumerate(tokens) if token in eos_ids),None)
    return dict(tokens=len(tokens),first_eos_index=first,post_eos_tokens=0 if first is None else len(tokens)-first-1)


def run(private,data_path,public,formal):
    os.umask(0o077)
    private.mkdir(mode=0o700)
    event(public,'profile-repair-execution-start')
    with (private/'runner.log').open('x') as log,redirect_stdout(log),redirect_stderr(log):
        environment=clean_environment()
        signal.signal(signal.SIGTERM,interrupted)
        try:
            with ExitStack() as resources:
                gpus=wait_for_idle([0,1])
                for gpu in gpus: resources.enter_context(gpu_lock(gpu))
                root=build(private,data_path,public,environment,gpus)
                original=json.loads((formal/'manifest.json').read_text())
                if root['dataset_sha256']!=original['dataset_sha256']:
                    raise ValueError('profile-only repair changed formal inputs')
                root.update(diagnostic_protocol='profile-transport-repair-v1',formal_directory=str(formal),
                    formal_manifest_sha256=diagnosis.digest(formal/'manifest.json'),formal_source_pin=original['source_pin'])
                write_json(private/'manifest.json',root)
                dataset=json.loads(data_path.read_text())
                diagnosis.validate_dataset(dataset)
                write_json(private/'profile-start.json',dict(started_unix=time.time()))
                with patch.object(diagnosis,'NativeClient',ProfileClient):
                    diagnosis.profiles(private,root,dataset,environment,public)
                check_ports(root['ports'])
                write_json(private/'cleanup.json',wait_for_idle([0,1]))
                subprocess.run(['git','diff','--exit-code',root['source_pin'],'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
                diagnosis.publish(public/'gpu-complete.json',dict(gpu_work_complete=True,formal_timing_rerun=False,
                    scientific_acceptance_complete=False,source_pin=root['source_pin']))
                event(public,'profile-repair-gpu-complete-independent-replay-pending')
        except BaseException as error:
            traceback.print_exc()
            write_json(private/'failed.json',dict(error=repr(error),time_unix=time.time()))
            event(public,'profile-repair-execution-failed',error_type=type(error).__name__)
            try: write_json(private/'failure-cleanup.json',wait_for_idle([0,1]))
            except Exception as cleanup: write_json(private/'failure-cleanup-error.json',dict(error=repr(cleanup)))
            return 1
    return 0


def analyze(private,out):
    root=json.loads((private/'manifest.json').read_text())
    if root['diagnostic_protocol']!='profile-transport-repair-v1' or diagnosis.digest(root['dataset_path'])!=root['dataset_sha256']:
        raise ValueError('changed profile-only protocol or dataset')
    formal=Path(root['formal_directory'])
    if diagnosis.digest(formal/'manifest.json')!=root['formal_manifest_sha256']:
        raise ValueError('profile repair detached from original formal measurement')
    if diagnosis.digest(root['source_archive'])!=root['source_archive_sha256']:
        raise ValueError('profile-only source archive changed')
    with tarfile.open(root['source_archive']) as archive:
        for name,checksum in root['source_sha256'].items():
            if diagnosis.digest(ROOT/name)!=checksum or hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=checksum:
                raise ValueError('profile-only evaluator differs from frozen source')
    for folder in sorted((private/'profiles').glob('round-*/*-api')):
        for path in sorted(folder.glob('*.json')):
            record=json.loads(path.read_text())
            if record['url'].endswith(('/start_profile','/stop_profile')):
                payload=base64.b64decode(record['response_bytes_base64'],validate=True)
                if hashlib.sha256(payload).hexdigest()!=record['response_bytes_sha256']:
                    raise ValueError('profile raw response bytes changed')
                if record['url'].endswith('/start_profile') and record['request'].get('detailed_annotations') is not True:
                    raise ValueError('declared detailed annotations missing')
    cleanup=json.loads((private/'cleanup.json').read_text())
    if len(cleanup)!=2 or any(gpu['memory_used_mib']>256 or gpu['utilization']>10 for gpu in cleanup):
        raise ValueError('profile GPU cleanup not established')
    dataset=json.loads(Path(root['dataset_path']).read_text())
    report=diagnosis.profile_report(private,root,dataset)
    result=dict(execution_complete=True,profile_only=True,formal_timing_rerun=False,source_pin=root['source_pin'],
        formal_source_pin=root['formal_source_pin'],formal_manifest_sha256=root['formal_manifest_sha256'],
        dataset_sha256=root['dataset_sha256'],profiling=report,promoted=False,ledger_eligible=False)
    diagnosis.publish(out,result)
    return result


def auxiliary(formal,out):
    from transformers import AutoTokenizer
    root=json.loads((formal/'manifest.json').read_text())
    dataset=json.loads(Path(root['dataset_path']).read_text())
    if diagnosis.digest(root['dataset_path'])!=root['dataset_sha256']:
        raise ValueError('formal dataset changed before auxiliary audit')
    tokenizer=AutoTokenizer.from_pretrained(root['model_path'],local_files_only=True)
    eos_ids=set()
    value=tokenizer.eos_token_id
    eos_ids.update(value if isinstance(value,list) else [value])
    generation=Path(root['model_path'])/'generation_config.json'
    if generation.exists():
        value=json.loads(generation.read_text()).get('eos_token_id',[])
        eos_ids.update(value if isinstance(value,list) else [value])
    eos_ids.discard(None)
    if not eos_ids: raise ValueError('no public EOS identity')
    indexed={row['id']:row for row in dataset['requests']}
    records={}
    summaries=defaultdict(list)
    for budget in (64,256,1024):
        for number in (1,2):
            for role in ('stock','final'):
                for row in read_rows(formal/f'fixed-{budget}'/'candidate'/f'round-{number:02d}'/(role+'.jsonl')):
                    request=indexed[row['id']]
                    records[budget,number,role,row['id']]=row['output_ids']
                    summaries[budget,role,request['language'],request['input_target']].append(eos_summary(row['output_ids'],eos_ids))
    aggregate=[]
    for (budget,role,language,target),values in sorted(summaries.items()):
        tokens=sum(value['tokens'] for value in values)
        aggregate.append(dict(budget=budget,arm=role,language=language,input_target=target,round_outputs=len(values),
            eos_encountered=sum(value['first_eos_index'] is not None for value in values),
            post_eos_tokens=sum(value['post_eos_tokens'] for value in values),total_tokens=tokens,
            post_eos_fraction=sum(value['post_eos_tokens'] for value in values)/tokens))
    prefix=[]
    for role in ('stock','final'):
        for budget in (256,1024):
            comparisons=[records[64,number,role,request['id']]==records[budget,number,role,request['id']][:64]
                for number in (1,2) for request in dataset['requests'] if request['answer_style']=='short']
            prefix.append(dict(arm=role,comparison=f'64-vs-{budget}',round_outputs=len(comparisons),equal_first_64=sum(comparisons)))
    result=dict(formal_source_pin=root['source_pin'],formal_manifest_sha256=diagnosis.digest(formal/'manifest.json'),
        auxiliary_source_sha256=diagnosis.digest(Path(__file__)),dataset_sha256=root['dataset_sha256'],
        eos_token_ids=sorted(eos_ids),eos_continuation=aggregate,prefix_stability=prefix,
        scope='auxiliary only; no primary endpoint replacement or mathematical lossless claim')
    diagnosis.publish(out,result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['run','audit','auxiliary'])
    parser.add_argument('--private',type=Path)
    parser.add_argument('--formal',type=Path)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--public',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.mode=='run': raise SystemExit(run(args.private,args.dataset,args.public,args.formal))
    else:
        if os.environ.get('CUDA_VISIBLE_DEVICES')!='': raise ValueError('CPU audit must explicitly disable CUDA')
        if args.mode=='auxiliary': auxiliary(args.formal,args.out)
        else:
            result=analyze(args.private,args.out)
            print(json.dumps(dict(profile_replay_complete=True,captured=result['profiling']['captured'])))
