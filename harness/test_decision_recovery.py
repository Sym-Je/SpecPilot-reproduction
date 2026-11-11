import unittest
import json
from harness.decision_recovery import count_actions, own_files, role_context
from harness.decision_review import check_delivery


class RecoveryTests(unittest.TestCase):
    def test_review_requires_actual_prompt_delivery_not_just_an_input_file(self):
        reports=[dict(value={'summary':'own result'},source={'sha256':'a'*64})]
        prompt='Delivered: '+json.dumps(dict(direction_feedback=reports))
        self.assertEqual(check_delivery(prompt,reports)['direction_feedback'],reports)
        with self.assertRaises(ValueError):check_delivery('Delivered: {}',reports)
        with self.assertRaises(ValueError):check_delivery(prompt,[])

    def test_failed_turn_charges_search_but_not_denied_execution(self):
        calls=[({'kind':'search_stock'}, {'status':'completed'}),
            ({'kind':'run_python'}, {'status':'rejected','reason':'CPU run budget exhausted'}),
            ({'kind':'write_file'}, {'status':'completed'})]
        self.assertEqual(count_actions(calls),dict(actions=3,cpu_runs=1))

    def test_recovery_only_accepts_native_successful_scratch_writes(self):
        calls=[({'kind':'write_file','path':'scratch/check.py','content':'print(1)'},
            {'status':'completed','sha256':'invalid'})]
        with self.assertRaises(ValueError):own_files(calls)

    def test_master_receives_status_not_private_direction_source(self):
        recovery=dict(provenance='own interrupted work',charged_counters={},roles={
            'master':dict(own_responses=[{'kind':'compare'}],own_scratch={},counters={}),
            'direction-a':dict(own_responses=[],own_scratch={'scratch/a.py':'private-source-a'},counters={}),
            'direction-b':dict(own_responses=[],own_scratch={'scratch/b.py':'private-source-b'},counters={})})
        self.assertNotIn('private-source',str(role_context(recovery,'master')))
        own=role_context(recovery,'direction-a')
        self.assertIn('private-source-a',str(own))
        self.assertNotIn('private-source-b',str(own))
        self.assertIsNone(role_context(recovery,'direction-c')['own_prior_work'])
