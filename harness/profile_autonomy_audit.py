"""Read-only native lineage, observation registration and bounded stage audit."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import tarfile
import time

from controller.dev_campaign import validate_campaign
from controller.phase4_final import trusted_metadata, validate_shutdown
from exp.engine_resource import IMAGE, ROOT, command as engine_command
from exp.profile_capture import validate_action as profile_action, validate_request as capture_request
from exp.profile_resource import feedback as replay_profile_feedback
from exp.source_resource import feedback as replay_source_feedback
from harness.engine_research import json_record
from harness.gpu_autonomy import job_rows
from harness import skill_rsi_audit as native_audit
from harness.skill_diagnostics import PROFILE_ONLY_PROTOCOL, checked_manifest, kernel_statistics, observed_shape_facts, read_trace


LIMITS = dict(gpu_seconds=28800, wall_seconds=43200, concurrent_gpus=2)
MODES = frozenset(('stock-profile', 'source-preflight', 'source-research', 'source-controller'))
require = native_audit.require


def public_path(path, within=None):
    path = Path(path).absolute()
    for candidate in (path, path.resolve()):
        require(not set(candidate.parts).intersection(('..', 'sealed', 'private', 'eval', '.git', '.config')) and
                candidate.name != 'auth.json', 'protected evidence is not readable by this public-stage audit')
    return native_audit.safe_path(path, within)


def load(path):
    return native_audit.load(public_path(path))


def sha(path):
    return native_audit.sha(public_path(path))


def reference(path):
    path = public_path(path)
    return dict(path=str(path), sha256=sha(path))


def frozen_sources(directory):
    source = directory / 'source.tar'
    identity = load(directory / 'source-identity.json')
    require(identity.get('archive', reference(source)) == reference(source) and
            identity.get('archive_sha256', sha(source)) == sha(source), 'frozen source archive SHA differs')
    files = identity['files']
    with tarfile.open(public_path(source)) as archive:
        members = archive.getmembers()
        require(bool(files) and len(members) == len(files) and set(archive.getnames()) == set(files),
                'archive inventory is incomplete or duplicated')
        for member in members:
            path = Path(member.name)
            require(member.isfile() and not path.is_absolute() and member.name == path.as_posix() and
                    not set(path.parts).intersection(('..', 'sealed', 'private', 'eval', '.git', '.config')) and
                    path.name != 'auth.json', 'protected or nonregular frozen source member')
            require(hashlib.sha256(archive.extractfile(member).read()).hexdigest() == files[member.name],
                    'frozen execution source content differs')
    return files


def terminal_job(root, reservation, state):
    require(reservation.get('terminated') is True and type(reservation.get('create_calls')) is int and reservation.get('create_calls') == 1 and
            reservation.get('submission_code') == 200, 'GPU task active or submission uncertain')
    name, uuid = reservation['name'], reservation['uuid']
    require(isinstance(name, str) and Path(name).name == name and
            isinstance(uuid, str) and re.fullmatch('job-[a-z0-9-]+', uuid), 'GPU reservation identity invalid')
    directory = public_path(root / name, root)
    request, pending, submitted, lifecycle = [load(directory / item) for item in
        ('request.json', 'pending.json', 'submitted.json', 'lifecycle-final.json')]
    mode = request['mode']
    require(mode in MODES, 'unknown task mode in this public stage')
    gpus = 1 if mode == 'stock-profile' else 2
    deadline = {'stock-profile':2700, 'source-preflight':1200,
                'source-research':3600, 'source-controller':7200}[mode]
    require(all(type(value) is int for value in (reservation['gpus'], pending['total_gpus'], pending['nodes'],
                pending['gpu_per_node'], pending['deadline_seconds'], reservation['seconds'])) and
            reservation['gpus'] == pending['total_gpus'] == gpus and
            pending['nodes'] == 1 and pending['gpu_per_node'] == gpus and
            pending['deadline_seconds'] == deadline and reservation['seconds'] == deadline + 1200 and
            pending['request_sha256'] == sha(directory / 'request.json') and
            pending['source_sha256'] == sha(directory / 'source.tar') and pending['image'] == IMAGE,
            'GPU request/source/resource identity differs')
    require(submitted == dict(uuid=uuid, code=200, name=name) and lifecycle['uuid'] == uuid and
            lifecycle['phase'] == reservation['terminal'] and
            lifecycle['phase'] in ('Completed', 'Failed', 'Aborted', 'Terminated') and
            lifecycle['conservative_gpu_seconds'] == reservation['charged_gpu_seconds'],
            'GPU terminal/submission identity differs')
    require(not job_rows(public_path(directory / 'pre-submit-query.txt').read_text(), name), 'duplicate pre-submit task')
    matches = job_rows(public_path(directory / 'post-submit-query.txt').read_text(), name)
    require(len(matches) == 1 and matches[0].get('name') == uuid and
            re.search(r'''["']code["']\s*:\s*200''', public_path(directory / 'submit.txt').read_text()),
            'submission lacks code200 and a unique UUID lookup')
    require(load(directory / 'submit-exit.json')['create_calls'] == 1, 'submission create counter differs')
    files = frozen_sources(directory)
    cli = pending['command']
    for flag, expected in (('--nnodes', '1'), ('--gpu-per-node', str(gpus)),
                           ('--k8s-priority', '3'), ('--k8s-images', IMAGE)):
        require(cli.count(flag) == 1 and cli[cli.index(flag) + 1] == expected, 'frozen CLI resource drift')
    prefix = 'SP_PROFILE_' if mode == 'stock-profile' else 'SP_SOURCE_'
    bootstrap = 'exp/profile_remote.sh' if mode == 'stock-profile' else 'exp/source_remote.sh'
    assignments = shlex.split(cli[-1])
    source_key = 'SOURCE_SHA' if mode == 'stock-profile' else 'ARCHIVE_SHA'
    require(prefix + 'BOOTSTRAP_SHA=' + files[bootstrap] in assignments and
            prefix + source_key + '=' + pending['source_sha256'] in assignments and
            prefix + 'REQUEST_SHA=' + pending['request_sha256'] in assignments,
            'executed bootstrap/request/archive is not the frozen source identity')
    expected = engine_command(directory / 'request.json', directory / 'source.tar', directory / 'remote', name, deadline)
    if mode == 'stock-profile':
        expected[expected.index('exp.engine_northjob')] = 'exp.profile_resource'
        expected[expected.index('--gpu-per-node') + 1] = '1'
    expected[-1] = shlex.join(['env', prefix + 'BOOTSTRAP_SHA=' + files[bootstrap],
        prefix + source_key + '=' + pending['source_sha256'], prefix + 'REQUEST_SHA=' + pending['request_sha256'],
        'bash', str(ROOT / bootstrap), str(directory / 'request.json'), str(directory / 'source.tar'),
        str(directory / 'remote'), str(deadline)])
    require(cli == expected, 'execution command differs from the trusted frozen workload')
    charged = reservation['charged_gpu_seconds']
    require(type(charged) is int and charged >= 0, 'invalid GPU charge')
    pods = lifecycle['pods']
    if lifecycle.get('preemption_receipt'):
        proof_ref = lifecycle['preemption_receipt']
        proof_path = public_path(proof_ref['path'], directory)
        require(reference(proof_path) == proof_ref, 'preemption proof changed')
        proof = load(proof_path)
        require(proof['uuid'] == uuid and proof['phase'] == lifecycle['phase'] and
                proof['terminal_job_and_pod_absence_confirmed'] is True and proof['reason'] == 'JobPreempted' and
                proof['conservative_gpu_seconds'] == charged and
                any(event.get('reason') == 'JobPreempted' and event.get('involved_name') == uuid for event in proof['events']),
                'invalid preemption termination proof')
        finished = proof['observed_end_unix']
    else:
        require(bool(pods), 'GPU termination has no container receipt')
        durations, endings = [], []
        for pod in pods.values():
            started = datetime.fromisoformat(pod['started_at']).timestamp()
            ended = datetime.fromisoformat(pod['finished_at']).timestamp()
            require(type(pod['exit_code']) is int and pod.get('restarts') == 0 and ended >= started and
                    pod.get('phase') == ('Succeeded' if pod['exit_code'] == 0 else 'Failed'),
                    'container exit/restart/timing evidence invalid')
            durations.append(ended - started)
            endings.append(ended)
        finished = max(endings)
        require(charged >= math.ceil(math.fsum(durations) * gpus), 'GPU charge is below actual container runtime')
    require(all(type(value) in (int, float) and math.isfinite(value) for value in
                (state['started'], reservation['reserved_unix'], finished)) and
            state['started'] <= reservation['reserved_unix'] <= finished <= state['started'] + LIMITS['wall_seconds'],
            'GPU lifetime exceeds the authorized wall budget')
    feedback = load(directory / 'feedback.json')
    require(feedback.get('uuid') == uuid and feedback.get('status') in ('completed', 'failed'), 'GPU outcome missing')
    if feedback['status'] == 'completed':
        require(lifecycle['phase'] == 'Completed' and not lifecycle.get('preemption_receipt') and
                pods and all(pod['exit_code'] == 0 for pod in pods.values()), 'failed task relabelled completed')
    else:
        require(feedback.get('controller_accepted') is False, 'failed task claims acceptance')
    return directory, request, feedback, finished


def profile_identity(directory, request, root):
    require(request.get('protocol') == 'bounded-stock-profile-resource-v1' and type(request.get('gpus')) is int and request.get('gpus') == 1 and
            request.get('deadline') == 2700 and request.get('budget_path') == str(root / 'resource-state.json'),
            'profile envelope does not share this stage budget')
    capture_request(request['capture'])
    require(request['capture']['source_archive'] == reference(directory / 'source.tar') and
            request['action'] == request['capture']['action'], 'profile capture/archive action differs')
    for item in (request['capture']['base_spec'], *request['capture']['dev_sources'].values()):
        public_path(item['path'])
    if request['capture']['bundle'] is not None:
        public_path(request['capture']['bundle']['path'])
    plan = load(directory / 'plan.json')
    require(plan['request'] == reference(directory / 'request.json') and plan['source'] == reference(directory / 'source.tar') and
            plan['budget_path'] == request['budget_path'] and plan['total_gpus'] == 1 and plan['deadline'] == 2700 and
            plan['command'] == load(directory / 'pending.json')['command'], 'profile frozen plan differs')


def profile_binding(directory, request):
    binding = load(directory / 'resource-binding.json')
    output = directory / 'remote'
    require(binding.get('request') == reference(directory / 'request.json') and
            binding.get('source') == reference(directory / 'source.tar') and
            binding.get('capture') == request['capture'] and load(output / 'request.json') == request['capture'] and
            binding.get('result_sha256') == sha(output / 'result.json'), 'profile resource binding/capture changed')


def process_closure(root, result, roles, preflight_finished):
    closure = load(root / 'process-closure.json')
    require(result.get('role_processes_closed') is True and closure.get('role_processes_closed') is True,
            'native processes are not closed')
    registry_ref = closure['shutdown_registry']
    public_path(registry_ref['path'], root / 'processes')
    owner = public_path(root / 'process-closure.json').stat().st_uid
    registry = trusted_metadata(registry_ref, owner)
    require(closure['process_members'] == registry['members'], 'process closure inventory differs')
    for member in registry['members']:
        for item in ('birth', 'exit'):
            public_path(member[item]['path'], root / 'processes')
    validate_shutdown(registry, broker_uid=owner, opened_unix=time.time())
    receipts = {}
    for member in registry['members']:
        birth, ended = trusted_metadata(member['birth'], owner), trusted_metadata(member['exit'], owner)
        child = birth['identity']
        require(result['resource_state']['started'] <= birth['observed_unix'] <= ended['reaped_unix'] <=
                registry['closed_unix'] <= result['resource_state']['started'] + LIMITS['wall_seconds'],
                'process lifecycle exceeds this stage wall budget')
        require(child['pid'] not in receipts, 'process PID reused in closure registry')
        receipts[child['pid']] = (birth, ended)
    processes = result['role_processes']
    require(set(processes) == {role['name'] for role in roles} and
            len({process['pid'] for process in processes.values()}) == len(processes), 'scientific role exit inventory differs')
    for process in processes.values():
        require(process['pid'] in receipts and type(process['exit_code']) is int, 'native role lacks actual birth/exit')
        birth, ended = receipts[process['pid']]
        require(ended['returncode'] == process['exit_code'] == 0 and birth['observed_unix'] >= preflight_finished,
                'native role exit or current-stage readiness chronology differs')
    require({public_path(path) for pattern in ('birth-*.json', 'exit-*.json') for path in (root / 'processes').glob(pattern)} ==
            {public_path(member[item]['path']) for member in registry['members'] for item in ('birth', 'exit')},
            'orphan process birth/exit receipt')
    return len(receipts)


def registrations(root, entries, jobs, responses, initial):
    require(isinstance(entries, list) and len(entries) <= 4, 'global profile request allocation exceeded')
    registered, seen, successful_keys = {}, set(), set()
    for number, entry in enumerate(entries, 1):
        directory = public_path(entry['directory'], root)
        require(directory.parent == root and directory.name not in seen and directory.name in jobs,
                'profile request has no unique actual reservation')
        seen.add(directory.name)
        job = jobs[directory.name]
        request, binding = job['request'], entry['role_binding']
        require(job['mode'] == 'stock-profile' and request['role_binding'] == binding and request['action'] == entry['action'],
                'profile entry/request role binding differs')
        profile_action(entry['action'])
        require(set(binding) == {'role', 'thread', 'turn', 'response'}, 'profile role binding schema differs')
        require(type(binding['turn']) is int and binding['turn'] >= 1 and isinstance(binding['thread'], str),
                'profile native turn identity has an invalid type')
        key = (binding['role'], entry['action']['workload_id'], entry['action']['preset'])
        require(key not in successful_keys, 'same-role successful observation was resubmitted instead of reused')
        response = responses.get((binding['thread'], binding['turn']))
        response_path = root / binding['role'] / f'turn-{binding["turn"]:02d}-response.json'
        require(response is not None and response['role'] == binding['role'] and
                binding['response'] == reference(response_path) and response['sha256'] == binding['response']['sha256'] and
                response['value'].get('action') == dict(kind='request_stock_profile', **entry['action']),
                'profile request lacks exact native role/thread/turn/action provenance')
        if job['status'] != 'completed':
            require('result' not in entry, 'failed profile request registered successful evidence')
            continue
        independent = job['independent']
        successful_keys.add(key)
        manifests = independent['profile_inputs']
        identifiers = [f'profile-{number:02d}-{index:02d}' for index in range(len(manifests))]
        answer = entry['result']
        require(manifests and answer.get('status') == 'completed' and answer.get('cached') is False and
                answer.get('evidence_ids') == identifiers and answer.get('workload_id') == entry['action']['workload_id'] and
                answer.get('preset') == entry['action']['preset'] and answer.get('controller_accepted') is False and
                answer.get('stage_attribution_validated') is False and answer.get('shape_status') == 'unknown',
                'profile registration result differs from independently replayed capture')
        for identity, manifest in zip(identifiers, manifests):
            path = root / 'profile-evidence' / binding['role'] / (identity + '.json')
            require(load(path) == manifest, 'registered profile manifest differs from original capture')
            checked_manifest(manifest)
            require(manifest['protocol'] == PROFILE_ONLY_PROTOCOL and manifest['workload'] is None,
                    'registered observation invents certified workload shape')
            registered[(binding['role'], identity)] = dict(manifest=manifest, path=public_path(path), turn=binding['turn'])
    require(seen == {name for name, job in jobs.items() if job['mode'] == 'stock-profile' and
                    job['request']['role_binding'] is not None}, 'orphan role-bound profile reservation')
    require({public_path(path) for path in (root / 'profile-evidence').rglob('*.json')} ==
            {item['path'] for item in registered.values()}, 'unregistered or cross-role profile evidence file')
    return registered


def skill_registrations(root, roles, registered, initial, initial_path):
    for role in roles:
        for path in sorted((root / role['name']).glob('tools-*/action-*/request.json')):
            request = load(path)
            action = request['arguments']['action']
            if action['kind'] not in ('run_skill', 'read_profile_shapes'):
                continue
            returned = load(path.parent / 'response.json')
            if returned['success'] is not True:
                continue
            answer = json.loads(returned['contentItems'][0]['text'])
            identity = action['evidence']
            if identity == 'stock':
                manifest = initial
                manifest_path = initial_path
            else:
                item = registered.get((role['name'], identity))
                ordinal = int(path.parent.parent.name.removeprefix('tools-'))
                require(item is not None and ordinal > item['turn'], 'skill evidence not registered to this role before its turn')
                manifest = item['manifest']
                manifest_path = item['path']
            if action['kind'] == 'read_profile_shapes':
                require(set(action) == {'kind', 'evidence', 'offset'} and type(action['offset']) is int and
                        action['offset'] >= 0, 'shape page action schema/offset differs')
                require(load(path.parent / 'execution/result.json') == answer and
                        set(answer) == {'status', 'kind', 'role', 'evidence', 'manifest_sha256', 'observed_shape_facts',
                            'independent_discovery', 'gpu_submissions', 'scope'} and
                        answer['status'] == 'completed' and answer['kind'] == 'read_profile_shapes' and
                        answer['role'] == role['kind'] and answer['evidence'] == identity and
                        answer['manifest_sha256'] == sha(manifest_path) and answer['independent_discovery'] is False and
                        type(answer['gpu_submissions']) is int and answer['gpu_submissions'] == 0,
                        'shape page return differs from its authorized execution receipt')
                trace, config, shape = checked_manifest(manifest)
                require(shape is None and manifest['protocol'] == PROFILE_ONLY_PROTOCOL,
                        'shape page used uncertified input as a validated workload')
                facts = observed_shape_facts(read_trace(trace), manifest['trace']['sha256'], offset=action['offset'])
                require(native_audit.object_sha(answer['observed_shape_facts']) == native_audit.object_sha(facts),
                        'shape page differs from independent authorized-trace replay')
                continue
            caches = [path for path in (root / 'skill-cache').glob('*/result.json') if sha(path) == answer['result_sha256']]
            require(len(caches) == 1, 'skill has no unique immutable cache')
            cache = load(caches[0])
            require(cache['input_identity'] == manifest, 'skill cache substituted registered evidence')
            trace, config, shape = checked_manifest(manifest)
            require(shape is None and manifest['protocol'] == PROFILE_ONLY_PROTOCOL, 'profile skill used uncertified shape as workload')
            events = read_trace(trace)
            facts = observed_shape_facts(events, manifest['trace']['sha256'])
            require(native_audit.object_sha(cache.get('kernel_statistics')) ==
                    native_audit.object_sha(kernel_statistics(events)),
                    'cached kernel statistics differ from independent authorized-trace replay')
            require(cache.get('observed_shape_facts') == facts, 'skill observed facts differ from actual trace')
            for tool in ('extract', 'profiler'):
                receipt = cache['tools'][tool]
                require(receipt.get('exit_code') == 0 and receipt.get('timed_out') is False and
                        set(receipt['output_sha256']) == {'stdout', 'stderr'}, 'profile skill lacks actual executed receipts')
            for tool in ('compute', 'pipeline'):
                require(cache['tools'][tool].get('status') == 'unavailable' and
                        'output_sha256' not in cache['tools'][tool], 'unknown shape was converted to computed workload')
            if action['skill'] == 'profiler':
                require(answer.get('observed_shape_facts') == facts and
                        answer.get('kernel_statistics') == cache['kernel_statistics'] and
                        answer.get('text') == public_path(caches[0].parent / 'profiler.stdout.txt').read_text()[:18000].replace(
                            str(caches[0].parent), '<diagnostic-artifact>') and
                        answer.get('stage_attribution_validated') is False, 'profiler answer differs from registered observation')
            if action['skill'] in ('compute', 'pipeline'):
                require(answer['status'] == 'unavailable' and 'estimate' not in answer, 'unavailable profile skill claims an estimate')


def _audit(root):
    root = public_path(root)
    result_path = root / 'profile-campaign-result.json'
    result, pipeline, state = load(result_path), load(root / 'pipeline-result.json'), load(root / 'resource-state.json')
    identities = {path:sha(root / path) for path in ('profile-campaign-result.json', 'pipeline-result.json', 'resource-state.json')}
    require(result.get('status') in ('research_complete', 'needs_attention'), 'profile campaign is still running')
    require(all(result.get(key) == value for key, value in pipeline.items()), 'pipeline and final profile snapshots differ')
    require(result['resource_state'] == state and all(type(state.get(key)) is int and state[key] == value
            for key, value in LIMITS.items()), 'new stage resource snapshot/authorized limits differ')
    require(result.get('prior_sealed_reused') is False and result.get('sealed_completed') is False and
            result.get('promoted') is False and result.get('real_engine_rsi_completed', False) is False,
            'public stage claims prior sealed reuse or unsupported completion')
    reservations = state['jobs']
    require(len({row['name'] for row in reservations}) == len(reservations) and
            len({row.get('uuid') for row in reservations}) == len(reservations), 'duplicate job name/UUID')
    require(all(public_path(path.parent).name in {row['name'] for row in reservations}
                for path in root.glob('*/pending.json')), 'orphan uncertain submission outside the stage budget')
    roles, responses, origins, totals = [], {}, {}, Counter()
    directories = [path for path in (root / 'master', *sorted(root.glob('direction-*')), root / 'integration', root / 'kernel')
                   if path.is_dir()]
    if (root / 'tools.json').exists():
        public_path(load(root / 'tools.json')['root'])
    for directory in directories:
        manifest = load(directory / 'manifest.json')
        for key in ('canary', 'home', 'work'):
            public_path(manifest[key])
        role, native, cpu = native_audit.audit_role(root, directory, allow_format_retries=True)
        require(not set(native).intersection(responses), 'native thread crossed roles')
        roles.append(role)
        responses.update(native)
        origins.update(cpu)
        totals.update(role['counts'])
    entries = result['profile_requests']
    if (root / 'profile-requests.json').exists():
        require(load(root / 'profile-requests.json') == entries, 'profile request snapshots differ')
    jobs, events, accepted = {}, [], {}
    for reservation in reservations:
        directory, request, feedback, finished = terminal_job(root, reservation, state)
        mode = request['mode']
        if mode == 'stock-profile':
            profile_identity(directory, request, root)
        if mode == 'source-research':
            native_audit.check_authorship(root, directory, request, responses, origins)
        independent = None
        if feedback['status'] == 'completed':
            if mode == 'stock-profile':
                profile_binding(directory, request)
                independent = json_record(replay_profile_feedback(directory / 'remote', request))
                require(independent.get('capture_completed') is True and independent.get('option_enabled') is False and
                        independent.get('controller_accepted') is False and independent.get('workload') is None and
                        independent.get('shape_status') == 'unknown', 'stock observation claims unsupported scientific acceptance')
            else:
                independent = json_record(replay_source_feedback(directory / 'remote', request))
            require(feedback == dict(independent, status='completed', uuid=reservation['uuid']), 'independent original-package feedback differs')
            if mode == 'source-controller':
                verdict = json_record(validate_campaign(directory / 'remote'))
                require(independent['controller_verdict'] == verdict and
                        independent['controller_accepted'] is verdict['joint_acceptance_passed'], 'independent dev gate differs')
                accepted[str(public_path(request['diagnostic_request'], root))] = verdict['joint_acceptance_passed']
        jobs[directory.name] = dict(mode=mode, status=feedback['status'], request=request,
            independent=independent, feedback=feedback, finished=finished, gpus=reservation['gpus'])
        events.extend(((reservation['reserved_unix'], reservation['gpus']), (finished, -reservation['gpus'])))
    research = {name:job for name, job in jobs.items() if job['mode'] == 'source-research'}
    reported = load(root / 'feedback.json') if (root / 'feedback.json').exists() else []
    for name, job in jobs.items():
        request = job['request']
        if job['mode'] in ('source-research', 'source-controller'):
            matching = [item for item in reported if item.get('request_directory') == str(root / name)]
            require(len(matching) == 1 and all(matching[0].get(key) == value for key, value in job['feedback'].items()),
                    'reported source feedback differs from original job')
        if job['mode'] == 'source-controller':
            parent = public_path(request['diagnostic_request'], root)
            require(parent.name in research and research[parent.name]['status'] == 'completed' and
                    request['diagnostic_feedback_sha256'] == sha(parent / 'feedback.json'), 'dev gate diagnostic lineage differs')
            original = research[parent.name]['request']
            require(request['action'] == dict(original['action'], per_suite=6, max_new_tokens=2048) and
                    all(request[key] == original[key] for key in ('role_thread', 'role_turn', 'role_response_sha256',
                        'patch_sha256', 'self_check_sha256', 'cpu_receipt_sha256')) and
                    all(sha(root / name / item) == sha(parent / item) for item in ('patch.json', 'self-check.py', 'cpu-receipt.json')) and
                    any(native['role'] == 'master' and str(parent) in native['value'].get('review', []) for native in responses.values()),
                    'dev gate changed native scientific authorship or lacks Master review')
        if request.get('comparison_source'):
            comparison = public_path(request['comparison_source'], root)
            require(accepted.get(str(comparison)) is True and
                    sha(root / name / 'comparison-base.json') == request['comparison_base_sha256'] == sha(comparison / 'patch.json'),
                    'comparison stack lacks current-stage independent acceptance')
    preflight = public_path(result['preflight_directory'], root)
    require(preflight.parent == root and preflight.name in jobs, 'readiness is not from this new stage')
    ready = jobs[preflight.name]
    require(ready['mode'] == 'stock-profile' and ready['status'] == 'completed' and
            ready['request']['role_binding'] is None, 'readiness is not a completed trusted single-card stock profile')
    initial_ref = result['initial_evidence']
    initial_path = public_path(initial_ref['path'], root)
    require(reference(initial_path) == initial_ref, 'initial evidence SHA changed')
    initial = load(initial_path)
    require(initial in ready['independent']['profile_inputs'] and initial['protocol'] == PROFILE_ONLY_PROTOCOL and
            checked_manifest(initial)[2] is None, 'initial stock evidence is not from selected current-stage readiness')
    registered = registrations(root, entries, jobs, responses, initial)
    skill_registrations(root, roles, registered, initial, initial_path)
    counts = result['counters']
    require(load(root / 'counters.json') == counts, 'campaign counter snapshots differ')
    for key in ('model_turns', 'cpu_runs', 'usage_updates'):
        require(type(counts.get(key)) is int and counts[key] == totals[key], 'native counter differs: ' + key)
    require(all(type(counts.get(key)) is int for key in ('gpu_attempts', 'controller_jobs', 'actions')) and
            counts.get('gpu_attempts') == len(research) and counts.get('controller_jobs') ==
            sum(job['mode'] == 'source-controller' for job in jobs.values()) and
            counts.get('actions') == totals['actions'] + len(research) + len(entries), 'profile/source/action counters differ')
    require(counts['actions'] <= 900 and counts['model_turns'] <= 96 and counts['cpu_runs'] <= 192 and
            counts['usage_updates'] <= 3072 and counts['gpu_attempts'] <= 16, 'native stage resource counters exceeded')
    for role in roles:
        attempts = sum(job['mode'] == 'source-research' and job['request']['role_thread'] == role['thread'] or
            job['mode'] == 'stock-profile' and job['request']['role_binding'] is not None and
            job['request']['role_binding']['role'] == role['name'] for job in jobs.values())
        allocation = 2
        packet = load(Path(load(root / role['name'] / 'manifest.json')['work']) / 'inputs/evidence.json')
        if role['kind'] == 'direction':
            allocation = packet.get('assignment', {}).get('allocation', {}).get('gpu_attempts', 2)
        elif role['kind'] in ('integration', 'kernel'):
            allocation = 2
        require(type(allocation) is int and attempts <= allocation, 'combined role profile/source GPU allocation exceeded')
    charged = sum(row['charged_gpu_seconds'] for row in reservations)
    active = peak = 0
    for timestamp, change in sorted(events):
        active += change
        peak = max(peak, active)
        require(active >= 0, 'GPU lifetime accounting invalid')
    require(active == 0 and peak <= LIMITS['concurrent_gpus'] and charged <= LIMITS['gpu_seconds'], 'live stage GPU budget exceeded')
    processes = process_closure(root, result, roles, ready['finished'])
    complete = result['status'] == 'research_complete'
    kinds = Counter(role['kind'] for role in roles)
    final = result.get('master_final', {})
    if complete:
        require(kinds['Master'] == 1 and kinds['direction'] >= 2 and kinds['integration'] == kinds['kernel'] == 1 and
                all(role['counts']['model_turns'] > 0 for role in roles), 'scientific role coverage is incomplete')
        require(final.get('decision') in ('stop', 'final') and
                any(native['role'] == 'master' and native['value'] == final for native in responses.values()),
                'final Master decision lacks native provenance')
    controller_accepted = final.get('decision') == 'final' and accepted.get(final.get('request_directory')) is True
    require(result.get('controller_accepted', False) == controller_accepted, 'pipeline claims unsupported controller acceptance')
    require(all(sha(root / path) == digest for path, digest in identities.items()), 'stage changed during read-only audit')
    return dict(protocol='profile-autonomy-audit-v1', engineering_evidence_verified=True,
        stage_status=result['status'], pipeline_completed=complete, scientific_roles=len(roles),
        native_turns=totals['model_turns'], format_rejections=totals['format_rejections'],
        tool_actions=totals['actions'], cpu_budget_charges=totals['cpu_runs'],
        python_executions=totals['python_executions'], skill_calls=totals['skill_calls'],
        skills_completed=totals['skills_completed'], skills_unavailable=totals['skills_unavailable'],
        skills_rejected=totals['skills_rejected'], research_attempts=len(research),
        profile_gpu_jobs=len(entries), registered_profile_evidence=len(registered),
        preflight_gpu_jobs=sum(job['mode'] == 'source-preflight' or job['mode'] == 'stock-profile' and
            job['request']['role_binding'] is None for job in jobs.values()),
        controller_gate_attempts=sum(job['mode'] == 'source-controller' for job in jobs.values()),
        terminated_gpu_jobs=len(jobs), failed_gpu_jobs=sum(job['status'] == 'failed' for job in jobs.values()),
        completed_diagnostics=sum(job['status'] == 'completed' for job in research.values()),
        conservative_gpu_seconds=charged, peak_reserved_concurrent_gpus=peak, verified_processes=processes,
        controller_accepted=controller_accepted, sealed_used=False, candidate_promoted=False, real_engine_rsi_completed=False,
        references=identities, scope='Public stock observations and dev research lineage only; role exits are not optimization completion.')


def audit(root):
    try:
        return _audit(root)
    except (KeyError, TypeError, OSError, tarfile.TarError) as error:
        raise ValueError('incomplete or malformed public-stage audit evidence: ' + str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
