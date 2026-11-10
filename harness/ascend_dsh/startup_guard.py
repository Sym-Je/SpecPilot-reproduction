"""Fail fast on a confirmed owned candidate startup fault; no model calls."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time

import psutil

from prepare_baseline import OUT, write, sha

FROZEN_PROFILE_SOURCE = '15f4bd2492ca800ff37fdb334908d299db42f01614ee8683b119a984ecb8ef6c'


def fatal_graph_failure(text):
    if 'NPUGraph: ERROR' not in text or 'NPUModelRunner init failed' not in text:
        return None
    lines = [line[:500] for line in text.splitlines() if any(s in line for s in (
        'NPUGraph: ERROR', 'NPUModelRunner init failed', 'current working operator name', 'ERR00100'))]
    return {'reason': 'Confirmed NPUGraph capture failure and worker initialization failure',
            'error_excerpt': lines[-8:]}


def eligible_state(state):
    return (state.get('status') == 'running' and state.get('phase') == 'candidate_startup'
            and bool(state.get('lock_acquired_epoch')) and not state.get('completed_epoch')
            and isinstance(state.get('candidate_owner'), dict))


def valid_runner(argv, birth, created, experiment_id, root=OUT):
    expected_script = str(root / 'experiment_runner.py')
    if expected_script not in argv or '--id' not in argv: return False
    index = argv.index('--id')
    return index + 1 < len(argv) and argv[index + 1] == experiment_id and abs(birth - created) < 15


def profile_contract(request, root=OUT):
    if request.get('mode') != 'profile' or sha(root / 'experiment_runner.py') != FROZEN_PROFILE_SOURCE:
        return None
    return {'source_sha256': FROZEN_PROFILE_SOURCE, 'function': 'profile_request',
            'actual_concurrency': 1, 'actual_input_stratum': 'mid', 'actual_request_count': 1,
            'actual_max_output_tokens': 128,
            'requested_screen_concurrency': request.get('config', {}).get('screen_concurrency'),
            'screen_concurrency_controls_benchmark_only': True,
            'trace_generated': False,
            'scope_warning': 'This frozen profiling implementation cannot produce a C32 or long-input workload. Do not label its traces as those workloads.'}


def inspect(folder, root=OUT):
    if folder.is_symlink() or not re.fullmatch(r'[a-z0-9-]{1,145}', folder.name): return None
    state = json.loads((folder / 'state.json').read_text())
    if not eligible_state(state) or (folder / 'startup-failure-intervention.json').exists(): return None
    path = folder / 'candidate-service/server.log'
    if not path.is_file() or path.is_symlink() or path.parent.is_symlink(): return None
    with path.open('rb') as f:
        size = f.seek(0, 2); f.seek(max(0, size - 128 * 1024)); tail = f.read()
    diagnosis = fatal_graph_failure(tail.decode(errors='replace'))
    if not diagnosis: return None
    submitted = json.loads((folder / 'submission.json').read_text())
    process = psutil.Process(submitted['pid'])
    if not valid_runner(process.cmdline(), process.create_time(), submitted['created_epoch'], folder.name, root):
        raise RuntimeError('Runner identity mismatch; no cancellation')
    candidate = psutil.Process(state['candidate_owner']['pid'])
    if candidate.create_time() != state['candidate_owner']['birth']:
        raise RuntimeError('Candidate PID reused; no cancellation')
    if process.pid not in [p.pid for p in candidate.parents()]:
        raise RuntimeError('Candidate is not owned by this runner')
    request = json.loads((folder / 'request.json').read_text())
    result = {'epoch': time.time(), 'experiment_id': folder.name, 'runner_pid': process.pid,
              'runner_birth': process.create_time(), 'candidate_owner': state['candidate_owner'],
              'log_tail_sha256': hashlib.sha256(tail).hexdigest(), 'log_bytes': size,
              'log_tail_bytes': len(tail), 'action': 'SIGTERM trusted runner; existing finally restores baseline',
              'scientific_source_or_config_changed': False, **diagnosis}
    contract = profile_contract(request, root)
    if contract: result['profile_workload_audit'] = contract
    return result


def scan(root=OUT, dry_run=False):
    outcomes = []
    for path in sorted((root / 'experiments').glob('*/state.json')):
        folder = path.parent
        try:
            result = inspect(folder, root)
            if result is None: continue
            if dry_run:
                outcomes.append(dict(result, dry_run=True)); continue
            # Recheck state and PID identity immediately before the signal.
            if not eligible_state(json.loads(path.read_text())): continue
            process = psutil.Process(result['runner_pid'])
            assert process.create_time() == result['runner_birth'], 'Runner PID reused'
            record = folder / 'startup-failure-intervention.json'
            with record.open('x') as f:
                json.dump(result, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
            process.send_signal(signal.SIGTERM)
            outcomes.append({'experiment_id': folder.name, 'runner_pid': process.pid, 'signal_sent': True})
        except (psutil.NoSuchProcess, FileExistsError):
            continue
        except Exception as exc:
            outcomes.append({'experiment_id': folder.name, 'error': f'{type(exc).__name__}: {exc}', 'signal_sent': False})
    return outcomes


def watch():
    directory = OUT / 'startup-guard'; directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / 'mutex').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write(directory / 'state.json', {'status': 'running', 'pid': os.getpid(), 'started_epoch': time.time()})
        while True:
            results = scan()
            if results:
                with (directory / 'events.jsonl').open('a') as f:
                    f.write(json.dumps({'epoch': time.time(), 'results': results}) + '\n'); f.flush(); os.fsync(f.fileno())
            state = json.loads((OUT / 'research/state.json').read_text())
            if state.get('campaign_status') == 'complete':
                write(directory / 'state.json', {'status': 'campaign_complete', 'completed_epoch': time.time()}); return
            time.sleep(5)


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser(); p.add_argument('action', choices=('dry-run', 'watch'))
    args = p.parse_args()
    print(json.dumps(scan(dry_run=True))) if args.action == 'dry-run' else watch()
