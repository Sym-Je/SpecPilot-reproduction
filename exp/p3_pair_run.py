"""Local, dev-only two-GPU orchestration; default is a non-mutating plan.

Servers and physical GPU swaps live here. Requests use HttpPairBench without
logical swaps or per-request warmups. Log-space confidence bounds are computed
by the existing controller.stats.bootstrap_ci; no promotion or ledger writes.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTING = 'h100_c1_qwen38-27b_dflash2'
SUITES = ['gsm8k', 'math500', 'humaneval', 'mbpp', 'mt-bench']
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from controller.http_transport import Arm, HttpPairBench, sha_ids
from controller.stats import bootstrap_ci
from harness.telemetry import Telemetry


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arms', nargs=2, choices=['ar', 'stock', 'final'])
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--gpus', type=int, nargs=2, default=[0, 1])
    parser.add_argument('--ports', type=int, nargs=2, default=[30100, 30110])
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--per-suite', type=int, default=int(os.environ.get('P3_PER_SUITE', '4')))
    parser.add_argument('--max-new', type=int, default=int(os.environ.get('P3_MAX_NEW', '2048')))
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--startup-timeout', type=float, default=1200)
    parser.add_argument('--bootstrap-iters', type=int, default=10000)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--stable-null', action='store_true')
    parser.add_argument('--pin-cpus', action='store_true')
    args = parser.parse_args(argv)
    if args.arms == ['stock', 'stock']:
        args.arms = ['stock-a', 'stock-b']
    elif args.arms[0] == args.arms[1]:
        parser.error('two distinct arm names are required')
    if args.rounds < 2 or args.rounds % 2:
        parser.error('rounds must be even and >= 2 for physical GPU swaps')
    if len(set(args.gpus)) != 2 or min(args.gpus) < 0:
        parser.error('two distinct nonnegative GPU indices are required')
    ports = [port + offset for port in args.ports for offset in (0, 1)]
    if len(set(ports)) != 4 or min(ports) < 1024 or max(ports) > 65535:
        parser.error('HTTP and NCCL ports must be distinct and within 1024..65535')
    if min(args.per_suite, args.max_new, args.warmup, args.bootstrap_iters) < 1:
        parser.error('sample counts, max-new, warmup and bootstrap-iters must be positive')
    if not math.isfinite(args.startup_timeout) or args.startup_timeout <= 0:
        parser.error('startup-timeout must be finite and positive')
    if args.stable_null and (args.arms != ['stock-a', 'stock-b'] or args.rounds != 4
                            or args.per_suite != 4 or args.max_new != 2048 or args.warmup != 2):
        parser.error('stable-null requires stock stock, four rounds, 4 items/suite, 2048 cap and warmup=2')
    if args.pin_cpus and not args.stable_null:
        parser.error('pin-cpus is only available in the explicit stable-null protocol')
    return args


def clean_environment():
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('SPECPILOT_') or key == 'SPECPILOT_DATA'}
    environment.update(SP_ROOT=str(ROOT), SP_SETTING=SETTING, PYTHONDONTWRITEBYTECODE='1')
    return environment


def load_requests(per_suite, suites, tokenizer, dev_dir=None):
    dev_dir = dev_dir or ROOT / 'assets/upstream/dev'
    requests = []
    for suite in suites:
        items = []
        with (dev_dir / f'{suite}.jsonl').open() as source:
            for line in source:
                if line.strip():
                    items.append(json.loads(line))
                if len(items) == per_suite:
                    break
        if len(items) != per_suite:
            raise ValueError(f'suite {suite}: expected {per_suite} items, got {len(items)}')
        for item in items:
            input_ids = tokenizer.apply_chat_template(
                [{'role': 'user', 'content': item['turns'][0]}],
                add_generation_prompt=True, tokenize=True, enable_thinking=True)
            if not isinstance(input_ids, list):
                input_ids = input_ids['input_ids']
            if not input_ids:
                raise ValueError(f'empty input: {item["id"]}')
            requests.append({'id': item['id'], 'suite': suite, 'turn': 0,
                             'input_ids': list(input_ids), 'input_sha256': sha_ids(input_ids)})
    if len({request['id'] for request in requests}) != len(requests):
        raise ValueError('duplicate request IDs')
    return requests


def write_json(path, value):
    with path.open('x') as destination:
        json.dump(value, destination, indent=2, ensure_ascii=False)
        destination.write('\n')
        destination.flush()
        os.fsync(destination.fileno())


def append_json(destination, value):
    destination.write(json.dumps(value, ensure_ascii=False) + '\n')
    destination.flush()
    os.fsync(destination.fileno())


def arm_specs(names, environment):
    config_path = ROOT / 'assets/upstream/configs' / SETTING / 'config.json'
    config = json.loads(config_path.read_text())
    data_dir = Path(environment.get('SPECPILOT_DATA', '/gpfs/users/jixinpeng/specpilot_data'))
    arms = []
    for name in names:
        kind = 'final' if name == 'final' else 'stock'
        engine = data_dir / 'work/engines' / f'{SETTING}-{kind}'
        tree_sha = (engine / 'TREE_SHA').read_text().strip()
        if len(tree_sha) != 64 or any(character not in '0123456789abcdef' for character in tree_sha):
            raise ValueError(f'invalid tree SHA: {engine}')
        arms.append({'name': name, 'block': 0 if name == 'ar' else config[kind]['block_size'],
                     'tree_sha': tree_sha, 'engine': str(engine),
                     'env': config['final']['env'] if name == 'final' else {}})
        if name in ('stock-a', 'stock-b'):
            arms[-1]['launch_arm'] = 'stock'
    return arms, config


def inspect_gpus(indices):
    output = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=index,uuid,name,memory.used,utilization.gpu',
         '--format=csv,noheader,nounits'], text=True)
    available = {}
    for values in csv.reader(output.splitlines(), skipinitialspace=True):
        index, uuid, name, memory, utilization = [value.strip() for value in values]
        available[int(index)] = {'index': int(index), 'uuid': uuid, 'name': name,
                                 'memory_used_mib': int(memory), 'utilization': int(utilization)}
    selected = [available[index] for index in indices]
    output = subprocess.check_output(
        ['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'], text=True)
    selected_uuids = {gpu['uuid'] for gpu in selected}
    busy = [line.strip() for line in output.splitlines()
            if line.split(',')[0].strip() in selected_uuids]
    if busy:
        raise RuntimeError('GPUs have existing compute processes; will not kill or overlap: '
                           + '; '.join(busy))
    for gpu in selected:
        if 'H100' not in gpu['name']:
            raise ValueError(f'expected H100: {gpu}')
        if gpu['utilization'] > 10 or gpu['memory_used_mib'] > 2048:
            raise RuntimeError(f'GPU not idle: {gpu}')
    return selected


@contextmanager
def gpu_lock(gpu):
    with Path(f'/tmp/specpilot-p3-{gpu["uuid"]}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def check_ports(ports):
    with ExitStack() as resources:
        for port in ports:
            for offset in (0, 1):
                listener = resources.enter_context(socket.socket())
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('127.0.0.1', port + offset))


def wait_for_idle(indices, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return inspect_gpus(indices)
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


class Server:
    def __init__(self, arm, gpu, port, output_dir, environment):
        self.arm, self.gpu, self.port = arm, gpu, port
        self.output_dir, self.environment = output_dir, environment
        self.process = None
        self.log = None

    def launch_spec(self):
        environment = dict(self.environment, SP_ENGINE=self.arm['engine'],
                           P3_SERVER_ONLY='1', P3_SERVER_LOG=str(self.output_dir / f'{self.arm["name"]}.server.log'))
        command = ['bash', str(ROOT / 'exp/p3_pair.sh'), self.arm.get('launch_arm', self.arm['name']),
                   self.gpu['uuid'], str(self.port),
                   str(self.output_dir / f'{self.arm["name"]}.unused.jsonl')]
        return command, environment

    def start(self):
        command, environment = self.launch_spec()
        self.log = (self.output_dir / f'{self.arm["name"]}.launcher.log').open('x')
        self.process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                        stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)

    def wait_ready(self, timeout):
        deadline = time.monotonic() + timeout
        arm = Arm(self.arm['name'], f'http://127.0.0.1:{self.port}')
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'{self.arm["name"]} server exited ({self.process.returncode}); '
                                   f'see {self.output_dir}')
            if arm.health(timeout=2):
                return
            time.sleep(2)
        raise TimeoutError(f'{self.arm["name"]} server startup timeout')

    def stop(self):
        try:
            if self.process is not None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.process.wait(timeout=30)
        finally:
            if self.log is not None:
                self.log.close()


def result_row(result, request, arm, gpu, round_index, max_new):
    if result['input_sha256'] != request['input_sha256']:
        raise ValueError(f'input hash mismatch: {request["id"]}')
    if not 0 < result['tokens'] <= max_new or len(result['output_ids']) != result['tokens']:
        raise ValueError(f'invalid token count: {request["id"]}')
    if not math.isfinite(result['tokens_per_s']) or result['tokens_per_s'] <= 0:
        raise ValueError(f'invalid throughput: {request["id"]}')
    if result['output_sha256'] != sha_ids(result['output_ids']):
        raise ValueError(f'output hash mismatch: {request["id"]}')
    if (arm['name'] == 'ar') != (result['spec_verify_ct'] == 0):
        raise ValueError(f'verify counter inconsistent with arm: {arm["name"]}')
    tau_source = ('ar_no_verify' if arm['name'] == 'ar' else
                  'spec_verify_ct_unverified_tlv' if arm['name'] == 'final' else 'per_verify_step')
    return dict(result, id=request['id'], item=request['id'], suite=request['suite'], turn=0,
                arm=arm['name'], block=arm['block'], tree_sha=arm['tree_sha'],
                gpu=gpu['index'], gpu_uuid=gpu['uuid'], round=round_index + 1,
                prompt_tokens=len(request['input_ids']), completion_tokens=result['tokens'],
                latency_s=result['latency_ms'] / 1000, max_new_tokens=max_new,
                tau_source=tau_source)


def run_round(arms, gpus, ports, round_index, requests, output_dir, environment,
              max_new, warmup, startup_timeout, server_factory=Server, bench_factory=HttpPairBench,
              stable_null=False, cpu_plan=None):
    output_dir.mkdir(parents=True, exist_ok=False)
    assigned = gpus if round_index % 2 == 0 else list(reversed(gpus))
    ports = list(reversed(ports)) if stable_null and round_index >= 2 else ports
    write_json(output_dir / 'deployment.json', {'round': round_index + 1,
               'assignments': [dict(arm=arm, gpu=gpu, port=port)
                               for arm, gpu, port in zip(arms, assigned, ports)]})
    pairs = []
    with ExitStack() as resources:
        events = resources.enter_context((output_dir / 'events.jsonl').open('x'))
        pair_file = resources.enter_context((output_dir / 'pairs.jsonl').open('x'))
        arm_files = [resources.enter_context((output_dir / f'{arm["name"]}.jsonl').open('x'))
                     for arm in arms]
        servers = [server_factory(arm, gpu, port, output_dir, environment)
                   for arm, gpu, port in zip(arms, assigned, ports)]
        launch = list(reversed(servers)) if stable_null and round_index in (1, 2) else servers
        for server in launch:
            resources.callback(server.stop)
            server.start()
        append_json(events, {'event': 'servers_started', 'time_unix': time.time()})
        if stable_null:
            resources.enter_context(Telemetry(servers, gpus, output_dir / 'telemetry.jsonl',
                                             inspect_threads=cpu_plan is not None))
        for server in servers:
            server.wait_ready(startup_timeout)
        if stable_null:
            append_json(events, {'event': 'servers_ready', 'time_unix': time.time()})
        if cpu_plan is not None:
            from harness.cpu_affinity import apply_bindings, owned_processes, plan_bindings
            if not cpu_plan:
                cpu_plan.update(plan_bindings(servers, owned_processes(servers)))
                write_json(output_dir.parent / 'cpu-plan.json', cpu_plan)
            ready_binding = apply_bindings(servers, cpu_plan)
            write_json(output_dir / 'cpu-binding-ready.json', ready_binding)
        clients = [Arm(arm['name'], f'http://127.0.0.1:{port}',
                       block_size=arm['block'], tree_sha=arm['tree_sha'], env=arm.get('env', {}),
                       trace_timing=stable_null)
                   for arm, port in zip(arms, ports)]
        for client in clients:
            client.begin_session()
        bench = (bench_factory(*clients, synchronized_start=True, reverse_submission=round_index in (1, 2))
                 if stable_null else bench_factory(*clients))
        warm_file = resources.enter_context((output_dir / 'warmup.jsonl').open('x')) if stable_null else None
        for warm_index in range(warmup):
            request = requests[warm_index % len(requests)]
            measurement = bench.run_pair(request['input_ids'], min(32, max_new), warmup=0, swap=False,
                                         rid=f'round-{round_index + 1}|warm-{warm_index}')
            if stable_null:
                append_json(warm_file, dict(phase='short', id=request['id'], suite=request['suite'],
                            **{key: result_row(measurement['rounds'][0][key], request, arm, gpu,
                                               round_index, min(32, max_new))
                               for key, arm, gpu in zip(('a', 'b'), arms, assigned)}))
        if stable_null:
            for index, request in enumerate(requests):
                measurement = bench.run_pair(request['input_ids'], max_new, warmup=0, swap=False,
                                             rid=f'round-{round_index + 1}|full-warm-{index}')
                append_json(warm_file, dict(phase='full', id=request['id'], suite=request['suite'],
                            **{key: result_row(measurement['rounds'][0][key], request, arm, gpu, round_index, max_new)
                               for key, arm, gpu in zip(('a', 'b'), arms, assigned)}))
                print(f'[round {round_index + 1} full-warm {index + 1}/{len(requests)}] {request["id"]}', flush=True)
        if cpu_plan is not None:
            measured_binding = apply_bindings(servers, cpu_plan, expected=ready_binding)
            write_json(output_dir / 'cpu-binding-measured.json', measured_binding)
        append_json(events, {'event': 'warmup_complete', 'time_unix': time.time()})
        for item_index, request in enumerate(requests):
            pair_id = f'round-{round_index + 1}|{request["id"]}'
            started = time.time()
            measurement = bench.run_pair(request['input_ids'], max_new, warmup=0,
                                         swap=False, rid=pair_id)
            if len(measurement['rounds']) != 1:
                raise ValueError('expected exactly one controller round per physical assignment')
            result = measurement['rounds'][0]
            row_a, row_b = [result_row(result[key], request, arm, gpu, round_index, max_new)
                            for key, arm, gpu in zip(('a', 'b'), arms, assigned)]
            pair = {'pair_id': pair_id, 'round': round_index + 1, 'id': request['id'],
                    'suite': request['suite'], 'started_unix': started,
                    'finished_unix': time.time(), 'a': row_a, 'b': row_b}
            append_json(pair_file, pair)
            for destination, row in zip(arm_files, (row_a, row_b)):
                append_json(destination, row)
            pairs.append(pair)
            print(f'[round {round_index + 1} {item_index + 1}/{len(requests)}] '
                  f'{request["id"]} {arms[0]["name"]}={row_a["tokens_per_s"]:.2f} '
                  f'{arms[1]["name"]}={row_b["tokens_per_s"]:.2f} tok/s', flush=True)
        append_json(events, {'event': 'requests_complete', 'time_unix': time.time()})
    write_json(output_dir / 'complete.json', {'round': round_index + 1, 'pairs': len(pairs)})
    return pairs


def summarize(pairs, requests, rounds, iters=10000):
    expected = {(round_index + 1, request['id'])
                for round_index in range(rounds) for request in requests}
    actual = [(pair['round'], pair['id']) for pair in pairs]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('missing or duplicate request/round pairs')
    by_request = {request['id']: [] for request in requests}
    for pair in pairs:
        if pair['a']['input_sha256'] != pair['b']['input_sha256']:
            raise ValueError('unpaired input hashes')
        by_request[pair['id']].append(math.log(pair['b']['tokens_per_s'] /
                                              pair['a']['tokens_per_s']))
    log_ratios = {request_id: sum(values) / len(values)
                  for request_id, values in by_request.items()}
    by_suite = {}
    for request in requests:
        by_suite.setdefault(request['suite'], []).append(log_ratios[request['id']])
    if len({len(values) for values in by_suite.values()}) != 1:
        raise ValueError('unequal suite coverage is not supported')
    values = list(log_ratios.values())
    mean_log, lower_log = bootstrap_ci(values, iters=iters, alpha=0.025, seed=0)
    _, negative_lower = bootstrap_ci([-value for value in values], iters=iters, alpha=0.025, seed=0)
    return {'geomean': math.exp(mean_log), 'lower': math.exp(lower_log),
            'upper': math.exp(-negative_lower), 'confidence_level': 0.95,
            'n_requests': len(requests), 'n_pairs': len(pairs), 'rounds': rounds,
            'per_suite': {suite: math.exp(sum(logs) / len(logs))
                          for suite, logs in by_suite.items()},
            'per_request_log_ratios': log_ratios,
            'aggregation': 'per-request geometric mean across GPU assignments; equal-weight suite geometric mean',
            'ci_method': 'controller.stats.bootstrap_ci on paired request log ratios; pooled request-cluster bootstrap; physical rounds kept together; not suite-stratified',
            'bootstrap_iters': iters, 'bootstrap_seed': 0, 'ledger_eligible': False,
            'scope': 'dev diagnostic; no promotion, sealed or lossless claim'}


def interrupted(signum, frame):
    raise KeyboardInterrupt(f'interrupted by signal {signum}')


def main(argv=None):
    args = parse_args(argv)
    output_dir = args.out_dir.resolve()
    plan = {'arms': args.arms, 'out_dir': str(output_dir), 'rounds': args.rounds,
            'per_suite': args.per_suite, 'max_new_tokens': args.max_new,
            'ports': args.ports, 'warmup': args.warmup,
            'startup_timeout_s': args.startup_timeout,
            'suites': SUITES, 'execute': args.execute,
            'gpu_assignments': [args.gpus if index % 2 == 0 else list(reversed(args.gpus))
                                for index in range(args.rounds)]}
    if args.stable_null:
        plan['stable_null'] = True
    if args.pin_cpus:
        plan['cpu_pinning'] = True
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return 0
    if output_dir.exists():
        raise FileExistsError(f'refusing to reuse output directory: {output_dir}')
    environment = clean_environment()
    environment['P3_READY_POLLS'] = str(math.ceil(args.startup_timeout / 2))
    arms, config = arm_specs(args.arms, environment)
    signal.signal(signal.SIGTERM, interrupted)
    with ExitStack() as resources:
        gpus = inspect_gpus(args.gpus)
        for gpu in sorted(gpus, key=lambda entry: entry['index']):
            resources.enter_context(gpu_lock(gpu))
        inspect_gpus(args.gpus)
        check_ports(args.ports)
        from transformers import AutoTokenizer
        target = environment.get('SP_TARGET', '/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B')
        tokenizer = AutoTokenizer.from_pretrained(target, local_files_only=True)
        requests = load_requests(args.per_suite, SUITES, tokenizer)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        sources = ['exp/p3_pair.sh', 'exp/p3_pair_run.py', 'controller/http_transport.py', 'controller/stats.py']
        if args.stable_null:
            sources += ['harness/telemetry.py', 'controller/stability_validation.py']
        if args.pin_cpus:
            sources += ['harness/cpu_affinity.py']
        source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
        output_dir.mkdir(parents=True, exist_ok=False)
        write_json(output_dir / 'manifest.json', dict(plan, arms=arms, gpus=gpus,
                   head=head, source_sha256=source_hashes, requests=requests,
                   model_path=target, declared_models=config['models'],
                   sampling={'temperature': 0.0, 'top_k': 1, 'enable_thinking': True},
                   started_unix=time.time()))
        pairs = []
        cpu_plan = {} if args.pin_cpus else None
        try:
            for round_index in range(args.rounds):
                if round_index:
                    check_ports(args.ports)
                pairs.extend(run_round(arms, gpus, args.ports, round_index, requests,
                             output_dir / f'round-{round_index + 1:02d}', environment,
                             args.max_new, args.warmup, args.startup_timeout,
                             stable_null=args.stable_null, cpu_plan=cpu_plan))
                wait_for_idle(args.gpus)
            summary = summarize(pairs, requests, args.rounds, args.bootstrap_iters)
            summary.update(arms=args.arms, max_new_tokens=args.max_new,
                           per_suite_requested=args.per_suite)
            if args.arms == ['ar', 'stock']:
                summary['acceptance'] = {'target': 3.95, 'relative_tolerance': 0.10,
                                         'passed': 3.95 * 0.9 <= summary['geomean'] <= 3.95 * 1.1}
            write_json(output_dir / 'summary.json', summary)
            print(json.dumps(summary, indent=2), flush=True)
            return 0 if summary.get('acceptance', {}).get('passed', True) else 1
        except BaseException as error:
            write_json(output_dir / 'failed.json', {'error': repr(error), 'time_unix': time.time()})
            raise


if __name__ == '__main__':
    raise SystemExit(main())
