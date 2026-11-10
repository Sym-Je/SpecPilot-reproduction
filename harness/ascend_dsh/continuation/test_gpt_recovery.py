import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_baseline import write


class RecoveryTests(unittest.TestCase):
    def test_checkpoint_replay_keeps_current_role_contract(self):
        import gpt_call
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'research-gpt/session-routing';directory.mkdir(parents=True)
            checkpoint=directory/'checkpoint.json';write(checkpoint,{'original_prompt':'old generic retry'})
            write(directory/'test-master.json',{'session_id':'test-master-gpt-c1','checkpoint_path':str(checkpoint.relative_to(root))})
            with patch('gpt_call.HERE',root), patch('gpt_call._native_call',return_value=('{}',{'result':{'finish_reason':'completed'}})) as native:
                gpt_call.call('test-master','master','CURRENT MASTER SCHEMA: return decision','system')
            self.assertIn('CURRENT MASTER SCHEMA',native.call_args.args[2])
            self.assertEqual(native.call_args.args[0],'test-master')

    def test_long_prompt_preserves_final_master_contract(self):
        from gpt_context import bounded_prompt
        prompt='Role identity\n'+'x'*50000+'\nReturn {"decision":"run_direction" or "needs_capability"}'
        bounded=bounded_prompt(prompt)
        self.assertTrue(bounded.startswith('Role identity'))
        self.assertTrue(bounded.endswith('"needs_capability"}'))
        self.assertLess(len(bounded),25000)

    def test_context_limit_detection_is_not_budget_exhaustion_or_refusal(self):
        from gpt_context import input_limit_failure
        def result(message):
            return {'events': [{'type': 'turn/end', 'data': {'reason': {'error': {'message': message}}}}]}
        self.assertTrue(input_limit_failure(result('ValueError: Request exceeds input byte limit')))
        self.assertTrue(input_limit_failure({'events':[{'type':'turn/end','data':{'reason':{'error':{'code':'CONTEXT_WINDOW_EXCEEDED','message':'context overflow'}}}}]}))
        self.assertFalse(input_limit_failure(result('500 USD budget admission denied')))
        self.assertFalse(input_limit_failure(result('Provider returned refusal')))

    def test_checkpoint_keeps_role_state_and_experiments_without_reset(self):
        from gpt_context import rotate_session
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / 'research/roles/role-one'; folder.mkdir(parents=True)
            state = {'actions': 55, 'experiments': ['existing']}
            write(folder / 'broker-state.json', state)
            (folder / 'scratch').mkdir(); (folder / 'scratch/notes.json').write_text('{"fact":7}')
            (folder / 'broker.jsonl').write_text(json.dumps({'tool': 'read_source', 'arguments': {'path': 'model.py'}, 'result': {'content': 'x'*20000, 'sha256': 'pin'}})+'\n')
            exp = root / 'experiments/existing';exp.mkdir(parents=True)
            write(exp/'state.json', {'id':'existing','status':'complete','baseline_restored':True})
            routing = rotate_session(root, 'role-one', 'role-one-gpt', 'Keep precision fixed', 'receipt-sha')
            text = (root / routing['checkpoint_path']).read_text()
            self.assertLess(len(text.encode()), 180000)
            self.assertIn('existing', text); self.assertIn('receipt-sha', text)
            self.assertEqual(json.loads((folder/'broker-state.json').read_text()), state)
            self.assertTrue(routing['session_id'].endswith('-c1'))

    def test_settlement_after_primary_failure_is_allowed_but_new_admission_is_not(self):
        from gpt_budget import activated
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('handoff','research','billing'): (root/directory).mkdir()
            write(root/'handoff/state.json', {'status':'gpt_running'})
            write(root/'research/state.json', {'status':'needs_attention','validation_opened':False})
            write(root/'billing/state.json', {'model':'claude-opus-5-5','limit_micro_usd':200000000,'budget_exhausted':True})
            with patch('gpt_budget.HERE',root):
                activated(settlement=True)
                with self.assertRaises(AssertionError):activated()


if __name__ == '__main__': unittest.main()
