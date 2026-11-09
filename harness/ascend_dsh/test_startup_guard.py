import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import startup_guard as guard


class StartupGuardTests(unittest.TestCase):
    def test_requires_both_fatal_markers(self):
        for text in ('compiling', 'NPUGraph: ERROR', 'NPUModelRunner init failed'):
            self.assertIsNone(guard.fatal_graph_failure(text))
        self.assertIsNotNone(guard.fatal_graph_failure('NPUGraph: ERROR\nNPUModelRunner init failed'))

    def test_never_cancels_running_measurement_or_cleanup(self):
        state = {'status':'running','phase':'candidate_startup','lock_acquired_epoch':1,'candidate_owner':{'pid':1,'birth':1}}
        self.assertTrue(guard.eligible_state(state))
        for override in ({'status':'failed'},{'phase':'benchmark'},{'phase':'profile'},{'completed_epoch':2}):
            self.assertFalse(guard.eligible_state(state | override))

    def test_runner_requires_exact_id_path_and_birth(self):
        root = Path('/fixture'); argv = ['python', str(root/'experiment_runner.py'), '--id','owned']
        self.assertTrue(guard.valid_runner(argv,100,100,'owned',root))
        self.assertFalse(guard.valid_runner(argv,100,100,'someone-else',root))
        self.assertFalse(guard.valid_runner(argv,100,200,'owned',root))
        self.assertFalse(guard.valid_runner(['python','other.py','--id','owned'],100,100,'owned',root))

    def test_signal_is_idempotent_and_runs_existing_runner_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); directory = root/'experiments/owned';directory.mkdir(parents=True)
            state = {'status':'running','phase':'candidate_startup','lock_acquired_epoch':1,'candidate_owner':{'pid':2,'birth':2}}
            (directory/'state.json').write_text(json.dumps(state))
            result = {'runner_pid':1,'runner_birth':1,'experiment_id':'owned'}
            process = Mock(); process.create_time.return_value=1
            def inspect(folder, _): return None if (folder/'startup-failure-intervention.json').exists() else result
            with patch.object(guard,'inspect',side_effect=inspect),patch.object(guard.psutil,'Process',return_value=process):
                self.assertEqual(len(guard.scan(root,dry_run=True)),1)
                process.send_signal.assert_not_called()
                self.assertTrue(guard.scan(root)[0]['signal_sent'])
                self.assertEqual(guard.scan(root),[])
            self.assertEqual(process.send_signal.call_count,1)

    def test_reused_pid_is_never_signalled(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'experiments/owned';directory.mkdir(parents=True)
            (directory/'state.json').write_text(json.dumps({'status':'running','phase':'candidate_startup',
                'lock_acquired_epoch':1,'candidate_owner':{'pid':2,'birth':2}}))
            process=Mock();process.create_time.return_value=99
            with patch.object(guard,'inspect',return_value={'runner_pid':1,'runner_birth':1,'experiment_id':'owned'}), \
                 patch.object(guard.psutil,'Process',return_value=process):
                self.assertFalse(guard.scan(root)[0]['signal_sent'])
            process.send_signal.assert_not_called()


if __name__ == '__main__': unittest.main()
