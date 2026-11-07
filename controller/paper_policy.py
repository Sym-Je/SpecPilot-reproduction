"""Explicit paper-aligned readiness verdicts; never promote or write a ledger."""

import math

from controller.stats import stratified_geomean_ci


POLICY = 'paper-aligned-v1'


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(character in '0123456789abcdef' for character in value)


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
    return dict(policy=policy, protocol_id=protocol_id, campaign_id=campaign_id,
                calibration_valid=True, noise=max(session['noise'] for session in results),
                noise_estimator='maximum distance from one of two-sided 95% null CI endpoints; max over predeclared sessions',
                sessions=results, ledger_eligible=False,
                scope='explicit readiness calibration; historical replay does not authorize retrospective promotion')


def candidate_verdict(*, groups, calibration, correctness, protocol_id, campaign_id, output_identical):
    if (calibration.get('policy') != POLICY or calibration.get('calibration_valid') is not True or
            calibration.get('protocol_id') != protocol_id or calibration.get('campaign_id') != campaign_id):
        raise ValueError('candidate does not match its declared calibration campaign and protocol')
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
