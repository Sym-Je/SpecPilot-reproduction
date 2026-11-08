"""Explicit dev campaign validation; produces evidence, never a promotion."""

import argparse
import json
import math
from pathlib import Path

from controller.http_transport import sha_ids
from controller.paper_policy import candidate_verdict, calibrate_null_runs, measurement_protocol_id, valid_digest
from controller.scored_forcing import calibrate_delta, calibrate_stock, checked_server, digest_record, judge_scored_forcing, load_score_trace, read_reference
from controller.scoring import server_arguments
from controller.stats import stratified_geomean_ci
from exp.p3_pair_run import SUITES
from harness.baseline_validation import read_rows, validate_paired_run


PROTOCOL = 'dev-joint-v1'
PHASES = ('null-pre', 'candidate', 'null-post')


def check_phase_order(phases):
    if len(phases) != 3:
        raise ValueError('both null sessions and the intervening candidate are required')
    previous = -math.inf
    for phase in phases:
        start, finish = phase.get('started_unix'), phase.get('completed_unix')
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, finish)) or
                not previous <= start < finish):
            raise ValueError('campaign phases overlap or are out of predeclared order')
        previous = finish


def combine_correctness(verdicts):
    if len(verdicts) != 2 or any(not valid_digest(verdict.get('evidence_sha256')) for verdict in verdicts):
        raise ValueError('both complete physical-round correctness verdicts required')
    result = dict(correctness_passed=all(verdict.get('correctness_passed') is True for verdict in verdicts),
                  rounds=verdicts, promoted=False, ledger_eligible=False)
    return dict(result, evidence_sha256=digest_record(result))


def check_scored_measurements(paths, rows, requests, *, evidence_root):
    if not len(paths) == len(rows) == len(requests) or len({row['id'] for row in rows}) != len(requests):
        raise ValueError('measured and scored request coverage differs')
    measured = {row['id']: row for row in rows}
    for path, request in zip(paths, requests):
        trace = load_score_trace(path, evidence_root=evidence_root)
        row = measured.get(request['id'])
        if (row is None or trace['request_id'] != request['id'] or trace['prompt_ids'] != request['input_ids'] or
                trace['output_ids'] != row['output_ids'] or trace['generation_segments'] != [row['raw_evidence']] or
                trace['generator'] != row['generator']):
            raise ValueError('forcing did not score the exact original timed generation')


def validate_packet(sample, request, assignment, cap, directory, launch_protocol):
    packet = read_reference(sample['raw_evidence'], directory)
    checked_server(sample['generator'], directory)
    actual = server_arguments(read_reference(sample['generator']['evidence'], directory)['response'])
    expected = dict(launch_protocol, speculative_algorithm='DFLASH',
                    speculative_num_draft_tokens=assignment['arm']['block'])
    if (sample['generator']['tree_sha'] != assignment['arm']['tree_sha'] or
            any(actual.get(key) != value for key, value in expected.items())):
        raise ValueError('live generator launch parameters differ from the frozen protocol')
    body, response = packet.get('request', {}), packet.get('response', {})
    if (packet.get('http_status') != 200 or body.get('input_ids') != request['input_ids'] or
            body.get('sampling_params') != dict(temperature=0.0, top_k=1, max_new_tokens=cap) or
            response.get('output_ids') != sample['output_ids'] or
            response.get('meta_info', {}).get('completion_tokens') != sample['completion_tokens'] or
            response['meta_info'].get('finish_reason', {}).get('type') != sample['finish_reason']):
        raise ValueError('timed generation differs from its original native HTTP packet')
    if (sample['input_sha256'] != request['input_sha256'] or sample['gpu_uuid'] != assignment['gpu']['uuid'] or
            sample['arm'] != assignment['arm']['name'] or sample['tree_sha'] != assignment['arm']['tree_sha'] or
            sample['block'] != assignment['arm']['block'] or sample['max_new_tokens'] != cap or
            not 0 < len(sample['output_ids']) == sample['completion_tokens'] <= cap or
            sha_ids(sample['output_ids']) != sample['output_sha256']):
        raise ValueError('invalid warmup or measured identity')
    timing = sample.get('client_timing', {})
    values = [timing.get(field) for field in ('step_start_ns', 'http_open_start_ns', 'body_complete_ns', 'step_end_ns')]
    if (any(type(value) is not int for value in values) or values != sorted(values) or values[-1] <= values[0] or
            timing.get('url') != f'http://127.0.0.1:{assignment["port"]}/generate' or
            abs((values[-1] - values[0]) / 1e9 - sample['latency_s']) > .005 or
            abs(sample['tokens_per_s'] * sample['latency_s'] - sample['completion_tokens']) > 1e-6):
        raise ValueError('invalid or inconsistent actual HTTP timing')


def validate_session(directory, campaign):
    directory = Path(directory)
    names = ['stock', 'final'] if directory.name == 'candidate' else ['stock-a', 'stock-b']
    expected_arms = campaign['candidate_arms'] if directory.name == 'candidate' else campaign['null_arms']
    checked, manifest, summary = validate_paired_run(directory, names, expected_arms,
        campaign['requests'], rounds=2, per_suite=6)
    if (manifest.get('head') != campaign['source_pin'] or manifest.get('campaign_id') != campaign['campaign_id'] or
            manifest.get('source_sha256') != campaign['source_sha256'] or
            measurement_protocol_id(manifest) != campaign['protocol_id']):
        raise ValueError('session deployment or source differs from the predeclared campaign')
    if any(manifest.get(key) is not True for key in ('full_scale_warmup', 'synchronized_start', 'raw_capture')):
        raise ValueError('full-scale warmup, synchronized start and original HTTP evidence required')
    if manifest.get('campaign_protocol_version') != PROTOCOL:
        raise ValueError('explicit dev campaign protocol is missing')
    process_sessions, round_groups, rows_by_round = [], [], []
    for number in (1, 2):
        root = directory / f'round-{number:02d}'
        deployment = json.loads((root / 'deployment.json').read_text())
        assignments = deployment['assignments']
        if [assignment['port'] for assignment in assignments] != campaign['ports']:
            raise ValueError('unexpected measured endpoints')
        pairs = read_rows(root / 'pairs.jsonl')
        if [pair['id'] for pair in pairs] != [request['id'] for request in campaign['requests']]:
            raise ValueError('measured request order changed')
        events = {event['event']: event['time_unix'] for event in read_rows(root / 'events.jsonl')}
        if not events['servers_started'] <= events['servers_ready'] <= events['warmup_complete'] <= pairs[0]['started_unix']:
            raise ValueError('measurement began before complete warmup')
        warmup = read_rows(root / 'warmup.jsonl')
        warm_requests = campaign['requests'][:2] + campaign['requests']
        phases = ['short'] * 2 + ['full'] * 30
        if [row['phase'] for row in warmup] != phases or [row['id'] for row in warmup] != [row['id'] for row in warm_requests]:
            raise ValueError('missing or adaptive full-pass warmup')
        for row, request, phase in zip(warmup, warm_requests, phases):
            for key, assignment in zip(('a', 'b'), assignments):
                validate_packet(row[key], request, assignment, 32 if phase == 'short' else 2048,
                                campaign['directory'], campaign['launch_protocol'])
                if not events['servers_ready'] <= row[key]['client_timing']['started_unix'] <= events['warmup_complete']:
                    raise ValueError('warmup escaped its declared phase')
        groups = {suite: [] for suite in SUITES}
        for pair, request in zip(pairs, campaign['requests']):
            for key, assignment in zip(('a', 'b'), assignments):
                validate_packet(pair[key], request, assignment, 2048, campaign['directory'], campaign['launch_protocol'])
            groups[request['suite']].append(math.log(pair['b']['tokens_per_s'] / pair['a']['tokens_per_s']))
        telemetry = read_rows(root / 'telemetry.jsonl')
        during = [row for row in telemetry if pairs[0]['started_unix'] <= row['time_unix'] <= pairs[-1]['finished_unix']]
        if len(during) < 2 or any('error' in row for row in telemetry):
            raise ValueError('missing or failed measurement telemetry')
        for snapshot in during:
            if {gpu['uuid'] for gpu in snapshot['gpus']} != {assignment['gpu']['uuid'] for assignment in assignments}:
                raise ValueError('telemetry physical GPU identity differs')
            for gpu in snapshot['gpus']:
                if any(not math.isfinite(gpu.get(field, math.nan)) or gpu[field] <= 0
                       for field in ('clocks_sm_mhz', 'clocks_mem_mhz', 'temperature_c', 'power_w')):
                    raise ValueError('missing GPU state evidence')
            if any(not snapshot['arms'].get(name) or not all(process.get('allowed_cpus') for process in snapshot['arms'][name]) for name in names):
                raise ValueError('missing owned CPU process evidence')
        process_sessions.append(tuple((name, during[0]['arms'][name][0]['pid'], during[0]['arms'][name][0]['start_ticks']) for name in names))
        round_groups.append({suite: math.exp(sum(values) / len(values)) for suite, values in groups.items()})
        rows_by_round.append({key: [pair[key] for pair in pairs] for key in ('a', 'b')})
    if len(set(process_sessions)) != 2:
        raise ValueError('fresh round server processes not demonstrated')
    if summary['bootstrap_iters'] != 10000 or summary['bootstrap_seed'] != 0:
        raise ValueError('unregistered bootstrap parameters')
    groups = {suite: [] for suite in SUITES}
    for request in campaign['requests']:
        groups[request['suite']].append(summary['per_request_log_ratios'][request['id']])
    checked.update(interval=stratified_geomean_ci(groups), round_per_suite=round_groups,
                   process_sessions=process_sessions, groups=groups)
    if directory.name != 'candidate':
        from controller.null_validation import validate_null
        validate_null(directory, per_suite=6)
    return checked, manifest, summary, rows_by_round


def validate_campaign(directory):
    directory = Path(directory).resolve()
    campaign = json.loads((directory / 'manifest.json').read_text())
    if campaign['directory'] != str(directory) or campaign['campaign_protocol_version'] != PROTOCOL:
        raise ValueError('unexpected campaign identity')
    sessions = [validate_session(directory / phase, campaign) for phase in PHASES]
    check_phase_order([dict(started_unix=session[1]['started_unix'], completed_unix=session[2]['completed_unix']) for session in sessions])
    if len({process for session in sessions for process in session[0]['process_sessions']}) != 6:
        raise ValueError('server process reuse across campaign phases')
    noise = calibrate_null_runs([directory / PHASES[0], directory / PHASES[2]],
        declared_sessions=[PHASES[0], PHASES[2]], campaign_id=campaign['campaign_id'], mode='current',
        expected_protocol_id=campaign['protocol_id'], expected_source_pin=campaign['source_pin'],
        campaign_started_unix=campaign['started_unix'], per_suite=6)
    requests = campaign['requests']
    root = directory / 'correctness'
    autoregressive = [root / 'ar' / f'{request["id"]}.json' for request in requests]
    head = json.loads((root / 'head-preflight/result.json').read_text())
    if (head.get('mode') != 'preflight' or head.get('tokens') != 1 or
            head.get('native_reverse_token_differences') != 0 or
            head.get('head_identity', {}).get('source_sha256') != campaign['source_sha256']['controller/head_reference.py']):
        raise ValueError('missing or wrong-source independent FP32 head preflight')
    for check in head['checks']:
        if any(not math.isfinite(check.get(key, math.nan)) or check[key] > .001
               for key in ('native_logprob_error', 'native_choice_margin', 'max_logit_difference')):
            raise ValueError('independent head numerical preflight failed')
    for path, request in zip(autoregressive, requests):
        trace = load_score_trace(path, evidence_root=directory)
        if (trace['request_id'] != request['id'] or trace['prompt_ids'] != request['input_ids'] or
                trace['generator']['server_args']['speculative_algorithm'] is not None or
                trace['scorer']['tree_sha'] != campaign['null_arms'][0]['tree_sha'] or
                trace['generator']['tree_sha'] != campaign['null_arms'][0]['tree_sha']):
            raise ValueError('invalid current AR calibration output')
    verdicts, deltas, stock_counts = [], [], []
    for number, rows in zip((1, 2), sessions[1][3]):
        stock = [root / f'round-{number:02d}-stock' / f'{request["id"]}.json' for request in requests]
        final = [root / f'round-{number:02d}-final' / f'{request["id"]}.json' for request in requests]
        check_scored_measurements(stock, rows['a'], requests, evidence_root=directory)
        check_scored_measurements(final, rows['b'], requests, evidence_root=directory)
        for path in stock + final + autoregressive:
            trace = json.loads(Path(path).read_text())
            raw = read_reference(trace['raw_evidence'], directory)
            if raw.get('started_unix', -math.inf) < sessions[2][2]['completed_unix']:
                raise ValueError('correctness scoring overlapped the paired performance campaign')
        delta = calibrate_delta(stock, autoregressive, evidence_root=directory)
        baseline = calibrate_stock(stock, delta, evidence_root=directory)
        audits = sorted((root / f'round-{number:02d}-final-audits').glob('[0-9][0-9][0-9][0-9].json'))
        verdict = judge_scored_forcing(baseline, final, evidence_root=directory, prefill_audits=audits)
        stored = json.loads((root / f'round-{number:02d}-verdict.json').read_text())
        if stored != verdict:
            raise ValueError('stored correctness differs from its original evidence')
        verdicts.append(verdict)
        deltas.append(delta['delta'])
        stock_counts.append(baseline['stock_counts'])
    correct = combine_correctness(verdicts)
    output_identical = all(pair['a']['output_sha256'] == pair['b']['output_sha256']
        for number in (1, 2) for pair in read_rows(directory / 'candidate' / f'round-{number:02d}' / 'pairs.jsonl'))
    verdict = candidate_verdict(groups=sessions[1][0]['groups'], calibration=noise, correctness=correct,
        protocol_id=campaign['protocol_id'], campaign_id=campaign['campaign_id'], output_identical=output_identical)
    result = dict(protocol=PROTOCOL, campaign_id=campaign['campaign_id'], source_pin=campaign['source_pin'],
        protocol_id=campaign['protocol_id'], noise_calibration=noise, correctness=correct, deltas=deltas,
        stock_counts=stock_counts, performance=verdict, session_checks=[session[0] for session in sessions],
        output_identical=output_identical, joint_acceptance_passed=verdict['eligible_for_promotion'],
        promoted=False, ledger_eligible=False,
        scope='author-product formal dev acceptance; not sealed, mathematical losslessness or independent discovery')
    return dict(result, evidence_sha256=digest_record(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = validate_campaign(args.directory)
    with args.out.open('x') as output:
        json.dump(result, output, indent=2, allow_nan=False)
    print(json.dumps(dict(joint_acceptance_passed=result['joint_acceptance_passed'],
        interval=result['performance']['interval'], noise=result['noise_calibration']['noise'], deltas=result['deltas'])))
    if not result['joint_acceptance_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
