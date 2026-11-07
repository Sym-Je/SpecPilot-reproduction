"""Read-only sampling for owned server processes and the allocated GPU UUIDs."""

import csv
import json
import os
from pathlib import Path
import subprocess
import threading
import time


class Telemetry:
    def __init__(self, servers, gpus, path, interval=2.0, inspect_threads=False):
        self.servers, self.gpus, self.path = servers, gpus, Path(path)
        self.interval = interval
        self.stopping = threading.Event()
        self.thread = None
        self.output = None
        self.inspect_threads = inspect_threads

    def read_gpus(self):
        fields = ['index', 'uuid', 'clocks.sm', 'clocks.mem', 'temperature.gpu',
                  'power.draw', 'utilization.gpu', 'memory.used', 'pstate', 'clocks_throttle_reasons.active']
        text = subprocess.check_output(['nvidia-smi', '--id=' + ','.join(gpu['uuid'] for gpu in self.gpus),
                '--query-gpu=' + ','.join(fields), '--format=csv,noheader,nounits'],
                text=True, timeout=5)
        results = []
        for values in csv.reader(text.splitlines(), skipinitialspace=True):
            if len(values) != len(fields):
                raise ValueError('incomplete GPU telemetry')
            results.append(dict(index=int(values[0]), uuid=values[1].strip(),
                                clocks_sm_mhz=float(values[2]), clocks_mem_mhz=float(values[3]),
                                temperature_c=float(values[4]), power_w=float(values[5]),
                                utilization_pct=float(values[6]), memory_used_mib=float(values[7]),
                                pstate=values[8].strip(), throttle_reasons=values[9].strip()))
        return results

    def read_processes(self):
        processes = {}
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / 'stat').read_text()
                values = raw.rsplit(')', 1)[1].split()
                processes[int(entry.name)] = dict(pid=int(entry.name), ppid=int(values[1]),
                    comm=raw.split('(', 1)[1].rsplit(')', 1)[0], state=values[0],
                    cpu_ticks=int(values[11]) + int(values[12]), threads=int(values[17]),
                    start_ticks=int(values[19]), processor=int(values[36]))
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        arms = {}
        for server in self.servers:
            selected = {server.process.pid}
            while True:
                expanded = selected | {pid for pid, item in processes.items() if item['ppid'] in selected}
                if expanded == selected:
                    break
                selected = expanded
            records = []
            for pid in sorted(selected & processes.keys()):
                try:
                    record = dict(processes[pid], allowed_cpus=sorted(os.sched_getaffinity(pid)))
                    if self.inspect_threads:
                        record['thread_affinities'] = []
                        for task in (Path('/proc') / str(pid) / 'task').iterdir():
                            try:
                                record['thread_affinities'].append(dict(tid=int(task.name),
                                    allowed_cpus=sorted(os.sched_getaffinity(int(task.name)))))
                            except ProcessLookupError:
                                continue
                    records.append(record)
                except (ProcessLookupError, PermissionError):
                    continue
            arms[server.arm['name']] = records
        return arms

    def sample(self):
        started = time.perf_counter()
        result = {'time_unix': time.time(), 'monotonic_ns': time.perf_counter_ns()}
        try:
            result.update(gpus=self.read_gpus(), arms=self.read_processes(),
                          parent_allowed_cpus=sorted(os.sched_getaffinity(0)), loadavg=list(os.getloadavg()))
            result['cgroup'] = {}
            for name in ('cpu.stat', 'cpu.max', 'cpuset.cpus.effective'):
                path = Path('/sys/fs/cgroup') / name
                result['cgroup'][name] = path.read_text().strip() if path.exists() else None
        except Exception as error:
            result['error'] = repr(error)
        result['sample_elapsed_s'] = time.perf_counter() - started
        return result

    def run(self):
        while not self.stopping.is_set():
            self.output.write(json.dumps(self.sample(), allow_nan=False) + '\n')
            self.output.flush()
            self.stopping.wait(self.interval)

    def __enter__(self):
        self.output = self.path.open('x')
        self.thread = threading.Thread(target=self.run, name='specpilot-telemetry', daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *errors):
        self.stopping.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise RuntimeError('telemetry sampler failed to stop')
        self.output.close()
