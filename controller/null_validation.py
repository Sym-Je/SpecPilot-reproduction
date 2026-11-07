"""Validate real dual-server stock null sessions without promoting a candidate."""

import json
from pathlib import Path

from controller.stats import stratified_geomean_ci
from exp.p3_pair_run import arm_specs, clean_environment
from harness.baseline_validation import read_rows, validate_paired_run


def validate_null(directory):
    directory = Path(directory)
    names = ['stock-a', 'stock-b']
    expected_arms, _ = arm_specs(names, clean_environment())
    result, manifest, summary = validate_paired_run(directory, names, expected_arms)
    first_outputs = {}
    for round_number in (1, 2):
        round_dir = directory / f'round-{round_number:02d}'
        deployment = json.loads((round_dir / 'deployment.json').read_text())
        if [entry['arm'] for entry in deployment['assignments']] != manifest['arms']:
            raise ValueError('null deployment identity differs from manifest')
        for pair in read_rows(round_dir / 'pairs.jsonl'):
            output = pair['a']['output_sha256']
            if pair['b']['output_sha256'] != output:
                raise ValueError('stock null outputs differ across independent instances')
            if first_outputs.setdefault(pair['id'], output) != output:
                raise ValueError('stock null outputs differ across physical GPU assignments')
    groups = {}
    for request in manifest['requests']:
        groups.setdefault(request['suite'], []).append(
            summary['per_request_log_ratios'][request['id']])
    interval = stratified_geomean_ci(groups)
    width = interval['upper'] - interval['lower']
    noise = max(abs(interval['upper'] - 1), abs(1 - interval['lower']))
    result.update(interval=interval, interval_width=width, width_limit=.002,
                  noise=noise, precision_passed=width < .002,
                  output_identical=True, session_directory=str(directory.resolve()),
                  scope='real stock null calibration only; not lossless or promotion',
                  ledger_eligible=False)
    return result
