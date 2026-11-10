"""Controller-only Phase4 pool/resource adapter; no role tool and no final authorization."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from controller.paper_policy import valid_digest
from controller.scored_forcing import read_reference
from controller.sealed_protocol import _frozen, _private, _save, validate_phase4
from controller.sealed_cohort import build_exclusions, generate_indexes, load_exclusions, materialize_cohort, plan_cohort, select_cohort, verify_cohort
from exp.phase4_run import execution_sources, freeze_bundle, reference, run, validate_dev, validate_science


PROTOCOL = 'controller-phase4-resource-v1'
LIMITS = dict(gpu_seconds=115200, wall_seconds=86400, concurrent_gpus=4)


def _reference(value):
    if (not isinstance(value, dict) or set(value) != {'path', 'sha256'} or
            not Path(value['path']).is_absolute() or not valid_digest(value['sha256'])):
        raise ValueError('absolute immutable controller reference required')
    return value


def checked_budget(budget, expected_path):
    from harness.engine_research import Budget
    path = Path(expected_path).absolute()
    if not isinstance(budget, Budget) or budget.path.resolve() != path.resolve() or not path.is_file():
        raise ValueError('inject the existing unique stage Budget, never create a Phase4 budget')
    state = budget.read()
    if any(state.get(key) != value for key, value in LIMITS.items()):
        raise ValueError('Phase4 must share the authorized 32h/24h/4-GPU budget')
    return state


def research_stopped(registry, *, maintenance_stock_control=False, pending_request=None):
    path = _private(registry['path'])
    _private(path.parent, directory=True)
    value = read_reference(registry, path.parent)
    from controller.phase4_final import LEGACY, REGISTRY, validate_legacy_shutdown, validate_shutdown
    if value.get('schema') == LEGACY:
        return validate_legacy_shutdown(registry, broker_uid=os.geteuid(),
            maintenance_stock_control=maintenance_stock_control, check_current_host=True, pending_request=pending_request)
    if value.get('schema') == REGISTRY:
        import time
        count = validate_shutdown(value, broker_uid=os.geteuid(), opened_unix=time.time())
        return dict(schema=REGISTRY, roles_checked=count, registry=registry)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if value.get('schema') != 'controller-research-process-registry-v1' or value.get('host_boot_id') != boot:
        raise ValueError('authoritative controller role registry from this host is required')
    roles = value.get('roles')
    if not isinstance(roles, list):
        raise ValueError('complete research process registry required')
    identities = set()
    for role in roles:
        if (not isinstance(role.get('role'), str) or not role['role'] or
                any(type(role.get(key)) is not int or role[key] <= 0 for key in ('pid', 'start_ticks')) or
                (role['pid'], role['start_ticks']) in identities):
            raise ValueError('invalid/duplicate research process identity')
        identities.add((role['pid'], role['start_ticks']))
        try:
            current = int(Path(f'/proc/{role["pid"]}/stat').read_text().rsplit(')', 1)[1].split()[19])
        except (FileNotFoundError, ProcessLookupError):
            continue
        if current == role['start_ticks']:
            raise ValueError('research process is still present; controller must not open the pool')
    return dict(schema=value['schema'], roles_checked=len(roles), registry=registry, host_boot_id=boot)


def archive_source(directory):
    names = execution_sources(('exp/phase4_resource.py', 'controller/sealed_cohort.py', 'exp/phase4_remote.sh'))
    destination = Path(directory) / 'source.tar'
    with tarfile.open(destination, 'x') as archive:
        for name in sorted(names):
            path = ROOT / name
            if path.is_symlink():
                raise ValueError('source archive cannot include symlinks')
            archive.add(path, arcname=name, recursive=False)
    _save(Path(directory) / 'source-identity.json', dict(archive=reference(destination),
        files={name: reference(ROOT / name)['sha256'] for name in sorted(names)}))
    return destination


def _request_identity(record, frozen=None):
    from harness.source_candidate import load_bundle
    bundle = load_bundle(record['bundle'])
    control = record['maintenance_stock_control']
    measured = bundle['stock_tree_sha'] if control else bundle['candidate_tree_sha']
    purpose = 'controller-negative-control' if control else 'scientific-candidate'
    if (type(control) is not bool or record['candidate_tree_sha'] != measured or
            record['bundle_candidate_tree_sha'] != bundle['candidate_tree_sha'] or record['purpose'] != purpose or
            (frozen is not None and (frozen['purpose'] != purpose or frozen['arms'][1]['tree_sha'] != measured))):
        raise ValueError('request actual measured tree/purpose differs from frozen bundle or arm identity')
    return measured


def prepare(directory, *, bundle, cohort, shutdown_registry, research_roots, budget, deadline=10800,
            isolate_network=False, maintenance_stock_control=False, dev_manifest=None):
    """No request/index body is read here; all private-pool access is remote/controller-only."""
    directory = Path(directory).absolute()
    checked_budget(budget, budget.path)
    if directory.parent.resolve() != budget.path.parent.resolve():
        raise ValueError('Phase4 request must belong to the same unique stage budget directory')
    _reference(shutdown_registry)
    generated = 'source_catalog_sha256' in cohort
    fields = {'source_catalog_sha256', 'dev_sources', 'used_sources', 'source_cache', 'pool_per_suite', 'counts', 'seed'} if generated else {
        'pool_index', 'dev_indexes', 'used_indexes', 'counts', 'seed'}
    if (type(deadline) is not int or not 600 <= deadline <= 14400 or type(isolate_network) is not bool or
            type(maintenance_stock_control) is not bool or set(cohort) != fields or
            not research_roots or any(not Path(path).is_absolute() for path in research_roots) or
            not isinstance(cohort['counts'], dict) or not cohort['counts'] or
            any(not isinstance(key, str) or not key or type(value) is not int or value < 1
                for key, value in cohort['counts'].items()) or not isinstance(cohort['seed'], str) or not cohort['seed']):
        raise ValueError('fixed deadline and complete blind cohort specification required')
    if generated:
        from controller.sealed_cohort import source_catalog_sha256
        from exp.p3_pair_run import SUITES
        if (cohort['source_catalog_sha256'] != source_catalog_sha256() or set(cohort['dev_sources']) != set(SUITES) or
                type(cohort['pool_per_suite']) is not int or cohort['pool_per_suite'] < 1):
            raise ValueError('all-dev sources and fixed public-source generation plan required')
        for source in list(cohort['dev_sources'].values()) + cohort['used_sources']:
            _reference(source)
        if cohort['source_cache'] is not None:
            _reference(cohort['source_cache'])
    else:
        if not cohort['dev_indexes']:
            raise ValueError('full dev indexes required')
        _reference(cohort['pool_index'])
        for source in cohort['dev_indexes'] + cohort['used_indexes']:
            _reference(source)
    if not maintenance_stock_control:
        _reference(dev_manifest)
    bundle = Path(bundle).absolute()
    from harness.source_candidate import load_bundle
    identity = load_bundle(bundle)
    directory.mkdir(mode=0o700)
    _private(directory, directory=True)
    _save(directory / 'request.json', dict(protocol=PROTOCOL, mode='phase4-controller',
        action=dict(per_suite=1, max_new_tokens=4096), bundle=str(bundle),
        bundle_manifest=reference(bundle / 'manifest.json'),
        candidate_tree_sha=identity['stock_tree_sha'] if maintenance_stock_control else identity['candidate_tree_sha'],
        bundle_candidate_tree_sha=identity['candidate_tree_sha'],
        cohort=cohort, shutdown_registry=shutdown_registry, budget_path=str(budget.path.resolve()),
        research_roots=[str(Path(path).resolve()) for path in research_roots],
        deadline=deadline, isolate_network=isolate_network, dev_manifest=dev_manifest,
        maintenance_stock_control=maintenance_stock_control,
        purpose='controller-negative-control' if maintenance_stock_control else 'scientific-candidate',
        broker_uid=os.geteuid()))
    source = archive_source(directory)
    cli = command(directory / 'request.json', source, directory / 'remote', directory.name, deadline)
    _save(directory / 'plan.json', dict(command=cli, shell_command=shlex.join(cli),
        request=reference(directory / 'request.json'), source=reference(source),
        budget_path=str(budget.path.resolve()), gpus=2, deadline_seconds=deadline,
        submission_performed=False, t3_passed=False))
    return dict(directory=str(directory), source=reference(source), plan=str(directory / 'plan.json'),
                submission_performed=False, t3_passed=False)


def command(request, source, output, name, deadline):
    from exp.engine_resource import command as engine_command
    bootstrap = ROOT / 'exp/phase4_remote.sh'
    cli = engine_command(request, source, output, name, deadline)
    cli[cli.index('exp.engine_northjob')] = 'exp.phase4_resource'
    cli[-1] = shlex.join(['env', 'SP_PHASE4_BOOTSTRAP_SHA=' + reference(bootstrap)['sha256'],
        'SP_PHASE4_SOURCE_SHA=' + reference(source)['sha256'], 'SP_PHASE4_REQUEST_SHA=' + reference(request)['sha256'],
        'bash', str(bootstrap), str(request), str(source), str(output), str(deadline)])
    return cli


def bounded_template(template, deadline):
    from exp.engine_northjob import bounded_template as engine_template
    if type(deadline) is not int or not 600 <= deadline <= 14400:
        raise ValueError('Phase4 deadline exceeds the authorized per-job ceiling')
    result = engine_template(template, min(deadline, 7200))
    result['spec']['tasks'][0]['template']['spec']['activeDeadlineSeconds'] = deadline
    return result


def create():
    import importlib
    launcher = importlib.import_module('northmirror.launcher.create_job')
    cli = importlib.import_module('northmirror.launcher.northjob')
    original = launcher.build_job_yaml
    def build(*arguments, **options):
        return bounded_template(original(*arguments, **options), int(os.environ['SP_ENGINE_DEADLINE']))
    launcher.build_job_yaml = build
    try:
        return cli.main()
    finally:
        launcher.build_job_yaml = original


def _terminal(directory):
    value = json.loads((directory / 'lifecycle-final.json').read_text())
    pods = list(value.get('pods', {}).values())
    if (value.get('phase') != 'Completed' or not pods or any(
            pod.get('phase') != 'Succeeded' or pod.get('exit_code') != 0 or pod.get('restarts') != 0 or
            not pod.get('finished_at') for pod in pods)):
        raise ValueError('complete successful job/Pod terminal evidence required')
    return value


def _aggregate(summary, counts):
    cohort = summary['cohort']
    if (set(cohort) != {'counts', 'selected', 'pool_records', 'excluded_records', 'prompt_protocol_sha256'} or
            cohort['counts'] != counts or not valid_digest(cohort['prompt_protocol_sha256']) or
            any(type(cohort.get(key)) is not int or cohort[key] < 0 for key in
                ('selected', 'pool_records', 'excluded_records')) or cohort['selected'] != sum(counts.values()) or
            summary['runtime_status'] not in ('blocked', 'scientific-rejection', 'evidence-ready-awaiting-independent-final', 'maintenance-stock-control-complete') or
            any(type(summary[key]) is not bool for key in ('protocol_evidence_passed', 'scientific_ready',
                'execution_completed', 'protocol_verified', 'expected_rejection', 'correctness_passed', 'performance_passed')) or
            [entry.get('cap') for entry in summary['caps']] != [2048, 4096] or
            not valid_digest(summary['private_evidence_seal_sha256']) or
            not valid_digest(summary['private_replay_sha256']) or
            type(summary['sealed_file_count']) is not int or summary['sealed_file_count'] < 1 or
            summary['post_terminal_t3_finalizer_executed'] is not False):
        raise ValueError('public feedback must contain only predeclared aggregate cohort/status')
    for entry in summary['caps']:
        interval = entry['interval']
        if (set(entry) != {'cap', 'interval', 'threshold', 'noise', 'correctness_passed'} or
                set(interval) != {'lower', 'upper', 'geomean', 'confidence_level', 'method', 'bootstrap_iters', 'bootstrap_seed'} or
                interval['method'] != 'suite-stratified request-cluster log bootstrap; physical rounds kept together' or
                interval['confidence_level'] != .95 or interval['bootstrap_iters'] != 10000 or interval['bootstrap_seed'] != 0 or
                any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in
                    (interval['lower'], interval['geomean'], interval['upper'])) or
                not interval['lower'] <= interval['geomean'] <= interval['upper'] or
                any(type(entry[key]) not in (int, float) or not math.isfinite(entry[key]) or entry[key] < 0
                    for key in ('threshold', 'noise')) or type(entry['correctness_passed']) is not bool):
            raise ValueError('raw/per-request data or invalid statistics cannot enter public feedback')


def feedback(output, record):
    output = Path(output)
    terminal = _terminal(output.parent)
    summary = json.loads((output / 'result.json').read_text())
    replay = json.loads((output / 'replay-summary.json').read_text())
    expected = {'protocol', 'request_sha256', 'candidate_tree_sha', 'source_sha256', 'cohort', 'purpose',
                'protocol_evidence_passed', 'scientific_ready', 'caps', 'runtime_status',
                'execution_completed', 'protocol_verified', 'expected_rejection', 'correctness_passed', 'performance_passed',
                'private_evidence_seal_sha256', 'private_replay_sha256', 'sealed_file_count',
                'post_terminal_t3_finalizer_executed',
                'recompute_sha256', 't3_passed', 'promoted', 'ledger_eligible', 'controller_accepted'}
    if (set(summary) != expected or summary['protocol'] != PROTOCOL or
            summary['request_sha256'] != reference(output.parent / 'request.json')['sha256'] or
            summary['source_sha256'] != reference(output.parent / 'source.tar')['sha256'] or
            summary['candidate_tree_sha'] != record['candidate_tree_sha'] or
            summary['purpose'] != record['purpose'] or
            summary['recompute_sha256'] != reference(output / 'replay-summary.json')['sha256'] or
            {key: value for key, value in summary.items() if key != 'recompute_sha256'} != replay or
            any(summary.get(key) is not False for key in ('t3_passed', 'promoted', 'ledger_eligible', 'controller_accepted'))):
        raise ValueError('aggregate receipt differs from the trusted request/source/recompute')
    _aggregate(summary, record['cohort']['counts'])
    return dict(summary, terminal_uuid=terminal['uuid'], terminal_observed=True,
                scope='job-local independent controller replay/seal plus host terminal/aggregate SHA; not post-terminal T3 authorization')


def _deployment(uuid):
    from kubernetes import client, config
    config.load_kube_config()
    job = client.CustomObjectsApi().get_namespaced_custom_object('batch.volcano.sh', 'v1alpha1', 'qiji', 'jobs', uuid)
    pod = job['spec']['tasks'][0]['template']['spec']
    if (job['spec'].get('priorityClassName') != 'higher-priority-job' or pod.get('hostNetwork') is True or
            any(container.get('securityContext', {}).get('privileged') is True for container in pod['containers'])):
        raise ValueError('actual priority/network/privileged contract differs')
    return dict(priority_class=job['spec']['priorityClassName'], privileged=False, host_network=False)


def publish_safe_error(request, output, error):
    private = _private(Path(output) / 'private', directory=True)
    trace = _save(private / 'error-trace.json', dict(traceback=''.join(traceback.format_exception(error))))
    allowed = set(execution_sources())
    frames = []
    for frame, number in traceback.walk_tb(error.__traceback__):
        path = Path(frame.f_code.co_filename).absolute()
        if path.is_relative_to(ROOT):
            name = path.relative_to(ROOT).as_posix()
            function = frame.f_code.co_name
            if name in allowed and re.fullmatch(r'[A-Za-z0-9_<>.]{1,100}', function):
                frames.append(dict(file=name, function=function, line=number))
    error_type = type(error).__name__
    result = _save(Path(output) / 'error.json', dict(schema='controller-phase4-safe-error-v1',
        error_type=error_type if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', error_type) else 'Exception',
        frames=frames[-32:], private_trace_sha256=trace['sha256'], request_sha256=reference(request)['sha256'],
        source_sha256=os.environ['SP_PHASE4_SOURCE_SHA'], t3_passed=False, promoted=False, ledger_eligible=False))
    Path(result['path']).chmod(0o644)
    return result


def safe_error_feedback(output):
    output = Path(output)
    source = output / 'error.json'
    if source.stat().st_size > 32768:
        raise ValueError('safe error receipt exceeds aggregate bound')
    value = json.loads(source.read_bytes())
    if (set(value) != {'schema', 'error_type', 'frames', 'private_trace_sha256', 'request_sha256',
            'source_sha256', 't3_passed', 'promoted', 'ledger_eligible'} or
            value['schema'] != 'controller-phase4-safe-error-v1' or
            not isinstance(value['error_type'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', value['error_type']) or
            not valid_digest(value['private_trace_sha256']) or
            value['request_sha256'] != reference(output.parent / 'request.json')['sha256'] or
            value['source_sha256'] != reference(output.parent / 'source.tar')['sha256'] or
            any(value[key] is not False for key in ('t3_passed', 'promoted', 'ledger_eligible')) or
            not isinstance(value['frames'], list) or len(value['frames']) > 32):
        raise ValueError('safe error receipt has unbound or non-aggregate fields')
    allowed = set(execution_sources())
    for frame in value['frames']:
        if (set(frame) != {'file', 'function', 'line'} or frame['file'] not in allowed or
                not isinstance(frame['function'], str) or not re.fullmatch(r'[A-Za-z0-9_<>.]{1,100}', frame['function']) or
                type(frame['line']) is not int or frame['line'] < 1):
            raise ValueError('safe code frame cannot contain paths, source text or data')
    return value


def execute(directory, source, budget, *, resume_only=False):
    from exp.engine_resource import execute as engine_execute
    directory = Path(directory).absolute()
    record = json.loads((directory / 'request.json').read_text())
    if record.get('protocol') != PROTOCOL or record.get('mode') != 'phase4-controller':
        raise ValueError('explicit controller-only Phase4 request required')
    checked_budget(budget, record['budget_path'])
    if directory.parent.resolve() != budget.path.parent.resolve():
        raise ValueError('Phase4 cannot migrate to another budget directory')
    research_stopped(record['shutdown_registry'], maintenance_stock_control=record['maintenance_stock_control'],
                     pending_request=reference(directory / 'request.json'))
    if reference(source) != json.loads((directory / 'source-identity.json').read_text())['archive']:
        raise ValueError('source archive changed after preparation')
    plan = json.loads((directory / 'plan.json').read_text())
    if plan['request'] != reference(directory / 'request.json') or plan['source'] != reference(source):
        raise ValueError('request/source differs from the predeclared resource plan')
    _request_identity(record)
    def checked_feedback(output, request):
        result = feedback(output, request)
        result['deployment'] = _deployment(result['terminal_uuid'])
        return result
    value = engine_execute(directory, Path(source), budget, resume_only=resume_only,
        command_factory=command, feedback_loader=checked_feedback, deadline=record['deadline'])
    if value.get('status') == 'failed':
        value = dict(status='failed', uuid=value.get('uuid'), controller_accepted=False,
            t3_passed=False, promoted=False, ledger_eligible=False,
            error='Phase4 incomplete; private controller evidence retained; no raw log tail exported')
        if (directory / 'remote/error.json').is_file():
            try:
                value['safe_error'] = safe_error_feedback(directory / 'remote')
            except (ValueError, KeyError, TypeError, OSError):
                value['safe_error_receipt_rejected'] = True
        from harness.engine_research import save
        save(directory / 'feedback.json', value)
    return value


def replay_private(private):
    private = _private(private, directory=True)
    execution = json.loads((private / 'execution.json').read_text())
    runtime = read_reference(execution['runtime'], private)
    opened = runtime['opened']
    protocol = validate_phase4(opened, runtime['evidence'])
    if protocol != runtime['protocol']:
        raise ValueError('independent protocol replay differs from original runtime')
    root, frozen = _frozen(read_reference(opened, private)['freeze'])
    source = frozen['artifacts']['phase4_resource_request']
    request = read_reference(source, Path(source['path']).parent)
    if _request_identity(request, frozen) != execution['candidate_tree_sha']:
        raise ValueError('independent replay measured tree differs from actual frozen candidate arm')
    packet = read_reference(runtime['evidence'], root)
    completed = max(read_reference(source, root)['finished_unix'] for session in packet['sessions']
        for source in read_reference(session['source'], root)['rounds'])
    science = runtime['science']
    if science is not None:
        science = validate_science(science['source'], root=root, frozen=frozen,
            phase4_sha256=opened['sha256'], not_before=completed)
        if science != runtime['science']:
            raise ValueError('independent score/head regression replay differs')
    selection = execution['selection']
    summary = verify_cohort(read_reference(opened, private)['freeze'], selection,
                            read_reference(opened, private)['request_source'])
    return dict(protocol=PROTOCOL, purpose=frozen['purpose'], request_sha256=execution['request_sha256'],
        candidate_tree_sha=execution['candidate_tree_sha'], source_sha256=execution['source_sha256'],
        cohort=summary, protocol_evidence_passed=protocol['protocol_evidence_passed'],
        scientific_ready=science is not None and science['scientific_ready'], runtime_status=runtime['runtime_status'],
        execution_completed=science is not None, protocol_verified=True,
        correctness_passed=all(entry['correctness']['correctness_passed'] for entry in protocol['caps']),
        performance_passed=all(entry['performance']['performance_passed'] for entry in protocol['caps']),
        expected_rejection=frozen['purpose'] == 'controller-negative-control' and science is not None and
            science['scientific_ready'] and all(entry['correctness']['correctness_passed'] for entry in protocol['caps']) and
            not all(entry['performance']['performance_passed'] for entry in protocol['caps']),
        caps=[dict(cap=entry['cap'], interval=entry['performance']['interval'],
                   threshold=entry['performance']['threshold'], noise=entry['noise_calibration']['noise'],
                   correctness_passed=entry['correctness']['correctness_passed']) for entry in protocol['caps']],
        t3_passed=False, promoted=False, ledger_eligible=False, controller_accepted=False)


def write_private_replay(private):
    """Runs only in the job-local independent controller subprocess; no GPU or final authorization."""
    from controller.phase4_final import identity
    private = _private(private, directory=True)
    if (private / 'recomputed.json').exists() or (private / 'job-evidence-seal.json').exists():
        raise FileExistsError('independent replay/seal already exists; never overwrite or selectively rerun')
    execution = json.loads((private / 'execution.json').read_bytes())
    producer, replay = execution['controller_identity'], identity()
    if (producer['uid'] != replay['uid'] or all(producer[key] == replay[key]
            for key in ('pid', 'start_ticks', 'host_boot_id', 'pid_namespace_inode'))):
        raise ValueError('job-local replay requires an independent process under the original controller UID')
    summary = _save(private / 'recomputed.json', replay_private(private))
    excluded = ('bootstrap.log', 'controller.log', 'replay.log', 'remote-exit-status')
    files = {}
    for path in sorted(private.rglob('*')):
        if path.is_symlink():
            raise ValueError('private evidence seal cannot follow symlinks')
        if path.is_file() and path.relative_to(private).as_posix() not in excluded:
            files[path.relative_to(private).as_posix()] = reference(path)['sha256']
    return _save(private / 'job-evidence-seal.json', dict(schema='controller-phase4-job-seal-v1',
        files=files, replay=summary, replay_identity=replay, producer_identity=producer,
        excluded_live_logs=list(excluded), post_terminal_t3_finalizer_executed=False,
        t3_passed=False, promoted=False, ledger_eligible=False))


def remote(request, output):
    request = Path(request).absolute()
    record = json.loads(request.read_text())
    output = Path(output).absolute()
    private = _private(output / 'private', directory=True)
    if (record.get('protocol') != PROTOCOL or record.get('mode') != 'phase4-controller' or
            reference(record['bundle_manifest']['path']) != record['bundle_manifest'] or
            reference(record['shutdown_registry']['path']) != record['shutdown_registry']):
        raise ValueError('remote request/bundle binding differs')
    research = record['research_roots']
    with (private / 'controller.log').open('x') as log, redirect_stdout(log), redirect_stderr(log):
        from controller.phase4_final import LEGACY, REGISTRY, identity, trusted_metadata, validate_legacy_shutdown, validate_shutdown
        import time
        shutdown = trusted_metadata(record['shutdown_registry'], record['broker_uid'])
        if shutdown.get('schema') == LEGACY:
            validate_legacy_shutdown(record['shutdown_registry'], broker_uid=record['broker_uid'],
                                     maintenance_stock_control=record['maintenance_stock_control'], pending_request=reference(request))
        elif shutdown.get('schema') == REGISTRY:
            validate_shutdown(shutdown, broker_uid=record['broker_uid'], opened_unix=time.time())
        else:
            raise ValueError('actual complete broker birth/exit receipts required before private pool generation')
        _request_identity(record)
        cohort = record['cohort']
        from exp.p3_pair_run import wait_for_idle
        base_artifacts = dict(phase4_resource_request=request,
            research_shutdown_registry=record['shutdown_registry']['path'],
            sealed_cohort_source=ROOT / 'controller/sealed_cohort.py', phase4_resource_source=Path(__file__).absolute(),
            remote_bootstrap=ROOT / 'exp/phase4_remote.sh')
        if not record['maintenance_stock_control']:
            base_artifacts['dev_campaign_manifest'] = record['dev_manifest']['path']
            read_reference(record['dev_manifest'], Path(record['dev_manifest']['path']).parent)
        candidate_lock = freeze_bundle(record['bundle'], private / 'candidate-lock', gpus=wait_for_idle([0, 1]),
            seen_input_hashes=[], research_roots=research, extra_artifacts=base_artifacts,
            maintenance_stock_control=record['maintenance_stock_control'])
        if not record['maintenance_stock_control']:
            validate_dev(_frozen(candidate_lock)[1])
        if 'source_catalog_sha256' in cohort:
            cohort = generate_indexes(candidate_lock, private / 'cohort-data', cohort)
        exclusions = build_exclusions(private / 'exclusions.json', dev_indexes=cohort['dev_indexes'], used_indexes=cohort['used_indexes'])
        plan = plan_cohort(private / 'cohort-plan.json', pool_index=cohort['pool_index'], exclusions=exclusions,
                           counts=cohort['counts'], seed=cohort['seed'])
        frozen = freeze_bundle(record['bundle'], private / 'controller-run', gpus=wait_for_idle([0, 1]),
            seen_input_hashes=load_exclusions(exclusions)['input_hashes'], research_roots=research,
            extra_artifacts=dict(base_artifacts, cohort_plan=plan['path'], candidate_lock=candidate_lock['path']),
            maintenance_stock_control=record['maintenance_stock_control'])
        _request_identity(record, _frozen(frozen)[1])
        selection = select_cohort(frozen)
        requests = materialize_cohort(frozen, selection)
        result = run(record['bundle'], frozen, requests['path'], isolate_network=record['isolate_network'],
                     maintenance_stock_control=record['maintenance_stock_control'])
        _save(private / 'execution.json', dict(runtime=result, selection=selection,
            request_sha256=reference(request)['sha256'], candidate_tree_sha=record['candidate_tree_sha'],
            source_sha256=os.environ['SP_PHASE4_SOURCE_SHA'],
            controller_identity=dict(identity(), pod_name=os.environ.get('HOSTNAME', ''))))
        command_line = [sys.executable, '-B', str(Path(__file__).absolute()), 'replay', '--private', str(private)]
        with (private / 'replay.log').open('x') as destination:
            subprocess.run(command_line, stdout=destination, stderr=subprocess.STDOUT, check=True, timeout=1800)
        seal = json.loads((private / 'job-evidence-seal.json').read_bytes())
        replay = dict(json.loads((private / 'recomputed.json').read_text()),
            private_evidence_seal_sha256=reference(private / 'job-evidence-seal.json')['sha256'],
            private_replay_sha256=reference(private / 'recomputed.json')['sha256'],
            sealed_file_count=len(seal['files']), post_terminal_t3_finalizer_executed=False)
        public_replay = output / 'replay-summary.json'
        public_replay.write_text(json.dumps(replay, sort_keys=True, allow_nan=False))
        public_replay.chmod(0o644)
        summary = dict(replay, recompute_sha256=reference(public_replay)['sha256'])
        (output / 'result.json').write_text(json.dumps(summary, sort_keys=True, allow_nan=False))
        (output / 'result.json').chmod(0o644)


def main():
    if sys.argv[1:2] == ['create']:
        return create()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='mode', required=True)
    remote_parser = subparsers.add_parser('remote')
    remote_parser.add_argument('--request', type=Path, required=True)
    remote_parser.add_argument('--output', type=Path, required=True)
    replay_parser = subparsers.add_parser('replay')
    replay_parser.add_argument('--private', type=Path, required=True)
    shutdown_parser = subparsers.add_parser('legacy-shutdown')
    shutdown_parser.add_argument('--pipeline', type=Path, required=True)
    shutdown_parser.add_argument('--output', type=Path, required=True)
    shutdown_parser.add_argument('--extra-shutdown-registry', type=Path, action='append', default=[])
    args = parser.parse_args()
    if args.mode == 'legacy-shutdown':
        from controller.phase4_final import observe_legacy_shutdown
        args.output.mkdir(mode=0o700)
        _private(args.output, directory=True)
        with os.fdopen(os.open(args.output / 'observer.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as log:
            try:
                with redirect_stdout(log), redirect_stderr(log):
                    receipt = observe_legacy_shutdown(args.pipeline, args.output,
                        extra_shutdown_registries=[reference(path.absolute()) for path in args.extra_shutdown_registry])
            except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                print(json.dumps(dict(observation_completed=False, error_type=type(error).__name__, t3_passed=False)))
                raise SystemExit(1) from None
        print(json.dumps(dict(registry=receipt, original_roles_checked=6, historical_birth_identity_unavailable=True,
                              purpose='controller-negative-control', submission_performed=False, t3_passed=False)))
    elif args.mode == 'replay':
        write_private_replay(args.private)
    else:
        try:
            remote(args.request, args.output)
        except Exception as error:
            try:
                publish_safe_error(args.request, args.output, error)
            except Exception:
                pass
            raise SystemExit(1) from None


if __name__ == '__main__':
    main()
