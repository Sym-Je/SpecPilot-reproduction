from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp import p5_readiness_audit as audit


class ReadinessAuditTests(unittest.TestCase):
    def test_invalid_input_validation_is_distinct_from_a_crash(self):
        for error, expected in ((ValueError('empty'), True),
                                (OverflowError('too large'), False),
                                (RuntimeError('unexpected'), False)):
            with self.subTest(error=type(error).__name__):
                with patch.object(audit, 'judge_forcing', side_effect=error):
                    result = audit.forcing_probe('empty', [], [], 'reject')
                self.assertEqual(result['passed'], expected)
                self.assertEqual(result['observed']['exception'], type(error).__name__)

    def test_invalid_output_acceptance_is_reported_as_failure(self):
        fixture = SimpleNamespace(lossless=True, rate_flagged=False,
                                  to_dict=lambda: {'lossless': True})
        with patch.object(audit, 'judge_forcing', return_value=fixture):
            result = audit.forcing_probe('empty', [], [], 'reject')
        self.assertFalse(result['passed'])

    def test_rate_probe_checks_rate_separately_from_event_rejection(self):
        fixture = SimpleNamespace(lossless=False, rate_flagged=False,
                                  to_dict=lambda: {'event_flagged': True})
        with patch.object(audit, 'judge_forcing', return_value=fixture):
            result = audit.forcing_probe('rate', [[1]], [[2]], 'rate_flagged')
        self.assertFalse(result['passed'])

    def test_synthetic_promotion_probe_never_contacts_a_server(self):
        with patch.object(audit.Arm, 'step', side_effect=AssertionError('no HTTP')):
            result = audit.divergence_probe()
        self.assertEqual(result['observed']['ci']['lower'], 1.025)
        self.assertFalse(result['observed']['output_identical'])
        self.assertFalse(result['passed'])

    def test_null_probe_only_requests_a_nonexecuting_plan(self):
        with patch.object(audit, 'pair_args', return_value=SimpleNamespace(
                arms=['stock', 'stock'], execute=False)) as parse:
            result = audit.null_entrypoint_probe()
        self.assertTrue(result['passed'])
        self.assertNotIn('--execute', parse.call_args.args[0])

    def test_green_synthetic_checks_never_imply_real_readiness(self):
        fixture = {'name': 'fixture', 'passed': True}
        with patch.object(audit, 'forcing_probe', return_value=fixture), \
                patch.object(audit, 'divergence_probe', return_value=fixture), \
                patch.object(audit, 'null_entrypoint_probe', return_value=fixture):
            result = audit.audit()
        self.assertTrue(result['contract_checks_passed'])
        self.assertFalse(result['production_ready'])
        self.assertFalse(result['ledger_eligible'])
        self.assertEqual(result['gpu_tasks_submitted'], 0)
        self.assertTrue(result['real_evidence_pending'])

    def test_cli_refuses_to_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'audit.json'
            output.write_text('original evidence\n')
            with patch.object(audit, 'audit') as collect:
                with self.assertRaises(FileExistsError):
                    audit.main(['--out', str(output)])
            collect.assert_not_called()
            self.assertEqual(output.read_text(), 'original evidence\n')


if __name__ == '__main__':
    unittest.main()
