import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch


class ExecutorTests(unittest.TestCase):
    def run_script(self,code):
        from harness.experiment_executor import execute_python
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            work=root/'work';work.mkdir()
            (work/'test.py').write_text(code)
            return execute_python(work,'test.py',root/'result')

    def test_real_cpu_script_can_use_stdlib_and_read_workspace(self):
        result=self.run_script('import json, statistics, os\nassert "test.py" in os.listdir(".")\nprint(json.dumps({"value":statistics.mean([1,2,3])}))')
        self.assertEqual(result['exit_code'],0)
        self.assertEqual(json.loads(result['stdout'])['value'],2)
        self.assertTrue(result['landlock_applied'])
        self.assertTrue(result['seccomp_applied'])

    def test_script_cannot_read_host_secret_write_spawn_or_connect(self):
        for code in ('open("/etc/passwd").read()',
                'open("test.py","w").write("changed")',
                'import subprocess; subprocess.run(["/bin/true"])',
                'import socket; socket.socket()',
                'open("/dev/nvidia0","rb")'):
            with self.subTest(code=code):
                self.assertNotEqual(self.run_script(code)['exit_code'],0)

    def test_timeout_and_python_failure_are_feedback_not_success(self):
        self.assertNotEqual(self.run_script('while True: pass')['exit_code'],0)
        result=self.run_script('raise ValueError("agent test failure")')
        self.assertNotEqual(result['exit_code'],0)
        self.assertIn('agent test failure',result['stderr'])

    def test_unsafe_paths_and_symlink_escape_are_rejected(self):
        from harness.experiment_executor import local_path
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'escape').symlink_to('/etc')
            for name in ('../outside','/etc/passwd','escape/passwd','inputs/../test.py',None,42,'a'*241):
                with self.assertRaises(ValueError):local_path(root,name)


class AutonomyTests(unittest.TestCase):
    def test_fixture_full_bridge_audit_and_tamper_rejection(self):
        from exp import autonomy as bridge
        from exp.exploration import write,read
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            archive=base/'source.tar'
            with tarfile.open(archive,'w') as snapshot:
                for name in bridge.SOURCE_NAMES:snapshot.add(bridge.ROOT/name,arcname=name)
            root=base/'session'
            bridge.prepare(root,archive)
            evidence=read(root/'evidence.json')['evidence_sha256']
            roles={}
            def message(role,parsed,direction=None):
                request=bridge.issue(root,role,direction)
                key='master' if role.startswith('master') else direction
                fresh=key not in roles
                agent=roles.setdefault(key,'fixture-'+key)
                raw=json.dumps(dict(parsed,evidence_sha256=evidence))
                receipt=dict(backend='codex-subagent-tool',agent_id=agent,request_sha256=request['request_sha256'],
                    model_selection='inherited-default',resolved_model_id=None,
                    dispatch_tool='multi_agent_v1__spawn_agent' if fresh else 'multi_agent_v1__send_input',
                    dispatch_arguments=dict(message=request['prompt'],**({'fork_context':False} if fresh else {'target':agent})),
                    dispatch_receipt=dict(agent_id=agent),completion_receipt=dict(status={agent:dict(completed=raw)}))
                rawpath=base/'raw';rawpath.write_text(raw)
                receiptpath=base/'receipt';receiptpath.write_text(json.dumps(receipt))
                bridge.accept(root,request['id'],rawpath,receiptpath)
                if role=='direction':return bridge.execute(root,request['id'])
            message('master-plan',dict(schema='autonomy-master-plan-v1',directions=[dict(id='one',hypothesis='fixture only',
                evidence_refs=['E001'],budget=dict(actions=5,runs=1))]))
            for action in (dict(kind='write_file',path='test.py',content='print("fixture lifecycle")'),
                    dict(kind='run_python',path='test.py'),dict(kind='finish',disposition='needs_evidence',
                    observations='fixture completed, not real agent inference',tool_refs=['T002'],limitations=['fixture'])):
                message('direction',dict(schema='autonomy-direction-v1',direction_id='one',hypothesis='fixture',why='test',action=action),'one')
            message('master-review',dict(schema='autonomy-master-review-v1',decisions=[dict(direction_id='one',decision='stop',
                extra_budget=dict(actions=0,runs=0),reason='fixture test done')]))
            result=bridge.audit(root)
            self.assertTrue(result['engineering_loop_passed'])
            self.assertEqual(len(result['real_cpu_runs']),1)
            tool=root/'tools/T002.json'
            altered=read(tool);altered['result']['stdout']='fabricated'
            tool.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError,'feedback edited'):bridge.audit(root)

    def test_master_allocates_budget_not_scientific_executor(self):
        from agents.autonomy import validate_plan
        plan=dict(directions=[dict(id='chosen-by-master',hypothesis='test an evidence-backed hypothesis',
            evidence_refs=['E001'],budget=dict(actions=8,runs=2))])
        validate_plan(plan,{'E001':{}})
        plan['directions'][0]['budget']['runs']=9
        with self.assertRaises(ValueError):validate_plan(plan,{'E001':{}})

    def test_generic_action_validation_has_no_science_registry_or_gpu(self):
        from agents.autonomy import validate_action
        validate_action(dict(kind='write_file',path='experiment.py',content='print(1)'))
        validate_action(dict(kind='run_python',path='experiment.py'))
        with self.assertRaises(ValueError):validate_action(dict(kind='gpu_submit',command='northjob create'))

    def test_master_can_reallocate_unused_ceiling_and_then_stop(self):
        from exp.autonomy import initial,apply_master
        state=initial()
        apply_master(state,'master-plan',dict(directions=[dict(id='direction-one',hypothesis='fixture',
            evidence_refs=['E001'],budget=dict(actions=5,runs=1))]))
        state['tasks']['direction-one']['closed']=True
        apply_master(state,'master-review',dict(decisions=[dict(direction_id='direction-one',decision='continue',
            extra_budget=dict(actions=2,runs=1),reason='fixture feedback justifies another run')]))
        self.assertEqual(state['allocated'],dict(actions=7,runs=2))
        self.assertFalse(state['tasks']['direction-one']['closed'])
        state['tasks']['direction-one']['closed']=True
        apply_master(state,'master-review',dict(decisions=[dict(direction_id='direction-one',decision='stop',
            extra_budget=dict(actions=0,runs=0),reason='fixture stop')]))
        self.assertTrue(state['finished'])

    def test_real_executor_returns_failure_then_accepts_agent_repair(self):
        from exp.autonomy import initial,apply_master,execute,write,read,save_state
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('requests','responses','tools','executions','work/one'):(root/name).mkdir(parents=True)
            state=initial()
            apply_master(state,'master-plan',dict(directions=[dict(id='one',hypothesis='fixture-only lifecycle',
                evidence_refs=['E001'],budget=dict(actions=8,runs=2))]))
            save_state(root,state)
            actions=[dict(kind='write_file',path='test.py',content='raise ValueError("fixture failure")'),
                dict(kind='run_python',path='test.py'),dict(kind='write_file',path='test.py',content='print("fixture repaired")'),
                dict(kind='run_python',path='test.py')]
            records=[]
            for number,action in enumerate(actions,1):
                name=f'R{number:03d}'
                write(root/'requests'/f'{name}.json',dict(role='direction',direction_id='one'))
                write(root/'responses'/f'{name}.json',dict(parsed=dict(action=action)))
                records.append(execute(root,name))
            self.assertNotEqual(records[1]['result']['exit_code'],0)
            self.assertEqual(records[3]['result']['exit_code'],0)
            self.assertIn('fixture repaired',records[3]['result']['stdout'])
            self.assertEqual(read(root/'state.json')['used'],dict(actions=4,runs=2))

    def test_inputs_are_immutable_and_gpu_denials_are_feedback(self):
        from exp.autonomy import run_action
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'work/one/inputs').mkdir(parents=True)
            for action in (dict(kind='write_file',path='inputs/evidence.json',content='{}'),
                    dict(kind='read_stock',path='../another-engine/file.py',offset=0),
                    dict(kind='gpu_submit',command='never executed')):
                with self.assertRaises(ValueError):run_action(root,'one',action,1)

    def test_default_executor_does_not_inherit_parent_secrets(self):
        with patch.dict('os.environ',UNTRUSTED_PARENT_TEST_SECRET='fixture-secret'):
            result=ExecutorTests().run_script('import os\nprint(os.environ.get("UNTRUSTED_PARENT_TEST_SECRET", "not-present"))')
        self.assertEqual(result['exit_code'],0)
        self.assertIn('not-present',result['stdout'])


if __name__=='__main__':
    unittest.main()
