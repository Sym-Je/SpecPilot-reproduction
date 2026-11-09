"""Stock observer on/off diagnostics; no profiler, speedup or promotion claims."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from controller.dev_campaign import validate_packet
from controller.scored_forcing import read_reference
from costmodel.observations import counter_observation
from exp.candidate_smoke import CandidateServer,CapturedArm,source_hashes
from exp.diagnosis import digest,publish
from exp.p3_pair_run import Server,clean_environment,gpu_lock,interrupted,run_round,wait_for_idle,write_json,check_ports
from harness.candidate import expected_arguments
from harness.step_replay import read_stream,replay_bound,replay_request
from harness.stock_step_build import STOCK_SHA,check_bundle


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def sources():
    result=source_hashes()
    names=subprocess.check_output(['git','ls-files','--','costmodel'],cwd=ROOT,text=True).splitlines()
    result.update({name:digest(ROOT/name) for name in names if name.endswith('.py')})
    return dict(sorted(result.items()))


def select_requests(original):
    manifest=json.loads((original/'manifest.json').read_text())
    verdicts={}
    for number in (1,2):
        for pair in rows(original/'timing'/f'round-{number:02d}'/'pairs.jsonl'):
            for key in ('a','b'):
                sample=pair[key]
                metadata=read_reference(sample['raw_evidence'],original)['response']['meta_info']
                verdicts.setdefault(sample['id'],set()).add(counter_observation(metadata)['algebra_consistent'])
    anomalous=[request for request in manifest['requests'] if verdicts.get(request['id'])=={False}]
    if len(anomalous)!=1 or any(len(value)!=1 for value in verdicts.values()):
        raise ValueError('expected one reproducible counter anomaly in the frozen diagnostic')
    same=[request for request in manifest['requests'] if request['suite']==anomalous[0]['suite']
          and verdicts.get(request['id'])=={True}]
    other=[request for request in manifest['requests'] if request['suite']!=anomalous[0]['suite']
           and verdicts.get(request['id'])=={True}]
    if not same or not other:
        raise ValueError('missing fixed same-suite and cross-suite normal controls')
    return [other[0],anomalous[0],same[0]],manifest


class ObservationServer(CandidateServer):
    def launch_spec(self):
        command,environment=Server.launch_spec(self)
        environment.pop('SPECPILOT_STEP_TRACE_DIR',None)
        if self.arm['name']=='observer':
            check_bundle(self.arm['bundle'])
            if self.arm['enabled']:
                directory=self.output_dir/'observer-events'
                directory.mkdir(mode=0o700)
                environment['SPECPILOT_STEP_TRACE_DIR']=str(directory)
        return command,environment


def event(public,phase,**values):
    path=public/'events.jsonl'
    with path.open('a') as output:
        import time
        output.write(json.dumps(dict(time_unix=time.time(),phase=phase,**values))+'\n')
    path.chmod(0o644)


def audit(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest['schema']!='stock-step-campaign-v1' or manifest['source_sha256']!=sources():
        raise ValueError('step diagnostic source/protocol drift')
    archive=manifest['source_archive']
    if digest(archive['path'])!=archive['sha256']:
        raise ValueError('step diagnostic archive changed')
    with tarfile.open(archive['path']) as snapshot:
        for name,checksum in manifest['source_sha256'].items():
            if hashlib.sha256(snapshot.extractfile(name).read()).hexdigest()!=checksum:
                raise ValueError('step diagnostic execution differs from frozen source')
    original=Path(manifest['original']['directory'])
    if digest(original/'manifest.json')!=manifest['original']['manifest_sha256']:
        raise ValueError('original request manifest changed')
    selected,original_manifest=select_requests(original)
    if selected!=manifest['requests'] or original_manifest['stock_spec']!=manifest['stock_spec']:
        raise ValueError('diagnostic selection or stock protocol changed')
    bundle=Path(manifest['bundle'])
    build=check_bundle(bundle)
    if digest(bundle/'build.json')!=manifest['build_sha256']:
        raise ValueError('observer build identity changed')
    for path,checksum in manifest['model_configs'].items():
        if digest(path)!=checksum:
            raise ValueError('model configuration changed')
    fingerprints=[]
    reports=[]
    faults=0
    for mode in ('disabled','enabled'):
        arms=manifest['arms'][mode]
        if (len(arms)!=2 or [arm['name'] for arm in arms]!=['stock','observer'] or
                arms[0]['tree_sha']!=STOCK_SHA or arms[1]['tree_sha']!=build['observer_tree_sha'] or
                any(arm['block']!=8 or arm['launch_arm']!='stock' or arm['env'] for arm in arms) or
                arms[1]['enabled']!=(mode=='enabled')):
            raise ValueError('observer on/off deployment changed')
        for number in (0,1):
            root=directory/mode/f'round-{number+1:02d}'
            assigned=manifest['gpus'] if number==0 else list(reversed(manifest['gpus']))
            assignments=[dict(arm=arm,gpu=gpu,port=port) for arm,gpu,port in zip(arms,assigned,manifest['ports'])]
            if json.loads((root/'deployment.json').read_text())!=dict(round=number+1,assignments=assignments):
                raise ValueError('observer physical GPU assignment changed')
            if json.loads((root/'complete.json').read_text())!=dict(round=number+1,pairs=3):
                raise ValueError('incomplete observer round')
            pairs=rows(root/'pairs.jsonl')
            if [pair['id'] for pair in pairs]!=[request['id'] for request in selected]:
                raise ValueError('observer request coverage changed')
            warm=rows(root/'warmup.jsonl')
            if [row['phase'] for row in warm]!=['short']+['full']*3 or [row['id'] for row in warm]!=[request['id'] for request in selected[:1]+selected]:
                raise ValueError('observer warmup coverage changed')
            timing={row['event']:row['time_unix'] for row in rows(root/'events.jsonl')}
            if not timing['servers_ready']<=timing['warmup_complete']<=pairs[0]['started_unix']:
                raise ValueError('observer generation escaped warmup order')
            for key,assignment in zip(('a','b'),assignments):
                name=assignment['arm']['name']
                fingerprints.append(tuple(json.loads((root/f'{name}.process.json').read_text())[field] for field in ('pid','start_ticks')))
                if json.loads((root/f'{name}.stopped.json').read_text())!=dict(stopped=True):
                    raise ValueError('observer server not stopped')
                if rows(root/f'{name}.jsonl')!=[pair[key] for pair in pairs]:
                    raise ValueError('arm data differs from canonical paired records')
                for record,request,cap in ([(record,request,2048) for record,request in zip(pairs,selected)]+
                        [(record,request,32 if index==0 else 2048) for index,(record,request) in enumerate(zip(warm,selected[:1]+selected))]):
                    validate_packet(record[key],request,assignment,cap,directory,expected_arguments(manifest['stock_spec'],8))
            for pair in pairs:
                if pair['a']['output_ids']!=pair['b']['output_ids']:
                    raise ValueError('observer/default-off changed the tested stock output')
            references=json.loads((root/'streams.json').read_text())
            if mode=='disabled':
                if references or (root/'observer-events').exists():
                    raise ValueError('disabled observer emitted step data')
                continue
            grouped=defaultdict(list)
            for reference in references:
                stream=read_stream(reference,directory)
                for record in stream:
                    if (record.get('runtime_path')!=str(bundle/'engine/python/sglang/srt/speculative/specpilot_step_observer.py') or
                            record.get('runtime_sha256')!=build['runtime_sha256'] or record.get('tree_sha')!=build['observer_tree_sha']):
                        raise ValueError('runtime observer did not come from the declared bundle')
                    grouped[record['rid']].append(record)
            for pair,request in zip(pairs,selected):
                generation=pair['b']['raw_evidence']
                rid=read_reference(generation,directory)['request']['rid']
                events=grouped.get(rid,[])
                report=replay_bound(events,generation,root=directory)
                for fault in ('accepted','bonus','missing','output'):
                    import copy
                    altered=copy.deepcopy(events)
                    first_verify=next(index for index,row in enumerate(altered) if row['kind']=='verify')
                    expected=list(pair['b']['output_ids'])
                    if fault in ('accepted','bonus'):
                        altered[first_verify][fault]+=1
                    elif fault=='missing':
                        del altered[first_verify]
                    else:
                        expected[0]+=1
                    try:
                        replay_request(altered,expected_output=expected)
                    except ValueError:
                        faults+=1
                    else:
                        raise ValueError('real observed path fault escaped local replay self-check')
                reports.append(dict(suite=request['suite'],role='anomaly' if request==selected[1] else 'normal',round=number+1,**report))
    if len(set(fingerprints))!=8:
        raise ValueError('observer rounds did not use eight fresh server processes')
    cleanup=json.loads((directory/'cleanup.json').read_text())
    if ({row['uuid'] for row in cleanup}!={row['uuid'] for row in manifest['gpus']} or
            any(row['memory_used_mib']!=0 or row['utilization']>10 for row in cleanup)):
        raise ValueError('observer GPU cleanup failed')
    return dict(schema=manifest['schema'],source_pin=manifest['source_pin'],independent_requests=3,
        paired_generations=12,arm_rows=24,default_off_matches_stock=True,enabled_matches_stock=True,
        real_request_replays=len(reports),replay_faults_rejected=faults,replays=reports,
        tau_best_available=False,profile_label_alignment_verified=False,unprofiled_step_timing_available=False,
        promoted=False,ledger_eligible=False,
        scope='instrumented stock linear chains and finite on/off output regression; no performance or losslessness verdict')


def run(directory,public,bundle,original):
    expected=os.environ['STEP_REPLAY_EXPECTED_COMMIT']
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=expected:
        raise ValueError('checkout is not frozen')
    subprocess.run(['git','diff','--exit-code',expected,'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    signal.signal(signal.SIGTERM,interrupted)
    selected,original_manifest=select_requests(original)
    build=check_bundle(bundle)
    environment=clean_environment()
    archive=Path(os.environ['STEP_REPLAY_SOURCE_TAR'])
    if digest(archive)!=os.environ['STEP_REPLAY_SOURCE_SHA256']:
        raise ValueError('declared execution archive differs')
    arms={}
    for mode in ('disabled','enabled'):
        baseline=dict(original_manifest['arms'][0],name='stock',launch_arm='stock')
        observer=dict(baseline,name='observer',engine=str(bundle/'engine'),tree_sha=build['observer_tree_sha'],
                      bundle=str(bundle),enabled=mode=='enabled')
        arms[mode]=[baseline,observer]
    with ExitStack() as resources:
        gpus=wait_for_idle([0,1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        manifest=dict(schema='stock-step-campaign-v1',source_pin=expected,source_sha256=sources(),
            source_archive=dict(path=str(archive),sha256=digest(archive)),bundle=str(bundle),build_sha256=digest(bundle/'build.json'),
            original=dict(directory=str(original),manifest_sha256=digest(original/'manifest.json')),requests=selected,
            stock_spec=original_manifest['stock_spec'],model_configs=original_manifest['model_configs'],arms=arms,gpus=gpus,ports=[30200,30210])
        write_json(directory/'manifest.json',manifest)
        for mode in ('disabled','enabled'):
            for number in (0,1):
                event(public,'round-start',mode=mode,round=number+1)
                root=directory/mode/f'round-{number+1:02d}'
                specs={arm['name']:dict(manifest['stock_spec'],stock_tree_sha=arm['tree_sha']) for arm in arms[mode]}
                def factory(name,url,**options):
                    return CapturedArm(name,url,directory=root,spec=specs[name],**options)
                check_ports(manifest['ports'])
                run_round(arms[mode],gpus,manifest['ports'],number,selected,root,environment,2048,1,1200,
                          server_factory=ObservationServer,arm_factory=factory,stable_null=True)
                wait_for_idle([0,1])
                references=[dict(path=str(path),sha256=digest(path)) for path in sorted((root/'observer-events').glob('*.jsonl'))]
                write_json(root/'streams.json',references)
                event(public,'round-complete',mode=mode,round=number+1,pairs=3,step_streams=len(references))
        check_ports(manifest['ports'])
        write_json(directory/'cleanup.json',wait_for_idle([0,1]))
        result=audit(directory)
        write_json(directory/'result.json',result)
        publish(public/'result.json',result)
        event(public,'gpu-work-complete',real_request_replays=result['real_request_replays'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    execute=commands.add_parser('run')
    for name in ('directory','public','bundle','original'):
        execute.add_argument('--'+name,type=Path,required=True)
    check=commands.add_parser('audit')
    check.add_argument('--directory',type=Path,required=True)
    check.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='run':
        run(args.directory.absolute(),args.public.absolute(),args.bundle.absolute(),args.original.absolute())
    else:
        publish(args.out,audit(args.directory.absolute()))
        print('PASS: stock step evidence replayed on CPU; no performance verdict')


if __name__=='__main__':
    main()
