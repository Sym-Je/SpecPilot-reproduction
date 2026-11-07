import json
import math
import unittest

from controller.null_validation import validate_null
from controller.stats import stratified_geomean_ci
from exp.p3_pair_run import arm_specs, clean_environment
from harness import test_p3_baseline_validation as baseline_tests


class NullValidationTests(unittest.TestCase):
    def setUp(self):
        helper = baseline_tests.BaselineValidationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.fixture(speedup=1.0)
        self.root = helper.root
        arms, _ = arm_specs(['stock-a', 'stock-b'], clean_environment())
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest['arms'] = arms
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        summary = json.loads((self.root / 'summary.json').read_text())
        summary['arms'] = ['stock-a', 'stock-b']
        summary.pop('acceptance')
        (self.root / 'summary.json').write_text(json.dumps(summary))
        for number in (1, 2):
            directory = self.root / f'round-{number:02d}'
            deployment = json.loads((directory / 'deployment.json').read_text())
            for entry, arm in zip(deployment['assignments'], arms):
                entry['arm'] = arm
            (directory / 'deployment.json').write_text(json.dumps(deployment))
            pairs = [json.loads(line) for line in (directory / 'pairs.jsonl').read_text().splitlines()]
            for pair in pairs:
                for key, arm in zip(('a', 'b'), arms):
                    pair[key].update(arm=arm['name'], block=8, tree_sha=arm['tree_sha'])
            for old in ('ar', 'stock'):
                (directory / f'{old}.jsonl').unlink()
            records = {'pairs': pairs, 'stock-a': [pair['a'] for pair in pairs],
                       'stock-b': [pair['b'] for pair in pairs]}
            for name, rows in records.items():
                (directory / f'{name}.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def test_complete_identical_null_is_valid_but_not_lossless_evidence(self):
        result = validate_null(self.root)
        self.assertTrue(result['precision_passed'])
        self.assertEqual(result['interval_width'], 0)
        self.assertEqual(result['noise'], 0)
        self.assertEqual(result['ci95'], [result['interval']['lower'], result['interval']['upper']])
        self.assertIn('suite-stratified', result['ci_method'])
        self.assertFalse(result['ledger_eligible'])
        self.assertEqual(result['width_limit'], .002)

    def test_hidden_deployment_identity_change_is_rejected(self):
        path = self.root / 'round-02/deployment.json'
        value = json.loads(path.read_text())
        value['assignments'][0]['arm']['env'] = {'unexpected': '1'}
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            validate_null(self.root)

    def test_stock_options_must_match_frozen_configuration(self):
        path = self.root / 'manifest.json'
        value = json.loads(path.read_text())
        value['arms'][0]['block'] = 16
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            validate_null(self.root)

    def test_wide_intervals_are_not_relaxed(self):
        with unittest.mock.patch('controller.null_validation.stratified_geomean_ci',
                                 return_value={'lower': .99, 'upper': 1.01, 'method': 'synthetic'}):
            result = validate_null(self.root)
        self.assertFalse(result['precision_passed'])
        self.assertAlmostEqual(result['interval_width'], .02)
        self.assertEqual(result['width_limit'], .002)


class StratifiedStatisticsTests(unittest.TestCase):
    def test_benchmark_weights_are_equal_not_token_or_sample_weighted(self):
        result = stratified_geomean_ci({'small': [0], 'large': [math.log(4)] * 5}, iters=100)
        self.assertAlmostEqual(result['geomean'], 2)
        self.assertAlmostEqual(result['lower'], 2)
        self.assertAlmostEqual(result['upper'], 2)
        self.assertEqual(result['confidence_level'], .95)

    def test_seed_and_coverage_are_explicit(self):
        groups = {'one': [-.01, .01], 'two': [-.02, .02]}
        first = stratified_geomean_ci(groups, iters=100, seed=7)
        self.assertEqual(first, stratified_geomean_ci(groups, iters=100, seed=7))
        for invalid in ({}, {'empty': []}, {'nan': [float('nan')]}):
            with self.assertRaises(ValueError):
                stratified_geomean_ci(invalid)


if __name__ == '__main__':
    unittest.main()
