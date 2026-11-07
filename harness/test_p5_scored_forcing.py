import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from controller.http_transport import sha_ids
from controller.scoring import decode_scores


class ScoredForcingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.counter = 0

    def save(self, value):
        self.counter += 1
        path = self.root / f'{self.counter}.json'
        path.write_text(json.dumps(value))
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def trace(self, output, mismatches=None, role='stock', request_id='one', prompt=None):
        mismatches = mismatches or {}
        prompt = prompt or [2, 3]
        args = dict(model_path='/model', dtype='bfloat16', enable_fp32_lm_head=True,
                    speculative_algorithm=None, chunked_prefill_size=8192,
                    enable_return_hidden_states=True, return_hidden_states_mode='last')
        identity = dict(tree_sha='a' * 64, server_args=args,
                        evidence=self.save({'http_status': 200, 'response': {'server_args': args}}))
        all_tokens = prompt + output
        actual = [[None, 2]] + [[-.1, token] for token in all_tokens[1:]]
        tops = [None] + [[[ -.1, token ]] for token in all_tokens[1:]]
        for index, (best, margin) in mismatches.items():
            actual[len(prompt) + index][0] = -.1 - margin
            tops[len(prompt) + index] = [[-.1, best]]
        response = {'meta_info': {'input_token_logprobs': actual, 'input_top_logprobs': tops}}
        body = dict(input_ids=all_tokens, return_logprob=True, logprob_start_len=0,
                    top_logprobs_num=1, sampling_params={'max_new_tokens': 1})
        raw = self.save({'http_status': 200, 'request': body, 'response': response})
        generator_args = dict(args, enable_fp32_lm_head=False,
                              speculative_algorithm='DFLASH' if role == 'stock' else None,
                              speculative_num_draft_tokens=8 if role == 'stock' else None)
        generator = dict(tree_sha='a' * 64, server_args=generator_args,
                         evidence=self.save({'http_status': 200, 'response': {'server_args': generator_args}}))
        generation = self.save({'http_status': 200, 'request': {'input_ids': prompt, 'sampling_params': {}},
            'response': {'output_ids': output, 'meta_info': {'completion_tokens': len(output)}}})
        trace = dict(request_id=request_id, prompt_ids=prompt, output_ids=output,
            prompt_tokens=len(prompt), output_tokens=len(output), prompt_sha256=sha_ids(prompt),
            output_sha256=sha_ids(output), scores=decode_scores(response, prompt, output),
            scorer=identity, raw_evidence=raw, generator=generator, generation_segments=[generation])
        return Path(self.save(trace)['path'])

    def calibration(self, length=4096):
        from controller.scored_forcing import calibrate_delta, calibrate_stock
        stock = self.trace([4] * length, {2: (6, .1)})
        ar = self.trace([4, 4, 6] + [4] * (length - 3), role='ar')
        delta = calibrate_delta([stock], [ar], evidence_root=self.root)
        self.assertEqual(delta['delta'], .125)
        return calibrate_stock([stock], delta, evidence_root=self.root)

    def test_real_score_contract_accepts_healthy_near_ties_and_rejects_large_faults(self):
        from controller.scored_forcing import judge_scored_forcing
        calibration = self.calibration()
        healthy = self.trace([4] * 4096, {2: (6, .1)})
        good = judge_scored_forcing(calibration, [healthy], evidence_root=self.root)
        self.assertTrue(good['correctness_passed'])
        fault = self.trace([4] * 4096, {index: (6, 2) for index in range(2048, 4096)})
        bad = judge_scored_forcing(calibration, [fault], evidence_root=self.root)
        self.assertTrue(bad['event_flagged'])
        self.assertFalse(bad['correctness_passed'])
        self.assertFalse(bad['ledger_eligible'])

    def test_finite_zero_stock_event_rate_has_nonzero_uncertainty(self):
        from controller.scored_forcing import binomial_upper
        upper = binomial_upper(0, 4096, .025)
        self.assertGreater(upper, 0)
        self.assertLess(upper, .001)

    def test_missing_modified_or_forged_explanation_evidence_is_rejected(self):
        from controller.scored_forcing import load_score_trace
        valid = self.trace([4] * 16)
        trace = json.loads(valid.read_text())
        for change in ('truncated', 'sha', 'explanation', 'generation', 'head'):
            altered = copy.deepcopy(trace)
            if change == 'truncated': altered['scores'].pop()
            if change == 'sha': altered['raw_evidence']['sha256'] = '0' * 64
            if change == 'explanation': altered['scores'][0]['explained'] = True
            if change == 'generation': altered['generation_segments'] = []
            if change == 'head': altered['scorer']['server_args']['enable_fp32_lm_head'] = False
            path = Path(self.save(altered)['path'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                load_score_trace(path, evidence_root=self.root)

    def test_missing_first_divergences_and_mismatched_request_sets_fail_closed(self):
        from controller.scored_forcing import calibrate_delta, judge_scored_forcing
        same = self.trace([4] * 20)
        with self.assertRaises(ValueError): calibrate_delta([same], [same], evidence_root=self.root)
        calibration = self.calibration(32)
        other = self.trace([4] * 32, request_id='different')
        with self.assertRaises(ValueError): judge_scored_forcing(calibration, [other], evidence_root=self.root)

    def test_same_request_id_cannot_hide_a_different_prompt(self):
        from controller.scored_forcing import judge_scored_forcing
        calibration = self.calibration(32)
        other = self.trace([4] * 32, prompt=[2, 9])
        with self.assertRaises(ValueError):
            judge_scored_forcing(calibration, [other], evidence_root=self.root)
