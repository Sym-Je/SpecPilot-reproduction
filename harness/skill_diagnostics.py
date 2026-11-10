"""Maintainer-only offline diagnostics; not a research sandbox or controller gate."""

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


LOCK = Path(__file__).with_name('skill_tools.json')
ENTRYPOINTS = {
    'profiler': 'skills/llm-torch-profiler-analysis/scripts/analyze_llm_torch_profile.py',
    'pipeline': 'skills/llm-pipeline-analysis/scripts/layer_timeline_analyzer.py',
    'compute': 'skills/model-compute-simulation/scripts/model_compute_simulator.py',
    'capacity': 'skills/llm-serving-capacity-planner/scripts/capacity_analyzer.py',
}


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def checked_file(record):
    if set(record) != {'path', 'sha256'}:
        raise ValueError('explicit path and SHA required')
    path = Path(record['path'])
    if not path.is_absolute() or any(part in ('..', 'sealed', '.git', '.config') for part in path.parts):
        raise ValueError('authorized local evidence path required')
    if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file():
        raise ValueError('regular non-symlink evidence required')
    if sha256(path) != record['sha256']:
        raise ValueError('evidence SHA differs')
    return path


def checked_tools(record):
    lock = json.loads(LOCK.read_text())
    if set(record) != {'root', 'revision'} or record['revision'] != lock['revision']:
        raise ValueError('pinned upstream revision required')
    root = Path(record['root'])
    if not root.is_absolute():
        raise ValueError('absolute snapshot root required')
    for name, expected in lock['files'].items():
        checked_file(dict(path=str(root / name), sha256=expected))
    for path in root.rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.pyc', '.pth', '.so'):
            if path.relative_to(root).as_posix() not in lock['files']:
                raise ValueError('unreviewed executable dependency in snapshot')
    return root


def checked_manifest(record):
    if set(record) != {'protocol', 'scope', 'trace', 'config', 'workload'}:
        raise ValueError('unknown diagnostic input field')
    if record['protocol'] != 'stock-diagnostic-inputs-v1' or record['scope'] != 'authorized-stock':
        raise ValueError('only explicitly authorized stock evidence is supported')
    trace, config = checked_file(record['trace']), checked_file(record['config'])
    shape = record['workload']
    if set(shape) != {'phase', 'batch_size', 'verify_rows', 'prefix_kv', 'shape_evidence'}:
        raise ValueError('explicit shape and provenance required')
    if shape['phase'] != 'target-verify' or shape['batch_size'] != 1:
        raise ValueError('only single-request target verification is validated')
    for field in ('batch_size', 'verify_rows', 'prefix_kv'):
        if type(shape[field]) is not int or not 1 <= shape[field] <= 1048576:
            raise ValueError('positive integer shape required')
    if not isinstance(shape['shape_evidence'], str) or not shape['shape_evidence'].strip():
        raise ValueError('shape source must be explained')
    return trace, config, shape


def interval_union(intervals):
    total = 0.0
    previous_end = -math.inf
    for start, end in sorted(intervals):
        total += max(0.0, end - max(start, previous_end))
        previous_end = max(previous_end, end)
    return total


def kernel_statistics(events):
    kernels = [event for event in events if event.get('ph') == 'X' and event.get('cat') == 'kernel']
    if not kernels:
        raise ValueError('trace has no CUDA kernel events')
    groups = defaultdict(list)
    for event in kernels:
        start, duration = event.get('ts'), event.get('dur')
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, duration)) or duration < 0:
            raise ValueError('invalid kernel timestamps')
        groups[str(event.get('pid'))].append(event)
    summaries = {}
    for pid, selected in sorted(groups.items()):
        durations = defaultdict(float)
        for event in selected:
            durations[event['name']] += event['dur']
        summaries[pid] = dict(count=len(selected), work_us=math.fsum(event['dur'] for event in selected),
            busy_us=interval_union((event['ts'], event['ts'] + event['dur']) for event in selected),
            span_us=max(event['ts'] + event['dur'] for event in selected) - min(event['ts'] for event in selected),
            top_kernels=sorted(durations.items(), key=lambda item: (-item[1], item[0]))[:12])
    return summaries


def crosscheck(reference, observed):
    if str(observed.get('pid')) not in reference:
        raise ValueError('skill selected an unknown GPU process')
    expected = reference[str(observed['pid'])]
    if observed.get('count') != expected['count']:
        raise ValueError('kernel count differs')
    for field in ('work_us', 'busy_us', 'span_us'):
        if not math.isclose(observed[field], expected[field], rel_tol=1e-9, abs_tol=1e-3):
            raise ValueError('kernel timing differs: ' + field)
    return dict(passed=True, pid=observed['pid'], count=observed['count'],
        scope='kernel extraction and timing only; source attribution is not certified')


def read_trace(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        data = json.load(stream)
    events = data.get('traceEvents') if isinstance(data, dict) else data
    if not isinstance(events, list):
        raise ValueError('Chrome trace event list required')
    return events


def run_tool(root, tool, arguments, output, *, timeout=300):
    if tool not in (*ENTRYPOINTS, 'extract'):
        raise ValueError('unknown offline tool')
    worker = Path(__file__).with_name('skill_worker.py')
    command = [sys.executable, '-I', '-B', str(worker), str(root), tool, *map(str, arguments)]
    environment = dict(PATH='/usr/bin:/bin', HOME=str(output), TMPDIR=str(output),
        CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1')
    timed_out = False
    with (output / (tool + '.stdout.txt')).open('w') as stdout, (output / (tool + '.stderr.txt')).open('w') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=output,
            env=environment, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return dict(exit_code=process.returncode, timed_out=timed_out,
        output_sha256={name: sha256(output / (tool + '.' + name + '.txt')) for name in ('stdout', 'stderr')})


def analyze(manifest_path, tools_path, output):
    manifest = json.loads(Path(manifest_path).read_text())
    trace, config, shape = checked_manifest(manifest)
    tools = json.loads(Path(tools_path).read_text())
    root = checked_tools(tools)
    output = Path(output).absolute()
    if any(part in ('..', 'controller', 'eval', 'ledger', 'memory', '.git', '.config') for part in output.parts):
        raise ValueError('output must not target protected directories')
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError('non-symlink output directory required')
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir()
    trace_copy = inputs / ('stock.trace.json.gz' if trace.suffix == '.gz' else 'stock.trace.json')
    config_copy = inputs / 'config.json'
    for source, target, identity in ((trace, trace_copy, manifest['trace']), (config, config_copy, manifest['config'])):
        shutil.copyfile(source, target)
        if sha256(target) != identity['sha256']:
            raise ValueError('copied input SHA differs')
    events = read_trace(trace_copy)
    reference = kernel_statistics(events)
    workload_labels = Counter(event.get('name', '') for event in events
        if event.get('cat') == 'user_annotation' and event.get('name', '').startswith('step['))
    del events
    result = dict(protocol='offline-skill-diagnostics-v1', upstream_revision=tools['revision'],
        input_identity=manifest, tool_lock_sha256=sha256(LOCK), kernel_statistics=reference,
        adapter_sources_sha256={name: sha256(Path(__file__).resolve().parents[1] / name)
            for name in ('harness/skill_diagnostics.py', 'harness/skill_worker.py', 'exp/skill_diagnostics.py')},
        workload_labels=dict(sorted(workload_labels.items())), tools={}, gpu_submissions=0,
        formal_ceiling=None, controller_accepted=False, ledger_eligible=False,
        scope='maintainer offline stock diagnostic; not autonomous research, speedup or lossless proof')
    result['tools']['extract'] = run_tool(root, 'extract', [trace_copy], output)
    if result['tools']['extract']['exit_code'] == 0:
        extracted = json.loads((output / 'extract.stdout.txt').read_text())
        result['crosscheck'] = crosscheck(reference, extracted)
        result['unvalidated_stage_kernel_work_us'] = extracted['stage_work_us']
        result['upstream_activity'] = extracted['upstream_activity']
        result['stage_attribution_validated'] = False
    else:
        result['crosscheck'] = dict(passed=False)
    result['tools']['profiler'] = run_tool(root, 'profiler', ['--framework', 'sglang', '--input', trace_copy,
        '--kernel-table-limit', '12', '--overlap-table-limit', '12'], output)
    result['tools']['pipeline'] = dict(status='not_run_unverified_layer_boundaries',
        reason='No independently verified per-layer anchor/offset; do not infer layers from counts alone.')
    result['tools']['compute'] = run_tool(root, 'compute', ['--config', config_copy,
        '--batch-size', '1', '--seq-len', str(shape['verify_rows']), '--context-len', str(shape['prefix_kv']),
        '--all-token-logits', '--tp', '1', '--dp', '1', '--ep', '1', '--gpu', 'h100', '--dtype', 'bf16',
        '--format', 'json'], output)
    result['limitations'] = [
        'Kernel work sums double-count overlap; busy unions and spans are not request latency.',
        'Skill source locations and fusion/overlap recommendations require independent path validation.',
        'Upstream kernel tables include GPU memcpy/memset; the crosscheck explicitly filters cat=kernel.',
        'Upstream stage labels are unvalidated for DFlash2; all/extend are not a draft/verify decomposition.',
        'Compute output is a target-only architectural estimate, not measured FLOPs, MFU, bytes or ceiling.',
        'A single declared shape does not model the full request, drafting, rollback or all KV lengths.',
        'Pipeline layer attribution is unavailable; no unverified anchors are supplied.',
        'Only a maintainer entrypoint is verified; no new research-role or kernel-enforced boundary is claimed.',
    ]
    checked_manifest(manifest)
    checked_tools(tools)
    result['engineering_passed'] = result['crosscheck']['passed'] and all(
        result['tools'][name]['exit_code'] == 0 for name in ('profiler', 'compute'))
    write_json(output / 'result.json', result)
    return result
