"""Explicit paper-aligned readiness verdicts; never promote or write a ledger."""

import math
import hashlib
import json
from pathlib import Path

from controller.stats import stratified_geomean_ci


POLICY = 'paper-aligned-v1'


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(character in '0123456789abcdef' for character in value)


def record_digest(record):
    return hashlib.sha256(json.dumps({key: value for key, value in record.items() if key != 'evidence_sha256'},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def calibration_from_intervals(sessions, *, declared_sessions, protocol_id, campaign_id, policy):
    if policy != POLICY or not protocol_id or not campaign_id:
        raise ValueError('explicit policy, protocol and campaign identities are required')
    if (len(declared_sessions) < 2 or len(set(declared_sessions)) != len(declared_sessions) or
            [session.get('session_id') for session in sessions] != declared_sessions):
        raise ValueError('all predeclared distinct calibration sessions are required in order')
    results = []
    for session in sessions:
        if session.get('protocol_id') != protocol_id or not valid_digest(session.get('source_sha256')):
            raise ValueError('calibration protocol or raw evidence identity is missing')
        interval = session.get('interval', {})
        values = [interval.get(key) for key in ('lower', 'geomean', 'upper')]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError('invalid null interval')
        lower, estimate, upper = values
        if not lower <= estimate <= upper:
            raise ValueError('null interval is not ordered')
        width = upper - lower
        results.append(dict(session, noise=max(abs(lower - 1), abs(upper - 1)),
                            interval_width=width, precision_diagnostic=width < .002,
                            centered=lower <= 1 <= upper))
    result = dict(policy=policy, protocol_id=protocol_id, campaign_id=campaign_id,
                calibration_valid=True, noise=max(session['noise'] for session in results),
                noise_estimator='maximum distance from one of two-sided 95% null CI endpoints; max over predeclared sessions',
                sessions=results, ledger_eligible=False,
                scope='explicit readiness calibration; historical replay does not authorize retrospective promotion')
    return dict(result, declared_sessions=list(declared_sessions), evidence_sha256=record_digest(dict(result, declared_sessions=list(declared_sessions))))


def measurement_protocol_id(manifest):
    required = ('model_path', 'declared_models', 'sampling', 'requests', 'suites',
                'rounds', 'warmup', 'per_suite', 'max_new_tokens', 'gpus')
    if any(key not in manifest for key in required):
        raise ValueError('complete measurement protocol identity is required')
    protocol = {key: manifest[key] for key in required if key != 'gpus'}
    protocol['gpus'] = [{key: gpu[key] for key in ('index', 'uuid', 'name')} for gpu in manifest['gpus']]
    protocol.update(stable_null=manifest.get('stable_null', False), cpu_pinning=manifest.get('cpu_pinning', False))
    if 'campaign_protocol_version' in manifest:
        protocol.update({key: manifest[key] for key in
            ('campaign_protocol_version', 'full_scale_warmup', 'synchronized_start', 'raw_capture')})
    return record_digest(protocol)


def calibrate_null_runs(directories, *, declared_sessions, campaign_id, mode,
                       expected_protocol_id=None, expected_source_pin=None, campaign_started_unix=None, per_suite=4):
    from controller.null_validation import validate_null
    from controller.stability_validation import validate_stable

    if mode not in ('replay', 'current') or len(directories) != len(declared_sessions):
        raise ValueError('explicit replay/current mode and all declared runs required')
    if mode == 'current' and (not expected_protocol_id or not expected_source_pin or
                              type(campaign_started_unix) not in (int, float) or not math.isfinite(campaign_started_unix)):
        raise ValueError('current calibration needs a predeclared protocol, source and campaign start')
    sessions = []
    protocol_id = expected_protocol_id
    for identifier, directory in zip(declared_sessions, directories):
        directory = Path(directory).resolve()
        manifest = json.loads((directory / 'manifest.json').read_text())
        actual_protocol = measurement_protocol_id(manifest)
        protocol_id = protocol_id or actual_protocol
        if actual_protocol != protocol_id:
            raise ValueError('null run protocols differ')
        if mode == 'current' and (manifest['head'] != expected_source_pin or manifest['started_unix'] < campaign_started_unix):
            raise ValueError('historical or wrong-source run cannot calibrate the current campaign')
        if manifest.get('cpu_pinning'):
            from harness.cpu_affinity import validate_cpu_bound
            checked = validate_cpu_bound(directory)
        elif manifest.get('stable_null'):
            checked = validate_stable(directory)
        else:
            checked = validate_null(directory, rounds=manifest['rounds'], per_suite=per_suite)
        files = [directory / 'manifest.json', directory / 'summary.json']
        files += [path for number in range(1, manifest['rounds'] + 1)
                  for path in sorted((directory / f'round-{number:02d}').glob('*.json*'))]
        inventory = {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        sessions.append(dict(session_id=identifier, protocol_id=protocol_id, source_sha256=record_digest(inventory),
                             interval=checked['interval'], directory=str(directory)))
    result = calibration_from_intervals(sessions, declared_sessions=declared_sessions,
        protocol_id=protocol_id, campaign_id=campaign_id, policy=POLICY)
    result.update(historical_replay=mode == 'replay', current_campaign_usable=mode == 'current')
    result['evidence_sha256'] = record_digest(result)
    return result


def candidate_verdict(*, groups, calibration, correctness, protocol_id, campaign_id, output_identical):
    if (calibration.get('policy') != POLICY or calibration.get('calibration_valid') is not True or
            calibration.get('protocol_id') != protocol_id or calibration.get('campaign_id') != campaign_id):
        raise ValueError('candidate does not match its declared calibration campaign and protocol')
    if calibration.get('evidence_sha256') != record_digest(calibration) or calibration.get('historical_replay') is True:
        raise ValueError('calibration was altered or is only a historical replay')
    rechecked = calibration_from_intervals(calibration['sessions'], declared_sessions=calibration['declared_sessions'],
        protocol_id=protocol_id, campaign_id=campaign_id, policy=POLICY)
    if calibration['noise'] != rechecked['noise']:
        raise ValueError('calibration noise differs from all predeclared source intervals')
    noise = calibration.get('noise')
    if type(noise) not in (int, float) or not math.isfinite(noise) or noise < 0:
        raise ValueError('invalid calibrated noise')
    if type(output_identical) is not bool or not valid_digest(correctness.get('evidence_sha256')):
        raise ValueError('explicit output comparison and correctness evidence are required')
    interval = stratified_geomean_ci(groups)
    threshold = max(.01 + 2 * noise, 0 if output_identical else .03)
    performance = interval['lower'] - 1 > threshold
    correct = correctness.get('correctness_passed') is True
    return dict(policy=POLICY, interval=interval, threshold=threshold, noise=noise,
                performance_passed=performance, correctness_passed=correct,
                eligible_for_promotion=performance and correct, promoted=False, ledger_eligible=False,
                scope='pre-promotion readiness verdict; no campaign integration or ledger mutation')
