"""Trusted serial NPU execution for DSH proposals; stock source is never edited."""
import argparse
import copy
import csv
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time
import shutil

from prepare_baseline import ROOT, OUT, write, sha
from audit_baseline import analyze
from activity_watchdog import wait_aiperf
from run_baseline import HTTP, URL, metrics, launch, wait_health, stop_owned

BOOL_ADDITIONAL = {
    'enable_cpu_binding', 'multistream_dsv4_dsa_overlap', 'multistream_engram_overlap',
    'enable_prefill_mc2', 'multistream_overlap_shared_expert', 'enable_mc2_hierarchy_comm',
    'enable_shared_expert_dp', 'enable_mlapo', 'mlapo_keep_prefill_weights', 'enable_flashcomm1',
}
COMPILE_BOOLS = {'enable_npugraph_ex', 'enable_static_kernel', 'fuse_norm_quant', 'fuse_qknorm_rope', 'fuse_muls_add'}


def validate_config(config):
    if not isinstance(config, dict): raise ValueError('Config object required')
    limits = {'max_num_batched_tokens': (1024, 32768), 'max_num_seqs': (1, 32), 'num_speculative_tokens': (0, 12)}
    allowed = set(limits) | {'gpu_memory_utilization', 'enable_prefix_caching', 'enforce_eager', 'additional_config', 'screen_concurrency', 'profile_stratum', 'profile_phase', 'profile_steps', 'cpu_work_metadata'}
    if set(config) - allowed: raise ValueError('Unsupported deployment field')
    for k, v in config.items():
        if k in limits:
            if type(v) is not int or not limits[k][0] <= v <= limits[k][1]: raise ValueError('Integer field outside bounds')
        elif k == 'screen_concurrency':
            if type(v) is not int or v not in (1, 8, 32): raise ValueError('Screen concurrency must be 1, 8, or 32')
        elif k == 'profile_stratum':
            if v not in ('short', 'mid', 'long'): raise ValueError('Unknown dev input stratum')
        elif k == 'profile_phase':
            if v not in ('prefill', 'decode'): raise ValueError('Unknown profile phase')
        elif k == 'profile_steps':
            if type(v) is not int or not 1 <= v <= 32: raise ValueError('Profile steps outside bounds')
        elif k == 'gpu_memory_utilization':
            if type(v) not in (float, int) or not .8 <= v <= .94: raise ValueError('Memory utilization outside bounds')
        elif k in ('enable_prefix_caching', 'enforce_eager', 'cpu_work_metadata'):
            if type(v) is not bool: raise ValueError('Boolean required')
        elif k == 'additional_config':
            if not isinstance(v, dict): raise ValueError('Additional config object required')
            for name, value in v.items():
                if name in BOOL_ADDITIONAL:
                    if type(value) is not bool: raise ValueError('Additional boolean required')
                elif name == 'ascend_compilation_config':
                    if not isinstance(value, dict) or set(value) - COMPILE_BOOLS or any(type(x) is not bool for x in value.values()):
                        raise ValueError('Unsupported compilation config')
                else: raise ValueError('Unsupported additional field')


def make_launch(config, directory, profile=False):
    validate_config(config)
    if config.get('cpu_work_metadata') and (not profile or config.get('profile_steps') != 2
            or config.get('profile_phase') != 'prefill' or config.get('profile_stratum') != 'long'):
        raise ValueError('CPU metadata diagnostic requires explicit long/prefill/two-step profile')
    text = (OUT / 'launch-mrv1.sh').read_text()
    lines = text.splitlines()
    command = shlex.split(next(l[5:] for l in lines if l.startswith('exec ')))
    def option(flag, value):
        if flag in command:
            i = command.index(flag); del command[i:i + 2]
        command.extend([flag, str(value)])
    for name in ('max_num_batched_tokens', 'max_num_seqs', 'gpu_memory_utilization'):
        if name in config: option('--' + name.replace('_', '-'), config[name])
    if 'enable_prefix_caching' in config:
        command[:] = [x for x in command if x not in ('--enable-prefix-caching', '--no-enable-prefix-caching')]
        command.append('--enable-prefix-caching' if config['enable_prefix_caching'] else '--no-enable-prefix-caching')
    if config.get('enforce_eager'): command.append('--enforce-eager')
    if 'num_speculative_tokens' in config:
        i = command.index('--speculative-config'); del command[i:i + 2]
        if config['num_speculative_tokens']:
            option('--speculative-config', json.dumps({'method': 'dspark', 'num_speculative_tokens': config['num_speculative_tokens'], 'enable_adaptive_verification': False}))
    if 'additional_config' in config:
        i = command.index('--additional-config'); additional = json.loads(command[i + 1])
        for k, v in config['additional_config'].items():
            if isinstance(v, dict): additional.setdefault(k, {}).update(v)
            else: additional[k] = v
        option('--additional-config', json.dumps(additional))
    if profile:
        option('--profiler-config', json.dumps({'profiler': 'torch', 'torch_profiler_dir': str(directory / 'traces'),
               'torch_profiler_with_stack': False, 'torch_profiler_record_shapes': False,
               'torch_profiler_with_memory': False, 'ignore_frontend': True,
               'max_iterations': config.get('profile_steps', 8)}))
    path = directory / 'launch.sh'
    prefix='\n'.join(l for l in lines if not l.startswith('exec '))
    if config.get('cpu_work_metadata'):
        runtime=directory/'diagnostic-runtime';runtime.mkdir()
        (runtime/'sparse_work_diag.py').write_bytes((OUT/'sparse_work_diag.py').read_bytes())
        (runtime/'sitecustomize.py').write_text((OUT/'runtime/sitecustomize.py').read_text()
            +'\nfrom sparse_work_diag import install as install_sparse_work_diag\ninstall_sparse_work_diag()\n')
        prefix+='\nexport SPARSE_WORK_DIAG_ENABLE=1\nexport SPARSE_WORK_DIAG_DIR='+shlex.quote(str(directory/'work-metadata'))
        prefix+='\nexport PYTHONPATH='+shlex.quote(str(runtime))+':"${PYTHONPATH:-}"'
    path.write_text(prefix + '\nexec ' + shlex.join(command) + '\n')
    return path


def quick_cases(concurrency):
    original = json.loads((OUT / 'baseline-input-manifest.json').read_text())['cases']
    return [c for c in original if c['concurrency'] == concurrency]


def run_screen(directory, concurrency, prepared_cases=None):
    directory.mkdir(exist_ok=True)
    rows = []
    for original in (quick_cases(concurrency) if prepared_cases is None else prepared_cases):
        case = copy.deepcopy(original)
        data = json.loads(Path(case['input_path']).read_text())
        if prepared_cases is None:
            count = {1: 2, 8: 8, 32: 32}[concurrency]
            if concurrency == 1: data['data'] = [data['data'][0], data['data'][2]]
            else: data['data'] = data['data'][:count]
        else:
            count = len(data['data'])
            assert count == case['request_count']
        d = directory / case['name']; d.mkdir()
        path = d / 'inputs.json'; write(path, data)
        keys = {r['session_id'] for r in data['data']}
        case.update(input_path=str(path), input_sha256=sha(path), request_count=count, warmups=1,
                    requests={k: v for k, v in case['requests'].items() if k in keys})
        write(d / 'case.json', case)
        before = metrics(); write(d / 'before.json', before)
        assert before['running'] == before['waiting'] == 0
        command = [str(ROOT / '.bench-venv/bin/aiperf'), 'profile', '--model', 'deepseek-v4-flash',
                   '--url', URL, '--endpoint-type', 'chat', '--streaming',
                   '--tokenizer', str(ROOT / 'models/DeepSeek-V4-Flash-0731-w8a8'),
                   '--input-file', str(path), '--custom-dataset-type', 'inputs-json',
                   '--concurrency', str(concurrency), '--request-count', str(count),
                   '--warmup-request-count', '1', '--request-timeout-seconds', '1800',
                   '--random-seed', '20261109', '--use-server-token-count',
                   '--export-level', 'raw', '--export-outputs-json',
                   '--artifact-dir', str(d / 'aiperf'), '--ui', 'none', '--no-gpu-telemetry', '--no-server-metrics']
        write(d / 'launch.json', {'argv': command})
        environment = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
        environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                           PYTHONPATH=str(OUT / 'runtime'), EXP241_NETWORK_LOG=str(d / 'network.jsonl'))
        process = None
        try:
            with (d / 'aiperf.log').open('xb') as log:
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                code = wait_aiperf(process, d, metrics)
            assert code == 0, f'AIPerf exit {code}'
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
        row = analyze(d, case)
        after = metrics(); write(d / 'after.json', after)
        row.update(preemptions_including_warmup=after['preemptions'] - before['preemptions'],
                   prefix_hits_including_warmup=after['prefix_hits'] - before['prefix_hits'])
        write(d / 'result.json', row); rows.append(row)
    return rows


def profile_request(directory):
    case = next(c for c in quick_cases(1) if c['stratum'] == 'mid')
    request = copy.deepcopy(json.loads(Path(case['input_path']).read_text())['data'][0]['payloads'][0])
    request['stream'] = False; request.pop('stream_options', None); request['max_tokens'] = 128
    write(directory / 'profile-request.json', request)
    HTTP.post(URL + '/start_profile', timeout=60).raise_for_status()
    try:
        response = HTTP.post(URL + '/v1/chat/completions', json=request, timeout=600)
        response.raise_for_status(); write(directory / 'profile-response.json', response.json())
    finally:
        HTTP.post(URL + '/stop_profile', timeout=600).raise_for_status()
    summaries = []
    for file in sorted((directory / 'traces').rglob('kernel_details.csv')):
        with file.open(newline='') as f:
            reader = csv.DictReader(f); fields = reader.fieldnames or []
            duration = next((k for k in fields if k.replace(' ', '').lower() == 'duration(us)'), None)
            if not duration: continue
            totals = {}
            for row in reader:
                name = row.get('Name', row.get('name', 'unknown'))
                try: value = float(row[duration])
                except (ValueError, TypeError): continue
                entry = totals.setdefault(name, {'name': name, 'calls': 0, 'duration_us': 0.0})
                entry['calls'] += 1; entry['duration_us'] += value
            summaries.append({'file': str(file.relative_to(directory)), 'columns': fields,
                              'top_kernels': sorted(totals.values(), key=lambda r: r['duration_us'], reverse=True)[:20]})
    result = {'diagnostic_only': True, 'output_cap': 128, 'rank_kernel_summaries': summaries,
              'warning': 'Summed kernel durations can overlap; do not treat them as end-to-end latency or theoretical headroom.',
              'csv_files': [{'path': str(p.relative_to(directory / 'traces')), 'bytes': p.stat().st_size} for p in sorted((directory / 'traces').rglob('*.csv'))],
              'trace_file_count': sum(1 for p in (directory / 'traces').rglob('*') if p.is_file())}
    write(directory / 'profile-summary.json', result)
    return result


def run(experiment_id):
    if not re.fullmatch(r'[a-z0-9-]{1,145}', experiment_id): raise ValueError('Invalid ID')
    directory = OUT / 'experiments' / experiment_id
    request = json.loads((directory / 'request.json').read_text())
    assert request['split'] == 'dev'
    assert request['source_sha256'] == sha(__file__), 'Execution source changed after submission'
    validate_config(request['config'])
    assert all(sha(OUT / name) == expected for name, expected in request['execution_pins'].items()), 'Queued dependency changed'
    assert sha(OUT / 'installed-engine-source-manifest.json') == request['installed_engine_manifest_sha256']
    state = {'id': experiment_id, 'status': 'queued', 'created_epoch': time.time(), 'request': request,
             'screening_only': True, 'validation_opened': False}
    def save(): write(directory / 'state.json', state)
    save()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError('Experiment cancellation')))
    with (ROOT / 'evaluation/npu-workload.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert all(sha(OUT / name) == expected for name, expected in request['execution_pins'].items()), 'Dependency changed while waiting for NPU'
        from research_broker import SOURCE_ROOTS
        for name, expected in json.loads((OUT / 'installed-engine-source-manifest.json').read_text()).items():
            tree, relative = name.split('/', 1)
            assert sha(SOURCE_ROOTS[tree] / relative) == expected, 'Installed engine changed: ' + name
        assert json.loads((OUT / 'baseline-state.json').read_text())['status'] == 'complete'
        selection = json.loads((ROOT / 'deployment/selected/selection.json').read_text())
        assert selection['selected_mode'] == 'MRV1-fixed-DSpark-K7'
        owner = {'pid': selection['owner_pid'], 'birth': selection['owner_create_time']}
        candidate = None
        stopped_baseline = False
        try:
            state.update(status='running', lock_acquired_epoch=time.time()); save()
            assert shutil.disk_usage(OUT).free > 8 * 1024**3, 'Need at least 8 GiB free for bounded traces and restoration logs'
            concurrency = request['config'].get('screen_concurrency', 8)
            if request['mode'] == 'benchmark':
                state['phase'] = 'reference'; save()
                state['reference'] = run_screen(directory / 'reference', concurrency); save()
            assert metrics()['running'] == metrics()['waiting'] == 0
            script = make_launch(request['config'], directory, profile=request['mode'] == 'profile')
            stop_owned(owner); stopped_baseline = True
            candidate = launch(script, directory / 'candidate-service')
            state.update(phase='candidate_startup', candidate_owner=candidate); save()
            wait_health(candidate)
            state['phase'] = request['mode']; save()
            if request['mode'] == 'profile':
                from profile_workload import profile_request as concurrent_profile_request
                state['profile'] = concurrent_profile_request(directory, request['config'])
                if request['config'].get('cpu_work_metadata'):
                    from sparse_work_export import export_observations
                    state['profile']['cpu_work_metadata']=export_observations(directory)
            else:
                state['candidate'] = run_screen(directory / 'candidate', concurrency)
                state['comparison'] = [{'case': a['case'], 'output_tok_s_ratio': b['e2e_output_tok_s'] / a['e2e_output_tok_s'],
                    'tpot_ratio': a['tpot_p50_ms'] / b['tpot_p50_ms'] if b['tpot_p50_ms'] else None,
                    'reference_output_tokens': a['output_tokens'], 'candidate_output_tokens': b['output_tokens'],
                    'reference_cap_hits': a['output_cap_hits'], 'candidate_cap_hits': b['output_cap_hits']}
                    for a, b in zip(state['reference'], state['candidate'])]
            state['measurement_finished_epoch'] = time.time()
        except BaseException as exc:
            state.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            save()
            raise
        finally:
            if candidate is not None:
                try: stop_owned(candidate)
                except Exception as exc: state['candidate_cleanup_error'] = str(exc)
            if not stopped_baseline and state['status'] == 'failed':
                try:
                    stop_owned(owner)
                except Exception as exc:
                    state['reference_cleanup_error'] = str(exc)
                stopped_baseline = True
            if stopped_baseline:
                try:
                    restored = launch(OUT / 'launch-mrv1.sh', directory / 'restored-baseline')
                    wait_health(restored)
                    selection.update(owner_pid=restored['pid'], owner_create_time=restored['birth'])
                    write(ROOT / 'deployment/selected/selection.json', selection)
                    state['baseline_restored'] = True
                except BaseException as exc:
                    state.update(status='failed', restore_error=f'{type(exc).__name__}: {exc}', baseline_restored=False)
                    save()
                    raise
            if state['status'] != 'failed': state['status'] = 'complete'
            state['completed_epoch'] = time.time(); save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--id', required=True)
    arguments = parser.parse_args()
    try:
        run(arguments.id)
    except BaseException as exc:
        if re.fullmatch(r'[a-z0-9-]{1,145}', arguments.id):
            path = OUT / 'experiments' / arguments.id / 'state.json'
            if path.parent.is_dir():
                state = json.loads(path.read_text()) if path.exists() else {'id': arguments.id}
                if state.get('status') != 'failed':
                    state.update(status='failed', error=f'{type(exc).__name__}: {exc}', failed_epoch=time.time())
                    write(path, state)
        raise
