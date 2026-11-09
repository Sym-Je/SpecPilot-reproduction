"""Frozen, paired real-engine diagnostics for agent-selected startup options."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from exp.candidate_smoke import CandidateServer, CapturedArm, FROZEN_STOCK_SHA
from exp.p3_pair_run import SETTING, SUITES, Server, check_ports, clean_environment, gpu_lock, interrupted, load_requests, run_round, summarize, wait_for_idle, write_json
from harness.candidate import build_bundle, candidate_arm, load_bundle, make_spec
from harness.engine_research import validate_action
from controller.dev_campaign import validate_packet


class ResearchServer(CandidateServer):
    def launch_spec(self):
        if 'candidate_id' not in self.arm:
            return Server.launch_spec(self)
        return super().launch_spec()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    action = validate_action(manifest['action'])
    request_path = directory.parent / 'request.json'
    request = json.loads(request_path.read_text())
    if (manifest['request_sha256'] != file_sha(request_path) or request['action'] != action or
            manifest['source_pin'] != request['source_pin'] or
            manifest['source_archive_sha256'] != file_sha(directory.parent / 'source.tar')):
        raise ValueError('output is not bound to the frozen role request/source')
    spec = load_bundle(manifest['bundle'])
    if spec['value'] != action['value'] or spec['stock_tree_sha'] != FROZEN_STOCK_SHA:
        raise ValueError('candidate does not match the role request')
    requests = manifest['requests']
    if (len(requests) != 5 * action['per_suite'] or {row['suite'] for row in requests} != set(SUITES) or
            len({row['id'] for row in requests}) != len(requests)):
        raise ValueError('invalid public dev coverage')
    if len(manifest['gpus']) != 2 or len({row['uuid'] for row in manifest['gpus']}) != 2:
        raise ValueError('two distinct physical GPUs required')
    pairs = []
    processes = set()
    for number in (0, 1):
        root = directory / f'round-{number + 1:02d}'
        mapping = manifest['gpus'] if number == 0 else list(reversed(manifest['gpus']))
        expected = [dict(arm=arm, gpu=gpu, port=port) for arm, gpu, port in
                    zip(manifest['arms'], mapping, manifest['ports'])]
        if json.loads((root / 'deployment.json').read_text()) != dict(round=number + 1, assignments=expected):
            raise ValueError('physical assignment changed')
        if json.loads((root / 'complete.json').read_text()) != dict(round=number + 1, pairs=len(requests)):
            raise ValueError('incomplete paired round')
        rows = [json.loads(line) for line in (root / 'pairs.jsonl').read_text().splitlines()]
        if ([row['id'] for row in rows] != [row['id'] for row in requests] or
                any(row['round'] != number + 1 for row in rows)):
            raise ValueError('reordered or missing requests')
        warmup = [json.loads(line) for line in (root / 'warmup.jsonl').read_text().splitlines()]
        if [row['phase'] for row in warmup] != ['short', 'short'] + ['full'] * len(requests):
            raise ValueError('incomplete registered warmup')
        warm_requests = requests[:2] + requests
        for key, assignment in zip(('a', 'b'), expected):
            name = assignment['arm']['name']
            process = json.loads((root / f'{name}.process.json').read_text())
            identity = (process['pid'], process['start_ticks'])
            if identity in processes:
                raise ValueError('server was not fresh')
            processes.add(identity)
            if any(type(value) is not int or value <= 0 for value in identity):
                raise ValueError('invalid process identity')
            if json.loads((root / f'{name}.stopped.json').read_text()) != dict(stopped=True):
                raise ValueError('server not terminated')
            arm_rows = [json.loads(line) for line in (root / f'{name}.jsonl').read_text().splitlines()]
            if arm_rows != [row[key] for row in rows]:
                raise ValueError('canonical arm output differs')
            for row, request in zip(arm_rows, requests):
                from harness.candidate import expected_arguments
                validate_packet(row, request, assignment, action['max_new_tokens'], directory,
                                expected_arguments(spec, assignment['arm']['block']))
            for row, request in zip(warmup, warm_requests):
                cap = min(32, action['max_new_tokens']) if row['phase'] == 'short' else action['max_new_tokens']
                validate_packet(row[key], request, assignment, cap, directory,
                                expected_arguments(spec, assignment['arm']['block']))
            if name == 'candidate':
                runtime = json.loads((root / 'candidate.runtime.json').read_text())
                if (runtime['pid'] != process['pid'] or runtime['spec_sha256'] != spec['spec_sha256'] or
                        runtime['block'] != spec['value'] or
                        not Path(runtime['module_origin']).is_relative_to(Path(assignment['arm']['engine']) / 'python')):
                    raise ValueError('candidate module identity changed')
        pairs.extend(rows)
    result = summarize(pairs, requests, 2)
    result.update(controller_accepted=False, candidate_promoted=False, lossless_verified=False,
        protocol='startup-option-research-v1', option_value=spec['value'], stock_default=8,
        max_new_tokens=action['max_new_tokens'], scope='public dev diagnostic; startup tuning, not algorithm discovery or promotion')
    return result


def run(request, directory):
    from transformers import AutoTokenizer
    from harness.gpu_autonomy import digest
    from exp.p3_pair_run import inspect_gpus

    record = json.loads(Path(request).read_text())
    action = validate_action(record['action'])
    directory.mkdir(parents=True, exist_ok=False)
    owner = directory.parent.stat()
    environment = clean_environment()
    environment['SP_ROOT'] = str(ROOT)
    environment['SP_KIND'] = 'stock'
    target = '/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B'
    draft = '/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2'
    stock = '/gpfs/users/jixinpeng/specpilot_data/work/engines/h100_c1_qwen38-27b_dflash2-stock'
    config = Path('/gpfs/users/jixinpeng/SpecDec/SpecPilot/assets/upstream/configs') / SETTING / 'config.json'
    if file_sha(config) != file_sha(ROOT / 'assets/upstream/configs' / SETTING / 'config.json'):
        raise ValueError('live baseline config differs from frozen source')
    spec = make_spec(stock, config,
                     target, draft, record['source_pin'], value=action['value'])
    if spec['stock_tree_sha'] != FROZEN_STOCK_SHA:
        raise ValueError('stock source identity changed')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        with ExitStack() as resources:
            gpus = inspect_gpus([0, 1])
            for gpu in gpus:
                resources.enter_context(gpu_lock(gpu))
            build_bundle(spec, directory / 'bundle')
            arms = [dict(name='stock', block=8, tree_sha=spec['stock_tree_sha'], engine=stock, env={}),
                    candidate_arm(directory / 'bundle', enabled=True)]
            tokenizer = AutoTokenizer.from_pretrained(target, trust_remote_code=True, local_files_only=True)
            requests = load_requests(action['per_suite'], SUITES, tokenizer)
            if record.get('mode') == 'controller-dev':
                from exp.engine_dev_gate import run_gate
                print(json.dumps(run_gate(directory, record, spec, arms, gpus, requests, environment)), flush=True)
                return
            manifest = dict(action=action, source_pin=record['source_pin'], request_sha256=digest(request),
                source_archive_sha256=os.environ['SP_ENGINE_SOURCE_SHA'], bundle=str(directory / 'bundle'),
                gpus=gpus, ports=[30400, 30410], arms=arms, requests=requests, started_unix=time.time())
            write_json(directory / 'manifest.json', manifest)
            pairs = []
            for number in (0, 1):
                check_ports(manifest['ports'])
                round_dir = directory / f'round-{number + 1:02d}'
                def factory(name, url, **options):
                    return CapturedArm(name, url, directory=round_dir, spec=spec, **options)
                pairs.extend(run_round(arms, gpus, manifest['ports'], number, requests, round_dir,
                    environment, action['max_new_tokens'], 2, 1200, server_factory=ResearchServer,
                    arm_factory=factory, stable_null=True))
                wait_for_idle([0, 1])
            check_ports(manifest['ports'])
            write_json(directory / 'cleanup.json', wait_for_idle([0, 1]))
            result = audit(directory)
            write_json(directory / 'result.json', result)
            print(json.dumps(result), flush=True)
    finally:
        for path in [directory, *directory.rglob('*')]:
            if not path.is_symlink():
                os.chown(path, owner.st_uid, owner.st_gid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'audit'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'run':
        if args.request is None:
            parser.error('--request is required for run')
        run(args.request, args.directory.absolute())
    else:
        print(json.dumps(audit(args.directory)))


if __name__ == '__main__':
    main()
