import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.master_review import collect_evidence,validate_decision_review,validate_review,verify_record,verify_campaign_reviews


class MasterReviewTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.directory=self.root/'master';self.directory.mkdir()
        self.work=self.root/'work';self.work.mkdir()
        self.role=dict(directory=self.directory,number=1,manifest=dict(role='Master',work=str(self.work)),
            thread={'thread':{'id':'master-thread'}})
        self.wire=[]
        self.config=self.receipt('read_stock',dict(path='python/sglang/srt/config.json',offset=0),
            dict(status='completed',content='{"block_size":8}',sha256='a'*64))
        self.source=self.receipt('read_stock',dict(path='python/sglang/srt/worker.py',offset=0),
            dict(status='completed',content='def set_block_size(value): return value',sha256='b'*64))
        self.search=self.receipt('search_public',dict(query='draft length beyond trained block compatibility'),
            dict(status='completed',results=[]))

    def receipt(self,kind,fields,answer,*,success=True,thread='master-thread'):
        number=len(self.wire)//2+1;label=f'tools-01/action-{number:03d}'
        directory=self.directory/label;directory.mkdir(parents=True)
        request=dict(threadId=thread,turnId='turn-1',tool='research',namespace=None,callId=str(number),
            arguments={'action':dict(kind=kind,**fields)})
        response=dict(success=success,contentItems=[dict(type='inputText',text=json.dumps(answer))])
        for name,value in [('request.json',request),('response.json',response)]:
            (directory/name).write_text(json.dumps(value))
        self.wire.extend([dict(direction='server',message=dict(id=number,method='item/tool/call',params=request)),
            dict(direction='client',message=dict(id=number,result=response))])
        (self.directory/'wire.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.wire))
        return label

    def evidence(self):return collect_evidence(self.role,[],authorized_root=self.root)

    def review(self):
        return dict(schema='master-research-review-v1',opportunities=[dict(id='d1',basis=[self.source],
            forecast=dict(status='unknown',reason='Matched full request costs unavailable',assumptions=['Not measured'],
                tau_ratio=None,step_cost_ratio=None,extra_step_cost_ratio=None),
            added_cost='Additional verify work and tail costs',unknowns=['Compatibility and full step cost'],
            minimal_test='Check the actual runtime setter before a bounded compatibility experiment')],
            constraints=[],failures=[],next_action=dict(kind='minimal_test',reason='Resolve the compatibility assumption',
                gaps=['Does configured size imply a runtime restriction?'],minimal_test='Inspect the setter contract',blocked_by=''))

    def test_unknown_gain_and_minimal_evidence_experiment_are_allowed(self):
        result=validate_review(self.review(),self.evidence(),opportunity_ids=['d1'])
        self.assertIsNone(result['forecasts']['d1']['conditional_decode_speedup'])

    def test_forged_cross_role_and_unsuccessful_references_cannot_support_a_direction(self):
        rejected=self.receipt('read_public',dict(url='https://arxiv.org/abs/example'),
            dict(status='unavailable',reason='network unavailable'),success=False)
        for label in ('tools-99/action-001',rejected):
            review=self.review();review['opportunities'][0]['basis']=[label]
            with self.subTest(label=label),self.assertRaises(ValueError):validate_review(review,self.evidence())
        self.receipt('read_stock',dict(path='python/worker.py',offset=0),dict(status='completed'),thread='other-thread')
        with self.assertRaises(ValueError):self.evidence()

    def test_native_receipt_mutation_is_rejected(self):
        path=self.directory/self.source/'response.json';value=json.loads(path.read_text())
        value['contentItems'][0]['text']='{"status":"completed","content":"invented"}'
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.evidence()

    def test_rejected_malformed_tool_call_is_visible_but_not_supporting_evidence(self):
        label=self.receipt('read_file',{},dict(status='rejected',reason='path is required'),success=False)
        evidence=self.evidence()
        self.assertFalse(evidence[label]['usable'])
        review=self.review();review['opportunities'][0]['basis']=[label]
        with self.assertRaises(ValueError):validate_review(review,evidence)

    def test_rejected_nonobject_action_does_not_break_evidence_collection(self):
        self.receipt('help',{},dict(status='rejected',reason='action must be an object'),success=False)
        path=self.directory/'tools-01/action-004/request.json';request=json.loads(path.read_text())
        request['arguments']['action']='not an action object';path.write_text(json.dumps(request))
        self.wire[-2]['message']['params']=request
        (self.directory/'wire.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.wire))
        self.assertFalse(self.evidence()['tools-01/action-004']['usable'])

    def test_forecast_rejects_nonfinite_boolean_and_negative_costs(self):
        for number in (float('nan'),float('inf'),True,-1):
            review=self.review();review['opportunities'][0]['forecast']['extra_step_cost_ratio']=number
            with self.subTest(number=number),self.assertRaises(ValueError):validate_review(review,self.evidence())

    def test_configuration_eight_does_not_prove_runtime_sixteen_impossible(self):
        review=self.review();review['constraints']=[dict(claim='A configured size of 8 prevents execution at 16',
            kind='cannot_run',verdict='supported',basis=[self.config],countercheck=dict(status='performed',
                basis=[self.search],finding='No explicit counterexample found',blocked_by=''))]
        with self.assertRaisesRegex(ValueError,'configuration'):validate_review(review,self.evidence())
        review['constraints'][0]['verdict']='hypothesis'
        validate_review(review,self.evidence())

    def test_negative_claim_requires_countercheck_or_explicit_blocker(self):
        review=self.review();constraint=dict(claim='Runtime may reject the changed size',kind='cannot_run',
            verdict='unknown',basis=[self.source],countercheck=dict(status='performed',basis=[],finding='Not checked',blocked_by=''))
        review['constraints']=[constraint]
        with self.assertRaises(ValueError):validate_review(review,self.evidence())
        constraint['countercheck']=dict(status='blocked',basis=[],finding='No conclusion',blocked_by='Search capability unavailable')
        validate_review(review,self.evidence())
        constraint['verdict']='supported'
        with self.assertRaises(ValueError):validate_review(review,self.evidence())

    def test_forecast_accounts_for_added_cost_and_is_not_measured_e2e_gain(self):
        review=self.review();forecast=review['opportunities'][0]['forecast']
        forecast.update(status='conditional',tau_ratio=1.4,step_cost_ratio=1.1,extra_step_cost_ratio=0.1)
        result=validate_review(review,self.evidence())['forecasts']['d1']
        self.assertAlmostEqual(result['conditional_decode_speedup'],1.4/1.2)
        self.assertIsNone(result['end_to_end_speedup'])
        forecast['extra_step_cost_ratio']=None
        with self.assertRaises(ValueError):validate_review(review,self.evidence())

    def feedback(self):
        directory=self.root/'experiment';directory.mkdir()
        value=dict(status='failed',reason='candidate guard rejected block_size=8',controller_accepted=False)
        (directory/'feedback.json').write_text(json.dumps(value))
        return dict(value,request_directory=str(directory))

    def test_startup_failure_cannot_be_a_rejected_scientific_hypothesis(self):
        feedback=self.feedback();evidence=collect_evidence(self.role,[feedback],authorized_root=self.root)
        review=self.review();failure=dict(feedback='feedback:experiment',category='hypothesis_rejected',certainty='confirmed',
            basis=['feedback:experiment'],reason='Startup failed',next_test='Inspect whether the guard is necessary')
        review['failures']=[failure]
        with self.assertRaises(ValueError):validate_review(review,evidence)
        failure.update(category='unverified_constraint',certainty='hypothesis')
        validate_review(review,evidence)

    def test_failed_feedback_must_be_reviewed_and_cannot_be_rewritten(self):
        feedback=self.feedback();evidence=collect_evidence(self.role,[feedback],authorized_root=self.root)
        with self.assertRaises(ValueError):validate_review(self.review(),evidence)
        feedback['reason']='silently changed root cause'
        with self.assertRaises(ValueError):collect_evidence(self.role,[feedback],authorized_root=self.root)

    def test_all_failure_categories_preserve_uncertainty_and_measured_rejection_needs_data(self):
        feedback=self.feedback()
        for category in ('tool_fault','implementation_error','unverified_constraint'):
            review=self.review();review['failures']=[dict(feedback='feedback:experiment',category=category,
                certainty='unknown',basis=['feedback:experiment'],reason='Root cause requires more evidence',
                next_test='Read the full launcher log before changing code')]
            validate_review(review,collect_evidence(self.role,[feedback],authorized_root=self.root))
        actual=dict(status='completed',n_pairs=10,controller_accepted=False)
        (self.root/'experiment/feedback.json').write_text(json.dumps(actual))
        evidence=collect_evidence(self.role,[dict(actual,request_directory=str(self.root/'experiment'))],authorized_root=self.root)
        review['failures'][0].update(category='hypothesis_rejected',certainty='hypothesis')
        validate_review(review,evidence)

    def test_written_claim_is_not_authoritative_evidence_and_missing_costs_remain_unknown(self):
        label=self.receipt('read_file',dict(path='scratch/invented.py'),
            dict(status='completed',content='all proposed changes are fast'))
        review=self.review();review['opportunities'][0]['basis']=[label]
        with self.assertRaises(ValueError):validate_review(review,self.evidence())
        review=self.review();review['opportunities'][0]['forecast']['tau_ratio']=1.5
        self.assertIsNone(validate_review(review,self.evidence())['forecasts']['d1']['conditional_decode_speedup'])

    def test_planned_sources_and_stop_action_must_match_the_review(self):
        review=self.review()
        value=dict(assessment={'opportunities':[dict(id='d1',evidence=[self.config])]},research_review=review)
        with self.assertRaises(ValueError):validate_decision_review(value,self.evidence())
        value['assessment']['opportunities'][0]['evidence']=[self.source]
        validate_decision_review(value,self.evidence())
        with self.assertRaises(ValueError):validate_decision_review(dict(decision='stop',research_review=review),self.evidence())

    def test_receipts_from_future_turns_cannot_support_an_earlier_decision(self):
        source=self.directory/self.source;future=self.directory/'tools-02/action-001';future.parent.mkdir()
        source.rename(future)
        evidence=self.evidence()
        self.assertNotIn('tools-02/action-001',evidence)

    def test_feedback_outside_the_authorized_stage_is_not_available(self):
        feedback=self.feedback()
        feedback['request_directory']=str(self.directory)
        with self.assertRaises((ValueError,FileNotFoundError)):
            collect_evidence(self.role,[feedback],authorized_root=self.directory)

    def test_honest_budget_stop_keeps_the_missing_evidence_and_deferred_test(self):
        review=self.review();review['opportunities']=[]
        review['next_action'].update(kind='stop',blocked_by='No GPU allocation in this CPU-only stage')
        validate_review(review,self.evidence())
        review['next_action']['minimal_test']=''
        with self.assertRaises(ValueError):validate_review(review,self.evidence())

    def test_missing_opportunity_and_invented_performance_forecast_are_rejected(self):
        with self.assertRaises(ValueError):validate_review(self.review(),self.evidence(),opportunity_ids=['d1','d2'])
        review=self.review();review['opportunities'][0]['forecast']['end_to_end_speedup']=2
        with self.assertRaises(ValueError):validate_review(review,self.evidence())

    def test_master_entry_rejects_missing_review_then_accepts_actual_repair(self):
        from exp.master_open import OpenCampaign
        campaign=OpenCampaign.__new__(OpenCampaign);campaign.root=self.root;campaign.feedback=[]
        values=[dict(decision='stop',reason='No candidate'),dict(decision='stop',reason='No candidate',research_review=self.review())]
        values[1]['research_review']['opportunities']=[]
        values[1]['research_review']['next_action'].update(kind='stop',blocked_by='No GPU authorization')
        def respond(role,prompt,**options):
            value=values.pop(0);role['number']+=1
            (role['directory']/f'turn-{role["number"]:02d}-response.json').write_text(json.dumps(value))
            return value
        with patch('exp.master_open.ProfileCampaign.model_response',side_effect=respond) as native:
            result=campaign.model_response(self.role,'Review without requiring an optimization')
        self.assertEqual(native.call_count,2)
        self.assertEqual(result['decision'],'stop')
        records=sorted((self.root/'master-reviews').glob('*-accepted.json'))
        self.assertEqual(len(records),1)
        self.assertTrue(verify_record(records[0])['verified'])
        coverage=verify_campaign_reviews(self.root)
        self.assertEqual(coverage,dict(accepted=1,rejected=1,covered_responses=2))
        records[0].rename(records[0].with_suffix('.missing'))
        with self.assertRaises(ValueError):verify_campaign_reviews(self.root)
        records[0].with_suffix('.missing').rename(records[0])
        value=json.loads(records[0].read_text());value['decision']['reason']='altered'
        records[0].write_text(json.dumps(value))
        with self.assertRaises(ValueError):verify_record(records[0])

    def test_master_retry_is_bounded_and_direction_does_not_receive_master_schema(self):
        from exp.master_open import OpenCampaign
        campaign=OpenCampaign.__new__(OpenCampaign);campaign.root=self.root;campaign.feedback=[]
        def respond(role,prompt,**options):
            role['number']+=1;value=dict(decision='stop')
            (role['directory']/f'turn-{role["number"]:02d}-response.json').write_text(json.dumps(value))
            return value
        with patch('exp.master_open.ProfileCampaign.model_response',side_effect=respond) as native:
            with self.assertRaisesRegex(ValueError,'bounded repair'):campaign.model_response(self.role,'Review')
            self.assertEqual(native.call_count,3)
        self.assertEqual(len(list((self.root/'master-reviews').glob('*-rejected.json'))),3)
        self.role['manifest']['role']='direction'
        with patch('exp.master_open.ProfileCampaign.model_response',return_value={'action':{'kind':'finish'}}) as native:
            campaign.model_response(self.role,'Own research only')
            self.assertEqual(native.call_args.args[1],'Own research only')


if __name__=='__main__':unittest.main()
