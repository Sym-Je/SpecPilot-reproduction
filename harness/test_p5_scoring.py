import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class NativeScoringTests(unittest.TestCase):
    def fixture(self):
        return {'meta_info': {'input_token_logprobs': [[None, 2], [-.2, 3], [-.3, 4], [-1.1, 5]],
                'input_top_logprobs': [None, [[-.2, 3]], [[-.3, 4]], [[-.1, 6]]]}}

    def test_native_scores_are_aligned_to_each_output_own_prefix(self):
        from controller.scoring import decode_scores
        from controller.http_transport import sha_ids
        scores = decode_scores(self.fixture(), [2, 3], [4, 5])
        self.assertEqual([row['token'] for row in scores], [4, 5])
        self.assertEqual([row['argmax'] for row in scores], [4, 6])
        self.assertAlmostEqual(scores[1]['margin'], 1)
        self.assertEqual(scores[1]['prefix_sha256'], sha_ids([2, 3, 4]))

    def test_missing_shifted_nonfinite_or_impossible_scores_fail_closed(self):
        from controller.scoring import decode_scores
        for change in ('missing', 'shifted', 'nonfinite', 'negative-margin'):
            response = self.fixture()
            if change == 'missing': response['meta_info']['input_token_logprobs'].pop()
            if change == 'shifted': response['meta_info']['input_token_logprobs'][2][1] = 9
            if change == 'nonfinite': response['meta_info']['input_top_logprobs'][3][0][0] = float('nan')
            if change == 'negative-margin': response['meta_info']['input_top_logprobs'][3][0][0] = -2
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_scores(response, [2, 3], [4, 5])
        for prompt, output in (([], [1]), ([1], []), ([True], [1])):
            with self.assertRaises(ValueError): decode_scores(self.fixture(), prompt, output)

    def test_native_client_records_raw_evidence_and_checks_fp32_identity(self):
        from controller.scoring import NativeClient
        with tempfile.TemporaryDirectory() as directory:
            client = NativeClient('http://local', Path(directory))
            with patch('controller.scoring.urllib.request.urlopen') as request:
                request.return_value.__enter__.return_value.status = 200
                request.return_value.__enter__.return_value.read.return_value = json.dumps(self.fixture()).encode()
                result = client.post('/generate', {'input_ids': [2, 3, 4, 5]})
            self.assertEqual(result, self.fixture())
            saved = json.loads(next(Path(directory).glob('*.json')).read_text())
            self.assertEqual(saved['request']['input_ids'], [2, 3, 4, 5])
            self.assertIn('response', saved)
            with patch.object(client, 'get', return_value={'server_args': {'enable_fp32_lm_head': False}}):
                with self.assertRaises(ValueError): client.scorer_identity('stock-tree')

    def test_prefix_hashes_match_canonical_json(self):
        from controller.scoring import prefix_hashes
        from controller.http_transport import sha_ids
        expected = [sha_ids([2, 3] + [4, 5, 6][:number]) for number in range(3)]
        self.assertEqual(prefix_hashes([2, 3], [4, 5, 6]), expected)
