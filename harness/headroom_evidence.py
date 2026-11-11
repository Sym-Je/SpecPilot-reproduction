"""Maintainer-authorized, public-stock priors; research roles receive no raw observations."""

import hashlib
import json
from pathlib import Path
import statistics

from harness.acceptance_headroom import finite_lattice_prior
from harness.diagnostic_archive import reference


ORIGINS={
    'lattice':('logs/ceiling-run-20261110-a01/sp-ceiling-20261110-a02/remote','exp.ceiling_run'),
    'mapping':('logs/ceiling-complete-run-20261110-b01/sp-ceiling-complete-20261110-b07/remote','exp.ceiling_mapping'),
    'timing':('logs/ceiling-complete-run-20261110-b01/sp-ceiling-complete-20261110-b06/remote','exp.ceiling_measure'),
}


def load(path):return json.loads(Path(path).read_text())


def compact_graph(graph):
    groups={}
    for trace in graph['traces']:
        for row in trace['groups']:
            identity=json.dumps({key:row[key] for key in ('kernel','operation','tensors')},sort_keys=True)
            if identity not in groups:
                groups[identity]=dict(kernel=row['kernel'],operation=row['operation'],tensors=row['tensors'],
                    count=0,work_us=0.,examples=[])
            target=groups[identity];target['count']+=row['count'];target['work_us']+=row['work_us']
            if len(target['examples'])<2:
                target['examples'].append(dict(trace_sha256=trace['source']['sha256'],event_index=row['first_event_index']))
    ordered=sorted(groups.values(),key=lambda row:-row['work_us'])
    return dict(capture_records=graph['capture_records'],captured_nodes=graph['captured_nodes'],
        request_traces=len(graph['traces']),kernel_count=sum(row['kernel_count'] for row in graph['traces']),
        matched_count=sum(row['mapped_kernel_count'] for row in graph['traces']),
        unmatched_count=sum(row['unmatched_kernel_count'] for row in graph['traces']),
        kernel_work_us=sum(row['kernel_work_us'] for row in graph['traces']),
        top_groups=ordered[:12],total_groups=len(ordered),groups_not_shown=max(0,len(ordered)-12),
        graph_mapping_assumption=graph['graph_mapping_assumption'],
        module_instance_fqn_known=False,consumer_dependency_graph_known=False,exposed_time_us=None,
        scope='Historical stock diagnostics; captured operation/module-type and tensor descriptors, not full module instance or critical path.',
        evidence_source='graph-context-full.json; maintainer audited, raw inputs not shared with research roles')


def matching_timing(repository,proof):
    timing=Path(repository)/ORIGINS['timing'][0];mapping=Path(repository)/ORIGINS['mapping'][0]
    samples=load(mapping/'stock/samples.json');rows=[]
    for number in (1,2):
        pairs=[json.loads(line) for line in (timing/f'round-{number:02d}/pairs.jsonl').read_text().splitlines()]
        if len(pairs)!=len(samples):raise ValueError('timing/profile request counts differ')
        for pair,sample in zip(pairs,samples):
            stock=pair['a'];profile=sample['row']
            if (pair['id']!=sample['id'] or stock['input_sha256']!=profile['input_sha256'] or
                    stock['output_ids']!=profile['output_ids'] or pair['b']['output_ids']!=profile['output_ids']):
                raise ValueError('historical timing/profile workload or output differs')
            rows.append(dict(id=pair['id'],round=number,output_tokens=stock['tokens'],
                input_sha256=stock['input_sha256'],output_sha256=hashlib.sha256(json.dumps(stock['output_ids'],separators=(',',':')).encode()).hexdigest(),
                unprofiled_stock_http_ms=stock['latency_ms'],profile_http_ms=profile['latency_ms']))
    clocks=proof['result']['clocks']
    expected={(row['id'],row['round']) for row in rows}
    actual={(row['id'],row['round']) for row in clocks}
    if len(clocks)!=len(rows) or len(actual)!=len(clocks) or actual!=expected:
        raise ValueError('historical clocks do not match the request/round timing cohort')
    decode=[];amortized=[];prefill=[]
    for row in clocks:
        decode.append(row['decode_step_ns']/1e6)
        amortized.append(row['request_elapsed_ns']/row['decode_steps']/1e6)
        prefill.append((row['request_elapsed_ns']-row['decode_elapsed_ns'])/1e6)
    return dict(independent_requests=len(samples),unprofiled_repeats=2,profile_repeats=1,max_new_tokens=2048,
        same_request_and_output_verified=True,rows=rows,mean_decode_step_ms=statistics.mean(decode),
        mean_request_amortized_step_ms=statistics.mean(amortized),mean_scheduler_prefill_ms=statistics.mean(prefill),
        clock_instrumentation='Buffered host scheduler commit clock; not per-kernel CUDA stage timing.',
        scope='Matched historical public workloads, different processes/instrumentation; profile time is not performance, no paired promotion.')


def build(root,repository):
    root=Path(root);repository=Path(repository)
    proofs={name:load(root/(name+'-frozen-audit.json')) for name in ORIGINS}
    requests={};protocols={}
    for name,(directory,module) in ORIGINS.items():
        proof=proofs[name];origin=repository/directory
        if (proof['module']!=module or proof['source_archive_verified'] is not True or
                proof['request']!=reference(origin.parent/'request.json') or
                proof['recorded_result']!=reference(origin/'result.json') or
                proof['result']!=load(origin/'result.json')):
            raise ValueError('frozen diagnostic receipt identity changed')
        request=load(origin.parent/'request.json')
        if proof['source']!=dict(path=request['source_archive']['path'],sha256=request['source_archive']['sha256']):
            raise ValueError('historical source archive differs from audit receipt')
        if reference(proof['source']['path'])!=proof['source']:raise ValueError('historical source archive changed')
        requests[name]=request['requests']
        protocols[name]=(request['stock_spec'],request['model_configs'],request['stock_engine'])
    if requests['lattice']!=requests['mapping'] or requests['lattice']!=requests['timing']:
        raise ValueError('lattice/profile/timing request protocols differ')
    if protocols['lattice']!=protocols['mapping'] or protocols['lattice']!=protocols['timing']:
        raise ValueError('lattice/profile/timing model or startup identity differs')
    lattice=proofs['lattice']['result']
    if lattice['independent_requests']!=10 or lattice['real_lattice_replays']!=20 or not lattice['output_regression_passed']:
        raise ValueError('historical finite lattice cohort incomplete')
    return dict(schema='stock-acceptance-path-priors-v1',gpu_submissions=0,
        acceptance=finite_lattice_prior(lattice['conditional_replay'],independent_requests=10,repeats=2),
        stock_paths=compact_graph(load(root/'graph-context-full.json')),
        matched_costs=matching_timing(repository,proofs['timing']),
        source_proofs={name:reference(root/(name+'-frozen-audit.json')) for name in ORIGINS},
        limitations=['All observations are historical reuse, not new GPU measurements.',
            'The separate old single-request baseline and cap256 timings are NOT this cohort.',
            'No live tree full-step cost or reliable same-path critical-path exposure is available.',
            'No final implementation, sealed data, promotion or trustworthy memory entry is provided.'])


def freeze_inputs(root,repository):
    root=Path(root);repository=Path(repository);files=set()
    for name,(directory,module) in ORIGINS.items():
        origin=repository/directory
        files.update((origin/'manifest.json',origin/'result.json',origin.parent/'request.json',origin.parent/'source.tar'))
        for prefix in (('disabled','enabled','profiles') if name=='lattice' else ('round-01','round-02') if name=='timing' else ('stock/live','stock/clocks','stock/graph-nodes','stock/runtime-profile')):
            for path in (origin/prefix).rglob('*'):
                if path.is_file() and path.suffix in ('.json','.jsonl','.gz'):files.add(path)
        if name=='mapping':
            files.update((origin/'metadata-files.json',origin/'traces.json',origin/'stock/samples.json'))
        files.add(root/(name+'-frozen-audit.json'))
    files.add(root/'graph-context-full.json')
    values=[reference(path) for path in sorted(files)]
    (root/'historical-inputs.json').write_text(json.dumps(values,sort_keys=True)+'\n')
    return values


def verify(root,repository):
    root=Path(root)
    for item in load(root/'historical-inputs.json'):
        if reference(item['path'])!=item:raise ValueError('frozen historical input changed')
    packet=build(root,repository)
    if packet!=load(root/'inputs/acceptance-paths.json'):raise ValueError('shared stock acceptance/path priors changed')
    return packet


def attach(root,repository,evidence):
    root=Path(root);packet=build(root,repository)
    target=root/'inputs/acceptance-paths.json'
    target.write_text(json.dumps(packet,sort_keys=True)+'\n')
    source=reference(target)
    for identity,key in (('acceptance-headroom','acceptance'),('stock-graph-paths','stock_paths'),('matched-stock-costs','matched_costs')):
        evidence['initial'][identity]=dict(value=packet[key],source=source,historical_reuse=True)
    profile_path=root/'inputs/stock-profile.json';profile=load(profile_path)
    mapping_request=load((Path(repository)/ORIGINS['mapping'][0]).parent/'request.json')
    target_config=str(Path(mapping_request['stock_spec']['target'])/'config.json')
    if profile['config']['sha256']!=mapping_request['model_configs'][target_config]:
        raise ValueError('matched profile target configuration differs from the prior stock metadata')
    graph=load(root/'graph-context-full.json')
    profile['trace']=graph['traces'][0]['source']
    profile_path.write_text(json.dumps(profile,sort_keys=True)+'\n')
    evidence['profile']=reference(profile_path)
    evidence['initial']['profile'].update(source=evidence['profile'],
        scope='First request of matched ten-request historical stock observer cohort; graph descriptors shared separately.')
    evidence['initial']['baseline']['scope']='Separate historical single-request counts, not the ten-request lattice/profile cohort.'
    evidence['headroom']=dict(packet=source,inputs=reference(root/'historical-inputs.json'),
        profile=evidence['profile'],repository=str(Path(repository).resolve()))
    return evidence


def verify_attachment(root,evidence):
    root=Path(root);context=evidence['headroom']
    if reference(context['packet']['path'])!=context['packet'] or reference(context['inputs']['path'])!=context['inputs']:
        raise ValueError('acceptance/path packet or historical input index changed')
    packet=verify(root,context['repository'])
    for identity,key in (('acceptance-headroom','acceptance'),('stock-graph-paths','stock_paths'),('matched-stock-costs','matched_costs')):
        if evidence['initial'][identity]!=dict(value=packet[key],source=context['packet'],historical_reuse=True):
            raise ValueError('registered stock prior was altered')
    profile=load(context['profile']['path']);graph=load(root/'graph-context-full.json')
    if evidence['profile']!=context['profile'] or profile['trace']!=graph['traces'][0]['source']:
        raise ValueError('BBuf profile differs from the matched historical cohort')
    return packet
