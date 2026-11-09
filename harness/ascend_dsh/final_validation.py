"""One final held-out serial validation after research stops and candidate freezes.

Not the repository's protected paper controller or paired promotion machinery.
No model calls, no feedback into research, and no quality certificate.
"""
import argparse
import copy
import fcntl
import json
import hashlib
from pathlib import Path
import time

from prepare_baseline import ROOT, OUT, DATA, BUCKETS, bucket, write, sha
from experiment_runner import validate_config, make_launch, run_screen
from run_baseline import metrics, launch, wait_health, stop_owned


def deployment_config(config):
    validate_config(config)
    return {k: v for k, v in config.items() if k != 'screen_concurrency'}


def freeze_candidate(research, root=OUT):
    assert research['status'] == 'research_finished', 'Research must be stopped before freeze'
    assert research['validation_opened'] is False
    candidate = research['master_decision'].get('candidate')
    configuration = None
    identity = None
    if candidate is not None:
        experiment_id = candidate['experiment_id']
        allowed = []
        for role in research['rounds']:
            broker = json.loads((root / 'research/roles' / role['role'] / 'broker-state.json').read_text())
            allowed += broker['experiments']
        assert experiment_id in allowed, 'Candidate must belong to this campaign'
        directory = root / 'experiments' / experiment_id
        result = json.loads((directory / 'state.json').read_text())
        request = json.loads((directory / 'request.json').read_text())
        assert result['status'] == 'complete' and result['baseline_restored'] is True
        assert request['mode'] == 'benchmark' and request['split'] == 'dev'
        assert result.get('comparison'), 'Completed measured comparison required'
        configuration = deployment_config(candidate['config'])
        assert configuration == deployment_config(request['config']), 'Cannot validate an unmeasured variant'
        identity = {'experiment_id': experiment_id, 'request_sha256': sha(directory / 'request.json'),
                    'result_sha256': sha(directory / 'state.json')}
    freeze = {'frozen_epoch': time.time(), 'config': configuration, 'source_experiment': identity,
              'validation_opened': False, 'research_stopped': True,
              'no_more_llm_calls': True, 'protocol': 'C1=2 per input bin; C8=all40; C32=32 per bin; natural EOS/high/8192',
              'final_runner_sha256': sha(__file__), 'baseline_launch_sha256': sha(root / 'launch-mrv1.sh')}
    path = root / 'candidate-freeze.json'
    assert not path.exists(), 'One freeze only'
    write(path, freeze)
    return freeze


def make_cases(rows, directory):
    assert len(rows) == len({r['id'] for r in rows}) == len({r['metadata']['group_id'] for r in rows}) == 40
    directory.mkdir(exist_ok=False)
    cases = []
    for label in BUCKETS:
        source = sorted((r for r in rows if bucket(r['metadata']['input_tokens']) == label), key=lambda r: r['id'])
        assert len(source) in (13, 14)
        for concurrency in (1, 8, 32):
            selected = [source[0], source[-1]] if concurrency == 1 else source if concurrency == 8 else [source[i % len(source)] for i in range(32)]
            entries, expected = [], {}
            for index, row in enumerate(selected):
                payload = copy.deepcopy(row['request'])
                if not payload.get('tools'): payload.pop('tools', None)
                assert payload['max_tokens'] == 8192 and payload['reasoning_effort'] == 'high'
                assert payload['temperature'] == 0 and not payload.get('ignore_eos', False)
                session_id = row['id'] + '-v' + str(index)
                entries.append({'session_id': session_id, 'payloads': [payload]})
                expected[session_id] = {'source_id': row['id'], 'input_tokens': row['metadata']['input_tokens']}
            name = f'{label}-c{concurrency}'; path = directory / (name + '.json')
            write(path, {'data': entries})
            cases.append({'name': name, 'stratum': label, 'concurrency': concurrency,
                          'request_count': len(entries), 'warmups': 1, 'requests': expected,
                          'input_path': str(path), 'input_sha256': sha(path)})
    assert sum(c['request_count'] for c in cases) == 142
    return cases


def open_validation(freeze, directory):
    # Guard is checked before ANY held-out file operation.
    assert freeze['research_stopped'] is True and freeze['validation_opened'] is False
    assert freeze['final_runner_sha256'] == sha(__file__)
    assert freeze['baseline_launch_sha256'] == sha(OUT / 'launch-mrv1.sh')
    manifest = json.loads((DATA.parent / 'manifest.json').read_text())
    path = DATA.parent / 'validation/requests.jsonl'
    assert sha(path) == manifest['validation/requests.jsonl']['sha256']
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    cases = make_cases(rows, directory / 'inputs')
    write(directory / 'manifest.json', {'split': 'validation', 'source_sha256': sha(path),
                                       'candidate_freeze_sha256': sha(OUT / 'candidate-freeze.json'), 'cases': cases})
    return cases



def output_agreement(directory, cases):
    rows = []
    for case in cases:
        c = case['concurrency']; name = case['name']
        arms = []
        for arm in ('baseline', 'candidate'):
            records = json.loads((directory / arm / f'c{c}' / name / 'aiperf/outputs.json').read_text())['data']
            values = {r['conversation_id']: hashlib.sha256(r['response_text'].encode()).hexdigest() for r in records}
            assert set(values) == set(case['requests']) and len(values) == len(records)
            arms.append(values)
        same = sum(arms[0][key] == arms[1][key] for key in arms[0])
        rows.append({'case': name, 'requests': len(arms[0]), 'exact_text_matches': same,
                     'exact_text_match_fraction': same / len(arms[0])})
    return {'rows': rows, 'scope': 'Surface text agreement only; may omit reasoning/tool fields. No task correctness or losslessness claim.'}


def run(research):
    freeze = freeze_candidate(research)
    directory = OUT / 'final-validation'; directory.mkdir(exist_ok=False)
    state = {'status': 'queued', 'validation_opened': False, 'candidate_freeze_sha256': sha(OUT / 'candidate-freeze.json'),
             'scope': 'Independent held-out serial validation; not formal paired promotion', 'arms': {}}
    def save(): write(directory / 'state.json', state)
    save()
    with (ROOT / 'evaluation/npu-workload.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        selection = json.loads((ROOT / 'deployment/selected/selection.json').read_text())
        assert selection['selected_mode'] == 'MRV1-fixed-DSpark-K7'
        baseline = {'pid': selection['owner_pid'], 'birth': selection['owner_create_time']}
        candidate = None
        stopped = False
        try:
            cases = open_validation(freeze, directory)
            state.update(status='running', validation_opened=True, opened_epoch=time.time()); save()
            for arm in ('baseline', 'candidate'):
                if arm == 'candidate':
                    if freeze['config'] is None: break
                    assert metrics()['running'] == metrics()['waiting'] == 0
                    script = make_launch(freeze['config'], directory)
                    stop_owned(baseline); stopped = True
                    candidate = launch(script, directory / 'candidate-service'); wait_health(candidate)
                state['active_arm'] = arm; state['arms'][arm] = []; save()
                arm_dir = directory / arm; arm_dir.mkdir()
                for concurrency in (1, 8, 32):
                    state['active_concurrency'] = concurrency; save()
                    rows = run_screen(arm_dir / f'c{concurrency}', concurrency,
                                      prepared_cases=[c for c in cases if c['concurrency'] == concurrency])
                    for row in rows: row['scope'] = state['scope']
                    state['arms'][arm] += rows; save()
            if 'candidate' in state['arms']:
                state['output_agreement'] = output_agreement(directory, cases)
                state['comparison'] = [{'case': a['case'], 'output_tok_s_ratio': b['e2e_output_tok_s'] / a['e2e_output_tok_s'],
                    'tpot_ratio': a['tpot_p50_ms'] / b['tpot_p50_ms'] if b['tpot_p50_ms'] else None,
                    'reference_output_tokens': a['output_tokens'], 'candidate_output_tokens': b['output_tokens'],
                    'reference_cap_hits': a['output_cap_hits'], 'candidate_cap_hits': b['output_cap_hits']}
                    for a, b in zip(state['arms']['baseline'], state['arms']['candidate'])]
            state.update(status='complete', completed_epoch=time.time(),
                         correctness='Not certified: static agent replay and output comparison do not establish semantic accuracy or losslessness.')
            save()
        except BaseException as exc:
            state.update(status='failed', error=f'{type(exc).__name__}: {exc}'); save(); raise
        finally:
            if candidate is not None:
                try: stop_owned(candidate)
                except Exception as exc: state['candidate_cleanup_error'] = str(exc)
            if not stopped and state['status'] == 'failed':
                try: stop_owned(baseline)
                except Exception as exc: state['baseline_cleanup_error'] = str(exc)
                stopped = True
            if stopped:
                try:
                    restored = launch(OUT / 'launch-mrv1.sh', directory / 'restored-baseline')
                    wait_health(restored)
                    selection.update(owner_pid=restored['pid'], owner_create_time=restored['birth'])
                    write(ROOT / 'deployment/selected/selection.json', selection)
                    state['baseline_restored'] = True
                except BaseException as exc:
                    state.update(status='failed', baseline_restored=False, restore_error=f'{type(exc).__name__}: {exc}')
                    save(); raise
            state['service_left_running'] = True; save()
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--research-state', required=True)
    args = parser.parse_args()
    run(json.loads(Path(args.research_state).read_text()))
