"""Trusted request freezing and receipts, separate from scientific acceptance."""

import hashlib
import json
from pathlib import Path

from harness.experiment_executor import local_path

CONTRACTS = {'legacy': (1560, 7200), 'stage2-preflight': (600, 3600), 'stage2-research': (1200, 3600), 'stage3-research': (900, 3600)}


def research_limits(contract):
    if contract not in CONTRACTS:
        raise ValueError('unknown resource contract')
    if contract == 'stage3-research':
        return dict(model_turns=24, cpu_runs=8, gpu_attempts=3, usage_updates=128)
    return dict(model_turns=16, cpu_runs=4, gpu_attempts=2, usage_updates=64)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def response_object(content):
    content = content.strip()
    if content.startswith('```json\n') and content.endswith('```'):
        content = content[8:-3].strip()
    try:
        value = json.loads(content)
    except (ValueError, TypeError) as error:
        raise ValueError('one complete JSON response required') from error
    if not isinstance(value, dict):
        raise ValueError('response object required')
    return value


def validate_allocation(budget, remaining_actions, *, contract='legacy', remaining_cpu=None, remaining_gpu=None):
    stage = research_limits(contract)
    limits = dict(actions=remaining_actions,
        cpu_runs=stage['cpu_runs'] if remaining_cpu is None else min(remaining_cpu, stage['cpu_runs']),
        gpu_attempts=stage['gpu_attempts'] if remaining_gpu is None else min(remaining_gpu, stage['gpu_attempts']))
    if not isinstance(budget, dict) or set(budget) != set(limits):
        raise ValueError('master allocation fields required')
    for name, limit in limits.items():
        if type(budget[name]) is not int or not 0 <= budget[name] <= limit:
            raise ValueError('master allocation exceeds trusted ceiling')
    if budget['actions'] < 1:
        raise ValueError('at least one research action required')


def freeze_request(work, action, output, *, attempts, contract='legacy'):
    if contract not in CONTRACTS:
        raise ValueError('unknown resource contract')
    pod_deadline, stage_ceiling = CONTRACTS[contract]
    if contract == 'stage2-preflight' and attempts != 0:
        raise ValueError('only one dependency preflight allowed')
    if type(attempts) is not int or not 0 <= attempts < research_limits(contract)['gpu_attempts']:
        raise ValueError('GPU attempt ceiling reached')
    if not isinstance(action, dict) or set(action) != {'kind', 'path', 'acceptance'} or action['kind'] != 'run_gpu_python':
        raise ValueError('bounded GPU action required; role cannot grant authority')
    work = Path(work).resolve()
    for name in (action['path'], action['acceptance']):
        path = local_path(work, name)
        if not name.startswith('scratch/') or path.suffix != '.py' or not path.is_file() or path.stat().st_size > 32768:
            raise ValueError('bounded scratch Python script required')
    if action['path'] == action['acceptance']:
        raise ValueError('separate experimental screening script required')
    payloads = {}
    for path in (work / 'scratch').rglob('*'):
        if path.is_symlink():
            raise ValueError('symlinks cannot enter GPU workspace')
        if path.is_file():
            name = path.relative_to(work).as_posix()
            payloads[name] = local_path(work, name).read_bytes()
    evidence = work / 'inputs/evidence.json'
    if evidence.is_symlink():
        raise ValueError('immutable evidence must be a regular file')
    payloads['inputs/evidence.json'] = evidence.read_bytes()
    if len(payloads) > 17 or sum(map(len, payloads.values())) > 1048576:
        raise ValueError('GPU input bundle exceeds limit')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, content in payloads.items():
        destination = output / 'work' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    manifest = dict(schema='agent-gpu-script-v1', script=action['path'], acceptance=action['acceptance'],
        script_sha256=hashlib.sha256(payloads[action['path']]).hexdigest(),
        files={name: hashlib.sha256(content).hexdigest() for name, content in sorted(payloads.items())},
        attempt=attempts + 1, gpus=1, pod_deadline_seconds=pod_deadline, script_wall_seconds=180,
        total_stage_gpu_seconds_ceiling=stage_ceiling, reserved_gpu_seconds=(attempts + 1) * pod_deadline,
        controller_accepted=False, scope='agent-owned screening; not paired performance or promotion')
    if contract != 'legacy':
        manifest['resource_contract'] = contract
    (output / 'request.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


def verify_request(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'request.json').read_text())
    contract = manifest.get('resource_contract', 'legacy')
    if contract not in CONTRACTS:
        raise ValueError('unknown resource contract')
    deadline, ceiling = CONTRACTS[contract]
    if manifest['schema'] != 'agent-gpu-script-v1' or manifest['gpus'] != 1 or manifest['pod_deadline_seconds'] != deadline:
        raise ValueError('GPU contract changed')
    if manifest['total_stage_gpu_seconds_ceiling'] != ceiling or manifest['script_wall_seconds'] != 180:
        raise ValueError('GPU resource ceiling changed')
    if type(manifest['attempt']) is not int or not 1 <= manifest['attempt'] <= (1 if contract == 'stage2-preflight' else research_limits(contract)['gpu_attempts']):
        raise ValueError('GPU attempt ceiling changed')
    if manifest['reserved_gpu_seconds'] != manifest['attempt'] * deadline or manifest['controller_accepted'] is not False:
        raise ValueError('GPU reservation or authority changed')
    for name, expected in manifest['files'].items():
        if digest(local_path(directory / 'work', name)) != expected:
            raise ValueError('frozen agent input changed: ' + name)
    if manifest['script_sha256'] != manifest['files'][manifest['script']]:
        raise ValueError('script identity changed')
    return manifest


def require_cpu_debug(work, records, action):
    work = Path(work)
    expected = {name: digest(work / name) for name in (action['path'], action['acceptance'])}
    for path in Path(records).glob('tools-*/action-*/response.json'):
        response = json.loads(path.read_text())
        value = json.loads(response['contentItems'][0]['text'])
        snapshot = value.get('workspace_code_sha256', {})
        if response['success'] and value.get('exit_code') == 0 and all(snapshot.get(name) == identity for name, identity in expected.items()):
            return dict(receipt=str(path), receipt_sha256=digest(path), scientific_code_sha256=expected)
    raise ValueError('run a successful research CPU self-check after the current scientific code was written')


def job_rows(content, name):
    for position, character in enumerate(content):
        if character != '{':
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(content[position:])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get('data'), list) and type(value.get('total')) is int:
            if value['total'] > 100:
                raise ValueError('job query is incomplete')
            return [row for row in value['data'] if row.get('user_def_name') == name]
    raise ValueError('no complete native job-query response')
