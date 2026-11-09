import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiment_lifecycle import cleanup_pending, finalized, visible_state, wait_final, failure_diagnostics
from gpt_handoff import experiment_receipts


class LifecycleTests(unittest.TestCase):
    def test_failure_is_not_terminal_until_cleanup_finishes(self):
        state = {'status': 'failed', 'lock_acquired_epoch': 1, 'error': 'fixture'}
        self.assertTrue(cleanup_pending(state)); self.assertFalse(finalized(state))
        view = visible_state(state)
        self.assertEqual(view['status'], 'restoring_baseline'); self.assertFalse(view['safe_to_advance'])
        self.assertEqual(state['status'], 'failed')
        state.update(completed_epoch=2, baseline_restored=True)
        self.assertTrue(finalized(state)); self.assertTrue(visible_state(state)['safe_to_advance'])

    def test_prelock_failure_is_terminal_but_restore_failure_cannot_advance(self):
        self.assertTrue(finalized({'status': 'failed', 'error': 'pin mismatch'}))
        state = {'status': 'failed', 'lock_acquired_epoch': 1, 'completed_epoch': 2, 'baseline_restored': False}
        self.assertTrue(finalized(state)); self.assertFalse(visible_state(state)['safe_to_advance'])

    def test_wait_does_not_return_first_failure_write(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'
            state = {'status': 'failed', 'lock_acquired_epoch': 1}
            path.write_text(json.dumps(state))
            def finish(_): path.write_text(json.dumps(dict(state, completed_epoch=2, baseline_restored=True)))
            with patch('experiment_lifecycle.time.sleep', side_effect=finish) as sleep:
                result = wait_final(path, timeout=10)
            self.assertEqual(sleep.call_count, 1)
            self.assertEqual(result['status'], 'failed'); self.assertTrue(result['safe_to_advance'])

    def test_wait_deadline_exposes_restoring_not_terminal_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'; path.write_text(json.dumps({'status': 'failed', 'lock_acquired_epoch': 1}))
            result = wait_final(path, timeout=0)
            self.assertEqual(result['status'], 'restoring_baseline'); self.assertTrue(result['cleanup_pending'])

    def test_scheduler_waits_for_restore_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); role = root / 'research/roles/test'; role.mkdir(parents=True)
            (role / 'broker-state.json').write_text(json.dumps({'actions': 21, 'experiments': ['owned']}))
            folder = root / 'experiments/owned'; folder.mkdir(parents=True)
            state = {'status': 'failed', 'lock_acquired_epoch': 1, 'error': 'original failure'}
            (folder / 'state.json').write_text(json.dumps(state))
            end = dict(state, completed_epoch=2, baseline_restored=True)
            with patch('gpt_handoff.wait_final', return_value=end) as wait:
                broker, evidence = experiment_receipts('test', root)
            self.assertEqual(wait.call_count, 1); self.assertEqual(broker['actions'], 21)
            self.assertEqual(evidence[0]['error'], 'original failure')
            (folder / 'state.json').write_text(json.dumps(dict(end, baseline_restored=False)))
            with self.assertRaisesRegex(AssertionError, 'Baseline restoration required'):
                experiment_receipts('test', root)

    def test_startup_diagnostic_is_bounded_and_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); (folder / 'candidate-service').mkdir()
            log = folder / 'candidate-service/server.log'
            log.write_text('ordinary context\n' + ('ERROR aclnnCumsum failed\n' * 100))
            (folder / 'startup-failure-intervention.json').write_text(json.dumps({'reason': 'confirmed graph failure'}))
            state = {'status': 'failed', 'phase': 'candidate_startup'}
            result = failure_diagnostics(folder, state)
            self.assertEqual(len(result['startup_error_evidence']['last_error_lines']), 24)
            self.assertEqual(result['operational_intervention']['reason'], 'confirmed graph failure')
            log.unlink(); log.symlink_to('/etc/passwd')
            self.assertNotIn('startup_error_evidence', failure_diagnostics(folder, state))


if __name__ == '__main__': unittest.main()
