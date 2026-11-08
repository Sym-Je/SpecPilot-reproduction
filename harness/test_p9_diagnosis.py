import unittest
from unittest.mock import patch,Mock
from pathlib import Path


class DiagnosisTests(unittest.TestCase):
    def test_factorial_has_twelve_independent_cards(self):
        from exp.diagnosis import specifications
        rows=specifications()
        self.assertEqual(len(rows),96)
        self.assertEqual(len({row['base_id'] for row in rows}),12)
        self.assertEqual(len({(row['base_id'],row['language'],row['input_target'],row['answer_style']) for row in rows}),96)

    def test_modes_keep_natural_eos_distinct_from_fixed_length(self):
        from exp.diagnosis import sampling
        self.assertNotIn('ignore_eos',sampling('natural'))
        self.assertTrue(sampling('fixed')['ignore_eos'])
        with self.assertRaises(ValueError): sampling('unknown')

    def test_actual_fixed_output_must_equal_budget(self):
        from exp.diagnosis import check_length
        check_length('fixed',64,64,'length')
        check_length('natural',17,2048,'stop')
        for arguments in [('fixed',63,64,'length'),('fixed',64,64,'stop'),('natural',0,2048,'stop')]:
            with self.assertRaises(ValueError): check_length(*arguments)

    def test_cluster_contrasts_preserve_direction_and_case_count(self):
        from exp.diagnosis import contrasts
        rows=[]
        for base in range(12):
            for language in ('zh','en'):
                for target in (512,1536):
                    for budget in (64,256,1024):
                        ratio=(.5 if language=='zh' else 1.)*(2 if budget==1024 else 1.)*(1.5 if target==1536 else 1.)
                        rows.append(dict(base_id=str(base),language=language,input_target=target,budget=budget,ratio=ratio))
        output=contrasts(rows)
        self.assertAlmostEqual(output['language-at-64']['simultaneous']['mean'],.5)
        self.assertAlmostEqual(output['output-1024-over-64']['simultaneous']['mean'],2.)
        self.assertAlmostEqual(output['input-1536-over-512']['simultaneous']['mean'],1.5)
        self.assertEqual(output['language-at-64']['simultaneous']['n'],12)
        with self.assertRaises(ValueError): contrasts(rows[:-1])
        with self.assertRaises(ValueError): contrasts(rows+rows[:1])

    def test_trace_summary_keeps_unknown_and_overlapping_scopes_unassigned(self):
        from exp.diagnosis import summarize_trace
        events=[dict(ph='X',cat='cpu_op',name='prefill',ts=0,dur=100),
                dict(ph='X',cat='cpu_op',name='draft_forward',ts=25,dur=50),
                dict(ph='X',cat='kernel',name='unknown_gemm',ts=5,dur=80)]
        result=summarize_trace(events)
        self.assertEqual(result['kernel_total_us'],80)
        self.assertEqual(result['unattributed_kernel_us'],80)
        self.assertTrue(result['overlapping_stage_scopes'])

    def test_trace_without_named_stages_is_not_causal_decomposition(self):
        from exp.diagnosis import summarize_trace
        result=summarize_trace([dict(ph='X',cat='kernel',name='some_kernel',ts=0,dur=20)])
        self.assertFalse(result['stage_decomposition_available'])

    def test_native_controller_transport_preserves_explicit_fixed_sampling(self):
        from controller.http_transport import Arm
        from exp.diagnosis import sampling
        reply=dict(output_ids=[1]*64,meta_info=dict(completion_tokens=64,spec_verify_ct=8,
                                                   finish_reason=dict(type='length')))
        with patch('controller.http_transport._post',return_value=reply) as post:
            client=Arm('stock','http://fixture',sampling=sampling('fixed'))
            result=client.step([1,2],64)
            self.assertEqual(result['tokens'],64)
            self.assertEqual(post.call_args.args[1]['sampling_params'],
                             dict(temperature=0.,top_k=1,ignore_eos=True,max_new_tokens=64))

    def test_profile_schema_optional_request_is_supported(self):
        from exp.diagnosis import profile_body
        client=Mock()
        client.request.return_value=dict(paths={'/start_profile':dict(post=dict(requestBody=dict(content={
            'application/json':dict(schema=dict(anyOf=[{'$ref':'#/components/schemas/Profile'},dict(type='null')]))})))},
            components=dict(schemas=dict(Profile=dict(properties=dict(output_dir={},record_shapes={},with_stack={})))))
        result=profile_body(client,Path('/tmp/synthetic-profile'))
        self.assertEqual(result,dict(output_dir='/tmp/synthetic-profile',record_shapes=True,with_stack=False))

    def test_trace_kernel_correlation_requires_unambiguous_stage(self):
        from exp.diagnosis import summarize_trace
        events=[dict(ph='X',cat='user_annotation',name='draft_forward',ts=0,dur=100,pid=1,tid=1),
                dict(ph='X',cat='cuda_runtime',name='cudaLaunchKernel',ts=10,dur=2,pid=1,tid=1,args=dict(correlation=7)),
                dict(ph='X',cat='kernel',name='gemm',ts=20,dur=15,pid=2,tid=1,args=dict(correlation=7))]
        result=summarize_trace(events)
        self.assertEqual(result['attributed_kernel_us']['draft'],15)
        self.assertTrue(result['stage_decomposition_available'])
        events.append(dict(ph='X',cat='user_annotation',name='target_verify',ts=5,dur=60,pid=1,tid=1))
        result=summarize_trace(events)
        self.assertEqual(result['unattributed_kernel_us'],15)

    def test_native_packet_validator_rejects_eos_policy_and_token_tampering(self):
        from exp.diagnosis import packet_validator
        from controller.http_transport import sha_ids
        tokens=[4]*64
        request=dict(input_ids=[1,2],input_sha256=sha_ids([1,2]))
        assignment=dict(arm=dict(name='stock',tree_sha='tree',block=8),gpu=dict(uuid='gpu'),port=30100)
        sample=dict(raw_evidence='raw',generator=dict(tree_sha='tree',evidence='identity'),
            output_ids=tokens,completion_tokens=64,finish_reason='length',input_sha256=request['input_sha256'],
            gpu_uuid='gpu',arm='stock',tree_sha='tree',block=8,max_new_tokens=64,output_sha256=sha_ids(tokens),
            latency_s=1.,tokens_per_s=64.,client_timing=dict(step_start_ns=0,http_open_start_ns=1,
                body_complete_ns=999999999,step_end_ns=1000000000,url='http://127.0.0.1:30100/generate'))
        packet=dict(http_status=200,request=dict(input_ids=[1,2],sampling_params=dict(temperature=0.,top_k=1,
                    ignore_eos=True,max_new_tokens=64)),response=dict(output_ids=tokens,
                    meta_info=dict(completion_tokens=64,finish_reason=dict(type='length'))))
        identity=dict(response=dict(server_args=dict(speculative_algorithm='DFLASH',speculative_num_draft_tokens=8)))
        with patch('exp.diagnosis.checked_server'),patch('exp.diagnosis.read_reference',side_effect=lambda ref,root:packet if ref=='raw' else identity):
            validate=packet_validator('fixed')
            validate(sample,request,assignment,64,'/tmp',{})
            packet['request']['sampling_params'].pop('ignore_eos')
            with self.assertRaises(ValueError): validate(sample,request,assignment,64,'/tmp',{})
            packet['request']['sampling_params']['ignore_eos']=True
            sample['output_sha256']='tampered'
            with self.assertRaises(ValueError): validate(sample,request,assignment,64,'/tmp',{})

    def test_factorial_validator_rejects_duplicate_and_unmatched_inputs(self):
        from exp.diagnosis import specifications,validate_dataset
        from controller.http_transport import sha_ids
        rows=[dict(row,id=str(index),suite=row['language']+'-'+row['answer_style'],
                   input_ids=[1]*row['input_target'],input_sha256=sha_ids([1]*row['input_target']))
              for index,row in enumerate(specifications())]
        validate_dataset(dict(requests=rows))
        with self.assertRaises(ValueError): validate_dataset(dict(requests=rows[:-1]+rows[:1]))
        rows[0]['input_ids']=rows[0]['input_ids'][:-1]
        with self.assertRaises(ValueError): validate_dataset(dict(requests=rows))

    def test_overall_interval_clusters_language_and_length_within_base(self):
        from exp.diagnosis import base_interval
        requests=[dict(id=f'{base}-{language}',suite=language,base_id=str(base)) for base in range(12) for language in ('zh','en')]
        pairs=[dict(id=row['id'],suite=row['suite'],round=number,
                    a=dict(latency_s=2.,tokens_per_s=1.),b=dict(latency_s=1.,tokens_per_s=2.))
               for number in (1,2) for row in requests]
        result=base_interval(pairs,requests)
        self.assertAlmostEqual(result['geomean'],2.)
        with self.assertRaises(ValueError): base_interval(pairs[:-1],requests)


if __name__=='__main__': unittest.main()
