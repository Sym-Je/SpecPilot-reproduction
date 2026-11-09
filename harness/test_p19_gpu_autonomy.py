import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class GpuAutonomyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / 'role'
        (self.work / 'scratch').mkdir(parents=True)
        (self.work / 'inputs').mkdir()
        (self.work / 'inputs/evidence.json').write_text('{"fixture":true}')
        (self.work / 'scratch/experiment.py').write_text('print("fixture")')
        (self.work / 'scratch/check.py').write_text('print("screen only")')
        self.action = dict(kind='run_gpu_python', path='scratch/experiment.py', acceptance='scratch/check.py')

    def test_freeze_binds_original_script_and_inputs(self):
        from harness.gpu_autonomy import freeze_request
        request = freeze_request(self.work, self.action, self.root / 'request', attempts=0)
        digest = hashlib.sha256(b'print("fixture")').hexdigest()
        self.assertEqual(request['script_sha256'], digest)
        (self.work / 'scratch/experiment.py').write_text('print("changed")')
        self.assertEqual((self.root / 'request/work/scratch/experiment.py').read_text(), 'print("fixture")')
        self.assertFalse(request['controller_accepted'])

    def test_exhausted_gpu_budget_creates_no_request(self):
        from harness.gpu_autonomy import freeze_request
        with self.assertRaises(ValueError):
            freeze_request(self.work, self.action, self.root / 'request', attempts=2)
        self.assertFalse((self.root / 'request').exists())

    def test_unknown_fields_and_paths_cannot_grant_authority(self):
        from harness.gpu_autonomy import freeze_request
        for action in (dict(self.action, approved=True), dict(self.action, path='../outside.py'),
                dict(self.action, kind='shell'), dict(self.action, path='/absolute.py')):
            with self.subTest(action=action), self.assertRaises(ValueError):
                freeze_request(self.work, action, self.root / 'request', attempts=0)

    def test_symlinks_and_large_files_are_rejected(self):
        from harness.gpu_autonomy import freeze_request
        outside = self.root / 'outside.txt'
        outside.write_text('nonsecret fixture')
        (self.work / 'scratch/alias.txt').symlink_to(outside)
        with self.assertRaises(ValueError):
            freeze_request(self.work, self.action, self.root / 'request', attempts=0)
        (self.work / 'scratch/alias.txt').unlink()
        (self.work / 'scratch/experiment.py').write_text('x' * 32769)
        with self.assertRaises(ValueError):
            freeze_request(self.work, self.action, self.root / 'request', attempts=0)

    def test_frozen_request_audit_detects_code_changes(self):
        from harness.gpu_autonomy import freeze_request, verify_request
        freeze_request(self.work, self.action, self.root / 'request', attempts=0)
        verify_request(self.root / 'request')
        (self.root / 'request/work/scratch/check.py').write_text('print("forged")')
        with self.assertRaises(ValueError):
            verify_request(self.root / 'request')

    def test_job_query_requires_complete_exact_name_match(self):
        from harness.gpu_autonomy import job_rows
        text = json.dumps(dict(total=2, data=[dict(user_def_name='target', job_uuid='one'),
            dict(user_def_name='target-extra', job_uuid='two')]))
        self.assertEqual(job_rows(text, 'target')[0]['job_uuid'], 'one')
        with self.assertRaises(ValueError):
            job_rows(json.dumps(dict(total=101, data=[])), 'target')
        with self.assertRaises(ValueError):
            job_rows('timeout, no JSON', 'target')

    def test_model_response_requires_one_structured_action(self):
        from harness.gpu_autonomy import response_object
        self.assertEqual(response_object('{"action":{"kind":"finish"}}')['action']['kind'], 'finish')
        self.assertEqual(response_object('```json\n{"passed":false}\n```'), dict(passed=False))
        for content in ('{"a":1}{"b":2}', 'I claim success', '[1,2]'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                response_object(content)

    def test_cpu_probe_exercises_actual_gpu_script_boundary(self):
        worker = Path(__file__).with_name('gpu_script_worker.py')
        canary = self.root / 'protected.txt'
        canary.write_text('nonsecret protected fixture')
        payload = dict(work=str(self.work), program='scratch/experiment.py', canary=str(canary),
            stock=None, models=[], cpu_probe=True)
        result = subprocess.run([sys.executable, '-I', '-B', str(worker)], input=json.dumps(payload),
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        proof = json.loads(result.stderr.splitlines()[0])
        self.assertTrue(all(proof['boundary_checks'].values()), proof)
        self.assertTrue(proof['kernel_boundary_applied'])
        self.assertIn('fixture', result.stdout)
        self.assertEqual(canary.read_text(), 'nonsecret protected fixture')

    def test_script_failure_does_not_run_acceptance_or_claim_gpu(self):
        from harness.gpu_autonomy import response_object
        self.assertNotIn('controller_accepted', response_object('{"status":"failed"}'))
        worker = Path(__file__).with_name('gpu_script_worker.py')
        (self.work / 'scratch/experiment.py').write_text('raise RuntimeError("agent must fix this")')
        canary = self.root / 'protected.txt'
        canary.write_text('nonsecret fixture')
        payload = dict(work=str(self.work), program='scratch/experiment.py', canary=str(canary),
            stock=None, models=[], cpu_probe=True)
        result = subprocess.run([sys.executable, '-I', '-B', str(worker)], input=json.dumps(payload),
            capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('agent must fix this', result.stderr)

    def test_master_cannot_expand_resource_or_action_budget(self):
        from harness.gpu_autonomy import validate_allocation
        validate_allocation(dict(actions=8, cpu_runs=2, gpu_attempts=1), 10)
        for budget in (dict(actions=11, cpu_runs=2, gpu_attempts=1),
                dict(actions=8, cpu_runs=2, gpu_attempts=3), dict(actions=8, cpu_runs=True, gpu_attempts=1)):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                validate_allocation(budget, 10)

    def test_missing_real_gpu_cannot_pass_strict_autonomy_audit(self):
        from harness.gpu_autonomy_audit import audit
        (self.root / 'result.json').write_text(json.dumps(dict(status='no_gpu_feedback')))
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_direction_exhaustion_does_not_erase_unallocated_stage_budget(self):
        from exp.gpu_autonomy import gpu_request
        role = dict(actions=0, gpu_attempts=1)
        counters = dict(actions=21, gpu_attempts=0)
        with self.assertRaisesRegex(ValueError, 'stage remaining actions=3; only master'):
            gpu_request(self.root, role, self.action, counters)
        self.assertEqual(counters, dict(actions=21, gpu_attempts=0))

    def test_legacy_usage_guard_remains_default_and_runtime_can_bound_research(self):
        import io
        from unittest.mock import patch
        from exp.codex_boundary import Client
        message = json.dumps(dict(method='thread/tokenUsage/updated')) + '\n'
        for ceiling, should_raise in ((None, True), (32, False)):
            client = Client.__new__(Client)
            client.process = type('ProcessFixture', (), dict(stdout=io.BytesIO(message.encode())))()
            client.wire = io.StringIO()
            client.events = []
            client.usage_updates = 12
            if ceiling is not None:
                client.usage_update_ceiling = ceiling
            with patch('exp.codex_boundary.select.select', return_value=([client.process.stdout], [], [])):
                if should_raise:
                    with self.assertRaises(RuntimeError):
                        client.receive()
                else:
                    client.receive()
                    self.assertEqual(client.usage_updates, 13)

    def test_private_cache_writable_but_inputs_still_readonly(self):
        (self.work / '.cache').mkdir()
        (self.work / 'cache').mkdir()
        (self.work / 'scratch/experiment.py').write_text('from pathlib import Path; Path(".cache/probe.txt").write_text("allowed cache")')
        canary = self.root / 'protected.txt'
        canary.write_text('nonsecret fixture')
        worker = Path(__file__).with_name('gpu_script_worker.py')
        payload = dict(work=str(self.work), program='scratch/experiment.py', canary=str(canary),
            stock=None, models=[], cpu_probe=True)
        result = subprocess.run([sys.executable, '-I', '-B', str(worker)], input=json.dumps(payload),
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.work / '.cache/probe.txt').read_text(), 'allowed cache')
        self.assertTrue(json.loads(result.stderr.splitlines()[0])['boundary_checks']['rules_write'])

    def test_gpu_runtime_read_grant_does_not_allow_write_or_sibling_access(self):
        runtime = self.root / 'cuda-runtime'
        runtime.mkdir()
        library = runtime / 'libcudart.fixture'
        library.write_text('nonsecret runtime fixture')
        canary = self.root / 'protected.txt'
        canary.write_text('nonsecret protected fixture')
        (self.work / 'cache').mkdir()
        (self.work / '.cache').mkdir()
        root = Path(__file__).resolve().parents[1]
        program = f'''import sys
sys.path.insert(0,{str(root)!r})
from pathlib import Path
from harness import gpu_script_worker as worker
worker.GPU_RUNTIME_PATHS=({str(runtime)!r},)
worker.restrict(Path({str(self.work)!r}),None,[],True)
assert Path({str(library)!r}).read_text()=="nonsecret runtime fixture"
for path,mode in (({str(library)!r},"w"),({str(canary)!r},"r")):
    try:
        open(path,mode)
    except PermissionError:
        continue
    raise AssertionError("unexpected authority")
print("runtime read only; sibling denied")
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', program], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(library.read_text(), 'nonsecret runtime fixture')


if __name__ == '__main__':
    unittest.main()
