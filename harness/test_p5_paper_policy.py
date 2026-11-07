import copy
import math
import unittest


class PaperPolicyTests(unittest.TestCase):
    def intervals(self):
        return [{'session_id': 'one', 'protocol_id': 'protocol', 'source_sha256': 'a' * 64,
                 'interval': {'geomean': 1.002, 'lower': 1.001, 'upper': 1.003}},
                {'session_id': 'two', 'protocol_id': 'protocol', 'source_sha256': 'b' * 64,
                 'interval': {'geomean': 1, 'lower': .997, 'upper': 1.0035}}]

    def calibrate(self, sessions=None):
        from controller.paper_policy import calibration_from_intervals
        return calibration_from_intervals(self.intervals() if sessions is None else sessions,
            declared_sessions=['one', 'two'], protocol_id='protocol', campaign_id='campaign',
            policy='paper-aligned-v1')

    def test_wide_or_shifted_null_is_reported_not_a_paper_width_failure(self):
        result = self.calibrate()
        self.assertTrue(result['calibration_valid'])
        self.assertAlmostEqual(result['noise'], .0035)
        self.assertFalse(result['sessions'][0]['centered'])
        self.assertGreater(result['sessions'][1]['interval_width'], .002)
        self.assertFalse(result['ledger_eligible'])

    def test_missing_duplicate_wrong_protocol_or_nonfinite_evidence_is_rejected(self):
        invalid = [self.intervals()[:1], [self.intervals()[0]] * 2]
        for change in ('protocol', 'nonfinite', 'source'):
            sessions = self.intervals()
            if change == 'protocol': sessions[1]['protocol_id'] = 'other'
            if change == 'nonfinite': sessions[1]['interval']['upper'] = math.inf
            if change == 'source': sessions[1]['source_sha256'] = ''
            invalid.append(sessions)
        for sessions in invalid:
            with self.subTest(sessions=sessions), self.assertRaises(ValueError): self.calibrate(sessions)

    def test_correctness_and_matching_calibration_are_required_for_candidate_verdict(self):
        from controller.paper_policy import candidate_verdict
        options = dict(groups={'suite': [math.log(1.04)] * 4}, calibration=self.calibrate(),
                       correctness={'correctness_passed': False, 'evidence_sha256': 'c' * 64},
                       protocol_id='protocol', campaign_id='campaign', output_identical=False)
        result = candidate_verdict(**options)
        self.assertFalse(result['eligible_for_promotion'])
        options['correctness']['correctness_passed'] = True
        result = candidate_verdict(**options)
        self.assertTrue(result['eligible_for_promotion'])
        self.assertAlmostEqual(result['threshold'], .03)
        self.assertFalse(result['promoted'])
        options['protocol_id'] = 'other'
        with self.assertRaises(ValueError): candidate_verdict(**options)

    def test_noise_cannot_be_replaced_by_a_smaller_number(self):
        from controller.paper_policy import candidate_verdict
        calibration = self.calibrate()
        calibration['noise'] = 0
        with self.assertRaises(ValueError):
            candidate_verdict(groups={'suite': [math.log(1.04)] * 4}, calibration=calibration,
                correctness={'correctness_passed': True, 'evidence_sha256': 'c' * 64},
                protocol_id='protocol', campaign_id='campaign', output_identical=True)
