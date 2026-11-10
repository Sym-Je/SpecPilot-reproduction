"""Trusted development-only concurrent profiling and bounded offline export."""
import concurrent.futures
import copy
import csv
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import time

import requests

from prepare_baseline import OUT, ROOT, sha, write


def select_requests(config, manifest=None):
    concurrency = config.get('screen_concurrency', 1)
    stratum = config.get('profile_stratum', 'mid')
    manifest = manifest or json.loads((OUT / 'baseline-input-manifest.json').read_text())
    case = next(c for c in manifest['cases'] if c['concurrency'] == concurrency and c['stratum'] == stratum)
    path = Path(case['input_path'])
    assert sha(path) == case['input_sha256'], 'Frozen dev input changed'
    entries = copy.deepcopy(json.loads(path.read_text())['data'][:concurrency])
    assert len(entries) == concurrency
    for entry in entries:
        payload = entry['payloads'][0]
        payload.update(stream=True, stream_options={'include_usage': True}, max_tokens=128)
    return case, entries


def export_quality(directory, service_log=None):
    traces = directory / 'traces'
    ranks = sorted(traces.glob('*_ascend_pt'))
    exported = []
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
    for line in (directory / 'launch.sh').read_text().splitlines():
        if line.startswith('export '):
            parts = shlex.split(line[7:])
            if len(parts) == 1 and '=' in parts[0]:
                key, value = parts[0].split('=', 1)
                env[key] = value
    env['TORCH_DEVICE_BACKEND_AUTOLOAD'] = '0'
    for rank in ranks:
        log = directory / ('export-' + rank.name + '.log')
        if not list(rank.rglob('kernel_details.csv')):
            command = [str(ROOT / '.venv/bin/python'), '-c',
                       'import sys; from torch_npu.profiler.profiler import analyse; analyse(sys.argv[1], max_process_number=1, export_type="text")', str(rank)]
            with log.open('w') as output:
                subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT,
                               timeout=300, check=False)
        csvs = list(rank.rglob('kernel_details.csv'))
        timelines = list(rank.rglob('trace_view.json'))
        totals = {}
        for file in csvs:
            with file.open(newline='') as stream:
                reader = csv.DictReader(stream)
                duration = next((c for c in reader.fieldnames or [] if c.replace(' ', '').lower() == 'duration(us)'), None)
                if duration is None:
                    continue
                for row in reader:
                    try:
                        value = float(row[duration])
                    except (ValueError, TypeError):
                        continue
                    name = row.get('Name', row.get('name', 'unknown'))
                    entry = totals.setdefault(name, {'name': name, 'calls': 0, 'duration_us': 0})
                    entry['calls'] += 1
                    entry['duration_us'] += value
        exported.append({'rank': rank.name, 'kernel_csv': [str(p.relative_to(traces)) for p in csvs],
                         'timeline': [str(p.relative_to(traces)) for p in timelines],
                         'top_kernels': sorted(totals.values(), key=lambda x: x['duration_us'], reverse=True)[:20]})
    warnings = []
    logs = list(directory.glob('export-*.log')) + ([service_log] if service_log and service_log.exists() else [])
    for log in logs:
        for line in log.read_text(errors='replace').splitlines():
            if re.search(r'data.{0,30}(loss|lost|missing)|TLV|failed to (parse|export)|analysis.{0,20}fail', line, re.I):
                warnings.append({'file': log.name, 'line': line[:500]})
    complete = len(ranks) == 8 and all(r['kernel_csv'] and r['timeline'] for r in exported) and not warnings
    result = {'all_eight_ranks_complete': complete, 'rank_count': len(ranks), 'warnings': warnings[:50],
              'rank_kernel_summaries': exported,
              'csv_files': [{'path': str(p.relative_to(traces)), 'bytes': p.stat().st_size} for p in traces.rglob('*.csv')],
              'trace_file_count': sum(p.is_file() for p in traces.rglob('*')),
              'scope': 'Bounded diagnostic window. Summed durations overlap; not unprofiled latency or an end-to-end speedup.'}
    write(directory / 'profile-quality.json', result)
    return result


def profile_request(directory, config):
    from run_baseline import HTTP, URL, metrics
    case, entries = select_requests(config)
    phase = config.get('profile_phase', 'prefill')
    write(directory / 'profile-inputs.json', {'data': entries})
    write(directory / 'profile-workload.json', {'split': 'dev', 'stratum': case['stratum'],
          'concurrency': len(entries), 'request_count': len(entries), 'output_cap': 128,
          'phase_requested': phase, 'max_worker_iterations': config.get('profile_steps', 8),
          'source_input_sha256': case['input_sha256'], 'request_ids': [x['session_id'] for x in entries],
          'diagnostic_only': True, 'sampling_unchanged_except_output_cap': True})
    warmup = copy.deepcopy(entries[0]['payloads'][0])
    warmup.update(stream=False, max_tokens=16)
    warmup.pop('stream_options', None)
    response = HTTP.post(URL + '/v1/chat/completions', json=warmup, timeout=600)
    response.raise_for_status()
    barrier = threading.Barrier(len(entries))
    lock = threading.Lock()
    progress = {'submitted': 0, 'first_tokens': 0, 'completed': 0}

    def request(entry):
        client = requests.Session()
        client.trust_env = False
        barrier.wait(timeout=30)
        start = time.monotonic()
        with lock:
            progress['submitted'] += 1
        first = None
        usage = None
        with client.post(URL + '/v1/chat/completions', json=entry['payloads'][0], stream=True, timeout=(15, 900)) as response:
            response.raise_for_status()
            for raw in response.iter_lines():
                if not raw.startswith(b'data: ') or raw == b'data: [DONE]':
                    continue
                event = json.loads(raw[6:])
                if event.get('usage'):
                    usage = event['usage']
                choices = event.get('choices', [])
                delta = choices[0].get('delta', {}) if choices else {}
                if first is None and any(delta.get(k) for k in ('content', 'reasoning', 'reasoning_content', 'tool_calls')):
                    first = time.monotonic() - start
                    with lock:
                        progress['first_tokens'] += 1
        with lock:
            progress['completed'] += 1
        return {'id': entry['session_id'], 'ttft_s': first, 'wall_s': time.monotonic() - start, 'usage': usage}

    active = False
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(entries)) as pool:
        try:
            if phase == 'prefill':
                HTTP.post(URL + '/start_profile', timeout=120).raise_for_status()
                active = True
            jobs = [pool.submit(request, entry) for entry in entries]
            deadline = time.monotonic() + 900
            with (directory / 'profile-activity.jsonl').open('w') as log:
                while not all(job.done() for job in jobs):
                    with lock:
                        current = dict(progress)
                    sample = metrics() | current
                    log.write(json.dumps(sample) + '\n')
                    log.flush()
                    if phase == 'decode' and not active and current['first_tokens'] == len(entries):
                        HTTP.post(URL + '/start_profile', timeout=120).raise_for_status()
                        active = True
                        write(directory / 'profile-start-activity.json', sample)
                    if time.monotonic() > deadline:
                        raise TimeoutError('Profile request deadline')
                    time.sleep(0.5)
            rows = [job.result() for job in jobs]
        finally:
            if active:
                HTTP.post(URL + '/stop_profile', timeout=600).raise_for_status()
    write(directory / 'profile-responses.json', rows)
    if not active:
        raise RuntimeError('Requested decode window never existed; no profile claimed')
    quality = export_quality(directory, directory / 'candidate-service/server.log')
    quality.update(diagnostic_only=True, workload={'stratum': case['stratum'], 'concurrency': len(entries),
                   'phase': phase, 'output_cap': 128})
    write(directory / 'profile-summary.json', quality)
    return quality
