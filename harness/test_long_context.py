"""Reject incomplete, truncated or unpaired long-context evidence."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from controller.http_transport import sha_ids
from exp.long_context import CAP, LENGTHS, summarize, validate_requests


class LongContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = [dict(id=f'{document}-{length}', document=document, suite='novel-summary',
            context_tokens=length, input_ids=[document_index + 1] * length,
            input_sha256=sha_ids([document_index + 1] * length))
            for length in LENGTHS for document_index, document in enumerate(('first', 'second', 'third'))]
        cls.gpus = [dict(uuid='GPU-first'), dict(uuid='GPU-second')]

    def pairs(self):
        pairs = []
        for number in (1, 2):
            assigned = self.gpus if number == 1 else list(reversed(self.gpus))
            for item in self.requests:
                rows = {}
                for key, role, gpu, speed in zip(('a', 'b'), ('stock', 'final'), assigned, (10., 20.)):
                    rows[key] = dict(arm=role, gpu_uuid=gpu['uuid'], input_sha256=item['input_sha256'],
                        tokens=2, output_ids=[7, 8], output_sha256=sha_ids([7, 8]), tokens_per_s=speed,
                        latency_ms=2000 / speed, finish_reason='stop')
                pairs.append(dict(id=item['id'], round=number, context_tokens=item['context_tokens'], **rows))
        return pairs

    def test_exact_lengths(self):
        validate_requests(self.requests)

    def test_short_input_rejected(self):
        requests = copy.deepcopy(self.requests)
        requests[0]['input_ids'].pop()
        with self.assertRaises(ValueError):
            validate_requests(requests)

    def test_duplicate_request_rejected(self):
        requests = list(self.requests)
        requests[-1] = requests[0]
        with self.assertRaises(ValueError):
            validate_requests(requests)

    def test_geomean_and_cluster(self):
        result = summarize(self.pairs(), self.requests, self.gpus)
        for condition in result['conditions'].values():
            self.assertTrue(condition['complete'])
            self.assertAlmostEqual(condition['speedup']['geomean'], 2.)
        self.assertFalse(result['ledger_eligible'])

    def test_missing_pair_never_complete(self):
        pairs = self.pairs()
        pairs.pop()
        result = summarize(pairs, self.requests, self.gpus)
        self.assertFalse(result['conditions']['131072']['complete'])
        self.assertNotIn('speedup', result['conditions']['131072'])

    def test_missing_physical_swap_rejected(self):
        pairs = self.pairs()
        pairs[15]['a']['gpu_uuid'] = self.gpus[0]['uuid']
        with self.assertRaises(ValueError):
            summarize(pairs, self.requests, self.gpus)

    def test_duplicate_pair_rejected(self):
        pairs = self.pairs()
        with self.assertRaises(ValueError):
            summarize(pairs + pairs[:1], self.requests, self.gpus)

    def test_modified_output_rejected(self):
        pairs = self.pairs()
        pairs[0]['a']['output_ids'] = [9, 8]
        with self.assertRaises(ValueError):
            summarize(pairs, self.requests, self.gpus)

    def test_truncated_http_input_rejected(self):
        pairs = self.pairs()[:1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            item = self.requests[0]
            for key in ('a', 'b'):
                packet = dict(http_status=200,
                    request=dict(input_ids=item['input_ids'], sampling_params=dict(temperature=0., top_k=1, max_new_tokens=CAP)),
                    response=dict(output_ids=[7, 8], meta_info=dict(prompt_tokens=128, completion_tokens=2)))
                path = root / f'{key}.json'
                path.write_text(json.dumps(packet))
                import hashlib
                pairs[0][key]['raw_evidence'] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, 'truncated'):
                summarize(pairs, self.requests, self.gpus, root)


if __name__ == '__main__':
    unittest.main()
