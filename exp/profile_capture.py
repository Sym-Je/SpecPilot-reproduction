"""Trusted, bounded canonical-stock profiling; never a performance acceptance."""

import argparse
import ast
import base64
from contextlib import ExitStack
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from controller.scoring import NativeClient, checked_tokens, server_arguments
from exp.candidate_smoke import FROZEN_STOCK_SHA, serve_command
from exp.diagnosis_profile import ProfileClient
from exp.p3_pair_run import SUITES, Server, check_ports, clean_environment, gpu_lock, load_requests, wait_for_idle
from exp.source_research import SourceServer, kernel_device_minor
from harness.candidate import check_inputs, check_tree, expected_arguments, validate_spec
from harness.build_engine import tree_sha


SCHEMA = 'stock-profile-capture-v1'
PORT = 30500
DEADLINE = 2700
PROFILE_STEPS = 128
TOTAL_LIMIT = 4 * 1024 ** 3
FILE_LIMIT = 512 * 1024 ** 2
SOURCE_LIMIT = 128 * 1024 ** 2
WORKLOADS = {f'{suite}:{index}': dict(suite=suite, index=index) for suite in SUITES for index in range(4)}
PRESETS = {'graph-128': dict(mode='canonical-stock-graph', profile_steps=128, max_new_tokens=2048,
    warmup_tokens=32, record_shapes=True, with_stack=True, detailed_annotations=True,
    activities=['CPU', 'GPU'], deadline_seconds=2700)}
SOURCES = ('exp/profile_capture.py', 'harness/source_boundary.py', 'harness/source_cache.py') + tuple(
    f'assets/upstream/dev/{suite}.jsonl' for suite in SUITES)
MODEL_METADATA = ('config.json', 'model.safetensors.index.json', 'tokenizer.json', 'tokenizer_config.json',
                  'tokenizer.model', 'special_tokens_map.json', 'chat_template.jinja')
WEIGHT_AUDIT = 'controller-recorded-sha256-size; offline-audit-receipt-only'
WEIGHT_POLICY = 'inference-uid-read-only-model-root-through-source-boundary'


def reference(path):
    path = Path(path).absolute()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return dict(path=str(path), sha256=digest.hexdigest())


def save_json(path, value):
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
    return reference(path)


def validate_action(action):
    if (not isinstance(action, dict) or set(action) != {'workload_id', 'preset', 'reason'} or
            not isinstance(action['workload_id'], str) or action['workload_id'] not in WORKLOADS or
            not isinstance(action['preset'], str) or action['preset'] not in PRESETS or
            not isinstance(action['reason'], str) or not 1 <= len(action['reason'].strip()) <= 4000):
        raise ValueError('only a fixed public workload, graph preset and bounded reason are accepted')
    return action


def validate_reference(value):
    if (not isinstance(value, dict) or set(value) != {'path', 'sha256'} or
            not isinstance(value['path'], str) or not Path(value['path']).is_absolute() or
            any(part in ('..', 'sealed', '.git', '.config') for part in Path(value['path']).parts) or
            not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise ValueError('explicit trusted absolute file and SHA reference required')


def validate_request(record):
    if (not isinstance(record, dict) or set(record) != {
            'schema', 'action', 'base_spec', 'bundle', 'source_archive', 'dev_sources'} or record['schema'] != SCHEMA):
        raise ValueError('unexpected collector request fields')
    validate_action(record['action'])
    for name in ('base_spec', 'source_archive'):
        validate_reference(record[name])
    if record['bundle'] is not None:
        validate_reference(record['bundle'])
    if not isinstance(record['dev_sources'], dict) or set(record['dev_sources']) != set(SUITES):
        raise ValueError('all five fixed public dev sources required')
    for value in record['dev_sources'].values():
        validate_reference(value)
    return record


def execution_sources(additional=()):
    names = set(SOURCES) | set(additional)
    pending = list(names)
    checked = set()
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        checked.add(name)
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('missing concrete collector execution dependency')
        if path.suffix != '.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=name)):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = name.split('/')[:-1]
                module = node.module or ''
                if node.level:
                    module = '.'.join(package[:len(package) - node.level + 1] + ([module] if module else []))
                modules = [module] + [module + '.' + alias.name for alias in node.names]
            candidates = set()
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


def concrete(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('artifact symlinks are forbidden')
    return path


def checked_file(value):
    validate_reference(value)
    path = concrete(value['path'])
    if not path.is_file() or reference(path) != value:
        raise ValueError('trusted artifact checksum changed')
    return path


def copy_bound(value, destination):
    path = checked_file(value)
    destination = Path(destination)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('rb') as source, destination.open('xb') as target:
        shutil.copyfileobj(source, target, 1024 * 1024)
    destination.chmod(0o600)
    if reference(destination)['sha256'] != value['sha256'] or reference(path) != value:
        raise ValueError('artifact changed during persistent copy')
    return reference(destination)


def source_identity(path):
    if Path(path).stat().st_size > SOURCE_LIMIT:
        raise ValueError('source archive exceeds fixed capacity')
    files = {}
    size = 0
    with tarfile.open(path, 'r:*') as archive:
        for member in archive:
            name = member.name
            relative = Path(name)
            if (not member.isfile() or relative.is_absolute() or '..' in relative.parts or
                    name != relative.as_posix() or name in files or member.size > SOURCE_LIMIT):
                raise ValueError('source archive must contain only unique bounded regular files')
            size += member.size
            if size > SOURCE_LIMIT:
                raise ValueError('source archive expands beyond its bound')
            with archive.extractfile(member) as stream:
                files[name] = hashlib.sha256(stream.read()).hexdigest()
    for name in execution_sources():
        if files.get(name) != reference(ROOT / name)['sha256']:
            raise ValueError('executed collector source/public workload differs from frozen archive')
    return files


def check_base(base, bundle):
    validate_spec(base)
    if base['stock_tree_sha'] != FROZEN_STOCK_SHA or base['value'] != 8 or base['stock_default'] != 8:
        raise ValueError('canonical stock with disabled option/default eight is required')
    check_inputs(base)
    if bundle is not None:
        provenance = bundle.get('base', bundle)
        if provenance != base or bundle.get('stock_tree_sha') != FROZEN_STOCK_SHA:
            raise ValueError('bundle stock provenance differs; candidate tree is never loaded')


def workload_request(action, base, dev_dir):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(base['target'], local_files_only=True)
    requests = load_requests(4, SUITES, tokenizer, dev_dir=dev_dir)
    selection = WORKLOADS[action['workload_id']]
    return [request for request in requests if request['suite'] == selection['suite']][selection['index']]


def checkpoint_names(index):
    mapping = index.get('weight_map') if isinstance(index, dict) else None
    if (not isinstance(mapping, dict) or not mapping or
            any(not isinstance(key, str) or not key for key in mapping) or
            any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*\.safetensors', name)
                or Path(name).name != name for name in mapping.values())):
        raise ValueError('checkpoint index requires a nonempty safe safetensors weight map')
    return sorted(set(mapping.values()))


def weight_stat(path):
    information = concrete(path).stat()
    return dict(device=information.st_dev, inode=information.st_ino, size=information.st_size,
                mtime_ns=information.st_mtime_ns, ctime_ns=information.st_ctime_ns)


def capture_model(directory, destination):
    directory, destination = concrete(directory), Path(destination)
    if not (directory / 'config.json').is_file():
        raise ValueError('model configuration is required')
    index = directory / 'model.safetensors.index.json'
    if index.is_file():
        names = checkpoint_names(json.loads(index.read_text()))
        layout = 'indexed-safetensors'
    elif (directory / 'model.safetensors').is_file():
        names, layout = ['model.safetensors'], 'single-safetensors'
    else:
        raise ValueError('no supported indexed or single-file safetensors checkpoint')
    metadata = {}
    for name in MODEL_METADATA:
        path = directory / name
        if path.is_file():
            original = reference(path)
            metadata[name] = dict(original=original, snapshot=copy_bound(original, destination / name))
    if index.is_file() and checkpoint_names(json.loads(Path(metadata[index.name]['snapshot']['path']).read_text())) != names:
        raise ValueError('checkpoint index changed during snapshot')
    weights = []
    for name in names:
        path = concrete(directory / name)
        if not path.is_file():
            raise ValueError('checkpoint index references a missing regular weight file')
        before = weight_stat(path)
        identity = reference(path)
        if before['size'] <= 0 or before != weight_stat(path):
            raise ValueError('weight file is empty or changed while hashing')
        weights.append(dict(**identity, size=before['size'], stat=before))
    checkpoint = dict(schema='model-checkpoint-identity-v1', model_path=str(directory), layout=layout,
        index=metadata[index.name]['snapshot'] if index.is_file() else None, weights=weights,
        hash_origin='trusted-controller-before-inference', source_policy=WEIGHT_POLICY, audit_policy=WEIGHT_AUDIT)
    return metadata, checkpoint


def check_model_sources(models, checkpoints):
    for entries in models.values():
        for value in entries.values():
            checked_file(value['original'])
    for checkpoint in checkpoints.values():
        for weight in checkpoint['weights']:
            if weight_stat(weight['path']) != weight['stat']:
                raise ValueError('model weight source identity changed during capture')


def audit_checkpoint(checkpoint, directory, metadata, read):
    if (not isinstance(checkpoint, dict) or set(checkpoint) != {
            'schema', 'model_path', 'layout', 'index', 'weights', 'hash_origin', 'source_policy', 'audit_policy'} or
            checkpoint['schema'] != 'model-checkpoint-identity-v1' or
            checkpoint['model_path'] != str(Path(directory).absolute()) or
            checkpoint['hash_origin'] != 'trusted-controller-before-inference' or
            checkpoint['source_policy'] != WEIGHT_POLICY or checkpoint['audit_policy'] != WEIGHT_AUDIT):
        raise ValueError('incomplete controller checkpoint identity receipt')
    if 'model.safetensors.index.json' in metadata:
        if (checkpoint['layout'] != 'indexed-safetensors' or
                checkpoint['index'] != metadata['model.safetensors.index.json']['snapshot']):
            raise ValueError('checkpoint layout differs from its snapshotted index')
        names = checkpoint_names(read(checkpoint['index']))
    else:
        if checkpoint['layout'] != 'single-safetensors' or checkpoint['index'] is not None:
            raise ValueError('single-file checkpoint identity must not invent an index')
        names = ['model.safetensors']
    if not isinstance(checkpoint['weights'], list) or len(checkpoint['weights']) != len(names):
        raise ValueError('complete checkpoint weight identity inventory required')
    for name, weight in zip(names, checkpoint['weights']):
        if not isinstance(weight, dict) or set(weight) != {'path', 'sha256', 'size', 'stat'}:
            raise ValueError('complete weight SHA/size/stat receipt required')
        validate_reference({key: weight[key] for key in ('path', 'sha256')})
        information = weight['stat']
        if (weight['path'] != str((Path(directory) / name).absolute()) or
                type(weight['size']) is not int or weight['size'] <= 0 or
                not isinstance(information, dict) or set(information) != {'device', 'inode', 'size', 'mtime_ns', 'ctime_ns'} or
                any(type(value) is not int or value < 0 for value in information.values()) or
                information['size'] != weight['size'] or information['inode'] <= 0):
            raise ValueError('weight receipt does not match the declared model layout and size')


def profile_body(schema, directory):
    fields = schema.get('components', {}).get('schemas', {}).get('ProfileReq', {}).get('properties', {})
    if not {'output_dir', 'num_steps', 'record_shapes', 'with_stack', 'detailed_annotations'} <= set(fields):
        raise ValueError('native API lacks bounded shape/stack/annotation profiling')
    body = dict(output_dir=str(directory), num_steps=PROFILE_STEPS,
                record_shapes=True, with_stack=True, detailed_annotations=True)
    if 'activities' in fields:
        body['activities'] = ['CPU', 'GPU']
    return body


def single_device_paths(gpu):
    import pynvml
    visible = os.environ.get('NVIDIA_VISIBLE_DEVICES', '').split(',')
    if visible != [gpu['uuid']]:
        raise ValueError('exactly the single allocated NVIDIA UUID must be visible')
    information = [path.read_text() for path in Path('/proc/driver/nvidia/gpus').glob('*/information')]
    minor = kernel_device_minor(information, gpu['uuid'])
    pynvml.nvmlInit()
    try:
        reported = pynvml.nvmlDeviceGetMinorNumber(pynvml.nvmlDeviceGetHandleByUUID(gpu['uuid']))
    finally:
        pynvml.nvmlShutdown()
    if type(reported) is not int or reported < 0:
        raise ValueError('invalid NVML device identity')
    devices = ['/dev/nvidia' + str(minor)]
    devices += [str(path) for path in Path('/dev').glob('nvidia*')
                if path.name in ('nvidiactl', 'nvidia-uvm', 'nvidia-uvm-tools')]
    forbidden = next((str(path) for path in Path('/dev').glob('nvidia[0-9]*') if str(path) not in devices), None)
    return devices, forbidden, dict(kernel_information=information, nvml_minor=reported, kernel_minor=minor)


def sandbox_payload(arm, gpu, port, scratch, allowed, canary, environment):
    devices, forbidden, layout = single_device_paths(gpu)
    cache, bootstrap = scratch / 'cache', scratch / 'trusted-bootstrap'
    cache.mkdir(mode=0o700)
    cache.chmod(0o700)
    work = cache / 'work'
    work.mkdir(mode=0o700)
    os.chown(work, 60010, 60010)
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
    for name in ('/bin/sh', '/bin/bash', '/usr/bin/env', '/usr/bin/uname', '/usr/bin/ld',
                 '/usr/bin/as', '/usr/bin/ninja', '/usr/bin/gcc', '/usr/bin/g++',
                 '/sbin/ldconfig.real', '/usr/sbin/ldconfig.real'):
        if Path(name).is_file():
            executables.append(str(Path(name).resolve()))
    for name in ('nvidia-smi', 'ldconfig', 'numactl'):
        executable = shutil.which(name)
        if executable is None and name == 'ldconfig':
            executable = next((name for name in ('/sbin/ldconfig', '/usr/sbin/ldconfig') if Path(name).is_file()), None)
        if executable is None and name == 'nvidia-smi':
            raise RuntimeError('fixed NVIDIA runtime helper missing')
        if executable:
            executables.append(str(Path(executable).resolve()))
    readonly = [str(runtime), arm['engine'], str(allowed), str(bootstrap), environment['SP_TARGET'], environment['SP_DRAFT']]
    for name in ('/usr/local/cuda', '/sys/devices', '/sys/class', '/sys/bus', '/proc',
                 '/gpfs/users/jixinpeng/specpilot_data/shared/cuda-compat/usr/local/cuda-13.0/compat'):
        if Path(name).exists():
            readonly.append(name)
    for name in environment.get('LD_LIBRARY_PATH', '').split(':'):
        if name and Path(name).is_dir():
            readonly.append(str(Path(name).resolve()))
    env = {key: environment[key] for key in ('PATH', 'CC', 'CXX', 'CUDA_HOME', 'LD_LIBRARY_PATH') if key in environment}
    env.update(HOME=str(cache), TMPDIR=str(cache), PYTHONPATH=str(bootstrap) + ':' + arm['engine'] + '/python:' + arm['engine'] + '/lab',
        PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', CUDA_VISIBLE_DEVICES=gpu['uuid'],
        HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
        SP_TREE_SHA=arm['tree_sha'], SGLANG_JIT_DEEPGEMM_PRECOMPILE='0', SGLANG_NUMA_BIND_V2='0',
        TRITON_CACHE_MANAGER='trusted_source_cache:SourceCacheManager', LANG='C.UTF-8')
    for key, suffix in [('SGLANG_CACHE_DIR', 'sglang'), ('SGLANG_JIT_CACHE_DIR', 'sglang/jit'),
                        ('TRITON_CACHE_DIR', 'triton'), ('FLASHINFER_WORKSPACE_BASE', 'flashinfer'),
                        ('TORCH_EXTENSIONS_DIR', 'torch_extensions')]:
        env[key] = str(cache / suffix)
    base = dict(target=environment['SP_TARGET'], draft=environment['SP_DRAFT'])
    return dict(uid=60010, scratch=str(cache), work=str(work), readonly=readonly, executables=sorted(set(executables)),
        devices=devices, device_layout=layout, forbidden_device=forbidden, protected_proc='/proc/' + str(os.getpid()) + '/environ',
        protected_pid=os.getpid(), executable_trees=[str(runtime)] + ([str(Path('/usr/local/cuda').resolve())]
            if Path('/usr/local/cuda').exists() else []), allowed_read=str(allowed), allowed_content=allowed.read_text(),
        canary=str(canary), command=serve_command(base, 8, sys.executable, port), environment=env, engine_tree_sha=arm['tree_sha'])


class ProfileSourceServer(SourceServer):
    def start(self):
        if os.geteuid() != 0:
            raise RuntimeError('profile source execution requires controller UID0')
        self.sandbox = Path(tempfile.mkdtemp(prefix='specpilot-profile-server-'))
        self.sandbox.chmod(0o711)
        allowed, canary = self.sandbox / 'allowed.txt', self.sandbox / 'canary.txt'
        allowed.write_text('authorized source probe\n')
        allowed.chmod(0o444)
        canary.write_text('protected probe\n')
        canary.chmod(0o600)
        engine = self.sandbox / 'engine'
        shutil.copytree(self.arm['engine'], engine, symlinks=True,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.git'))
        check_tree(engine, self.arm['tree_sha'])
        for path in engine.rglob('*'):
            if not path.is_symlink():
                path.chmod(0o555 if path.is_dir() else 0o444)
        engine.chmod(0o555)
        payload = sandbox_payload(dict(self.arm, engine=str(engine)), self.gpu, self.port, self.sandbox,
                                  allowed, canary, self.environment)
        self.work = Path(payload['work'])
        ready_read, ready_write = os.pipe()
        payload['ready_fd'] = ready_write
        save_json(self.output_dir / 'stock.sandbox.json', payload)
        self.log = (self.output_dir / 'stock.launcher.log').open('x')
        try:
            self.process = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'harness/source_boundary.py')],
                stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, cwd=ROOT, env=payload['environment'],
                close_fds=True, pass_fds=(ready_write,), start_new_session=True, text=True)
            os.close(ready_write)
            ready_write = None
            self.process.stdin.write(json.dumps(payload))
            self.process.stdin.close()
            ticks = Path(f'/proc/{self.process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
            save_json(self.output_dir / 'stock.process.json', dict(pid=self.process.pid, start_ticks=int(ticks),
                host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
            if not select.select([ready_read], [], [], 30)[0]:
                raise RuntimeError('profile source boundary READY timeout')
            with os.fdopen(ready_read) as stream:
                ready_read = None
                line = stream.readline(16384)
            try:
                receipt = json.loads(line)
            except (ValueError, TypeError) as error:
                raise RuntimeError('profile source boundary missing/invalid READY') from error
            if (receipt.get('event') != 'SOURCE_BOUNDARY_READY' or receipt.get('uid') != 60010 or
                    not receipt.get('denied') or not all(value is True for value in receipt['denied'].values()) or
                    receipt.get('landlock_applied') is not True or receipt.get('seccomp_applied') is not True):
                raise RuntimeError('profile source boundary READY rejected')
            save_json(self.output_dir / 'stock.boundary.json', dict(receipt, trusted_pipe=True))
        finally:
            if ready_read is not None:
                os.close(ready_read)
            if ready_write is not None:
                os.close(ready_write)

    def stop(self):
        Server.stop(self)
        if self.process is not None and not (self.output_dir / 'stock.stopped.json').exists():
            save_json(self.output_dir / 'stock.stopped.json', dict(stopped=self.process.poll() is not None,
                exit_code=self.process.poll()))

    def cleanup(self):
        if hasattr(self, 'sandbox'):
            for path in self.sandbox.rglob('*'):
                if path.is_dir() and not path.is_symlink():
                    path.chmod(0o700)
            shutil.rmtree(self.sandbox)


def artifact_files(directory):
    values = {}
    if not Path(directory).exists():
        return values
    for path in Path(directory).rglob('*'):
        if path.is_symlink():
            raise ValueError('artifact symlinks are forbidden')
        if path.is_file():
            if path.stat().st_size > FILE_LIMIT:
                raise ValueError('artifact exceeds the source boundary single-file limit')
            values[path.relative_to(directory).as_posix()] = path
    if sum(path.stat().st_size for path in values.values()) > TOTAL_LIMIT:
        raise ValueError('total profile artifact budget exceeded')
    return values


def trace_statistics(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rb') as stream:
        content = stream.read(FILE_LIMIT + 1)
    if len(content) > FILE_LIMIT:
        raise ValueError('trace expansion exceeds fixed file bound')
    document = json.loads(content)
    events = document.get('traceEvents') if isinstance(document, dict) else document
    if not isinstance(events, list):
        raise ValueError('native traceEvents list required')
    kernels = [event for event in events if isinstance(event, dict) and event.get('ph') == 'X' and event.get('cat') == 'kernel']
    if not kernels:
        raise ValueError('profile contains no actual CUDA kernel events')
    for event in kernels:
        if (any(type(event.get(key)) not in (int, float) or not math.isfinite(event[key]) for key in ('ts', 'dur')) or
                event['dur'] < 0 or not isinstance(event.get('name'), str) or not event['name']):
            raise ValueError('invalid native CUDA kernel timing')
    if math.fsum(event['dur'] for event in kernels) <= 0:
        raise ValueError('profile contains no positive CUDA kernel work')
    return dict(kernel_count=len(kernels), kernel_work_us=math.fsum(event['dur'] for event in kernels),
        event_count=len(events), shape_status='unknown', stage_attribution_validated=False)


def copy_traces(staging, destination):
    files = artifact_files(staging)
    if not files or len(files) > 64 or any(not name.endswith(('.json', '.json.gz')) for name in files):
        raise ValueError('bounded complete native trace files required')
    destination = Path(destination)
    destination.mkdir(mode=0o700)
    copied = []
    for index, (name, path) in enumerate(sorted(files.items())):
        statistics = trace_statistics(path)
        source = reference(path)
        suffix = '.json.gz' if name.endswith('.gz') else '.json'
        target = copy_bound(source, destination / f'trace-{index:02d}{suffix}')
        if trace_statistics(target['path']) != statistics:
            raise ValueError('persistent trace differs from native export')
        copied.append(dict(**target, native_name=name, statistics=statistics))
    return copied


def control_packet(packet):
    payload = base64.b64decode(packet['response_bytes_base64'], validate=True)
    if hashlib.sha256(payload).hexdigest() != packet['response_bytes_sha256']:
        raise ValueError('profile raw response checksum changed')
    text = payload.decode(errors='replace').lower()
    if '<html' in text or '<!doctype html' in text or 'html' in packet.get('content_type', '').lower():
        raise ValueError('HTML is not profile-control evidence')
    return text


def stop_profile(client, directory):
    path = Path(directory) / 'stock.launcher.log'
    offset = path.stat().st_size
    try:
        client.post('/stop_profile', {})
    except (RuntimeError, ValueError):
        pass
    source = client.last_evidence
    packet = json.loads(Path(source['path']).read_text())
    text = control_packet(packet)
    proof = None
    if packet['http_status'] == 500:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with path.open('rb') as stream:
                stream.seek(offset)
                content = stream.read(1024 * 1024)
            if b'RuntimeError: Profiling is not in progress. Call /start_profile first.' in content.splitlines():
                proof = dict(offset=offset, length=len(content), sha256=hashlib.sha256(content).hexdigest())
                break
            time.sleep(.05)
    inactive = packet['http_status'] in (400, 409) and any(phrase in text for phrase in ('not running', 'not started', 'has not been started'))
    if packet['http_status'] != 200 and not inactive and proof is None:
        raise ValueError('profile stop has no native inactive-state proof')
    return dict(source=source, inactive_log=proof)


class ArtifactWatch:
    def __init__(self, output, staging, server, *, expires=None):
        self.output, self.staging, self.server = output, staging, server
        self.expires = expires
        self.done, self.failed = threading.Event(), None
        self.thread = threading.Thread(target=self.watch, daemon=True)
    def watch(self):
        while not self.done.wait(.2):
            try:
                if self.expires is not None and time.monotonic() >= self.expires:
                    raise TimeoutError('profile capture deadline exhausted')
                files = list(artifact_files(self.output).values()) + list(artifact_files(self.staging).values())
                if sum(path.stat().st_size for path in files) > TOTAL_LIMIT:
                    raise ValueError('total staged/persistent profile budget exceeded')
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as error:
                self.failed = type(error).__name__
                if self.server.process is not None:
                    try:
                        os.killpg(self.server.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                return
    def __enter__(self):
        self.thread.start()
        return self
    def __exit__(self, *arguments):
        self.done.set()
        self.thread.join()
        if self.failed is not None:
            raise ValueError('profile artifact watcher rejected incomplete/over-budget evidence')


def run(request_json, output):
    if os.geteuid() != 0:
        raise RuntimeError('trusted profile collector requires controller UID0')
    started = time.time()
    expires = time.monotonic() + DEADLINE
    request_path = None if isinstance(request_json, dict) else concrete(request_json)
    record = validate_request(request_json if request_path is None else json.loads(request_path.read_text()))
    base = json.loads(checked_file(record['base_spec']).read_text())
    bundle = None if record['bundle'] is None else json.loads(checked_file(record['bundle']).read_text())
    check_base(base, bundle)
    checked_file(record['source_archive'])
    sources = source_identity(record['source_archive']['path'])
    output = concrete(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir(mode=0o700)
    if request_path is None:
        save_json(output / 'request.json', record)
    else:
        copy_bound(reference(request_path), output / 'request.json')
    copy_bound(record['base_spec'], inputs / 'base.json')
    copy_bound(record['source_archive'], inputs / 'source.tar')
    if bundle is not None:
        copy_bound(record['bundle'], inputs / 'bundle.json')
    for suite, value in record['dev_sources'].items():
        if value['sha256'] != sources[f'assets/upstream/dev/{suite}.jsonl']:
            raise ValueError('public workload reference differs from frozen source archive')
        copy_bound(value, inputs / 'dev' / f'{suite}.jsonl')
    models, checkpoints = {}, {}
    for role in ('target', 'draft'):
        models[role], checkpoints[role] = capture_model(base[role], inputs / role)
    request = workload_request(record['action'], base, inputs / 'dev')
    artifact_files(output)
    arm = dict(name='stock', block=8, tree_sha=FROZEN_STOCK_SHA, engine=base['stock_engine'], env={}, option_enabled=False)
    environment = clean_environment()
    environment.update(SP_TARGET=base['target'], SP_DRAFT=base['draft'], SP_ENGINE=base['stock_engine'], SP_TREE_SHA=FROZEN_STOCK_SHA)
    with ExitStack() as resources:
        gpus = wait_for_idle([0])
        if len(gpus) != 1 or gpus[0]['index'] != 0 or 'H100' not in gpus[0]['name']:
            raise ValueError('one allocated H100 required')
        gpu = gpus[0]
        resources.enter_context(gpu_lock(gpu))
        check_ports([PORT])
        server = ProfileSourceServer(arm, gpu, PORT, output, environment)
        try:
            server.start()
            server.wait_ready(1200)
            client = ProfileClient(f'http://127.0.0.1:{PORT}', output / 'native')
            identity = client.server_identity(FROZEN_STOCK_SHA)
            actual = server_arguments(json.loads(Path(identity['evidence']['path']).read_text())['response'])
            expected = expected_arguments(base, 8)
            if any(actual.get(key) != value for key, value in expected.items()):
                raise ValueError('profile engine is not the canonical graph/default stock deployment')
            identity['server_args'] = expected
            schema = client.request('/openapi.json')
            schema_source = client.last_evidence
            staging = server.work / 'profile-traces'
            staging.mkdir(mode=0o700)
            os.chown(staging, 60010, 60010)
            body = profile_body(schema, staging)
            with ArtifactWatch(output, staging, server, expires=expires):
                client.post('/generate', dict(input_ids=request['input_ids'], sampling_params=dict(
                    temperature=0, top_k=1, max_new_tokens=32, ignore_eos=False)))
                warmup = client.last_evidence
                client.post('/start_profile', body)
                start_control = client.last_evidence
                try:
                    client.post('/generate', dict(input_ids=request['input_ids'], sampling_params=dict(
                        temperature=0, top_k=1, max_new_tokens=2048, ignore_eos=False)))
                    generation = client.last_evidence
                finally:
                    stop_control = stop_profile(client, output)
            server.stop()
            traces = copy_traces(staging, output / 'traces')
        finally:
            if not (output / 'stock.stopped.json').exists():
                server.stop()
            server.cleanup()
        check_ports([PORT])
        cleanup = wait_for_idle([0])
    check_model_sources(models, checkpoints)
    finished = time.time()
    if finished - started > DEADLINE:
        raise TimeoutError('profile capture exceeded the registered deadline')
    save_json(output / 'cleanup.json', dict(gpus=cleanup, scratch_removed=not server.sandbox.exists()))
    manifest = dict(schema=SCHEMA, action=record['action'], preset=PRESETS[record['action']['preset']],
        started_unix=started, finished_unix=finished, gpu=gpu, arm=arm, models=models, checkpoints=checkpoints,
        source_files=sources, request=request, identity=identity, schema_source=schema_source,
        warmup=warmup, start_control=start_control, generation=generation, stop_control=stop_control, traces=traces,
        files={name: reference(path)['sha256'] for name, path in artifact_files(output).items()})
    save_json(output / 'manifest.json', manifest)
    result = audit(output)
    save_json(output / 'result.json', result)
    try:
        artifact_files(output)
    except (OSError, ValueError):
        (output / 'result.json').unlink()
        raise
    return result


def audit(output):
    output = concrete(output)
    manifest = json.loads((output / 'manifest.json').read_text())
    files = artifact_files(output)
    actual = {name: reference(path)['sha256'] for name, path in files.items() if name not in ('manifest.json', 'result.json')}
    if actual != manifest['files'] or manifest.get('schema') != SCHEMA:
        raise ValueError('profile inventory is incomplete, changed or has extra artifacts')
    def read(value):
        validate_reference(value)
        path = concrete(value['path'])
        if not path.is_relative_to(output) or reference(path) != value:
            raise ValueError('evidence escaped the persistent output or checksum changed')
        return json.loads(path.read_text())
    record = validate_request(json.loads((output / 'request.json').read_text()))
    base = json.loads((output / 'inputs/base.json').read_text())
    bundle = None if record['bundle'] is None else json.loads((output / 'inputs/bundle.json').read_text())
    for key, name in (('base_spec', 'base.json'), ('source_archive', 'source.tar'), ('bundle', 'bundle.json')):
        if record[key] is not None and reference(output / 'inputs' / name)['sha256'] != record[key]['sha256']:
            raise ValueError('persistent input differs from its trusted request reference')
    check_base(base, bundle)
    sources = source_identity(output / 'inputs/source.tar')
    if sources != manifest['source_files']:
        raise ValueError('source inventory differs from archive')
    for suite, source in record['dev_sources'].items():
        if (reference(output / 'inputs/dev' / f'{suite}.jsonl')['sha256'] != source['sha256'] or
                sources[f'assets/upstream/dev/{suite}.jsonl'] != source['sha256']):
            raise ValueError('fixed public dev input changed')
    request = workload_request(record['action'], dict(base, target=str(output / 'inputs/target')), output / 'inputs/dev')
    if request != manifest['request'] or manifest['action'] != record['action'] or manifest['preset'] != PRESETS[record['action']['preset']]:
        raise ValueError('workload/preset differs from the registered public selection')
    if set(manifest['models']) != {'target', 'draft'}:
        raise ValueError('both model metadata inventories required')
    if set(manifest.get('checkpoints', {})) != {'target', 'draft'}:
        raise ValueError('both controller checkpoint identity receipts required')
    for role, entries in manifest['models'].items():
        if 'config.json' not in entries or not set(entries) <= set(MODEL_METADATA):
            raise ValueError('missing required model metadata')
        for name, value in entries.items():
            snapshot = output / 'inputs' / role / name
            validate_reference(value['original'])
            if (reference(snapshot) != value['snapshot'] or value['snapshot']['sha256'] != value['original']['sha256'] or
                    value['original']['path'] != str((Path(base[role]) / name).absolute())):
                raise ValueError('model configuration/tokenizer snapshot identity drifted')
        audit_checkpoint(manifest['checkpoints'][role], base[role], entries, read)
    expected = expected_arguments(base, 8)
    identity = manifest['identity']
    identity_packet = read(identity['evidence'])
    actual_identity = server_arguments(identity_packet['response'])
    if (identity['tree_sha'] != FROZEN_STOCK_SHA or identity['server_args'] != expected or
            identity_packet['http_status'] != 200 or not identity_packet['url'].endswith('/get_server_info') or
            any(actual_identity.get(key) != value for key, value in expected.items()) or
            manifest['arm'] != dict(name='stock', block=8, tree_sha=FROZEN_STOCK_SHA, engine=base['stock_engine'], env={}, option_enabled=False)):
        raise ValueError('actual generator identity is not frozen canonical stock')
    boundary = json.loads((output / 'stock.boundary.json').read_text())
    if (boundary.get('event') != 'SOURCE_BOUNDARY_READY' or boundary.get('uid') != 60010 or
            any(boundary.get(key) is not True for key in ('trusted_pipe', 'landlock_applied', 'seccomp_applied')) or
            not boundary.get('denied') or not all(value is True for value in boundary['denied'].values())):
        raise ValueError('missing actual trusted source boundary receipt')
    payload = json.loads((output / 'stock.sandbox.json').read_text())
    if (payload['uid'] != 60010 or payload['engine_tree_sha'] != FROZEN_STOCK_SHA or
            payload['environment']['CUDA_VISIBLE_DEVICES'] != manifest['gpu']['uuid'] or
            payload['command'] != serve_command(base, 8, payload['command'][0], PORT) or
            manifest['gpu']['index'] != 0 or 'H100' not in manifest['gpu']['name']):
        raise ValueError('sandbox/allocated GPU identity changed')
    for role in ('target', 'draft'):
        model = Path(base[role])
        if (not any(Path(name) == model for name in payload['readonly']) or
                Path(payload['scratch']).is_relative_to(model) or model.is_relative_to(Path(payload['scratch']))):
            raise ValueError('checkpoint identity lacks the source-boundary read-only model grant')
    process = json.loads((output / 'stock.process.json').read_text())
    stopped = json.loads((output / 'stock.stopped.json').read_text())
    cleanup = json.loads((output / 'cleanup.json').read_text())
    if (any(type(process.get(key)) is not int or process[key] <= 0 for key in ('pid', 'start_ticks')) or
            not process.get('host_boot_id') or stopped.get('stopped') is not True or cleanup.get('scratch_removed') is not True):
        raise ValueError('server process/cleanup evidence incomplete')
    schema = read(manifest['schema_source'])['response']
    staging = Path(payload['work']) / 'profile-traces'
    if not staging.is_absolute() or staging.parent != Path(payload['scratch']) / 'work':
        raise ValueError('profile trace staging is not the sandbox cache/work directory')
    start = read(manifest['start_control'])
    control_packet(start)
    if (start['http_status'] != 200 or not start['url'].endswith('/start_profile') or
            start['request'] != profile_body(schema, staging)):
        raise ValueError('actual start_profile differs from the frozen bounded preset')
    stop = read(manifest['stop_control']['source'])
    text = control_packet(stop)
    inactive = stop['http_status'] in (400, 409) and any(phrase in text for phrase in ('not running', 'not started', 'has not been started'))
    proof = manifest['stop_control']['inactive_log']
    if proof is not None:
        with (output / 'stock.launcher.log').open('rb') as stream:
            stream.seek(proof['offset'])
            content = stream.read(proof['length'])
        if (stop['http_status'] != 500 or hashlib.sha256(content).hexdigest() != proof['sha256'] or
                b'RuntimeError: Profiling is not in progress. Call /start_profile first.' not in content.splitlines()):
            raise ValueError('native inactive profile log proof changed')
    if (not stop['url'].endswith('/stop_profile') or stop['request'] != {} or
            (stop['http_status'] != 200 and not inactive and proof is None)):
        raise ValueError('native profile stop is not independently proven')
    warmup, generation = read(manifest['warmup']), read(manifest['generation'])
    for packet, cap in ((warmup, 32), (generation, 2048)):
        response = packet.get('response', {})
        checked_tokens(response.get('output_ids'))
        if (packet['http_status'] != 200 or not packet['url'].endswith('/generate') or
                packet['request'] != dict(input_ids=request['input_ids'], sampling_params=dict(
                    temperature=0, top_k=1, max_new_tokens=cap, ignore_eos=False)) or
                len(response['output_ids']) > cap or response['meta_info']['completion_tokens'] != len(response['output_ids']) or
                response['meta_info'].get('finish_reason', {}).get('type') not in ('stop', 'length')):
            raise ValueError('actual profiled generation or warmup differs from its fixed request/cap')
    times = [manifest['started_unix'], warmup['started_unix'], warmup['finished_unix'], start['started_unix'],
        start['finished_unix'], generation['started_unix'], generation['finished_unix'], stop['started_unix'],
        stop['finished_unix'], manifest['finished_unix']]
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in times) or
            times != sorted(times) or times[-1] - times[0] > DEADLINE):
        raise ValueError('capture chronology/deadline is invalid')
    traces = []
    if not manifest['traces'] or len(manifest['traces']) > 64:
        raise ValueError('no bounded complete trace inventory')
    for trace in manifest['traces']:
        path = concrete(trace['path'])
        if not path.is_relative_to(output / 'traces') or reference(path)['sha256'] != trace['sha256']:
            raise ValueError('trace escaped or changed')
        statistics = trace_statistics(path)
        if statistics != trace['statistics']:
            raise ValueError('uploaded trace statistics differ from independent recomputation')
        traces.append(dict(path=str(path), sha256=trace['sha256']))
    config = reference(output / 'inputs/target/config.json')
    result = dict(schema=SCHEMA, status='completed', manifest=reference(output / 'manifest.json'),
        request_sha256=reference(output / 'request.json')['sha256'], source_archive_sha256=record['source_archive']['sha256'],
        workload_id=record['action']['workload_id'], preset=record['action']['preset'], gpu=manifest['gpu'],
        stock_tree_sha=FROZEN_STOCK_SHA, option_enabled=False, workload=None, shape_status='unknown',
        model_identity_verification=dict(metadata='sha256-recomputed-from-persistent-snapshots',
            weights=WEIGHT_AUDIT, source_readonly_scope=WEIGHT_POLICY, live_model_access_required=False),
        traces=traces, profile_inputs=[dict(protocol='stock-profile-only-inputs-v1', scope='authorized-stock',
            trace=trace, config=config, workload=None) for trace in traces],
        capture_completed=True, stage_attribution_validated=False, controller_accepted=False, promoted=False,
        ledger_eligible=False, profiled_timings_are_performance=False,
        limits=dict(profile_steps=PROFILE_STEPS, max_new_tokens=2048, artifact_bytes=TOTAL_LIMIT,
                    file_bytes=FILE_LIMIT, deadline_seconds=DEADLINE),
        scope='canonical-stock graph profile only; shapes/stacks/stages require independent validation; not throughput or correctness acceptance')
    if (output / 'result.json').exists() and json.loads((output / 'result.json').read_text()) != result:
        raise ValueError('stored capture result differs from independent audit')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'audit'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'run' and args.request is None:
        parser.error('--request required for run')
    value = run(args.request, args.output) if args.mode == 'run' else audit(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    main()
