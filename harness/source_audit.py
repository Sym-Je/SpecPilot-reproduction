"""Read-only provenance and resource audit for a closed source-option stage."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tarfile

from harness.engine_research import json_record
from harness.gpu_autonomy import job_rows, response_object
from harness.source_candidate import file_sha
from exp.source_resource import LIMITS, feedback as replay_feedback


def load(path):
    return json.loads(Path(path).read_text())


def audit(root):
    root = Path(root)
    state = load(root / 'resource-state.json')
    if any(state[key] != value for key, value in LIMITS.items()):
        raise ValueError('source resource ceilings changed')
    if any(not row.get('terminated') or row.get('create_calls') != 1 for row in state['jobs']):
        raise ValueError('source task is active or submission is uncertain')
    charged = sum(row['charged_gpu_seconds'] for row in state['jobs'])
    if charged > LIMITS['gpu_seconds']:
        raise ValueError('source GPU ceiling exceeded')
    native_turns, tool_actions, cpu_runs, usage_updates = 0, 0, 0, 0
    role_results = []
    cpu_origins = {}
    role_responses = {}
    for role in [root / 'master', *sorted(root.glob('direction-*'))]:
        if not role.is_dir():
            continue
        manifest = load(role / 'manifest.json')
        for path, key in ((manifest['canary'], 'canary_sha256'),
                (Path(manifest['work']) / 'inputs/rules.txt', 'rules_sha256'),
                (Path(manifest['work']) / 'inputs/evidence.json', 'evidence_sha256'),
                (Path(manifest['home']) / 'config.toml', 'config_sha256')):
            if file_sha(path) != manifest[key]:
                raise ValueError('source role input/canary changed')
        wire = [json.loads(line) for line in (role / 'wire.jsonl').read_text().splitlines()]
        usage_updates += sum(row['message'].get('method') == 'thread/tokenUsage/updated' for row in wire)
        authored = {}
        for request_path in sorted(role.glob('tools-*/action-*/request.json')):
            request = load(request_path)
            calls = [row['message'] for row in wire if row['message'].get('method') == 'item/tool/call' and
                row['message'].get('params') == request]
            if len(calls) != 1:
                raise ValueError('source action has no unique native tool call')
            response = load(request_path.parent / 'response.json')
            if not any(row['direction'] == 'client' and row['message'].get('id') == calls[0]['id'] and
                    row['message'].get('result') == response for row in wire):
                raise ValueError('source tool feedback differs from the native stream')
            action = request['arguments']['action']
            if action['kind'] == 'write_file' and response['success']:
                authored[action['path']] = hashlib.sha256(action['content'].encode()).hexdigest()
            execution = request_path.parent / 'execution'
            if action['kind'] == 'run_python' and (execution / 'result.json').exists():
                record = load(execution / 'result.json')
                if record['code_sha256'] != authored.get(action['path']):
                    raise ValueError('CPU code is not bound to actual direction authorship')
                for stream in ('stdout', 'stderr'):
                    if file_sha(execution / stream) != record['output_sha256'][stream]:
                        raise ValueError('source CPU output changed')
                if not record['landlock_applied'] or not record['seccomp_applied'] or record['gpu_submissions'] != 0:
                    raise ValueError('source CPU isolation missing')
                returned = json.loads(response['contentItems'][0]['text'])
                cpu_origins[str(request_path.parent / 'response.json')] = returned
                authored.update(returned.get('workspace_file_sha256', {}))
                cpu_runs += 1
            tool_actions += 1
        for path in sorted(role.glob('turn-*-native.json')):
            native = load(path)
            texts = [row['message']['params']['item']['text'] for row in wire
                if row['message'].get('method') == 'item/completed' and
                row['message']['params'].get('item', {}).get('type') == 'agentMessage' and
                row['message']['params'].get('turnId') == native['turn']['id']]
            if (native['turn']['status'] != 'completed' or native['texts'] != texts or
                    response_object(texts[-1]) != load(path.with_name(path.name.replace('-native', '-response')))):
                raise ValueError('source native response changed')
            native_turns += 1
            response_path = path.with_name(path.name.replace('-native', '-response'))
            role_responses[file_sha(response_path)] = load(response_path)
        role_results.append(dict(role=role.name, input_unchanged=True))
    jobs = []
    source_requests = 0
    unique_requests = set()
    paired_rows = 0
    for reservation in state['jobs']:
        directory = root / reservation['name']
        request = load(directory / 'request.json')
        pending = load(directory / 'pending.json')
        submitted = load(directory / 'submitted.json')
        lifecycle = load(directory / 'lifecycle-final.json')
        if (pending['total_gpus'] != 2 or pending['request_sha256'] != file_sha(directory / 'request.json') or
                pending['source_sha256'] != file_sha(directory / 'source.tar') or submitted['code'] != 200 or
                submitted['uuid'] != reservation['uuid'] or lifecycle['uuid'] != reservation['uuid'] or
                lifecycle['conservative_gpu_seconds'] != reservation['charged_gpu_seconds'] or
                any('finished_at' not in row for row in lifecycle['pods'].values())):
            raise ValueError('source task identity/accounting differs')
        matches = job_rows((directory / 'post-submit-query.txt').read_text(), reservation['name'])
        if len(matches) != 1 or matches[0].get('name') != reservation['uuid']:
            raise ValueError('source task has no unique independent lookup')
        identity = load(directory / 'source-identity.json')
        if identity['archive_sha256'] != file_sha(directory / 'source.tar'):
            raise ValueError('trusted source archive changed')
        with tarfile.open(directory / 'source.tar') as archive:
            for name, expected in identity['files'].items():
                if hashlib.sha256(archive.extractfile(name).read()).hexdigest() != expected:
                    raise ValueError('trusted execution source content changed')
        feedback = load(directory / 'feedback.json')
        if feedback['status'] == 'completed':
            independent = replay_feedback(directory / 'remote', request)
            expected = dict(independent, status='completed', uuid=reservation['uuid'])
            if feedback != expected:
                raise ValueError('source output differs from independent replay')
            if request['mode'] != 'source-controller':
                manifest = load(directory / 'remote/manifest.json')
                unique_requests.update(row['id'] for row in manifest['requests'])
                paired_rows += independent['n_pairs']
        if request['mode'] == 'source-research':
            source_requests += 1
            if (request['patch_sha256'] != file_sha(directory / 'patch.json') or
                    request['self_check_sha256'] != file_sha(directory / 'self-check.py') or
                    request['cpu_receipt_sha256'] != file_sha(directory / 'cpu-receipt.json')):
                raise ValueError('source scientific code/CPU receipt changed')
            receipt = load(directory / 'cpu-receipt.json')
            if receipt['sha256'] != file_sha(receipt['path']):
                raise ValueError('original source CPU broker receipt changed')
            actual = cpu_origins.get(receipt['path'])
            scientific_action = request['action']
            if (not actual or actual.get('exit_code') != 0 or
                    actual.get('code_sha256') != request['self_check_sha256'] or
                    actual.get('workspace_file_sha256', {}).get(scientific_action['patch']) != request['patch_sha256'] or
                    role_responses.get(request['role_response_sha256'], {}).get('action') != scientific_action):
                raise ValueError('scientific patch/request is not bound to direction native authorship/CPU execution')
        jobs.append(dict(name=reservation['name'], uuid=reservation['uuid'], mode=request['mode'],
            status=feedback['status'], conservative_gpu_seconds=reservation['charged_gpu_seconds']))
    result_path = root / 'result.json'
    result = load(result_path) if result_path.exists() else None
    if result:
        if result['resource_state'] != state or result['status'] not in ('completed', 'infrastructure_blocked'):
            raise ValueError('source stage is still active or resource state differs')
        if any(code != 0 for code in result['closed_role_processes']) or not all(result['immutable_role_inputs']):
            raise ValueError('source roles did not close cleanly or immutable inputs changed')
        for name, count in dict(model_turns=native_turns, cpu_runs=cpu_runs, usage_updates=usage_updates).items():
            if result['counters'][name] != count:
                raise ValueError('source role counters differ from native evidence')
        if result['counters']['actions'] != tool_actions + result['counters']['gpu_attempts']:
            raise ValueError('source action accounting differs from native tools/GPU requests')
    return dict(stage_status=result['status'] if result else 'preflight_only',
        stage_goal_met=bool(result and result['source_experiment_completed'] and result['status'] == 'completed'),
        native_turns=native_turns, tool_actions=tool_actions, cpu_runs=cpu_runs, usage_update_events=usage_updates,
        roles=role_results, jobs=jobs, source_requests=source_requests, paired_rows=paired_rows,
        independent_public_requests=len(unique_requests), conservative_gpu_seconds=charged,
        controller_accepted=bool(result and result['controller_accepted']), candidate_promoted=False,
        sealed_used=False, full_phase1_completed=False, real_engine_rsi_completed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    print(json.dumps(audit(parser.parse_args().directory), sort_keys=True))
