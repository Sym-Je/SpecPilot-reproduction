import copy
import json
import multiprocessing
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import budget
import gpt_budget
import gpt_handoff
from resume_claude import cached_answer

REQUEST = {'model': 'gpt-6.1-sol', 'input_bytes': 2000, 'max_tokens': 8192,
           'request_sha256': 'offline-fixture', 'role_id': 'ctrip-d1-existing'}
SNAPSHOT = {'total_used_quota': 1000000, 'epoch': 10, 'rates': {}}


def reserve(directory):
    gpt_budget.Budget(directory).transact('reserve', REQUEST, SNAPSHOT)


class GPTBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_phase_limits_are_independent_and_never_reset(self):
        claude = budget.Budget(self.root / 'claude')
        request = dict(REQUEST, model=budget.MODEL)
        a = claude.transact('reserve', request, SNAPSHOT)
        b = gpt_budget.Budget(self.root / 'gpt').transact('reserve', REQUEST, SNAPSHOT)
        self.assertEqual((a['limit_usd'], b['limit_usd']), (200, 500))
        self.assertEqual(claude.transact('status', {}, SNAPSHOT)['reserved_usd'], a['reserved_usd'])
        self.assertEqual(gpt_budget.Budget(self.root / 'gpt').transact('status', {}, SNAPSHOT)['reserved_usd'], b['reserved_usd'])
        with self.assertRaisesRegex(AssertionError, 'Ledger model mismatch'):
            gpt_budget.Budget(self.root / 'claude').transact('status', {}, SNAPSHOT)

    def test_500_limit_denial_durable_and_no_refunds(self):
        ledger = gpt_budget.Budget(self.root)
        a = ledger.transact('reserve', REQUEST, SNAPSHOT)
        b = ledger.transact('settle', {'reservation_id': a['reservation_id'], 'finish': 'error'}, SNAPSHOT)
        self.assertEqual(a['reserved_usd'], b['reserved_usd'])
        state = json.loads(ledger.state_path.read_text())
        state['conservative_reserved_micro_usd'] = 500_000_000 - 1
        ledger.state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(RuntimeError, '500 USD budget admission denied'):
            ledger.transact('reserve', REQUEST, SNAPSHOT)
        saved = json.loads(ledger.state_path.read_text())
        self.assertEqual(len(saved['reservations']), 1)
        self.assertEqual(saved['budget_exhausted']['reason'], 'admission_ceiling')
        self.assertTrue(saved['stopped'])
        with self.assertRaises(RuntimeError):
            gpt_budget.Budget(self.root).transact('reserve', REQUEST, SNAPSHOT)

    def test_no_55_model_or_malformed_cap(self):
        ledger = gpt_budget.Budget(self.root)
        for model in ('gpt-5.5', 'gpt-6.1', 'claude-opus-5-5'):
            with self.assertRaises(AssertionError): ledger.transact('reserve', dict(REQUEST, model=model), SNAPSHOT)
        with self.assertRaises(ValueError): ledger.transact('reserve', dict(REQUEST, max_tokens=None), SNAPSHOT)
        self.assertFalse(ledger.state_path.exists())

    def test_concurrent_admission_is_persistent(self):
        procs = [multiprocessing.Process(target=reserve, args=(str(self.root),)) for _ in range(4)]
        for p in procs: p.start()
        for p in procs: p.join(10); self.assertEqual(p.exitcode, 0)
        state = json.loads((self.root / 'state.json').read_text())
        self.assertEqual(len(state['reservations']), 4)
        self.assertEqual(state['conservative_reserved_micro_usd'], 4 * budget.reserve_amount(2000, 8192))

    def test_gateway_reset_and_spend_stop_admission(self):
        ledger = gpt_budget.Budget(self.root)
        ledger.transact('status', {}, SNAPSHOT)
        with self.assertRaisesRegex(RuntimeError, 'counter reset'):
            ledger.transact('reserve', REQUEST, dict(SNAPSHOT, total_used_quota=0))
        self.assertNotIn('budget_exhausted', json.loads(ledger.state_path.read_text()))
        with self.assertRaisesRegex(RuntimeError, 'admission denied'):
            ledger.transact('reserve', REQUEST, dict(SNAPSHOT, total_used_quota=501_000_000))

    def test_gateway_cost_parser_uses_actual_and_exact_target(self):
        data = {'isValid': True, 'unit': 'USD', 'usage': {'total': {'actual_cost': 2.1234561}},
                'model_stats': [{'model': gpt_budget.MODEL, 'cost': 1, 'actual_cost': 1,
                                 'input_tokens': 100000, 'output_tokens': 100000}]}
        self.assertEqual(gpt_budget.parse_snapshot(data)['total_used_quota'], 2123457)
        for field, value in [('actual_cost', 2), ('model', 'gpt-5.5')]:
            broken = copy.deepcopy(data); broken['model_stats'][0][field] = value
            with self.assertRaises(AssertionError): gpt_budget.parse_snapshot(broken)
        for amount in (-1, 'NaN', 'Infinity'):
            with self.assertRaises(ValueError): gpt_budget.micro_usd(amount)

    def test_claude_denial_event_is_distinct_from_network_or_role_failure(self):
        ledger = budget.Budget(self.root)
        ledger.transact('status', {}, SNAPSHOT)
        with self.assertRaisesRegex(RuntimeError, 'counter reset'):
            ledger.transact('reserve', dict(REQUEST, model=budget.MODEL), dict(SNAPSHOT, total_used_quota=0))
        self.assertNotIn('budget_exhausted', json.loads(ledger.state_path.read_text()))
        state = json.loads(ledger.state_path.read_text()); state['conservative_reserved_micro_usd'] = 200_000_000
        ledger.state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(RuntimeError, '200 USD budget admission denied'):
            ledger.transact('reserve', dict(REQUEST, model=budget.MODEL), SNAPSHOT)
        state = json.loads(ledger.state_path.read_text())
        self.assertEqual(state['budget_exhausted']['role_id'], REQUEST['role_id'])


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.ledger = {'model': 'claude-opus-5-5', 'limit_micro_usd': 200_000_000,
                       'budget_exhausted': {'epoch': 10, 'role_id': 'ctrip-d1-existing'}}
        self.research = {'status': 'stopped_with_error', 'stopped_epoch': 11,
                         'active_role': 'ctrip-d1-existing', 'rounds': [], 'validation_opened': False}

    def test_normal_work_and_unrelated_errors_never_activate_gpt(self):
        ledger = dict(self.ledger); ledger.pop('budget_exhausted')
        self.assertEqual(gpt_handoff.eligibility(ledger, self.research), 'needs_attention')
        self.assertEqual(gpt_handoff.eligibility(ledger, dict(self.research, status='researching')), 'waiting_for_claude')
        wrong = dict(self.research, active_role='other')
        self.assertEqual(gpt_handoff.eligibility(self.ledger, wrong), 'needs_attention')

    def test_completed_report_format_recovery_changes_no_values(self):
        text = 'Report\n{"status":"needs_evidence","hypothesis":"h","cost_floor":{}},"experiments":[],"conclusion":"c","candidate_config":null,"limitations":[]}'
        value, repair = cached_answer(text)
        self.assertEqual(value['status'], 'needs_evidence')
        self.assertIsNone(value['candidate_config'])
        self.assertFalse(repair['scientific_values_modified'])
        with self.assertRaises((AssertionError, ValueError)):
            cached_answer(text.replace('"experiments":[]', '"experiments":[],"status":"candidate"'))

    def test_validation_or_completed_research_prevents_handoff(self):
        for state in (dict(self.research, validation_opened=True), dict(self.research, status='research_finished')):
            self.assertEqual(gpt_handoff.eligibility(self.ledger, state), 'finished_without_handoff')
        self.assertEqual(gpt_handoff.eligibility(self.ledger, self.research, validation_started=True), 'finished_without_handoff')

    def test_pending_cleanup_waits_then_only_budget_denial_is_ready(self):
        self.assertEqual(gpt_handoff.eligibility(self.ledger, self.research, pending_experiments=True), 'waiting_for_experiment_restoration')
        self.assertEqual(gpt_handoff.eligibility(self.ledger, self.research), 'ready')
        self.assertEqual(gpt_handoff.eligibility(self.ledger, dict(self.research, stopped_epoch=9)), 'needs_attention')

    def test_existing_direction_resumes_without_reallocating_or_rerunning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); role = self.research['active_role']
            directory = root / 'research/roles' / role; directory.mkdir(parents=True)
            spec = {'name': 'existing', 'objective': 'Existing research', 'required_evidence': 'own receipts',
                    'cost_floor_plan': 'measure', 'max_experiments': 2, 'max_actions': 40}
            decision = {'decision': 'run_direction', 'direction': spec, 'candidate': None}
            gpt_handoff.write(root / 'research/master-decision-1.json', decision)
            allocation = {k: spec[k] for k in ('max_experiments', 'max_actions')}
            gpt_handoff.write(directory / 'allocation.json', allocation)
            broker = {'actions': 31, 'experiments': ['already-ran']}
            gpt_handoff.write(directory / 'broker-state.json', broker)
            (root / 'experiments/already-ran').mkdir(parents=True)
            receipt = {'status': 'complete', 'lock_acquired_epoch': 1, 'completed_epoch': 2, 'baseline_restored': True}
            gpt_handoff.write(root / 'experiments/already-ran/state.json', receipt)
            plan = gpt_handoff.recovery_plan(self.research, root)
            self.assertEqual(plan['resume_role'], role)
            self.assertEqual(plan['allocation'], allocation)
            state = copy.deepcopy(self.research)
            calls = []
            def invoke(name, mode, prompt):
                calls.append((name, mode))
                return {'status': 'no_gain', 'candidate_config': None} if mode == 'direction' else {'decision': 'stop', 'candidate': None}
            # Patch paths/side effects only. The real continuation loop is executed.
            with patch.object(gpt_handoff, 'OUT', root), \
                 patch.object(gpt_handoff, 'recovery_plan', lambda s: plan), \
                 patch.object(gpt_handoff, 'experiment_receipts', lambda name: (broker, [receipt])), \
                 patch.object(gpt_handoff, 'invoke', invoke), \
                 patch.object(gpt_handoff.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                gpt_handoff.continue_research(state)
            self.assertEqual(calls, [(role, 'direction'), ('ctrip-master', 'master')])
            self.assertEqual(json.loads((directory / 'allocation.json').read_text()), allocation)
            self.assertEqual(json.loads((directory / 'broker-state.json').read_text()), broker)
            self.assertEqual(len(state['rounds']), 1)
            self.assertEqual(state['status'], 'research_finished')
            self.assertEqual(state['campaign_status'], 'complete')
            self.assertEqual(json.loads((root / 'research/master-decision-1.json').read_text()), decision)


if __name__ == '__main__': unittest.main()
