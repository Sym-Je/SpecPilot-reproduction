import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


class GpuPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work=Path(self.temporary.name)
        self.pin='a'*40
        for name,content in (('experiment.py','print("fixture, not real research")\n'),
                ('acceptance.py','raise SystemExit(0)\n'),('inputs/public.json','{}\n')):
            path=self.work/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content)
        self.request=dict(schema='autonomy-gpu-request-v1',direction_id='fixture-only',
            hypothesis='fixture interface check, not a scientific proposal',source_pin=self.pin,
            script=dict(path='experiment.py',sha256=self.sha('experiment.py')),
            acceptance=dict(path='acceptance.py',sha256=self.sha('acceptance.py')),
            inputs=[dict(path='inputs/public.json',sha256=self.sha('inputs/public.json'))],
            resources=dict(nodes=1,gpus_per_node=1,gpu_type='h100',wall_minutes=10,memory_gib=80),
            proposed_image=None,stop_condition='fixture only: stop on nonzero exit')

    def sha(self,name):
        return hashlib.sha256((self.work/name).read_bytes()).hexdigest()

    def inspect(self,request=...):
        from harness.gpu_preflight import inspect_request
        return inspect_request(self.work,self.request if request is ... else request,self.pin)

    def test_valid_request_is_bound_but_never_authorizes_submission(self):
        result=self.inspect()
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['requested_total_gpus'],1)
        self.assertEqual(result['requested_gpu_minutes'],10)
        self.assertEqual(len(result['files']),3)
        self.assertFalse(result['submission_allowed'])
        self.assertFalse(result['submitted'])
        self.assertFalse(result['process_started'])
        self.assertIsNone(result['gpu_test_passed'])
        self.assertIsNone(result['job_uuid'])
        self.assertIn('backend_tool_boundary_unenforced',result['blockers'])
        self.assertIn('stage_gpu_authorization_missing',result['blockers'])
        self.assertIn('gpu_executor_not_connected',result['blockers'])
        self.assertEqual(self.inspect(),result)

    def test_agent_cannot_self_attest_isolation_or_authorize_resources(self):
        for key,value in (('backend_isolated',True),('gpu_authorized',True),
                ('submit',True),('command','northjob create'),('tools',[])):
            request=copy.deepcopy(self.request)
            request[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.inspect(request)

    def test_changed_script_input_acceptance_or_pin_is_rejected(self):
        for key in ('script','acceptance','inputs','source_pin'):
            request=copy.deepcopy(self.request)
            if key=='source_pin':request[key]='b'*40
            elif key=='inputs':request[key][0]['sha256']='b'*64
            else:request[key]['sha256']='b'*64
            with self.subTest(key=key),self.assertRaises(ValueError):self.inspect(request)

    def test_unsafe_paths_symlinks_and_duplicate_inputs_are_rejected(self):
        (self.work/'alias.py').symlink_to(self.work/'experiment.py')
        for name in ('../outside.py','/etc/passwd','alias.py','inputs/../experiment.py','experiment.py/'):
            request=copy.deepcopy(self.request)
            request['script']['path']=name
            with self.subTest(name=name),self.assertRaises(ValueError):self.inspect(request)
        self.request['inputs'].append(self.request['inputs'][0])
        with self.assertRaises(ValueError):self.inspect()
        self.request['inputs'][1]=dict(path='inputs//public.json',sha256=self.sha('inputs/public.json'))
        with self.assertRaises(ValueError):self.inspect()

    def test_strict_resource_types_and_bounds(self):
        for key,value in (('nodes',0),('nodes',2),('gpus_per_node',True),('gpus_per_node',0),
                ('gpus_per_node',9),('wall_minutes',0),('wall_minutes',61),
                ('memory_gib',257),('gpu_type','b300')):
            request=copy.deepcopy(self.request)
            request['resources'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.inspect(request)
        request=copy.deepcopy(self.request)
        request['resources']['privileged']=True
        with self.assertRaises(ValueError):self.inspect(request)

    def test_image_proposal_is_not_image_approval(self):
        self.request['proposed_image']='harbor.invalid/fixture@sha256:'+'c'*64
        result=self.inspect()
        self.assertIn('stage_gpu_authorization_missing',result['blockers'])
        self.assertFalse(result['submission_allowed'])
        for image in ('latest','image; northjob create','image\nextra',True):
            self.request['proposed_image']=image
            with self.subTest(image=image),self.assertRaises(ValueError):self.inspect()

    def test_request_limit_is_not_a_gpu_budget(self):
        self.request['resources'].update(gpus_per_node=8,wall_minutes=60)
        result=self.inspect()
        self.assertEqual(result['requested_total_gpus'],8)
        self.assertEqual(result['requested_gpu_minutes'],480)
        self.assertFalse(result['submission_allowed'])

    def test_missing_oversized_and_wrong_type_files_are_rejected(self):
        for name in ('missing.py','inputs','inputs/public.json'):
            request=copy.deepcopy(self.request)
            request['script']['path']=name
            with self.subTest(name=name),self.assertRaises(ValueError):self.inspect(request)
        (self.work/'experiment.py').write_bytes(b'x'*32769)
        self.request['script']['sha256']=self.sha('experiment.py')
        with self.assertRaises(ValueError):self.inspect()

    def test_malformed_requests_are_rejected(self):
        for field,value in (('schema','wrong'),('direction_id','master'),('hypothesis',' '),
                ('source_pin','not-a-pin'),('stop_condition',''),('inputs',{}),
                ('script',[]),('acceptance',dict(path='acceptance.py'))):
            request=copy.deepcopy(self.request)
            request[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.inspect(request)
        for request in (None,[],True,{},dict(self.request,resources=[])):
            with self.subTest(request=request),self.assertRaises(ValueError):self.inspect(request)

    def test_preflight_does_not_execute_experiment_or_acceptance(self):
        for field in ('script','acceptance'):
            path=self.work/self.request[field]['path']
            path.write_text('raise RuntimeError("must never execute in preflight")\n')
            self.request[field]['sha256']=self.sha(self.request[field]['path'])
        self.assertEqual(self.inspect()['status'],'blocked')

    def test_cpu_bridge_still_rejects_gpu_submission(self):
        from agents.autonomy import validate_action
        with self.assertRaises(ValueError):validate_action(dict(kind='gpu_submit',request=self.request))

    def test_cli_persists_blocked_result_and_refuses_overwrite(self):
        from exp.gpu_preflight import main
        from unittest.mock import patch
        import io
        request=self.work/'request.json'
        output=self.work/'result.json'
        request.write_text(json.dumps(self.request))
        args=['--work',str(self.work),'--request',str(request),'--output',str(output)]
        with patch('exp.gpu_preflight.source_pin',return_value=self.pin),patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(main(args),75)
            with self.assertRaises(FileExistsError):main(args)
        self.assertEqual(json.loads(output.read_text()),self.inspect())
