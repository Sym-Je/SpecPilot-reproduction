"""Opt-in affinity control for owned null-benchmark servers, not CPU reservation."""

import json
import os
from pathlib import Path

from harness.telemetry import Telemetry


def is_scheduler(process):
    return process['comm'].startswith('sglang::schedul')


def cpu_topology(cpus):
    root = Path('/sys/devices/system/cpu')
    return {cpu: tuple(int((root / f'cpu{cpu}/topology' / field).read_text())
                       for field in ('physical_package_id', 'core_id')) for cpu in cpus}


def owned_processes(servers):
    if any(server.process.poll() is not None for server in servers):
        raise RuntimeError('owned server root exited before affinity operation')
    records = Telemetry(servers, [], '/unused').read_processes()
    if any(server.process.pid not in {process['pid'] for process in records[server.arm['name']]}
           for server in servers):
        raise RuntimeError('missing owned server root identity')
    return records


def scheduler_for(processes):
    schedulers = [process for process in processes if is_scheduler(process)]
    if len(schedulers) != 1:
        raise ValueError('expected exactly one owned TP1 scheduler')
    return schedulers[0]


def plan_bindings(servers, processes):
    schedulers = {server.gpu['uuid']: scheduler_for(processes[server.arm['name']]) for server in servers}
    topology = cpu_topology({cpu for scheduler in schedulers.values() for cpu in scheduler['allowed_cpus']})
    used = set()
    result = {}
    for gpu, scheduler in sorted(schedulers.items()):
        physical = {}
        for cpu in sorted(scheduler['allowed_cpus']):
            physical.setdefault(topology[cpu], cpu)
        candidates = [(core, cpu) for core, cpu in sorted(physical.items())[2:] if core not in used]
        if len(candidates) < 9:
            raise ValueError('insufficient disjoint physical CPU cores for declared policy')
        selected = candidates[:9]
        used.update(core for core, cpu in selected)
        result[gpu] = dict(main_cpu=selected[0][1], worker_cpus=[cpu for core, cpu in selected[1:]],
                           physical_cores=[list(core) for core, cpu in selected])
    return result


def apply_bindings(servers, plan, expected=None):
    processes = owned_processes(servers)
    result = {}
    for server in servers:
        arm = server.arm['name']
        scheduler = scheduler_for(processes[arm])
        identity = dict(scheduler_pid=scheduler['pid'], start_ticks=scheduler['start_ticks'])
        if expected is not None and any(expected[arm][key] != value for key, value in identity.items()):
            raise RuntimeError('scheduler identity changed before reapplying fixed affinity')
        policy = plan[server.gpu['uuid']]
        changes = []
        for process in processes[arm]:
            directory = Path('/proc') / str(process['pid'])
            for task in (directory / 'task').iterdir():
                current = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(current[19]) != process['start_ticks'] or directory.stat().st_uid != os.geteuid():
                    raise RuntimeError('owned process identity or owner changed')
                thread = int(task.name)
                cpus = [policy['main_cpu']] if thread == scheduler['pid'] else policy['worker_cpus']
                os.sched_setaffinity(thread, cpus)
                if os.sched_getaffinity(thread) != set(cpus):
                    raise RuntimeError('CPU affinity was not applied')
                changes.append(dict(pid=process['pid'], tid=thread, allowed_cpus=cpus))
        result[arm] = dict(policy, **identity, gpu_uuid=server.gpu['uuid'], changed_threads=changes)
    return result


def check_thread_evidence(processes, policy):
    pool = {policy['main_cpu'], *policy['worker_cpus']}
    found = False
    for process in processes:
        threads = process.get('thread_affinities', [])
        if not threads:
            raise ValueError('missing server thread affinity evidence')
        for thread in threads:
            mask = set(thread['allowed_cpus'])
            if not mask or not mask <= pool:
                raise ValueError('server thread escaped GPU-bound CPU pool')
            if thread['tid'] == policy['scheduler_pid']:
                if mask != {policy['main_cpu']}:
                    raise ValueError('scheduler main thread escaped fixed CPU')
                if 'start_ticks' in policy and process['start_ticks'] != policy['start_ticks']:
                    raise ValueError('scheduler PID was reused')
                found = True
    if not found:
        raise ValueError('missing pinned scheduler main thread')


def validate_cpu_bound(directory, reference_requests=None):
    from controller.stability_validation import validate_stable
    from harness.baseline_validation import read_rows

    directory = Path(directory)
    result = validate_stable(directory, reference_requests)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('cpu_pinning') is not True:
        raise ValueError('CPU-bound protocol was not declared')
    plan = json.loads((directory / 'cpu-plan.json').read_text())
    if set(plan) != {gpu['uuid'] for gpu in manifest['gpus']}:
        raise ValueError('CPU plan GPU identity mismatch')
    physical = [tuple(core) for policy in plan.values() for core in policy['physical_cores']]
    if len(physical) != 18 or len(set(physical)) != 18:
        raise ValueError('CPU plan does not use 18 distinct physical cores')
    for number in range(1, 5):
        root = directory / f'round-{number:02d}'
        deployment = json.loads((root / 'deployment.json').read_text())
        ready = json.loads((root / 'cpu-binding-ready.json').read_text())
        measured = json.loads((root / 'cpu-binding-measured.json').read_text())
        for assignment in deployment['assignments']:
            arm, gpu = assignment['arm']['name'], assignment['gpu']['uuid']
            for binding in (ready[arm], measured[arm]):
                if binding['gpu_uuid'] != gpu or any(binding[key] != value for key, value in plan[gpu].items()):
                    raise ValueError('CPU mapping did not follow physical GPU')
            if any(ready[arm][key] != measured[arm][key] for key in ('scheduler_pid', 'start_ticks')):
                raise ValueError('scheduler changed between fixed binding phases')
        pairs = read_rows(root / 'pairs.jsonl')
        during = [sample for sample in read_rows(root / 'telemetry.jsonl')
                  if pairs[0]['started_unix'] <= sample['time_unix'] <= pairs[-1]['finished_unix']]
        for sample in during:
            for arm, policy in measured.items():
                check_thread_evidence(sample['arms'][arm], policy)
    return dict(result, cpu_binding_protocol_passed=True,
                cpu_binding_scope='owned server CPU affinity only; not exclusive CPU allocation')
