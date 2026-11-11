import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp.master_autonomy import MasterCampaign
from harness.master_research import MasterAccess
from harness.master_proposal import AXES, validate_axes


class MasterResearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stock = self.root / 'stock'
        source = self.stock / 'python/sglang/srt/worker.py'
        source.parent.mkdir(parents=True)
        source.write_text('def verify():\n    return 8\n')
        self.baseline = dict(status='completed', tau=5, profiled=True, normal_performance=False)
        self.access = MasterAccess('Master', {}, self.root / 'tools.json', self.root / 'cache',
            baseline_loader=lambda:self.baseline, stock=self.stock)

    def test_help_exposes_tools_but_not_arbitrary_network_or_gpu(self):
        result = self.access.dispatch(self.root, dict(kind='help'), self.root / 'help')
        for name in ('search_stock', 'search_public', 'read_public', 'get_baseline_stats'):
            self.assertIn(name, result['master_actions'])
        self.assertFalse(result['arbitrary_network'])
        self.assertFalse(result['gpu_submission_allowed'])

    def test_baseline_statistics_are_readonly_and_not_a_formal_ceiling(self):
        result = self.access.dispatch(self.root, dict(kind='get_baseline_stats'), self.root / 'stats')
        self.assertEqual(result['statistics'], self.baseline)
        self.assertIsNone(result['formal_ceiling'])
        self.assertEqual(json.loads((self.root / 'stats/result.json').read_text()), result)
        with self.assertRaises(ValueError):
            self.access.dispatch(self.root, dict(kind='get_baseline_stats', path='/protected'), self.root / 'bad')

    def test_literal_stock_search_is_bounded_and_cannot_escape(self):
        result = self.access.dispatch(self.root, dict(kind='search_stock', query='verify',
            prefix='python/sglang/srt/', offset=0), self.root / 'search')
        self.assertEqual(result['matches'][0]['path'], 'python/sglang/srt/worker.py')
        self.assertEqual(result['matches'][0]['line'], 1)
        for prefix in ('../', '/etc/', 'python/../'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                self.access.dispatch(self.root, dict(kind='search_stock', query='verify',
                    prefix=prefix, offset=0), self.root / 'bad-search')

    def test_search_refuses_bool_offset_or_unbounded_query(self):
        for changes in (dict(offset=True), dict(query='x' * 300)):
            action = dict(kind='search_stock', query='verify', prefix='python/sglang/', offset=0)
            action.update(changes)
            with self.assertRaises(ValueError):
                self.access.dispatch(self.root, action, self.root / 'bad')

    def test_network_uses_normalized_auditable_dispatch_not_a_raw_ok_status(self):
        expected = dict(status='completed', content='public technical facts')
        action = dict(kind='search_public', query='speculative decoding performance model')
        with patch('harness.research_knowledge.dispatch_public', return_value=expected) as fetch, \
                patch('harness.research_knowledge.trusted_proxy_transport', return_value=None):
            self.assertEqual(self.access.dispatch(self.root, action, self.root / 'network'), expected)
        fetch.assert_called_once_with(action, self.root / 'network', transport=None)

    def test_four_axes_require_all_dimensions_and_no_evidence_means_not_explore(self):
        values = [dict(axis=name, findings='Need a workload-specific observation', evidence_calls=[],
            unknowns=['Runtime attribution is missing'], priority='diagnose',
            benefit_assessment='Unknown net benefit; do not assume zero overhead') for name in sorted(AXES)]
        self.assertEqual(validate_axes(values, self.root), values)
        with self.assertRaises(ValueError):
            validate_axes(values[:-1], self.root)
        values[0]['priority'] = 'explore'
        with self.assertRaises(ValueError):
            validate_axes(values, self.root)

    def test_authored_file_alone_is_not_factual_support_for_an_exploration_axis(self):
        directory = self.root / 'tools-01/action-001'
        directory.mkdir(parents=True)
        (directory / 'request.json').write_text(json.dumps(dict(arguments=dict(action=dict(
            kind='write_file', path='scratch/claim.txt', content='unverified assertion')))))
        (directory / 'response.json').write_text(json.dumps(dict(success=True,
            contentItems=[dict(type='inputText', text=json.dumps(dict(status='completed')))])))
        values = [dict(axis=name, findings='A claimed opportunity', evidence_calls=['tools-01/action-001'],
            unknowns=['No measured or source observation'], priority='explore',
            benefit_assessment='Conditional estimate remains unverified') for name in sorted(AXES)]
        with self.assertRaises(ValueError):
            validate_axes(values, self.root)

    def test_new_campaign_does_not_reuse_old_job_prefix_or_budget(self):
        with patch('exp.skill_rsi.subprocess.check_output', return_value='a' * 40):
            campaign = MasterCampaign(self.root, self.root / 'inputs', self.root / 'tools', {}, self.root / 'preflight')
        self.assertEqual(campaign.job_prefix, 'sp-masterprop-20261111-a01')
        self.assertEqual(campaign.budget.read()['gpu_seconds'], 28800)


if __name__ == '__main__':
    unittest.main()
