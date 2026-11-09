"""Trusted remote runner for frozen, agent-authored GPU screening scripts."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from harness.gpu_autonomy import digest, verify_request
from harness.candidate import check_tree


def execute(work, program, output, canary, stock, models):
    output.mkdir()
    environment = dict(PATH=os.environ['PATH'], LD_LIBRARY_PATH=os.environ.get('LD_LIBRARY_PATH', ''),
        CUDA_VISIBLE_DEVICES='0', HOME=str(work), TMPDIR=str(work / 'cache'),
        CUDA_CACHE_PATH=str(work / 'cache'), XDG_CACHE_HOME=str(work / 'cache'),
        HF_HUB_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
        SP_TARGET=os.environ.get('SP_TARGET', ''), SP_DRAFT=os.environ.get('SP_DRAFT', ''))
    environment.update(TORCHINDUCTOR_CACHE_DIR=str(work / 'cache/torchinductor'),
        TRITON_CACHE_DIR=str(work / 'cache/triton'), TORCH_EXTENSIONS_DIR=str(work / 'cache/extensions'))
    payload = dict(work=str(work), program=program, canary=str(canary), stock=str(stock), models=models, cpu_probe=False)
    started = time.monotonic()
    timed_out = False
    with (output / 'stdout').open('xb') as stdout, (output / 'stderr').open('xb') as stderr:
        process = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'harness/gpu_script_worker.py')],
            stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, env=environment, close_fds=True, start_new_session=True)
        try:
            process.communicate(json.dumps(payload).encode(), timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
    proof = None
    for line in (output / 'stderr').read_text(errors='replace').splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('kernel_boundary_applied'):
            proof = value
            break
    result = dict(program=program, code_sha256=digest(work / program), exit_code=process.returncode,
        timed_out=timed_out, wall_seconds=time.monotonic() - started, proof=proof,
        outputs={name: dict(sha256=digest(output / name), bytes=(output / name).stat().st_size,
            text=(output / name).read_text(errors='replace')[:16000]) for name in ('stdout', 'stderr')})
    (output / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def run(request, output):
    manifest = verify_request(request)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    work = output / 'work'
    shutil.copytree(request / 'work', work)
    (work / 'cache').mkdir()
    (work / '.cache').mkdir()
    canary = output / 'protected-canary.txt'
    canary.write_text('nonsecret remote boundary fixture\n')
    canary_sha = digest(canary)
    stock = Path(os.environ['SP_ENGINE'])
    if (stock / 'TREE_SHA').read_text().strip() != 'e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff':
        raise ValueError('authorized stock identity changed')
    check_tree(stock, 'e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff')
    environment = dict(python=sys.version, sglang=importlib.metadata.version('sglang'),
        torch=importlib.metadata.version('torch'), stock_tree_sha=(stock / 'TREE_SHA').read_text().strip(),
        nvidia_smi=subprocess.check_output(['nvidia-smi', '--query-gpu=uuid,name,driver_version,memory.total', '--format=csv'], text=True))
    if environment['sglang'] != '0.5.20':
        raise ValueError('SGLang version differs')
    (output / 'environment.json').write_text(json.dumps(environment, indent=2, sort_keys=True) + '\n')
    models = [name for name in (os.environ.get('SP_TARGET'), os.environ.get('SP_DRAFT')) if name and Path(name).is_dir()]
    runs = []
    for label, program in (('experiment', manifest['script']), ('acceptance', manifest['acceptance'])):
        row = execute(work, program, output / label, canary, stock, models)
        runs.append(row)
        if row['exit_code'] != 0 or not row['proof'] or not row['proof']['gpu'] or not all(row['proof']['boundary_checks'].values()):
            break
    immutable = all(digest(work / name) == expected for name, expected in manifest['files'].items())
    passed = len(runs) == 2 and all(row['exit_code'] == 0 and row['proof'] and row['proof']['gpu'] and
        all(row['proof']['boundary_checks'].values()) for row in runs) and immutable and digest(canary) == canary_sha
    result = dict(schema='agent-gpu-feedback-v1', status='completed' if passed else 'failed',
        request_sha256=digest(request / 'request.json'), script_sha256=manifest['script_sha256'],
        process_started=True, gpu_test_passed=bool(runs and runs[0]['proof'] and runs[0]['proof']['gpu']),
        boundary_passed=bool(runs and runs[0]['proof'] and all(runs[0]['proof']['boundary_checks'].values())),
        immutable_inputs=immutable, canary_unchanged=digest(canary) == canary_sha, runs=runs,
        controller_accepted=False, scope='agent-designed GPU screening, not model end-to-end or paired performance acceptance')
    (output / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.request, args.output)
    finally:
        owner = args.request.stat()
        if args.output.is_dir():
            for path in [*args.output.rglob('*'), args.output]:
                os.chown(path, owner.st_uid, owner.st_gid, follow_symlinks=False)
    print(json.dumps(dict(status=result['status'], gpu_test_passed=result['gpu_test_passed'], boundary_passed=result['boundary_passed'])))
    sys.exit(0 if result['status'] == 'completed' else 1)
