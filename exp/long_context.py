"""Small frozen-author long-context comparison, not autonomous research or promotion."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import signal
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controller.http_transport import Arm, HttpPairBench, sha_ids
from controller.scored_forcing import calibrate_delta, calibrate_stock, judge_scored_forcing, read_reference
from controller.scoring import NativeClient, server_arguments
from controller.stats import stratified_geomean_ci
from exp.p3_pair_run import clean_environment, gpu_lock, interrupted, result_row, wait_for_idle
from exp.p5_real_run import Campaign, launch
from exp.sampling_run import SamplingServer, identity
from harness.engine_research import save
from harness.gpu_autonomy import digest

LENGTHS = (2048, 8192, 32768, 65536, 131072)
CAP = 2048
PROTOCOL = 'frozen-author-long-context-v1'


def condition_key(item):
    return str(item.get('condition', item['context_tokens']))


def condition_keys(requests):
    return list(dict.fromkeys(condition_key(item) for item in requests))


def validate_requests(requests):
    if len(requests) != 15 or len({item['id'] for item in requests}) != 15:
        raise ValueError('exactly fifteen unique frozen requests required')
    for length in LENGTHS:
        selected = [item for item in requests if item['context_tokens'] == length]
        if len(selected) != 3 or len({item['document'] for item in selected}) != 3:
            raise ValueError('three documents required at every length')
        for item in selected:
            if (len(item['input_ids']) != length or item['input_sha256'] != sha_ids(item['input_ids']) or
                    any(type(token) is not int or token < 0 for token in item['input_ids'])):
                raise ValueError('input length or identity differs')


def check_request(path, runtime=False):
    record = json.loads(Path(path).read_text())
    if record['protocol'] == 'author-dev-prefix-context-v1':
        from harness.prefix_context import validate
        validate(record)
    elif record['protocol'] == PROTOCOL:
        validate_requests(record['requests'])
    else:
        raise ValueError('unexpected long-context protocol')
    source = record['source_archive']
    if digest(source['path']) != source['sha256']:
        raise ValueError('source archive changed')
    with tarfile.open(source['path']) as archive:
        for name, checksum in source['files'].items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest() != checksum:
                raise ValueError('source member changed')
            if runtime and digest(ROOT / name) != checksum:
                raise ValueError('runtime differs from frozen source')
    for document in record['documents']:
        if digest(document['path']) != document['sha256']:
            raise ValueError('public document changed after freeze')
    return record


class ContextArm(Arm):
    def __init__(self, *arguments, generator, **options):
        super().__init__(*arguments, **options)
        self.generator = generator

    def step(self, *arguments, **options):
        return dict(super().step(*arguments, **options), generator=self.generator)


def measure(record, directory, gpus):
    environment = clean_environment()
    for number in (0, 1):
        root = directory / f'round-{number + 1:02d}'
        root.mkdir()
        assigned = gpus if number == 0 else list(reversed(gpus))
        save(root / 'deployment.json', dict(round=number + 1, assignments=[
            dict(arm=arm, gpu=gpu, port=30700 + index * 10)
            for index, (arm, gpu) in enumerate(zip(record['arms'], assigned))]))
        statuses = []
        with ExitStack() as resources:
            servers = []
            for index, (arm, gpu) in enumerate(zip(record['arms'], assigned)):
                server = SamplingServer(arm, gpu, 30700 + index * 10, root, environment)
                resources.callback(server.stop)
                server.start()
                servers.append(server)
            for server in servers:
                server.wait_ready(1200)
            clients, probes = [], []
            for server, arm in zip(servers, record['arms']):
                native = NativeClient(f'http://127.0.0.1:{server.port}', root / f'{arm["name"]}-identity')
                generator = identity(native, arm)
                probes.append(native)
                client = ContextArm(arm['name'], native.url, generator=generator, block_size=arm['block'],
                    tree_sha=arm['tree_sha'], env=arm['env'], trace_timing=True, raw_dir=root / f'{arm["name"]}-raw')
                client.begin_session()
                clients.append(client)
            bench = HttpPairBench(*clients, synchronized_start=True, reverse_submission=bool(number))
            with (root / 'pairs.jsonl').open('x') as destination:
                for condition in condition_keys(record['requests']):
                    requests = [item for item in record['requests'] if condition_key(item) == condition]
                    status = dict(condition=condition, context_tokens=requests[0]['context_tokens'], pairs=0, preflight=[])
                    for native in probes:
                        try:
                            response = native.post('/generate', dict(input_ids=requests[0]['input_ids'],
                                sampling_params=dict(temperature=0., top_k=1, max_new_tokens=32)))
                            if response['meta_info']['prompt_tokens'] != requests[0]['context_tokens']:
                                raise ValueError('server truncated the requested context')
                            status['preflight'].append(dict(ok=True, evidence=native.last_evidence))
                        except Exception as error:
                            status['preflight'].append(dict(ok=False, error=str(error), evidence=native.last_evidence))
                    if all(probe['ok'] for probe in status['preflight']):
                        for item in requests:
                            try:
                                result = bench.run_pair(item['input_ids'], CAP, warmup=0, swap=False,
                                    rid=f'round-{number + 1}|{item["id"]}')['rounds'][0]
                                pair = dict(id=item['id'], round=number + 1, context_tokens=item['context_tokens'],
                                    **{key: result_row(result[key], item, arm, gpu, number, CAP)
                                       for key, arm, gpu in zip(('a', 'b'), record['arms'], assigned)})
                                if 'condition' in item:
                                    pair['condition'] = item['condition']
                                destination.write(json.dumps(pair, allow_nan=False) + '\n')
                                destination.flush()
                                status['pairs'] += 1
                                print(json.dumps(dict(event='pair', round=number + 1, id=item['id'],
                                    stock_tps=pair['a']['tokens_per_s'], final_tps=pair['b']['tokens_per_s'])), flush=True)
                            except Exception as error:
                                status['error'] = str(error)
                                break
                    statuses.append(status)
                    save(root / 'status.json', statuses)
                    print(json.dumps(dict(event='length-complete', round=number + 1, **status)), flush=True)
                    if any(server.process.poll() is not None for server in servers):
                        break
        save(root / 'cleanup.json', wait_for_idle([0, 1]))
        save(root / 'complete.json', dict(round=number + 1, pairs=sum(row['pairs'] for row in statuses)))


def read_pairs(directory):
    return [json.loads(line) for number in (1, 2)
            for line in (directory / f'round-{number:02d}' / 'pairs.jsonl').read_text().splitlines()]


def correctness(record, directory, gpus):
    from exp.p3_pair_run import arm_specs
    environment = clean_environment()
    arm = arm_specs(['ar'], environment)[0][0]
    root = directory / 'correctness'
    root.mkdir()
    pairs = read_pairs(directory)
    reports = {}
    with ExitStack() as resources:
        servers = []
        for role, gpu in zip(('ar', 'scorer'), gpus):
            location = root / role
            location.mkdir()
            servers.append(launch(arm, role, gpu, location, environment, resources))
        scorer = NativeClient('http://127.0.0.1:30130', root / 'scorer-raw')
        scorer.scorer_identity(arm['tree_sha'])
        generator = NativeClient('http://127.0.0.1:30120', root / 'ar-raw')
        ar_identity = generator.server_identity(arm['tree_sha'])
        for condition in condition_keys(record['requests']):
            selected = [pair for pair in pairs if condition_key(pair) == condition]
            requests = [item for item in record['requests'] if condition_key(item) == condition]
            if len(selected) != 2 * len(requests):
                reports[condition] = dict(status='incomplete-performance')
                save(root / 'summary.json', reports)
                continue
            location = root / f'ctx-{condition}'
            location.mkdir()
            bench = Campaign(location, scorer, evidence_root=directory)
            try:
                ar_paths, _, _ = bench.generate('ar', requests, generator, ar_identity, CAP)
                rounds = []
                for number in (1, 2):
                    traces = {}
                    for key, role in (('a', 'stock'), ('b', 'final')):
                        traces[role] = [bench.save_trace(f'{role}-round-{number}', item,
                            next(pair for pair in selected if pair['round'] == number and pair['id'] == item['id'])[key]['output_ids'],
                            next(pair for pair in selected if pair['round'] == number and pair['id'] == item['id'])[key]['generator'],
                            [next(pair for pair in selected if pair['round'] == number and pair['id'] == item['id'])[key]['raw_evidence']])
                            for item in requests]
                    delta = calibrate_delta(traces['stock'], ar_paths, evidence_root=directory)
                    baseline = calibrate_stock(traces['stock'], delta, evidence_root=directory)
                    audits = bench.audit(f'final-round-{number}', traces['final'], delta['delta'])
                    verdict = judge_scored_forcing(baseline, traces['final'], evidence_root=directory, prefill_audits=audits)
                    save(location / f'round-{number}-calibration.json', dict(delta=delta, baseline=baseline))
                    save(location / f'round-{number}-verdict.json', verdict)
                    rounds.append(verdict)
                reports[condition] = dict(status='checked', correctness_passed=all(row['correctness_passed'] for row in rounds))
            except Exception as error:
                reports[condition] = dict(status='unavailable', error=str(error))
            save(root / 'summary.json', reports)
            print(json.dumps(dict(event='correctness', condition=condition, **reports[condition])), flush=True)
            if any(server.process.poll() is not None for server in servers):
                break
    save(root / 'cleanup.json', wait_for_idle([0, 1]))


def summarize(pairs, requests, gpus, evidence_root=None):
    indexed = {item['id']: item for item in requests}
    seen = set()
    for pair in pairs:
        item = indexed[pair['id']]
        key = pair['round'], pair['id']
        if (key in seen or pair['round'] not in (1, 2) or pair['context_tokens'] != item['context_tokens'] or
                condition_key(pair) != condition_key(item)):
            raise ValueError('duplicate, invalid round or context drift')
        seen.add(key)
        assigned = gpus if pair['round'] == 1 else list(reversed(gpus))
        for key, role, gpu in zip(('a', 'b'), ('stock', 'final'), assigned):
            row = pair[key]
            if (row['gpu_uuid'] != gpu['uuid'] or row['arm'] != role or row['input_sha256'] != item['input_sha256'] or
                    row['output_sha256'] != sha_ids(row['output_ids']) or row['tokens'] != len(row['output_ids']) or
                    not 0 < row['tokens'] <= CAP or not math.isfinite(row['tokens_per_s']) or row['tokens_per_s'] <= 0):
                raise ValueError('measurement identity, output or GPU swap differs')
            if evidence_root is not None:
                raw = read_reference(row['raw_evidence'], evidence_root)
                if (raw['http_status'] != 200 or raw['request']['input_ids'] != item['input_ids'] or
                        raw['request']['sampling_params'] != dict(temperature=0., top_k=1, max_new_tokens=CAP) or
                        raw['response']['output_ids'] != row['output_ids'] or
                        raw['response']['meta_info']['prompt_tokens'] != item['context_tokens'] or
                        raw['response']['meta_info']['completion_tokens'] != row['tokens']):
                    raise ValueError('raw request/response differs or input was truncated')
                timing = row['client_timing']
                elapsed = (timing['step_end_ns'] - timing['step_start_ns']) / 1e9
                if abs(row['latency_ms'] / 1000 - elapsed) > .02 or not math.isclose(
                        row['tokens_per_s'], row['tokens'] / (row['latency_ms'] / 1000), rel_tol=1e-9):
                    raise ValueError('throughput does not match recorded timing')
    conditions = {}
    for condition in condition_keys(requests):
        selected = [pair for pair in pairs if condition_key(pair) == condition]
        cohort = [item for item in requests if condition_key(item) == condition]
        expected = {(number, item['id']) for number in (1, 2) for item in cohort}
        complete = {(pair['round'], pair['id']) for pair in selected} == expected
        result = dict(complete=complete, pairs=len(selected), requests=len(cohort))
        if complete:
            groups = defaultdict(list)
            for item in requests:
                if condition_key(item) == condition:
                    cluster = [pair for pair in selected if pair['id'] == item['id']]
                    groups[item['suite']].append(sum(math.log(pair['b']['tokens_per_s'] / pair['a']['tokens_per_s'])
                        for pair in cluster) / 2)
            result['speedup'] = stratified_geomean_ci(dict(groups))
            result['identical_output_pairs'] = sum(pair['a']['output_ids'] == pair['b']['output_ids'] for pair in selected)
            for key, role in (('a', 'stock'), ('b', 'final')):
                rows = [pair[key] for pair in selected]
                result[role] = dict(mean_tokens=sum(row['tokens'] for row in rows) / len(rows),
                    mean_latency_s=sum(row['latency_ms'] / 1000 for row in rows) / len(rows),
                    geomean_tps=math.exp(sum(math.log(row['tokens_per_s']) for row in rows) / len(rows)),
                    cap_count=sum(row['finish_reason'] == 'length' for row in rows))
            result['round_speedups'] = {str(number): math.exp(sum(math.log(pair['b']['tokens_per_s'] / pair['a']['tokens_per_s'])
                for pair in selected if pair['round'] == number) / len(cohort)) for number in (1, 2)}
        conditions[condition] = result
    prefixed = any('condition' in item for item in requests)
    return dict(protocol='author-dev-prefix-context-v1' if prefixed else PROTOCOL, conditions=conditions, ledger_eligible=False,
        metric='final/stock output tokens per complete request wall second; includes prefill and HTTP, not decode-only',
        scope=('exploratory ten-public-task irrelevant-prefix control; not sealed, RSI or losslessness proof' if prefixed else
            'exploratory three-public-novel sample; not all long-context tasks, sealed, RSI or losslessness proof'))


def audit(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if digest(manifest['request_path']) != manifest['request_sha256']:
        raise ValueError('request freeze changed')
    record = check_request(manifest['request_path'])
    for number in (1, 2):
        root = directory / f'round-{number:02d}'
        deployment = json.loads((root / 'deployment.json').read_text())
        assigned = manifest['gpus'] if number == 1 else list(reversed(manifest['gpus']))
        if deployment['assignments'] != [dict(arm=arm, gpu=gpu, port=30700 + index * 10)
                for index, (arm, gpu) in enumerate(zip(record['arms'], assigned))]:
            raise ValueError('deployment differs from frozen arms and physical swap')
        if not (root / 'complete.json').is_file() or not (root / 'cleanup.json').is_file():
            raise ValueError('round lifecycle is incomplete')
    pairs = read_pairs(directory)
    for pair in pairs:
        for key, arm in zip(('a', 'b'), record['arms']):
            row = pair[key]
            actual = server_arguments(read_reference(row['generator']['evidence'], directory)['response'])
            if (row['tree_sha'] != arm['tree_sha'] or row['generator']['tree_sha'] != arm['tree_sha'] or
                    actual.get('speculative_algorithm') != 'DFLASH' or actual.get('speculative_num_draft_tokens') != arm['block']):
                raise ValueError('author engine identity changed')
    result = summarize(pairs, record['requests'], manifest['gpus'], directory)
    correctness_root = directory / 'correctness'
    summary = json.loads((correctness_root / 'summary.json').read_text())
    for length, condition in result['conditions'].items():
        condition['correctness'] = summary.get(length, dict(status='unavailable'))
        if condition['correctness']['status'] == 'checked':
            for number in (1, 2):
                location = correctness_root / f'ctx-{length}'
                calibration = json.loads((location / f'round-{number}-calibration.json').read_text())
                expected = json.loads((location / f'round-{number}-verdict.json').read_text())
                recomputed = judge_scored_forcing(calibration['baseline'],
                    [source['path'] for source in expected['candidate_sources']], evidence_root=directory,
                    prefill_audits=sorted(str(path) for path in (location / f'final-round-{number}-audits').glob('[0-9]*.json')))
                if recomputed != expected:
                    raise ValueError('independent controller correctness replay differs')
    return result


def run(request, directory):
    record = check_request(request, runtime=True)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    signal.signal(signal.SIGTERM, interrupted)
    with ExitStack() as resources:
        gpus = wait_for_idle([0, 1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        save(directory / 'manifest.json', dict(request_path=str(request), request_sha256=digest(request), gpus=gpus,
            started_unix=time.time()))
        measure(record, directory, gpus)
        try:
            correctness(record, directory, gpus)
        except Exception as error:
            root = directory / 'correctness'
            root.mkdir(exist_ok=True)
            save(root / 'summary.json', {condition: dict(status='unavailable', error=str(error))
                for condition in condition_keys(record['requests'])})
        save(directory / 'cleanup.json', wait_for_idle([0, 1]))
    result = audit(directory)
    save(directory / 'result.json', result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'audit'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'run':
        run(args.request, args.directory)
    else:
        print(json.dumps(audit(args.directory)))


if __name__ == '__main__':
    main()
