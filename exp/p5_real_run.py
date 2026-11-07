"""Real-model correctness regression, separate from throughput and promotion."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.http_transport import sha_ids
from controller.scoring import NativeClient
from controller.scored_forcing import calibrate_delta, calibrate_stock, judge_scored_forcing, load_score_trace, validate_injected_generation
from exp.p3_pair_run import arm_specs, check_ports, clean_environment, gpu_lock, interrupted, wait_for_idle, write_json
from exp.p5_api_probe import CorrectnessServer


def eligible_requests(requests, generated):
    return [request for request in requests
            if len(generated[request['id']]['output_ids']) == 2048
            and generated[request['id']].get('meta_info', {}).get('finish_reason', {}).get('type') == 'length']


def final_acceptance(verdicts, *, post2048_tokens):
    healthy = all(verdicts[name]['correctness_passed'] for name in
                  ('healthy_stock', 'healthy_ar', 'healthy_segmented', 'equivalent_head'))
    fault_rejected = verdicts['faulty']['event_flagged'] and not verdicts['faulty']['correctness_passed']
    ready = healthy and fault_rejected and post2048_tokens >= 1024
    author_passed = verdicts['author_final']['correctness_passed']
    return dict(judge_ready=ready, healthy_controls_passed=healthy, faulty_event_rejected=fault_rejected,
                post2048_tokens=post2048_tokens, injection_coverage_passed=post2048_tokens >= 1024,
                author_final_correctness_passed=author_passed, next_stage_allowed=ready and author_passed,
                promoted=False, ledger_eligible=False,
                scope='dev correctness readiness only; no sealed, throughput or autonomous discovery claim')


class Campaign:
    def __init__(self, directory, scorer):
        self.directory, self.scorer = directory, scorer

    def event(self, **value):
        with (self.directory / 'events.jsonl').open('a') as destination:
            destination.write(json.dumps(dict(time_unix=time.time(), **value)) + '\n')
            destination.flush()
            os.fsync(destination.fileno())
        print(json.dumps(value), flush=True)

    def save_trace(self, cohort, request, output, identity, segments):
        trace = self.scorer.score(request['input_ids'], output)
        trace.update(request_id=request['id'], generator=identity, generation_segments=segments)
        directory = self.directory / cohort
        directory.mkdir(exist_ok=True)
        path = directory / f'{request["id"]}.json'
        write_json(path, trace)
        load_score_trace(path, evidence_root=self.directory)
        self.event(cohort=cohort, request_id=request['id'], tokens=len(output), status='scored')
        return str(path)

    def generate(self, cohort, requests, client, identity, cap):
        paths, responses, segments = [], {}, {}
        for request in requests:
            response = client.post('/generate', dict(input_ids=request['input_ids'],
                sampling_params={'temperature': 0, 'top_k': 1, 'max_new_tokens': cap, 'ignore_eos': False}))
            segment = client.last_evidence
            paths.append(self.save_trace(cohort, request, response['output_ids'], identity, [segment]))
            responses[request['id']], segments[request['id']] = response, segment
        return paths, responses, segments

    def audit(self, cohort, paths, delta):
        directory = self.directory / f'{cohort}-audits'
        directory.mkdir()
        audits, examined, total = [], 0, 0
        for path in paths:
            trace = load_score_trace(path, evidence_root=self.directory)
            for score in trace['scores']:
                if score['token'] == score['argmax'] or score['margin'] <= 2 * delta:
                    continue
                total += 1
                if examined >= 200:
                    continue
                index = score['index']
                audit = self.scorer.score(trace['prompt_ids'] + trace['output_ids'][:index], [score['token']])
                audit.update(request_id=trace['request_id'])
                destination = directory / f'{examined:04d}.json'
                write_json(destination, audit)
                audits.append(str(destination))
                examined += 1
        write_json(directory / 'coverage.json', dict(large_margin_events=total, audited=examined,
            unaudited=total - examined, order='manifest then output position', maximum=200,
            scope='prefill-length audit only; no stock-path replay explanation implemented'))
        self.event(cohort=cohort, large_margin_events=total, audited=examined)
        return audits


def head_process(mode, directory, reference, tree_sha):
    command = [sys.executable, '-B', str(ROOT / 'controller/head_reference.py'), '--mode', mode,
               '--out-dir', str(directory), '--reference', str(reference / 'manifest.json'),
               '--url', 'http://127.0.0.1:30130', '--tree-sha', tree_sha, '--device', 'cuda:1']
    with directory.with_suffix('.log').open('x') as destination:
        subprocess.run(command, cwd=ROOT, stdout=destination, stderr=subprocess.STDOUT, check=True, timeout=1800)
    return json.loads((directory / 'result.json').read_text())


def launch(arm, role, gpu, directory, environment, resources):
    server = CorrectnessServer(dict(arm, name=role, role=role), gpu, 30130 if role == 'scorer' else 30120,
                               directory, environment)
    resources.callback(server.stop)
    server.start()
    server.wait_ready(900)
    return server


def run(directory, reference):
    environment = clean_environment()
    expected = os.environ['P5_EXPECTED_COMMIT']
    subprocess.run(['git', 'diff', '--exit-code', expected, '--', 'exp', 'harness', 'controller'], cwd=ROOT, check=True)
    signal.signal(signal.SIGTERM, interrupted)
    gpus = wait_for_idle([0, 1])
    check_ports([30120, 30130])
    arms, _ = arm_specs(['ar', 'stock', 'final'], environment)
    reference_manifest = reference / 'manifest.json'
    manifest = json.loads(reference_manifest.read_text())
    requests = manifest['requests']
    suites = {row['suite'] for row in requests}
    if (len(requests) != 20 or len(suites) != 5 or
            any(sum(row['suite'] == suite for row in requests) != 4 for suite in suites) or
            len({row['id'] for row in requests}) != 20 or
            any(sha_ids(row['input_ids']) != row['input_sha256'] for row in requests)):
        raise ValueError('expected the original twenty A1 requests, four per suite')
    sources = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
               for folder in ('controller', 'exp', 'harness') for path in (ROOT / folder).rglob('*')
               if path.is_file() and path.suffix in ('.py', '.sh') and '__pycache__' not in path.parts}
    write_json(directory / 'manifest.json', dict(source_pin=expected, source_sha256=sources, gpus=gpus,
        requests=requests, arms=arms, reference_manifest=str(reference_manifest),
        reference_manifest_sha256=hashlib.sha256(reference_manifest.read_bytes()).hexdigest(),
        generation_cap=2048, injection_tail_cap=2048, vocabulary_size=248320,
        injection_bias=2, injection_stride=7, minimum_post2048_tokens=1024,
        head_control='first request per suite, 64 cap, reverse 8-part FP32 reduction',
        event_audit_limit=200, scope='real dev correctness regression; not paired throughput or promotion'))
    cohorts = {}
    with ExitStack() as resources:
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        launch(arms[0], 'scorer', gpus[1], directory, environment, resources)
        scorer = NativeClient('http://127.0.0.1:30130', directory / 'scorer-raw')
        scorer.scorer_identity(arms[0]['tree_sha'])
        campaign = Campaign(directory, scorer)
        head_process('preflight', directory / 'head-preflight', reference, arms[0]['tree_sha'])
        campaign.event(stage='head_preflight', passed=True)
        with ExitStack() as generator_resources:
            launch(arms[0], 'ar', gpus[0], directory, environment, generator_resources)
            client = NativeClient('http://127.0.0.1:30120', directory / 'ar-raw')
            identity = client.server_identity(arms[0]['tree_sha'])
            cohorts['ar'], generated, segments = campaign.generate('ar', requests, client, identity, 2048)
            eligible = eligible_requests(requests, generated)
            write_json(directory / 'injection-selection.json', dict(eligible_ids=[row['id'] for row in eligible],
                selection='all AR requests with exactly 2048 generated tokens and length finish; frozen before faults'))
            if not eligible:
                raise ValueError('no actual AR request reached the registered injection boundary')
            for cohort, bias in (('healthy_segmented', None), ('faulty', {str(token): 2 for token in range(0, 248320, 7)})):
                paths = []
                for request in eligible:
                    prefix = generated[request['id']]['output_ids']
                    parameters = dict(temperature=0, top_k=1, max_new_tokens=2048, ignore_eos=False)
                    if bias is not None:
                        parameters['logit_bias'] = bias
                    response = client.post('/generate', dict(input_ids=request['input_ids'] + prefix,
                                                              sampling_params=parameters))
                    tail_segment = client.last_evidence
                    paths.append(campaign.save_trace(cohort, request, prefix + response['output_ids'], identity,
                                                     [segments[request['id']], tail_segment]))
                cohorts[cohort] = paths
        check_ports([30120])
        wait_for_idle([0])
        with ExitStack() as generator_resources:
            launch(arms[1], 'stock', gpus[0], directory, environment, generator_resources)
            client = NativeClient('http://127.0.0.1:30120', directory / 'stock-raw')
            identity = client.server_identity(arms[1]['tree_sha'])
            cohorts['stock'], _, _ = campaign.generate('stock', requests, client, identity, 2048)
            cohorts['healthy_stock'], _, _ = campaign.generate('healthy_stock', requests, client, identity, 2048)
            cohorts['stock_long'], _, _ = campaign.generate('stock_long', eligible, client, identity, 4096)
        check_ports([30120])
        wait_for_idle([0])
        delta = calibrate_delta(cohorts['stock'], cohorts['ar'], evidence_root=directory)
        write_json(directory / 'delta-calibration.json', delta)
        baseline = calibrate_stock(cohorts['stock'], delta, evidence_root=directory)
        long_baseline = calibrate_stock(cohorts['stock_long'], delta, evidence_root=directory)
        write_json(directory / 'stock-calibration.json', baseline)
        write_json(directory / 'long-stock-calibration.json', long_baseline)
        campaign.event(stage='stock_calibration', delta=delta['delta'], stock=baseline['stock_counts'])
        head = head_process('control', directory / 'head-control', reference, arms[0]['tree_sha'])
        cohorts['equivalent_head'] = head['traces']
        selected_ids = {json.loads(Path(path).read_text())['request_id'] for path in cohorts['equivalent_head']}
        head_baseline = calibrate_stock([path for path in cohorts['stock']
            if json.loads(Path(path).read_text())['request_id'] in selected_ids], delta, evidence_root=directory)
        write_json(directory / 'head-stock-calibration.json', head_baseline)
        with ExitStack() as generator_resources:
            launch(arms[2], 'final', gpus[0], directory, environment, generator_resources)
            client = NativeClient('http://127.0.0.1:30120', directory / 'final-raw')
            identity = client.server_identity(arms[2]['tree_sha'])
            cohorts['author_final'], _, _ = campaign.generate('author_final', requests, client, identity, 2048)
        check_ports([30120])
        wait_for_idle([0])
        cohorts['healthy_ar'] = cohorts['ar']
        write_json(directory / 'cohorts.json', cohorts)
        verdicts = {}
        for name in ('healthy_stock', 'healthy_ar', 'healthy_segmented', 'equivalent_head', 'faulty', 'author_final'):
            calibration = long_baseline if name in ('healthy_segmented', 'faulty') else head_baseline if name == 'equivalent_head' else baseline
            audits = campaign.audit(name, cohorts[name], delta['delta'])
            verdicts[name] = judge_scored_forcing(calibration, cohorts[name], evidence_root=directory, prefill_audits=audits)
            write_json(directory / f'{name}-verdict.json', verdicts[name])
            campaign.event(stage='judgment', cohort=name, passed=verdicts[name]['correctness_passed'],
                           rate=verdicts[name]['rate'], events=verdicts[name]['unexplained_events'])
        coverage = [validate_injected_generation(path, evidence_root=directory) for path in cohorts['faulty']]
        write_json(directory / 'injection-coverage.json', coverage)
        result = final_acceptance(verdicts, post2048_tokens=sum(row['post2048_tokens'] for row in coverage))
        write_json(directory / 'acceptance.json', result)
    check_ports([30120, 30130])
    write_json(directory / 'cleanup.json', wait_for_idle([0, 1]))
    if not result['judge_ready']:
        raise ValueError('real correctness judge regression failed; inspect acceptance and cohort verdicts')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    try:
        run(args.out_dir, args.reference)
    except BaseException as error:
        write_json(args.out_dir / 'failed.json', {'error': repr(error)})
        try:
            check_ports([30120, 30130])
            write_json(args.out_dir / 'failure-cleanup.json', wait_for_idle([0, 1]))
        except Exception as cleanup_error:
            write_json(args.out_dir / 'failure-cleanup-error.json', {'error': repr(cleanup_error)})
        raise


if __name__ == '__main__':
    main()
