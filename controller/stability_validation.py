"""Strict evidence checks for the predeclared four-round stable-null protocol."""

import json
import math
from pathlib import Path

from controller.null_validation import validate_null
from controller.http_transport import sha_ids
from harness.baseline_validation import read_rows


def validate_stable(directory, reference_requests=None):
    directory = Path(directory)
    result = validate_null(directory, rounds=4)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('stable_null') is not True:
        raise ValueError('stable-null protocol not declared')
    if reference_requests is not None and manifest['requests'] != reference_requests:
        raise ValueError('stable-null inputs differ from frozen A1 requests')
    ports = manifest['ports']
    if len(ports) != 2 or ports[0] == ports[1]:
        raise ValueError('invalid stable-null base ports')
    process_sessions = []
    trace_skews = []
    monitoring = []
    for number in range(1, 5):
        root = directory / f'round-{number:02d}'
        deployment = json.loads((root / 'deployment.json').read_text())
        assignments = deployment['assignments']
        assigned_ports = ports if number <= 2 else list(reversed(ports))
        if [entry['port'] for entry in assignments] != assigned_ports:
            raise ValueError('ports were not crossed independently of physical GPU assignments')
        pairs = read_rows(root / 'pairs.jsonl')
        events = {row['event']: row['time_unix'] for row in read_rows(root / 'events.jsonl')}
        warmup = read_rows(root / 'warmup.jsonl')
        phases = ['short'] * 2 + ['full'] * 20
        expected_ids = [request['id'] for request in manifest['requests'][:2] + manifest['requests']]
        if [row.get('phase') for row in warmup] != phases or [row['id'] for row in warmup] != expected_ids:
            raise ValueError('missing, adaptive or incorrect full-pass warmup')
        measured = {pair['id']: pair for pair in pairs}
        for row, phase in zip(warmup, phases):
            for key, assignment in zip(('a', 'b'), assignments):
                sample = row[key]
                expected_cap = 32 if phase == 'short' else 2048
                if (sample['max_new_tokens'] != expected_cap or
                        sample['gpu_uuid'] != assignment['gpu']['uuid'] or
                        sample['arm'] != assignment['arm']['name'] or
                        sample['tree_sha'] != assignment['arm']['tree_sha'] or sample['block'] != 8 or
                        sha_ids(sample['output_ids']) != sample['output_sha256'] or
                        not 0 < sample['tokens'] == len(sample['output_ids']) <= expected_cap):
                    raise ValueError('invalid warmup execution identity or token coverage')
                started = sample.get('client_timing', {}).get('started_unix', math.nan)
                if not events['servers_ready'] <= started <= events['warmup_complete']:
                    raise ValueError('warmup did not execute before primary measurement')
                if (sample['input_sha256'] != measured[row['id']][key]['input_sha256'] or
                        (phase == 'full' and sample['output_sha256'] != measured[row['id']][key]['output_sha256'])):
                    raise ValueError('warmup did not replay the actual measured path')
        for pair in pairs:
            for key, port in zip(('a', 'b'), assigned_ports):
                sample = pair[key]
                timing = sample.get('client_timing', {})
                fields = ('step_start_ns', 'http_open_start_ns', 'body_complete_ns', 'step_end_ns')
                if any(type(timing.get(field)) is not int for field in fields):
                    raise ValueError('missing HTTP timing evidence')
                values = [timing[field] for field in fields]
                if values != sorted(values) or values[-1] <= values[0]:
                    raise ValueError('invalid HTTP timing order')
                if timing.get('url') != f'http://127.0.0.1:{port}/generate':
                    raise ValueError('request trace endpoint differs from deployment')
                if abs((values[-1] - values[0]) / 1e9 - sample['latency_s']) > .005:
                    raise ValueError('timing trace does not enclose the primary measurement')
            trace_skews.append(abs(pair['a']['client_timing']['http_open_start_ns'] -
                                   pair['b']['client_timing']['http_open_start_ns']) / 1e6)
        if not events['servers_started'] <= events['servers_ready'] <= events['warmup_complete'] <= pairs[0]['started_unix']:
            raise ValueError('warmup/readiness ordering is invalid')
        samples = read_rows(root / 'telemetry.jsonl')
        during = [sample for sample in samples if pairs[0]['started_unix'] <= sample['time_unix'] <= pairs[-1]['finished_unix']]
        if len(during) < 2 or any('error' in sample for sample in samples):
            raise ValueError('missing or failed telemetry coverage')
        gpu_ids = {entry['gpu']['uuid'] for entry in assignments}
        for sample in during:
            if {gpu['uuid'] for gpu in sample.get('gpus', [])} != gpu_ids:
                raise ValueError('telemetry GPU identity mismatch')
            for gpu in sample['gpus']:
                for field in ('clocks_sm_mhz', 'clocks_mem_mhz', 'temperature_c', 'power_w'):
                    if not math.isfinite(gpu.get(field, math.nan)) or gpu[field] <= 0:
                        raise ValueError('missing GPU state metrics')
            for arm in ('stock-a', 'stock-b'):
                if not sample.get('arms', {}).get(arm) or not all(process.get('allowed_cpus') for process in sample['arms'][arm]):
                    raise ValueError('missing owned server CPU affinity evidence')
        process_sessions.append(tuple((arm, during[0]['arms'][arm][0]['pid'],
                                       during[0]['arms'][arm][0]['start_ticks']) for arm in ('stock-a', 'stock-b')))
        monitoring.append({'round': number, 'measurement_samples': len(during)})
    if len(set(process_sessions)) != 4:
        raise ValueError('fresh server process identity not demonstrated')
    centered = result['interval']['lower'] <= 1 <= result['interval']['upper']
    result.update(stable_protocol_passed=True, centered=centered,
                  stable_passed=result['precision_passed'] and centered,
                  full_warmup_pairs=80, monitoring=monitoring,
                  maximum_http_open_skew_ms=max(trace_skews),
                  scope='predeclared stable null only; not correctness, promotion or sealed')
    return result
