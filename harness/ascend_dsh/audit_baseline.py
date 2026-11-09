"""Independent absolute performance audit; does not perform candidate promotion."""
import argparse
import collections
import json
from pathlib import Path

from prepare_baseline import OUT, sha, write


def percentile(values, q):
    v = sorted(values)
    return v[round((len(v) - 1) * q)] if v else None


def analyze(directory, case):
    artifact = directory / 'aiperf'
    records = [json.loads(l) for l in (artifact / 'profile_export.jsonl').open() if l.strip()]
    phases = json.loads((artifact / 'phase_manifest.json').read_text())['phases']
    phase, = [p for p in phases if p['phase_kind'] == 'profiling']
    assert phase['error_request_count'] == 0, phase
    assert phase['successful_request_count'] == case['request_count'], phase
    measured = [r for r in records if r['metadata']['phase_kind'] == 'profiling']
    assert len(measured) == case['request_count']
    assert collections.Counter(r['metadata']['conversation_id'] for r in measured) == collections.Counter(case['requests'].keys()), 'Request identity coverage mismatch'
    assert sha(case['input_path']) == case['input_sha256']
    permitted_lengths = {r['input_tokens'] for r in case['requests'].values()}
    starts, ends, inputs, outputs, latencies, ttfts, tpots, events = [], [], [], [], [], [], [], []
    for r in measured:
        meta, m = r['metadata'], r['metrics']
        inp, out = int(m['usage_prompt_tokens']['value']), int(m['usage_completion_tokens']['value'])
        assert inp in permitted_lengths, (inp, permitted_lengths)
        assert inp == case['requests'][meta['conversation_id']]['input_tokens'], 'Per-request prompt length mismatch'
        assert 0 < out <= 8192
        a, b = meta['request_start_ns'], meta['request_end_ns']
        assert b > a
        starts.append(a); ends.append(b); inputs.append(inp); outputs.append(out)
        ttft = m['time_to_first_token']['value'] / 1000
        latency = (b - a) / 1e9
        latencies.append(latency); ttfts.append(ttft)
        if out > 1:
            tpots.append(max(0, latency - ttft) / (out - 1) * 1000)
        events += [(a, 1), (b, -1)]
    active = peak = 0
    for _, delta in sorted(events):
        active += delta; peak = max(peak, active)
    assert active == 0
    assert peak == case['concurrency'], (peak, case['concurrency'])
    wall = (max(ends) - min(starts)) / 1e9
    return {'case': case['name'], 'stratum': case['stratum'], 'concurrency': case['concurrency'],
            'actual_client_peak': peak, 'requests': len(measured), 'errors': 0,
            'wall_seconds': wall, 'output_tokens': sum(outputs), 'input_tokens': sum(inputs),
            'e2e_output_tok_s': sum(outputs) / wall, 'logical_input_tok_s': sum(inputs) / wall,
            'input_token_min': min(inputs), 'input_token_max': max(inputs),
            'output_token_p50': percentile(outputs, .5), 'output_token_max': max(outputs),
            'output_cap_hits': outputs.count(8192),
            'ttft_p50_s': percentile(ttfts, .5), 'ttft_p90_s': percentile(ttfts, .9),
            'tpot_p50_ms': percentile(tpots, .5), 'latency_p50_s': percentile(latencies, .5),
            'directory': str(directory), 'scope': 'absolute serial baseline; no candidate promotion'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--completed-only', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((OUT / 'baseline-input-manifest.json').read_text())
    results = []
    for case in manifest['cases']:
        directory = OUT / 'baseline' / case['name']
        if args.completed_only and not (directory / 'result.json').exists():
            continue
        row = analyze(directory, case)
        assert row == {k: v for k, v in json.loads((directory / 'result.json').read_text()).items() if k in row}
        results.append(row)
    report = {'passed': True, 'cases': len(results), 'rows': results, 'validation_opened': False}
    write(OUT / 'baseline-independent-audit.json', report)
    print(json.dumps({'passed': True, 'cases': len(results), 'validation_opened': False}))
