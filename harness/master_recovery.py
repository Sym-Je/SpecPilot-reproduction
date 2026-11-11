"""One explicit proposal-protocol continuation with unchanged stage accounting."""

import json
from pathlib import Path

from exp.phase4_run import reference
from harness.engine_research import save
from harness import skill_rsi_audit as native


FILES = ('pipeline-result.json', 'profile-campaign-result.json', 'counters.json',
    'process-closure.json', 'master-proposal-stop.json')
LABEL = 'master-recovery-01'


def load(path):
    return json.loads(Path(path).read_text())


def prepare_recovery(root):
    root = Path(root).resolve()
    destination = root / 'proposal-recovery-01'
    if destination.exists() or (root / 'proposal-recovery.json').exists():
        raise ValueError('only one explicit proposal protocol continuation is allowed')
    pipeline = load(root / 'pipeline-result.json')
    counters = load(root / 'counters.json')
    state = load(root / 'resource-state.json')
    stop = load(root / 'master-proposal-stop.json')
    closure = load(root / 'process-closure.json')
    if (pipeline.get('status') != 'needs_attention' or pipeline.get('stages') != {} or
            list(root.glob('direction-*')) or (root / 'master-plan.json').exists() or
            (root / LABEL).exists() or pipeline.get('counters') != counters or
            pipeline.get('resource_state') != state or counters.get('gpu_attempts') != 0 or
            counters.get('controller_jobs') != 0 or
            stop.get('action', {}).get('kind') != 'finish' or
            pipeline.get('role_processes_closed') is not True or closure.get('role_processes_closed') is not True or
            set(pipeline.get('role_processes', {})) != {'master'} or
            any(not job.get('terminated') for job in state['jobs'])):
        raise ValueError('only a closed initial proposal stop can be continued')
    role, responses, origins = native.audit_role(root, root / 'master', allow_format_retries=True)
    if (any(counters[key] != role['counts'][key] for key in ('actions', 'cpu_runs', 'model_turns', 'usage_updates')) or
            not any(item['value'] == stop for item in responses.values())):
        raise ValueError('prior counters or stop differ from native Master evidence')
    destination.mkdir(mode=0o700)
    snapshots = {}
    for name in FILES:
        path = destination / name
        with path.open('xb') as output:
            output.write((root / name).read_bytes())
        snapshots[name] = reference(path)
    value = dict(schema='master-proposal-protocol-recovery-v1', master_label=LABEL,
        snapshots=snapshots, prior_counters=counters, prior_resource_state=state,
        remaining_master_actions=120-counters['actions'], remaining_master_cpu_runs=20-counters['cpu_runs'],
        provenance='maintainer protocol clarification; own-context replay into a new native thread, not independent discovery')
    if value['remaining_master_actions'] < 1 or value['remaining_master_cpu_runs'] < 0:
        raise ValueError('original Master allocation has no remaining actions')
    save(root / 'proposal-recovery.json', value)
    return verify_recovery(root)


def verify_recovery(root):
    root = Path(root).resolve()
    value = load(root / 'proposal-recovery.json')
    if value.get('schema') != 'master-proposal-protocol-recovery-v1' or value.get('master_label') != LABEL:
        raise ValueError('unrecognized proposal recovery identity')
    if set(value['snapshots']) != set(FILES):
        raise ValueError('incomplete original proposal stop snapshots')
    for name, identity in value['snapshots'].items():
        path = root / 'proposal-recovery-01' / name
        if path.is_symlink() or reference(path) != identity:
            raise ValueError('original proposal recovery snapshot changed')
    prior = load(value['snapshots']['pipeline-result.json']['path'])
    old = value['prior_resource_state']
    state = load(root / 'resource-state.json')
    counters = value['prior_counters']
    if (prior['counters'] != counters or prior['resource_state'] != old or
            load(value['snapshots']['counters.json']['path']) != counters or
            any(state[key] != old[key] for key in ('started', 'wall_seconds', 'gpu_seconds', 'concurrent_gpus')) or
            state['jobs'][:len(old['jobs'])] != old['jobs'] or
            value['remaining_master_actions'] != 120-counters['actions'] or
            value['remaining_master_cpu_runs'] != 20-counters['cpu_runs']):
        raise ValueError('proposal continuation reset original accounting')
    current = load(root / 'counters.json')
    if any(current[key] < counters[key] for key in counters):
        raise ValueError('proposal continuation reset cumulative counters')
    return value
