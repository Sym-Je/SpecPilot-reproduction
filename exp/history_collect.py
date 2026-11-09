"""One-arm stock observation collection, never a paired performance benchmark."""

import argparse
from collections import Counter,defaultdict
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from controller.dev_campaign import validate_packet
from controller.http_transport import sha_ids
from controller.scored_forcing import read_reference
from exp.candidate_smoke import CapturedArm,source_hashes
from exp.diagnosis import digest,publish
from exp.p3_pair_run import append_json,check_ports,clean_environment,gpu_lock,interrupted,load_requests,result_row,wait_for_idle,write_json,SETTING
from exp.step_replay import ObservationServer,event,rows
from harness.candidate import expected_arguments,make_spec
from harness.exploration_observations import history_screen
from harness.step_replay import read_stream,replay_bound,replay_request
from harness.stock_step_build import check_bundle

SUITES=('gsm8k','humaneval')
SELECTION_SEED='history-confirmation-v1'


def select_requests(pool,excluded):
    if any(sha_ids(row['input_ids'])!=row['input_sha256'] for row in pool):
        raise ValueError('source pool input hash changed')
    excluded_ids={row['id'] for row in excluded}
    excluded_inputs={row['input_sha256'] for row in excluded}
    excluded_sources={row['source_sha256'] for row in pool
        if row['id'] in excluded_ids or row['input_sha256'] in excluded_inputs}
    seen_inputs,seen_sources=set(),set()
    candidates=[]
    for row in sorted(pool,key=lambda value:value['id']):
        if (row['suite'] not in SUITES or row['id'] in excluded_ids or row['input_sha256'] in excluded_inputs or
                row['source_sha256'] in excluded_sources or row['input_sha256'] in seen_inputs or row['source_sha256'] in seen_sources):
            continue
        seen_inputs.add(row['input_sha256'])
        seen_sources.add(row['source_sha256'])
        candidates.append(row)
    selected=[]
    for suite in SUITES:
        eligible=sorted((row for row in candidates if row['suite']==suite),key=lambda row:(
            hashlib.sha256(f'{SELECTION_SEED}|{suite}|{row["input_sha256"]}'.encode()).hexdigest(),row['id']))
        if len(eligible)<2:
            raise ValueError('not enough independent new requests')
        selected.extend(eligible[:2])
    if len({row['id'] for row in selected})!=4:
        raise ValueError('request identity collision')
    return selected


def screen(observations):
    if len(observations['requests'])!=4 or Counter(row['suite'] for row in observations['requests'])!=Counter(dict.fromkeys(SUITES,2)):
        raise ValueError('confirmation requires four new requests, two per suite')
    result=history_screen(observations)
    result['limitations']=['four newly selected dev requests support screening only, not population generalization',
        'prediction MAE does not establish budget decisions, counterfactual generation or net speedup']
    result['fixed_rule_screen_passed']=all(row['mae']['previous_one']<value
        for row in result['per_request'] for name,value in row['mae'].items() if name!='previous_one')
    return result


def check_sources(manifest):
    if manifest['schema']!='history-collection-v1' or manifest['source_sha256']!=source_hashes():
        raise ValueError('collection source/protocol drift')
    archive=manifest['source_archive']
    if digest(archive['path'])!=archive['sha256']:
        raise ValueError('frozen archive changed')
    with tarfile.open(archive['path']) as snapshot:
        for name,checksum in manifest['source_sha256'].items():
            if hashlib.sha256(snapshot.extractfile(name).read()).hexdigest()!=checksum:
                raise ValueError('execution differs from archived code')
    for path,checksum in manifest['inputs'].items():
        if digest(path)!=checksum:
            raise ValueError('frozen input or model configuration changed')
    build=check_bundle(manifest['bundle'])
    if digest(Path(manifest['bundle'])/'build.json')!=manifest['build_sha256']:
        raise ValueError('observer bundle identity changed')
    if (manifest['selection_seed']!=SELECTION_SEED or manifest['max_new_tokens']!=2048 or manifest['rounds']!=2 or
            manifest['arm']['block']!=8 or manifest['arm']['env'] or not manifest['arm']['enabled'] or
            manifest['arm']['tree_sha']!=build['observer_tree_sha']):
        raise ValueError('observation protocol changed')
    if select_requests(manifest['pool'],manifest['excluded'])!=manifest['requests']:
        raise ValueError('independent selection changed')
    return build


def prepare(directory,public,bundle,original,archive):
    from transformers import AutoTokenizer
    os.umask(0o077)
    directory.mkdir(parents=True,exist_ok=False)
    original_manifest=json.loads((original/'manifest.json').read_text())
    old=original_manifest['stock_spec']
    pin=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','diff','--exit-code',pin,'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
    build=check_bundle(bundle)
    spec=make_spec(build['stock'],ROOT/f'assets/upstream/configs/{SETTING}/config.json',old['target'],old['draft'],pin)
    tokenizer=AutoTokenizer.from_pretrained(spec['target'],local_files_only=True)
    pool=load_requests(20,SUITES,tokenizer)
    sources={}
    inputs={str(original/'manifest.json'):digest(original/'manifest.json')}
    for suite in SUITES:
        path=ROOT/f'assets/upstream/dev/{suite}.jsonl'
        inputs[str(path)]=digest(path)
        for item in rows(path):
            sources[item['id']]=hashlib.sha256(' '.join(item['turns'][0].split()).encode()).hexdigest()
    for request in pool:request['source_sha256']=sources[request['id']]
    for model in (spec['target'],spec['draft']):
        for name in ('config.json','tokenizer_config.json','tokenizer.json'):
            path=Path(model)/name
            if path.is_file():inputs[str(path)]=digest(path)
    selected=select_requests(pool,original_manifest['requests'])
    arm=dict(name='observer',block=8,tree_sha=build['observer_tree_sha'],engine=str(bundle/'engine'),
        env={},launch_arm='stock',bundle=str(bundle),enabled=True)
    manifest=dict(schema='history-collection-v1',source_pin=pin,source_sha256=source_hashes(),
        source_archive=dict(path=str(archive),sha256=digest(archive)),inputs=inputs,bundle=str(bundle),
        build_sha256=digest(bundle/'build.json'),stock_spec=spec,arm=arm,port=30240,
        pool=pool,excluded=original_manifest['requests'],requests=selected,selection_seed=SELECTION_SEED,
        max_new_tokens=2048,rounds=2)
    check_sources(manifest)
    write_json(directory/'manifest.json',manifest)
    publish(public/'selection.json',dict(independent_requests=4,old_diagnostic_excluded=True,
        requests=[dict(request_group=f'new-{index+1}',suite=row['suite'],input_tokens=len(row['input_ids']))
            for index,row in enumerate(selected)],manifest_sha256=digest(directory/'manifest.json')))


def audit(directory):
    if digest(directory/'manifest.json')!=os.environ['HISTORY_MANIFEST_SHA256']:
        raise ValueError('selection differs from the pre-submit manifest identity')
    manifest=json.loads((directory/'manifest.json').read_text())
    build=check_sources(manifest)
    runtime=json.loads((directory/'runtime.json').read_text())
    gpu=runtime['gpu']
    observations=dict(schema='count-order-observations-v1',independent_requests=4,requests=[],
        provenance=dict(original_manifest_sha256=digest(directory/'manifest.json'),source_pin=manifest['source_pin']),
        privacy='anonymous acceptance counts only; no prompts, output IDs or text')
    collected=defaultdict(list)
    outputs=defaultdict(list)
    fingerprints=[]
    faults=0
    spec=dict(manifest['stock_spec'],stock_tree_sha=manifest['arm']['tree_sha'])
    for number in (1,2):
        root=directory/f'round-{number:02d}'
        assignment=dict(arm=manifest['arm'],gpu=gpu,port=manifest['port'])
        if json.loads((root/'deployment.json').read_text())!=dict(round=number,assignment=assignment):
            raise ValueError('single-arm deployment changed')
        process=json.loads((root/'observer.process.json').read_text())
        fingerprints.append((process['pid'],process['start_ticks']))
        if json.loads((root/'observer.stopped.json').read_text())!=dict(stopped=True):
            raise ValueError('observer process not stopped')
        if json.loads((root/'complete.json').read_text())!=dict(round=number,requests=4):
            raise ValueError('incomplete observation round')
        samples=rows(root/'samples.jsonl')
        warmup=rows(root/'warmup.jsonl')
        if [row['id'] for row in samples]!=[row['id'] for row in manifest['requests']]:
            raise ValueError('measured request coverage changed')
        expected=manifest['requests'][:1]+manifest['requests']
        if [row['id'] for row in warmup]!=[row['id'] for row in expected]:
            raise ValueError('warmup coverage changed')
        for index,(sample,request) in enumerate(zip(warmup,expected)):
            validate_packet(sample,request,assignment,32 if index==0 else 2048,directory,expected_arguments(spec,8))
            if read_reference(sample['raw_evidence'],directory)['request']['rid']!=f'history-{number}|warmup.jsonl|{index}|measure':
                raise ValueError('warmup request binding changed')
        grouped=defaultdict(list)
        references=json.loads((root/'streams.json').read_text())
        if not references:raise ValueError('no real observation stream')
        for reference in references:
            for record in read_stream(reference,directory):
                if (record.get('runtime_path')!=str(Path(manifest['bundle'])/'engine/python/sglang/srt/speculative/specpilot_step_observer.py') or
                        record.get('runtime_sha256')!=build['runtime_sha256'] or record.get('tree_sha')!=build['observer_tree_sha']):
                    raise ValueError('unbound observer runtime')
                grouped[record['rid']].append(record)
        for index,(sample,request) in enumerate(zip(samples,manifest['requests'])):
            validate_packet(sample,request,assignment,2048,directory,expected_arguments(spec,8))
            packet=read_reference(sample['raw_evidence'],directory)
            if packet['request']['rid']!=f'history-{number}|samples.jsonl|{index}|measure':
                raise ValueError('measured data was substituted with warmup or another request')
            events=grouped[packet['request']['rid']]
            report=replay_bound(events,sample['raw_evidence'],root=directory)
            counts=[]
            previous=0
            for record in events:
                if record['kind']=='commit':
                    if record['phase']=='decode':counts.append(record['correct_drafts']-previous)
                    previous=record['correct_drafts']
            if len(counts)!=report['committed_verify_steps']:
                raise ValueError('committed count sequence incomplete')
            collected[index].append(dict(round=number,accepted_counts=counts))
            outputs[index].append(sample['output_sha256'])
            for fault in ('accepted','bonus','missing','output'):
                altered=copy.deepcopy(events)
                first=next(position for position,row in enumerate(altered) if row['kind']=='verify')
                output=list(sample['output_ids'])
                if fault in ('accepted','bonus'):altered[first][fault]+=1
                elif fault=='missing':del altered[first]
                else:output[0]+=1
                try:replay_request(altered,expected_output=output)
                except ValueError:faults+=1
                else:raise ValueError('real-chain fault escaped reconstruction')
    if len(set(fingerprints))!=2 or any(len(set(values))!=1 for values in outputs.values()):
        raise ValueError('servers not fresh or output drift across repetitions')
    for index,request in enumerate(manifest['requests']):
        observations['requests'].append(dict(request_group=f'new-{index+1}',suite=request['suite'],rounds=collected[index]))
    prediction=screen(observations)
    cleanup=json.loads((directory/'cleanup.json').read_text())
    if len(cleanup)!=1 or cleanup[0]['uuid']!=gpu['uuid'] or cleanup[0]['memory_used_mib']!=0 or cleanup[0]['utilization']>10:
        raise ValueError('single GPU cleanup failed')
    result=dict(schema='history-confirmation-result-v1',source_pin=manifest['source_pin'],independent_requests=4,
        physical_repetitions=2,fresh_servers=2,real_chain_replays=8,replay_faults_rejected=faults,
        prediction=prediction,disposition='continue_evidence_only' if prediction['fixed_rule_screen_passed'] else 'stop_fixed_one_step_rule',
        end_to_end_gain=None,implementation_ready=False,promoted=False,ledger_eligible=False,
        scope='four new dev requests; instrumented one-arm collection, not paired timing or population generalization')
    return result,observations


def run(directory,public):
    if digest(directory/'manifest.json')!=os.environ['HISTORY_MANIFEST_SHA256']:
        raise ValueError('pre-submit selection identity changed')
    manifest=json.loads((directory/'manifest.json').read_text())
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=manifest['source_pin']:
        raise ValueError('checkout not at frozen execution pin')
    check_sources(manifest)
    environment=clean_environment()
    environment.update(SP_TARGET=manifest['stock_spec']['target'],SP_DRAFT=manifest['stock_spec']['draft'])
    signal.signal(signal.SIGTERM,interrupted)
    gpu=wait_for_idle([0])[0]
    write_json(directory/'runtime.json',dict(gpu=gpu,started_unix=time.time()))
    spec=dict(manifest['stock_spec'],stock_tree_sha=manifest['arm']['tree_sha'])
    with gpu_lock(gpu):
        for number in (1,2):
            root=directory/f'round-{number:02d}'
            root.mkdir()
            check_ports([manifest['port']])
            write_json(root/'deployment.json',dict(round=number,assignment=dict(arm=manifest['arm'],gpu=gpu,port=manifest['port'])))
            server=ObservationServer(manifest['arm'],gpu,manifest['port'],root,environment)
            event(public,'round-start',round=number)
            try:
                server.start()
                server.wait_ready(900)
                client=CapturedArm('observer',f'http://127.0.0.1:{manifest["port"]}',directory=root,
                    spec=spec,block_size=8,tree_sha=manifest['arm']['tree_sha'],env={})
                client.begin_session()
                for filename,requests in (('warmup.jsonl',manifest['requests'][:1]+manifest['requests']),('samples.jsonl',manifest['requests'])):
                    with (root/filename).open('x') as destination:
                        for index,request in enumerate(requests):
                            cap=32 if filename=='warmup.jsonl' and index==0 else 2048
                            value=client.step(request['input_ids'],cap,rid=f'history-{number}|{filename}|{index}')
                            append_json(destination,result_row(value,request,manifest['arm'],gpu,number-1,cap))
                            event(public,'request-complete',round=number,phase=filename,index=index+1)
            finally:
                server.stop()
            wait_for_idle([0])
            references=[dict(path=str(path),sha256=digest(path)) for path in sorted((root/'observer-events').glob('*.jsonl'))]
            write_json(root/'streams.json',references)
            write_json(root/'complete.json',dict(round=number,requests=4))
            event(public,'round-complete',round=number)
        check_ports([manifest['port']])
        write_json(directory/'cleanup.json',wait_for_idle([0]))
    result,observations=audit(directory)
    write_json(directory/'result.json',result)
    publish(public/'observations.json',observations)
    publish(public/'result.json',result)
    event(public,'gpu-work-complete',disposition=result['disposition'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','run','audit'))
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--public',type=Path)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--original',type=Path)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.command=='prepare':
        prepare(args.directory.absolute(),args.public.absolute(),args.bundle.absolute(),args.original.absolute(),args.archive.absolute())
    elif args.command=='run':run(args.directory.absolute(),args.public.absolute())
    else:
        result,_=audit(args.directory.absolute())
        publish(args.out,result)
        print('PASS: independent stock count chains and fixed-rule screening audited; no performance verdict')
