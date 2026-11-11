"""Read-only closed-stage Skill RSI audit; never executes tools or submits jobs."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import tarfile

from agents.exploration import object_sha
from controller.dev_campaign import validate_campaign
from exp.skill_rsi import LIMITS
from exp.phase4_resource import feedback as replay_phase4_feedback
from exp.source_resource import feedback as replay_feedback
from harness.engine_research import json_record
from harness.gpu_autonomy import job_rows, response_object
from harness.skill_broker import CATALOG, ROLE_SKILLS
from harness.skill_diagnostics import checked_tools
from harness.source_audit import load as source_load
from harness.source_candidate import read_patch, validate_action


ROOT = Path(__file__).resolve().parents[1]


def safe_path(path, within=None):
    path = Path(path)
    if any(part in ('sealed', '.git') for part in path.parts) or path.name == 'auth.json':
        raise ValueError('protected evidence path is not readable by this audit')
    resolved = path.resolve()
    if any(part in ('sealed', '.git') for part in resolved.parts) or resolved.name == 'auth.json':
        raise ValueError('protected evidence target')
    if within is not None and not resolved.is_relative_to(Path(within).resolve()):
        raise ValueError('evidence escaped its declared root')
    return resolved


def load(path):
    return source_load(safe_path(path))


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def skill_evidence(root, execution, answer, role):
    require(load(execution / 'result.json') == answer, 'skill return differs from its execution record')
    require(answer['skill'] in ROLE_SKILLS[role] and answer['upstream'] == CATALOG[answer['skill']]['upstream'],
            'skill is outside the native role capability')
    tools = load(root / 'tools.json')
    checked_tools(tools)
    require(answer['upstream_revision'] == tools['revision'] and answer['independent_discovery'] is False,
            'skill version/provenance changed')
    caches = [path for path in (root / 'skill-cache').glob('*/result.json') if sha(path) == answer['result_sha256']]
    require(len(caches) == 1, 'skill result has no unique immutable cache evidence')
    cache = caches[0]
    result = load(cache)
    require(result['engineering_passed'] is True and result['upstream_revision'] == tools['revision'] and
            result['tool_lock_sha256'] == sha(ROOT / 'harness/skill_tools.json'), 'skill lock/cache identity differs')
    require(set(result['adapter_sources_sha256']) == {'harness/skill_diagnostics.py', 'harness/skill_worker.py',
            'exp/skill_diagnostics.py'}, 'skill adapter inventory incomplete')
    for name, digest in result['adapter_sources_sha256'].items():
        require(sha(safe_path(ROOT / name, ROOT)) == digest, 'skill adapter source changed')
    for name, receipt in result['tools'].items():
        if 'output_sha256' in receipt:
            for stream, digest in receipt['output_sha256'].items():
                require(stream in ('stdout', 'stderr') and sha(cache.parent / f'{name}.{stream}.txt') == digest,
                        'skill output SHA differs')
    if answer['skill'] in ('triage', 'capacity'):
        lock = load(ROOT / 'harness/skill_extension_tools.json')
        require(lock['revision'] == tools['revision'], 'extension revision differs')
        for name, digest in lock['files'].items():
            require(sha(safe_path(root / 'extensions' / name, root / 'extensions')) == digest,
                    'skill extension SHA differs')
        if 'guide' in answer:
            card = root / 'extensions/skills/sglang-prod-incident-triage/SKILL.md'
            require(answer['guide_sha256'] == sha(card) and answer['guide'] == safe_path(card).read_text()[:12000],
                    'triage guide changed')
        if 'receipt' in answer:
            for stream, digest in answer['receipt']['output_sha256'].items():
                require(sha(execution / 'capacity' / f'capacity.{stream}.txt') == digest,
                        'capacity output SHA differs')
            require(sha(execution / 'capacity/startup.log') == answer.get('input_sha256', sha(execution / 'capacity/startup.log')),
                    'capacity input SHA differs')
    require(answer['status'] in ('completed', 'unavailable'), 'skill has no recognized evidence disposition')
    return answer['status']


def audit_role(root, directory, *, allow_format_retries=False):
    manifest = load(directory / 'manifest.json')
    kind = manifest['role']
    require(kind in ROLE_SKILLS, 'unknown scientific role')
    for path, key in ((manifest['canary'], 'canary_sha256'),
            (Path(manifest['work']) / 'inputs/rules.txt', 'rules_sha256'),
            (Path(manifest['work']) / 'inputs/evidence.json', 'evidence_sha256'),
            (Path(manifest['home']) / 'config.toml', 'config_sha256')):
        require(sha(path) == manifest[key], 'role immutable input/config/canary changed')
    require(object_sha(load(Path(manifest['work']) / 'inputs/evidence.json')) == manifest['research_packet_sha256'],
            'role packet identity changed')
    wire = [json.loads(line) for line in safe_path(directory / 'wire.jsonl').read_text().splitlines()]
    messages = [row['message'] for row in wire]
    def rpc(method):
        pairs = []
        for row in wire:
            if row['direction'] == 'client' and row['message'].get('method') == method:
                request = row['message']
                matches = [value['message'] for value in wire if value['direction'] == 'server' and
                           value['message'].get('id') == request['id'] and 'result' in value['message']]
                require(len(matches) == 1, 'native RPC has no unique server result')
                pairs.append((request, matches[0]['result']))
        return pairs
    threads = rpc('thread/start')
    require(len(threads) == 1, 'scientific role needs one native thread')
    thread = threads[0][1]['thread']['id']
    turns, responses, cpu_origins = {}, {}, {}
    native_turns = list(rpc('turn/start'))
    format_rejections, consecutive_rejections = 0, 0
    for number, (request, reply) in enumerate(native_turns, 1):
        require(request['params']['threadId'] == thread, 'native turn crossed role thread')
        turn = reply['turn']['id']
        require(turn not in turns.values(), 'native turn ID reused')
        turns[number] = turn
        stem = directory / f'turn-{number:02d}'
        prompt = load(stem.with_name(stem.name + '-request.json'))
        require(hashlib.sha256(prompt['prompt'].encode()).hexdigest() == prompt['prompt_sha256'] and
                request['params']['input'] == [dict(type='text', text=prompt['prompt'])], 'native prompt differs')
        native = load(stem.with_name(stem.name + '-native.json'))
        completions = [message['params']['turn'] for message in messages
                       if message.get('method') == 'turn/completed' and message['params']['turn']['id'] == turn]
        texts = [message['params']['item']['text'] for message in messages if message.get('method') == 'item/completed' and
                 message['params'].get('turnId') == turn and message['params'].get('item', {}).get('type') == 'agentMessage']
        require(len(completions) == 1 and native['turn'] == completions[0] and
                native['turn']['status'] == 'completed' and native['texts'] == texts and texts,
                'native response/completion differs or is incomplete')
        path = stem.with_name(stem.name + '-response.json')
        try:
            value = response_object(texts[-1])
        except ValueError as error:
            require(allow_format_retries and not path.exists() and number < len(native_turns) and
                    consecutive_rejections < 2, 'native format retry is missing, fabricated or exceeds its bound')
            expected_prompt = '模型JSON/协议格式未通过：' + str(error) + '。仅修复格式，保留自己的科学判断，重交完整JSON对象。'
            next_request = native_turns[number][0]
            require(next_request['params']['threadId'] == thread and
                    next_request['params']['input'] == [dict(type='text', text=expected_prompt)],
                    'native format retry does not preserve the actual parser failure')
            format_rejections += 1
            consecutive_rejections += 1
            continue
        require(load(path) == value, 'structured response differs from native text')
        consecutive_rejections = 0
        responses[(thread, number)] = dict(value=load(path), sha256=sha(path), role=directory.name)
    require(len(list(directory.glob('turn-*-native.json'))) == len(turns), 'orphan native turn record')
    counts = Counter(model_turns=len(turns), format_rejections=format_rejections,
                     usage_updates=sum(message.get('method') == 'thread/tokenUsage/updated'
                                                            for message in messages))
    authored, seen_calls = {}, set()
    requests = sorted(directory.glob('tools-*/action-*/request.json'))
    calls = [row for row in wire if row['direction'] == 'server' and row['message'].get('method') == 'item/tool/call']
    require(len(requests) == len(calls), 'native tool calls and private action records differ')
    require([load(path) for path in requests] == [row['message'].get('params') for row in calls],
            'private tool record order differs from the native stream')
    for path in requests:
        request = load(path)
        ordinal = int(path.parent.parent.name.removeprefix('tools-'))
        require(request['threadId'] == thread and request['turnId'] == turns.get(ordinal) and
                request.get('tool') == 'research' and request.get('namespace') is None,
                'tool request crossed native thread/turn')
        identity = (request['turnId'], request['callId'])
        require(identity not in seen_calls, 'native tool call repeated')
        seen_calls.add(identity)
        matches = [row['message'] for row in calls if row['message'].get('params') == request]
        require(len(matches) == 1, 'tool has no unique native call')
        returned = load(path.parent / 'response.json')
        replies = [row['message'] for row in wire if row['direction'] == 'client' and
                   row['message'].get('id') == matches[0]['id'] and row['message'].get('result') == returned]
        require(len(replies) == 1, 'tool feedback differs from native wire')
        answer = json.loads(returned['contentItems'][0]['text'])
        action = request['arguments']['action']
        execution = path.parent / 'execution'
        counts['actions'] += 1
        if action['kind'] in ('run_python', 'run_skill', 'read_profile_shapes') and answer.get('reason') != 'CPU run budget exhausted':
            counts['cpu_runs'] += 1
        if action['kind'] == 'write_file' and returned['success']:
            authored[action['path']] = hashlib.sha256(action['content'].encode()).hexdigest()
            require(answer['sha256'] == authored[action['path']], 'native write-file SHA differs')
        if action['kind'] == 'run_python' and (execution / 'result.json').exists():
            record = load(execution / 'result.json')
            require(record['code_sha256'] == authored.get(action['path']), 'CPU script lacks native authorship')
            require(all(answer.get(key) == value for key, value in record.items()), 'CPU result differs from broker return')
            for stream, digest in record['output_sha256'].items():
                require(stream in ('stdout', 'stderr') and sha(execution / stream) == digest, 'CPU output SHA differs')
            require(record['landlock_applied'] is True and record['seccomp_applied'] is True and
                    record['gpu_submissions'] == 0, 'CPU execution boundary differs')
            cpu_origins[str(safe_path(path.parent / 'response.json'))] = dict(
                value=answer, thread=thread, turn=ordinal, authored=dict(authored))
            authored.update(answer.get('workspace_file_sha256', {}))
            counts['python_executions'] += 1
        if action['kind'] == 'run_skill':
            counts['skill_calls'] += 1
            if returned['success']:
                require(answer.get('role') == kind and answer.get('skill') == action['skill'] and
                        answer.get('evidence') == action['evidence'], 'skill response crossed role/input')
                counts['skills_' + skill_evidence(root, execution, answer, kind)] += 1
            else:
                counts['skills_rejected'] += 1
    return dict(name=directory.name, kind=kind, thread=thread, counts=counts), responses, cpu_origins


def check_authorship(root, directory, request, responses, origins):
    validate_action(request['action'])
    for name, key in (('patch.json', 'patch_sha256'), ('self-check.py', 'self_check_sha256'),
                      ('cpu-receipt.json', 'cpu_receipt_sha256')):
        require(sha(directory / name) == request[key], 'scientific patch/self-check/CPU receipt SHA differs')
    read_patch(directory / 'patch.json')
    native = responses.get((request['role_thread'], request['role_turn']))
    require(native is not None and native['sha256'] == request['role_response_sha256'] and
            native['value'].get('action') == request['action'], 'research request lacks exact role/thread/turn response binding')
    receipt = load(directory / 'cpu-receipt.json')
    receipt_path = safe_path(receipt['path'], root / native['role'])
    require(receipt['sha256'] == sha(receipt_path), 'original CPU response SHA differs')
    origin = origins.get(str(receipt_path))
    require(origin is not None and origin['thread'] == request['role_thread'] and origin['turn'] <= request['role_turn'],
            'CPU receipt belongs to another role or a future turn')
    answer = origin['value']
    files = {request['action']['patch']: request['patch_sha256'], request['action']['self_check']: request['self_check_sha256']}
    require(receipt['files'] == files and answer.get('exit_code') == 0 and
            answer.get('code_sha256') == request['self_check_sha256'] and
            all(answer.get('workspace_file_sha256', {}).get(name) == digest for name, digest in files.items()),
            'successful CPU execution does not bind the current scientific files')


def terminal_job(root, reservation, state, *, controller_extension=False):
    require(reservation.get('terminated') is True and reservation.get('create_calls') == 1, 'GPU task active or submission uncertain')
    directory = safe_path(root / reservation['name'], root)
    pending, submitted, lifecycle = [load(directory / name) for name in ('pending.json', 'submitted.json', 'lifecycle-final.json')]
    require(lifecycle.get('phase') in ('Completed', 'Failed', 'Aborted', 'Terminated'), 'GPU terminal phase unconfirmed')
    require(submitted == dict(uuid=reservation['uuid'], code=200, name=reservation['name']) and
            lifecycle['uuid'] == reservation['uuid'] and lifecycle['phase'] == reservation['terminal'] and
            lifecycle['conservative_gpu_seconds'] == reservation['charged_gpu_seconds'] and
            pending['total_gpus'] == reservation['gpus'] == 2 and
            pending['request_sha256'] == sha(directory / 'request.json') and
            pending['source_sha256'] == sha(directory / 'source.tar'), 'GPU identity/accounting changed')
    require(not job_rows(safe_path(directory / 'pre-submit-query.txt').read_text(), reservation['name']), 'duplicate pre-submit job')
    matches = job_rows(safe_path(directory / 'post-submit-query.txt').read_text(), reservation['name'])
    require(len(matches) == 1 and matches[0].get('name') == reservation['uuid'], 'GPU UUID lacks unique lookup')
    identity = load(directory / 'source-identity.json')
    archive_digest = sha(directory / 'source.tar')
    if controller_extension:
        require(identity['archive'] == dict(path=str(directory / 'source.tar'), sha256=archive_digest),
                'controller archive reference differs')
    else:
        require(identity['archive_sha256'] == archive_digest, 'frozen archive SHA differs')
    with tarfile.open(safe_path(directory / 'source.tar')) as archive:
        require(identity['files'] and len(archive.getmembers()) == len(identity['files']) and
                set(archive.getnames()) == set(identity['files']), 'frozen source inventory incomplete or contains extras')
        for name, digest in identity['files'].items():
            require('sealed' not in Path(name).parts and not Path(name).is_absolute() and '..' not in Path(name).parts,
                    'protected/escaping archive member')
            member = archive.getmember(name)
            require(member.isfile() and hashlib.sha256(archive.extractfile(member).read()).hexdigest() == digest,
                    'frozen runtime source content differs')
    pods = lifecycle['pods']
    if lifecycle.get('preemption_receipt'):
        reference = lifecycle['preemption_receipt']
        path = safe_path(reference['path'], directory)
        require(sha(path) == reference['sha256'], 'preemption receipt SHA differs')
        proof = load(path)
        require(proof['uuid'] == reservation['uuid'] and proof['phase'] == lifecycle['phase'] and
                proof['terminal_job_and_pod_absence_confirmed'] is True and proof['reason'] == 'JobPreempted' and
                proof['conservative_gpu_seconds'] == reservation['charged_gpu_seconds'] and
                any(event.get('reason') == 'JobPreempted' and event.get('involved_name') == reservation['uuid']
                    for event in proof['events']), 'invalid terminal preemption proof')
        finished = proof['observed_end_unix']
    else:
        require(bool(pods) and all('finished_at' in pod and 'started_at' in pod and 'exit_code' in pod for pod in pods.values()),
                'GPU container termination evidence missing')
        finished = max(datetime.fromisoformat(pod['finished_at']).timestamp() for pod in pods.values())
        durations = [datetime.fromisoformat(pod['finished_at']).timestamp() -
                     datetime.fromisoformat(pod['started_at']).timestamp() for pod in pods.values()]
        require(all(duration >= 0 for duration in durations) and
                reservation['charged_gpu_seconds'] >= math.ceil(sum(durations) * reservation['gpus']),
                'GPU charge is smaller than container runtime')
    require(type(reservation['charged_gpu_seconds']) is int and reservation['charged_gpu_seconds'] >= 0 and
            state['started'] <= reservation['reserved_unix'] <= finished <= state['started'] + state['wall_seconds'],
            'GPU time/wall budget invalid')
    feedback = load(directory / 'feedback.json')
    require(feedback.get('uuid') == reservation['uuid'] and feedback.get('status') in ('completed', 'failed'), 'GPU outcome missing')
    require(feedback['status'] != 'completed' or (lifecycle['phase'] == 'Completed' and
            not lifecycle.get('preemption_receipt') and all(pod['exit_code'] == 0 for pod in pods.values())),
            'failed GPU task relabelled completed')
    return directory, feedback, finished


def phase4_extension(root, reservation, state):
    directory = safe_path(root / reservation['name'], root)
    request = load(directory / 'request.json')
    require(request.get('mode') == 'phase4-controller' and request.get('protocol') == 'controller-phase4-resource-v1' and
            request.get('maintenance_stock_control') is True and request.get('purpose') == 'controller-negative-control',
            'unknown or non-stock-control extension')
    require(request.get('budget_path') == str(root / 'resource-state.json'), 'extension does not share the original budget')
    directory, feedback, finished = terminal_job(root, reservation, state, controller_extension=True)
    lifecycle = load(directory / 'lifecycle-final.json')
    require(reservation.get('submission_code', 200) == 200 and lifecycle.get('pods') and
            all(type(pod.get('exit_code')) is int and pod.get('restarts') == 0 and
                pod.get('phase') == ('Succeeded' if pod['exit_code'] == 0 else 'Failed')
                for pod in lifecycle['pods'].values()), 'extension container exit/restart receipt incomplete')
    plan = load(directory / 'plan.json')
    require(plan['budget_path'] == request['budget_path'] and plan['gpus'] == reservation['gpus'] and
            plan['request'] == dict(path=str(directory / 'request.json'), sha256=sha(directory / 'request.json')) and
            plan['source'] == dict(path=str(directory / 'source.tar'), sha256=sha(directory / 'source.tar')),
            'extension request/source/resource plan changed')
    bundle = safe_path(request['bundle'], root)
    manifest = bundle / 'manifest.json'
    require(request['bundle_manifest'] == dict(path=str(manifest), sha256=sha(manifest)), 'extension bundle manifest changed')
    identity = load(manifest)
    require(request['candidate_tree_sha'] == identity['stock_tree_sha'] and
            request['bundle_candidate_tree_sha'] == identity['candidate_tree_sha'], 'stock control measured a non-canonical tree')
    require(all(feedback.get(key) is False for key in ('controller_accepted', 't3_passed', 'promoted', 'ledger_eligible')),
            'controller-only extension claims scientific acceptance')
    replayed = feedback['status'] == 'completed'
    references = {}
    if replayed:
        independent = json_record(replay_phase4_feedback(directory / 'remote', request))
        expected = dict(independent, status='completed', uuid=reservation['uuid'])
        if 'deployment' in feedback:
            require(feedback['deployment'] == dict(priority_class='higher-priority-job', privileged=False, host_network=False),
                    'extension deployment differs from the trusted contract')
            expected['deployment'] = feedback['deployment']
        require(feedback == expected, 'independent controller aggregate replay differs')
        references = {name:sha(directory / 'remote' / name) for name in ('result.json', 'replay-summary.json')}
    return dict(name=reservation['name'], uuid=reservation['uuid'], mode=request['mode'], purpose=request['purpose'],
        status=feedback['status'], terminal=reservation['terminal'], controller_only=True,
        conservative_gpu_seconds=reservation['charged_gpu_seconds'], independently_replayed=replayed,
        sealed_used=True if replayed else None, controller_accepted=False, t3_passed=False,
        aggregate_references=references, scope='controller-only terminal/archive/aggregate audit; no private body read'), finished


def audit(root):
    root = safe_path(root)
    result, state = load(root / 'pipeline-result.json'), load(root / 'resource-state.json')
    require(result.get('status') in ('research_complete', 'needs_attention'), 'pipeline still running: no closed-stage audit')
    pipeline_sha = sha(root / 'pipeline-result.json')
    snapshot = result['resource_state']
    require({key:value for key, value in snapshot.items() if key != 'jobs'} ==
            {key:value for key, value in state.items() if key != 'jobs'} and
            all(state.get(key) == value for key, value in LIMITS.items()), 'pipeline resource snapshot/authorized limits differ')
    require(len(state['jobs']) >= len(snapshot['jobs']) and state['jobs'][:len(snapshot['jobs'])] == snapshot['jobs'],
            'historical GPU records are not an unchanged ordered prefix')
    require(len({job['name'] for job in state['jobs']}) == len(state['jobs']) and
            len({job['uuid'] for job in state['jobs']}) == len(state['jobs']), 'GPU reservation name/UUID duplicated')
    require(result.get('role_processes_closed') is True, 'scientific role processes not closed')
    directories = [path for path in (root / 'master', *sorted(root.glob('direction-*')), root / 'integration', root / 'kernel')
                   if path.is_dir()]
    roles, responses, origins, totals = [], {}, {}, Counter()
    for directory in directories:
        role, native, cpu = audit_role(root, directory)
        require(not set(native).intersection(responses), 'native thread reused between roles')
        roles.append(role)
        responses.update(native)
        origins.update(cpu)
        totals.update(role['counts'])
    processes = result.get('role_processes', {})
    require(set(processes) == {role['name'] for role in roles} and
            all(type(process.get('exit_code')) is int and process['exit_code'] == 0 for process in processes.values()),
            'role exit receipts missing or nonzero')
    research = {}
    for reservation in snapshot['jobs']:
        directory = safe_path(root / reservation['name'], root)
        if directory.is_dir() and (directory / 'request.json').is_file():
            request = load(directory / 'request.json')
            if request.get('mode') == 'source-research':
                check_authorship(root, directory, request, responses, origins)
                research[str(directory)] = request
    counts = result['counters']
    for key in ('model_turns', 'cpu_runs', 'usage_updates'):
        require(counts.get(key) == totals[key], 'parallel native counter differs: ' + key)
    require(counts.get('gpu_attempts') == len(research) and counts.get('actions') == totals['actions'] + len(research),
            'research action/GPU attempt counters differ from actual requests')
    if (root / 'counters.json').exists():
        require(load(root / 'counters.json') == counts, 'pipeline counter snapshots differ')
    jobs, events, accepted, paired, charged = [], [], {}, 0, 0
    preflights = []
    reported_feedback = load(root / 'feedback.json') if (root / 'feedback.json').exists() else []
    for reservation in snapshot['jobs']:
        directory, feedback, finished = terminal_job(root, reservation, state)
        request = load(directory / 'request.json')
        mode = request['mode']
        require(mode in ('source-preflight', 'source-research', 'source-controller'), 'unknown GPU task mode')
        if mode != 'source-preflight':
            entries = [entry for entry in reported_feedback if entry.get('request_directory') == str(directory)]
            require(len(entries) == 1 and all(entries[0].get(key) == value for key, value in feedback.items()),
                    'pipeline feedback differs from original GPU result')
        if mode == 'source-research':
            require(str(directory) in research, 'GPU research request has no native lineage')
        if mode == 'source-controller':
            original = safe_path(request['diagnostic_request'], root)
            require(str(original) in research and load(original / 'feedback.json').get('status') == 'completed' and
                    sha(original / 'feedback.json') == request['diagnostic_feedback_sha256'],
                    'gate diagnostic lineage changed')
            parent = research[str(original)]
            require(request['action'] == dict(parent['action'], per_suite=6, max_new_tokens=2048) and
                    all(request[key] == parent[key] for key in ('role_thread', 'role_turn', 'role_response_sha256',
                        'patch_sha256', 'self_check_sha256', 'cpu_receipt_sha256')) and
                    all(sha(directory / name) == sha(original / name) for name in ('patch.json', 'self-check.py', 'cpu-receipt.json')),
                    'gate changed its original scientific code/role binding')
            require(any(native['role'] == 'master' and str(original) in native['value'].get('review', [])
                        for native in responses.values()), 'gate lacks native Master review authorization')
        if request.get('comparison_base_sha256'):
            comparison = safe_path(request['comparison_source'], root)
            require(sha(directory / 'comparison-base.json') == request['comparison_base_sha256'] == sha(comparison / 'patch.json'),
                    'comparison stack patch lineage differs')
        if feedback['status'] == 'completed':
            independent = json_record(replay_feedback(directory / 'remote', request))
            require(feedback == dict(independent, status='completed', uuid=reservation['uuid']), 'independent source feedback replay differs')
            if mode == 'source-controller':
                verdict = json_record(validate_campaign(directory / 'remote'))
                require(independent['controller_verdict'] == verdict and
                        independent['controller_accepted'] is verdict['joint_acceptance_passed'], 'independent gate verdict differs')
                accepted[str(safe_path(request['diagnostic_request'], root))] = verdict['joint_acceptance_passed']
            elif mode == 'source-preflight':
                require(independent.get('preflight') is True, 'preflight has no independently verified preflight outcome')
                preflights.append(feedback)
            elif mode == 'source-research':
                paired += independent['n_pairs']
        else:
            require(feedback.get('controller_accepted') is False, 'failed job claims acceptance')
        charged += reservation['charged_gpu_seconds']
        events.extend(((reservation['reserved_unix'], reservation['gpus']), (finished, -reservation['gpus'])))
        jobs.append(dict(mode=mode, status=feedback['status'], independently_replayed=feedback['status'] == 'completed'))
    prefix_charged = charged
    prefix_finished = max((timestamp for timestamp, change in events if change < 0), default=state['started'])
    extensions = []
    for reservation in state['jobs'][len(snapshot['jobs']):]:
        extension, finished = phase4_extension(root, reservation, state)
        require(reservation['reserved_unix'] >= prefix_finished, 'controller extension predates scientific GPU closure')
        charged += reservation['charged_gpu_seconds']
        events.extend(((reservation['reserved_unix'], reservation['gpus']), (finished, -reservation['gpus'])))
        extensions.append(extension)
    for request in research.values():
        if request.get('comparison_source'):
            require(accepted.get(str(safe_path(request['comparison_source'], root))) is True,
                    'comparison stack was not independently accepted')
    active = peak = 0
    for timestamp, change in sorted(events):
        active += change
        peak = max(peak, active)
        require(active >= 0, 'invalid GPU lifetime interval')
    require(active == 0 and peak <= LIMITS['concurrent_gpus'] and charged <= LIMITS['gpu_seconds'], 'stage GPU budget exceeded')
    kinds = Counter(role['kind'] for role in roles)
    pipeline_complete = result['status'] == 'research_complete'
    if pipeline_complete:
        require(kinds['Master'] == 1 and kinds['direction'] >= 2 and kinds['integration'] == kinds['kernel'] == 1 and
                all(role['counts']['model_turns'] > 0 for role in roles), 'scientific stages skipped or replaced by engineering probes')
        require(load(root / 'preflight-result.json') in preflights, 'research pipeline has no independently completed preflight')
    final = result.get('master_final', {})
    if pipeline_complete:
        require(final.get('decision') in ('final', 'stop') and
                any(native['role'] == 'master' and native['value'] == final for native in responses.values()),
                'pipeline final decision lacks native Master provenance')
    if 'controller_jobs' in counts:
        require(counts['controller_jobs'] == sum(job['mode'] == 'source-controller' for job in jobs),
                'controller job counter differs from reservations')
    controller_accepted = final.get('decision') == 'final' and accepted.get(final.get('request_directory')) is True
    require(result.get('controller_accepted', False) == controller_accepted and result.get('promoted') is False and
            result.get('sealed_completed') is False, 'pipeline scientific completion claims lack evidence')
    require(load(root / 'resource-state.json') == state and sha(root / 'pipeline-result.json') == pipeline_sha,
            'live budget or historical pipeline changed during audit')
    return dict(engineering_evidence_verified=True, pipeline_completed=pipeline_complete,
        stage_status=result['status'], controller_accepted=controller_accepted, real_engine_rsi_completed=False,
        sealed_used=False, candidate_promoted=False, scientific_roles=len(roles), native_turns=totals['model_turns'],
        tool_actions=totals['actions'], cpu_budget_charges=totals['cpu_runs'], python_executions=totals['python_executions'],
        skill_calls=totals['skill_calls'], skills_completed=totals['skills_completed'],
        skills_unavailable=totals['skills_unavailable'], skills_rejected=totals['skills_rejected'],
        research_attempts=len(research), controller_gate_attempts=sum(job['mode'] == 'source-controller' for job in jobs),
        preflight_gpu_jobs=sum(job['mode'] == 'source-preflight' for job in jobs), terminated_gpu_jobs=len(jobs) + len(extensions),
        completed_diagnostics=sum(job['mode'] == 'source-research' and job['independently_replayed'] for job in jobs),
        failed_gpu_jobs=sum(job['status'] == 'failed' for job in (*jobs, *extensions)), paired_rows=paired,
        conservative_gpu_seconds=charged, peak_reserved_concurrent_gpus=peak,
        scientific_prefix=dict(resource_snapshot_sha256=object_sha(snapshot), pipeline_result_sha256=pipeline_sha,
            terminated_gpu_jobs=len(jobs), conservative_gpu_seconds=prefix_charged, counters=counts, sealed_used=False),
        controller_phase4_extension_occurred=bool(extensions), controller_extensions=extensions,
        sealed_used_scope='scientific prefix only; controller-only extensions reported separately',
        scope='read-only native lineage/accounting audit; failures/unavailable retain their own status, not scientific passes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = audit(arguments.directory)
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(json.dumps(dict(engineering_evidence_verified=False, error=type(error).__name__ + ': ' + str(error))))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
