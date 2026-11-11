import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from exp import codex_boundary
from exp.skill_rsi_continue import recorded_processes
from harness.research_shutdown import inspect_members, observe_shutdown, verify_observation


class ResearchShutdownTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.started = time.time()-1
        self.closure = {}
        with recorded_processes(self.root/'processes', self.closure):
            process=codex_boundary.subprocess.Popen([sys.executable,'-c','pass'])
            process.wait()
        self.write('process-closure.json', self.closure)
        self.write('resource-state.json', dict(started=self.started, wall_seconds=43200))
        self.write('campaign-recovery-exit-status', '1')

    def write(self, name, value):
        path=self.root/name
        path.write_text(value if isinstance(value,str) else json.dumps(value))

    def test_actual_birth_and_wait_are_verified_without_claiming_preopen_clearance(self):
        answer=inspect_members(self.root,self.closure)
        self.assertEqual(answer['verified_processes'],1)
        self.assertFalse(answer['phase4_preopen_clearance'])

    def test_exit_receipt_tampering_is_rejected(self):
        Path(self.closure['process_members'][0]['exit']['path']).write_text('{}')
        with self.assertRaises(ValueError):
            inspect_members(self.root,self.closure)

    def test_missing_process_receipt_is_rejected(self):
        self.closure['process_members']=[]
        with self.assertRaises(ValueError):
            inspect_members(self.root,self.closure)

    def test_live_recorded_identity_is_rejected(self):
        birth=json.loads(Path(self.closure['process_members'][0]['birth']['path']).read_text())
        with patch('harness.research_shutdown.identity',return_value=birth['identity']):
            with self.assertRaises(ValueError):
                inspect_members(self.root,self.closure)

    def test_observer_proof_is_recomputed_and_failure_preserved(self):
        proof=observe_shutdown(self.root)
        result=verify_observation(self.root,json.loads((self.root/'process-closure.json').read_text()))
        self.assertFalse(result['phase4_preopen_clearance'])
        self.assertEqual(result['verified_processes'],1)
        self.assertTrue(Path(proof['original_failure']['path']).exists())


if __name__ == '__main__':
    unittest.main()
