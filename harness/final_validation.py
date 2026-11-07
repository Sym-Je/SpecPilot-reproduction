import hashlib
import json
import os
from pathlib import Path

from exp.p3_pair_run import ROOT, SETTING
from harness.baseline_validation import validate_baseline, validate_paired_run


def final_identity():
    config = json.loads((ROOT / 'assets/upstream/configs' / SETTING / 'config.json').read_text())
    data = Path(os.environ.get('SPECPILOT_DATA', '/gpfs/users/jixinpeng/specpilot_data'))
    tree_sha = (data / 'work/engines' / f'{SETTING}-final' / 'TREE_SHA').read_text().strip()
    if len(tree_sha) != 64 or any(character not in '0123456789abcdef' for character in tree_sha):
        raise ValueError('invalid final tree SHA')
    if config['final']['block_size'] != 32 or len(config['final']['env']) != 46:
        raise ValueError('unexpected final configuration')
    return config, tree_sha


def validate_final(directory, reference_directory):
    reference_directory = Path(reference_directory)
    if not validate_baseline(reference_directory)['diagnostic_passed']:
        raise ValueError('A1 baseline diagnostic did not pass')
    reference_path = reference_directory / 'manifest.json'
    reference = json.loads(reference_path.read_text())
    manifest = json.loads((Path(directory) / 'manifest.json').read_text())
    names = [arm['name'] for arm in manifest['arms']]
    if names not in (['ar', 'final'], ['stock', 'final']):
        raise ValueError('expected AR/final or direct stock/final')
    for field in ('model_path', 'declared_models', 'sampling', 'suites'):
        if manifest.get(field) != reference.get(field):
            raise ValueError(f'{field} differs from the frozen baseline')
    config, tree_sha = final_identity()
    expected = [{'name': names[0], 'block': 0 if names[0] == 'ar' else config['stock']['block_size'],
                 'tree_sha': reference['arms'][0]['tree_sha'], 'env': {}},
                {'name': 'final', 'block': config['final']['block_size'],
                 'tree_sha': tree_sha, 'env': config['final']['env']}]
    result, manifest, summary = validate_paired_run(
        directory, names, expected_arms=expected, reference_requests=reference['requests'])
    if 'acceptance' in summary:
        raise ValueError('final comparisons must not inherit an unrelated numeric gate')
    result.update(comparison=f'final/{names[0]}', baseline_requests_match=True,
                  baseline_manifest_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                  final_env_options=len(config['final']['env']),
                  performance_gate='no numeric gate defined for this dev subset',
                  scope='A2/A3 direct paired dev diagnostic; not sealed, lossless or promotion')
    return result
