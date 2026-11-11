"""Trusted single-H100 profile submission under an existing stage budget."""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from exp.engine_resource import command as engine_command, execute as engine_execute
from exp.history_northjob import with_model_mount
from exp.phase4_run import execution_sources, reference
from harness.engine_research import Budget, save


LIMITS = dict(gpu_seconds=28800, wall_seconds=43200, concurrent_gpus=2)
PROTOCOL = 'bounded-stock-profile-resource-v1'
DEADLINE = 2700


def bounded_template(template, deadline):
    if type(deadline) is not int or not 600 <= deadline <= DEADLINE:
        raise ValueError('profile deadline outside the fixed bounded range')
    result = with_model_mount(template, 600)
    result['spec']['tasks'][0]['template']['spec']['activeDeadlineSeconds'] = deadline
    return result


def create():
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


def command(request, source, output, name, deadline):
    bootstrap = ROOT / 'exp/profile_remote.sh'
    cli = engine_command(request, source, output, name, deadline)
    cli[cli.index('exp.engine_northjob')] = 'exp.profile_resource'
    cli[cli.index('--gpu-per-node') + 1] = '1'
    cli[-1] = shlex.join(['env', 'SP_PROFILE_BOOTSTRAP_SHA=' + reference(bootstrap)['sha256'],
        'SP_PROFILE_SOURCE_SHA=' + reference(source)['sha256'],
        'SP_PROFILE_REQUEST_SHA=' + reference(request)['sha256'], 'bash', str(bootstrap),
        str(request), str(source), str(output), str(deadline)])
    return cli


def check_budget(budget, directory):
    if not isinstance(budget, Budget) or Path(directory).absolute().parent != budget.path.parent.absolute():
        raise ValueError('profile unit must share the existing stage budget directory')
    state = budget.read()
    if any(state[key] != value for key, value in LIMITS.items()):
        raise ValueError('profile stage limits differ from the new authorization')
    return state


def archive(directory):
    names = execution_sources(('exp/profile_resource.py', 'exp/profile_capture.py', 'exp/profile_remote.sh',
        'exp/profile_autonomy.py', 'exp/skill_rsi_continue.py', 'exp/source_remote.sh',
        'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'))
    output = Path(directory) / 'source.tar'
    with tarfile.open(output, 'x') as destination:
        for name in names:
            destination.add(ROOT / name, arcname=name, recursive=False)
    save(Path(directory) / 'source-identity.json', dict(archive=reference(output),
        files={name: reference(ROOT / name)['sha256'] for name in names}))
    return output


def prepare(directory, capture, budget, *, role_binding=None):
    from exp.profile_capture import validate_request
    directory = Path(directory).absolute()
    check_budget(budget, directory)
    capture = dict(capture, source_archive=dict(path=str(directory / 'source.tar'), sha256='0' * 64))
    validate_request(capture)
    directory.mkdir(mode=0o700)
    source = archive(directory)
    capture['source_archive'] = reference(source)
    validate_request(capture)
    save(directory / 'request.json', dict(protocol=PROTOCOL, mode='stock-profile',
        action=capture['action'], capture=capture, budget_path=str(budget.path.absolute()),
        role_binding=role_binding, deadline=DEADLINE, gpus=1))
    cli = command(directory / 'request.json', source, directory / 'remote', directory.name, DEADLINE)
    save(directory / 'plan.json', dict(command=cli, shell_command=shlex.join(cli),
        request=reference(directory / 'request.json'), source=reference(source), total_gpus=1,
        budget_path=str(budget.path.absolute()), deadline=DEADLINE, submission_performed=False))
    return directory


def feedback(output, record):
    from exp.profile_capture import audit
    output = Path(output)
    binding = json.loads((output.parent / 'resource-binding.json').read_text())
    if (binding['request'] != reference(output.parent / 'request.json') or
            binding['source'] != reference(output.parent / 'source.tar') or
            binding['capture'] != record['capture'] or
            json.loads((output / 'request.json').read_text()) != record['capture']):
        raise ValueError('profile result differs from its frozen resource request/source')
    try:
        result = audit(output)
    except ModuleNotFoundError as error:
        if error.name != 'transformers':
            raise
        result = cpu_replay(output)
    if binding['result_sha256'] != reference(output / 'result.json')['sha256']:
        raise ValueError('profile result changed after capture')
    return result


def cpu_replay(output):
    output = Path(output).absolute()
    runtime = output.parent / (output.name + '.runtime-source')
    identity = json.loads((output.parent / 'source-identity.json').read_text())
    source = output.parent / 'source.tar'
    expected = {}
    with tarfile.open(source) as archive_file:
        for member in archive_file:
            if not member.isfile() or member.name in expected:
                raise ValueError('frozen CPU audit archive must contain unique regular files')
            expected[member.name] = hashlib.sha256(archive_file.extractfile(member).read()).hexdigest()
    if identity['archive'] != reference(source) or identity['files'] != expected:
        raise ValueError('CPU audit file inventory differs from its bound source archive')
    for name, checksum in identity['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('frozen CPU audit source path escaped its runtime')
        path = runtime / name
        if any(parent.is_symlink() for parent in (path, *path.parents)) or reference(path)['sha256'] != checksum:
            raise ValueError('frozen CPU audit runtime source changed')
    for path in runtime.rglob('*'):
        if path.is_symlink() or (path.suffix in ('.py', '.pyc', '.pth', '.so') and
                                path.relative_to(runtime).as_posix() not in identity['files']):
            raise ValueError('unreviewed frozen audit executable dependency')
    python = Path('/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python')
    worker = ROOT / 'harness/profile_cpu_audit.py'
    worker_identity = reference(worker)
    if not python.is_file():
        raise RuntimeError('installed CPU tokenizer environment is unavailable; do not skip retokenization')
    with tempfile.TemporaryDirectory(prefix='specpilot-profile-audit-') as temporary:
        environment = dict(PATH=str(python.parent) + ':/usr/bin:/bin', HOME=temporary, TMPDIR=temporary,
            CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
            TOKENIZERS_PARALLELISM='false', PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.run([str(python), '-I', '-B', str(worker), str(runtime), str(output)],
            capture_output=True, text=True, env=environment, timeout=300, check=True)
    answer = json.loads(process.stdout)
    if reference(worker) != worker_identity:
        raise ValueError('CPU audit worker changed while executing')
    return answer['result']


def execute(directory, budget, *, resume_only=False):
    directory = Path(directory).absolute()
    check_budget(budget, directory)
    record = json.loads((directory / 'request.json').read_text())
    plan = json.loads((directory / 'plan.json').read_text())
    source = directory / 'source.tar'
    if (record['protocol'] != PROTOCOL or record['mode'] != 'stock-profile' or record['gpus'] != 1 or
            record['deadline'] != DEADLINE or record['budget_path'] != str(budget.path.absolute()) or
            plan['request'] != reference(directory / 'request.json') or plan['source'] != reference(source)):
        raise ValueError('profile resource plan drifted before execution')
    return engine_execute(directory, source, budget, resume_only=resume_only, command_factory=command,
                          feedback_loader=feedback, deadline=DEADLINE, gpus=1)


def remote(request, directory):
    from exp.profile_capture import run
    request, directory = Path(request).absolute(), Path(directory).absolute()
    record = json.loads(request.read_text())
    if record['protocol'] != PROTOCOL or record['mode'] != 'stock-profile' or record['gpus'] != 1:
        raise ValueError('controller-owned profile envelope required')
    try:
        run(record['capture'], directory)
    except BaseException:
        if directory.exists():
            publish_evidence(directory)
        raise
    source = request.parent / 'source.tar'
    if reference(source)['sha256'] != os.environ['SP_PROFILE_SOURCE_SHA']:
        raise ValueError('profile runtime archive identity differs')
    save(directory.parent / 'resource-binding.json', dict(request=reference(request), source=reference(source),
        capture=record['capture'], result_sha256=reference(directory / 'result.json')['sha256']))
    (directory.parent / 'resource-binding.json').chmod(0o644)
    publish_evidence(directory)


def publish_evidence(directory):
    directory = Path(directory).absolute()
    if (any(part in ('..', 'sealed', 'private', '.git', '.config') for part in directory.parts) or
            any(parent.is_symlink() for parent in (directory, *directory.parents))):
        raise ValueError('only the registered public stock profile may be published')
    paths = [directory, *directory.rglob('*')]
    if any(path.is_symlink() or not (path.is_dir() or path.is_file()) for path in paths):
        raise ValueError('public profile publication rejects symlinks and special files')
    for path in paths:
        path.chmod(0o755 if path.is_dir() else 0o644)


def main():
    if sys.argv[1:2] == ['create']:
        return create()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['remote'])
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    remote(args.request, args.directory)


if __name__ == '__main__':
    main()
