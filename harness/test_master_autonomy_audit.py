import json
from pathlib import Path
import tempfile
import unittest

from harness.master_autonomy_audit import replay_tool
from harness.master_research import MasterAccess


class MasterToolReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stats = dict(schema='acceptance-evidence-v1', aggregate=dict(emitted_tokens_per_verify=5))
        self.access = MasterAccess('Master', {}, self.root / 'tools', self.root / 'cache',
            baseline_loader=lambda:self.stats, stock=self.root / 'stock')

    def test_real_baseline_callback_is_independently_recomputed(self):
        action = dict(kind='get_baseline_stats')
        answer = self.access.dispatch(self.root, action, self.root / 'execution')
        replay_tool(action, answer, self.root / 'execution', self.access)
        answer['statistics']['aggregate']['emitted_tokens_per_verify'] = 99
        self.stats = dict(schema='acceptance-evidence-v1', aggregate=dict(emitted_tokens_per_verify=5))
        with self.assertRaises(ValueError):
            replay_tool(action, answer, self.root / 'execution', self.access)

    def test_unknown_added_cost_cannot_be_replaced_with_zero_in_replay(self):
        action = dict(kind='estimate_scenario', tau_ratio=1.2, step_cost_ratio=1,
            extra_step_cost_ratio=None, assumptions=['Conditional and explicit unknown extra cost'])
        answer = self.access.dispatch(self.root, action, self.root / 'execution')
        replay_tool(action, answer, self.root / 'execution', self.access)
        answer['scenario']['conditional_decode_speedup'] = 1.2
        (self.root / 'execution/result.json').write_text(json.dumps(answer))
        with self.assertRaises(ValueError):
            replay_tool(action, answer, self.root / 'execution', self.access)

    def test_network_response_without_raw_receipt_is_rejected(self):
        with self.assertRaises(ValueError):
            replay_tool(dict(kind='read_public', url='https://docs.pytorch.org/'),
                dict(status='completed', content='invented', receipt_path=str(self.root / 'absent')),
                self.root, self.access)

    def test_stock_search_is_replayed_not_trusted_from_its_echo(self):
        path = self.root / 'stock/python/sglang/srt/worker.py'
        path.parent.mkdir(parents=True)
        path.write_text('def verify():\n    return 8\n')
        action = dict(kind='search_stock', query='verify', prefix='python/sglang/', offset=0)
        answer = self.access.dispatch(self.root, action, self.root / 'execution')
        replay_tool(action, answer, self.root / 'execution', self.access)
        answer['matches'][0]['line'] = 999
        (self.root / 'execution/result.json').write_text(json.dumps(answer))
        with self.assertRaises(ValueError):
            replay_tool(action, answer, self.root / 'execution', self.access)


if __name__ == '__main__':
    unittest.main()
