import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from harness.master_proposal import validate_estimate_review, validate_proposals


class MasterProposalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stock = self.root / 'stock'
        self.role = self.root / 'master'
        self.path = 'python/sglang/srt/example.py'
        self.source = 'def process(values):\n    previous = list(values)\n    return list(previous)\n'
        destination = self.stock / self.path
        destination.parent.mkdir(parents=True)
        destination.write_text(self.source)
        self.digest = hashlib.sha256(self.source.encode()).hexdigest()
        self.receipt('tools-01/action-001', dict(kind='read_stock', path=self.path, offset=0),
                     dict(status='completed', content=self.source, sha256=self.digest))
        self.receipt('tools-01/action-002', dict(kind='get_baseline_stats'),
                     dict(status='completed', protocol='acceptance-evidence-v1', tau=5, scope='public stock'))
        self.scenario('tools-01/action-003', 1, 1.01)
        self.scenario('tools-01/action-004', 1, 0.98)

    def scenario(self, identity, tau, cost, *, extra=0):
        from harness.acceptance_evidence import estimate_conditional
        action = dict(kind='estimate_scenario', tau_ratio=tau, step_cost_ratio=cost,
            extra_step_cost_ratio=extra, assumptions=['Conditional fixture; not measured candidate benefit'])
        result = estimate_conditional(**{key:value for key,value in action.items() if key != 'kind'})
        self.receipt(identity, action, dict(status='completed', scenario=result))

    def receipt(self, name, action, answer):
        directory = self.role / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'request.json').write_text(json.dumps(dict(arguments=dict(action=action))))
        (directory / 'response.json').write_text(json.dumps(dict(success=True,
            contentItems=[dict(type='inputText', text=json.dumps(answer))])))

    def proposal(self):
        return dict(directions=[dict(id='d1', brief='Investigate repeated materialization without aliasing changes',
            allocation=dict(actions=120, cpu_runs=24, gpu_attempts=2), proposal=dict(
                changes=[dict(path=self.path, symbol='process', source_sha256=self.digest,
                    source_call='tools-01/action-001', quote='previous = list(values)',
                    mechanism='Retain independent output ownership while removing one redundant materialization')],
                invariants=['Preserve values and independent output storage'],
                risks=['Input mutation and aliasing require explicit differential checks'],
                benefit=dict(model='acceptance_over_step_cost', baseline_calls=[
                    'tools-01/action-002', 'tools-01/action-003', 'tools-01/action-004'],
                    acceptance_ratio=[1, 1], step_cost_ratio=[0.98, 1.01], net_speedup=[1 / 1.01, 1 / 0.98],
                    saved_work='One materialization in a source-level conditional model',
                    added_cost='Potential lifetime and allocation overhead included in cost ratio',
                    assumptions=['Conditional cost ratios, not measured candidate throughput'],
                    unknowns=['Runtime path and wall-time contribution remain unverified'], next_action='implement'),
                validation=dict(correctness='Differential and aliasing cases; default off must reproduce stock',
                    path_hit='Demonstrate actual option execution in the public workload',
                    performance='Controller paired requests with fresh servers and GPU swap',
                    stop='Stop on numerical mismatch or no credible speedup'), external_sources=[]))])

    def check(self, value):
        return validate_proposals(value, self.role, self.stock)

    def test_source_grounded_conditional_proposal_is_not_scientific_acceptance(self):
        result = self.check(self.proposal())
        self.assertEqual(result[0]['id'], 'd1')
        self.assertIn('proposal', result[0])

    def test_generic_direction_without_mechanism_rejected(self):
        value = self.proposal()
        del value['directions'][0]['proposal']
        with self.assertRaises(ValueError):
            self.check(value)

    def test_wrong_source_sha_unread_quote_and_unknown_function_rejected(self):
        for field, replacement in (('source_sha256', '0' * 64), ('quote', 'invented operation'),
                                   ('symbol', 'missing'), ('source_call', '../other-role/action-001')):
            value = self.proposal()
            value['directions'][0]['proposal']['changes'][0][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(value)

    def test_other_function_quote_cannot_ground_selected_function(self):
        original = self.stock / self.path
        original.write_text(self.source + '\ndef unrelated():\n    return 123\n')
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        self.receipt('tools-01/action-001', dict(kind='read_stock', path=self.path, offset=0),
                     dict(status='completed', content=original.read_text(), sha256=digest))
        value = self.proposal()
        value['directions'][0]['proposal']['changes'][0].update(source_sha256=digest, quote='return 123')
        with self.assertRaises(ValueError):
            self.check(value)

    def test_unknown_cost_cannot_claim_net_gain_or_implementation(self):
        value = self.proposal()
        benefit = value['directions'][0]['proposal']['benefit']
        benefit.update(model='unquantified', acceptance_ratio=None, step_cost_ratio=None, net_speedup=None)
        with self.assertRaises(ValueError):
            self.check(value)
        benefit['next_action'] = 'diagnose'
        self.assertEqual(self.check(value)[0]['proposal']['benefit']['net_speedup'], None)

    def test_more_acceptance_does_not_ignore_extra_step_cost(self):
        value = self.proposal()
        benefit = value['directions'][0]['proposal']['benefit']
        benefit.update(acceptance_ratio=[1.2, 1.2], step_cost_ratio=[1.3, 1.4], net_speedup=[1.2, 1.2])
        with self.assertRaises(ValueError):
            self.check(value)
        benefit['net_speedup'] = [1.2 / 1.4, 1.2 / 1.3]
        self.scenario('tools-01/action-003', 1.2, 1.4)
        self.scenario('tools-01/action-004', 1.2, 1.3)
        self.assertLess(self.check(value)[0]['proposal']['benefit']['net_speedup'][1], 1)

    def test_repeated_quote_in_an_unread_function_cannot_ground_the_proposal(self):
        source = self.source + '\n' + '# padding\n' * 1300 + '\ndef unread(values):\n    previous = list(values)\n    return previous\n'
        (self.stock / self.path).write_text(source)
        digest = hashlib.sha256(source.encode()).hexdigest()
        self.receipt('tools-01/action-001', dict(kind='read_stock', path=self.path, offset=0),
            dict(status='completed', content=source[:12000], sha256=digest))
        value = self.proposal()
        value['directions'][0]['proposal']['changes'][0].update(symbol='unread', source_sha256=digest)
        with self.assertRaises(ValueError):
            self.check(value)

    def test_unavailable_baseline_cannot_support_quantified_implementation(self):
        self.receipt('tools-01/action-002', dict(kind='get_baseline_stats'), dict(status='unavailable'))
        with self.assertRaises(ValueError):
            self.check(self.proposal())

    def test_estimator_unknown_extra_cost_cannot_be_overridden_by_handwritten_gain(self):
        self.scenario('tools-01/action-003', 1, 1.01, extra=None)
        with self.assertRaises(ValueError):
            self.check(self.proposal())

    def test_missing_cost_or_correctness_explanation_rejected(self):
        for group, field in (('benefit', 'added_cost'), ('benefit', 'saved_work'),
                             ('validation', 'correctness'), ('validation', 'path_hit')):
            value = self.proposal()
            value['directions'][0]['proposal'][group][field] = ''
            with self.subTest(group=group, field=field), self.assertRaises(ValueError):
                self.check(value)

    def test_invalid_ratios_rejected(self):
        for ratio in ([True, 1], [0, 1], [2, 1], [1, float('nan')], [1, float('inf')]):
            value = self.proposal()
            value['directions'][0]['proposal']['benefit']['step_cost_ratio'] = ratio
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                self.check(value)

    def test_unretrieved_external_reference_rejected(self):
        value = self.proposal()
        value['directions'][0]['proposal']['external_sources'] = [dict(call='tools-01/action-099', reuse='background')]
        with self.assertRaises((ValueError, OSError)):
            self.check(value)

    def test_failed_baseline_receipt_and_unbounded_allocation_rejected(self):
        value = self.proposal()
        value['directions'][0]['allocation']['gpu_attempts'] = 100
        with self.assertRaises(ValueError):
            self.check(value)
        value = self.proposal()
        self.receipt('tools-01/action-002', dict(kind='get_baseline_stats'), dict(status='failed'))
        with self.assertRaises(ValueError):
            self.check(value)

    def test_forecast_review_must_use_actual_controller_statistic(self):
        feedback = [dict(role_label='direction-d1', status='completed', geomean=0.9)]
        review = dict(estimate_reviews=[dict(id='d1', observed_geomean=0.9,
            forecast_supported=False, revision='The assumed saving did not translate into system throughput')])
        validate_estimate_review(review, {'d1':self.proposal()['directions'][0]}, feedback)
        review['estimate_reviews'][0]['observed_geomean'] = 1.1
        with self.assertRaises(ValueError):
            validate_estimate_review(review, {'d1':{}}, feedback)

    def test_unmeasured_proposal_cannot_claim_forecast_confirmed(self):
        review = dict(estimate_reviews=[dict(id='d1', observed_geomean=None,
            forecast_supported=True, revision='No actual GPU measurement exists')])
        with self.assertRaises(ValueError):
            validate_estimate_review(review, {'d1':{}}, [])
        review['estimate_reviews'][0]['forecast_supported'] = None
        validate_estimate_review(review, {'d1':{}}, [])

    def test_estimate_review_cannot_omit_a_direction(self):
        with self.assertRaises(ValueError):
            validate_estimate_review(dict(estimate_reviews=[]), {'d1':{}}, [])


if __name__ == '__main__':
    unittest.main()
