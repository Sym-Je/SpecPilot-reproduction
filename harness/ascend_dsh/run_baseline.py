"""Queue on the existing NPU lock, switch only our server, run frozen dev cases."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import time

import psutil
import requests

from prepare_baseline import ROOT, OUT, sha, write, prepare
from audit_baseline import analyze

URL = 'http://127.0.0.1:8000'
HTTP = requests.Session()
HTTP.trust_env = False
STATE = {'status': 'queued_for_npu_lock', 'started_epoch': time.time(), 'rows': [],
         'runner': 'MRV1', 'validation_opened': False}


def save():
    write(OUT / 'baseline-state.json', STATE)


def metrics():
    for attempt in range(3):
        try:
            response = HTTP.get(URL + '/metrics', timeout=15)
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2: raise
            time.sleep(1)
    def total(name):
        return sum(float(l.split()[-1]) for l in response.text.splitlines()
                   if l.startswith(name + '{') or l.startswith(name + ' '))
    return {k: total(n) for k, n in {
        'running': 'vllm:num_requests_running', 'waiting': 'vllm:num_requests_waiting',
        'generated': 'vllm:generation_tokens_total', 'preemptions': 'vllm:num_preemptions_total',
        'prefix_hits': 'vllm:prefix_cache_hits_total'}.items()} | {'epoch': time.time()}


def identity(process):
    return {'pid': process.pid, 'birth': process.create_time()}


def stop_owned(owner):
    p = psutil.Process(owner['pid'])
    assert p.create_time() == owner['birth']
    children = p.children(recursive=True)
    known = [identity(q) for q in children] + [identity(p)]
    p.terminate()
    _, alive = psutil.wait_procs([p] + children, timeout=30)
    for process in alive:
        try:
            assert identity(process) in known
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(alive, timeout=15)
    for process in alive:
        try:
            assert identity(process) in known
            process.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(alive, timeout=10)
    assert not [p for p in alive if p.status() != psutil.STATUS_ZOMBIE]


def wait_health(owner, timeout=1800):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        p = psutil.Process(owner['pid'])
        assert p.create_time() == owner['birth'] and p.status() != psutil.STATUS_ZOMBIE
        try:
            if HTTP.get(URL + '/health', timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise TimeoutError('Service startup deadline')


def launch(script, directory):
    directory.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')
           and not any(s in k.lower() for s in ('api_key', 'claude_key', 'northgate_key'))}
    with (directory / 'server.log').open('xb') as log:
        p = subprocess.Popen(['/bin/bash', str(script)], cwd=ROOT, env=env,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
    owner = identity(psutil.Process(p.pid))
    write(directory / 'owner.json', owner)
    return owner


def main(reuse_current=False, recover_attempt=None, resume=False):
    if resume:
        previous = json.loads((OUT / 'baseline-state.json').read_text())
        assert previous['status'] == 'failed_attempt_retained'
        STATE['rows'] = previous['rows']
        STATE['resumed_after'] = previous['error']
    else:
        assert not (OUT / 'baseline-state.json').exists(), 'Refuse duplicate attempt'
    prepare(check=True)
    save()
    with (ROOT / 'evaluation/npu-workload.lock').open('a+') as lock:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('NPU queue deadline')))
        signal.alarm(6 * 3600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        signal.alarm(0)
        STATE.update(status='starting_mrv1', lock_acquired_epoch=time.time()); save()
        if resume:
            child = previous.get('aiperf_owner')
            if child:
                try: stop_owned(child)
                except psutil.NoSuchProcess: pass
            idle_deadline = time.monotonic() + 120
            while metrics()['running'] + metrics()['waiting']:
                if time.monotonic() > idle_deadline: raise TimeoutError('Cancelled requests did not drain')
                time.sleep(2)
        selection = json.loads((ROOT / 'deployment/selected/selection.json').read_text())
        if not recover_attempt:
            assert metrics()['running'] == metrics()['waiting'] == 0
        write(OUT / 'previous-selection.json', selection)
        if recover_attempt:
            assert selection['selected_mode'] == 'MRV1-fixed-DSpark-K7'
            old = {'pid': selection['owner_pid'], 'birth': selection['owner_create_time']}
            try: stop_owned(old)
            except psutil.NoSuchProcess: pass
            owner = launch(OUT / 'launch-mrv1.sh', OUT / ('service-' + recover_attempt))
            wait_health(owner)
        elif reuse_current:
            assert selection['selected_mode'] == 'MRV1-fixed-DSpark-K7'
            owner = {'pid': selection['owner_pid'], 'birth': selection['owner_create_time']}
            assert selection['scripts'][0]['sha256'] == sha(OUT / 'launch-mrv1.sh')
            wait_health(owner, timeout=30)
        else:
            assert selection['owner_pid'] == 1334844 and selection['owner_create_time'] == 1794221302.76
            old = {'pid': selection['owner_pid'], 'birth': selection['owner_create_time']}
            stop_owned(old)
            owner = launch(OUT / 'launch-mrv1.sh', OUT / 'service-mrv1')
            try:
                wait_health(owner)
            except BaseException:
                try:
                    stop_owned(owner)
                except psutil.NoSuchProcess:
                    pass
                restored = launch(Path(selection['scripts'][0]['path']), OUT / 'restore-mrv2')
                wait_health(restored)
                selection.update(owner_pid=restored['pid'], owner_create_time=restored['birth'])
                write(ROOT / 'deployment/selected/selection.json', selection)
                raise
        write(OUT / 'service-owner.json', owner)
        new_selection = dict(selection, status='ctrip_mrv1_baseline_running', owner_pid=owner['pid'],
                             owner_create_time=owner['birth'], selected_mode='MRV1-fixed-DSpark-K7',
                             runtime_current_state=str(OUT / 'baseline-state.json'),
                             scripts=[{'path': str(OUT / 'launch-mrv1.sh'), 'sha256': sha(OUT / 'launch-mrv1.sh')}])
        write(ROOT / 'deployment/selected/selection.json', new_selection)
        STATE.update(status='benchmarking', ready_epoch=time.time(), service_owner=owner); save()
        manifest = json.loads((OUT / 'baseline-input-manifest.json').read_text())
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
        env.update(PYTHONPATH=str(OUT / 'runtime'), TRANSFORMERS_OFFLINE='1', HF_HUB_OFFLINE='1',
                   VLLM_USE_MODELSCOPE='true', EXP241_NETWORK_LOG=str(OUT / 'benchmark-network-hosts.jsonl'))
        (OUT / 'baseline').mkdir(exist_ok=resume)
        for case in manifest['cases']:
            directory = OUT / 'baseline' / case['name']
            if resume and any(row['case'] == case['name'] for row in STATE['rows']):
                analyze(directory, case)
                continue
            if directory.exists():
                assert resume
                shutil.move(str(directory), str(OUT / (case['name'] + '-metrics-disconnect-' + str(time.time_ns()))))
            directory.mkdir()
            before = metrics(); assert before['running'] == before['waiting'] == 0
            write(directory / 'before.json', before)
            command = [str(ROOT / '.bench-venv/bin/aiperf'), 'profile', '--model', 'deepseek-v4-flash',
                       '--url', URL, '--endpoint-type', 'chat', '--streaming',
                       '--tokenizer', str(ROOT / 'models/DeepSeek-V4-Flash-0731-w8a8'),
                       '--input-file', case['input_path'], '--custom-dataset-type', 'inputs-json',
                       '--concurrency', str(case['concurrency']), '--request-count', str(case['request_count']),
                       '--warmup-request-count', str(case['warmups']), '--request-timeout-seconds', '1800',
                       '--random-seed', '20261109', '--use-server-token-count',
                       '--export-level', 'raw', '--export-outputs-json',
                       '--artifact-dir', str(directory / 'aiperf'), '--ui', 'none',
                       '--no-gpu-telemetry', '--no-server-metrics']
            write(directory / 'launch.json', {'argv': command, 'case': case, 'runner_source_sha256': sha(__file__)})
            STATE['current_case'] = case['name']; save(); print('START', case['name'], flush=True)
            with (directory / 'aiperf.log').open('xb') as log, (directory / 'server-activity.jsonl').open('w') as monitor:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, start_new_session=True)
                STATE['aiperf_owner'] = identity(psutil.Process(process.pid)); save()
                started = time.monotonic()
                while process.poll() is None:
                    if time.monotonic() - started > 5400:
                        os.killpg(process.pid, signal.SIGTERM)
                        raise TimeoutError('Cell deadline')
                    monitor.write(json.dumps(metrics()) + '\n'); monitor.flush(); time.sleep(5)
                assert process.returncode == 0, f'AIPerf exit {process.returncode}'
            after = metrics(); write(directory / 'after.json', after)
            row = analyze(directory, case)
            row.update(preemptions_including_warmup=after['preemptions'] - before['preemptions'],
                       prefix_hits_including_warmup=after['prefix_hits'] - before['prefix_hits'])
            write(directory / 'result.json', row)
            STATE['rows'].append(row); save(); print('RESULT', json.dumps(row), flush=True)
        STATE.update(status='complete', completed_epoch=time.time(), service_left_running=True); save()
        new_selection['status'] = 'ctrip_mrv1_baseline_complete'; write(ROOT / 'deployment/selected/selection.json', new_selection)
        print('BASELINE_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse-current', action='store_true')
    parser.add_argument('--recover-attempt')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        main(args.reuse_current, args.recover_attempt, args.resume)
    except BaseException as exc:
        STATE.update(status='failed_attempt_retained', error=repr(exc), failed_epoch=time.time()); save()
        raise
