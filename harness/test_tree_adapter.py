from pathlib import Path
import json
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from exp.tree_adapter import LIMITS, execution_plan, interrupted_usage, validate_admission
from exp.source_autonomy import ask, choose, run
from harness.source_candidate import file_sha
from harness.source_audit import audit as audit_source


class TreeAdapterTests(unittest.TestCase):
    def test_master_finish_alias_preserves_its_stop_conclusion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);master=dict(directory=root,number=1)
            original=dict(action={'kind':'finish'},candidate=False,conclusion='stop faulty candidate')
            with patch('exp.source_autonomy.ask',return_value=original):
                value=choose(master,'review',{},root)
            self.assertEqual(value,dict(decision='stop',reason=original['conclusion']))
            self.assertEqual(json.loads((root/'turn-01-decision-alias.json').read_text())['original'],original)

    def test_master_overallocation_is_repaired_without_changing_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            counters=dict(actions=500,cpu_runs=60,gpu_attempts=15)
            invalid=dict(decision='explore',allocation=dict(actions=100,cpu_runs=20,gpu_attempts=2))
            with patch('exp.source_autonomy.ask',side_effect=[invalid,{'decision':'stop','reason':'insufficient allowance'}]) as mocked:
                value=choose({},'review',counters,root)
            self.assertEqual(value['decision'],'stop')
            self.assertEqual(mocked.call_count,2)
            self.assertEqual(counters,dict(actions=500,cpu_runs=60,gpu_attempts=15))

    def test_continuation_counts_skip_direction_conclusion_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'master').mkdir()
            (root/'master/wire.jsonl').write_text('')
            counters=dict(actions=0,cpu_runs=0,gpu_attempts=0,model_turns=0,usage_updates=0)
            (root/'result.json').write_text(json.dumps({'counters':counters}))
            (root/'direction-conclusion-01.json').write_text('{}')
            self.assertEqual(interrupted_usage(root)[0],counters)

    def test_json_failure_is_repaired_by_the_same_native_role(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'role';directory.mkdir()
            (directory/'turn-01-native.json').write_text('{}')
            role=dict(directory=directory,number=1)
            expected={'action':{'kind':'finish'}}
            with patch('exp.source_autonomy.roles.turn',side_effect=[ValueError('one complete JSON response required'),expected]) as turn:
                self.assertEqual(ask(role,'original',{},root),expected)
            self.assertEqual(turn.call_count,2)
            self.assertEqual(turn.call_args_list[1].args[1],
                '模型JSON/协议格式未通过：one complete JSON response required。仅修复格式，保留自己的科学判断，重交完整JSON对象。')

    def test_nonparser_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);role=dict(directory=root,number=1)
            with patch('exp.source_autonomy.roles.turn',side_effect=ValueError('budget exhausted')) as turn:
                with self.assertRaises(ValueError):ask(role,'original',{},root)
            self.assertEqual(turn.call_count,1)

    def test_audit_requires_this_stage_explicit_resource_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'resource-state.json').write_text(json.dumps(dict(LIMITS,jobs=[])))
            with self.assertRaises(ValueError):audit_source(root)
            self.assertEqual(audit_source(root,limits=LIMITS)['conservative_gpu_seconds'],0)

    def test_history_audit_requires_unchanged_budget_and_exact_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous=Path(temporary)/'previous';previous.mkdir()
            current=Path(temporary)/'current';current.mkdir()
            state=dict(LIMITS,jobs=[],started=1)
            (current/'resource-state.json').write_text(json.dumps(state))
            (previous/'result.json').write_text(json.dumps(dict(resource_state=state)))
            (current/'continuation.json').write_text(json.dumps(dict(prior_root=str(previous))))
            value=audit_source(current,limits=LIMITS,history_roots=[previous])
            self.assertEqual(value['conservative_gpu_seconds'],0)
            (previous/'result.json').write_text(json.dumps(dict(resource_state=dict(state,started=2))))
            with self.assertRaisesRegex(ValueError,'historical resource'):
                audit_source(current,limits=LIMITS,history_roots=[previous])

    def test_history_audit_rejects_omitted_or_duplicate_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prior=root/'prior';prior.mkdir()
            (root/'resource-state.json').write_text(json.dumps(dict(LIMITS,jobs=[])))
            (root/'continuation.json').write_text(json.dumps(dict(prior_root=str(prior))))
            with self.assertRaisesRegex(ValueError,'lineage'):
                audit_source(root,limits=LIMITS,history_roots=[])
            with self.assertRaisesRegex(ValueError,'lineage'):
                audit_source(root,limits=LIMITS,history_roots=[prior,prior])

    def test_interruption_cannot_be_asserted_without_actual_birth_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'resource-state.json').write_text(json.dumps(dict(LIMITS,jobs=[])))
            (root/'result.json').write_text(json.dumps(dict(status='running',controller_accepted=False)))
            with self.assertRaisesRegex(ValueError,'birth inventory'):
                audit_source(root,limits=LIMITS,interrupted=True)

    def test_interruption_rejects_live_child_and_never_invents_exit_code(self):
        from controller.phase4_final import record_birth
        from harness.source_audit import absent_processes
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);processes=root/'processes';processes.mkdir(mode=0o700)
            child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
            try:
                record_birth(child,'nonsecret test fixture',processes)
                with self.assertRaisesRegex(ValueError,'still present'):
                    absent_processes(root)
            finally:
                child.terminate();child.wait(timeout=5)
            rows=absent_processes(root)
            self.assertEqual(len(rows),1)
            self.assertIsNone(rows[0]['exit_code'])

    def test_new_budget_is_not_the_old_source_default(self):
        self.assertEqual(LIMITS,dict(gpu_seconds=28800,wall_seconds=28800,concurrent_gpus=2))

    def test_admission_binds_exact_command_source_request_and_budget(self):
        plan=dict(command=['trusted','command'],source_sha256='a'*64,request_sha256='b'*64,
            resource_state='/trusted/resource.json',name='unique',total_gpus=2)
        with self.assertRaises(ValueError):validate_admission(plan,{'approved':True})
        receipt=dict(approved=True,plan=plan)
        self.assertEqual(validate_admission(plan,receipt),plan)
        changed=dict(plan,total_gpus=1)
        with self.assertRaises(ValueError):validate_admission(changed,receipt)

    def test_execution_plan_uses_stage_paths_and_bounded_deadlines(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'unique';directory.mkdir()
            (directory/'request.json').write_text('{"mode":"source-research"}')
            source=directory/'source.tar';source.write_bytes(b'source')
            with patch('exp.tree_adapter.source_command',return_value=['trusted','command']):
                plan=execution_plan(directory,source,Path(temporary)/'resource.json')
            self.assertEqual(plan['total_gpus'],2)
            self.assertEqual(plan['deadline_seconds'],1800)
            self.assertEqual(plan['priority_class'],'higher-priority-job')
            self.assertNotIn('16',str(LIMITS))

    def test_full_controller_protocol_keeps_its_original_two_hour_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            (directory/'request.json').write_text('{"mode":"source-controller"}')
            source=directory/'source.tar';source.write_bytes(b'source')
            with patch('exp.tree_adapter.source_command',return_value=['trusted','command']):
                plan=execution_plan(directory,source,directory/'resource.json')
            self.assertEqual(plan['deadline_seconds'],7200)

    def test_context_stop_does_not_spend_gpu_or_require_a_fake_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            work=root/'work';(work/'inputs').mkdir(parents=True)
            home=root/'home';home.mkdir()
            paths={'canary':root/'canary','rules':work/'inputs/rules.txt',
                'evidence':work/'inputs/evidence.json','config':home/'config.toml'}
            for path in paths.values():path.write_text('harmless fixture')
            manifest=dict(work=str(work),home=str(home),canary=str(paths['canary']),
                canary_sha256=file_sha(paths['canary']),rules_sha256=file_sha(paths['rules']),
                evidence_sha256=file_sha(paths['evidence']),config_sha256=file_sha(paths['config']))
            role=dict(manifest=manifest,client=SimpleNamespace(close=Mock(),process=SimpleNamespace(returncode=0)))
            context=SimpleNamespace(packet={'scope':'fixture only'},rules='fixture',job_prefix='unique',
                master_brief='bounded fixture',budget=SimpleNamespace(read=lambda:{'jobs':[]}),
                execute=Mock(),freeze=Mock(),session=Mock(return_value=role))
            with patch('exp.source_autonomy.ask',return_value={'decision':'stop','reason':'no viable candidate'}),\
                    patch('exp.source_autonomy.stage_budget',side_effect=AssertionError('legacy budget forbidden')),\
                    patch('exp.source_autonomy.roles.ACTION_LIMIT'),\
                    patch('exp.source_autonomy.roles.RUN_LIMITS'),\
                    patch('exp.source_autonomy.roles.COMMON'):
                run(root,context=context)
            context.execute.assert_not_called()
            value=json.loads((root/'result.json').read_text())
            self.assertEqual(value['status'],'completed')
            self.assertFalse(value['full_phase1_completed'])
            self.assertFalse(value['source_experiment_completed'])
