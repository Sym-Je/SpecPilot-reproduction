import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_baseline import sha, write
from research_broker import Broker


class ParallelTests(unittest.TestCase):
    def test_terminal_report_after_adjacent_prose_preserves_numbers(self):
        from parallel_research import parse_report
        text = 'Evidence is incomplete.{"status":"needs_evidence","cost_floor":{"bytes":268238848}}'
        self.assertEqual(parse_report(text)['cost_floor']['bytes'], 268238848)

    def test_terminal_report_rejects_trailing_prose_or_incomplete_json(self):
        from parallel_research import parse_report
        for text in ('{"status":"needs_evidence"} unfinished discussion', 'Evidence.{"status":'):
            with self.subTest(text=text), self.assertRaises(json.JSONDecodeError):
                parse_report(text)

    def fixture(self, root):
        role = root / 'research/roles/parallel-fixture'
        role.mkdir(parents=True)
        write(role / 'allocation.json', {'analysis_only': True, 'max_actions': 20,
                                       'max_experiments': 0, 'shared_profile_csvs': {}})
        return role

    def test_analysis_role_cannot_submit_or_wait_for_npu(self):
        with tempfile.TemporaryDirectory() as tmp, patch('research_broker.OUT', Path(tmp)):
            self.fixture(Path(tmp))
            broker = Broker('parallel-fixture', 'direction')
            self.assertNotIn('launch_experiment', broker.names())
            self.assertNotIn('wait_experiment', broker.names())
            self.assertIn('run_cpu', broker.names())
            with self.assertRaises(ValueError):
                broker.act('launch_experiment', {'id': 'x', 'config': {}, 'mode': 'profile'})

    def test_only_pinned_shared_csv_is_readable_and_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch('research_broker.OUT', Path(tmp)):
            root = Path(tmp); role = self.fixture(root)
            exp = root / 'experiments/completed-profile'
            (exp / 'traces').mkdir(parents=True)
            write(exp / 'state.json', {'status': 'complete'})
            csv = exp / 'traces/kernel_type_summary.csv'; csv.write_text('type,time\nlocal,1\n')
            allocation = json.loads((role / 'allocation.json').read_text())
            allocation['shared_profile_csvs'] = {'completed-profile': {'kernel_type_summary.csv': sha(csv)}}
            write(role / 'allocation.json', allocation)
            broker = Broker('parallel-fixture', 'direction')
            args = {'id': 'completed-profile', 'path': 'kernel_type_summary.csv', 'offset': 0}
            self.assertIn('local', broker.act('read_profile', args)['result']['content'])
            with self.assertRaises(ValueError):
                broker.act('read_profile', args | {'path': '../state.json'})
            csv.write_text('changed')
            with self.assertRaises(ValueError):
                broker.act('read_profile', args)

    def test_analysis_does_not_receive_peer_reports(self):
        from parallel_evidence import shared_updates
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'research/parallel/roles/one'
            out.mkdir(parents=True)
            write(out / 'result.json', {'status': 'complete', 'report': {'hypothesis': 'unmeasured'}})
            self.assertEqual(shared_updates(root, analysis_only=True), {})
            data = shared_updates(root)
            self.assertEqual(len(data['parallel_reports']), 1)
            self.assertFalse(data['parallel_reports'][0]['measured_gain'])

    def test_completed_cpu_prefix_audit_is_attributed_and_not_shared_with_independent_peers(self):
        from parallel_evidence import shared_updates
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); area=root/'research/prefix-reuse-audit';area.mkdir(parents=True)
            report={'status':'complete','support_gate':{'all_required_state_restoration_proven':False},'cases':[]}
            write(area/'summary.json',report)
            audit=shared_updates(root)['prefix_reuse_audit']
            self.assertEqual(audit['report'],report)
            self.assertFalse(audit['measured_gain'])
            self.assertEqual(audit['source_sha256'],sha(area/'summary.json'))
            self.assertEqual(shared_updates(root,analysis_only=True),{})
            write(area/'summary.json',report|{'status':'incomplete'})
            self.assertNotIn('prefix_reuse_audit',shared_updates(root))

    def test_parallel_plan_requires_two_distinct_bounded_directions(self):
        from parallel_research import validate_plan
        valid = {'directions': [{'name': n, 'objective': 'review', 'required_evidence': 'source',
                                 'cost_floor_plan': 'unknown until measured', 'max_actions': 24}
                                for n in ('one', 'two')]}
        validate_plan(valid)
        valid['directions'][1]['name'] = 'one'
        with self.assertRaises(ValueError): validate_plan(valid)

    def test_long_direction_slug_still_fits_broker_role_limit(self):
        from parallel_research import validate_plan
        plan = {'directions': [{'name': name, 'objective': 'review', 'required_evidence': 'source',
                                'cost_floor_plan': 'unknown', 'max_actions': 24}
                               for name in ('local-hyperconnection-materialization-cost', 'a' * 60)]}
        validate_plan(plan)
        self.assertTrue(all(len('parallel-a1-' + d['name']) <= 80 for d in plan['directions']))
        plan['directions'][1]['name'] += 'a'
        with self.assertRaises(ValueError): validate_plan(plan)

    def test_parallel_budget_route_waits_for_authorized_handoff(self):
        from parallel_research import route
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'billing').mkdir(); (root / 'research').mkdir()
            write(root / 'research/state.json', {'status': 'researching', 'validation_opened': False})
            write(root / 'billing/state.json', {'budget_exhausted': False})
            self.assertEqual(route(root), 'claude-opus-5-5')
            write(root / 'billing/state.json', {'budget_exhausted': True})
            self.assertEqual(route(root), 'wait_for_primary_handoff')
            (root / 'handoff').mkdir(); write(root / 'handoff/state.json', {'status': 'gpt_running'})
            self.assertEqual(route(root), 'gpt-6.1-sol')
            write(root / 'research/state.json', {'status': 'researching', 'validation_opened': True})
            with self.assertRaises(RuntimeError): route(root)

    def test_truncated_role_resumes_without_repeating_work_or_changing_model(self):
        from parallel_research import call_role
        with tempfile.TemporaryDirectory() as tmp:
            area = Path(tmp) / 'parallel'
            calls = [AssertionError('max-tokens'), ('{"status":"needs_evidence"}', {'call_id': 'fixture'})]
            with patch('parallel_research.AREA', area), patch('parallel_research.route', return_value='claude-opus-5-5'), \
                    patch('parallel_research.patch_for', return_value=Path(tmp) / 'fixture.yml'), \
                    patch('dsh_call.call', side_effect=calls) as native:
                call_role('parallel-fixture', 'direction', 'Original bounded analysis brief')
            result = json.loads((area / 'roles/parallel-fixture/result.json').read_text())
            self.assertEqual(result['model'], 'claude-opus-5-5')
            self.assertEqual(native.call_count, 2)
            self.assertIn('Do not repeat', native.call_args_list[1].args[1])

    def test_shared_phase_activation_requires_recorded_budget_denial(self):
        from parallel_research import activate_gpt_phase
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'billing').mkdir()
            ledger = {'model': 'claude-opus-5-5', 'limit_micro_usd': 200_000_000}
            write(root / 'billing/state.json', ledger)
            with self.assertRaises(RuntimeError): activate_gpt_phase(root)
            write(root / 'billing/state.json', ledger | {'budget_exhausted': {'reason': 'admission_ceiling'}})
            activate_gpt_phase(root)
            result = json.loads((root / 'handoff/state.json').read_text())
            self.assertEqual(result['gpt_limit_usd'], 1000)
            self.assertFalse((root / 'research/state.json').exists())
            self.assertEqual(json.loads((root / 'billing/state.json').read_text())['limit_micro_usd'], 200_000_000)


if __name__ == '__main__':
    unittest.main()
