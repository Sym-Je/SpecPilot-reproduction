import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.gpu_autonomy import freeze_request, verify_request


class GpuStageTests(unittest.TestCase):
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

    def test_new_contracts_have_exact_deadlines_and_no_expansion(self):
        for contract, deadline in [('legacy', 1560), ('stage2-preflight', 600), ('stage2-research', 1200)]:
            request = self.root / contract
            manifest = freeze_request(self.work, self.action, request, attempts=0, contract=contract)
            self.assertEqual(manifest['pod_deadline_seconds'], deadline)
            verify_request(request)
            for field, value in [('pod_deadline_seconds', deadline+1), ('total_stage_gpu_seconds_ceiling', 99999),
                    ('reserved_gpu_seconds', 0), ('attempt', 3), ('controller_accepted', True)]:
                altered = dict(manifest, **{field: value})
                (request / 'request.json').write_text(json.dumps(altered))
                with self.subTest(contract=contract, field=field), self.assertRaises(ValueError):
                    verify_request(request)

    def test_preflight_cannot_be_repeated_or_unknown_contract_created(self):
        for contract, attempts in [('stage2-preflight', 1), ('unknown', 0)]:
            with self.assertRaises(ValueError):
                freeze_request(self.work, self.action, self.root / 'rejected', attempts=attempts, contract=contract)
        self.assertFalse((self.root / 'rejected').exists())

    def test_deadline_adapter_preserves_readonly_mount_and_original(self):
        from exp.history_northjob import with_model_mount
        template = dict(spec=dict(tasks=[dict(replicas=1, template=dict(spec=dict(containers=[dict(resources=dict(limits={'nvidia.com/gpu': 1}))])))]))
        before = copy.deepcopy(template)
        for deadline in (600, 1200, 1560):
            result = with_model_mount(template, deadline)
            pod = result['spec']['tasks'][0]['template']['spec']
            self.assertEqual(pod['activeDeadlineSeconds'], deadline)
            self.assertTrue(pod['containers'][0]['volumeMounts'][0]['readOnly'])
        self.assertEqual(template, before)
        for deadline in (3600, True, 0):
            with self.assertRaises(ValueError):
                with_model_mount(template, deadline)

    def test_new_phase_requires_successful_preflight_and_preserves_prior_counts(self):
        from exp.gpu_autonomy import continuation_state
        prior = self.root / 'prior'
        prior.mkdir()
        original = dict(master_review=dict(decision='stop'), counters=dict(model_turns=16, actions=26, cpu_runs=2, gpu_attempts=2, usage_updates=36))
        (prior / 'result.json').write_text(json.dumps(original))
        preflight = self.root / 'preflight'
        preflight.mkdir()
        proof = dict(status='failed', gpu_test_passed=True, boundary_passed=True, immutable_inputs=True, canary_unchanged=True)
        (preflight / 'result.json').write_text(json.dumps(proof))
        destination = self.root / 'new-phase'
        destination.mkdir()
        with self.assertRaises(ValueError):
            continuation_state(destination, prior, preflight)
        proof['status'] = 'completed'
        (preflight / 'result.json').write_text(json.dumps(proof))
        with patch('harness.gpu_autonomy_audit.audit') as audit:
            self.assertEqual(continuation_state(destination, prior, preflight), original)
            audit.assert_called_once_with(prior)
        state = json.loads((destination / 'continuation.json').read_text())
        self.assertEqual(state['prior_counters'], original['counters'])
        self.assertTrue(all(value == 0 for value in state['new_phase_counters'].values()))
        self.assertEqual(json.loads((prior / 'result.json').read_text()), original)

    def test_zero_action_stop_has_empty_feedback_without_rewriting_history(self):
        from exp.gpu_autonomy import read_feedback
        self.assertEqual(read_feedback(self.root), [])
        self.assertFalse((self.root / 'feedback.json').exists())
        (self.root / 'feedback.json').write_text('[{"status":"fixture"}]')
        self.assertEqual(read_feedback(self.root), [{'status': 'fixture'}])

    def test_trusted_preload_only_uses_fixed_installed_module_not_agent_path(self):
        from harness.gpu_script_worker import preload_gpu_runtime
        from types import SimpleNamespace
        library = self.root / 'installed/flash_attn.py'
        library.parent.mkdir()
        library.write_text('trusted fixture')
        with patch('harness.gpu_script_worker.sys.prefix', str(library.parent)), \
                patch('harness.gpu_script_worker.importlib.import_module', return_value=SimpleNamespace(__file__=str(library))) as loader:
            self.assertEqual(preload_gpu_runtime()['module'], 'sgl_kernel.flash_attn')
            loader.assert_called_once_with('sgl_kernel.flash_attn')
        with patch('harness.gpu_script_worker.sys.prefix', str(self.root / 'other')), \
                patch('harness.gpu_script_worker.importlib.import_module', return_value=SimpleNamespace(__file__=str(library))), \
                self.assertRaisesRegex(RuntimeError, 'trusted installed'):
            preload_gpu_runtime()


if __name__ == '__main__':
    unittest.main()
