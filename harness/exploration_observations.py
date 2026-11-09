"""Controlled count/order export; no token IDs leave the original replay process."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def history_screen(observations):
    requests=observations['requests']
    if len(requests)<2 or len({row['request_group'] for row in requests})!=len(requests):
        raise ValueError('independent request groups required')
    canonical=[]
    for request in requests:
        rounds=request['rounds']
        if len(rounds)!=2 or {row['round'] for row in rounds}!={1,2}:
            raise ValueError('both physical repetitions required')
        sequences=[row['accepted_counts'] for row in rounds]
        if (sequences[0]!=sequences[1] or len(sequences[0])<2 or
                any(type(value) is not int or not 0<=value<=7 for sequence in sequences for value in sequence)):
            raise ValueError('repeat paths differ or invalid stock counts; no silent regrouping')
        canonical.append(dict(request_group=request['request_group'],suite=request['suite'],sequence=sequences[0]))
    results=[]
    for held in canonical:
        train=[row for row in canonical if row['request_group']!=held['request_group']]
        global_values=[value for row in train for value in row['sequence'][1:]]
        suite_values=[value for row in train if row['suite']==held['suite'] for value in row['sequence'][1:]]
        fallback=not suite_values
        suite_values=suite_values or global_values
        constants=dict(training_mean=statistics.mean(global_values),training_median=statistics.median(global_values),
            suite_training_mean=statistics.mean(suite_values),suite_training_median=statistics.median(suite_values))
        targets=held['sequence'][1:]
        errors={name:statistics.mean(abs(value-prediction) for value in targets) for name,prediction in constants.items()}
        errors['previous_one']=statistics.mean(abs(value-previous) for value,previous in zip(targets,held['sequence'][:-1]))
        results.append(dict(request_group=held['request_group'],suite=held['suite'],observed_steps=len(held['sequence']),
            evaluated_targets=len(targets),suite_fallback_to_global=fallback,training_constants=constants,mae=errors))
    return dict(independent_requests=len(canonical),physical_repeats_per_request=2,
        protocol='leave-one-request-out; previous one committed count; training-only mean/median and suite constants; first target excluded',
        per_request=results,equal_request_mean_mae={name:statistics.mean(row['mae'][name] for row in results) for name in results[0]['mae']},
        population_generalization_established=False,end_to_end_gain=None,
        limitations=['three preselected diagnostic requests are not a representative population',
            'predicting stock counts does not simulate a changed block size, its graph costs or a complete generation'])


def terminal_order_screen(observations):
    samples=[]
    for request in observations['requests']:
        for row in request['rounds']:
            orders=row['uncommitted_emitted_before_finish']
            if not isinstance(orders,list) or any(type(value) is not bool for value in orders):
                raise ValueError('invalid recorded order')
            samples.append(dict(request_group=request['request_group'],round=row['round'],
                uncommitted_steps=len(orders),uncommitted_emitted_before_finish=sum(orders),
                uncommitted_emitted_after_finish=len(orders)-sum(orders)))
    return dict(independent_requests=len(observations['requests']),samples=samples,
        queue_entry_timestamps_available=False,native_critical_path_available=False,end_to_end_gain=None,
        scope='instrumented worker output materialization/emission vs scheduler finish commit; no queue/cancellation or latency causality')


def export_observations(original,out):
    from controller.scored_forcing import read_reference
    from harness.step_replay import read_stream,replay_bound
    original=Path(original).absolute()
    manifest=json.loads((original/'manifest.json').read_text())
    collected=defaultdict(list)
    stream_hashes=[]
    generation_hashes=[]
    for number in (1,2):
        root=original/'enabled'/f'round-{number:02d}'
        grouped=defaultdict(list)
        for reference in json.loads((root/'streams.json').read_text()):
            stream_hashes.append(reference['sha256'])
            for event in read_stream(reference,original):
                if event['tree_sha']!=manifest['arms']['enabled'][1]['tree_sha']:
                    raise ValueError('observer tree drift')
                grouped[event['rid']].append(event)
        pairs=[json.loads(line) for line in (root/'pairs.jsonl').read_text().splitlines()]
        for index,(pair,request) in enumerate(zip(pairs,manifest['requests'])):
            if pair['id']!=request['id']:
                raise ValueError('diagnostic request ordering changed')
            generation=pair['b']['raw_evidence']
            generation_hashes.append(generation['sha256'])
            packet=read_reference(generation,original)
            events=grouped[packet['request']['rid']]
            report=replay_bound(events,generation,root=original)
            commits=[event for event in events if event['kind']=='commit']
            verifications=[event for event in events if event['kind']=='verify']
            final=commits[-1]
            counts=[]
            previous=0
            for event in commits:
                if event['phase']=='decode':
                    counts.append(event['correct_drafts']-previous)
                previous=event['correct_drafts']
            if len(counts)!=report['committed_verify_steps']:
                raise ValueError('accepted sequence differs from original chain replay')
            tail=verifications[len(counts):]
            collected[index].append(dict(round=number,accepted_counts=counts,
                uncommitted_emitted_before_finish=[event['sequence']<final['sequence'] for event in tail],
                seed_tokens=report['seed_tokens'],output_tokens=report['output_tokens'],tail_clip_tokens=report['tail_clip_tokens']))
    result=dict(schema='count-order-observations-v1',independent_requests=3,
        requests=[dict(request_group=f'probe-{index+1}',suite=request['suite'],role='anomaly' if index==1 else 'normal',rounds=collected[index])
                  for index,request in enumerate(manifest['requests'])],
        provenance=dict(original_manifest_sha256=hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
            source_pin=manifest['source_pin'],raw_stream_sha256=sorted(stream_hashes),generation_packet_sha256=generation_hashes),
        privacy='counts and order only; no input/output/candidate/target token IDs or generated text')
    history_screen(result)
    terminal_order_screen(result)
    with Path(out).open('x') as output:
        json.dump(result,output,indent=2)
        output.write('\n')
    return result
