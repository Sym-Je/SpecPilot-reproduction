import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp.master_decisions import Campaign, research_brief
from harness.master_decisions import DecisionState, validate_decision
from harness.master_decisions_audit import replay_journal, verify_master_feedback, verify_runtime_sources
from harness import skill_rsi_audit as native_audit
from harness import test_skill_rsi_audit as native_fixtures


def opportunity(identity='budget', axis='verification_budget', priority='diagnose'):
    return dict(id=identity, axis=axis, mechanism='Compare work against accepted progress',
        potential_gain='Unknown until matching workload cost is available', added_cost='Decision and shape costs unknown',
        unknowns=['Unprofiled step cost'], cheapest_check='Read stock and compute an explicitly conditional bound',
        priority=priority, evidence=['baseline'])


def comparison(kind='compare', based_on=None):
    return dict(kind=kind, opportunities=[opportunity(), opportunity('kernel','kernel')],
        axis_assessments={name:'Evidence is incomplete; diagnosis or deferral, not a gain claim'
            for name in ('verification_budget','verification_selection','kernel','end_to_end')},
        reason='Compare the least expensive evidence before implementation', based_on=based_on or [])


class AttributionBriefTests(unittest.TestCase):
    def test_acceptance_headroom_supplies_bounds_without_claiming_measured_tree_speedup(self):
        with self.assertRaises(ValueError):research_brief(True,acceptance_headroom=True)
        rules,prompt=research_brief(True,prioritize_e2e=True,acceptance_headroom=True)
        self.assertIn('acceptance-headroom',prompt)
        self.assertIn('含bonus进度≤min(D+1,N)',prompt)
        self.assertIn('tau(N)/T_step(N)',prompt)
        self.assertIn('不能外推收益',prompt)
        self.assertIn('禁止直接提交GPU',prompt)
        self.assertNotIn('stock-runtime在自己的',rules)

    def test_attribution_requires_context_and_declares_graph_and_no_gpu_limits(self):
        with self.assertRaises(ValueError): research_brief(True,attribute_kernels=True)
        rules,prompt=research_brief(True,prioritize_e2e=True,attribute_kernels=True)
        self.assertIn('GPU授权为零',rules)
        self.assertIn('read_kernel_links',prompt)
        self.assertIn('graph launch的CPU形状不能转给graph node',prompt)
        self.assertIn('不提交GPU',prompt)

    def test_default_mode_does_not_silently_enable_attribution(self):
        rules,prompt=research_brief(True,prioritize_e2e=True)
        self.assertNotIn('read_kernel_links',prompt)


class MasterDecisionTests(unittest.TestCase):
    def setUp(self):
        self.state=DecisionState({'baseline':dict(scope='synthetic fixture')})

    def test_compare_then_feedback_then_revision_changes_priority(self):
        self.state.apply(comparison())
        self.state.deliver('historical-feedback',dict(geomean=0.9956),source=dict(path='/fixture/public.json',sha256='a'*64))
        action=comparison('revise',['historical-feedback'])
        action['opportunities'][1]['priority']='defer'
        self.state.apply(action)
        self.assertEqual(self.state.opportunities['kernel']['priority'],'defer')
        self.assertEqual(self.state.revisions,1)

    def test_revision_requires_feedback_that_was_actually_delivered(self):
        with self.assertRaises(ValueError):
            self.state.apply(comparison('revise',['invented-feedback']))

    def test_feedback_cannot_be_forged_as_a_master_action(self):
        with self.assertRaises(ValueError):
            self.state.apply(dict(kind='deliver',id='historical-feedback',value=dict(geomean=2)))

    def test_cpu_stage_rejects_gpu_and_arbitrary_execution_actions(self):
        for kind in ('run_source','request_stock_profile','northjob','shell'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.state.apply(dict(kind=kind))

    def test_compares_multiple_opportunities_and_all_axes(self):
        action=comparison(); action['opportunities']=action['opportunities'][:1]
        with self.assertRaises(ValueError): self.state.apply(action)
        action=comparison(); action['axis_assessments'].pop('end_to_end')
        with self.assertRaises(ValueError): self.state.apply(action)

    def test_dispatch_and_continue_preserve_identity_and_allocation(self):
        self.state.apply(comparison())
        action=dict(kind='dispatch',id='budget',brief='CPU-only source and cost analysis',
            allocation=dict(actions=20,cpu_runs=3),reason='Cheap diagnosis',based_on=['baseline'])
        self.state.apply(action)
        self.state.return_direction('budget',dict(summary='Missing runtime evidence'),dict(actions=5,cpu_runs=1))
        self.state.apply(dict(action,kind='continue',allocation=dict(actions=4,cpu_runs=1),based_on=['direction-budget-01']))
        self.assertEqual(self.state.directions['budget']['allocated'],dict(actions=24,cpu_runs=4))
        self.assertEqual(self.state.directions['budget']['used'],dict(actions=5,cpu_runs=1))

    def test_direction_budget_cannot_reset_or_exceed_stage_reservations(self):
        self.state.apply(comparison())
        action=dict(kind='dispatch',id='budget',brief='CPU-only check',allocation=dict(actions=64,cpu_runs=9),
            reason='diagnose',based_on=['baseline'])
        with self.assertRaises(ValueError): self.state.apply(action)
        self.assertEqual(self.state.directions,{})

    def test_unsupported_actions_do_not_mutate_state(self):
        before=copy.deepcopy(self.state.snapshot())
        with self.assertRaises(ValueError): self.state.apply(dict(kind='stop',reason=''))
        self.assertEqual(self.state.snapshot(),before)

    def test_honest_stop_is_allowed_without_forcing_another_direction(self):
        self.state.apply(dict(kind='stop',reason='No evidence-backed direction available',based_on=[]))
        self.assertTrue(self.state.stopped)
        with self.assertRaises(ValueError): self.state.apply(comparison())

    def test_journal_replay_binds_feedback_and_native_decisions(self):
        evidence=dict(initial={'baseline':{}},historical_feedback=dict(geomean=0.9956),
            feedback_source=dict(path='/fixture/actual-feedback.json',sha256='a'*64))
        values={'initial':comparison(),'revision':comparison('revise',['historical-feedback']),
            'stop':dict(kind='stop',reason='No justified extra work',based_on=['historical-feedback'])}
        journal=[dict(kind='decision',response='initial'),dict(kind='historical_feedback',source=evidence['feedback_source']),
            dict(kind='decision',response='revision'),dict(kind='decision',response='stop')]
        state=replay_journal(evidence,journal,lambda identity:values[identity])
        self.assertTrue(state.stopped)
        self.assertEqual(state.revisions,1)
        changed=copy.deepcopy(journal); changed[1]['source']['sha256']='b'*64
        with self.assertRaises(ValueError): replay_journal(evidence,changed,lambda identity:values[identity])

    def test_journal_cannot_relabel_a_valid_action_as_a_rejection(self):
        evidence=dict(initial={'baseline':{}})
        with self.assertRaises(ValueError):
            replay_journal(evidence,[dict(kind='rejected',response='value',reason='pretended invalid')],lambda identity:comparison())

    def test_stop_and_forged_feedback_cannot_skip_pending_direction(self):
        self.state.apply(comparison())
        action=dict(kind='dispatch',id='budget',brief='Own CPU check',allocation=dict(actions=4,cpu_runs=1),
            reason='Cheap diagnosis',based_on=['baseline'])
        self.state.apply(action)
        before=self.state.snapshot()
        with self.assertRaises(ValueError):
            self.state.apply(dict(kind='stop',reason='Skip unfinished work',based_on=[]))
        with self.assertRaises(ValueError):
            self.state.return_direction('budget',dict(summary='Overclaimed use'),dict(actions=5,cpu_runs=1))
        self.assertEqual(before,self.state.snapshot())

    def test_repeated_continuation_cannot_exceed_cumulative_stage_budget(self):
        self.state.apply(comparison())
        action=dict(kind='dispatch',id='budget',brief='Own CPU check',allocation=dict(actions=64,cpu_runs=0),
            reason='Cheap diagnosis',based_on=['baseline'])
        self.state.apply(action)
        feedback=self.state.return_direction('budget',dict(summary='Need more evidence'),dict(actions=64,cpu_runs=0))
        self.state.apply(dict(action,kind='continue',based_on=[feedback]))
        feedback=self.state.return_direction('budget',dict(summary='Still incomplete'),dict(actions=64,cpu_runs=0))
        before=self.state.snapshot()
        with self.assertRaises(ValueError):
            self.state.apply(dict(action,kind='continue',allocation=dict(actions=17,cpu_runs=0),based_on=[feedback]))
        self.assertEqual(before,self.state.snapshot())

    def test_feedback_identity_is_immutable_and_cannot_arrive_after_stop(self):
        self.state.deliver('actual-feedback',dict(summary='Known limit'),source={})
        with self.assertRaises(ValueError): self.state.deliver('actual-feedback',{},source={})
        self.state.apply(dict(kind='stop',reason='No justified next diagnostic',based_on=['actual-feedback']))
        with self.assertRaises(ValueError): self.state.deliver('new-feedback',{},source={})

    def test_continuation_cannot_use_feedback_from_prefix_similar_other_direction(self):
        action=comparison()
        action['opportunities'].append(opportunity('budget-other'))
        self.state.apply(action)
        dispatch=dict(kind='dispatch',id='budget',brief='Own CPU check',allocation=dict(actions=4,cpu_runs=1),
            reason='Cheap diagnosis',based_on=['baseline'])
        for identity in ('budget','budget-other'):
            self.state.apply(dict(dispatch,id=identity))
            self.state.return_direction(identity,dict(summary='Incomplete'),dict(actions=1,cpu_runs=0))
        with self.assertRaises(ValueError):
            self.state.apply(dict(dispatch,kind='continue',based_on=['direction-budget-other-01']))


class BudgetDenialAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture=native_fixtures.SkillRsiAuditTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.directory=self.root/'direction-d1'
        self.path=self.directory/'wire.jsonl'
        self.rows=[json.loads(line) for line in self.path.read_text().splitlines()]
        request=copy.deepcopy(next(row['message']['params'] for row in self.rows if row['message'].get('method')=='item/tool/call'))
        request.update(callId='quota-denial',arguments=dict(action=dict(kind='run_python',path='scratch/check.py')))
        position=next(index for index,row in enumerate(self.rows) if row['message'].get('method')=='item/completed')
        self.rows[position:position]=[dict(direction='server',message=dict(id=999,method='item/tool/call',params=request)),
            dict(direction='client',message=dict(id=999,result=dict(success=False,contentItems=[dict(type='inputText',text='research action budget exhausted')])))]
        self.save()

    def save(self):
        self.path.write_text(''.join(json.dumps(row)+'\n' for row in self.rows))

    def test_existing_strict_audit_still_rejects_unmirrored_calls(self):
        with self.assertRaises(ValueError): native_audit.audit_role(self.root,self.directory)

    def test_exact_wire_denial_at_actual_limit_is_not_a_cpu_execution(self):
        role,responses,origins=native_audit.audit_role(self.root,self.directory,action_limits={1:3})
        self.assertEqual(role['counts']['budget_rejections'],1)
        self.assertEqual(role['counts']['actions'],3)
        self.assertEqual(role['counts']['python_executions'],1)

    def test_denial_before_actual_limit_is_rejected(self):
        with self.assertRaises(ValueError): native_audit.audit_role(self.root,self.directory,action_limits={1:4})

    def test_successful_unmirrored_execution_cannot_be_hidden_as_denial(self):
        next(row for row in self.rows if row['direction']=='client' and row['message'].get('id')==999)['message']['result']['success']=True
        self.save()
        with self.assertRaises(ValueError): native_audit.audit_role(self.root,self.directory,action_limits={1:3})


class RuntimeBudgetTests(unittest.TestCase):
    def test_e2e_mode_prioritizes_net_benefit_not_an_easy_experiment(self):
        rules,prompt=research_brief(True,prioritize_e2e=True)
        self.assertIn('端到端',prompt)
        self.assertIn('上限',prompt)
        self.assertIn('不能把累计kernel',prompt)
        self.assertIn('先评估',prompt)
        self.assertIn('GPU',rules)
        self.assertNotIn('可读inputs/runtime-metadata.json',rules)

    def test_knowledge_mode_uses_actual_research_without_lifting_cpu_boundaries(self):
        rules,prompt=research_brief(True)
        self.assertIn('自主检索',prompt)
        self.assertIn('实际执行',prompt)
        self.assertIn('GPU',rules)
        self.assertNotIn('这是明确标注的历史失败反馈回顾性验证',rules)
        old_rules,old_prompt=research_brief(False)
        self.assertIn('这是明确标注的历史失败反馈回顾性验证',old_rules)
        self.assertNotEqual(prompt,old_prompt)

    def test_direction_feedback_must_be_in_actual_next_master_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            identity='direction-budget-01'
            packet=dict(value=dict(summary='Script was not executed'),historical_reuse=False)
            path=directory/'turn-03-request.json'
            path.write_text(json.dumps(dict(prompt='Actual state: '+json.dumps(dict(evidence={identity:packet})))))
            verify_master_feedback(directory,2,identity,packet)
            path.write_text(json.dumps(dict(prompt='Actual state: '+json.dumps(dict(evidence={})))))
            with self.assertRaises(ValueError): verify_master_feedback(directory,2,identity,packet)

    def test_direction_receives_own_remaining_allocation_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            campaign=Campaign(Path(temporary),dict(initial={'baseline':{}}))
            campaign.state.apply(comparison())
            action=dict(kind='dispatch',id='budget',brief='Design your own diagnostic',
                allocation=dict(actions=12,cpu_runs=2),reason='Cheap check',based_on=['baseline'])
            campaign.state.apply(action)
            role=dict(actions=12,runs=2,counters=dict(actions=0,cpu_runs=0),directory=Path(temporary),number=1)
            (Path(temporary)/'turn-01-response.json').write_text('{}')
            result=dict(kind='return',summary='No execution claimed',limitations=['Incomplete evidence'])
            with patch.object(campaign,'open_role',return_value=role) as opened, patch.object(campaign,'ask',return_value=result) as asked:
                campaign.direction(action)
            packet=opened.call_args.args[2]
            self.assertEqual(packet['remaining'],dict(actions=12,cpu_runs=2))
            self.assertEqual(packet['allocation'],dict(actions=12,cpu_runs=2))
            self.assertIn('"remaining": {"actions": 12, "cpu_runs": 2}',asked.call_args.args[1])
            self.assertIn('run_python',asked.call_args.args[1])

    def test_archived_launch_source_binds_old_run_without_claiming_new_code_executed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'run'; repository=Path(temporary)/'repository'
            root.mkdir(); repository.mkdir()
            (repository/'runner.py').write_text('launch source')
            manifest=dict(source_sha256={'runner.py':hashlib.sha256(b'launch source').hexdigest()})
            self.assertFalse(verify_runtime_sources(root,manifest,repository)['archived_launch_sources'])
            archive=root/'runtime-source'; archive.mkdir()
            (archive/'runner.py').write_text('launch source')
            (repository/'runner.py').write_text('later fix')
            result=verify_runtime_sources(root,manifest,repository)
            self.assertEqual(result['post_run_modified_sources'],['runner.py'])
            (archive/'runner.py').write_text('changed original')
            with self.assertRaises(ValueError): verify_runtime_sources(root,manifest,repository)


if __name__=='__main__':
    unittest.main()
