import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.research_protocol import ResearchBroker
from harness.skill_broker import SkillAccess
from harness.skill_diagnostics import sha256, write_json


class SkillRsiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / 'work'
        (self.work / 'scratch').mkdir(parents=True)
        (self.work / 'inputs').mkdir()
        self.inputs, self.tools = self.root / 'inputs.json', self.root / 'tools.json'
        write_json(self.inputs, {'fixture': 'authorized stock only'})
        write_json(self.tools, {'revision': 'a' * 40})
        self.access = SkillAccess('direction', {'stock': self.inputs}, self.tools, self.root / 'cache')

    def request(self, call, action):
        return dict(threadId='thread-own', turnId='turn-own', tool='research', namespace=None,
            callId=call, arguments={'action': action})

    def mock_analysis(self, manifest, tools, output):
        output.mkdir(parents=True)
        (output / 'profiler.stdout.txt').write_text('fixture diagnostic')
        write_json(output / 'compute.stdout.txt', {'measured_ms': None, 'mfu_pct': None})
        write_json(output / 'result.json', dict(input_identity={'fixture': 'authorized stock only'},
            engineering_passed=True, upstream_revision='a' * 40, kernel_statistics={'fixture': 1},
            limitations=['synthetic fixture, not GPU evidence'],
            tools={name: {'output_sha256': {'stdout': sha256(output / (name + '.stdout.txt'))}}
                for name in ('profiler', 'compute')}))

    def authorized(self):
        return patch.multiple('harness.skill_broker', checked_manifest=lambda value: value,
            checked_tools=lambda value: value, analyze=self.mock_analysis)

    def test_catalog_is_role_scoped_without_host_paths_or_submission(self):
        result = self.access.dispatch(self.work, {'kind': 'list_skills'}, self.root / 'result')
        self.assertEqual(set(result['skills']), {'profiler', 'compute', 'pipeline', 'capacity', 'triage'})
        self.assertEqual(result['evidence'], ['stock'])
        self.assertFalse(result['gpu_submission_allowed'])
        self.assertFalse(result['arbitrary_shell'])

    def test_unregistered_role_rejected(self):
        with self.assertRaises(ValueError):
            SkillAccess('controller', {}, self.tools, self.root / 'cache')

    def test_unknown_evidence_or_shell_parameters_rejected_before_execution(self):
        for action in ({'kind': 'run_skill', 'skill': 'compute', 'evidence': 'other-direction'},
                       {'kind': 'run_skill', 'skill': 'shell', 'evidence': 'stock'},
                       {'kind': 'run_skill', 'skill': 'compute', 'evidence': 'stock', 'path': '/host/file'},
                       {'kind': 'list_skills', 'url': 'https://example.org'}):
            with self.subTest(action=action), patch('harness.skill_broker.analyze') as run, self.assertRaises(ValueError):
                self.access.dispatch(self.work, action, self.root / 'result')
            run.assert_not_called()

    def test_broker_retains_call_identity_and_cpu_budget_for_skills(self):
        broker = self.access.factory()(self.work, self.root / 'records', 'thread-own', 'turn-own', max_runs=0)
        result = broker.handle(self.request('call-one', {'kind': 'run_skill', 'skill': 'compute', 'evidence': 'stock'}))
        self.assertFalse(result['success'])
        self.assertEqual(broker.actions, 1)
        with self.assertRaises(ValueError):
            broker.handle(self.request('call-one', {'kind': 'list_skills'}))
        other = self.request('call-other', {'kind': 'list_skills'})
        other['threadId'] = 'other-direction'
        with self.assertRaises(ValueError):
            broker.handle(other)

    def test_native_broker_routes_authorized_skill_and_records_provenance(self):
        broker = self.access.factory()(self.work, self.root / 'records', 'thread-own', 'turn-own')
        with self.authorized():
            result = broker.handle(self.request('call-one', {'kind': 'run_skill', 'skill': 'compute', 'evidence': 'stock'}))
        self.assertTrue(result['success'])
        value = json.loads(result['contentItems'][0]['text'])
        self.assertFalse(value['independent_discovery'])
        self.assertEqual(value['estimate']['mfu_pct'], None)
        self.assertEqual(broker.runs, 1)
        self.assertTrue((self.root / 'records/action-001/execution/result.json').is_file())

    def test_cached_analysis_outputs_are_rechecked_not_blindly_reused(self):
        action = {'kind': 'run_skill', 'skill': 'profiler', 'evidence': 'stock'}
        with self.authorized():
            first = self.access.dispatch(self.work, action, self.root / 'first')
            self.assertFalse(first['cached'])
            second = self.access.dispatch(self.work, action, self.root / 'second')
            self.assertTrue(second['cached'])
            output = next((self.root / 'cache').glob('*/profiler.stdout.txt'))
            output.write_text('changed')
            with self.assertRaises(ValueError):
                self.access.dispatch(self.work, action, self.root / 'third')

    def test_role_without_evidence_cannot_access_another_role_cache(self):
        access = SkillAccess('kernel', {}, self.tools, self.root / 'cache')
        with self.assertRaises(ValueError):
            access.dispatch(self.work, {'kind': 'run_skill', 'skill': 'compute', 'evidence': 'stock'}, self.root / 'out')

    def test_parallel_roles_share_analysis_without_duplicate_writers(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        action = {'kind': 'run_skill', 'skill': 'compute', 'evidence': 'stock'}
        def slow_analysis(*arguments):
            time.sleep(.05)
            return self.mock_analysis(*arguments)
        with self.authorized(), patch('harness.skill_broker.analyze', side_effect=slow_analysis) as analyze:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(self.access.dispatch, self.work, action, self.root / name)
                           for name in ('parallel-one', 'parallel-two')]
                results = [future.result() for future in futures]
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(sorted(result['cached'] for result in results), [False, True])

    def test_parallel_role_counters_are_aggregated_without_cross_role_overwrite(self):
        """Archive CPU acceptance: python -B -m unittest harness.test_skill_rsi -v."""
        from concurrent.futures import ThreadPoolExecutor
        import threading
        from exp.skill_rsi import Campaign
        barrier = threading.Barrier(2)
        def fake_turn(role, prompt, counters):
            barrier.wait(timeout=5)
            counters['actions'] += role['increment']
            counters['model_turns'] += 1
            return {'role': role['increment']}
        fixture_pin = '0123456789abcdef0123456789abcdef01234567'
        with patch('exp.skill_rsi.Budget') as budget, patch('exp.skill_rsi.roles.turn', side_effect=fake_turn), \
                patch('exp.skill_rsi.subprocess.check_output', return_value=fixture_pin + '\n') as git_pin:
            budget.return_value.read.return_value = {'started': 10**12, 'wall_seconds': 86400}
            campaign = Campaign(self.root, self.inputs, self.tools)
            roles = [dict(increment=increment, counters=dict(campaign.counters)) for increment in (2, 3)]
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(campaign.ask, role, 'fixture') for role in roles]
                for future in futures:
                    future.result()
        git_pin.assert_called_once()
        self.assertEqual(campaign.pin, fixture_pin)
        self.assertEqual(campaign.counters['actions'], 5)
        self.assertEqual(campaign.counters['model_turns'], 2)
        self.assertEqual([role['counters']['actions'] for role in roles], [2, 3])

    def test_master_plan_requires_multiple_independent_bounded_allocations(self):
        from exp.skill_rsi import validate_plan
        direction = dict(id='d1', brief='falsifiable direction, not an implementation',
            allocation=dict(actions=80, cpu_runs=16, gpu_attempts=2))
        plan = dict(directions=[direction, dict(direction, id='d2')])
        self.assertEqual(len(validate_plan(plan)), 2)
        for value in (dict(directions=[direction]), dict(directions=[direction, direction]),
                      dict(directions=[direction, dict(direction, id='../escape')])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_plan(value)
        altered = copy.deepcopy(plan)
        altered['directions'][0]['allocation']['gpu_attempts'] = 4
        with self.assertRaises(ValueError):
            validate_plan(altered)

    def test_no_research_before_real_preflight_and_no_replay_of_started_campaign(self):
        """Use an explicit fixture Git pin without changing production identity checks."""
        from exp.skill_rsi import Campaign
        fixture_pin = '0123456789abcdef0123456789abcdef01234567'
        with patch('exp.skill_rsi.Budget'), patch('exp.skill_rsi.roles.session') as session, \
                patch('exp.skill_rsi.subprocess.check_output', return_value=fixture_pin + '\n') as git_pin:
            campaign = Campaign(self.root, self.inputs, self.tools)
            with self.assertRaises(ValueError):
                campaign.run()
            session.assert_not_called()
            write_json(self.root / 'pipeline-result.json', {'status': 'running'})
            with self.assertRaises(ValueError):
                campaign.run()
            session.assert_not_called()
        git_pin.assert_called_once()
        self.assertEqual(campaign.pin, fixture_pin)

    def test_same_directory_cache_preserves_text_binary_and_rejects_escape(self):
        from types import SimpleNamespace
        from harness.source_cache import atomic_put
        cache = self.root / 'cache'
        cache.mkdir()
        manager = SimpleNamespace(cache_dir=str(cache), lock_path=str(cache / 'lock'),
            _make_path=lambda filename: str(cache / filename))
        self.assertEqual(Path(atomic_put(manager, b'first', 'kernel.bin')).read_bytes(), b'first')
        self.assertEqual(Path(atomic_put(manager, b'second', 'kernel.bin')).read_bytes(), b'second')
        self.assertEqual(Path(atomic_put(manager, 'metadata', 'group.json')).read_text(), 'metadata')
        self.assertEqual(list(cache.glob('.atomic-*')), [])
        for name in ('../outside', '/tmp/outside', '..'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                atomic_put(manager, b'bad', name)

    def test_atomic_cache_writes_under_actual_inherited_landlock(self):
        cache = self.root / 'isolated-cache'
        cache.mkdir()
        allowed = self.root / 'allowed.txt'
        allowed.write_text('authorized')
        repository = Path(__file__).resolve().parents[1]
        script = ('import json,sys;sys.path.insert(0,' + repr(str(repository)) + ');'
            'from types import SimpleNamespace;from pathlib import Path;'
            'from harness.source_cache import atomic_put;from harness.source_boundary import restrict;'
            'payload=json.load(sys.stdin);restrict(payload);'
            'manager=SimpleNamespace(cache_dir=payload["scratch"],lock_path="lock",'
            '_make_path=lambda name:str(Path(payload["scratch"])/name));'
            'target=atomic_put(manager,b"binary-cache","fixture.bin");'
            'assert Path(target).read_bytes()==b"binary-cache";print("atomic_cache_boundary_passed")')
        payload = dict(cpu_probe=True, scratch=str(cache), readonly=[str(allowed), sys.prefix],
            executables=[], allowed_read=str(allowed), allowed_content='authorized', canary=str(self.root / 'protected'))
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script], input=json.dumps(payload),
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('atomic_cache_boundary_passed', result.stdout)

    def test_compiler_self_group_allowed_but_session_and_other_groups_denied(self):
        repository = Path(__file__).resolve().parents[1]
        script = ('import os,sys;sys.path.insert(0,' + repr(str(repository)) + ');'
            'from harness.source_boundary import process_filter;process_filter();os.setpgid(0,0);'
            '\nfor operation in (lambda:os.setsid(),lambda:os.setpgid(0,os.getppid())):'
            '\n try: operation()'
            '\n except PermissionError: pass'
            '\n else: raise RuntimeError("group escape allowed")'
            '\nprint("compiler_group_passed")')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('compiler_group_passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
