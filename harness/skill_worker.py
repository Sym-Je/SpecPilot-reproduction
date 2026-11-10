"""Run reviewed offline scripts without live capture or nested process actions."""

import collections
import json
from pathlib import Path
import runpy
import sys


def audit(event, arguments):
    if event in ('socket.__new__', 'socket.connect', 'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork'):
        raise PermissionError('offline diagnostics deny network and nested processes')


def main():
    root, tool, *arguments = sys.argv[1:]
    sys.addaudithook(audit)
    scripts = dict(
        profiler='skills/llm-torch-profiler-analysis/scripts/analyze_llm_torch_profile.py',
        pipeline='skills/llm-pipeline-analysis/scripts/layer_timeline_analyzer.py',
        compute='skills/model-compute-simulation/scripts/model_compute_simulator.py',
        capacity='skills/llm-serving-capacity-planner/scripts/capacity_analyzer.py')
    if tool == 'extract':
        sys.path.insert(0, str(Path(root) / 'skills/llm-torch-profiler-analysis/scripts'))
        from profile_common import load_trace_json
        from triage_kernel_helpers import extract_trace_data
        trace = load_trace_json(Path(arguments[0]))
        kernels, _, _, _, pid, span = extract_trace_data(trace)
        activity = dict(count=len(kernels), work_us=sum(kernel.dur for kernel in kernels), span_us=span,
            scope='upstream GPU activity includes memcpy/memset; not kernel-only work')
        events = trace['traceEvents'] if isinstance(trace, dict) else trace
        keys = {(event.get('name'), float(event.get('ts', 0)), float(event.get('dur', 0)),
                 str(event.get('pid')), str(event.get('tid'))) for event in events
                if event.get('ph') == 'X' and event.get('cat') == 'kernel'}
        kernels = [kernel for kernel in kernels
                   if (kernel.name, kernel.ts, kernel.dur, kernel.pid, kernel.tid) in keys]
        intervals = sorted((kernel.ts, kernel.ts + kernel.dur) for kernel in kernels)
        busy, previous = 0.0, float('-inf')
        for start, end in intervals:
            busy += max(0.0, end - max(start, previous))
            previous = max(previous, end)
        stages = collections.defaultdict(float)
        for kernel in kernels:
            stages[kernel.stage] += kernel.dur
        span = max(kernel.ts + kernel.dur for kernel in kernels) - min(kernel.ts for kernel in kernels)
        print(json.dumps(dict(pid=pid, count=len(kernels), work_us=sum(kernel.dur for kernel in kernels),
            busy_us=busy, span_us=span, stage_work_us=dict(stages), upstream_activity=activity)))
        return
    if tool not in scripts:
        raise ValueError('unknown tool')
    script = Path(root) / scripts[tool]
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *arguments]
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()
