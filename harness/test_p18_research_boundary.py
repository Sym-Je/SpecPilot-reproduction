import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ResearchBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.work=self.root/'work'
        (self.work/'scratch').mkdir(parents=True)
        (self.work/'inputs').mkdir()
        (self.work/'inputs/evidence.json').write_text('{"fixture":true}\n')
        self.canary=self.root/'protected.txt'
        self.canary.write_text('nonsecret fixture canary\n')
        self.digest=hashlib.sha256(self.canary.read_bytes()).hexdigest()

    def run_role(self,code):
        from harness.research_boundary import launch_command
        return launch_command(self.work,[sys.executable,'-I','-B','-c',code],
            executables=[sys.executable],readonly=[sys.prefix],network=False,timeout=10)

    def test_role_can_read_inputs_and_write_scratch(self):
        result=self.run_role('from pathlib import Path; print(Path("inputs/evidence.json").read_text()); Path("scratch/a.txt").write_text("allowed")')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('fixture',result.stdout)
        self.assertEqual((self.work/'scratch/a.txt').read_text(),'allowed')

    def test_individual_runtime_metadata_grant_does_not_grant_parent(self):
        from harness.research_boundary import launch_command
        state=self.root/'state.txt';state.write_text('fixture')
        code=f'open({str(state)!r},"w").write("allowed metadata"); open({str(self.canary)!r},"w").write("wrong")'
        result=launch_command(self.work,[sys.executable,'-I','-B','-c',code],executables=[sys.executable],
            readonly=[sys.prefix],writable=[state])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(state.read_text(),'allowed metadata')
        self.assertEqual(hashlib.sha256(self.canary.read_bytes()).hexdigest(),self.digest)

    def test_role_rejects_host_reads_writes_and_readonly_input_writes(self):
        for code in (f'open({str(self.canary)!r}).read()',f'open({str(self.canary)!r},"w").write("wrong")',
                'open("inputs/evidence.json","w").write("wrong")'):
            with self.subTest(code=code):self.assertNotEqual(self.run_role(code).returncode,0)
        self.assertEqual(hashlib.sha256(self.canary.read_bytes()).hexdigest(),self.digest)
        self.assertEqual(json.loads((self.work/'inputs/evidence.json').read_text()),dict(fixture=True))

    def test_truncate_symlink_hardlink_and_replace_cannot_bypass(self):
        for code in (f'import os; os.truncate({str(self.canary)!r},0)',
                f'import os; os.open({str(self.canary)!r},os.O_RDONLY|os.O_TRUNC)',
                f'import os; os.symlink({str(self.canary)!r},"scratch/alias")',
                f'import os; os.link({str(self.canary)!r},"scratch/alias")',
                f'from pathlib import Path; Path("scratch/replace").write_text("wrong"); Path("scratch/replace").replace({str(self.canary)!r})'):
            with self.subTest(code=code):self.assertNotEqual(self.run_role(code).returncode,0)
        self.assertEqual(hashlib.sha256(self.canary.read_bytes()).hexdigest(),self.digest)

    def test_preexisting_symlink_cannot_escape(self):
        (self.work/'scratch/alias').symlink_to(self.canary)
        self.assertNotEqual(self.run_role('open("scratch/alias").read()').returncode,0)

    def test_restrictions_survive_exec_and_environment_is_scrubbed(self):
        child=f'open({str(self.canary)!r}).read()'
        code=f'import os; os.execv({sys.executable!r},[{sys.executable!r},"-I","-B","-c",{child!r}])'
        self.assertNotEqual(self.run_role(code).returncode,0)
        from unittest.mock import patch
        with patch.dict(os.environ,BOUNDARY_TEST_SECRET='must-not-inherit'):
            result=self.run_role('import os; print(os.environ.get("BOUNDARY_TEST_SECRET","absent"))')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('absent',result.stdout)

    def test_network_is_denied_in_offline_probe_and_unlisted_exec_is_denied(self):
        for code in ('import socket; socket.socket()', 'import os; os.execv("/bin/sh",["sh","-c","true"])'):
            with self.subTest(code=code):self.assertNotEqual(self.run_role(code).returncode,0)

    def test_tool_broker_keeps_general_read_write_and_cpu_execution(self):
        from harness.research_tools import dispatch
        records=self.root/'audit'
        result=dispatch(self.work,dict(kind='write_file',path='scratch/test.py',content='print("CPU fixture")'),records)
        self.assertEqual(result['status'],'completed')
        result=dispatch(self.work,dict(kind='read_file',path='scratch/test.py'),records)
        self.assertIn('CPU fixture',result['content'])
        result=dispatch(self.work,dict(kind='run_python',path='scratch/test.py'),records/'execution')
        self.assertEqual(result['exit_code'],0,result['stderr'])
        self.assertTrue(result['landlock_applied'] and result['seccomp_applied'])
        self.assertIn('CPU fixture',result['stdout'])

    def test_broker_rejects_path_and_resource_bypasses(self):
        from harness.research_tools import dispatch
        (self.work/'scratch/alias.py').symlink_to(self.canary)
        actions=[dict(kind='read_file',path='../protected.txt'),
            dict(kind='write_file',path='inputs/evidence.json',content='wrong'),
            dict(kind='read_file',path='scratch/alias.py'),
            dict(kind='gpu_submit',command='northjob create'),dict(kind='shell',command='true')]
        for action in actions:
            with self.subTest(action=action),self.assertRaises(ValueError):dispatch(self.work,action,self.root/'audit')

    def test_authorized_stock_source_access_is_retained(self):
        from harness.research_tools import dispatch
        listing=dispatch(self.work,dict(kind='list_stock',prefix='python/sglang/',offset=0),self.root/'audit')
        self.assertEqual(listing['status'],'completed')
        self.assertTrue(listing['files'])
        result=dispatch(self.work,dict(kind='read_stock',path=listing['files'][0],offset=0),self.root/'audit')
        self.assertEqual(result['status'],'completed')
        self.assertIn('sha256',result)
        with self.assertRaises(ValueError):dispatch(self.work,dict(kind='read_stock',path='../another-engine/code.py',offset=0),self.root/'audit')

    def test_cpu_experiment_cannot_read_host_connect_or_spawn(self):
        from harness.research_tools import dispatch
        for index,code in enumerate((f'open({str(self.canary)!r}).read()',
                'import socket; socket.socket()', 'import subprocess; subprocess.run(["/bin/true"])')):
            (self.work/'scratch/test.py').write_text(code)
            result=dispatch(self.work,dict(kind='run_python',path='scratch/test.py'),self.root/f'run{index}')
            self.assertNotEqual(result['exit_code'],0)

    def test_launcher_refuses_broad_or_unlisted_executable(self):
        from harness.research_boundary import ROOT,launch_command
        with self.assertRaises(ValueError):launch_command(self.work,['/bin/sh','-c','true'],executables=[sys.executable])
        for root in (Path('/'),ROOT,ROOT.parent):
            with self.assertRaises(ValueError):launch_command(self.work,[sys.executable,'-V'],executables=[sys.executable],readonly=[root])

    def test_transport_binds_role_and_rejects_forged_tool_identity(self):
        from harness.research_protocol import ResearchBroker
        broker=ResearchBroker(self.work,self.root/'audit','thread-fixture','turn-fixture')
        valid=dict(threadId='thread-fixture',turnId='turn-fixture',callId='one',namespace=None,
            tool='research',arguments=dict(action=dict(kind='read_file',path='inputs/evidence.json')))
        result=broker.handle(valid)
        self.assertTrue(result['success'])
        for key,value in (('threadId','other'),('turnId','other'),('namespace','shell'),('tool','exec_command')):
            with self.subTest(key=key),self.assertRaises(ValueError):broker.handle(dict(valid,**{key:value}))

    def test_transport_denies_gpu_and_caps_actions_and_runs(self):
        from harness.research_protocol import ResearchBroker
        broker=ResearchBroker(self.work,self.root/'audit','thread-fixture','turn-fixture',max_actions=1,max_runs=0)
        request=dict(threadId='thread-fixture',turnId='turn-fixture',callId='one',namespace=None,
            tool='research',arguments=dict(action=dict(kind='gpu_submit',command='northjob create')))
        self.assertFalse(broker.handle(request)['success'])
        with self.assertRaises(ValueError):broker.handle(dict(request,callId='two'))
        self.assertEqual(broker.runs,0)

    def test_transport_does_not_replay_calls_or_accept_malformed_arguments(self):
        from harness.research_protocol import ResearchBroker
        broker=ResearchBroker(self.work,self.root/'audit','thread-fixture','turn-fixture')
        request=dict(threadId='thread-fixture',turnId='turn-fixture',callId='one',namespace=None,
            tool='research',arguments=dict(action=dict(kind='read_file',path='inputs/evidence.json')))
        broker.handle(request)
        with self.assertRaises(ValueError):broker.handle(request)
        for index,arguments in enumerate((dict(action=dict(kind=[])),dict(action={},approved=True),None)):
            self.assertFalse(broker.handle(dict(request,callId=f'invalid-{index}',arguments=arguments))['success'])
        limited=ResearchBroker(self.work,self.root/'limited','thread-fixture','turn-fixture',max_runs=0)
        response=limited.handle(dict(request,arguments=dict(action=dict(kind='run_python',path='scratch/test.py'))))
        self.assertFalse(response['success'])
        self.assertEqual(limited.runs,0)

    def test_live_verifier_cannot_promote_text_or_partial_tool_success(self):
        from exp.codex_boundary import verify_live
        directory=self.root/'live';directory.mkdir()
        result=dict(turn=dict(status='completed'),canary_unchanged=True,rules_unchanged=True,evidence_unchanged=True,config_unchanged=True)
        verify_live(directory,result)
        self.assertFalse(result['live_model_probe_passed'])

    def test_independent_transport_audit_binds_requests_responses_and_policy(self):
        from harness.research_integrity import verify_transport
        import copy
        thread=dict(thread=dict(id='thread'),approvalPolicy='never')
        turn=dict(id='turn',status='completed')
        request=dict(threadId='thread',turnId='turn',callId='call',namespace=None,tool='research')
        response=dict(success=False,contentItems=[])
        wire=[dict(direction='client',message=dict(id=1,method='thread/start',params=dict(approvalPolicy='never'))),
            dict(direction='server',message=dict(id=1,result=thread)),
            dict(direction='server',message=dict(id='native',method='item/tool/call',params=request)),
            dict(direction='client',message=dict(id='native',result=response)),
            dict(direction='server',message=dict(method='turn/completed',params=dict(threadId='thread',turn=turn)))]
        self.assertEqual(verify_transport(wire,[(request,response)]),(thread,turn))
        with self.assertRaises(ValueError):verify_transport(wire,[(request,dict(success=True))])
        altered=copy.deepcopy(wire);altered[1]['message']['result']['approvalPolicy']='on-request'
        with self.assertRaises(ValueError):verify_transport(altered,[(request,response)])
        with self.assertRaises(ValueError):verify_transport(wire,[])
