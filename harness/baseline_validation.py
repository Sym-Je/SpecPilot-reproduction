import json
import math
from collections import Counter
from pathlib import Path

from controller.http_transport import sha_ids
from exp.p3_pair_run import SUITES, summarize


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def validate_paired_run(directory, names, expected_arms=None, reference_requests=None):
    directory = Path(directory)
    if (directory / 'failed.json').exists():
        raise ValueError('runner recorded a failure')
    manifest = json.loads((directory / 'manifest.json').read_text())
    expected = {'rounds': 2, 'per_suite': 4, 'max_new_tokens': 2048,
                'warmup': 2, 'suites': SUITES}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('unexpected baseline protocol')
    if manifest.get('sampling') != {'temperature': 0.0, 'top_k': 1, 'enable_thinking': True}:
        raise ValueError('unexpected sampling protocol')
    arms = manifest['arms']
    if len(names) != 2 or len(set(names)) != 2 or [arm['name'] for arm in arms] != names:
        raise ValueError('unexpected comparison arms')
    if expected_arms is not None and (len(expected_arms) != 2 or any(
            actual.get(field) != value for actual, expected_arm in zip(arms, expected_arms)
            for field, value in expected_arm.items())):
        raise ValueError('arm configuration or tree identity mismatch')
    requests = manifest['requests']
    if reference_requests is not None and requests != reference_requests:
        raise ValueError('requests differ from the frozen baseline')
    by_id = {request['id']: request for request in requests}
    if (len(requests) != 20 or len(by_id) != 20 or
            Counter(request['suite'] for request in requests) != Counter({suite: 4 for suite in SUITES})):
        raise ValueError('unexpected request coverage')
    if any(request['turn'] != 0 or not request['input_ids'] or
           sha_ids(request['input_ids']) != request['input_sha256'] for request in requests):
        raise ValueError('invalid request identity')
    all_pairs = []
    assignments = []
    arm_rows = {name: [] for name in names}
    for round_number in (1, 2):
        round_dir = directory / f'round-{round_number:02d}'
        complete = json.loads((round_dir / 'complete.json').read_text())
        if complete != {'round': round_number, 'pairs': 20}:
            raise ValueError('incomplete round')
        deployment = json.loads((round_dir / 'deployment.json').read_text())
        entries = deployment['assignments']
        mapping = {entry['arm']['name']: entry['gpu']['uuid'] for entry in entries}
        if len(entries) != 2 or set(mapping) != set(arm_rows) or len(set(mapping.values())) != 2:
            raise ValueError('invalid physical GPU assignment')
        assignments.append(mapping)
        pairs = read_rows(round_dir / 'pairs.jsonl')
        if len(pairs) != 20 or {pair['id'] for pair in pairs} != set(by_id):
            raise ValueError('missing or duplicate request/round coverage')
        for key, arm in zip(('a', 'b'), arms):
            name = arm['name']
            rows = read_rows(round_dir / f'{name}.jsonl')
            if rows != [pair[key] for pair in pairs]:
                raise ValueError('arm rows differ from canonical pairs')
            for pair, row in zip(pairs, rows):
                request = by_id[pair['id']]
                if pair['round'] != round_number or pair['suite'] != request['suite']:
                    raise ValueError('invalid pair identity')
                identity = {'id': request['id'], 'suite': request['suite'], 'turn': 0,
                            'round': round_number, 'arm': name, 'block': arm['block'],
                            'tree_sha': arm['tree_sha'], 'gpu_uuid': mapping[name],
                            'input_sha256': request['input_sha256'], 'max_new_tokens': 2048}
                if any(row.get(field) != value for field, value in identity.items()):
                    raise ValueError('arm/request/GPU identity mismatch')
                tokens = row['completion_tokens']
                if not (0 < tokens <= 2048 and row['tokens'] == tokens == len(row['output_ids'])):
                    raise ValueError('invalid token coverage')
                if sha_ids(row['output_ids']) != row['output_sha256']:
                    raise ValueError('invalid output hash')
                if not math.isfinite(row['tokens_per_s']) or row['tokens_per_s'] <= 0:
                    raise ValueError('invalid throughput')
            arm_rows[name].extend(rows)
        all_pairs.extend(pairs)
    if assignments[0] != {names[0]: assignments[1][names[1]], names[1]: assignments[1][names[0]]}:
        raise ValueError('physical GPUs were not exchanged')
    summary = json.loads((directory / 'summary.json').read_text())
    if (summary.get('arms') != names or summary.get('max_new_tokens') != 2048 or
            summary.get('per_suite_requested') != 4):
        raise ValueError('unexpected summary protocol')
    recalculated = summarize(all_pairs, requests, 2, summary['bootstrap_iters'])
    if any(summary.get(key) != value for key, value in recalculated.items()):
        raise ValueError('statistics differ from the existing controller implementation')
    lengths = {}
    for name, rows in arm_rows.items():
        counts = [row['completion_tokens'] for row in rows]
        lengths[name] = {'min': min(counts), 'max': max(counts),
                         'mean': sum(counts) / len(counts), 'at_cap': counts.count(2048),
                         'finish_reasons': dict(Counter(row['finish_reason'] for row in rows))}
    result = {'protocol_passed': True,
            'requests': 20, 'pairs': 40, 'arm_rows': 80, 'rounds': 2,
            'physical_gpu_swap': True, 'geomean': summary['geomean'],
            'ci95': [summary['lower'], summary['upper']],
            'actual_lengths': lengths,
            'ledger_eligible': False,
            'scope': 'paired dev-scale diagnostic; not sealed, lossless or promotion'}
    return result, manifest, summary


def validate_baseline(directory):
    result, manifest, summary = validate_paired_run(directory, ['ar', 'stock'])
    arms = manifest['arms']
    if ([arm['block'] for arm in arms] != [0, 8] or
            arms[0]['tree_sha'] != arms[1]['tree_sha'] or any(arm.get('env') for arm in arms)):
        raise ValueError('AR/stock must use the same stock tree without final options')
    diagnostic_passed = 3.95 * 0.9 <= summary['geomean'] <= 3.95 * 1.1
    if summary.get('acceptance') != {'target': 3.95, 'relative_tolerance': 0.10,
                                     'passed': diagnostic_passed}:
        raise ValueError('diagnostic reference was changed or misreported')
    result.update(diagnostic_passed=diagnostic_passed,
                  reference_interval=[3.95 * 0.9, 3.95 * 1.1],
                  scope='A1 dev-scale diagnostic; not sealed, lossless or promotion')
    return result
