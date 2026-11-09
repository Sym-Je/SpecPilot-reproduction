import json
from pathlib import Path
import tempfile
import unittest

from harness.gpu_autonomy import digest, freeze_request, verify_request, require_cpu_debug, validate_allocation


class GpuIterationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / 'work'
        (self.work / 'scratch').mkdir(parents=True)
        (self.work / 'inputs').mkdir()
        (self.work / 'inputs/evidence.json').write_text('{}')
        for name in ('experiment.py', 'check.py'):
            (self.work / 'scratch' / name).write_text('print("fixture")')
        self.action = dict(kind='run_gpu_python', path='scratch/experiment.py', acceptance='scratch/check.py')

    def test_third_attempt_is_allowed_only_in_new_contract(self):
        request = self.root / 'request'
        manifest = freeze_request(self.work, self.action, request, attempts=2, contract='stage3-research')
        self.assertEqual(manifest['pod_deadline_seconds'], 900)
        self.assertEqual(manifest['reserved_gpu_seconds'], 2700)
        verify_request(request)
        for contract, attempts in [('legacy', 2), ('stage2-research', 2), ('stage3-research', 3)]:
            with self.assertRaises(ValueError):
                freeze_request(self.work, self.action, self.root / 'rejected', attempts=attempts, contract=contract)

    def test_cpu_guard_requires_success_and_current_code_identity(self):
        records = self.root / 'direction'
        path = records / 'tools-01/action-001/response.json'
        path.parent.mkdir(parents=True)
        with self.assertRaises(ValueError):
            require_cpu_debug(self.work, records, self.action)
        snapshot = {name: digest(self.work / name) for name in (self.action['path'], self.action['acceptance'])}
        for exit_code in (1, 0):
            response = dict(success=True, contentItems=[dict(type='inputText', text=json.dumps(dict(exit_code=exit_code, workspace_code_sha256=snapshot)))])
            path.write_text(json.dumps(response))
            if exit_code:
                with self.assertRaises(ValueError):
                    require_cpu_debug(self.work, records, self.action)
            else:
                self.assertEqual(require_cpu_debug(self.work, records, self.action)['receipt_sha256'], digest(path))
        (self.work / self.action['acceptance']).write_text('print("changed after CPU check")')
        with self.assertRaises(ValueError):
            require_cpu_debug(self.work, records, self.action)

    def test_master_reallocation_cannot_restore_spent_budget(self):
        from exp.gpu_autonomy import allocate_direction
        role = {}
        counters = dict(actions=20, cpu_runs=3, gpu_attempts=1)
        budget = dict(actions=25, cpu_runs=5, gpu_attempts=2)
        allocate_direction(role, budget, counters, 'stage3-research', 64)
        self.assertEqual(role, dict(actions=25, runs=5, gpu_attempts=3))
        for changed in (dict(budget, actions=45), dict(budget, cpu_runs=6), dict(budget, gpu_attempts=3)):
            with self.assertRaises(ValueError):
                allocate_direction(role, changed, counters, 'stage3-research', 64)
        with self.assertRaises(ValueError):
            validate_allocation(budget, 44)

    def test_deadline_adapter_accepts_fifteen_minutes_not_unbounded(self):
        from exp.history_northjob import with_model_mount
        template = dict(spec=dict(tasks=[dict(replicas=1, template=dict(spec=dict(containers=[dict(resources=dict(limits={'nvidia.com/gpu': 1}))])))]))
        result = with_model_mount(template, 900)
        self.assertEqual(result['spec']['tasks'][0]['template']['spec']['activeDeadlineSeconds'], 900)
        with self.assertRaises(ValueError):
            with_model_mount(template, 3600)


if __name__ == '__main__':
    unittest.main()
