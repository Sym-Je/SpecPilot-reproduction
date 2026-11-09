import copy
import unittest


class ExplorationTests(unittest.TestCase):
    def packet(self):
        from agents.exploration import object_sha
        packet=dict(schema='exploration-evidence-v1',source_pin='a'*40,evidence={
            'E001':dict(kind='deployment',data=dict(block_size=8)),
            'E002':dict(kind='profile',data=dict(cumulative_kernel_ms=100,
                identifiable_mm_cumulative_kernel_ms=2,equal_request_profile_window_kernel_work_share=dict(VERIFY=.89))),
            'E003':dict(kind='counters',data=dict(suites={'suite':dict(native_correct_draft_histogram_work_counts=[1]*8)})),
            'E004':dict(kind='linear-replay',data=dict(replays=[dict(committed_verify_steps=81,uncommitted_verify_steps=1)]))},
            capabilities=dict(full_factors_available=False,tau_best_available=False))
        packet['evidence_sha256']=object_sha(packet)
        return packet

    def test_no_response_or_fixture_is_a_real_agent_result(self):
        from agents.exploration import validate_transport
        for receipt in ({},dict(backend='fixture',agent_id='fake',request_sha256='a'*64)):
            with self.assertRaises(ValueError):
                validate_transport(receipt,'a'*64)
        receipt=dict(backend='codex-subagent-tool',agent_id='real-id',request_sha256='a'*64,
            model_selection='inherited-default',resolved_model_id=None)
        validate_transport(receipt,'a'*64)
        with self.assertRaises(ValueError):
            validate_transport(receipt,'b'*64)

    def test_unknown_tools_and_shell_are_rejected(self):
        from agents.exploration import run_cpu_tool
        for request in (dict(name='shell',arguments=dict(cmd='whoami')),dict(name='gpu_profile',arguments={})):
            with self.assertRaises(ValueError):
                run_cpu_tool(self.packet(),request)

    def test_profile_coverage_is_not_end_to_end_headroom(self):
        from agents.exploration import run_cpu_tool
        result=run_cpu_tool(self.packet(),dict(name='profile_coverage',arguments={}))
        self.assertEqual(result['shape_qualified_kernel_work_fraction'],.02)
        self.assertIsNone(result['end_to_end_gain'])
        self.assertIsNone(result['kernel_factor'])

    def test_overlap_fraction_is_gpu_work_not_latency_saving(self):
        from agents.exploration import run_cpu_tool
        result=run_cpu_tool(self.packet(),dict(name='overlap_work',arguments={}))
        self.assertEqual(result['samples'][0]['uncommitted_step_count_fraction'],1/82)
        self.assertIsNone(result['end_to_end_gain'])

    def test_prefix_budget_is_only_local_observed_chain_arithmetic(self):
        from agents.exploration import run_cpu_tool
        result=run_cpu_tool(self.packet(),dict(name='local_prefix_budget',arguments=dict(suite='suite',budget=4)))
        self.assertEqual(result['mean_local_emitted_tokens'],(1+2+3+4*5)/8)
        self.assertFalse(result['full_counterfactual_trajectory_available'])
        self.assertIsNone(result['end_to_end_gain'])

    def test_master_must_select_its_own_bounded_directions(self):
        from agents.exploration import validate_master
        response=dict(schema='master-plan-v1',evidence_sha256=self.packet()['evidence_sha256'],
            directions=[dict(id='probe-one',factor='unknown',hypothesis='test a hypothesis',
                evidence_refs=['E002'],cheapest_test='ask a CPU tool')],unknowns=['floors unavailable'])
        validate_master(response,self.packet())
        bad=copy.deepcopy(response)
        bad['directions'][0]['evidence_refs']=['E999']
        with self.assertRaises(ValueError):
            validate_master(bad,self.packet())

    def test_missing_data_cannot_be_called_an_experimentally_closed_direction(self):
        from agents.exploration import validate_direction
        response=dict(schema='direction-result-v1',direction_id='probe-one',
            evidence_sha256=self.packet()['evidence_sha256'],status='needs_measurement',
            evidence_refs=['E002'],tool_refs=[],hypothesis='requires a measurement',
            net_headroom_estimate=None,limitations=['unknown end-to-end cost'],
            next_experiment=dict(procedure='minimal probe',budget_gpu_minutes=10,kill_if='measured net headroom below 3%'),
            proposal=None,implementation_ready=False)
        validate_direction(response,self.packet(),'probe-one',[])
        response['status']='closed'
        with self.assertRaises(ValueError):
            validate_direction(response,self.packet(),'probe-one',[])

    def test_wrong_evidence_and_self_authorized_implementation_are_rejected(self):
        from agents.exploration import validate_direction
        response=dict(schema='direction-result-v1',direction_id='probe-one',
            evidence_sha256=self.packet()['evidence_sha256'],status='needs_measurement',
            evidence_refs=['E002'],tool_refs=[],hypothesis='unknown benefit',net_headroom_estimate=None,
            limitations=['no matched timing'],next_experiment=dict(procedure='probe',budget_gpu_minutes=10,kill_if='no headroom'),
            proposal=None,implementation_ready=False)
        for key,value in [('implementation_ready',True),('evidence_sha256','b'*64),('tool_refs',['T999']),
                          ('net_headroom_estimate',float('nan')),('status','proposal')]:
            altered=copy.deepcopy(response)
            altered[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_direction(altered,self.packet(),'probe-one',[])

    def test_prompt_and_raw_completion_are_bound_to_transport_receipt(self):
        import json
        from pathlib import Path
        import tempfile
        from exp.exploration import issue,checked_response
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('requests','responses','tools'):
                (root/name).mkdir()
            (root/'manifest.json').write_text(json.dumps(dict(source_pin='a'*40)))
            (root/'evidence.json').write_text(json.dumps(self.packet()))
            request=issue(root,'master-plan','master-plan')
            parsed=dict(schema='master-plan-v1',evidence_sha256=self.packet()['evidence_sha256'],
                directions=[dict(id='one',factor='unknown',hypothesis='fixture-only hypothesis',evidence_refs=['E002'],
                                 cheapest_test='fixture')],unknowns=['not a live agent test'])
            raw=json.dumps(parsed)
            receipt=dict(backend='codex-subagent-tool',agent_id='fixture-only',request_sha256=request['request_sha256'],
                model_selection='inherited-default',resolved_model_id=None,
                dispatch_tool='multi_agent_v1__spawn_agent',dispatch_arguments=dict(fork_context=False,message=request['prompt']),
                dispatch_receipt=dict(agent_id='fixture-only'),completion_receipt=dict(status={'fixture-only':dict(completed=raw)}))
            self.assertEqual(checked_response(root,'master-plan',raw,receipt),parsed)
            receipt['dispatch_arguments']['message']='preassigned answer'
            with self.assertRaises(ValueError):
                checked_response(root,'master-plan',raw,receipt)
            receipt['dispatch_arguments']['message']=request['prompt']
            with self.assertRaises(ValueError):
                checked_response(root,'master-plan',raw+' ',receipt)


if __name__=='__main__':
    unittest.main()
