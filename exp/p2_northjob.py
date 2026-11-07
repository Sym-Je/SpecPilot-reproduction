import copy
import importlib
import json
import sys
from pathlib import Path


def with_model_mount(template):
    result = copy.deepcopy(template)
    tasks = result['spec']['tasks']
    if len(tasks) != 1 or tasks[0]['replicas'] != 1:
        raise ValueError('P2 smoke requires one node')
    pod = tasks[0]['template']['spec']
    container = pod['containers'][0]
    if str(container['resources']['limits'].get('nvidia.com/gpu')) != '2':
        raise ValueError('P2 smoke requires two H100 resource units')
    mounts = container.setdefault('volumeMounts', [])
    volumes = pod.setdefault('volumes', [])
    if any(mount['mountPath'] == '/gpfs/models' for mount in mounts):
        raise ValueError('model mount already exists')
    if any(volume['name'] == 'specpilot-models' for volume in volumes):
        raise ValueError('model volume already exists')
    volumes.append({'name': 'specpilot-models', 'persistentVolumeClaim': {
        'claimName': 'share-readonly', 'readOnly': True}})
    mounts.append({'name': 'specpilot-models', 'mountPath': '/gpfs/models',
                   'subPath': 'models', 'readOnly': True})
    return result


def validate_smoke(directory):
    directory = Path(directory)
    if (directory / 'failed.json').exists():
        raise ValueError('runner recorded a failure')
    summary = json.loads((directory / 'summary.json').read_text())
    expected = {'arms': ['stock', 'final'], 'rounds': 2, 'n_requests': 5,
                'n_pairs': 10, 'max_new_tokens': 64}
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError('unexpected smoke protocol or coverage')
    assignments = []
    request_sets = []
    for round_number in (1, 2):
        round_dir = directory / f'round-{round_number:02d}'
        complete = json.loads((round_dir / 'complete.json').read_text())
        if complete != {'round': round_number, 'pairs': 5}:
            raise ValueError('incomplete round')
        deployment = json.loads((round_dir / 'deployment.json').read_text())
        mapping = {item['arm']['name']: item['gpu']['uuid']
                   for item in deployment['assignments']}
        if set(mapping) != {'stock', 'final'} or len(set(mapping.values())) != 2:
            raise ValueError('invalid physical GPU assignment')
        assignments.append(mapping)
        pairs = [json.loads(line) for line in (round_dir / 'pairs.jsonl').read_text().splitlines()]
        request_ids = {pair['id'] for pair in pairs}
        if len(pairs) != 5 or len(request_ids) != 5 or len({pair['suite'] for pair in pairs}) != 5:
            raise ValueError('missing or duplicate request coverage')
        request_sets.append({pair['id']: pair['a']['input_sha256'] for pair in pairs})
        for key, arm in (('a', 'stock'), ('b', 'final')):
            rows = [json.loads(line) for line in (round_dir / f'{arm}.jsonl').read_text().splitlines()]
            if rows != [pair[key] for pair in pairs]:
                raise ValueError('arm records do not match canonical pairs')
            if any(row['arm'] != arm or row['gpu_uuid'] != mapping[arm] for row in rows):
                raise ValueError('arm GPU identity mismatch')
        if any(pair['a']['input_sha256'] != pair['b']['input_sha256'] for pair in pairs):
            raise ValueError('paired requests differ')
    if request_sets[0] != request_sets[1]:
        raise ValueError('request coverage changed across rounds')
    if assignments[0] != {'stock': assignments[1]['final'], 'final': assignments[1]['stock']}:
        raise ValueError('physical GPUs were not exchanged')
    return {'passed': True, 'scope': 'P2 lifecycle smoke only; not lossless or paper performance',
            'rounds': 2, 'pairs': 10, 'arm_rows': 20, 'physical_gpu_swap': True}


def main():
    if sys.argv[1:2] != ['create']:
        raise SystemExit('Use this adapter only for a P2 northjob create command')
    launcher = importlib.import_module('northmirror.launcher.create_job')
    cli = importlib.import_module('northmirror.launcher.northjob')
    original_builder = launcher.build_job_yaml

    def build_with_models(*arguments, **options):
        return with_model_mount(original_builder(*arguments, **options))

    launcher.build_job_yaml = build_with_models
    try:
        return cli.main()
    finally:
        launcher.build_job_yaml = original_builder


if __name__ == '__main__':
    main()
