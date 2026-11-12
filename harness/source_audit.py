"""Read-only provenance and resource audit for a closed source-option stage."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tarfile

from harness.engine_research import json_record
from harness.gpu_autonomy import job_rows, response_object
from harness.source_candidate import file_sha
from exp.source_resource import LIMITS, feedback as replay_feedback
from harness.research_protocol import CPU_ACTIONS
from harness.source_replay import verify_replay


def load(path):
    return json.loads(Path(path).read_text())


def absent_processes(root):
    from controller.phase4_final import identity, trusted_metadata
    from exp.phase4_run import reference
    paths = sorted((root / 'processes').glob('birth-*.json'))
    if not paths:
        raise ValueError('interruption needs an actual broker birth inventory')
    current = identity()
    records = []
    for path in paths:
        birth = trusted_metadata(reference(path), os.geteuid())
        child = birth['identity']
        if (child['uid'] != current['uid'] or
                (child['host_boot_id'], child['pid_namespace_inode']) !=
                (current['host_boot_id'], current['pid_namespace_inode'])):
            raise ValueError('cannot verify interrupted processes from another host or namespace')
        try:
            live = identity(child['pid'])
        except (FileNotFoundError, ProcessLookupError):
            live = None
        if live is not None and live['start_ticks'] == child['start_ticks']:
            raise ValueError('interrupted research process is still present')
        records.append(dict(birth=reference(path),present=False,exit_code=None))
    return records


def audit(root, *, limits=None, resource_state=None, prior_counters=None, history_roots=None, interrupted=False):
    root = Path(root).resolve()
    limits = LIMITS if limits is None else limits
    state = load(root / 'resource-state.json' if resource_state is None else resource_state)
    roots = [root]
    if history_roots is not None:
        if prior_counters:
            raise ValueError('history must be recounted, not seeded from prior counters')
        roots = [Path(path).resolve() for path in history_roots] + [root]
        if len({path.resolve() for path in roots}) != len(roots):
            raise ValueError('continuation lineage contains duplicate attempts')
        for index, directory in enumerate(roots):
            continuation = directory / 'continuation.json'
            previous = load(continuation).get('prior_root') if continuation.exists() else None
            expected = None if index == 0 else roots[index - 1].resolve()
            if (None if previous is None else Path(previous).resolve()) != expected:
                raise ValueError('continuation lineage omitted or reordered an attempt')
            if directory != root:
                old = load(directory / 'result.json')['resource_state']
                if (any(old.get(key) != state.get(key) for key in (*limits, 'started')) or
                        old['jobs'] != state['jobs'][:len(old['jobs'])]):
                    raise ValueError('historical resource accounting changed or reset')
    if any(state[key] != value for key, value in limits.items()):
        raise ValueError('source resource ceilings changed')
    if any(not row.get('terminated') or row.get('create_calls') != 1 for row in state['jobs']):
        raise ValueError('source task is active or submission is uncertain')
    charged = sum(row['charged_gpu_seconds'] for row in state['jobs'])
    if charged > limits['gpu_seconds']:
        raise ValueError('source GPU ceiling exceeded')
    interruption = absent_processes(root) if interrupted else None
    prior_counters={} if prior_counters is None else prior_counters
    native_turns=prior_counters.get('model_turns',0)
    tool_actions=prior_counters.get('actions',0)-prior_counters.get('gpu_attempts',0)
    cpu_runs=prior_counters.get('cpu_runs',0)
    usage_updates=prior_counters.get('usage_updates',0)
    role_results = []
    preserved_format_failures = []
    cpu_origins = {}
    role_responses = {}
    role_paths = [role for directory in roots
        for role in [directory / 'master', *sorted(directory.glob('direction-*'))] if role.is_dir()]
    for role in role_paths:
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
        if (sum(row['message'].get('method') == 'turn/start' for row in wire) !=
                len(list(role.glob('turn-*-native.json'))) or
                sum(row['message'].get('method') == 'item/tool/call' for row in wire) !=
                len(list(role.glob('tools-*/action-*/request.json')))):
            raise ValueError('native source turn or tool inventory is incomplete')
        usage_updates += sum(row['message'].get('method') == 'thread/tokenUsage/updated' for row in wire)
        authored = verify_replay(manifest['own_replay'],manifest['role']) if 'own_replay' in manifest else {}
        from harness.source_replay import replay_text
        restored=manifest.get('own_replay',{})
        authored_text={name:replay_text(name,entry,restored['source_wire'])
            for name,entry in restored.get('files',{}).items()}
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
            if action['kind'] in ('write_file','append_file') and response['success']:
                from harness.open_research import record_authored_text
                answer=json.loads(response['contentItems'][0]['text'])
                authored[action['path']]=record_authored_text(action,answer,authored_text)
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
            answer = json.loads(response['contentItems'][0]['text'])
            if action['kind'] in CPU_ACTIONS and answer.get('reason') != 'CPU run budget exhausted':
                cpu_runs += 1
            tool_actions += 1
        for path in sorted(role.glob('turn-*-native.json')):
            native = load(path)
            texts = [row['message']['params']['item']['text'] for row in wire
                if row['message'].get('method') == 'item/completed' and
                row['message']['params'].get('item', {}).get('type') == 'agentMessage' and
                row['message']['params'].get('turnId') == native['turn']['id']]
            if native['turn']['status'] != 'completed' or native['texts'] != texts:
                raise ValueError('source native response changed')
            native_turns += 1
            response_path = path.with_name(path.name.replace('-native', '-response'))
            try:
                parsed=response_object(texts[-1])
            except ValueError as error:
                number=int(path.name.split('-')[1])
                next_request=role/f'turn-{number+1:02d}-request.json'
                expected='模型JSON/协议格式未通过：'+str(error)+'。仅修复格式，保留自己的科学判断，重交完整JSON对象。'
                recoveries = []
                if role.parent != root and not response_path.exists():
                    for later in role_paths:
                        if roots.index(later.parent) <= roots.index(role.parent):
                            continue
                        replay = load(later / 'manifest.json').get('own_replay')
                        if replay and Path(replay['source_role']['path']).resolve() == (role / 'manifest.json').resolve():
                            verify_replay(replay, manifest['role'])
                            recoveries.append(str(later))
                if recoveries:
                    stopped = load(role.parent / 'result.json')
                    if stopped.get('status') != 'infrastructure_blocked' or stopped.get('error') != 'ValueError: ' + str(error):
                        raise ValueError('historical format rejection lacks its preserved actual failure') from error
                    preserved_format_failures.append(dict(role=str(role),native_sha256=file_sha(path),
                        error=str(error),same_role_recoveries=recoveries))
                    continue
                if response_path.exists() or not next_request.exists() or load(next_request)['prompt']!=expected:
                    raise ValueError('source format rejection lacks an actual same-role repair') from error
                continue
            if parsed!=load(response_path):raise ValueError('source structured response differs from native text')
            role_responses[file_sha(response_path)] = load(response_path)
        role_results.append(dict(role=role.name, input_unchanged=True,
            **({'attempt':role.parent.name} if history_roots is not None else {})))
    jobs = []
    source_requests = 0
    unique_requests = set()
    paired_rows = 0
    for reservation in state['jobs']:
        matches = [directory / reservation['name'] for directory in roots
            if (directory / reservation['name'] / 'request.json').is_file()]
        if len(matches) != 1:
            raise ValueError('resource reservation has no unique actual attempt directory')
        directory = matches[0]
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
        jobs.append(dict(name=reservation['name'], uuid=reservation['uuid'], mode=request['mode'],
            status=feedback['status'], conservative_gpu_seconds=reservation['charged_gpu_seconds']))
    unsubmitted = []
    for attempt in roots:
        for path in sorted(attempt.glob('*/request.json')):
            request = load(path)
            if request.get('mode') != 'source-research':
                continue
            source_requests += 1
            directory = path.parent
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
            if not any(row['name'] == directory.name for row in state['jobs']):
                if (not interrupted or any((directory / name).exists() for name in
                        ('trusted-admission.json', 'pending.json', 'submitted.json', 'submit.txt'))):
                    raise ValueError('unreserved source request needs explicit interruption and no submission')
                unsubmitted.append(dict(name=directory.name,request_sha256=file_sha(path),submitted=False))
    result_path = root / 'result.json'
    result = load(result_path) if result_path.exists() else None
    if result and interrupted:
        if result.get('status') != 'running' or result.get('controller_accepted'):
            raise ValueError('interruption cannot replace a completed or accepted scientific result')
    elif result:
        if result['resource_state'] != state or result['status'] not in ('completed', 'infrastructure_blocked'):
            raise ValueError('source stage is still active or resource state differs')
        if any(code != 0 for code in result['closed_role_processes']) or not all(result['immutable_role_inputs']):
            raise ValueError('source roles did not close cleanly or immutable inputs changed')
        for name, count in dict(model_turns=native_turns, cpu_runs=cpu_runs, usage_updates=usage_updates).items():
            if result['counters'][name] != count:
                raise ValueError('source role counters differ from native evidence')
        if result['counters']['actions'] != tool_actions + result['counters']['gpu_attempts']:
            raise ValueError('source action accounting differs from native tools/GPU requests')
        if history_roots is not None and result['counters']['gpu_attempts'] != source_requests:
            raise ValueError('source GPU attempts differ from all historical native requests')
    return dict(stage_status='interrupted' if interrupted else (result['status'] if result else 'preflight_only'),
        stage_goal_met=bool(not interrupted and result and result['source_experiment_completed'] and result['status'] == 'completed'),
        native_turns=native_turns, tool_actions=tool_actions, cpu_runs=cpu_runs, usage_update_events=usage_updates,
        roles=role_results, jobs=jobs, source_requests=source_requests, paired_rows=paired_rows,
        independent_public_requests=len(unique_requests), conservative_gpu_seconds=charged,
        controller_accepted=bool(result and result['controller_accepted']), candidate_promoted=False,
        sealed_used=False, full_phase1_completed=False, real_engine_rsi_completed=False,
        **({'audited_attempts':[path.name for path in roots],
            'preserved_format_failures':preserved_format_failures} if history_roots is not None else {}),
        **({'absent_processes':interruption,'unsubmitted_requests':unsubmitted,
            'normal_pipeline_completed':False,'original_running_result_preserved':True,
            'original_result_sha256':file_sha(result_path),
            'exit_codes_certified':False} if interrupted else {}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--resource-state', type=Path)
    parser.add_argument('--history-root', action='append', type=Path)
    parser.add_argument('--limits-json', type=json.loads)
    parser.add_argument('--interrupted', action='store_true')
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.directory, resource_state=arguments.resource_state,
        history_roots=arguments.history_root, limits=arguments.limits_json,
        interrupted=arguments.interrupted), sort_keys=True))
