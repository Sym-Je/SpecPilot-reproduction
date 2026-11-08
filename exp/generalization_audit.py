"""Protocol adapter around the unchanged controller's validators and estimators."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.dev_campaign import check_phase_order, check_scored_measurements, combine_correctness, validate_packet
from controller.paper_policy import POLICY, calibration_from_intervals, candidate_verdict, measurement_protocol_id
from controller.scored_forcing import calibrate_delta, calibrate_stock, digest_record, judge_scored_forcing, load_score_trace, read_reference
from controller.stats import bootstrap_ci, stratified_geomean_ci
from exp.generalization_data import DOMAINS
from exp.p3_pair_run import SUITES, write_json
from harness.baseline_validation import read_rows

PHASES = ('null-pre', 'candidate', 'null-post')
PROTOCOL = 'public-generalization-v1'


def cluster_groups(pairs, requests, metric='throughput'):
    expected = {(number, request['id']) for number in (1, 2) for request in requests}
    actual = [(pair['round'], pair['id']) for pair in pairs]
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError('missing or duplicate physical-round request cluster')
    indexed = {(pair['round'], pair['id']):pair for pair in pairs}
    groups = {}
    for request in requests:
        values = []
        for number in (1, 2):
            pair = indexed[number, request['id']]
            if pair['suite'] != request['suite']:
                raise ValueError('request suite changed')
            ratio = (pair['b']['tokens_per_s'] / pair['a']['tokens_per_s'] if metric == 'throughput' else
                     pair['a']['latency_s'] / pair['b']['latency_s'])
            if not math.isfinite(ratio) or ratio <= 0:
                raise ValueError('invalid paired ratio')
            values.append(math.log(ratio))
        groups.setdefault(request['suite'], []).append(statistics.mean(values))
    return groups


def validate_session(directory, campaign):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest != campaign:
        raise ValueError('session manifest differs from the frozen campaign')
    if campaign['campaign_protocol_version'] != PROTOCOL or measurement_protocol_id(campaign) != campaign['protocol_id']:
        raise ValueError('wrong explicit protocol')
    if any(campaign.get(key) is not True for key in ('full_scale_warmup','synchronized_start','raw_capture')):
        raise ValueError('explicit complete warmup, synchronization and native capture required')
    requests = campaign['requests']
    arms = campaign['candidate_arms'] if directory.name == 'candidate' else campaign['null_arms']
    cap, all_pairs, assignments_seen, sessions, phases = campaign['max_new_tokens'], [], [], [], []
    for number in (1, 2):
        root = directory / f'round-{number:02d}'
        assignments = json.loads((root / 'deployment.json').read_text())['assignments']
        expected_gpus = campaign['gpus'] if number == 1 else list(reversed(campaign['gpus']))
        expected = [dict(arm=arm, gpu=gpu, port=port) for arm,gpu,port in zip(arms, expected_gpus, campaign['ports'])]
        if assignments != expected or len({item['gpu']['uuid'] for item in assignments}) != 2:
            raise ValueError('wrong arm, physical GPU, port, or swap')
        assignments_seen.append([item['gpu']['uuid'] for item in assignments])
        complete = json.loads((root / 'complete.json').read_text())
        if complete != dict(round=number, pairs=len(requests)):
            raise ValueError('incomplete measured round')
        pairs = read_rows(root / 'pairs.jsonl')
        if [pair['id'] for pair in pairs] != [request['id'] for request in requests]:
            raise ValueError('request order or coverage changed')
        for key, arm in zip(('a', 'b'), arms):
            if read_rows(root / (arm['name']+'.jsonl')) != [pair[key] for pair in pairs]:
                raise ValueError('arm rows do not match original pairs')
        events = {row['event']:row['time_unix'] for row in read_rows(root / 'events.jsonl')}
        if not events['servers_started'] < events['servers_ready'] <= events['warmup_complete'] <= pairs[0]['started_unix'] <= pairs[-1]['finished_unix'] <= events['requests_complete']:
            raise ValueError('invalid phase times')
        phases.append(dict(started_unix=events['servers_started'], completed_unix=events['requests_complete']))
        warmups = read_rows(root / 'warmup.jsonl')
        warm_requests = requests[:2] + requests
        if ([row['id'] for row in warmups] != [request['id'] for request in warm_requests] or
                [row['phase'] for row in warmups] != ['short'] * 2 + ['full'] * len(requests)):
            raise ValueError('missing or adaptive full-scale warmup')
        for row, request in zip(warmups, warm_requests):
            for key, assignment in zip(('a', 'b'), assignments):
                validate_packet(row[key], request, assignment, 32 if row['phase'] == 'short' else cap,
                                campaign['directory'], campaign['launch_protocol'])
                if row[key]['finish_reason'] not in ('stop','length'):
                    raise ValueError('failed warmup generation')
                if not events['servers_ready'] <= row[key]['client_timing']['started_unix'] <= events['warmup_complete']:
                    raise ValueError('warmup escaped declared phase')
        previous = events['warmup_complete']
        for pair, request in zip(pairs, requests):
            if pair['round'] != number or not previous <= pair['started_unix'] < pair['finished_unix']:
                raise ValueError('nonmonotonic or wrong-round measurement')
            previous = pair['finished_unix']
            for key, assignment in zip(('a', 'b'), assignments):
                validate_packet(pair[key], request, assignment, cap, campaign['directory'], campaign['launch_protocol'])
                if pair[key]['finish_reason'] not in ('stop','length'):
                    raise ValueError('failed measured generation')
                if not pair['started_unix'] <= pair[key]['client_timing']['started_unix'] <= pair['finished_unix']:
                    raise ValueError('HTTP timing escaped measured pair')
        telemetry = read_rows(root / 'telemetry.jsonl')
        during = [row for row in telemetry if pairs[0]['started_unix'] <= row['time_unix'] <= pairs[-1]['finished_unix']]
        if len(during) < 2 or any('error' in row for row in telemetry):
            raise ValueError('missing or failed telemetry')
        for snapshot in during:
            if {gpu['uuid'] for gpu in snapshot['gpus']} != set(assignments_seen[-1]):
                raise ValueError('telemetry GPU identity changed')
            for gpu in snapshot['gpus']:
                if any(not math.isfinite(gpu.get(field, math.nan)) or gpu[field] <= 0
                       for field in ('clocks_sm_mhz','clocks_mem_mhz','temperature_c','power_w')):
                    raise ValueError('invalid GPU state')
            if any(not snapshot['arms'].get(arm['name']) or
                   not all(process.get('allowed_cpus') for process in snapshot['arms'][arm['name']]) for arm in arms):
                raise ValueError('missing owned process evidence')
        sessions.append([(during[0]['arms'][arm['name']][0]['pid'], during[0]['arms'][arm['name']][0]['start_ticks']) for arm in arms])
        all_pairs.extend(pairs)
    if any(left == right for left,right in zip(sessions[0], sessions[1])):
        raise ValueError('server process reused across physical rounds')
    if phases[0]['completed_unix'] >= phases[1]['started_unix']:
        raise ValueError('physical rounds overlap')
    groups = cluster_groups(all_pairs, requests)
    inventory = {str(path.relative_to(directory)):hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(directory.rglob('*.json*')) if path.name != 'session-validation.json'}
    return dict(groups=groups, interval=stratified_geomean_ci(groups),
                started_unix=phases[0]['started_unix'], completed_unix=phases[1]['completed_unix'],
                source_sha256=digest_record(inventory), physical_gpu_swap=True, fresh_servers=True), all_pairs


def verdict_summary(verdict):
    return {key:verdict[key] for key in ('n','mismatches','rate','delta','rate_flagged',
            'large_margin_events','unexplained_events','event_flagged','correctness_passed')}


def rescore(directory, campaign, requests):
    root = directory / 'correctness'
    verdicts, subgroup = [], {domain:[] for domain in DOMAINS}
    for number in (1, 2):
        timed_root = directory / 'candidate' / f'round-{number:02d}'
        paths = {role:[root / f'round-{number:02d}-{role}' / (request['id']+'.json') for request in requests]
                 for role in ('stock', 'final')}
        ar = [root / 'ar' / (request['id']+'.json') for request in requests]
        for role in ('stock', 'final'):
            check_scored_measurements(paths[role], read_rows(timed_root / (role+'.jsonl')), requests,
                                      evidence_root=campaign['directory'])
        for path, request in zip(ar, requests):
            trace = load_score_trace(path, evidence_root=campaign['directory'])
            if (trace['prompt_ids'] != request['input_ids'] or trace['request_id'] != request['id'] or
                    trace['generator']['server_args']['speculative_algorithm'] is not None):
                raise ValueError('wrong AR calibration identity')
        score_start = json.loads((Path(campaign['directory'])/'score-start.json').read_text())['started_unix']
        for path in paths['stock'] + paths['final'] + ar:
            trace = load_score_trace(path, evidence_root=campaign['directory'])
            packet = read_reference(trace['raw_evidence'], campaign['directory'])
            if packet['started_unix'] < score_start:
                raise ValueError('scoring overlapped timing')
            for segment in trace['generation_segments']:
                body=read_reference(segment,campaign['directory'])['request']
                if body['sampling_params'].get('max_new_tokens') != campaign['max_new_tokens'] or body['sampling_params'].get('ignore_eos',False):
                    raise ValueError('wrong cap or forced length in scored generation')
        audits = sorted((root / f'round-{number:02d}-final-audits').glob('[0-9][0-9][0-9][0-9].json'))
        delta = calibrate_delta(paths['stock'], ar, evidence_root=campaign['directory'])
        baseline = calibrate_stock(paths['stock'], delta, evidence_root=campaign['directory'])
        verdict = judge_scored_forcing(baseline, paths['final'], evidence_root=campaign['directory'], prefill_audits=audits)
        stored = json.loads((root / f'round-{number:02d}-verdict.json').read_text())
        if stored != verdict:
            raise ValueError('stored forcing verdict differs from raw evidence')
        verdicts.append(verdict)
        for domain in DOMAINS:
            indices = [index for index,request in enumerate(requests) if request['suite'] == domain]
            selected = {role:[values[index] for index in indices] for role,values in paths.items()}
            try:
                local_delta = calibrate_delta(selected['stock'], [ar[index] for index in indices], evidence_root=campaign['directory'])
            except ValueError as error:
                if 'no observed stock/AR first divergence' not in str(error):
                    raise
                subgroup[domain].append(dict(correctness_passed=None, reason='no first divergence; local delta uncalibrated'))
                continue
            local_stock = calibrate_stock(selected['stock'], local_delta, evidence_root=campaign['directory'])
            domain_audits = [path for path in audits if json.loads(path.read_text())['request_id'] in
                             {request['id'] for request in requests if request['suite'] == domain}]
            local = judge_scored_forcing(local_stock, selected['final'], evidence_root=campaign['directory'], prefill_audits=domain_audits)
            subgroup[domain].append(dict(verdict_summary(local), stock=local_stock['stock_counts']))
    return combine_correctness(verdicts), subgroup


def quality_summary(directory, requests):
    rows = read_rows(directory / 'quality.jsonl')
    expected = {(number, role, request['id']) for number in (1,2) for role in ('stock','final') for request in requests}
    actual = [(row['round'],row['role'],row['id']) for row in rows]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('incomplete task-quality coverage')
    indexed = {(row['round'],row['role'],row['id']):row for row in rows}
    for number in (1,2):
        pairs=read_rows(directory/'candidate'/f'round-{number:02d}'/'pairs.jsonl')
        for pair in pairs:
            for key,role in (('a','stock'),('b','final')):
                if indexed[number,role,pair['id']]['output_sha256'] != pair[key]['output_sha256']:
                    raise ValueError('quality not bound to actual timed output')
    output = {}
    for domain in DOMAINS:
        selected = [request for request in requests if request['suite'] == domain]
        differences, stock, final = [], [], []
        ungraded = 0
        for request in selected:
            scores = {role:[indexed[number,role,request['id']]['quality']['score'] for number in (1,2)] for role in ('stock','final')}
            if any(value is None for values in scores.values() for value in values):
                ungraded += 1
                continue
            stock.append(statistics.mean(scores['stock']))
            final.append(statistics.mean(scores['final']))
            differences.append(final[-1] - stock[-1])
        result = dict(evaluated_requests=len(differences), ungraded_requests=ungraded,
                      metric=indexed[1,'stock',selected[0]['id']]['quality']['metric'],
                      semantic_noninferiority_proven=False)
        if differences:
            mean, lower = bootstrap_ci(differences, iters=10000, alpha=.025, seed=0)
            _, negative_lower = bootstrap_ci([-value for value in differences], iters=10000, alpha=.025, seed=0)
            result.update(stock_mean=statistics.mean(stock), final_mean=statistics.mean(final),
                          paired_difference=dict(mean=mean, lower=lower, upper=-negative_lower),
                          scope='task proxy; 20 or 4 independent requests; not a lossless proof or powered quality noninferiority test')
        output[domain] = result
    return output


def verify_quality(private,dataset):
    from transformers import AutoTokenizer
    from exp.generalization_quality import grade,run_code
    tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True)
    items={item['id']:item for item in dataset['items']}
    controls=json.loads((private/'quality-controls.json').read_text())
    for item in dataset['items']:
        if item['metric']=='code':
            code=item['canonical'] if not item.get('entry_point') else item['code_prompt']+item['canonical']
            if controls[item['id']] != (run_code(code,item['tests'])['status']=='pass'):
                raise ValueError('quality canonical control not reproducible')
    for cap in (2048,256,4096):
        directory=private/f'cap-{cap}'
        quality={(row['round'],row['role'],row['id']):row for row in read_rows(directory/'quality.jsonl')}
        for number in (1,2):
            for role in ('stock','final'):
                for row in read_rows(directory/'candidate'/f'round-{number:02d}'/(role+'.jsonl')):
                    item=items[row['id']]
                    result=grade(item,tokenizer.decode(row['output_ids'],skip_special_tokens=False)) if controls.get(item['id'],True) else dict(score=None,metric='code-control-failed',answered=None)
                    if result != quality[number,role,row['id']]['quality']:
                        raise ValueError('task quality differs on independent replay')


def analyze_cap(directory, campaign):
    sessions = [validate_session(directory / phase, campaign) for phase in PHASES]
    check_phase_order([session[0] for session in sessions])
    nulls = [dict(session_id=phase, protocol_id=campaign['protocol_id'], source_sha256=session[0]['source_sha256'],
                  interval=session[0]['interval']) for phase,session in zip(PHASES,sessions) if phase != 'candidate']
    calibration = calibration_from_intervals(nulls, declared_sessions=['null-pre','null-post'],
        protocol_id=campaign['protocol_id'], campaign_id=campaign['campaign_id'], policy=POLICY)
    correct, domain_correct = rescore(directory, campaign, campaign['requests'])
    pairs = sessions[1][1]
    identical = all(pair['a']['output_sha256'] == pair['b']['output_sha256'] for pair in pairs)
    verdict = candidate_verdict(groups=sessions[1][0]['groups'], calibration=calibration,
        correctness=correct, protocol_id=campaign['protocol_id'], campaign_id=campaign['campaign_id'], output_identical=identical)
    groups = sessions[1][0]['groups']
    subgroup = {}
    for name, domains in [('ID',SUITES), ('OOD',[domain for domain in DOMAINS if domain not in SUITES])]:
        subgroup[name] = stratified_geomean_ci({domain:groups[domain] for domain in domains})
    for band in ('short','long'):
        selected = [request for request in campaign['requests'] if request['input_band'] == band]
        selected_pairs = [pair for pair in pairs if pair['id'] in {request['id'] for request in selected}]
        subgroup['input-'+band] = stratified_geomean_ci(cluster_groups(selected_pairs, selected))
    domains = {}
    quality = quality_summary(directory, campaign['requests'])
    dataset=json.loads(Path(campaign['dataset_path']).read_text())
    panel_requests=[request for request in campaign['requests'] if request['id'] in dataset['panel_ids']]
    panel_pairs=[pair for pair in pairs if pair['id'] in {request['id'] for request in panel_requests}]
    panel_groups=cluster_groups(panel_pairs,panel_requests)
    panel=dict(unique_requests=40,throughput=stratified_geomean_ci(panel_groups),
               latency=stratified_geomean_ci(cluster_groups(panel_pairs,panel_requests,'latency')),
               per_domain={domain:stratified_geomean_ci({domain:panel_groups[domain]}) for domain in DOMAINS},
               outputs={role:dict(mean_tokens=statistics.mean(pair[key]['completion_tokens'] for pair in panel_pairs),
                   stop=sum(pair[key]['finish_reason']=='stop' for pair in panel_pairs),
                   length=sum(pair[key]['finish_reason']=='length' for pair in panel_pairs)) for key,role in (('a','stock'),('b','final'))})
    for domain in DOMAINS:
        selected = [pair for pair in pairs if pair['suite'] == domain]
        fields = {}
        for key, role in (('a','stock'),('b','final')):
            values = [pair[key] for pair in selected]
            fields[role] = dict(mean_tokens=statistics.mean(row['completion_tokens'] for row in values),
                mean_latency_s=statistics.mean(row['latency_s'] for row in values),
                mean_tokens_per_s=statistics.mean(row['tokens_per_s'] for row in values),
                stop=sum(row['finish_reason'] == 'stop' for row in values),
                length=sum(row['finish_reason'] == 'length' for row in values), failures=0, measured_outputs=len(values))
        domains[domain] = dict(throughput=stratified_geomean_ci({domain:groups[domain]}),
            latency=stratified_geomean_ci(cluster_groups(selected, [request for request in campaign['requests'] if request['suite']==domain], 'latency')),
            physical_rounds=[math.exp(statistics.mean(math.log(pair['b']['tokens_per_s']/pair['a']['tokens_per_s'])
                for pair in selected if pair['round'] == number)) for number in (1,2)],
            outputs=fields, correctness=domain_correct[domain], quality=quality[domain])
    return dict(cap=campaign['max_new_tokens'], unique_requests=len(campaign['requests']),
        protocol_id=campaign['protocol_id'], throughput=verdict['interval'], latency=stratified_geomean_ci(cluster_groups(pairs,campaign['requests'],'latency')),
        noise=calibration['noise'], nulls=[dict(session=phase, interval=session[0]['interval']) for phase,session in zip(PHASES,sessions) if phase!='candidate'],
        threshold=verdict['threshold'], performance_passed=verdict['performance_passed'],
        forcing_passed=correct['correctness_passed'], forcing_rounds=[verdict_summary(value) for value in correct['rounds']],
        joint_acceptance_passed=verdict['eligible_for_promotion'], output_identical=identical,
        groups=subgroup, domains=domains, fixed_length_panel=panel, promoted=False, ledger_eligible=False,
        interval_scope='unadjusted exploratory 95% intervals; physical rounds clustered; no universal-domain claim')


def analyze(private, public):
    root = json.loads((private / 'manifest.json').read_text())
    dataset_path = Path(root['dataset_path'])
    if hashlib.sha256(dataset_path.read_bytes()).hexdigest() != root['dataset_sha256']:
        raise ValueError('blind dataset changed')
    snapshot=Path(root['source_archive'])
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != root['source_archive_sha256']:
        raise ValueError('source archive changed')
    with tarfile.open(snapshot) as archive:
        for name,checksum in root['source_sha256'].items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest() != checksum:
                raise ValueError('runtime source differs from frozen archive')
    dataset=json.loads(dataset_path.read_text())
    verify_quality(private,dataset)
    head = json.loads((private / 'head-preflight/result.json').read_text())
    if (head.get('native_reverse_token_differences') != 0 or head.get('tokens') != 1 or
            head.get('head_identity',{}).get('source_sha256') != root['source_sha256']['controller/head_reference.py'] or
            any(not math.isfinite(check[key]) or check[key] > .001 for check in head['checks'] for key in ('native_logprob_error','native_choice_margin','max_logit_difference'))):
        raise ValueError('independent FP32 head preflight failed')
    results = []
    previous = -math.inf
    for cap in (2048,256,4096):
        directory = private / f'cap-{cap}'
        campaign = json.loads((directory / 'manifest.json').read_text())
        if campaign['source_pin'] != root['source_pin'] or campaign['source_sha256'] != root['source_sha256']:
            raise ValueError('source differs across cap conditions')
        dataset = json.loads(dataset_path.read_text())
        expected = dataset['requests'] if cap == 2048 else [request for request in dataset['requests'] if request['id'] in dataset['panel_ids']]
        if campaign['requests'] != expected:
            raise ValueError('cap input differs from the frozen panel')
        for phase in PHASES:
            session,_ = validate_session(directory / phase,campaign)
            if session['started_unix'] < previous:
                raise ValueError('cap sessions overlapped or reordered')
            previous = session['completed_unix']
        results.append(analyze_cap(directory,campaign))
    score_start=json.loads((private/'score-start.json').read_text())['started_unix']
    if score_start <= previous:
        raise ValueError('scoring was not isolated from all timing')
    cleanup = json.loads((private / 'cleanup.json').read_text())
    if len(cleanup) != 2 or any(gpu['memory_used_mib'] > 256 or gpu['utilization'] > 10 for gpu in cleanup):
        raise ValueError('GPU cleanup not established')
    result = dict(execution_complete=True, source_pin=root['source_pin'], dataset_sha256=root['dataset_sha256'],
        unique_requests=200, length_panel_unique_requests=40, caps=results,
        final_modified=False, sealed_read=False, promoted=False, ledger_eligible=False,
        limitations=['public data not guaranteed author-unseen','MT/dialogue semantic quality not evaluated',
                    'quality proxies not powered noninferiority tests','unadjusted domain intervals',
                    'not original paper sealed, mathematical losslessness, autonomous discovery or proof against all reward hacking'])
    with public.open('x') as destination:
        json.dump(result,destination,indent=2,ensure_ascii=False,allow_nan=False)
        destination.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=analyze(args.private.resolve(),args.out.resolve())
    print(json.dumps(dict(execution_complete=True, conditions=[dict(cap=cap['cap'],interval=cap['throughput'],forcing_passed=cap['forcing_passed']) for cap in result['caps']])))
