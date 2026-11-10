"""Private Phase4 GPU wiring; execution is opt-in and never authorizes final/T3."""

import argparse
import ast
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import ctypes
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from controller.scored_forcing import calibrate_delta, calibrate_stock, judge_scored_forcing, load_score_trace, read_reference, validate_injected_generation
from controller.http_transport import sha_ids
from controller.scoring import NativeClient
from controller.paper_policy import valid_digest
from controller.sealed_protocol import CAPS, PHASES, PROTOCOL, _frozen, _private, _save, freeze_candidate, open_phase4, validate_phase4
from exp.p3_pair_run import SUITES, check_ports, clean_environment, gpu_lock, load_requests, run_round, wait_for_idle, write_json
from exp.p5_real_run import Campaign, fresh_generations, head_process, launch
from exp.source_research import SourceCapturedArm, SourceServer, sandbox_payload
from harness.candidate import expected_arguments
from harness.source_candidate import candidate_arm, load_bundle


READINESS_PROTOCOL = 'fixed-public-dev-readiness-v1'
PUBLIC_DEV_SOURCES = tuple(f'assets/upstream/dev/{suite}.jsonl' for suite in SUITES)


SOURCES = (
    'exp/phase4_run.py', 'controller/sealed_protocol.py', 'controller/scored_forcing.py',
    'controller/scoring.py', 'controller/head_reference.py', 'controller/dev_campaign.py',
    'controller/paper_policy.py', 'controller/stats.py', 'controller/token_force.py',
    'exp/p3_pair_run.py', 'exp/p5_real_run.py', 'exp/p5_api_probe.py', 'exp/p5_serve.sh',
    'exp/source_research.py', 'exp/candidate_smoke.py', 'harness/source_boundary.py',
    'harness/source_candidate.py', 'harness/candidate.py', 'harness/build_engine.py',
    'controller/http_transport.py', 'harness/telemetry.py', 'harness/sglang/env.sh',
    'harness/source_cache.py', 'harness/source_open_trace.c',
    'controller/phase4_final.py',
) + PUBLIC_DEV_SOURCES


def execution_sources(additional=()):
    names = set(SOURCES) | set(additional)
    pending, checked = list(names), set()
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        checked.add(name)
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('execution dependency is missing or not a concrete repository file')
        if path.suffix != '.py':
            continue
        tree = ast.parse(path.read_text(), filename=name)
        candidates = set()
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = name.split('/')[:-1]
                module = node.module or ''
                if node.level:
                    module = '.'.join(package[:len(package) - node.level + 1] + ([module] if module else []))
                modules = [module] + [module + '.' + alias.name for alias in node.names]
            for module in modules:
                if module.split('.')[0] in ('controller', 'exp', 'harness', 'agents', 'costmodel'):
                    candidates.update((module.replace('.', '/') + '.py', module.replace('.', '/') + '/__init__.py'))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(('.py', '.sh', '.c')):
                literal = Path(node.value)
                if not literal.is_absolute() and '..' not in literal.parts:
                    if literal.parts[0] in ('controller', 'exp', 'harness', 'agents', 'costmodel'):
                        candidates.add(literal.as_posix())
                    elif len(literal.parts) == 1:
                        candidates.add((Path(name).parent / literal).as_posix())
        for candidate in candidates:
            if (ROOT / candidate).is_file() and candidate not in names:
                names.add(candidate)
                pending.append(candidate)
    return tuple(sorted(names))


def reference(path):
    path = Path(path).absolute()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def bundle_parameters(bundle, *, maintenance_stock_control=False):
    if type(maintenance_stock_control) is not bool:
        raise ValueError('maintenance control must be an explicit controller boolean')
    manifest = load_bundle(bundle)
    base = manifest['base']
    stock = dict(name='stock', block=8, tree_sha=base['stock_tree_sha'], engine=base['stock_engine'], env={})
    arms = [stock, dict(stock, name='candidate', option_enabled=False) if maintenance_stock_control
            else candidate_arm(bundle, enabled=True)]
    common = expected_arguments(base, 8)
    for key in ('speculative_algorithm', 'speculative_num_draft_tokens'):
        common.pop(key)
    return base, arms, common


def freeze_bundle(bundle, private_root, *, gpus, seen_input_hashes, research_roots, extra_artifacts=None,
                  maintenance_stock_control=False):
    """Controller preparation only; bundle must already be frozen/default-off validated."""
    base, arms, common = bundle_parameters(bundle, maintenance_stock_control=maintenance_stock_control)
    extra_sources = [Path(path).absolute().relative_to(ROOT).as_posix() for path in (extra_artifacts or {}).values()
                     if Path(path).absolute().is_relative_to(ROOT) and Path(path).suffix in ('.py', '.sh', '.c')]
    artifacts = {name: ROOT / name for name in execution_sources(extra_sources)}
    artifacts.update(bundle_manifest=Path(bundle) / 'manifest.json', baseline_config=base['config_path'],
        target_config=Path(base['target']) / 'config.json',
        target_index=Path(base['target']) / 'model.safetensors.index.json', python_executable=Path(sys.executable).resolve())
    for role in ('target', 'draft'):
        for name in ('config.json', 'model.safetensors.index.json', 'tokenizer.json', 'tokenizer_config.json',
                     'special_tokens_map.json', 'tokenizer.model', 'chat_template.jinja'):
            path = Path(base[role]) / name
            if path.is_file():
                artifacts[f'{role}/{name}'] = path
    if extra_artifacts:
        if set(extra_artifacts) & set(artifacts):
            raise ValueError('additional controller artifacts cannot replace runtime identities')
        artifacts.update(extra_artifacts)
    return freeze_candidate(private_root, artifacts=artifacts, arms=arms, launch_protocol=common,
        gpus=gpus, seen_input_hashes=seen_input_hashes, research_roots=research_roots,
        purpose='controller-negative-control' if maintenance_stock_control else 'scientific-candidate')


def check_bundle(bundle, freeze, *, maintenance_stock_control=False):
    root, frozen = _frozen(freeze)
    purpose = 'controller-negative-control' if maintenance_stock_control else 'scientific-candidate'
    if frozen.get('purpose') != purpose:
        raise ValueError('frozen controller purpose cannot be switched after preparation')
    base, arms, common = bundle_parameters(bundle, maintenance_stock_control=maintenance_stock_control)
    if arms != frozen['arms'] or common != frozen['launch_protocol']:
        raise ValueError('runtime bundle differs from the frozen candidate/deployment')
    if frozen['artifacts'].get('bundle_manifest') != reference(Path(bundle) / 'manifest.json'):
        raise ValueError('bundle manifest is not in the controller freeze')
    for name in execution_sources():
        if frozen['artifacts'].get(name) != reference(ROOT / name):
            raise ValueError('all executed runtime/controller sources must be frozen')
    return root, frozen, base


def validate_dev(frozen):
    from controller.dev_campaign import validate_campaign
    source = frozen['artifacts']['dev_campaign_manifest']
    manifest = read_reference(source, Path(source['path']).parent)
    result = validate_campaign(Path(source['path']).parent)
    if not result['joint_acceptance_passed']:
        raise ValueError('independent actual dev campaign did not pass')
    if any(actual.get(key) != expected.get(key) for actual, expected in zip(manifest['candidate_arms'], frozen['arms'])
           for key in ('tree_sha', 'block', 'env')) or len(manifest['candidate_arms']) != 2:
        raise ValueError('dev candidate/stock identity differs from the frozen Phase4 candidate')
    if any(manifest['launch_protocol'].get(key) != value for key, value in frozen['launch_protocol'].items()):
        raise ValueError('dev deployment differs from frozen Phase4 deployment')
    for name in ('controller/scored_forcing.py', 'controller/scoring.py', 'controller/token_force.py',
                 'controller/stats.py', 'controller/paper_policy.py', 'controller/head_reference.py'):
        if manifest['source_sha256'].get(name) != frozen['artifacts'][name]['sha256']:
            raise ValueError('dev scientific judge source differs from the Phase4 judge')
    return result


@contextmanager
def private_network():
    if os.geteuid() != 0 or threading.active_count() != 1:
        raise RuntimeError('optional network enhancement requires single-threaded UID0 and namespace capability')
    original = os.open('/proc/self/ns/net', os.O_RDONLY)
    before = os.fstat(original).st_ino
    libc = ctypes.CDLL(None, use_errno=True)
    entered = False
    try:
        if libc.unshare(0x40000000) != 0:
            raise OSError(ctypes.get_errno(), 'requested optional CLONE_NEWNET enhancement unavailable')
        entered = True
        if Path('/proc/self/ns/net').stat().st_ino == before or [name for index, name in socket.if_nameindex()] != ['lo']:
            raise RuntimeError('new loopback-only network namespace not demonstrated')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
            fcntl.ioctl(control.fileno(), 0x8914, struct.pack('16sH14x', b'lo', 1))
        yield dict(host_netns_inode=before, private_netns_inode=Path('/proc/self/ns/net').stat().st_ino,
                   interfaces=['lo'], pid=os.getpid(), uid=os.geteuid())
    finally:
        try:
            if entered and libc.setns(original, 0x40000000) != 0:
                raise OSError(ctypes.get_errno(), 'failed to restore controller network namespace')
        finally:
            os.close(original)


class BoundaryHandshakeError(RuntimeError):
    pass


class PrivateSourceServer(SourceServer):
    def start(self):
        if os.geteuid() != 0:
            raise RuntimeError('private source launch requires controller UID0')
        self.sandbox = Path(tempfile.mkdtemp(prefix='specpilot-phase4-server-'))
        self.sandbox.chmod(0o711)
        allowed, canary = self.sandbox / 'allowed.txt', self.sandbox / 'canary.txt'
        allowed.write_text('authorized source probe\n')
        allowed.chmod(0o444)
        canary.write_text('protected probe\n')
        canary.chmod(0o600)
        engine = self.sandbox / 'engine'
        shutil.copytree(self.arm['engine'], engine, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.git'))
        from harness.build_engine import tree_sha
        if tree_sha(engine) != self.arm['tree_sha']:
            raise ValueError('private runtime engine copy drifted')
        payload = sandbox_payload(dict(self.arm, engine=str(engine)), self.gpu, self.port,
                                  self.sandbox, allowed, canary, self.environment)
        cache = Path(payload['scratch'])
        cache.chmod(0o710)
        os.chown(cache, 0, payload['uid'])
        work = cache / 'work'
        work.mkdir(mode=0o700)
        payload['scratch'] = str(work)
        payload['environment'] = {key: str(work) + value[len(str(cache)):] if value.startswith(str(cache)) else value
                                  for key, value in payload['environment'].items()}
        ready_read, ready_write = os.pipe()
        payload['ready_fd'] = ready_write
        try:
            write_json(self.output_dir / f'{self.arm["name"]}.sandbox.json', payload)
            self.log = (self.output_dir / f'{self.arm["name"]}.launcher.log').open('x')
            self.process = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'harness/source_boundary.py')],
                stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, cwd=ROOT,
                env=payload['environment'], close_fds=True, pass_fds=(ready_write,), start_new_session=True, text=True)
            os.close(ready_write)
            ready_write = None
            self.process.stdin.write(json.dumps(payload))
            self.process.stdin.close()
            ticks = int(Path(f'/proc/{self.process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
            write_json(self.output_dir / f'{self.arm["name"]}.process.json', dict(pid=self.process.pid, start_ticks=ticks))
            if not select.select([ready_read], [], [], 30)[0]:
                raise BoundaryHandshakeError('private source boundary READY acknowledgment timed out')
            packet = os.read(ready_read, 16384)
            if not packet:
                raise BoundaryHandshakeError('private source boundary exited before READY acknowledgment')
            try:
                receipt = json.loads(packet)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise BoundaryHandshakeError('private source boundary sent malformed READY acknowledgment') from None
            if (not isinstance(receipt, dict) or receipt.get('event') != 'SOURCE_BOUNDARY_READY' or not receipt.get('denied') or
                    not all(receipt['denied'].values()) or receipt.get('uid') != payload['uid'] or
                    not receipt.get('landlock_applied') or not receipt.get('seccomp_applied')):
                raise BoundaryHandshakeError('private source boundary READY validation failed; refusing requests')
            write_json(self.output_dir / f'{self.arm["name"]}.boundary.json', dict(receipt, trusted_pipe=True))
        finally:
            os.close(ready_read)
            if ready_write is not None:
                os.close(ready_write)


class TimedSourceArm(SourceCapturedArm):
    def step(self, *arguments, **options):
        result = super().step(*arguments, **options)
        timing = result['client_timing']
        timing['finished_unix'] = timing['started_unix'] + (timing['step_end_ns'] - timing['step_start_ns']) / 1e9
        return result


def normalize_round(directory, *, cap, number, started_unix):
    directory = Path(directory)
    def rows(name):
        return [json.loads(line) for line in (directory / name).read_text().splitlines()]
    complete = json.loads((directory / 'complete.json').read_text())
    if complete.get('round') != number:
        raise ValueError('physical round completion identity drifted')
    assignments = json.loads((directory / 'deployment.json').read_text())['assignments']
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for assignment in assignments:
        name = assignment['arm']['name']
        process = json.loads((directory / f'{name}.process.json').read_text())
        stopped = json.loads((directory / f'{name}.stopped.json').read_text())
        if stopped.get('stopped') is not True:
            raise RuntimeError('fresh server process not stopped')
        assignment['process'] = dict(process, host_boot_id=boot)
    telemetry = rows('telemetry.jsonl')
    for snapshot in telemetry:
        selected = {}
        for assignment in assignments:
            name, expected = assignment['arm']['name'], assignment['process']
            matches = [process for process in snapshot.get('arms', {}).get(name, [])
                       if process['pid'] == expected['pid'] and process['start_ticks'] == expected['start_ticks']]
            if matches:
                selected[name] = expected
        snapshot['arms'] = selected
    events = {row['event']: row['time_unix'] for row in rows('events.jsonl')}
    return dict(protocol=PROTOCOL, cap=cap, round=number,
        complete=dict(pairs=complete['pairs'], exit_code=0), assignments=assignments,
        started_unix=started_unix, ready_unix=events['servers_ready'],
        warmup_complete_unix=events['warmup_complete'], finished_unix=time.time(),
        warmup=rows('warmup.jsonl'), pairs=rows('pairs.jsonl'), telemetry=telemetry)


def checked_head(source, *, root, mode, frozen, not_before):
    result = read_reference(source, root)
    identity = result.get('head_identity', {})
    checks = result.get('checks', [])
    if (result.get('mode') != mode or not checks or result.get('tokens') != len(checks) or
            (mode == 'preflight' and len(checks) != 1) or identity.get('shape') != [248320, 5120] or
            identity.get('compute_dtype') != 'torch.float32' or identity.get('tf32') is not False or
            identity.get('checkpoint_dtype') != 'torch.bfloat16' or identity.get('chunks') != 8 or
            identity.get('reversed_accumulation') is not True or not valid_digest(identity.get('tensor_sha256')) or
            identity.get('config_sha256') != frozen['artifacts']['target_config']['sha256'] or
            identity.get('index_sha256') != frozen['artifacts']['target_index']['sha256'] or
            identity.get('checkpoint') != frozen['launch_protocol']['model_path'] or
            identity.get('source_sha256') != frozen['artifacts']['controller/head_reference.py']['sha256']):
        raise ValueError('missing/wrong-source real FP32 head preflight/control')
    for check in checks:
        raw = read_reference(check['raw_evidence'], root)
        started = raw.get('started_unix')
        body = raw.get('request', {})
        if (type(started) not in (int, float) or not math.isfinite(started) or started < not_before or
                raw.get('http_status') != 200 or body.get('return_hidden_states') != 'last' or
                body.get('return_logprob') is not True or body.get('sampling_params', {}).get('max_new_tokens') != 1 or
                sha_ids(body.get('input_ids', [])) != check.get('prefix_sha256') or
                raw.get('response', {}).get('output_ids') != [check['native_token']] or
                check['native_token'] != check['reverse_token'] or any(
                type(check.get(key)) not in (int, float) or not math.isfinite(check[key]) or not 0 <= check[key] <= .001
                for key in ('native_logprob_error', 'native_choice_margin', 'max_logit_difference'))):
            raise ValueError('independent FP32 head numerical regression failed')
    return result


def load_readiness_requests(frozen):
    from transformers import AutoTokenizer
    for name in PUBLIC_DEV_SOURCES:
        path = ROOT / name
        if path.is_symlink() or frozen['artifacts'].get(name) != reference(path):
            raise ValueError('readiness requires frozen unchanged public dev sources')
    tokenizer = AutoTokenizer.from_pretrained(frozen['launch_protocol']['model_path'], local_files_only=True)
    return load_requests(4, SUITES, tokenizer, dev_dir=ROOT / 'assets/upstream/dev')


def validate_science(source, *, root, frozen, phase4_sha256, not_before):
    science = read_reference(source, root)
    if science.get('phase4_sha256') != phase4_sha256:
        raise ValueError('head/regressions do not belong to the current Phase4 opening')
    requests = load_readiness_requests(frozen)
    if (science.get('readiness_protocol') != READINESS_PROTOCOL or
            read_reference(science['reference'], root) != dict(requests=requests)):
        raise ValueError('head readiness reference differs from the fixed public dev cohort')
    preflight = checked_head(science['preflight'], root=root, mode='preflight', frozen=frozen, not_before=not_before)
    if preflight['checks'][0]['prefix_sha256'] != sha_ids(requests[0]['input_ids']):
        raise ValueError('FP32 head preflight must use the first fixed public dev prompt')
    control = checked_head(science['control'], root=root, mode='control', frozen=frozen, not_before=not_before)
    cohorts, traces = {}, {}
    by_id = {request['id']: request for request in requests}
    for name in ('stock', 'ar', 'stock_long', 'healthy_stock', 'healthy_segmented', 'faulty', 'equivalent_head'):
        sources = science['cohorts'][name]
        if not sources:
            raise ValueError('missing healthy/fault/reduction cohort')
        traces[name] = []
        for item in sources:
            read_reference(item, root)
            trace = load_score_trace(item['path'], evidence_root=root)
            started = read_reference(trace['raw_evidence'], root).get('started_unix')
            request = by_id.get(trace['request_id'])
            if request is None or trace['prompt_ids'] != request['input_ids']:
                raise ValueError('readiness trace is not from the fixed public dev cohort')
            if (trace['scorer']['tree_sha'] != frozen['arms'][0]['tree_sha'] or
                    trace['generator']['tree_sha'] != frozen['arms'][0]['tree_sha'] or
                    trace['scorer']['server_args'].get('model_path') != frozen['launch_protocol']['model_path'] or
                    type(started) not in (int, float) or not math.isfinite(started) or started < not_before):
                raise ValueError('regressions must use current frozen stock generation and scoring')
            traces[name].append(trace)
        cohorts[name] = [item['path'] for item in sources]
    eligible = []
    for trace in traces['ar']:
        raw = read_reference(trace['generation_segments'][0], root)
        if (len(trace['output_ids']) == 2048 and
                raw['response'].get('meta_info', {}).get('finish_reason', {}).get('type') == 'length'):
            eligible.append(trace['request_id'])
    if not eligible:
        raise ValueError('no public AR request reached the registered injection boundary')
    first_per_suite = {}
    for request in requests:
        first_per_suite.setdefault(request['suite'], request['id'])
    for name, values in traces.items():
        expected = (list(first_per_suite.values()) if name == 'equivalent_head' else eligible
                    if name in ('stock_long', 'healthy_segmented', 'faulty') else list(by_id))
        if [trace['request_id'] for trace in values] != expected:
            raise ValueError('readiness cohort coverage/order differs from the fixed public dev protocol')
    if cohorts['equivalent_head'] != control['traces']:
        raise ValueError('reduction traces do not come from the executed head control')
    steps = []
    for path in cohorts['equivalent_head']:
        trace = load_score_trace(path, evidence_root=root)
        reduction = trace.get('head_reduction_control', {})
        if (reduction.get('head_identity') != control['head_identity'] or
                [step['reverse_token'] for step in reduction.get('steps', [])] != trace['output_ids'] or
                [step['raw_evidence'] for step in reduction.get('steps', [])] != trace['generation_segments']):
            raise ValueError('equivalent reduction does not bind its actual generated tokens')
        steps.extend(reduction['steps'])
    if steps != control['checks']:
        raise ValueError('reduction checks differ from their original traces')
    delta = calibrate_delta(cohorts['stock'], cohorts['ar'], evidence_root=root)
    baseline = calibrate_stock(cohorts['stock'], delta, evidence_root=root)
    long_baseline = calibrate_stock(cohorts['stock_long'], delta, evidence_root=root)
    selected = {load_score_trace(path, evidence_root=root)['request_id'] for path in cohorts['equivalent_head']}
    subset = [path for path in cohorts['stock'] if load_score_trace(path, evidence_root=root)['request_id'] in selected]
    head_baseline = calibrate_stock(subset, delta, evidence_root=root)
    verdicts = {}
    for name, paths in ((name, cohorts[name]) for name in
                        ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head', 'faulty')):
        audits = science.get('audits', {}).get(name, [])
        for item in audits:
            read_reference(item, root)
        calibration = long_baseline if name in ('healthy_segmented', 'faulty') else head_baseline if name == 'equivalent_head' else baseline
        verdicts[name] = judge_scored_forcing(calibration, paths, evidence_root=root,
                                            prefill_audits=[item['path'] for item in audits])
    coverage = [validate_injected_generation(path, evidence_root=root) for path in cohorts['faulty']]
    post = sum(item['post2048_tokens'] for item in coverage)
    ready = (all(verdicts[name]['correctness_passed'] for name in
                 ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head')) and
             verdicts['faulty']['event_flagged'] and not verdicts['faulty']['correctness_passed'] and post >= 1024)
    return dict(scientific_ready=ready, verdicts=verdicts, post2048_tokens=post, source=source,
                t3_passed=False, promoted=False, ledger_eligible=False)


def source_uids_idle():
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / 'status').read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        uid = next(line.split()[1:] for line in status.splitlines() if line.startswith('Uid:'))
        if any(int(value) in (60010, 60011) for value in uid):
            raise RuntimeError('source server UIDs are already in use; refusing Phase4 request opening')


class LiveRuntime:
    def __init__(self, base, frozen, *, isolate_network=False):
        if type(isolate_network) is not bool:
            raise ValueError('network enhancement must be an explicit boolean')
        self.base, self.frozen = base, frozen
        self.isolate_network = isolate_network
        self.environment = clean_environment()
        self.environment.update(SP_TARGET=base['target'], SP_DRAFT=base['draft'],
                                SP_ENGINE=base['stock_engine'], SP_TREE_SHA=base['stock_tree_sha'])

    @contextmanager
    def guard(self):
        with ExitStack() as resources:
            identity = dict(uid=os.geteuid(), pid=os.getpid(), network_isolated=False,
                scope='controller/source UID and private-file boundary; network and IPC retained',
                research_shutdown_verified=False)
            if self.isolate_network:
                enhancement = resources.enter_context(private_network())
                identity.update(network_isolated=True, optional_network_enhancement=enhancement)
            actual = wait_for_idle([0, 1])
            if [{key: gpu[key] for key in ('index', 'uuid', 'name')} for gpu in actual] != [
                    {key: gpu[key] for key in ('index', 'uuid', 'name')} for gpu in self.frozen['gpus']]:
                raise ValueError('live GPU allocation differs from freeze')
            source_uids_idle()
            for gpu in actual:
                resources.enter_context(gpu_lock(gpu))
            check_ports([30100, 30110, 30120, 30130])
            yield identity

    def measure(self, arms, requests, directory, cap, number):
        check_ports([30100, 30110])
        started = time.time()
        def factory(name, url, **options):
            return TimedSourceArm(name, url, directory=directory, spec=self.base, **options)
        run_round(arms, self.frozen['gpus'], [30100, 30110], number - 1, requests, directory,
            self.environment, cap, min(2, len(requests)), 1200, stable_null=True,
            server_factory=PrivateSourceServer, arm_factory=factory)
        wait_for_idle([0, 1])
        return normalize_round(directory, cap=cap, number=number, started_unix=started)

    def score(self, root, requests, records):
        from harness.candidate import check_inputs
        check_inputs(self.base)
        completed = max(record['finished_unix'] for rounds in records.values() for record in rounds)
        opening = reference(root / 'phase4.json')['sha256']
        directory = root / 'scoring'
        directory.mkdir(mode=0o700)
        reference_dir = directory / 'reference'
        reference_dir.mkdir()
        readiness_requests = load_readiness_requests(self.frozen)
        head_reference = _save(reference_dir / 'manifest.json', dict(requests=readiness_requests))
        stock = self.frozen['arms'][0]
        gpus = self.frozen['gpus']
        with ExitStack() as resources:
            launch(stock, 'scorer', gpus[1], directory, self.environment, resources)
            scorer = NativeClient('http://127.0.0.1:30130', directory / 'scorer-raw')
            scorer.scorer_identity(stock['tree_sha'])
            head_process('preflight', directory / 'head-preflight', reference_dir, stock['tree_sha'])
            checked_head(reference(directory / 'head-preflight/result.json'), root=root, mode='preflight',
                         frozen=self.frozen, not_before=completed)
            campaign = Campaign(directory, scorer, evidence_root=root)
            cohorts = fresh_generations(campaign, directory, [dict(stock, name='ar'), stock],
                                         gpus, self.environment, readiness_requests)
            head = head_process('control', directory / 'head-control', reference_dir, stock['tree_sha'])
            cohorts['equivalent_head'] = head['traces']
            delta = calibrate_delta(cohorts['stock'], cohorts['ar'], evidence_root=root)
            science = dict(phase4_sha256=opening, readiness_protocol=READINESS_PROTOCOL, reference=head_reference,
                preflight=reference(directory / 'head-preflight/result.json'),
                control=reference(directory / 'head-control/result.json'),
                cohorts={name: [reference(path) for path in paths] for name, paths in cohorts.items()},
                audits={name: [reference(path) for path in campaign.audit('science-' + name, cohorts[name], delta['delta'])]
                        for name in ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head', 'faulty')})
            science_ref = _save(directory / 'science.json', science)
            validate_science(science_ref, root=root, frozen=self.frozen,
                             phase4_sha256=opening, not_before=completed)
            actual_directory = directory / 'actual'
            actual_directory.mkdir(mode=0o700)
            actual = Campaign(actual_directory, scorer, evidence_root=root)
            ar = {}
            with ExitStack() as generation:
                launch(stock, 'ar', gpus[0], actual_directory, self.environment, generation)
                client = NativeClient('http://127.0.0.1:30120', actual_directory / 'ar-raw')
                identity = client.server_identity(stock['tree_sha'])
                for cap in CAPS:
                    ar[cap], _, _ = actual.generate(f'ar-cap-{cap}', requests, client, identity, cap)
            wait_for_idle([0])
            forcing = []
            for cap in CAPS:
                for number in (1, 2):
                    entry = dict(cap=cap, round=number, ar=[reference(path) for path in ar[cap]])
                    paths = {}
                    pairs = records[cap, 'candidate'][number - 1]['pairs']
                    for role, key in (('stock', 'a'), ('candidate', 'b')):
                        paths[role] = [actual.save_trace(f'cap-{cap}-round-{number}-{role}', request,
                            pair[key]['output_ids'], pair[key]['generator'], [pair[key]['raw_evidence']])
                            for request, pair in zip(requests, pairs)]
                        entry[role] = [reference(path) for path in paths[role]]
                    delta = calibrate_delta(paths['stock'], ar[cap], evidence_root=root)
                    entry['prefill_audits'] = [reference(path) for path in
                        actual.audit(f'cap-{cap}-round-{number}-candidate', paths['candidate'], delta['delta'])]
                    forcing.append(entry)
        check_ports([30100, 30110, 30120, 30130])
        write_json(directory / 'cleanup.json', wait_for_idle([0, 1]))
        check_inputs(self.base)
        return forcing, science_ref


def execute_schedule(freeze, request_path, runtime):
    """Trusted in-process adapter seam for CPU fixtures; never expose it as a role tool."""
    root, frozen = _frozen(freeze)
    with runtime.guard() as identity:
        opened = open_phase4(freeze, request_path)
        state = read_reference(opened, root)
        requests = state['requests']
        if any(not request['id'].isascii() or not request['id'].replace('-', '').replace('_', '').isalnum()
               for request in requests):
            raise ValueError('request IDs must be safe file stems, never paths')
        _save(root / 'runtime-isolation.json', identity)
        records, sessions = {}, []
        for cap in CAPS:
            for phase in PHASES:
                arms = frozen['arms'] if phase == 'candidate' else [
                    dict(frozen['arms'][0], name='stock-a'), dict(frozen['arms'][0], name='stock-b')]
                rounds = []
                for number in (1, 2):
                    directory = root / f'cap-{cap}-{phase}-round-{number}'
                    record = runtime.measure(arms, requests, directory, cap, number)
                    rounds.append(record)
                records[cap, phase] = rounds
                session_ref = _save(root / f'cap-{cap}-{phase}.json', dict(protocol=PROTOCOL, cap=cap,
                    phase=phase, rounds=[_save(root / f'cap-{cap}-{phase}-round-{number}.json', record)
                                        for number, record in enumerate(rounds, 1)]))
                sessions.append(dict(cap=cap, phase=phase, source=session_ref))
        forcing, science = runtime.score(root, requests, records)
        evidence = _save(root / 'phase4-evidence.json', dict(protocol=PROTOCOL,
            phase4_sha256=opened['sha256'], sessions=sessions, forcing=forcing))
        protocol = validate_phase4(opened, evidence)
        completed = max(record['finished_unix'] for rounds in records.values() for record in rounds)
        science_result = validate_science(science, root=root, frozen=frozen,
            phase4_sha256=opened['sha256'], not_before=completed) if science else None
        ready = science_result is not None and science_result['scientific_ready'] and protocol['protocol_evidence_passed']
        control = frozen.get('purpose') == 'controller-negative-control'
        complete = science_result is not None
        correct = all(entry['correctness']['correctness_passed'] for entry in protocol['caps'])
        performance = all(entry['performance']['performance_passed'] for entry in protocol['caps'])
        scientific_ready = complete and science_result['scientific_ready']
        result = dict(runtime_status=('blocked' if not complete else 'maintenance-stock-control-complete' if control
            else 'evidence-ready-awaiting-independent-final' if ready else 'scientific-rejection'),
            purpose=frozen.get('purpose'),
            execution_completed=complete, protocol_verified=True, scientific_ready=scientific_ready,
            correctness_passed=correct, performance_passed=performance,
            expected_rejection=control and scientific_ready and correct and not performance,
            opened=opened, evidence=evidence, protocol=protocol, science=science_result,
            missing=(['current FP32 head preflight and healthy/fault/reduction evidence missing'] if science_result is None
                     else ['healthy/fault/reduction judge regression rejected'] if not science_result['scientific_ready']
                     else ['paired performance or forcing gate rejected'] if not protocol['protocol_evidence_passed'] else []),
            unverified_final_requirements=['independent T0/dev prerequisite review',
                'real GPU validation and controller/research UID/private-evidence boundary',
                'broker evidence that all research roles stopped before Phase4', 'job terminal state and archival',
                'independent final/T3 controller authorization'],
            t3_passed=False, promoted=False, ledger_eligible=False)
    _frozen(freeze)
    return _save(root / 'runtime-result.json', result)


def run(bundle, freeze, request_path, *, isolate_network=False, maintenance_stock_control=False):
    root, frozen, base = check_bundle(bundle, freeze, maintenance_stock_control=maintenance_stock_control)
    if not maintenance_stock_control:
        validate_dev(frozen)
    _private(root, directory=True)
    if [gpu['index'] for gpu in frozen['gpus']] != [0, 1]:
        raise ValueError('stock head/scoring launcher currently requires frozen GPU indices [0,1]')
    with (root / 'runtime.log').open('x') as log, redirect_stdout(log), redirect_stderr(log):
        try:
            return execute_schedule(freeze, request_path, LiveRuntime(base, frozen, isolate_network=isolate_network))
        except BaseException as error:
            _save(root / 'runtime-failed.json', dict(error_type=type(error).__name__,
                error=str(error), time_unix=time.time(), execution_completed=False,
                failure_kind='scientific-evidence-incomplete' if isinstance(error, ValueError) else 'runtime-execution-error',
                t3_passed=False, promoted=False, ledger_eligible=False))
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--request-path', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--isolate-network', action='store_true', help='optional namespace enhancement, not a T3 criterion')
    parser.add_argument('--maintenance-stock-control', action='store_true')
    args = parser.parse_args()
    frozen = dict(path=str(args.freeze.absolute()), sha256=args.freeze_sha256)
    if not args.execute:
        check_bundle(args.bundle, frozen, maintenance_stock_control=args.maintenance_stock_control)
        print(json.dumps(dict(status='plan-only', rounds=12, caps=CAPS,
                              optional_network_enhancement=args.isolate_network, t3_passed=False)))
        return
    try:
        receipt = run(args.bundle, frozen, args.request_path, isolate_network=args.isolate_network,
                      maintenance_stock_control=args.maintenance_stock_control)
    except BaseException:
        print(json.dumps(dict(status='blocked', t3_passed=False, private_logs=True)))
        raise SystemExit(1) from None
    result = read_reference(receipt, args.freeze.parent)
    print(json.dumps(dict(runtime_status=result['runtime_status'], result=receipt, t3_passed=False)))
    if result['runtime_status'] == 'blocked':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
