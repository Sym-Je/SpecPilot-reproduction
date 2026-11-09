import copy
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from budget import Budget, LIMIT_MICRO_USD, MODEL, reserve_amount

SNAPSHOT = {'total_used_quota': 1000000, 'rates': {}, 'epoch': 1}
REQUEST = {'model': MODEL, 'input_bytes': 1000, 'max_tokens': 1024, 'request_sha256': 'fixture'}


def reserve_process(directory):
    Budget(directory).transact('reserve', REQUEST, SNAPSHOT)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.budget = Budget(self.tmp.name)

    def test_reserve_precedes_dispatch_and_survives_restart(self):
        result = self.budget.transact('reserve', REQUEST, SNAPSHOT)
        resumed = Budget(self.tmp.name).transact('status', {}, SNAPSHOT)
        self.assertEqual(result['reserved_usd'], resumed['reserved_usd'])
        self.assertGreater(result['reserved_usd'], 0)

    def test_settlement_does_not_refund_failed_or_completed_requests(self):
        result = self.budget.transact('reserve', REQUEST, SNAPSHOT)
        after = self.budget.transact('settle', {'reservation_id': result['reservation_id'], 'finish': 'error'}, SNAPSHOT)
        self.assertEqual(after['reserved_usd'], result['reserved_usd'])
        with self.assertRaises(AssertionError):
            self.budget.transact('settle', {'reservation_id': result['reservation_id']}, SNAPSHOT)

    def test_over_budget_request_is_never_admitted(self):
        self.budget.transact('status', {}, SNAPSHOT)
        p = self.budget.state_path
        state = json.loads(p.read_text()); state['conservative_reserved_micro_usd'] = LIMIT_MICRO_USD - 1
        p.write_text(json.dumps(state))
        with self.assertRaisesRegex(RuntimeError, 'admission denied'):
            self.budget.transact('reserve', REQUEST, SNAPSHOT)
        self.assertFalse(json.loads(p.read_text())['reservations'])

    def test_shared_gateway_spend_only_reduces_remaining_budget(self):
        self.budget.transact('status', {}, SNAPSHOT)
        snapshot = dict(SNAPSHOT, total_used_quota=SNAPSHOT['total_used_quota'] + 250000000)
        with self.assertRaisesRegex(RuntimeError, 'admission denied'):
            self.budget.transact('reserve', REQUEST, snapshot)

    def test_old_500_ledger_is_lowered_without_resetting_usage(self):
        original = self.budget.transact('reserve', REQUEST, SNAPSHOT)
        state = json.loads(self.budget.state_path.read_text())
        state['limit_micro_usd'] = 500_000_000
        before = copy.deepcopy(state['reservations'])
        self.budget.state_path.write_text(json.dumps(state))
        updated = Budget(self.tmp.name).transact('status', {}, SNAPSHOT)
        persisted = json.loads(self.budget.state_path.read_text())
        self.assertEqual(updated['limit_usd'], 200)
        self.assertEqual(persisted['reservations'], before)
        self.assertEqual(updated['reserved_usd'], original['reserved_usd'])
        self.assertEqual(persisted['limit_changes'][-1]['from_micro_usd'], 500_000_000)
        settled = Budget(self.tmp.name).transact('settle', {'reservation_id': original['reservation_id']}, SNAPSHOT)
        self.assertEqual(settled['limit_usd'], 200)
        self.assertEqual(settled['reserved_usd'], original['reserved_usd'])

    def test_200_ceiling_cannot_be_raised_by_stale_ledger(self):
        self.budget.transact('status', {}, SNAPSHOT)
        state = json.loads(self.budget.state_path.read_text())
        state['limit_micro_usd'] = 500_000_000
        state['conservative_reserved_micro_usd'] = 200_000_000 - 1
        self.budget.state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(RuntimeError, '200 USD budget admission denied'):
            Budget(self.tmp.name).transact('reserve', REQUEST, SNAPSHOT)
        self.assertFalse(json.loads(self.budget.state_path.read_text())['reservations'])

    def test_counter_reset_fails_closed(self):
        self.budget.transact('status', {}, SNAPSHOT)
        with self.assertRaisesRegex(RuntimeError, 'counter reset'):
            self.budget.transact('reserve', REQUEST, dict(SNAPSHOT, total_used_quota=0))

    def test_wrong_model_and_missing_output_cap_rejected(self):
        with self.assertRaises(AssertionError):
            self.budget.transact('reserve', dict(REQUEST, model='other'), SNAPSHOT)
        for value in (None, 0, 100000, True):
            with self.assertRaises(ValueError):
                reserve_amount(100, value)

    def test_concurrent_processes_share_one_budget(self):
        processes = [multiprocessing.Process(target=reserve_process, args=(self.tmp.name,)) for _ in range(4)]
        for p in processes: p.start()
        for p in processes: p.join(10); self.assertEqual(p.exitcode, 0)
        state = json.loads(self.budget.state_path.read_text())
        self.assertEqual(len(state['reservations']), 4)
        self.assertEqual(state['conservative_reserved_micro_usd'], 4 * reserve_amount(1000, 1024))


if __name__ == '__main__':
    unittest.main()
