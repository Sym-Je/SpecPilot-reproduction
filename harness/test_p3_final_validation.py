import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.http_transport import sha_ids
from exp.p3_pair_run import SUITES, summarize
from harness.final_validation import validate_final


class FinalValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.reference = self.root / 'baseline'
        self.run = self.root / 'final'
        self.config = {'stock': {'block_size': 8}, 'final': {
            'block_size': 32, 'env': {f'SPECPILOT_TEST_{index}': '1' for index in range(46)}}}
        identity = patch('harness.final_validation.final_identity', return_value=(self.config, 'b' * 64))
        identity.start()
        self.addCleanup(identity.stop)
        self.requests = [{'id': f'{suite}-{index}', 'suite': suite, 'turn': 0,
                          'input_ids': [100, index], 'input_sha256': sha_ids([100, index])}
                         for suite in SUITES for index in range(4)]
        self.make_run(self.reference, ['ar', 'stock'], 4.0)

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def make_run(self, directory, names, speedup, swap=True):
        directory.mkdir()
        specs = {'ar': {'block': 0, 'tree_sha': 'a' * 64, 'env': {}},
                 'stock': {'block': 8, 'tree_sha': 'a' * 64, 'env': {}},
                 'final': {'block': 32, 'tree_sha': 'b' * 64, 'env': self.config['final']['env']}}
        arms = [dict(specs[name], name=name) for name in names]
        self.write(directory / 'manifest.json', {'arms': arms, 'rounds': 2, 'per_suite': 4,
            'max_new_tokens': 2048, 'warmup': 2, 'suites': SUITES, 'requests': self.requests,
            'model_path': '/test/target', 'declared_models': {'target': 'target', 'draft': 'draft'},
            'sampling': {'temperature': 0.0, 'top_k': 1, 'enable_thinking': True}})
        all_pairs = []
        for number in (1, 2):
            round_dir = directory / f'round-{number:02d}'
            round_dir.mkdir()
            uuids = ['gpu-0', 'gpu-1']
            if number == 2 and swap:
                uuids.reverse()
            self.write(round_dir / 'deployment.json', {'assignments': [
                {'arm': arm, 'gpu': {'uuid': uuid}} for arm, uuid in zip(arms, uuids)]})
            pairs = []
            for request in self.requests:
                rows = []
                for arm, uuid, throughput in zip(arms, uuids, (1.0, speedup)):
                    rows.append({'id': request['id'], 'suite': request['suite'], 'turn': 0,
                        'arm': arm['name'], 'block': arm['block'], 'tree_sha': arm['tree_sha'],
                        'round': number, 'gpu_uuid': uuid, 'input_sha256': request['input_sha256'],
                        'output_ids': [9, 10], 'output_sha256': sha_ids([9, 10]),
                        'tokens': 2, 'completion_tokens': 2, 'max_new_tokens': 2048,
                        'tokens_per_s': throughput, 'finish_reason': 'stop'})
                pairs.append({'id': request['id'], 'suite': request['suite'], 'round': number,
                              'a': rows[0], 'b': rows[1]})
            for name, rows in (('pairs', pairs), (names[0], [pair['a'] for pair in pairs]),
                               (names[1], [pair['b'] for pair in pairs])):
                (round_dir / f'{name}.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            self.write(round_dir / 'complete.json', {'round': number, 'pairs': 20})
            all_pairs.extend(pairs)
        summary = summarize(all_pairs, self.requests, 2, iters=64)
        summary.update(arms=names, max_new_tokens=2048, per_suite_requested=4)
        if names == ['ar', 'stock']:
            summary['acceptance'] = {'target': 3.95, 'relative_tolerance': 0.1,
                                     'passed': 3.95 * 0.9 <= speedup <= 3.95 * 1.1}
        self.write(directory / 'summary.json', summary)

    def alter(self, relative, update):
        path = self.run / relative
        value = json.loads(path.read_text())
        update(value)
        self.write(path, value)

    def test_ar_final_is_directly_validated(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        result = validate_final(self.run, self.reference)
        self.assertEqual(result['comparison'], 'final/ar')
        self.assertEqual(result['pairs'], 40)
        self.assertEqual(result['final_env_options'], 46)
        self.assertTrue(result['baseline_requests_match'])

    def test_stock_final_is_directly_validated(self):
        self.make_run(self.run, ['stock', 'final'], 2.0)
        result = validate_final(self.run, self.reference)
        self.assertEqual(result['comparison'], 'final/stock')
        self.assertEqual(result['geomean'], 2.0)

    def test_low_speedup_is_retained_without_invented_numeric_gate(self):
        self.make_run(self.run, ['stock', 'final'], 1.5)
        result = validate_final(self.run, self.reference)
        self.assertTrue(result['protocol_passed'])
        self.assertNotIn('diagnostic_passed', result)
        self.assertFalse(result['ledger_eligible'])

    def test_missing_final_option_is_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.alter('manifest.json', lambda value: value['arms'][1]['env'].pop('SPECPILOT_TEST_0'))
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_wrong_final_tree_is_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.alter('manifest.json', lambda value: value['arms'][1].update(tree_sha='a' * 64))
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_changed_requests_are_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.alter('manifest.json', lambda value: value['requests'][0].update(input_ids=[999]))
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_changed_model_identity_is_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.alter('manifest.json', lambda value: value.update(model_path='/other/target'))
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_ar_stock_threshold_cannot_be_applied_to_final(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.alter('summary.json', lambda value: value.update(acceptance={'passed': True}))
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_missing_physical_swap_is_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0, swap=False)
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_failed_a1_reference_is_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.write(self.reference / 'failed.json', {'error': 'injected'})
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)

    def test_changed_statistics_are_rejected(self):
        self.make_run(self.run, ['ar', 'final'], 8.0)
        self.alter('summary.json', lambda value: value.update(geomean=99.0))
        with self.assertRaises(ValueError):
            validate_final(self.run, self.reference)


if __name__ == '__main__':
    unittest.main()
