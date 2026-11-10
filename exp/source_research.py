"""Trusted source-option engine diagnostics; never an independent promotion."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from controller.dev_campaign import validate_packet
from controller.http_transport import Arm
from controller.scoring import NativeClient, server_arguments
from controller.scored_forcing import read_reference
from exp.candidate_smoke import FROZEN_STOCK_SHA, serve_command
from exp.p3_pair_run import SETTING, SUITES, Server, check_ports, clean_environment, gpu_lock, inspect_gpus, interrupted, load_requests, run_round, summarize, wait_for_idle, write_json
from harness.candidate import expected_arguments, make_spec
from harness.build_engine import tree_sha
from harness.source_candidate import build_bundle, candidate_arm, file_sha, load_bundle, validate_action


def device_paths(gpu):
    import pynvml
    pynvml.nvmlInit()
    try:
        handle = pynvml.nvmlDeviceGetHandleByUUID(gpu['uuid'])
        reported_minor = pynvml.nvmlDeviceGetMinorNumber(handle)
    finally:
        pynvml.nvmlShutdown()
    information = [path.read_text() for path in Path('/proc/driver/nvidia/gpus').glob('*/information')]
    visible = os.environ.get('NVIDIA_VISIBLE_DEVICES', '').split(',')
    if len(visible) != 2 or len(set(visible)) != 2 or gpu['uuid'] not in visible:
        raise ValueError('exact two-UUID pod allocation required for source execution')
    minors = [kernel_device_minor(information, uuid) for uuid in visible]
    if type(reported_minor) is not int or reported_minor < 0:
        raise ValueError('invalid NVML NVIDIA device minor')
    allowed = ['/dev/nvidia' + str(minor) for minor in minors]
    allowed += [str(path) for path in Path('/dev').glob('nvidia*')
        if path.name in ('nvidiactl', 'nvidia-uvm', 'nvidia-uvm-tools') and (path.is_file() or path.is_char_device())]
    forbidden = next((str(path) for path in Path('/dev').glob('nvidia[0-9]*')
        if str(path) not in allowed), None)
    return allowed, forbidden


def kernel_device_minor(information, uuid):
    matches = []
    for content in information:
        fields = {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip()
            for line in content.splitlines() if ':' in line}
        if fields.get('GPU UUID') == uuid:
            matches.append(fields.get('Device Minor', ''))
    if len(matches) != 1 or not matches[0].isdecimal():
        raise ValueError('physical GPU UUID/minor must have a unique kernel-driver mapping')
    return int(matches[0])


def sandbox_payload(arm, gpu, port, scratch, allowed, canary, environment):
    devices, forbidden = device_paths(gpu)
    engine = Path(arm['engine'])
    cache = scratch / 'cache'
    cache.mkdir(mode=0o755)
    bootstrap = scratch / 'trusted-bootstrap'
    bootstrap.mkdir(mode=0o755)
    bootstrap.chmod(0o755)
    shutil.copyfile(ROOT / 'harness/source_cache.py', bootstrap / 'trusted_source_cache.py')
    (bootstrap / 'trusted_source_cache.py').chmod(0o444)
    runtime = Path(sys.prefix)
    executables = [str(path.resolve()) for path in (runtime / 'bin').iterdir()
        if path.is_file() and os.access(path, os.X_OK)]
    for prefix in ('libexec', 'lib/gcc'):
        executables += [str(path.resolve()) for path in (runtime / prefix).rglob('*')
            if path.is_file() and os.access(path, os.X_OK)]
    executables += [str(path.resolve()) for path in map(Path, ('/bin/sh', '/bin/bash', '/usr/bin/env',
        '/usr/bin/uname', '/usr/bin/ld', '/usr/bin/as', '/usr/bin/ninja', '/usr/bin/gcc', '/usr/bin/g++')) if path.is_file()]
    for helper in ('nvidia-smi', 'ldconfig', 'numactl'):
        executable = shutil.which(helper)
        if not executable and helper == 'ldconfig':
            executable = next((name for name in ('/sbin/ldconfig', '/usr/sbin/ldconfig') if Path(name).is_file()), None)
        if not executable and helper == 'nvidia-smi':
            raise RuntimeError('fixed NVIDIA runtime helper missing')
        if executable:
            executables.append(str(Path(executable).resolve(strict=True)))
    for helper in ('/sbin/ldconfig.real', '/usr/sbin/ldconfig.real'):
        if Path(helper).is_file():
            executables.append(str(Path(helper).resolve(strict=True)))
    readonly = [str(runtime), str(engine), str(allowed), str(bootstrap), environment['SP_TARGET'], environment['SP_DRAFT']]
    for name in ('/usr/local/cuda', '/sys/devices', '/sys/class', '/sys/bus', '/proc',
                 '/gpfs/users/jixinpeng/specpilot_data/shared/cuda-compat/usr/local/cuda-13.0/compat'):
        if Path(name).exists():
            readonly.append(name)
    for name in environment.get('LD_LIBRARY_PATH', '').split(':'):
        if name and Path(name).is_dir():
            readonly.append(str(Path(name).resolve()))
    env = {key: environment[key] for key in ('PATH', 'CC', 'CXX', 'CUDA_HOME', 'LD_LIBRARY_PATH') if key in environment}
    env.update(HOME=str(cache), TMPDIR=str(cache), PYTHONPATH=str(bootstrap) + ':' + str(engine / 'python') + ':' + str(engine / 'lab'),
        PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', CUDA_VISIBLE_DEVICES=gpu['uuid'],
        HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
        SP_TREE_SHA=arm['tree_sha'], SGLANG_JIT_DEEPGEMM_PRECOMPILE='0',
        SGLANG_NUMA_BIND_V2='0', TRITON_CACHE_MANAGER='trusted_source_cache:SourceCacheManager', LANG='C.UTF-8')
    for key, suffix in [('SGLANG_CACHE_DIR', 'sglang'), ('SGLANG_JIT_CACHE_DIR', 'sglang/jit'),
                        ('TRITON_CACHE_DIR', 'triton'), ('FLASHINFER_WORKSPACE_BASE', 'flashinfer'),
                        ('TORCH_EXTENSIONS_DIR', 'torch_extensions')]:
        env[key] = str(cache / suffix)
    base = dict(target=environment['SP_TARGET'], draft=environment['SP_DRAFT'])
    return dict(uid=60010 if arm['name'] in ('stock', 'stock-a') else 60011, scratch=str(cache),
        readonly=readonly, executables=sorted(set(executables)), devices=devices, forbidden_device=forbidden,
        protected_proc='/proc/' + str(os.getpid()) + '/environ',
        protected_pid=os.getpid(),
        executable_trees=[str(runtime)] + ([str(Path('/usr/local/cuda').resolve())] if Path('/usr/local/cuda').exists() else []),
        allowed_read=str(allowed), allowed_content=allowed.read_text(), canary=str(canary),
        command=serve_command(base, arm['block'], sys.executable, port), environment=env)


def gpu_runtime_probe(arm, gpu, directory, environment):
    scratch = Path(tempfile.mkdtemp(prefix='specpilot-source-probe-'))
    scratch.chmod(0o755)
    try:
        source = scratch / 'source.txt'
        source.write_text('authorized source probe\n')
        canary = scratch / 'protected.txt'
        canary.write_text('protected probe\n')
        write_json(directory / 'kernel-device-layout.json', dict(selected=gpu,
            information=[path.read_text() for path in Path('/proc/driver/nvidia/gpus').glob('*/information')],
            visible_environment={key: os.environ.get(key) for key in ('CUDA_VISIBLE_DEVICES', 'NVIDIA_VISIBLE_DEVICES')}))
        payload = sandbox_payload(arm, gpu, 30400, scratch, source, canary, environment)
        write_json(directory / 'gpu-device-layout.json', dict(selected=gpu, allowed_devices=payload['devices'],
            kernel_information=[path.read_text() for path in Path('/proc/driver/nvidia/gpus').glob('*/information')],
            cuda_environment={key: os.environ.get(key) for key in ('CUDA_VISIBLE_DEVICES', 'NVIDIA_VISIBLE_DEVICES')}))
        payload['trusted_gpu_probe'] = True
        trace_library = scratch / 'open-trace.so'
        build = subprocess.run([environment['CC'], '-shared', '-fPIC', '-O2',
            str(ROOT / 'harness/source_open_trace.c'), '-ldl', '-o', str(trace_library)],
            capture_output=True, text=True, timeout=60)
        write_json(directory / 'diagnostic-trace-build.json', dict(exit_code=build.returncode,
            stdout=build.stdout, stderr=build.stderr, scope='trusted diagnostic only; not a scientific kernel'))
        if build.returncode == 0:
            payload['environment']['LD_PRELOAD'] = str(trace_library)
        command = [sys.executable, '-I', '-B', str(ROOT / 'harness/source_boundary.py')]
        tracer = shutil.which('strace')
        if tracer:
            command = [tracer, '-f', '-e', 'trace=file,process,network', '-o',
                str(directory / 'gpu-runtime-strace.txt'), *command]
        process = subprocess.run(command, input=json.dumps(payload), env=payload['environment'],
            capture_output=True, text=True, timeout=90)
        write_json(directory / 'gpu-runtime-probe.json', dict(exit_code=process.returncode,
            stdout=process.stdout, stderr=process.stderr, strace_available=bool(tracer)))
        if process.returncode or 'SOURCE_GPU_READY' not in process.stdout:
            matrix = {}
            for name in ('uid_only', 'filesystem_only', 'seccomp_only', 'pod_devices', 'expanded_readonly', 'numeric_device'):
                variant = dict(payload, trusted_diagnostic=name)
                variant['environment'] = dict(payload['environment'])
                if name == 'pod_devices':
                    variant['devices'] = list(payload['devices'])
                    for assigned in inspect_gpus([0, 1]):
                        variant['devices'].extend(device_paths(assigned)[0])
                    variant['devices'] = sorted(set(variant['devices']))
                if name == 'expanded_readonly':
                    variant['readonly'] = [*payload['readonly'], '/usr', '/etc', '/sys']
                if name == 'numeric_device':
                    variant['environment']['CUDA_VISIBLE_DEVICES'] = str(gpu['index'])
                process = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'harness/source_boundary.py')],
                    input=json.dumps(variant), env=variant['environment'], capture_output=True, text=True, timeout=60)
                matrix[name] = dict(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr,
                    gpu_ready='SOURCE_GPU_READY' in process.stdout, diagnostic_only=True, source_execution_allowed=False)
                write_json(directory / f'gpu-diagnostic-{name}.json', matrix[name])
            write_json(directory / 'gpu-runtime-matrix.json', matrix)
            raise RuntimeError('isolated CUDA initialization failed; see gpu-runtime-probe.json/strace')
    finally:
        shutil.rmtree(scratch)


class SourceServer(Server):
    def start(self):
        if os.geteuid() != 0:
            raise RuntimeError('source server requires the verified remote UID-drop launcher')
        self.sandbox = Path(tempfile.mkdtemp(prefix='specpilot-source-server-'))
        self.sandbox.chmod(0o755)
        allowed = self.sandbox / 'source-canary.txt'
        allowed.write_text('authorized source probe\n')
        canary = self.sandbox / 'protected-canary.txt'
        canary.write_text('protected probe\n')
        runtime_engine = self.sandbox / 'engine'
        shutil.copytree(self.arm['engine'], runtime_engine, symlinks=True,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.git'))
        if tree_sha(runtime_engine) != self.arm['tree_sha']:
            raise ValueError('concrete source runtime copy differs from the frozen tree')
        payload = sandbox_payload(dict(self.arm, engine=str(runtime_engine)), self.gpu, self.port,
            self.sandbox, allowed, canary, self.environment)
        ready_read, ready_write = os.pipe()
        payload['ready_fd'] = ready_write
        write_json(self.output_dir / f'{self.arm["name"]}.sandbox.json', payload)
        self.log = (self.output_dir / f'{self.arm["name"]}.launcher.log').open('x')
        self.process = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'harness/source_boundary.py')],
            stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, cwd=ROOT,
            env=payload['environment'], close_fds=True, pass_fds=(ready_write,), start_new_session=True, text=True)
        os.close(ready_write)
        self.process.stdin.write(json.dumps(payload))
        self.process.stdin.close()
        ticks = Path(f'/proc/{self.process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        write_json(self.output_dir / f'{self.arm["name"]}.process.json', dict(pid=self.process.pid, start_ticks=int(ticks)))
        try:
            if not select.select([ready_read], [], [], 30)[0]:
                raise RuntimeError('source boundary did not acknowledge before engine execution')
            with os.fdopen(ready_read) as source:
                ready_read = None
                receipt = json.loads(source.readline(16384))
            if (receipt.get('event') != 'SOURCE_BOUNDARY_READY' or not all(receipt['denied'].values()) or
                    receipt['uid'] != payload['uid'] or not receipt['landlock_applied'] or not receipt['seccomp_applied']):
                raise RuntimeError('source boundary pipe has an invalid receipt')
            write_json(self.output_dir / f'{self.arm["name"]}.boundary.json', dict(receipt, trusted_pipe=True))
        finally:
            if ready_read is not None:
                os.close(ready_read)

    def wait_ready(self, timeout):
        super().wait_ready(timeout)
        receipt_path = self.output_dir / f'{self.arm["name"]}.boundary.json'
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
        else:
            raise RuntimeError('no independently captured pre-source boundary receipt')
        if (receipt.get('event') != 'SOURCE_BOUNDARY_READY' or not all(receipt['denied'].values()) or
                receipt['uid'] not in (60010, 60011) or not receipt['landlock_applied'] or not receipt['seccomp_applied']):
            raise RuntimeError('source server has no valid pre-source boundary receipt')

    def stop(self):
        try:
            super().stop()
        finally:
            if self.process is not None:
                write_json(self.output_dir / f'{self.arm["name"]}.stopped.json', dict(stopped=self.process.poll() is not None))
            if hasattr(self, 'sandbox'):
                shutil.rmtree(self.sandbox)


class SourceCapturedArm(Arm):
    def __init__(self, name, url, *, directory, spec, **options):
        options['trace_timing'] = True
        super().__init__(name, url, raw_dir=directory / f'{name}-raw', **options)
        client = NativeClient(url, directory / f'{name}-identity')
        self.generator = client.server_identity(self.tree_sha)
        actual = server_arguments(read_reference(self.generator['evidence'], directory)['response'])
        expected = expected_arguments(spec, self.block_size)
        self.generator['server_args'] = {key: actual.get(key) for key in expected}
        if self.generator['tree_sha'] != self.tree_sha or self.generator['server_args'] != expected:
            raise ValueError('source server identity/startup settings differ')

    def step(self, *arguments, **options):
        return dict(super().step(*arguments, **options), generator=self.generator)


def audit(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    request_path = directory.parent / 'request.json'
    record = json.loads(request_path.read_text())
    if (manifest['request_sha256'] != file_sha(request_path) or
            manifest['source_archive_sha256'] != file_sha(directory.parent / 'source.tar') or
            manifest['source_pin'] != record['source_pin'] or manifest['action'] != record['action']):
        raise ValueError('source diagnostic request/trusted source identity differs')
    preflight = record['mode'] == 'source-preflight'
    action = record['action'] if preflight else validate_action(record['action'])
    if not preflight:
        bundle = load_bundle(manifest['bundle'])
        if bundle['patch'] != json.loads((directory.parent / 'patch.json').read_text()):
            raise ValueError('diagnostic patch differs from the frozen role patch')
        if record['patch_sha256'] != file_sha(directory.parent / 'patch.json'):
            raise ValueError('role source patch changed')
        if (record['self_check_sha256'] != file_sha(directory.parent / 'self-check.py') or
                record['cpu_receipt_sha256'] != file_sha(directory.parent / 'cpu-receipt.json')):
            raise ValueError('source CPU self-check identity changed')
        base = bundle['base']
    else:
        base = manifest['base']
    if base['source_pin'] != record['source_pin']:
        raise ValueError('source baseline pin differs')
    comparison_sha = base['stock_tree_sha']
    if record.get('comparison_base_sha256'):
        comparison_path = directory.parent / 'comparison-base.json'
        comparison = load_bundle(directory / 'comparison-bundle')
        if (preflight or file_sha(comparison_path) != record['comparison_base_sha256']
                or comparison['patch'] != json.loads(comparison_path.read_text())
                or comparison['base'] != base):
            raise ValueError('comparison stack differs from the frozen canonical-stock patch')
        comparison_sha = comparison['candidate_tree_sha']
    arms = manifest['arms']
    if (len(arms) != 2 or [arm['name'] for arm in arms] != ['stock', 'candidate'] or
            any(arm['block'] != 8 or arm['env'] for arm in arms) or
            arms[0]['tree_sha'] != comparison_sha or
            arms[1]['tree_sha'] != (base['stock_tree_sha'] if preflight else bundle['candidate_tree_sha']) or
            len(manifest['gpus']) != 2 or len({gpu['uuid'] for gpu in manifest['gpus']}) != 2):
        raise ValueError('source arm/tree/physical GPU identity differs')
    requests = manifest['requests']
    if (len(requests) != 5 * action['per_suite'] or {row['suite'] for row in requests} != set(SUITES) or
            len({row['id'] for row in requests}) != len(requests)):
        raise ValueError('invalid source diagnostic request coverage')
    pairs = []
    identities = set()
    for number in (0, 1):
        root = directory / f'round-{number + 1:02d}'
        gpus = manifest['gpus'] if number == 0 else list(reversed(manifest['gpus']))
        expected = [dict(arm=arm, gpu=gpu, port=port) for arm, gpu, port in zip(manifest['arms'], gpus, manifest['ports'])]
        if json.loads((root / 'deployment.json').read_text()) != dict(round=number + 1, assignments=expected):
            raise ValueError('physical source diagnostic assignment differs')
        rows = [json.loads(line) for line in (root / 'pairs.jsonl').read_text().splitlines()]
        warmup = [json.loads(line) for line in (root / 'warmup.jsonl').read_text().splitlines()]
        if [row['phase'] for row in warmup] != ['short', 'short'] + ['full'] * len(requests):
            raise ValueError('source warmup coverage changed')
        if ([row['id'] for row in rows] != [row['id'] for row in requests] or
                json.loads((root / 'complete.json').read_text()) != dict(round=number + 1, pairs=len(requests))):
            raise ValueError('incomplete source diagnostic round')
        for key, assignment in zip(('a', 'b'), expected):
            name = assignment['arm']['name']
            process = json.loads((root / f'{name}.process.json').read_text())
            identity = (process['pid'], process['start_ticks'])
            if identity in identities or min(identity) <= 0:
                raise ValueError('source servers were not fresh')
            identities.add(identity)
            receipt = json.loads((root / f'{name}.boundary.json').read_text())
            if not all(receipt['denied'].values()) or receipt['uid'] not in (60010, 60011):
                raise ValueError('source boundary missing')
            if json.loads((root / f'{name}.stopped.json').read_text()) != dict(stopped=True):
                raise ValueError('source server still running')
            arm_rows = [json.loads(line) for line in (root / f'{name}.jsonl').read_text().splitlines()]
            if arm_rows != [row[key] for row in rows]:
                raise ValueError('canonical source diagnostic arm data changed')
            for row, request in zip(arm_rows, requests):
                validate_packet(row, request, assignment, action['max_new_tokens'], directory,
                    expected_arguments(base, 8))
            for row, request in zip(warmup, requests[:2] + requests):
                cap = min(32, action['max_new_tokens']) if row['phase'] == 'short' else action['max_new_tokens']
                validate_packet(row[key], request, assignment, cap, directory, expected_arguments(base, 8))
        pairs.extend(rows)
    result = summarize(pairs, requests, 2)
    result.update(protocol='source-option-research-v1', controller_accepted=False, candidate_promoted=False,
        lossless_verified=False, preflight=preflight, source_spec_sha256=None if preflight else bundle['spec_sha256'],
        scope='public dev source diagnostic; no lossless, sealed or promotion claim')
    if record.get('comparison_base_sha256'):
        result['comparison_tree_sha'] = comparison_sha
    if preflight and any(row['a']['output_ids'] != row['b']['output_ids'] for row in pairs):
        raise ValueError('sandboxed stock preflight output differs')
    return result


def run(request, directory):
    from transformers import AutoTokenizer
    record = json.loads(request.read_text())
    preflight = record['mode'] == 'source-preflight'
    action = record['action'] if preflight else validate_action(record['action'])
    directory.mkdir(parents=True, exist_ok=False)
    environment = clean_environment()
    target = '/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B'
    draft = '/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2'
    environment.update(SP_TARGET=target, SP_DRAFT=draft)
    stock = '/gpfs/users/jixinpeng/specpilot_data/work/engines/h100_c1_qwen38-27b_dflash2-stock'
    config = Path('/gpfs/users/jixinpeng/SpecDec/SpecPilot/assets/upstream/configs') / SETTING / 'config.json'
    if file_sha(config) != file_sha(ROOT / 'assets/upstream/configs' / SETTING / 'config.json'):
        raise ValueError('live stock configuration differs from the frozen trusted source')
    base = make_spec(stock, config, target, draft, record['source_pin'])
    if base['stock_tree_sha'] != FROZEN_STOCK_SHA:
        raise ValueError('source research stock identity changed')
    arms = [dict(name='stock', block=8, tree_sha=FROZEN_STOCK_SHA, engine=stock, env={})]
    if preflight:
        arms.append(dict(arms[0], name='candidate', option_enabled=False))
    else:
        patch = directory.parent / 'patch.json'
        if file_sha(patch) != record['patch_sha256']:
            raise ValueError('source patch no longer matches its frozen request')
        build_bundle(base, patch, directory / 'bundle')
        arms.append(candidate_arm(directory / 'bundle', enabled=True))
        if record.get('comparison_base_sha256'):
            comparison_path = directory.parent / 'comparison-base.json'
            if file_sha(comparison_path) != record['comparison_base_sha256']:
                raise ValueError('frozen comparison stack patch changed')
            build_bundle(base, comparison_path, directory / 'comparison-bundle')
            arms[0] = dict(candidate_arm(directory / 'comparison-bundle', enabled=True), name='stock')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    with ExitStack() as resources:
        gpus = inspect_gpus([0, 1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        if preflight:
            gpu_runtime_probe(arms[0], gpus[0], directory, environment)
        tokenizer = AutoTokenizer.from_pretrained(target, trust_remote_code=False, local_files_only=True)
        requests = load_requests(action['per_suite'], SUITES, tokenizer)
        if record['mode'] == 'source-controller':
            from exp.engine_dev_gate import run_gate
            bundle = load_bundle(directory / 'bundle')
            print(json.dumps(run_gate(directory, record, base, arms, gpus, requests, environment,
                server_factory=SourceServer, arm_class=SourceCapturedArm,
                candidate_origin=dict(source='direction source-option request', spec_sha256=bundle['spec_sha256'],
                    option_id=bundle['patch']['option_id'], changed_files=bundle['changed_files']))), flush=True)
            return
        manifest = dict(action=action, base=base, source_pin=record['source_pin'],
            request_sha256=file_sha(request), source_archive_sha256=os.environ['SP_SOURCE_ARCHIVE_SHA'],
            bundle=str(directory / 'bundle'), gpus=gpus, arms=arms, ports=[30400, 30410],
            requests=requests, started_unix=time.time())
        write_json(directory / 'manifest.json', manifest)
        for number in (0, 1):
            check_ports(manifest['ports'])
            round_dir = directory / f'round-{number + 1:02d}'
            def factory(name, url, **options):
                return SourceCapturedArm(name, url, directory=round_dir, spec=base, **options)
            run_round(arms, gpus, manifest['ports'], number, requests, round_dir, environment,
                action['max_new_tokens'], 2, 1200, server_factory=SourceServer, arm_factory=factory, stable_null=True)
            wait_for_idle([0, 1])
        write_json(directory / 'cleanup.json', wait_for_idle([0, 1]))
        result = audit(directory)
        write_json(directory / 'result.json', result)
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'audit'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'run':
        run(args.request.absolute(), args.directory.absolute())
    else:
        print(json.dumps(audit(args.directory)))


if __name__ == '__main__':
    main()
