import json
import tempfile
import unittest
from pathlib import Path

from controller.http_transport import sha_ids
from exp.p3_pair_run import SUITES, summarize
from harness.baseline_validation import validate_baseline


class BaselineValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def fixture(self, speedup=4.0, swap=True, per_suite=4):
        requests = [{'id': f'{suite}-{index}', 'suite': suite, 'turn': 0,
                     'input_ids': [100, index], 'input_sha256': sha_ids([100, index])}
                    for suite in SUITES for index in range(per_suite)]
        arms = [{'name': name, 'block': block, 'tree_sha': 'a' * 64, 'env': {}}
                for name, block in (('ar', 0), ('stock', 8))]
        self.write(self.root / 'manifest.json', {
            'arms': arms, 'rounds': 2, 'per_suite': per_suite, 'max_new_tokens': 2048,
            'warmup': 2, 'suites': SUITES, 'requests': requests,
            'sampling': {'temperature': 0.0, 'top_k': 1, 'enable_thinking': True}})
        all_pairs = []
        for round_number in (1, 2):
            directory = self.root / f'round-{round_number:02d}'
            directory.mkdir()
            uuids = ['gpu-0', 'gpu-1']
            if round_number == 2 and swap:
                uuids.reverse()
            self.write(directory / 'deployment.json', {'assignments': [
                {'arm': arm, 'gpu': {'uuid': uuid}} for arm, uuid in zip(arms, uuids)]})
            pairs = []
            for request in requests:
                rows = []
                for arm, uuid, throughput in zip(arms, uuids, (1.0, speedup)):
                    rows.append({'id': request['id'], 'suite': request['suite'], 'turn': 0,
                        'arm': arm['name'], 'block': arm['block'], 'tree_sha': arm['tree_sha'],
                        'round': round_number, 'gpu_uuid': uuid,
                        'input_sha256': request['input_sha256'], 'output_ids': [9, 10],
                        'output_sha256': sha_ids([9, 10]), 'tokens': 2, 'completion_tokens': 2,
                        'max_new_tokens': 2048, 'tokens_per_s': throughput,
                        'finish_reason': 'stop'})
                pairs.append({'id': request['id'], 'suite': request['suite'],
                              'round': round_number, 'a': rows[0], 'b': rows[1]})
            for name, rows in (('pairs', pairs), ('ar', [pair['a'] for pair in pairs]),
                               ('stock', [pair['b'] for pair in pairs])):
                (directory / f'{name}.jsonl').write_text(
                    ''.join(json.dumps(row) + '\n' for row in rows))
            self.write(directory / 'complete.json', {'round': round_number, 'pairs': len(requests)})
            all_pairs.extend(pairs)
        summary = summarize(all_pairs, requests, 2, iters=64)
        summary.update(arms=['ar', 'stock'], max_new_tokens=2048, per_suite_requested=per_suite,
                       acceptance={'target': 3.95, 'relative_tolerance': 0.10,
                                   'passed': 3.95 * 0.9 <= speedup <= 3.95 * 1.1})
        self.write(self.root / 'summary.json', summary)

    def alter_json(self, relative, update):
        path = self.root / relative
        value = json.loads(path.read_text())
        update(value)
        self.write(path, value)

    def test_complete_baseline_and_natural_eos_are_accepted(self):
        self.fixture()
        result = validate_baseline(self.root)
        self.assertTrue(result['protocol_passed'])
        self.assertTrue(result['diagnostic_passed'])
        self.assertEqual(result['pairs'], 40)
        self.assertEqual(result['arm_rows'], 80)
        self.assertEqual(result['actual_lengths']['ar']['min'], 2)
        self.assertFalse(result['ledger_eligible'])

    def test_outside_reference_is_reported_not_relaxed(self):
        self.fixture(speedup=2.0)
        result = validate_baseline(self.root)
        self.assertTrue(result['protocol_passed'])
        self.assertFalse(result['diagnostic_passed'])

    def test_no_physical_swap_is_rejected(self):
        self.fixture(swap=False)
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_wrong_protocol_is_rejected(self):
        self.fixture()
        self.alter_json('manifest.json', lambda value: value.update(max_new_tokens=64))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_missing_arm_row_is_rejected(self):
        self.fixture()
        path = self.root / 'round-02/stock.jsonl'
        path.write_text('\n'.join(path.read_text().splitlines()[:-1]) + '\n')
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_failed_attempt_is_rejected(self):
        self.fixture()
        self.write(self.root / 'failed.json', {'error': 'injected'})
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_relaxed_reference_is_rejected(self):
        self.fixture()
        self.alter_json('summary.json', lambda value: value['acceptance'].update(target=2.0))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_incorrect_statistic_is_rejected(self):
        self.fixture()
        self.alter_json('summary.json', lambda value: value.update(geomean=99.0))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_changed_request_hash_is_rejected(self):
        self.fixture()
        self.alter_json('manifest.json', lambda value: value['requests'][0].update(input_sha256='bad'))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_uncontrolled_sampling_is_rejected(self):
        self.fixture()
        self.alter_json('manifest.json', lambda value: value['sampling'].update(temperature=0.5))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def alter_first_pair(self, update):
        directory = self.root / 'round-01'
        pairs = [json.loads(line) for line in (directory / 'pairs.jsonl').read_text().splitlines()]
        update(pairs[0])
        for name, rows in (('pairs', pairs), ('ar', [pair['a'] for pair in pairs]),
                           ('stock', [pair['b'] for pair in pairs])):
            (directory / f'{name}.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def test_mismatched_paired_input_is_rejected(self):
        self.fixture()
        self.alter_first_pair(lambda pair: pair['b'].update(input_sha256='bad'))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_output_hash_corruption_is_rejected(self):
        self.fixture()
        self.alter_first_pair(lambda pair: pair['a'].update(output_ids=[99, 100]))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)

    def test_exceeded_token_cap_is_rejected(self):
        self.fixture()
        self.alter_first_pair(lambda pair: pair['a'].update(
            tokens=2049, completion_tokens=2049, output_ids=[9] * 2049,
            output_sha256=sha_ids([9] * 2049)))
        with self.assertRaises(ValueError):
            validate_baseline(self.root)


if __name__ == '__main__':
    unittest.main()
