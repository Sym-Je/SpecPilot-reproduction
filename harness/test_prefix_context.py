"""Prefix controls preserve task identity and retain physical-round clustering."""

import copy
import unittest

from controller.http_transport import sha_ids
from exp.long_context import condition_keys, summarize
from harness.prefix_context import CONDITIONS, SUITES, text_sha, validate


class PrefixContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = dict(base_requests=[], requests=[])
        for suite in SUITES:
            for index in range(2):
                name = suite + '-' + str(index)
                base = dict(id=name, suite=suite, question=name, question_sha256=text_sha(name),
                    input_ids=[1, 2, 3], input_sha256=sha_ids([1, 2, 3]), chat_prefix_ids=[1],
                    question_suffix_ids=[2, 3], document_prefix_ids=list(range(100, 100 + 65536)))
                cls.record['base_requests'].append(base)
                for condition in CONDITIONS:
                    ids = base['input_ids'] if condition == 'original' else [1] + base['document_prefix_ids'][:int(condition) - 3] + [2, 3]
                    cls.record['requests'].append(dict(id=name + '-ctx-' + condition, base_id=name, suite=suite,
                        condition=condition, context_tokens=len(ids), input_ids=ids, input_sha256=sha_ids(ids),
                        question_sha256=base['question_sha256']))

    def test_fifty_valid_requests(self):
        self.assertTrue(validate(self.record))
        self.assertEqual(condition_keys(self.record['requests']), list(CONDITIONS))

    def test_altered_question_rejected(self):
        record = copy.deepcopy(self.record)
        record['base_requests'][0]['question'] += 'altered'
        with self.assertRaises(ValueError):
            validate(record)

    def test_original_control_must_be_identical(self):
        record = copy.deepcopy(self.record)
        record['requests'][0]['input_ids'] = [1, 4, 3]
        record['requests'][0]['input_sha256'] = sha_ids([1, 4, 3])
        with self.assertRaises(ValueError):
            validate(record)

    def test_suffix_change_rejected(self):
        record = copy.deepcopy(self.record)
        item = record['requests'][1]
        item['input_ids'][-1] = 9
        item['input_sha256'] = sha_ids(item['input_ids'])
        with self.assertRaises(ValueError):
            validate(record)

    def test_repeated_padding_rejected(self):
        record = copy.deepcopy(self.record)
        item = record['requests'][1]
        item['input_ids'][5] = item['input_ids'][4]
        item['input_sha256'] = sha_ids(item['input_ids'])
        with self.assertRaises(ValueError):
            validate(record)

    def test_missing_condition_rejected(self):
        record = dict(self.record, requests=self.record['requests'][:-1])
        with self.assertRaises(ValueError):
            validate(record)

    def test_variable_original_lengths_grouped_as_one_condition(self):
        requests = self.record['requests'][:5]
        gpus = [dict(uuid='GPU-first'), dict(uuid='GPU-second')]
        pairs = []
        for item in requests:
            for number in (1, 2):
                assigned = gpus if number == 1 else list(reversed(gpus))
                rows = {key: dict(arm=role, gpu_uuid=gpu['uuid'], input_sha256=item['input_sha256'],
                    output_ids=[8, 9], output_sha256=sha_ids([8, 9]), tokens=2, tokens_per_s=speed,
                    latency_ms=2000 / speed, finish_reason='stop')
                    for key, role, gpu, speed in zip(('a', 'b'), ('stock', 'final'), assigned, (10., 20.))}
                pairs.append(dict(id=item['id'], condition=item['condition'], context_tokens=item['context_tokens'], round=number, **rows))
        result = summarize(pairs, requests, gpus)
        self.assertEqual(result['protocol'], 'author-dev-prefix-context-v1')
        self.assertEqual(result['conditions']['original']['requests'], 1)
        self.assertAlmostEqual(result['conditions']['65536']['speedup']['geomean'], 2.)


if __name__ == '__main__':
    unittest.main()
