import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

from harness.master_recovery import prepare_recovery, verify_recovery
from exp.skill_rsi_continue import recorded_processes
from exp import codex_boundary


class MasterRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.counters = dict(actions=36, cpu_runs=14, model_turns=4, usage_updates=25,
            gpu_attempts=0, controller_jobs=0)
        self.state = dict(started=1000, wall_seconds=43200, gpu_seconds=28800,
            concurrent_gpus=2, jobs=[])
        self.write('resource-state.json', self.state)
        self.write('counters.json', self.counters)
        self.write('master-proposal-stop.json', dict(action=dict(kind='finish'), conclusion='Source protocol failure'))
        self.pipeline = dict(status='needs_attention', stages={}, counters=self.counters,
            resource_state=self.state, role_processes_closed=True,
            role_processes=dict(master=dict(pid=123, exit_code=0)))
        self.write('pipeline-result.json', self.pipeline)
        self.write('profile-campaign-result.json', self.pipeline)
        self.write('process-closure.json', dict(role_processes_closed=True, process_members=[]))
        self.write('master/turn-04-response.json', dict(action=dict(kind='finish'), conclusion='Source protocol failure'))
        self.role = dict(name='master', kind='Master', counts=self.counters)
        responses = {('thread', 4):dict(value=dict(action=dict(kind='finish'), conclusion='Source protocol failure'))}
        original = patch('harness.master_recovery.native.audit_role', return_value=(self.role, responses, {}))
        original.start()
        self.addCleanup(original.stop)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_recovery_preserves_prior_counters_and_budget(self):
        result = prepare_recovery(self.root)
        self.assertEqual(result['prior_counters'], self.counters)
        self.assertEqual(result['prior_resource_state'], self.state)
        self.assertEqual(verify_recovery(self.root), result)
        self.assertEqual(json.loads((self.root / 'pipeline-result.json').read_text()), self.pipeline)

    def test_second_recovery_is_rejected(self):
        prepare_recovery(self.root)
        with self.assertRaises(ValueError):
            prepare_recovery(self.root)

    def test_started_direction_cannot_be_replayed(self):
        (self.root / 'direction-d1').mkdir()
        with self.assertRaises(ValueError):
            prepare_recovery(self.root)

    def test_non_stop_failure_is_not_a_protocol_continuation(self):
        self.write('master-proposal-stop.json', dict(action=dict(kind='run_source')))
        with self.assertRaises(ValueError):
            prepare_recovery(self.root)

    def test_snapshot_tampering_is_rejected(self):
        result = prepare_recovery(self.root)
        Path(result['snapshots']['counters.json']['path']).write_text('{}')
        with self.assertRaises(ValueError):
            verify_recovery(self.root)

    def test_budget_reset_is_rejected(self):
        prepare_recovery(self.root)
        self.write('resource-state.json', dict(self.state, started=2000))
        with self.assertRaises(ValueError):
            verify_recovery(self.root)

    def test_counter_reset_is_rejected(self):
        self.write('counters.json', dict(self.counters, actions=0))
        with self.assertRaises(ValueError):
            prepare_recovery(self.root)

    def test_new_process_inventory_keeps_old_exit_receipts(self):
        first = {}
        with recorded_processes(self.root / 'processes', first):
            process = codex_boundary.subprocess.Popen([sys.executable, '-c', 'pass'])
            process.wait()
        second = {}
        with recorded_processes(self.root / 'processes/recovery', second,
                prior_members=first['process_members']):
            process = codex_boundary.subprocess.Popen([sys.executable, '-c', 'pass'])
            process.wait()
        self.assertTrue(second['role_processes_closed'])
        self.assertEqual(len(second['process_members']), 2)
        self.assertEqual(second['process_members'][0], first['process_members'][0])
        registry = json.loads(Path(second['shutdown_registry']['path']).read_text())
        self.assertEqual(registry['members'], second['process_members'][1:])

    def test_unregistered_extra_master_is_rejected(self):
        from harness.profile_autonomy_audit import master_directories
        (self.root / 'master-recovery-01').mkdir()
        with self.assertRaises(ValueError):
            master_directories(self.root)


if __name__ == '__main__':
    unittest.main()
