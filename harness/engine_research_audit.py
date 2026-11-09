"""Read-only evidence audit, separate from research decisions and controller gates."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from harness.gpu_autonomy import digest, job_rows, response_object
from harness.engine_research import feedback_metrics, json_record


def load(path):
    return json.loads(Path(path).read_text())


def audit(root):
    root = Path(root)
    result = load(root / 'result.json')
    recovery = load(root / 'recovery.json') if (root / 'recovery.json').exists() else None
    state = load(recovery['resource_path'] if recovery else root / 'resource-state.json')
    if result['status'] != 'completed' or result['resource_state'] != state:
        raise ValueError('stage is incomplete or resource snapshot differs')
    if (state['gpu_seconds'], state['wall_seconds'], state['concurrent_gpus']) != (230400, 86400, 8):
        raise ValueError('authorized stage ceilings changed')
    if any(not row.get('terminated') or row.get('create_calls') != 1 for row in state['jobs']):
        raise ValueError('active or uncertain resource reservation')
    if sum(row['charged_gpu_seconds'] for row in state['jobs']) > 230400:
        raise ValueError('GPU time ceiling exceeded')
    native_turns = 0
    tool_actions = 0
    usage_updates = 0
    cpu_runs = 0
    cpu_code_checks = 0
    roots = [root]
    cursor = recovery
    while cursor:
        prior = Path(cursor['prior_run'])
        if prior in roots or digest(prior / 'result.json') != cursor['prior_result_sha256']:
            raise ValueError('prior phase snapshot changed or recovery cycle exists')
        roots.insert(0, prior)
        cursor = load(prior / 'recovery.json') if (prior / 'recovery.json').exists() else None
    roles = [role for scope in roots for role in [scope / 'master', *sorted(scope.glob('direction-*'))]]
    roles = [role for role in roles if role.is_dir()]
    if not roles or not (root / 'master').is_dir():
        raise ValueError('native Master evidence is required')
    for role in roles:
        manifest = load(role / 'manifest.json')
        for path, key in [(manifest['canary'], 'canary_sha256'),
                (Path(manifest['work']) / 'inputs/rules.txt', 'rules_sha256'),
                (Path(manifest['work']) / 'inputs/evidence.json', 'evidence_sha256'),
                (Path(manifest['home']) / 'config.toml', 'config_sha256')]:
            if digest(path) != manifest[key]:
                raise ValueError('role input/canary/config changed')
        wire = [json.loads(line) for line in (role / 'wire.jsonl').read_text().splitlines()]
        usage_updates += sum(row['message'].get('method') == 'thread/tokenUsage/updated' for row in wire)
        written = {}
        for request_path in sorted(role.glob('tools-*/action-*/request.json')):
            request = load(request_path)
            calls = [row['message'] for row in wire if row['message'].get('method') == 'item/tool/call'
                     and row['message'].get('params') == request]
            if len(calls) != 1:
                raise ValueError('tool action is not bound to a unique native research call')
            recorded = load(request_path.parent / 'response.json')
            if not any(row['direction'] == 'client' and row['message'].get('id') == calls[0]['id'] and
                       row['message'].get('result') == recorded for row in wire):
                raise ValueError('tool feedback differs from native client return')
            action = request['arguments']['action']
            if action['kind'] == 'write_file' and recorded['success']:
                written[action['path']] = hashlib.sha256(action['content'].encode()).hexdigest()
            execution = request_path.parent / 'execution'
            if action['kind'] == 'run_python' and (execution / 'result.json').exists():
                checked = load(execution / 'result.json')
                if checked['code_sha256'] != written.get(action['path']):
                    raise ValueError('CPU script was not authored in the direction native tool stream')
                for stream in ('stdout', 'stderr'):
                    if digest(execution / stream) != checked['output_sha256'][stream]:
                        raise ValueError('actual isolated CPU output changed')
                if not checked['landlock_applied'] or not checked['seccomp_applied'] or checked['gpu_submissions'] != 0:
                    raise ValueError('CPU execution boundary differs')
                cpu_code_checks += 1
        for native_path in role.glob('turn-*-native.json'):
            native = load(native_path)
            if native['turn']['status'] != 'completed':
                raise ValueError('native role turn incomplete')
            responses = [row['message']['params']['item']['text'] for row in wire
                if row['message'].get('method') == 'item/completed' and
                row['message'].get('params', {}).get('item', {}).get('type') == 'agentMessage' and
                row['message'].get('params', {}).get('turnId') == native['turn']['id']]
            if native['texts'] != responses:
                raise ValueError('role response does not match native wire text')
            response_path = native_path.with_name(native_path.name.replace('-native', '-response'))
            if response_object(native['texts'][-1]) != load(response_path):
                raise ValueError('structured response differs from native text')
            native_turns += 1
        tool_actions += len(list(role.glob('tools-*/action-*/request.json')))
        cpu_runs += len(list(role.glob('tools-*/action-*/execution/result.json')))
    if (native_turns != result['counters']['model_turns'] or usage_updates != result['counters']['usage_updates'] or
            cpu_runs != result['counters']['cpu_runs']):
        raise ValueError('native turn/usage/CPU counters differ')
    accepted_requests = 0
    diagnostics = 0
    gates = 0
    resource_events = []
    for job in state['jobs']:
        locations = [scope / job['name'] for scope in roots if (scope / job['name']).is_dir()]
        if len(locations) != 1:
            raise ValueError('unique original job evidence is required')
        directory = locations[0]
        request = load(directory / 'request.json')
        pending = load(directory / 'pending.json')
        submitted = load(directory / 'submitted.json')
        lifecycle = load(directory / 'lifecycle-final.json')
        from datetime import datetime
        finished = max(datetime.fromisoformat(row['finished_at']).timestamp() for row in lifecycle['pods'].values())
        if finished > state['started'] + 86400:
            raise ValueError('stage wall deadline exceeded')
        resource_events.extend([(job['reserved_unix'], job['gpus']), (finished, -job['gpus'])])
        if (job_rows((directory / 'pre-submit-query.txt').read_text(), job['name']) or
                submitted != dict(uuid=job['uuid'], code=200, name=job['name']) or
                pending['request_sha256'] != digest(directory / 'request.json') or
                pending['source_sha256'] != digest(directory / 'source.tar') or
                lifecycle['uuid'] != job['uuid'] or lifecycle['conservative_gpu_seconds'] != job['charged_gpu_seconds']):
            raise ValueError('job identity, request, duplicate check or resources differ')
        identity = load(directory / 'source-identity.json')
        with tarfile.open(directory / 'source.tar') as archive:
            if identity['archive_sha256'] != digest(directory / 'source.tar'):
                raise ValueError('frozen source archive changed')
            for name, expected in identity['files'].items():
                if hashlib.sha256(archive.extractfile(name).read()).hexdigest() != expected:
                    raise ValueError('frozen execution source changed')
        if request.get('mode') == 'controller-dev':
            gates += 1
            candidates = [path for scope in roots for path in (scope / 'master').glob('turn-*-response.json')
                          if digest(path) == request['master_response_sha256']]
            if len(candidates) != 1 or load(candidates[0]).get('value') != request['action']['value']:
                raise ValueError('dev gate lacks native Master authorization')
        else:
            accepted_requests += 1
            candidates = [path for role in roles if role.name.startswith('direction-') for path in role.glob('turn-*-response.json')
                          if digest(path) == request['role_response_sha256']]
            if len(candidates) != 1 or load(candidates[0]).get('action') != request['action']:
                raise ValueError('engine request was not authored by direction')
        feedback = load(directory / 'feedback.json')
        if feedback.get('status') == 'completed':
            if request.get('mode') == 'controller-dev':
                from controller.dev_campaign import validate_campaign
                from harness.candidate import load_bundle
                campaign = load(directory / 'remote/manifest.json')
                spec = load_bundle(directory / 'remote/bundle')
                if (spec['value'] != request['action']['value'] or
                        campaign['candidate_origin']['value'] != spec['value'] or
                        json_record(validate_campaign(directory / 'remote')) != feedback['controller_verdict']):
                    raise ValueError('controller independent replay differs')
            else:
                from exp.engine_research import audit as audit_engine
                expected = dict(audit_engine(directory / 'remote'), status='completed', uuid=job['uuid'])
                if feedback not in (expected, feedback_metrics(expected)):
                    raise ValueError('engine independent replay differs')
                diagnostics += 1
    expected_count = diagnostics
    if result.get('diagnostic_counter_schema') != 'all-lineage-diagnostics-v2':
        if (root / 'feedback.json').exists():
            scoped_feedback = load(root / 'feedback.json')
        else:
            prior = Path(recovery['prior_run']) if recovery else root
            scoped_feedback = [load(path) for path in prior.glob('sp-engine-*/feedback.json')]
        expected_count = sum(row.get('status') == 'completed' for row in scoped_feedback)
    if (tool_actions + accepted_requests != result['counters']['actions'] or
            expected_count != result['real_engine_diagnostics']):
        raise ValueError('research action count differs')
    if any(code != 0 for code in result['closed_role_processes']) or not all(result['immutable_role_inputs']):
        raise ValueError('role termination/integrity check failed')
    concurrent = peak = 0
    for stamp, change in sorted(resource_events):
        concurrent += change
        peak = max(peak, concurrent)
    if concurrent != 0 or peak > 8:
        raise ValueError('stage GPU concurrency exceeded')
    return dict(engine_evidence_audit_passed=True, diagnostics=diagnostics, controller_gate_attempts=gates,
        native_turns=native_turns, tool_actions=tool_actions, cpu_runs=cpu_runs,
        native_cpu_code_output_checks=cpu_code_checks, usage_update_events=usage_updates,
        producer_counter_schema=result.get('diagnostic_counter_schema', 'legacy-resume-scope-all-completions'),
        producer_scoped_completion_count=result['real_engine_diagnostics'],
        terminated_jobs=len(state['jobs']), peak_reserved_concurrent_gpus=peak,
        conservative_gpu_seconds=sum(row['charged_gpu_seconds'] for row in state['jobs']),
        controller_accepted=result['controller_accepted'], candidate_promoted=False, real_engine_rsi_completed=False,
        scope='engineering provenance audit, not a new controller verdict or paper reproduction')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
