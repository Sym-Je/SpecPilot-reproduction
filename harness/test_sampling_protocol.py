import copy
import math
import unittest


class SamplingProtocolTests(unittest.TestCase):
    def test_positive_temperature_really_disables_greedy_topk(self):
        from harness.sampling_protocol import parameters
        for temperature in (.7,1.):
            self.assertEqual(parameters(temperature,1),dict(temperature=temperature,top_k=-1,top_p=1.,sampling_seed=1))
        self.assertEqual(parameters(0.,0)['top_k'],1)
        for temperature,seed in ((-1,0),(math.nan,0),(.7,-1),(.7,True)):
            with self.assertRaises(ValueError):
                parameters(temperature,seed)

    def fixture(self):
        requests=[dict(id=f'{suite}-{index}',suite=suite) for suite in ('gsm8k','math500','humaneval','mbpp','mt-bench') for index in range(4)]
        pairs=[dict(id=item['id']+f'@s{seed}',round=number,a=dict(tokens_per_s=100.),b=dict(tokens_per_s=200.))
            for number in (1,2) for item in requests for seed in (0,1)]
        return requests,pairs

    def test_seed_and_round_repeats_are_not_independent_prompts(self):
        from harness.sampling_protocol import summarize
        requests,pairs=self.fixture()
        report=summarize(pairs,requests)
        self.assertEqual(report['independent_requests'],20)
        self.assertEqual(report['pairs'],80)
        self.assertAlmostEqual(report['interval']['geomean'],2.)
        self.assertAlmostEqual(report['interval']['lower'],2.)

    def test_missing_or_duplicate_pairs_and_invalid_rates_rejected(self):
        from harness.sampling_protocol import summarize
        requests,pairs=self.fixture()
        for altered in (pairs[:-1],pairs+[pairs[0]]):
            with self.assertRaises(ValueError):
                summarize(altered,requests)
        altered=copy.deepcopy(pairs)
        altered[0]['b']['tokens_per_s']=math.nan
        with self.assertRaises(ValueError):
            summarize(altered,requests)

    def test_logprob_evidence_is_not_claimed_distributional_correctness(self):
        from harness.sampling_protocol import non_argmax_count
        response=dict(meta_info=dict(output_token_logprobs=[[-2.,10,'x'],[-.1,20,'y']],
            output_top_logprobs=[[[-.2,11,'z'],[-2.,10,'x']],[[-.1,20,'y']]]))
        self.assertEqual(non_argmax_count(response),1)
        self.assertIsNone(non_argmax_count(dict(meta_info={})))

    def test_timed_packet_binding_rejects_greedy_fallback_and_forged_rate(self):
        from controller.http_transport import sha_ids
        from harness.sampling_protocol import parameters,validate_measurement
        packet=dict(http_status=200,request=dict(input_ids=[1,2],sampling_params=dict(parameters(.7,1),max_new_tokens=2048)),
            response=dict(output_ids=[3,4],meta_info=dict(completion_tokens=2,finish_reason=dict(type='length'))))
        row=dict(tokens=2,completion_tokens=2,output_ids=[3,4],output_sha256=sha_ids([3,4]),input_sha256=sha_ids([1,2]),
            tokens_per_s=2.,latency_ms=1000.,latency_s=1.,finish_reason='length',
            client_timing=dict(step_start_ns=1_000_000_000,step_end_ns=2_000_000_000))
        validate_measurement(row,packet,[1,2],.7,1)
        altered=copy.deepcopy(packet)
        altered['request']['sampling_params']['top_k']=1
        with self.assertRaises(ValueError):
            validate_measurement(row,altered,[1,2],.7,1)
        with self.assertRaises(ValueError):
            validate_measurement(dict(row,tokens_per_s=20.),packet,[1,2],.7,1)

    def test_prepare_and_plan_cannot_submit_or_initialize_budget(self):
        from unittest.mock import patch
        from exp import sampling_resource
        for action in ('prepare','plan'):
            with patch('sys.argv',['sampling_resource',action,'--directory','/tmp/sampling-no-submit']),\
                    patch.object(sampling_resource,'prepare') as prepare,\
                    patch.object(sampling_resource,'execute') as execute,\
                    patch.object(sampling_resource,'Budget') as budget,\
                    patch.object(sampling_resource,'command',return_value=['planned']):
                sampling_resource.main()
            self.assertEqual(prepare.call_count,int(action=='prepare'))
            execute.assert_not_called()
            budget.assert_not_called()


if __name__=='__main__':
    unittest.main()
