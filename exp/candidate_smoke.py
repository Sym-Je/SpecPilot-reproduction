"""No-op real candidate lifecycle and scoring integration; never a promotion gate."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from controller.dev_campaign import check_scored_measurements, validate_packet
from controller.http_transport import Arm, sha_ids
from controller.scored_forcing import load_score_trace, read_reference
from controller.scoring import NativeClient, server_arguments
from exp.p3_pair_run import Server, SETTING, SUITES, arm_specs, check_ports, clean_environment, gpu_lock, interrupted, load_requests, run_round, wait_for_idle, write_json
from exp.p5_real_run import Campaign, head_process, launch
from harness.candidate import build_bundle, candidate_arm, check_identity, expected_arguments, launch_environment, load_bundle, make_spec


MODES = ('disabled', 'enabled')
PROTOCOL = 'noop-candidate-smoke-v1'
FROZEN_STOCK_SHA = 'e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff'


class CandidateServer(Server):
    def launch_spec(self):
        if self.arm['name'] == 'stock':
            return super().launch_spec()
        spec = load_bundle(Path(self.arm['engine']).parent)
        environment = launch_environment(self.environment, self.arm, spec, self.gpu['uuid'], self.port)
        environment['SP_ROOT'] = str(ROOT)
        environment['SP_SETTING'] = SETTING
        return ['bash', str(ROOT / 'exp/candidate_serve.sh'), str(Path(self.arm['engine']).parent),
                '1' if self.arm['option_enabled'] else '0',
                str(self.output_dir / 'candidate.runtime.json')], environment

    def start(self):
        super().start()
        start_ticks = Path(f'/proc/{self.process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        write_json(self.output_dir / f'{self.arm["name"]}.process.json',
                   dict(pid=self.process.pid, start_ticks=int(start_ticks)))

    def stop(self):
        super().stop()
        if self.process is not None:
            write_json(self.output_dir / f'{self.arm["name"]}.stopped.json', dict(stopped=self.process.poll() is not None))


class CapturedArm(Arm):
    def __init__(self, name, url, *, directory, spec, **options):
        options['trace_timing'] = True
        super().__init__(name, url, raw_dir=directory / f'{name}-raw', **options)
        client = NativeClient(url, directory / f'{name}-identity')
        self.generator = client.server_identity(self.tree_sha)
        actual = server_arguments(read_reference(self.generator['evidence'], directory)['response'])
        self.generator['server_args'] = {key: actual.get(key) for key in expected_arguments(spec, self.block_size)}
        check_identity(self.generator, spec, self.block_size)

    def step(self, *arguments, **options):
        return dict(super().step(*arguments, **options), generator=self.generator)


def source_hashes():
    names = subprocess.check_output(['git', 'ls-files', '--', 'controller', 'harness', 'exp',
        'assets/upstream/dev', f'assets/upstream/configs/{SETTING}/config.json'], cwd=ROOT, text=True).splitlines()
    names += ['harness/candidate.py', 'exp/candidate_smoke.py', 'exp/candidate_remote.sh', 'exp/candidate_serve.sh']
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sorted(set(names)) if Path(name).suffix in ('.py', '.sh', '.json', '.jsonl')}


def smoke_manifest(bundle, gpus, requests, ports):
    spec = load_bundle(bundle)
    if spec['value'] != 8:
        raise ValueError('this smoke requires an intentionally no-op enabled value of 8')
    return dict(protocol=PROTOCOL, source_pin=spec['source_pin'], source_sha256=source_hashes(),
                bundle=str(Path(bundle).absolute()), spec_sha256=spec['spec_sha256'],
                requests=requests, gpus=gpus, ports=ports, modes=list(MODES), rounds=2,
                max_new_tokens=64, warmup=2, model_path=spec['target'],
                launch_protocol=expected_arguments(spec, 8), started_unix=time.time())


def mode_arms(manifest, mode):
    spec = load_bundle(manifest['bundle'])
    stock = dict(name='stock', block=8, tree_sha=spec['stock_tree_sha'], engine=spec['stock_engine'], env={})
    return [stock, candidate_arm(manifest['bundle'], enabled=mode == 'enabled')]


def run_modes(directory, manifest, environment, *, server_factory=CandidateServer, after_round=None):
    spec = load_bundle(manifest['bundle'])
    for mode in MODES:
        mode_dir = directory / mode
        mode_dir.mkdir()
        arms = mode_arms(manifest, mode)
        for number in (0, 1):
            check_ports(manifest['ports'])
            round_dir = mode_dir / f'round-{number + 1:02d}'
            def factory(name, url, **options):
                return CapturedArm(name, url, directory=round_dir, spec=spec, **options)
            run_round(arms, manifest['gpus'], manifest['ports'], number, manifest['requests'], round_dir,
                      environment, 64, 2, 1200, server_factory=server_factory, arm_factory=factory)
            if after_round is not None:
                after_round()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def validate_smoke(directory, *, require_scores=True):
    directory = Path(directory).absolute()
    manifest = json.loads((directory / 'manifest.json').read_text())
    spec = load_bundle(manifest['bundle'])
    if (manifest['protocol'] != PROTOCOL or manifest['modes'] != list(MODES) or manifest['rounds'] != 2 or
            manifest['max_new_tokens'] != 64 or manifest['warmup'] != 2 or spec['value'] != 8 or
            manifest['source_pin'] != spec['source_pin'] or manifest['spec_sha256'] != spec['spec_sha256'] or
            manifest['launch_protocol'] != expected_arguments(spec, 8)):
        raise ValueError('unexpected smoke protocol or candidate identity')
    requests = manifest['requests']
    if (len(requests) != 5 or {request['suite'] for request in requests} != set(SUITES) or
            len({request['id'] for request in requests}) != 5 or
            any(sha_ids(request['input_ids']) != request['input_sha256'] for request in requests) or
            len(manifest['gpus']) != 2 or len({gpu['uuid'] for gpu in manifest['gpus']}) != 2):
        raise ValueError('invalid request or GPU coverage')
    if manifest['source_sha256'] != source_hashes():
        raise ValueError('execution sources changed')
    index = json.loads((directory / 'correctness/index.json').read_text()) if require_scores else {}
    processes, measured, expected_index, measured_end = set(), 0, set(), 0
    for mode in MODES:
        arms = mode_arms(manifest, mode)
        for number in (0, 1):
            root = directory / mode / f'round-{number + 1:02d}'
            if json.loads((root / 'complete.json').read_text()) != dict(round=number+1, pairs=5):
                raise ValueError('missing complete physical round')
            assigned = manifest['gpus'] if number == 0 else list(reversed(manifest['gpus']))
            expected = [dict(arm=arm, gpu=gpu, port=port) for arm,gpu,port in zip(arms,assigned,manifest['ports'])]
            if json.loads((root / 'deployment.json').read_text()) != dict(round=number+1, assignments=expected):
                raise ValueError('physical GPU assignment or candidate mode changed')
            pairs = read_rows(root / 'pairs.jsonl')
            if len(pairs) != 5 or [pair['id'] for pair in pairs] != [request['id'] for request in requests]:
                raise ValueError('incomplete or reordered paired requests')
            measured_end = max(measured_end, max(pair['finished_unix'] for pair in pairs))
            events = read_rows(root / 'events.jsonl')
            if [event['event'] for event in events] != ['servers_started','warmup_complete','requests_complete']:
                raise ValueError('incomplete server lifecycle')
            for key, assignment in zip(('a','b'), expected):
                name = assignment['arm']['name']
                process = json.loads((root / f'{name}.process.json').read_text())
                identity = (process['pid'], process['start_ticks'])
                if identity in processes or any(type(value) is not int or value <= 0 for value in identity):
                    raise ValueError('servers were not fresh')
                processes.add(identity)
                if name == 'candidate':
                    runtime = json.loads((root / 'candidate.runtime.json').read_text())
                    if (runtime['pid'] != process['pid'] or runtime['block'] != assignment['arm']['block'] or
                            runtime['spec_sha256'] != spec['spec_sha256'] or
                            not Path(runtime['module_origin']).is_relative_to(Path(assignment['arm']['engine']) / 'python')):
                        raise ValueError('candidate runtime did not resolve the bound snapshot')
                if json.loads((root / f'{name}.stopped.json').read_text()) != dict(stopped=True):
                    raise ValueError('server was not stopped')
                rows = read_rows(root / f'{name}.jsonl')
                if rows != [pair[key] for pair in pairs] or len(list((root / f'{name}-raw').glob('*.json'))) != 7:
                    raise ValueError('canonical arm rows or captured warmup coverage changed')
                for sample, request in zip(rows,requests):
                    validate_packet(sample,request,assignment,64,directory,manifest['launch_protocol'])
                index_key = f'{mode}/round-{number+1:02d}/{name}'
                expected_index.add(index_key)
                if require_scores:
                    check_scored_measurements(index[index_key], rows, requests, evidence_root=directory)
                measured += len(rows)
            if any(pair['a']['output_ids'] != pair['b']['output_ids'] for pair in pairs):
                raise ValueError('no-op candidate output differs from stock')
    if require_scores:
        if spec['stock_tree_sha'] != FROZEN_STOCK_SHA:
            raise ValueError('smoke baseline is not the frozen stock engine')
        if set(index) != expected_index:
            raise ValueError('unexpected scored cohort coverage')
        for paths in index.values():
            for path in paths:
                trace = load_score_trace(path,evidence_root=directory)
                if read_reference(trace['raw_evidence'],directory)['started_unix'] < measured_end:
                    raise ValueError('FP32 scoring overlapped the timing smoke')
        head = json.loads((directory / 'correctness/head-preflight/result.json').read_text())
        if (head.get('mode') != 'preflight' or head.get('tokens') != 1 or
                head.get('native_reverse_token_differences') != 0 or
                head.get('head_identity',{}).get('source_sha256') != manifest['source_sha256']['controller/head_reference.py']):
            raise ValueError('missing or wrong-source FP32 head preflight')
        for path, checksum in manifest['model_configs'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != checksum:
                raise ValueError('target or draft model config changed')
        cleanup = json.loads((directory / 'cleanup.json').read_text())
        if ({gpu['uuid'] for gpu in cleanup} != {gpu['uuid'] for gpu in manifest['gpus']} or
                any(gpu['memory_used_mib'] != 0 or gpu['utilization'] > 10 for gpu in cleanup)):
            raise ValueError('GPU cleanup failed')
        archive = manifest['source_archive']
        if hashlib.sha256(Path(archive['path']).read_bytes()).hexdigest() != archive['sha256']:
            raise ValueError('frozen execution archive changed')
        with tarfile.open(archive['path']) as snapshot:
            for name, expected in manifest['source_sha256'].items():
                if hashlib.sha256(snapshot.extractfile(name).read()).hexdigest() != expected:
                    raise ValueError('archive does not match the running code')
    return dict(protocol=PROTOCOL, source_pin=spec['source_pin'], spec_sha256=spec['spec_sha256'],
                modes=list(MODES), rounds_per_mode=2, independent_requests=5, pairs=measured//2,
                arm_rows=measured, fresh_servers=len(processes), physical_gpu_swap_verified=True,
                noop_output_identical=True, scoring_interface_verified=require_scores,
                correctness_passed=None, performance_passed=None, promoted=False, ledger_eligible=False,
                scope='no-op lifecycle and scoring integration only; no lossless, performance or discovery claim')


def score_outputs(directory, manifest, environment):
    correctness = directory / 'correctness'
    correctness.mkdir()
    spec = load_bundle(manifest['bundle'])
    stock = mode_arms(manifest,'disabled')[0]
    with ExitStack() as resources:
        check_ports([30130])
        launch(stock,'scorer',manifest['gpus'][1],correctness,environment,resources)
        scorer = NativeClient('http://127.0.0.1:30130',correctness / 'scorer-raw')
        scorer.scorer_identity(spec['stock_tree_sha'])
        head_process('preflight',correctness / 'head-preflight',directory,spec['stock_tree_sha'])
        bench = Campaign(correctness,scorer,evidence_root=directory)
        index = {}
        for mode in MODES:
            for number in (1,2):
                root = directory / mode / f'round-{number:02d}'
                for name in ('stock','candidate'):
                    cohort = f'{mode}-round-{number:02d}-{name}'
                    rows = read_rows(root / f'{name}.jsonl')
                    index[f'{mode}/round-{number:02d}/{name}'] = [
                        bench.save_trace(cohort,request,row['output_ids'],row['generator'],[row['raw_evidence']])
                        for request,row in zip(manifest['requests'],rows)]
        write_json(correctness / 'index.json',index)


def serve_command(spec, block, python, port):
    command = [python, '-m', 'sglang.launch_server']
    for name, value in expected_arguments(spec, block).items():
        if value is False:
            continue
        command.append('--' + name.replace('_','-'))
        if value is not True:
            command.append(str(value))
    return command + ['--served-model-name',Path(spec['target']).name,'--host','127.0.0.1',
                      '--port',str(port),'--nccl-port',str(port+1)]


def serve(bundle, enabled, receipt):
    spec = load_bundle(bundle)
    if spec['stock_tree_sha'] != FROZEN_STOCK_SHA:
        raise ValueError('candidate baseline is not the pinned stock build')
    arm = candidate_arm(bundle, enabled=enabled)
    engine = Path(arm['engine'])
    origin = importlib.util.find_spec('sglang').origin
    if origin is None or not Path(origin).resolve().is_relative_to(engine / 'python'):
        raise ValueError('sglang module resolved outside the candidate engine snapshot')
    port = int(os.environ['PORT'])
    command = serve_command(spec,arm['block'],sys.executable,port)
    write_json(receipt,dict(pid=os.getpid(),block=arm['block'],spec_sha256=spec['spec_sha256'],
                           module_origin=str(Path(origin).resolve()),command=command))
    os.execve(sys.executable,command,dict(os.environ))


def run(directory, bundle):
    from transformers import AutoTokenizer
    spec = load_bundle(bundle)
    if spec['stock_tree_sha'] != FROZEN_STOCK_SHA or spec['value'] != 8:
        raise ValueError('this smoke requires the pinned stock tree and a no-op option value')
    actual = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if actual != spec['source_pin'] or actual != os.environ['CANDIDATE_EXPECTED_COMMIT']:
        raise ValueError('live checkout is not the frozen candidate source')
    subprocess.run(['git','diff','--exit-code',actual,'--','controller','exp','harness','assets/upstream'],cwd=ROOT,check=True)
    directory.mkdir(parents=True,exist_ok=False)
    environment = clean_environment()
    environment.update(SP_TARGET=spec['target'], SP_DRAFT=spec['draft'])
    signal.signal(signal.SIGTERM,interrupted)
    with ExitStack() as resources:
        gpus = wait_for_idle([0,1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        tokenizer = AutoTokenizer.from_pretrained(spec['target'],local_files_only=True)
        requests = load_requests(1,SUITES,tokenizer)
        manifest = smoke_manifest(bundle,gpus,requests,[30100,30110])
        manifest['model_configs'] = {str(Path(path)/'config.json'):
            hashlib.sha256((Path(path)/'config.json').read_bytes()).hexdigest()
            for path in (spec['target'],spec['draft'])}
        archive = Path(os.environ['CANDIDATE_SOURCE_TAR'])
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        if checksum != os.environ['CANDIDATE_SOURCE_SHA256']:
            raise ValueError('source archive differs from the predeclared identity')
        manifest['source_archive'] = dict(path=str(archive),sha256=checksum)
        write_json(directory / 'manifest.json',manifest)
        run_modes(directory,manifest,environment,after_round=lambda:wait_for_idle([0,1]))
        check_ports(manifest['ports'])
        write_json(directory / 'timing-cleanup.json',wait_for_idle([0,1]))
        score_outputs(directory,manifest,environment)
        check_ports(manifest['ports']+[30130])
        write_json(directory / 'cleanup.json',wait_for_idle([0,1]))
        result = validate_smoke(directory)
        write_json(directory / 'result.json',result)
        print(json.dumps(result),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--bundle',type=Path,required=True)
    execute = commands.add_parser('run')
    execute.add_argument('--bundle',type=Path,required=True)
    execute.add_argument('--out-dir',type=Path,required=True)
    audit = commands.add_parser('audit')
    audit.add_argument('--directory',type=Path,required=True)
    audit.add_argument('--out',type=Path,required=True)
    server = commands.add_parser('serve')
    server.add_argument('--bundle',type=Path,required=True)
    server.add_argument('--enabled',action='store_true')
    server.add_argument('--receipt',type=Path,required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        environment = clean_environment()
        arms, _ = arm_specs(['stock'],environment)
        pin = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        spec = make_spec(arms[0]['engine'],ROOT/'assets/upstream/configs'/SETTING/'config.json',
            environment.get('SP_TARGET','/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B'),
            environment.get('SP_DRAFT','/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2'),pin)
        if spec['stock_tree_sha'] != FROZEN_STOCK_SHA:
            raise ValueError('baseline differs from the frozen stock tree')
        build_bundle(spec,args.bundle)
        print(json.dumps(dict(spec_sha256=spec['spec_sha256'],stock_tree_sha=spec['stock_tree_sha'])))
    elif args.command == 'run':
        run(args.out_dir.absolute(),args.bundle.absolute())
    elif args.command == 'audit':
        result = validate_smoke(args.directory)
        write_json(args.out,result)
        print(json.dumps(result))
    else:
        serve(args.bundle.absolute(),args.enabled,args.receipt.absolute())


if __name__ == '__main__':
    main()
