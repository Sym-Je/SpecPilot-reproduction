"""Fixed thirty-request dev campaign with bracketed null and exact-output forcing."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.dev_campaign import PHASES, PROTOCOL, correctness_reference, validate_campaign, validate_session
from controller.http_transport import Arm
from controller.paper_policy import measurement_protocol_id
from controller.scored_forcing import calibrate_delta, calibrate_stock, judge_scored_forcing
from controller.scoring import NativeClient
from exp.p3_pair_run import SUITES, arm_specs, check_ports, clean_environment, gpu_lock, interrupted, load_requests, run_round, summarize, wait_for_idle, write_json
from exp.p5_real_run import Campaign, head_process, launch


class CapturedArm(Arm):
    def __init__(self, name, url, *, output_dir, **options):
        super().__init__(name, url, raw_dir=output_dir / f'{name}-raw', **options)
        client = NativeClient(url, output_dir / f'{name}-identity')
        self.generator = client.server_identity(self.tree_sha)

    def step(self, *args, **options):
        result = super().step(*args, **options)
        return dict(result, generator=self.generator)


def build_campaign(directory, environment, gpus):
    from transformers import AutoTokenizer

    expected = os.environ['DEV_EXPECTED_COMMIT']
    subprocess.run(['git', 'diff', '--exit-code', expected, '--', 'controller', 'exp', 'harness', 'assets/upstream/dev'], cwd=ROOT, check=True)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if actual != expected:
        raise ValueError('the live checkout is not the frozen campaign source')
    target = environment.get('SP_TARGET', '/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B')
    draft = environment.get('SP_DRAFT', '/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2')
    tokenizer = AutoTokenizer.from_pretrained(target, local_files_only=True)
    requests = load_requests(6, SUITES, tokenizer)
    candidate_arms, config = arm_specs(['stock', 'final'], environment)
    null_arms, _ = arm_specs(['stock-a', 'stock-b'], environment)
    files = subprocess.check_output(['git', 'ls-files', '--', 'controller', 'exp', 'harness'], cwd=ROOT, text=True).splitlines()
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files if Path(name).suffix in ('.py', '.sh')}
    campaign = dict(directory=str(directory), campaign_id=directory.name, campaign_protocol_version=PROTOCOL,
        source_pin=expected, source_sha256=sources, started_unix=time.time(), requests=requests,
        suites=SUITES, rounds=2, per_suite=6, max_new_tokens=2048, warmup=2,
        full_scale_warmup=True, synchronized_start=True, raw_capture=True, ports=[30100, 30110],
        sampling=dict(temperature=0.0, top_k=1, enable_thinking=True),
        model_path=target, declared_models=config['models'], gpus=gpus,
        candidate_arms=candidate_arms, null_arms=null_arms,
        launch_protocol=dict(model_path=target, dtype='bfloat16', mem_fraction_static=.90,
            attention_backend='fa3', disable_radix_cache=True, random_seed=0, chunked_prefill_size=8192,
            enable_fp32_lm_head=False, speculative_draft_model_path=draft,
            mamba_ssm_dtype='float32', kv_cache_dtype='auto'),
        dev_sources={suite:hashlib.sha256((ROOT / 'assets/upstream/dev' / f'{suite}.jsonl').read_bytes()).hexdigest() for suite in SUITES},
        scope='author-product formal dev acceptance only; no ledger, sealed or independent discovery')
    campaign['protocol_id'] = measurement_protocol_id(campaign)
    return campaign


def run_session(directory, campaign, environment):
    directory.mkdir()
    arms = campaign['candidate_arms'] if directory.name == 'candidate' else campaign['null_arms']
    names = [arm['name'] for arm in arms]
    manifest = dict(campaign, arms=arms, head=campaign['source_pin'], started_unix=time.time())
    write_json(directory / 'manifest.json', manifest)
    pairs = []
    for number in (0, 1):
        check_ports(campaign['ports'])
        root = directory / f'round-{number + 1:02d}'
        def factory(name, url, **options):
            return CapturedArm(name, url, output_dir=root, **options)
        pairs.extend(run_round(arms, campaign['gpus'], campaign['ports'], number, campaign['requests'],
            root, environment, 2048, 2, 1200, stable_null=True, arm_factory=factory))
        wait_for_idle([0, 1])
    summary = summarize(pairs, campaign['requests'], 2, 10000)
    summary.update(arms=names, max_new_tokens=2048, per_suite_requested=6, completed_unix=time.time())
    write_json(directory / 'summary.json', summary)
    checked, _, _, _ = validate_session(directory, campaign)
    write_json(directory / 'session-validation.json', checked)
    print(json.dumps(dict(phase=directory.name, protocol_passed=True, interval=checked['interval'])), flush=True)


def score_campaign(directory, campaign, environment):
    reference, separate = correctness_reference(campaign)
    specifications, _ = arm_specs(['ar'], environment)
    arm = specifications[0]
    if arm['tree_sha'] != reference:
        raise ValueError('installed canonical scorer/AR engine differs from the declared reference')
    reference_arm = None
    if separate:
        specifications, _ = arm_specs(['stock'], environment)
        reference_arm = specifications[0]
        if reference_arm['tree_sha'] != reference or reference_arm['block'] != 8 or reference_arm.get('env'):
            raise ValueError('independent reference-stock must use the unchanged canonical engine')
    correctness = directory / 'correctness'
    correctness.mkdir()
    gpus = wait_for_idle([0, 1])
    check_ports([30120, 30130])
    with ExitStack() as resources:
        launch(arm, 'scorer', gpus[1], correctness, environment, resources)
        scorer = NativeClient('http://127.0.0.1:30130', correctness / 'scorer-raw')
        scorer.scorer_identity(arm['tree_sha'])
        head_process('preflight', correctness / 'head-preflight', directory, arm['tree_sha'])
        bench = Campaign(correctness, scorer, evidence_root=directory)
        with ExitStack() as generation:
            launch(arm, 'ar', gpus[0], correctness, environment, generation)
            client = NativeClient('http://127.0.0.1:30120', correctness / 'ar-raw')
            identity = client.server_identity(arm['tree_sha'])
            ar_paths, _, _ = bench.generate('ar', campaign['requests'], client, identity, 2048)
        check_ports([30120])
        wait_for_idle([0])
        reference_paths = None
        if separate:
            with ExitStack() as generation:
                launch(reference_arm, 'stock', gpus[0], correctness, environment, generation)
                client = NativeClient('http://127.0.0.1:30120', correctness / 'reference-stock-raw')
                identity = client.server_identity(reference)
                reference_paths, _, _ = bench.generate('reference-stock', campaign['requests'], client, identity, 2048)
            check_ports([30120])
            wait_for_idle([0])
        for number in (1, 2):
            root = directory / 'candidate' / f'round-{number:02d}'
            traces = {}
            for role in ('stock', 'final'):
                rows = [json.loads(line) for line in (root / f'{role}.jsonl').read_text().splitlines()]
                paths = []
                for row, request in zip(rows, campaign['requests']):
                    if row['id'] != request['id']:
                        raise ValueError('original timed request order changed before scoring')
                    paths.append(bench.save_trace(f'round-{number:02d}-{role}', request, row['output_ids'],
                                                 row['generator'], [row['raw_evidence']]))
                traces[role] = paths
            calibration_paths = reference_paths if separate else traces['stock']
            delta = calibrate_delta(calibration_paths, ar_paths, evidence_root=directory)
            calibration = calibrate_stock(calibration_paths, delta, evidence_root=directory)
            audits = bench.audit(f'round-{number:02d}-final', traces['final'], delta['delta'])
            verdict = judge_scored_forcing(calibration, traces['final'], evidence_root=directory, prefill_audits=audits)
            write_json(correctness / f'round-{number:02d}-delta.json', delta)
            write_json(correctness / f'round-{number:02d}-stock.json', calibration)
            write_json(correctness / f'round-{number:02d}-verdict.json', verdict)
            print(json.dumps(dict(phase='correctness', round=number, delta=delta['delta'],
                stock=calibration['stock_counts'], correctness_passed=verdict['correctness_passed'])), flush=True)
    check_ports([30120, 30130])
    write_json(correctness / 'cleanup.json', wait_for_idle([0, 1]))


def run(directory):
    directory.mkdir(parents=True, exist_ok=False)
    environment = clean_environment()
    signal.signal(signal.SIGTERM, interrupted)
    with ExitStack() as resources:
        gpus = wait_for_idle([0, 1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        campaign = build_campaign(directory, environment, gpus)
        write_json(directory / 'manifest.json', campaign)
        for phase in PHASES:
            run_session(directory / phase, campaign, environment)
        check_ports(campaign['ports'])
        write_json(directory / 'timing-cleanup.json', wait_for_idle([0, 1]))
        score_campaign(directory, campaign, environment)
        result = validate_campaign(directory)
        write_json(directory / 'joint-acceptance.json', result)
        check_ports(campaign['ports'] + [30120, 30130])
        write_json(directory / 'cleanup.json', wait_for_idle([0, 1]))
        print(json.dumps(dict(execution_complete=True, joint_acceptance_passed=result['joint_acceptance_passed'],
            interval=result['performance']['interval'], noise=result['noise_calibration']['noise'],
            threshold=result['performance']['threshold'], deltas=result['deltas'])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    directory = args.out_dir.resolve()
    if directory.exists():
        raise FileExistsError('refusing to reuse campaign output or resume a partial timing campaign')
    try:
        run(directory)
    except BaseException as error:
        if directory.exists():
            write_json(directory / 'failed.json', dict(error=repr(error), time_unix=time.time()))
            try:
                check_ports([30100, 30110, 30120, 30130])
                write_json(directory / 'failure-cleanup.json', wait_for_idle([0, 1]))
            except Exception as cleanup:
                write_json(directory / 'failure-cleanup-error.json', dict(error=repr(cleanup)))
        raise


if __name__ == '__main__':
    main()
