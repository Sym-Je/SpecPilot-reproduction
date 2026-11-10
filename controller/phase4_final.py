"""Independent controller-only Phase4 finalization; never promotes or writes a ledger."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import tarfile
import time

from controller.sealed_protocol import _frozen, _private, _save


FINAL = 'controller-phase4-final-v1'
REGISTRY = 'controller-research-shutdown-v2'
LEGACY = 'controller-legacy-research-shutdown-v1'


def identity(pid=None):
    pid = os.getpid() if pid is None else pid
    base = Path(f'/proc/{pid}')
    fields = (base / 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, start_ticks=int(fields[19]), parent_pid=int(fields[1]), uid=base.stat().st_uid,
        host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        pid_namespace_inode=(base / 'ns/pid').stat().st_ino)


def trusted_metadata(reference, uid):
    path = Path(reference['path']).absolute()
    info = path.stat()
    if (path != path.resolve() or not stat.S_ISREG(info.st_mode) or info.st_uid != uid or
            stat.S_IMODE(info.st_mode) & 0o077 or
            hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']):
        raise ValueError('trusted producer UID/owner-only metadata/SHA required')
    return json.loads(path.read_bytes())


def record_birth(process, role, directory):
    """Broker calls immediately after its own Popen, never with role-provided PID metadata."""
    directory = _private(directory, directory=True)
    child = identity(process.pid)
    if not isinstance(role, str) or not role or child['parent_pid'] != os.getpid() or process.poll() is not None:
        raise ValueError('a live broker-owned child and explicit role required')
    return _save(directory / f'birth-{process.pid}-{child["start_ticks"]}.json',
                 dict(schema='controller-process-birth-v1', role=role, identity=child, observed_unix=time.time()))


def record_exit(process, birth, directory, *, timeout=None):
    directory = _private(directory, directory=True)
    started = trusted_metadata(birth, os.geteuid())
    if started['identity']['pid'] != process.pid:
        raise ValueError('wait receipt does not belong to the recorded child')
    returncode = process.wait(timeout=timeout)
    return _save(directory / f'exit-{process.pid}-{started["identity"]["start_ticks"]}.json',
        dict(schema='controller-process-exit-v1', birth=birth, returncode=returncode, reaped_unix=time.time()))


def close_registry(directory, members):
    """Freeze the broker's complete role inventory, including Master/Integration/Kernel when started."""
    directory = _private(directory, directory=True)
    value = dict(schema=REGISTRY, members=list(members), closed_unix=time.time(), broker=identity())
    validate_shutdown(value, broker_uid=os.geteuid(), opened_unix=time.time())
    return _save(directory / 'shutdown-registry.json', value)


def validate_shutdown(value, *, broker_uid, opened_unix, check_current_processes=True):
    if (value.get('schema') != REGISTRY or not value.get('members') or
            value['broker']['uid'] != broker_uid or not value['closed_unix'] <= opened_unix):
        raise ValueError('complete actual research birth/exit registry before opening required')
    seen = set()
    current = identity() if check_current_processes else None
    for member in value['members']:
        birth = trusted_metadata(member['birth'], broker_uid)
        ended = trusted_metadata(member['exit'], broker_uid)
        child = birth['identity']
        key = (child['host_boot_id'], child['pid_namespace_inode'], child['pid'], child['start_ticks'])
        if (birth.get('schema') != 'controller-process-birth-v1' or not birth.get('role') or key in seen or
                child['parent_pid'] != value['broker']['pid'] or child['start_ticks'] < 1 or
                child['host_boot_id'] != value['broker']['host_boot_id'] or
                child['pid_namespace_inode'] != value['broker']['pid_namespace_inode'] or
                ended.get('schema') != 'controller-process-exit-v1' or ended['birth'] != member['birth'] or
                type(ended.get('returncode')) is not int or
                not birth['observed_unix'] <= ended['reaped_unix'] <= value['closed_unix']):
            raise ValueError('research birth/exit identity or chronology mismatch')
        seen.add(key)
        if current is not None and (child['host_boot_id'], child['pid_namespace_inode']) == (
                current['host_boot_id'], current['pid_namespace_inode']):
            try:
                live = identity(child['pid'])
            except (FileNotFoundError, ProcessLookupError):
                continue
            if live['start_ticks'] == child['start_ticks']:
                raise ValueError('research process is still present')
    return len(seen)


def _legacy_role_records(root, pipeline):
    processes = pipeline.get('role_processes', {})
    names = {'master', 'integration', 'kernel'} | {path.name for path in root.glob('direction-*') if path.is_dir()}
    if (len(names) != 6 or set(processes) != names or pipeline.get('status') != 'research_complete' or
            pipeline.get('role_processes_closed') is not True or
            len({row.get('pid') for row in processes.values()}) != 6):
        raise ValueError('complete six-role closed native pipeline required')
    roles = []
    for name in sorted(names):
        process = processes[name]
        if type(process.get('pid')) is not int or process['pid'] <= 0 or type(process.get('exit_code')) is not int or process['exit_code'] != 0:
            raise ValueError('six distinct original PIDs and actual exit0 receipts required')
        directory = root / name
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        expected = 'Master' if name == 'master' else 'direction' if name.startswith('direction-') else name
        if manifest.get('role') != expected:
            raise ValueError('native role kind differs from complete pipeline inventory')
        work, home, canary = (Path(manifest[key]) for key in ('work', 'home', 'canary'))
        temporary = work.parent
        contexts = [directory, temporary, work, home]
        if (directory != directory.resolve() or
                any(not path.is_absolute() or '..' in path.parts for path in contexts + [canary]) or
                temporary.parent != Path('/tmp') or not temporary.name.startswith('specpilot-codex-role-') or
                work != temporary / 'work' or home != temporary / 'home' or canary != temporary / 'protected.txt'):
            raise ValueError('restricted role requires its concrete /tmp/specpilot-codex-role-* common parent')
        roles.append(dict(name=name, pid=process['pid'], exit_code=0, contexts=[str(path) for path in contexts]))
    return roles


def _legacy_roles(root, pipeline):
    roles = _legacy_role_records(root, pipeline)
    owner = (root / 'pipeline-result.json').stat().st_uid
    for role in roles:
        directory, temporary, work, home = (Path(path) for path in role['contexts'])
        canary = temporary / 'protected.txt'
        for path in (temporary, work, home, canary):
            info = path.stat()
            if (path != path.resolve() or info.st_uid != owner or stat.S_IMODE(info.st_mode) & 0o022 or
                    (not stat.S_ISREG(info.st_mode) if path == canary else not stat.S_ISDIR(info.st_mode)) or
                    (path in (temporary, home) and stat.S_IMODE(info.st_mode) & 0o077)):
                raise ValueError('role temporary workspace/canary owner or permissions differ')
    return roles


def _legacy_proc_observation(roles, broker_uid):
    pids = [role['pid'] for role in roles]
    contexts = sorted({path for role in roles for path in role['contexts']})
    started = time.time()
    for pid in pids:
        if Path(f'/proc/{pid}').exists():
            raise ValueError('old research PID still exists; legacy route never guesses startticks')
    scanned, digests = 0, []
    for base in Path('/proc').iterdir():
        if not base.name.isdecimal() or int(base.name) == os.getpid():
            continue
        try:
            uid = base.stat().st_uid
            command = (base / 'cmdline').read_bytes()
            values = [command.decode(errors='replace')]
            if uid == broker_uid:
                fields = (base / 'stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] != 'Z':
                    values.extend((str((base / 'cwd').resolve(strict=True)),
                                   (base / 'environ').read_bytes().decode(errors='replace')))
            if any(context in value for context in contexts for value in values):
                raise ValueError('restricted role workspace/session execution process remains')
            scanned += 1
            digests.append(hashlib.sha256(str(base).encode() + b'\0' + b'\0'.join(value.encode() for value in values)).hexdigest())
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise ValueError('host /proc observation incomplete; cannot certify role shutdown') from None
    for pid in pids:
        if Path(f'/proc/{pid}').exists():
            raise ValueError('old research PID appeared during observation')
    return dict(host_boot_id=identity()['host_boot_id'], pid_namespace_inode=identity()['pid_namespace_inode'],
        hostname=socket.gethostname(), broker_uid=broker_uid, started_unix=started, finished_unix=time.time(),
        absent_pids=sorted(pids), contexts=contexts, inspected_processes=scanned,
        process_inventory_sha256=hashlib.sha256(json.dumps(sorted(digests)).encode()).hexdigest(), matches=[],
        scope='all visible host cmdlines plus same-broker-UID cwd/session environment; no birth identity claim')


def _legacy_sources():
    from exp.phase4_run import ROOT, execution_sources, reference
    return {name: reference(ROOT / name)['sha256'] for name in execution_sources(('harness/skill_rsi_audit.py',))}


def _legacy_files(root, roles, pipeline, snapshot):
    from exp.phase4_run import reference
    from harness.skill_rsi_audit import safe_path
    paths = {root / name for name in ('pipeline-result.json', 'host-loaded-identity.json',
                                      'feedback.json', 'preflight-result.json', 'counters.json') if (root / name).is_file()}
    host = _legacy_archive(root)
    paths.update(Path(host[key]['path']) for key in ('source_archive', 'source_identity', 'host_source_copy'))
    for role in roles:
        directory = root / role['name']
        paths.update(directory.glob('turn-*.json'))
        paths.update((directory / name for name in ('manifest.json', 'wire.jsonl')))
        for tools in directory.glob('tools-*'):
            paths.update(path for path in tools.rglob('*') if path.is_file())
    for number, job in enumerate(snapshot['jobs']):
        directory = safe_path(root / job['name'], root)
        paths.update(path for path in directory.iterdir() if path.is_file())
        if number >= len(pipeline['resource_state']['jobs']):
            paths.update(directory / 'remote' / name for name in ('error.json', 'result.json', 'replay-summary.json')
                         if (directory / 'remote' / name).is_file())
    if any(path.is_symlink() or not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError('shared legacy evidence cannot escape the shared pipeline root')
    return {str(safe_path(path, root)): reference(path)['sha256'] for path in sorted(paths)}


def _legacy_expected_host_files(root, roles):
    result = {}
    for role in roles:
        manifest = json.loads((root / role['name'] / 'manifest.json').read_bytes())
        for path, key in ((Path(manifest['canary']), 'canary_sha256'),
                (Path(manifest['work']) / 'inputs/rules.txt', 'rules_sha256'),
                (Path(manifest['work']) / 'inputs/evidence.json', 'evidence_sha256'),
                (Path(manifest['home']) / 'config.toml', 'config_sha256')):
            result[str(path)] = manifest[key]
    return result


def _legacy_host_files(root, roles):
    from exp.phase4_run import reference
    expected = _legacy_expected_host_files(root, roles)
    actual = {}
    for name in expected:
        path = Path(name)
        if path != path.resolve():
            raise ValueError('host immutable role file cannot follow symlinks')
        actual[name] = reference(path)['sha256']
    if actual != expected:
        raise ValueError('host immutable role file SHA differs from the audited manifest')
    return actual


def _legacy_archive(root):
    from exp.phase4_run import reference
    loaded = json.loads((root / 'host-loaded-identity.json').read_bytes())
    def bound_path(value):
        path = Path(value)
        choices = [path] if path.is_absolute() else [parent / path for parent in (root, *root.parents)]
        for candidate in choices:
            if candidate.is_relative_to(root) and candidate == candidate.resolve() and candidate.is_file():
                return candidate
        raise ValueError('historical host source identity escaped its original pipeline root')
    archive_path, copy_path = bound_path(loaded['archive']), bound_path(loaded['copy'])
    pipeline = json.loads((root / 'pipeline-result.json').read_bytes())
    if (archive_path.name != 'source.tar' or archive_path.parent.name not in
            {job['name'] for job in pipeline['resource_state']['jobs']} or
            loaded.get('hot_reload') is not False or type(loaded.get('pid')) is not int or loaded['pid'] <= 0 or
            reference(copy_path)['sha256'] != loaded['script_sha256']):
        raise ValueError('preserved host-loaded source copy/archive binding differs')
    identity_path = archive_path.with_name('source-identity.json')
    inventory = json.loads(identity_path.read_bytes())
    if (inventory['archive_sha256'] != reference(archive_path)['sha256'] or not inventory['files'] or
            inventory['files'].get('exp/skill_rsi.py') != loaded['script_sha256']):
        raise ValueError('original pipeline source archive SHA missing or changed')
    with tarfile.open(archive_path) as archive:
        if len(archive.getmembers()) != len(inventory['files']) or set(archive.getnames()) != set(inventory['files']):
            raise ValueError('original pipeline source archive inventory incomplete')
        for name, checksum in inventory['files'].items():
            member = archive.getmember(name)
            if (not member.isfile() or Path(name).is_absolute() or '..' in Path(name).parts or
                    'sealed' in Path(name).parts or Path(name).name == 'auth.json' or
                    hashlib.sha256(archive.extractfile(member).read()).hexdigest() != checksum):
                raise ValueError('original pipeline source archive member invalid')
    return dict(host_loaded_identity=reference(root / 'host-loaded-identity.json'),
        host_source_copy=reference(copy_path), source_archive=reference(archive_path), source_identity=reference(identity_path),
        scope='preserved while-running host source copy matched the diagnostic archive; not historical process birth proof')


def _legacy_additional(root, sources, broker_uid, opened_unix, *, check_current_processes=True):
    expected = {path.resolve() for path in root.glob('coverage-review-*/processes') if path.is_dir()}
    parents = {Path(source['path']).parent.resolve() for source in sources}
    if not expected.issubset(parents) or len(parents) != len(sources):
        raise ValueError('all additional coverage-review process registries must be explicitly closed and frozen')
    count = 0
    for source in sources:
        path = Path(source['path'])
        if not path.is_absolute() or not path.is_relative_to(root):
            raise ValueError('additional shutdown registry must belong to this closed stage')
        count += validate_shutdown(trusted_metadata(source, broker_uid), broker_uid=broker_uid, opened_unix=opened_unix,
                                   check_current_processes=check_current_processes)
    return count


def _legacy_prefix_audit(audit, pipeline, snapshot, pipeline_sha256):
    from agents.exploration import object_sha
    historical = pipeline['resource_state']
    prefix = audit['scientific_prefix']
    extensions = snapshot['jobs'][len(historical['jobs']):]
    if (not all(row.get('terminated') is True for row in snapshot['jobs']) or
            snapshot['jobs'][:len(historical['jobs'])] != historical['jobs'] or
            {key: value for key, value in snapshot.items() if key != 'jobs'} !=
            {key: value for key, value in historical.items() if key != 'jobs'} or
            prefix['resource_snapshot_sha256'] != object_sha(historical) or
            prefix['pipeline_result_sha256'] != pipeline_sha256 or prefix['terminated_gpu_jobs'] != len(historical['jobs']) or
            audit['terminated_gpu_jobs'] != len(snapshot['jobs']) or
            audit['conservative_gpu_seconds'] != sum(row['charged_gpu_seconds'] for row in snapshot['jobs']) or
            [row['name'] for row in audit['controller_extensions']] != [row['name'] for row in extensions] or
            audit['controller_phase4_extension_occurred'] is not bool(extensions)):
        raise ValueError('independent prefix audit is not bound to both frozen resource snapshots')


def _legacy_live_prefix(root, snapshot, proof, broker_uid, pending_request):
    from exp.phase4_run import reference
    live = json.loads((root / 'resource-state.json').read_bytes())
    length = len(snapshot['jobs'])
    if ({key: value for key, value in live.items() if key != 'jobs'} !=
            {key: value for key, value in snapshot.items() if key != 'jobs'} or live['jobs'][:length] != snapshot['jobs']):
        raise ValueError('live Budget must retain the unchanged frozen observed prefix')
    extra = live['jobs'][length:]
    if not extra:
        return
    if len(extra) != 1 or pending_request is None:
        raise ValueError('only the explicitly bound current request reservation may follow the frozen prefix')
    request = trusted_metadata(pending_request, broker_uid)
    directory = Path(pending_request['path']).parent
    row = extra[0]
    plan = json.loads((directory / 'plan.json').read_bytes())
    if (directory.parent != root or Path(pending_request['path']).name != 'request.json' or
            request.get('protocol') != 'controller-phase4-resource-v1' or request.get('mode') != 'phase4-controller' or
            request.get('purpose') != 'controller-negative-control' or request.get('maintenance_stock_control') is not True or
            request.get('shutdown_registry') != proof or request.get('budget_path') != str(root / 'resource-state.json') or
            type(request.get('deadline')) is not int or not 600 <= request['deadline'] <= 14400 or
            row.get('name') != directory.name or row.get('gpus') != 2 or row.get('seconds') != request['deadline'] + 1200 or
            row.get('terminated') is not False or type(row.get('create_calls')) is not int or row['create_calls'] not in (0, 1) or
            row.get('reserved_unix', 0) < trusted_metadata(proof, broker_uid)['closed_unix'] or
            set(row) - {'name', 'gpus', 'seconds', 'reserved_unix', 'terminated', 'create_calls', 'uuid', 'submission_code', 'started'} or
            plan.get('request') != pending_request or plan.get('source') != reference(directory / 'source.tar') or
            plan.get('budget_path') != request['budget_path'] or plan.get('gpus') != 2 or
            plan.get('deadline_seconds') != request['deadline']):
        raise ValueError('additional reservation is not the frozen controller request/plan/source/budget')
    if row['create_calls']:
        pending = json.loads((directory / 'pending.json').read_bytes())
        if pending.get('request_sha256') != pending_request['sha256'] or pending.get('source_sha256') != plan['source']['sha256']:
            raise ValueError('submitted reservation source/request identity differs')


def observe_legacy_shutdown(pipeline_root, directory, *, extra_shutdown_registries=()):
    """Trusted controller observation of a closed legacy stage, ONLY for maintenance stock control."""
    from exp.phase4_run import reference
    from harness import skill_rsi_audit
    root = skill_rsi_audit.safe_path(pipeline_root)
    directory = _private(directory, directory=True)
    pipeline = skill_rsi_audit.load(root / 'pipeline-result.json')
    snapshot = skill_rsi_audit.load(root / 'resource-state.json')
    roles = _legacy_roles(root, pipeline)
    extra_count = _legacy_additional(root, extra_shutdown_registries, os.geteuid(), time.time())
    if any(directory.is_relative_to(Path(context)) for role in roles for context in role['contexts']):
        raise ValueError('trusted shutdown evidence cannot be in a role workspace')
    sources = _legacy_sources()
    before = _legacy_files(root, roles, pipeline, snapshot)
    host_files = _legacy_host_files(root, roles)
    host_source = _legacy_archive(root)
    observation = _legacy_proc_observation(roles, os.geteuid())
    _legacy_additional(root, extra_shutdown_registries, os.geteuid(), time.time())
    audit = skill_rsi_audit.audit(root)
    _legacy_prefix_audit(audit, pipeline, snapshot, reference(root / 'pipeline-result.json')['sha256'])
    if (audit.get('engineering_evidence_verified') is not True or audit.get('pipeline_completed') is not True or
            audit.get('scientific_roles') != 6 or audit.get('sealed_used') is not False or
            _legacy_files(root, roles, pipeline, snapshot) != before or _legacy_sources() != sources or
            _legacy_roles(root, pipeline) != roles or _legacy_host_files(root, roles) != host_files or
            skill_rsi_audit.load(root / 'resource-state.json') != snapshot):
        raise ValueError('independent closed-stage audit/complete native evidence changed or failed')
    observation = _legacy_proc_observation(roles, os.geteuid())
    audit_ref = _save(directory / 'legacy-audit.json', audit)
    state_ref = _save(directory / 'resource-state-at-audit.json', snapshot)
    historical_ref = _save(directory / 'historical-resource-state.json', pipeline['resource_state'])
    return _save(directory / 'legacy-shutdown.json', dict(schema=LEGACY,
        purpose='controller-negative-control', historical_birth_identity_unavailable=True,
        observer=dict(identity(), hostname=socket.gethostname()), pipeline_root=str(root), roles=roles,
        pipeline_result=reference(root / 'pipeline-result.json'), host_source=host_source,
        audit=audit_ref, resource_state=state_ref, historical_resource_state=historical_ref,
        extra_shutdown_registries=list(extra_shutdown_registries), additional_processes_checked=extra_count,
        audit_sources=sources, original_files=before, host_temporary_files=host_files,
        proc_observation=observation, closed_unix=time.time()))


def validate_legacy_shutdown(reference, *, broker_uid, maintenance_stock_control, check_current_host=False, pending_request=None):
    from exp.phase4_run import reference as file_reference
    value = trusted_metadata(reference, broker_uid)
    parent = Path(reference['path']).parent
    info = parent.stat()
    if (parent != parent.resolve() or info.st_uid != broker_uid or stat.S_IMODE(info.st_mode) & 0o777 != 0o700 or
            maintenance_stock_control is not True or value.get('schema') != LEGACY or
            value.get('purpose') != 'controller-negative-control' or
            value.get('historical_birth_identity_unavailable') is not True or
            value['observer']['uid'] != broker_uid or value['audit_sources'] != _legacy_sources()):
        raise ValueError('legacy proof is controller-owned, source-bound and negative-control-only')
    audit = trusted_metadata(value['audit'], broker_uid)
    state = trusted_metadata(value['resource_state'], broker_uid)
    historical = trusted_metadata(value['historical_resource_state'], broker_uid)
    pipeline = json.loads(Path(value['pipeline_result']['path']).read_bytes())
    root = Path(value['pipeline_root'])
    roles = _legacy_role_records(root, pipeline)
    additional = _legacy_additional(root, value['extra_shutdown_registries'], broker_uid, value['closed_unix'],
                                   check_current_processes=check_current_host)
    if (file_reference(root / 'pipeline-result.json') != value['pipeline_result'] or
            _legacy_archive(root) != value['host_source'] or
            pipeline['resource_state'] != historical or roles != value['roles'] or additional != value['additional_processes_checked'] or
            _legacy_files(root, roles, pipeline, state) != value['original_files'] or
            _legacy_expected_host_files(root, roles) != value['host_temporary_files'] or
            audit.get('engineering_evidence_verified') is not True or audit.get('pipeline_completed') is not True or
            audit.get('scientific_roles') != 6 or audit.get('sealed_used') is not False):
        raise ValueError('legacy original native/pipeline/source/audit snapshot drifted')
    _legacy_prefix_audit(audit, pipeline, state, value['pipeline_result']['sha256'])
    _legacy_live_prefix(root, state, reference, broker_uid, pending_request)
    observed = value['proc_observation']
    if (observed['broker_uid'] != broker_uid or observed['absent_pids'] != sorted(role['pid'] for role in roles) or
            observed['contexts'] != sorted({context for role in roles for context in role['contexts']}) or
            observed['host_boot_id'] != value['observer']['host_boot_id'] or
            observed['pid_namespace_inode'] != value['observer']['pid_namespace_inode'] or
            observed['hostname'] != value['observer']['hostname'] or observed['matches'] != [] or
            observed['inspected_processes'] < 1 or not observed['started_unix'] <= observed['finished_unix'] <= value['closed_unix']):
        raise ValueError('legacy complete host observation missing')
    if check_current_host:
        current = identity()
        if (current['uid'] != broker_uid or current['host_boot_id'] != value['observer']['host_boot_id'] or
                current['pid_namespace_inode'] != value['observer']['pid_namespace_inode']):
            raise ValueError('legacy submission requires renewed observation on its original broker host')
        if _legacy_roles(root, pipeline) != roles or _legacy_host_files(root, roles) != value['host_temporary_files']:
            raise ValueError('original broker host immutable role evidence changed')
        _legacy_proc_observation(roles, broker_uid)
    return dict(schema=LEGACY, roles_checked=6, original_roles_checked=6, processes_checked=6 + additional,
        additional_processes_checked=additional, registry=reference,
        historical_birth_identity_unavailable=True, purpose='controller-negative-control')


def observe_terminal(job_name, directory, *, request, source):
    """Trusted broker queries Kubernetes itself; no supplied status/passed flag is consumed."""
    from kubernetes import client, config
    directory = _private(directory, directory=True)
    config.load_kube_config()
    job = client.CustomObjectsApi().get_namespaced_custom_object(
        'batch.volcano.sh', 'v1alpha1', 'qiji', 'jobs', job_name)
    api = client.CoreV1Api()
    pods = [api.api_client.sanitize_for_serialization(pod) for pod in
            api.list_namespaced_pod('qiji', label_selector='volcano.sh/job-name=' + job_name).items]
    return _save(directory / 'terminal-observation.json', dict(schema='controller-kubernetes-terminal-v1',
        observer=identity(), observed_unix=time.time(), request=request, source=source, job=job, pods=pods))


def validate_terminal(value, *, request, source, record, execution):
    from exp.engine_resource import IMAGE
    from exp.phase4_resource import command
    if (value.get('schema') != 'controller-kubernetes-terminal-v1' or value['request'] != request or
            value['source'] != source or value['observer']['uid'] != record['broker_uid']):
        raise ValueError('trusted resource observation/request/source identity missing')
    job, pods = value['job'], value['pods']
    metadata, spec = job['metadata'], job['spec']
    template = spec['tasks'][0]['template']['spec']
    container = template['containers'][0]
    expected_shell = command(request['path'], source['path'], Path(request['path']).parent / 'remote',
                             Path(request['path']).parent.name, record['deadline'])[-1]
    actual_command = container.get('command', []) + container.get('args', [])
    if (metadata.get('namespace') != 'qiji' or not metadata.get('uid') or
            job.get('status', {}).get('state', {}).get('phase') != 'Completed' or
            spec.get('priorityClassName') != 'higher-priority-job' or spec.get('queue') != 'qiji' or
            spec.get('maxRetry') != 0 or job.get('status', {}).get('retryCount', 0) != 0 or
            template.get('activeDeadlineSeconds') != record['deadline'] or template.get('hostNetwork') is True or
            len(template['containers']) != 1 or container.get('image') != IMAGE or
            str(container['resources']['limits'].get('nvidia.com/gpu')) != '2' or
            container.get('securityContext', {}).get('privileged') is True or expected_shell not in actual_command or
            not any(mount.get('mountPath') == '/gpfs/models' and mount.get('readOnly') is True
                    for mount in container.get('volumeMounts', [])) or not pods):
        raise ValueError('real terminal Job/deployment differs from authorized frozen execution')
    names, uids = set(), set()
    for pod in pods:
        info, status = pod['metadata'], pod['status']
        statuses = status.get('containerStatuses', [])
        if (not info.get('uid') or info['uid'] in uids or info.get('namespace') != 'qiji' or
                info.get('labels', {}).get('volcano.sh/job-name') != metadata['name'] or
                not any(owner.get('uid') == metadata['uid'] for owner in info.get('ownerReferences', [])) or
                status.get('phase') != 'Succeeded' or len(statuses) != 1 or
                pod['spec']['containers'][0]['image'] != IMAGE):
            raise ValueError('real terminal Pod identity/status missing')
        state = statuses[0].get('state', {}).get('terminated', {})
        started, finished = state.get('startedAt'), state.get('finishedAt')
        if (statuses[0].get('restartCount') != 0 or state.get('exitCode') != 0 or
                state.get('reason') != 'Completed' or not started or not finished or
                not statuses[0].get('imageID') or IMAGE.split('@')[-1] not in statuses[0]['imageID'] or
                not datetime.fromisoformat(started.replace('Z', '+00:00')).timestamp() <=
                datetime.fromisoformat(finished.replace('Z', '+00:00')).timestamp() <= value['observed_unix']):
            raise ValueError('real container exit/image/chronology missing')
        names.add(info['name'])
        uids.add(info['uid'])
    if len(pods) != 1 or execution['controller_identity']['pod_name'] not in names:
        raise ValueError('runtime controller does not belong to the observed single Pod')
    return metadata['uid']


def _inventory(private, external_roots):
    paths = set()
    for base in [private] + [Path(path).absolute() for path in external_roots]:
        if base.is_symlink():
            raise ValueError('sealed inventory cannot follow symlinks')
        for path in base.rglob('*') if base.is_dir() else [base]:
            if path.is_symlink():
                raise ValueError('sealed inventory cannot follow symlinks')
            if path.is_file():
                paths.add(path.absolute())
    pending = list(paths)
    def references(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'}:
                yield value
            else:
                for item in value.values():
                    yield from references(item)
        elif isinstance(value, list):
            for item in value:
                yield from references(item)
    while pending:
        path = pending.pop()
        if path.suffix != '.json':
            continue
        try:
            value = json.loads(path.read_bytes())
        except (ValueError, UnicodeError):
            continue
        for ref in references(value):
            target = Path(ref['path']).absolute()
            if target != target.resolve() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != ref['sha256']:
                raise ValueError('sealed evidence reference drifted or disappeared')
            if target not in paths:
                paths.add(target)
                pending.append(target)
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def seal_evidence(private, destination, *, terminal):
    """After real Job termination, controller seals retained private, dev and referenced evidence."""
    from exp.phase4_run import reference
    private = _private(private, directory=True)
    destination = _private(destination, directory=True)
    if destination.is_relative_to(private) or private.is_relative_to(destination):
        raise ValueError('seal must be outside the execution evidence tree')
    execution = trusted_metadata(reference(private / 'execution.json'), os.geteuid())
    runtime = trusted_metadata(execution['runtime'], os.geteuid())
    opened = trusted_metadata(runtime['opened'], os.geteuid())
    _, frozen = _frozen(opened['freeze'])
    request = frozen['artifacts']['phase4_resource_request']
    record = trusted_metadata(request, Path(request['path']).stat().st_uid)
    trusted_metadata(terminal, record['broker_uid'])
    external = [terminal['path']]
    dev = frozen['artifacts'].get('dev_campaign_manifest')
    if dev:
        external.append(str(Path(dev['path']).parent))
    return _save(destination / 'seal.json', dict(schema='controller-phase4-seal-v1',
        private=str(private), terminal=terminal, external_roots=external, created_unix=time.time(),
        files=_inventory(private, external)))


def finalize(private, seal):
    """Independent CPU process, same controller UID/paths/image; failures return aggregate false."""
    from exp.phase4_resource import replay_private
    from exp.phase4_run import check_bundle, reference, validate_dev
    result = dict(schema=FINAL, execution_completed=False, protocol_verified=False, scientific_ready=False,
        correctness_passed=False, performance_passed=False, expected_rejection=False,
        t3_passed=False, promoted=False, ledger_eligible=False, finalization_verified=False)
    try:
        private = _private(private, directory=True)
        sealed = trusted_metadata(seal, os.geteuid())
        if (sealed.get('schema') != 'controller-phase4-seal-v1' or sealed['private'] != str(private) or
                sealed['files'] != _inventory(private, sealed['external_roots'])):
            raise ValueError('complete sealed SHA inventory mismatch')
        execution = trusted_metadata(reference(private / 'execution.json'), os.geteuid())
        producer = execution['controller_identity']
        current = identity()
        if producer['uid'] != current['uid'] or all(producer[key] == current[key] for key in
                ('pid', 'start_ticks', 'host_boot_id', 'pid_namespace_inode')):
            raise ValueError('independent process under original controller UID required')
        runtime = trusted_metadata(execution['runtime'], os.geteuid())
        opened = trusted_metadata(runtime['opened'], os.geteuid())
        _, frozen = _frozen(opened['freeze'])
        request = frozen['artifacts']['phase4_resource_request']
        record = trusted_metadata(request, Path(request['path']).stat().st_uid)
        if record['broker_uid'] != Path(request['path']).stat().st_uid:
            raise ValueError('request is not owned by its trusted broker')
        source = reference(Path(request['path']).parent / 'source.tar')
        if execution['request_sha256'] != request['sha256'] or execution['source_sha256'] != source['sha256']:
            raise ValueError('runtime request/source mismatch')
        terminal = trusted_metadata(sealed['terminal'], record['broker_uid'])
        if sealed['created_unix'] < terminal['observed_unix']:
            raise ValueError('seal predates terminal observation')
        validate_terminal(terminal, request=request, source=source, record=record, execution=execution)
        registry = trusted_metadata(record['shutdown_registry'], record['broker_uid'])
        validate_shutdown(registry, broker_uid=record['broker_uid'], opened_unix=opened['opened_unix'])
        control = record['maintenance_stock_control']
        check_bundle(record['bundle'], opened['freeze'], maintenance_stock_control=control)
        if record['candidate_tree_sha'] != execution['candidate_tree_sha']:
            raise ValueError('original frozen bundle identity drifted')
        if not control:
            validate_dev(frozen)
        summary = replay_private(private)
        for key in ('execution_completed', 'protocol_verified', 'scientific_ready', 'correctness_passed',
                    'performance_passed', 'expected_rejection'):
            result[key] = summary[key]
        result.update(finalization_verified=True, purpose=frozen['purpose'],
            t3_passed=not control and all(result[key] for key in ('execution_completed', 'protocol_verified',
                'scientific_ready', 'correctness_passed', 'performance_passed')))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError):
        result['reason'] = 'incomplete, failed or inconsistent trusted evidence; see controller-private finalizer log'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private', type=Path, required=True)
    parser.add_argument('--seal', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _private(args.private, directory=True)
    _private(args.output.parent, directory=True)
    from exp.phase4_run import reference
    with (args.output.parent / 'finalizer.log').open('x') as log, redirect_stdout(log), redirect_stderr(log):
        result = finalize(args.private, reference(args.seal))
        _save(args.output, result)


if __name__ == '__main__':
    main()
