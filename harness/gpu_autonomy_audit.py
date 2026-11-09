"""Read-only binding of real role traffic, frozen scripts and remote GPU receipts."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from harness.gpu_autonomy import digest, response_object, verify_request


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(root, require_gpu=True):
    root = Path(root)
    result = read(root / 'result.json')
    require(result['status'] in ('completed', 'no_gpu_feedback'), 'role protocol did not complete')
    if require_gpu:
        require(result['status'] == 'completed', 'real autonomy run did not complete')
    require(result['controller_accepted'] is False, 'screening promoted itself')
    authored = {}
    provenance = root / ('continuation.json' if (root / 'continuation.json').exists() else 'recovery.json')
    if provenance.exists():
        recovery_record = read(provenance)
        previous = Path(recovery_record['prior_run'])
        require(previous.name.startswith('gpu-autonomy-run-'), 'unexpected recovery source')
        require(digest(previous / 'result.json') == recovery_record['prior_result_sha256'], 'recovered state changed')
        if provenance.name == 'continuation.json':
            require(read(previous / 'result.json')['counters'] == recovery_record['prior_counters'], 'prior phase counters changed')
            require(all(value == 0 for value in recovery_record['new_phase_counters'].values()), 'new phase counters were not explicit')
            preflight = Path(recovery_record['preflight_result'])
            require(digest(preflight) == recovery_record['preflight_sha256'], 'dependency preflight changed')
            proof = read(preflight)
            require(proof['status'] == 'completed' and proof['gpu_test_passed'] and proof['boundary_passed'], 'dependency preflight did not pass')
        source_roles = []
        while previous.name.startswith('gpu-autonomy-run-'):
            if (previous / 'master-plan.json').exists() and read(previous / 'master-plan.json')['direction_id'] == read(root / 'master-plan.json')['direction_id']:
                source_roles.insert(0, previous / 'direction')
            ancestor = previous / ('continuation.json' if (previous / 'continuation.json').exists() else 'recovery.json')
            if not ancestor.exists():
                break
            previous = Path(read(ancestor)['prior_run'])
        for source_role in source_roles:
            for record in sorted(source_role.glob('tools-*/action-*')):
                request = read(record / 'request.json')
                response = read(record / 'response.json')
                action = request['arguments']['action']
                if response['success'] and action.get('kind') == 'write_file':
                    authored[action['path']] = hashlib.sha256(action['content'].encode()).hexdigest()
    native_calls = 0
    native_cpu_runs = 0
    native_usage_updates = 0
    final_actions = 0
    final_cpu_runs = 0
    turns = 0
    gpu_turns = []
    if (root / 'master-authorized-retry.json').exists():
        authority = read(root / 'master-authorized-retry.json')
        parent = Path(authority['authority_run'])
        require(digest(parent / 'master-review.json') == authority['authority_sha256'], 'master retry authority changed')
        require(read(parent / 'master-review.json')['decision'] == 'continue', 'retry lacks a real master decision')
        require(read(parent / 'master-review.json') == read(parent / 'master/turn-02-response.json'), 'retry authority differs from actual master response')
        original = verify_request(Path(authority['original_request']))
        gpu_turns.append((dict(kind='run_gpu_python', path=original['script'], acceptance=original['acceptance']), dict(authored)))
    for role in ('master', 'direction'):
        directory = root / role
        manifest = read(directory / 'manifest.json')
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        native_usage_updates += sum(row['message'].get('method') == 'thread/tokenUsage/updated' for row in wire)
        starts = [row['message'] for row in wire if row['direction'] == 'client' and row['message'].get('method') == 'thread/start']
        require(len(starts) == 1 and starts[0]['params']['approvalPolicy'] == 'never', 'role policy changed')
        require(starts[0]['params']['cwd'] == manifest['work'], 'role workspace changed')
        require((directory / 'runtime-stderr.log').read_bytes().startswith(b'SP_ROLE_ISOLATION_READY\n'), 'role kernel marker missing')
        require(digest(directory / 'workspace-evidence/inputs/evidence.json') == manifest['evidence_sha256'], 'role input changed')
        require(digest(directory / 'protected-canary-after.txt') == manifest['canary_sha256'], 'role canary changed')
        calls = [row['message'] for row in wire if row['direction'] == 'server' and row['message'].get('method') == 'item/tool/call']
        records = sorted(directory.glob('tools-*/action-*'))
        require(len(calls) == len(records), 'native tool traffic differs from audit files')
        for native, record in zip(calls, records):
            request = read(record / 'request.json')
            response = read(record / 'response.json')
            require(native['params'] == request, 'tool request was rewritten')
            require(request['tool'] == 'research' and request.get('namespace') is None, 'unapproved dynamic tool')
            replies = [row['message'] for row in wire if row['direction'] == 'client' and row['message'].get('id') == native['id'] and 'method' not in row['message']]
            require(len(replies) == 1 and replies[0].get('result') == response, 'tool feedback differs from actual reply')
            action = request['arguments']['action']
            value = json.loads(response['contentItems'][0]['text'])
            if action.get('kind') == 'run_python' and value.get('reason') != 'CPU run budget exhausted':
                native_cpu_runs += 1
            native_calls += 1
        for response_path in sorted(directory.glob('turn-*-response.json')):
            number = int(response_path.name.split('-')[1])
            response = read(response_path)
            saved = read(directory / f'turn-{number:02d}-native.json')
            require(response_object(saved['texts'][-1]) == response, 'model JSON not bound to native text')
            completed = [row['message']['params']['turn'] for row in wire if row['direction'] == 'server' and row['message'].get('method') == 'turn/completed'
                and row['message']['params']['turn']['id'] == saved['turn']['id']]
            require(len(completed) == 1 and completed[0] == saved['turn'], 'role completion binding missing')
            for record in sorted((directory / f'tools-{number:02d}').glob('action-*')):
                request = read(record / 'request.json')
                reply = read(record / 'response.json')
                action = request['arguments']['action']
                if role == 'direction' and reply['success'] and action.get('kind') == 'write_file':
                    authored[action['path']] = hashlib.sha256(action['content'].encode()).hexdigest()
            if role == 'direction':
                action = response.get('action', {})
                if action.get('kind') == 'write_file':
                    authored[action['path']] = hashlib.sha256(action['content'].encode()).hexdigest()
                if action.get('kind') == 'run_gpu_python':
                    gpu_turns.append((action, dict(authored)))
                elif action.get('kind') != 'finish':
                    final_actions += 1
                    final_cpu_runs += action.get('kind') == 'run_python'
            turns += 1
    requests = sorted(root.glob('gpu-*/request.json'))
    require(len(requests) <= len(gpu_turns) <= 2, 'GPU attempt identities inconsistent')
    successful = 0
    scientific_screens = 0
    for request_path, (action, source_codes) in zip(requests, gpu_turns):
        directory = request_path.parent
        manifest = verify_request(directory)
        source = read(directory / 'source-identity.json')
        require(digest(directory / 'source.tar') == source['archive_sha256'], 'trusted source archive changed')
        with tarfile.open(directory / 'source.tar') as archive:
            for name, expected in source['source_sha256'].items():
                require(hashlib.sha256(archive.extractfile(name).read()).hexdigest() == expected, 'frozen trusted source differs')
        require(manifest['script'] == action['path'] and manifest['acceptance'] == action['acceptance'], 'GPU script paths changed')
        for name in (manifest['script'], manifest['acceptance']):
            require(source_codes.get(name) == manifest['files'][name], 'GPU code differs from agent-authored code')
        remote = root / ('remote-' + directory.name.split('-')[1])
        receipt = read(remote / 'result.json')
        require(receipt['request_sha256'] == digest(request_path), 'remote request identity mismatch')
        require(receipt['immutable_inputs'] and receipt['canary_unchanged'], 'remote immutable files changed')
        environment = read(remote / 'environment.json')
        require(environment['sglang'] == '0.5.20' and 'H100' in environment['nvidia_smi'], 'deployment identity differs')
        for index, run in enumerate(receipt['runs']):
            label = 'experiment' if index == 0 else 'acceptance'
            require(run == read(remote / label / 'result.json'), 'remote execution receipt rewritten')
            require(run['code_sha256'] == manifest['files'][run['program']], 'executed program identity mismatch')
            for stream, metadata in run['outputs'].items():
                path = remote / label / stream
                require(digest(path) == metadata['sha256'] and path.stat().st_size == metadata['bytes'], 'raw GPU output changed')
                require(path.read_text(errors='replace')[:16000] == metadata['text'], 'visible GPU output changed')
            if run['proof']:
                proofs = []
                for line in (remote / label / 'stderr').read_text(errors='replace').splitlines():
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict) and value.get('kernel_boundary_applied'):
                        proofs.append(value)
                require(proofs and proofs[0] == run['proof'], 'kernel proof differs from actual stderr')
                require(run['proof']['gpu'] and all(run['proof']['boundary_checks'].values()), 'GPU confinement failed')
        if receipt['process_started'] and receipt['gpu_test_passed'] and receipt['boundary_passed']:
            successful += 1
        scientific_screens += receipt['status'] == 'completed'
        feedback = read(directory / 'feedback.json')
        require(all(feedback.get(key) == value for key, value in receipt.items()), 'agent did not receive actual GPU feedback')
        require(feedback.get('job_uuid') and feedback.get('submission_code') == 200, 'submission identity missing')
    recovery = read(root / 'recovery.json')['charged_actual_counters'] if (root / 'recovery.json').exists() else dict(model_turns=0, actions=0, cpu_runs=0, gpu_attempts=0, usage_updates=0)
    require(result['counters']['model_turns'] == recovery['model_turns'] + turns <= 16, 'model turn budget differs')
    require(result['counters']['actions'] == recovery['actions'] + native_calls + final_actions + len(requests), 'charged actions differ from actual requests')
    require(result['counters']['cpu_runs'] == recovery['cpu_runs'] + native_cpu_runs + final_cpu_runs, 'CPU run accounting differs')
    require(result['counters']['gpu_attempts'] == recovery['gpu_attempts'] + len(requests), 'GPU attempt accounting differs')
    require(result['counters']['usage_updates'] == recovery['usage_updates'] + native_usage_updates, 'native update accounting differs')
    action_limit = result.get('internal_action_limit', 24)
    require(action_limit in (24, 28), 'unsupported internal action ceiling')
    require(result['counters']['actions'] <= action_limit and result['counters']['cpu_runs'] <= 4 and result['counters']['gpu_attempts'] <= 2, 'resource budget exceeded')
    if require_gpu:
        require(successful > 0, 'no real constrained GPU feedback')
    review = read(root / 'master-review.json')
    require(review == result['master_review'] and review.get('decision') in ('stop', 'continue'), 'master review not bound')
    if review['decision'] == 'continue':
        allocation = review['extra_budget']
        require(all(type(allocation[name]) is int and 0 <= allocation[name] <= limit-result['counters'][counter]
            for name, limit, counter in (('actions', action_limit, 'actions'), ('cpu_runs', 4, 'cpu_runs'), ('gpu_attempts', 2, 'gpu_attempts'))), 'master expanded stage limits')
    return dict(schema='gpu-autonomy-audit-v1', passed=True, gpu_autonomy_passed=successful > 0,
        current_run_model_turns=turns, current_run_native_tool_calls=native_calls,
        cumulative_counters=result['counters'], gpu_requests=len(requests), actual_gpu_feedback=successful,
        scientific_screens_passed=scientific_screens, master_decision=review['decision'],
        code_authorship_bound=True if requests else None, raw_outputs_bound=True if requests else None,
        controller_accepted=False, scope='restricted GPU script receipts' if requests else
            'role protocol only; no GPU request, code execution or remote boundary verification')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--allow-no-gpu', action='store_true')
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, require_gpu=not args.allow_no_gpu), sort_keys=True))
