import copy
import json
import unittest
from continuation_compare import compare_three_arms


class ComparisonTests(unittest.TestCase):
    def response(self):
        return {'choices':[{'message':{'role':'assistant','content':'PRIVATE_ANSWER',
            'reasoning_content':'PRIVATE_REASONING','tool_calls':[{'id':'random-id',
                'type':'function','function':{'name':'lookup','arguments':'{"x":1}'}}]},'finish_reason':'tool_calls'}],
            'usage':{'prompt_tokens':128,'completion_tokens':20,'prompt_tokens_details':{'cached_tokens':0}}}

    def compare(self,a,b,c,signatures=None):
        return compare_three_arms(a,b,c,signatures or ['a'*64]*3)

    def test_equal_outputs_allow_cache_count_and_generated_call_id_difference(self):
        a=self.response();b=copy.deepcopy(a);c=copy.deepcopy(a)
        c['choices'][0]['message']['tool_calls'][0]['id']='another-random-id'
        c['usage']['prompt_tokens_details']['cached_tokens']=64
        report=self.compare([a],[b],[c])
        self.assertTrue(report['capture_valid']);self.assertTrue(report['candidate_passes_finite_output_check'])
        self.assertEqual(report['token_totals']['candidate']['cached_tokens'],64)
        for value in ['PRIVATE_ANSWER','PRIVATE_REASONING','random-id','lookup']:
            self.assertNotIn(value,json.dumps(report))
        self.assertFalse(report['global_accuracy_or_losslessness_certified'])

    def test_reasoning_difference_is_a_real_mismatch(self):
        a=self.response();c=copy.deepcopy(a);c['choices'][0]['message']['reasoning_content']='different'
        report=self.compare([a],[a],[c]);self.assertTrue(report['off_controls_reproducible'])
        self.assertFalse(report['candidate_passes_finite_output_check'])

    def test_nonreproducible_off_controls_block_candidate_judgment(self):
        a=self.response();b=copy.deepcopy(a);b['choices'][0]['message']['content']='changed'
        report=self.compare([a],[b],[a]);self.assertFalse(report['off_controls_reproducible'])
        self.assertIsNone(report['candidate_matches_controls']);self.assertFalse(report['candidate_passes_finite_output_check'])

    def test_missing_usage_or_changed_protocol_invalidates_capture(self):
        a=self.response();bad=copy.deepcopy(a);bad.pop('usage')
        self.assertFalse(self.compare([a],[a],[bad])['capture_valid'])
        self.assertFalse(self.compare([a],[a],[a],['a'*64,'a'*64,'b'*64])['capture_valid'])

    def test_zero_or_unmatched_counts_and_wrong_prompt_counts_are_invalid(self):
        a=self.response();bad=copy.deepcopy(a);bad['usage']['prompt_tokens']=129
        for arms in (([],[],[]),([a],[a],[]),([a],[a],[bad])):
            with self.subTest(arms_lengths=[len(x) for x in arms]):
                self.assertFalse(self.compare(*arms)['capture_valid'])


if __name__=='__main__':unittest.main()
