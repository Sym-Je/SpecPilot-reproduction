"""Adapter to the unchanged dev controller; final slot denotes an agent candidate."""

import json
from pathlib import Path
import time

from controller.dev_campaign import PHASES, PROTOCOL, validate_campaign, validate_session
from controller.paper_policy import measurement_protocol_id
from exp.candidate_smoke import CapturedArm
from exp.dev_campaign import score_campaign
from exp.engine_research import ROOT, ResearchServer, file_sha
from exp.p3_pair_run import SUITES, SETTING, check_ports, run_round, summarize, wait_for_idle, write_json


def run_gate(directory, record, spec, arms, gpus, requests, environment):
    if len(requests) != 30 or record['action']['max_new_tokens'] != 2048:
        raise ValueError('controller dev gate requires the registered thirty-request protocol')
    candidate_arms = [dict(arms[0]), dict(arms[1], name='final')]
    null_arms = [dict(arms[0], name=name, launch_arm='stock') for name in ('stock-a', 'stock-b')]
    config = json.loads(Path(spec['config_path']).read_text())
    sources = {path.relative_to(ROOT).as_posix(): file_sha(path)
        for prefix in ('controller', 'exp', 'harness') for path in (ROOT / prefix).rglob('*')
        if path.is_file() and path.suffix in ('.py', '.sh')}
    campaign = dict(directory=str(directory), campaign_id=directory.name, campaign_protocol_version=PROTOCOL,
        source_pin=record['source_pin'], source_sha256=sources, started_unix=time.time(), requests=requests,
        suites=SUITES, rounds=2, per_suite=6, max_new_tokens=2048, warmup=2,
        full_scale_warmup=True, synchronized_start=True, raw_capture=True, ports=[30100, 30110],
        sampling=dict(temperature=0.0, top_k=1, enable_thinking=True),
        model_path=spec['target'], declared_models=config['models'], gpus=gpus,
        candidate_arms=candidate_arms, null_arms=null_arms,
        launch_protocol=dict(model_path=spec['target'], dtype='bfloat16', mem_fraction_static=.90,
            attention_backend='fa3', disable_radix_cache=True, random_seed=0, chunked_prefill_size=8192,
            enable_fp32_lm_head=False, speculative_draft_model_path=spec['draft'],
            mamba_ssm_dtype='float32', kv_cache_dtype='auto'),
        dev_sources={suite:file_sha(ROOT / 'assets/upstream/dev' / f'{suite}.jsonl') for suite in SUITES},
        scope='agent startup-option dev gate; final is a schema slot, not author final',
        candidate_origin=dict(spec_sha256=spec['spec_sha256'], value=spec['value'], source='direction request'))
    campaign['protocol_id'] = measurement_protocol_id(campaign)
    write_json(directory / 'manifest.json', campaign)
    for phase in PHASES:
        phase_dir = directory / phase
        phase_dir.mkdir()
        selected = candidate_arms if phase == 'candidate' else null_arms
        write_json(phase_dir / 'manifest.json', dict(campaign, arms=selected,
            head=campaign['source_pin'], started_unix=time.time()))
        pairs = []
        for number in (0, 1):
            check_ports(campaign['ports'])
            root = phase_dir / f'round-{number + 1:02d}'
            def factory(name, url, **options):
                return CapturedArm(name, url, directory=root, spec=spec, **options)
            pairs.extend(run_round(selected, gpus, campaign['ports'], number, requests, root,
                environment, 2048, 2, 1200, stable_null=True, server_factory=ResearchServer, arm_factory=factory))
            wait_for_idle([0, 1])
        summary = summarize(pairs, requests, 2)
        summary.update(arms=[arm['name'] for arm in selected], max_new_tokens=2048,
            per_suite_requested=6, completed_unix=time.time())
        write_json(phase_dir / 'summary.json', summary)
        checked, _, _, _ = validate_session(phase_dir, campaign)
        write_json(phase_dir / 'session-validation.json', checked)
        print(json.dumps(dict(phase=phase, protocol_passed=True, interval=checked['interval'])), flush=True)
    write_json(directory / 'timing-cleanup.json', wait_for_idle([0, 1]))
    score_campaign(directory, campaign, environment)
    verdict = validate_campaign(directory)
    write_json(directory / 'joint-acceptance.json', verdict)
    write_json(directory / 'cleanup.json', wait_for_idle([0, 1]))
    result = dict(protocol='agent-startup-dev-gate-v1', controller_accepted=verdict['joint_acceptance_passed'],
        candidate_promoted=False, ledger_eligible=False, option_value=spec['value'],
        scope='registered independent dev gate, not sealed, author-final reproduction or algorithm discovery',
        controller_verdict=verdict, schema_final_slot='agent startup option, not author code')
    write_json(directory / 'result.json', result)
    return result
