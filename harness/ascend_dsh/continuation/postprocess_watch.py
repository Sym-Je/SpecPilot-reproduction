"""Publish diagnostic workload facts; archive finished traces between NPU jobs."""
import csv
import fcntl
import json
import os
import time

import psutil

from archive_timelines import archive
from prepare_baseline import ROOT, OUT, write
from summarize_kernels import summarize


def workload_summary(directory):
    if not (directory / 'profile-responses.json').exists():
        return
    destination = directory / 'traces/workload_activity_summary.csv'
    if destination.exists():
        return
    workload = json.loads((directory / 'profile-workload.json').read_text())
    rows = [json.loads(x) for x in (directory / 'profile-activity.jsonl').read_text().splitlines()]
    responses = json.loads((directory / 'profile-responses.json').read_text())
    start_path = directory / 'profile-start-activity.json'
    start = json.loads(start_path.read_text()) if start_path.exists() else {}
    values = {
        'offered_client_concurrency': workload['concurrency'],
        'requests_completed': len(responses),
        'peak_server_running_entire_replay': max(x['running'] for x in rows),
        'peak_server_waiting_entire_replay': max(x['waiting'] for x in rows),
        'server_running_at_profile_trigger': start.get('running', 'not separately recorded'),
        'completed_requests_at_profile_trigger': start.get('completed', 'not separately recorded'),
        'input_stratum': workload['stratum'], 'phase_requested': workload['phase_requested'],
        'output_cap': workload['output_cap'],
        'scope': 'Offered concurrency is not active decode batch size. Peaks cover entire replay, not only capture window.'}
    with destination.open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['metric', 'value']); writer.writerows(values.items())


def main():
    status_path = OUT / 'postprocess-state.json'
    owner = json.loads((OUT / 'research/supervisor.json').read_text())
    while True:
        state = {'status': 'watching', 'pid': os.getpid(), 'updated_epoch': time.time(), 'processed': []}
        for path in (OUT / 'experiments').glob('*/state.json'):
            directory = path.parent
            if not (directory / 'profile-responses.json').exists():
                continue
            workload_summary(directory)
            for log in directory.glob('export-*.log'):
                if 'All profiling data parsed' not in log.read_text(errors='replace'):
                    continue
                rank = log.name[len('export-'):-4]
                source = directory / 'traces' / rank / 'ASCEND_PROFILER_OUTPUT/kernel_details.csv'
                if source.exists() and not source.with_name('kernel_type_summary.csv').exists():
                    summarize(source)
            experiment = json.loads(path.read_text())
            # Heavy compression runs only after final restoration, under the
            # same machine lock as timing, so it cannot perturb a benchmark.
            if experiment.get('completed_epoch') and experiment.get('baseline_restored'):
                remaining = list((directory / 'traces').rglob('trace_view.json'))
                if remaining:
                    with (ROOT / 'evaluation/npu-workload.lock').open('a+') as lock:
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            continue
                        archive(directory)
                state['processed'].append(directory.name)
        write(status_path, state)
        try:
            process = psutil.Process(owner['pid'])
            alive = process.create_time() == owner['birth'] and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            alive = False
        if not alive:
            state.update(status='driver_exited_needs_supervision', updated_epoch=time.time())
            write(status_path, state)
            return
        time.sleep(5)


if __name__ == '__main__':
    main()
