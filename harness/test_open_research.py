import copy
import json
from pathlib import Path
import tempfile
import unittest

from harness.open_research import OpenAccess
from harness.source_candidate import apply_edits,build_bundle,candidate_arm,file_sha,load_bundle,validate_patch
from harness import test_source_candidate as candidate_fixture


class OpenAccessTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.stock=self.root/'stock';self.work=self.root/'work'
        (self.stock/'python/sglang/kernels').mkdir(parents=True)
        (self.work/'scratch').mkdir(parents=True);(self.work/'inputs').mkdir()
        self.source=self.stock/'python/sglang/kernels/example.cu'
        self.source.write_text('__global__ void observed_kernel() {}\n')
        self.access=OpenAccess('Master',{},self.root/'tools',self.root/'cache',
            baseline_loader=lambda:{'fixture':True},stock=self.stock)

    def call(self,action):
        directory=self.root/('record-'+str(len(list(self.root.glob('record-*')))))
        return self.access.dispatch(self.work,action,directory)

    def test_cuda_source_read_list_and_search_have_actual_source_sha(self):
        answer=self.call(dict(kind='read_stock',path=self.source.relative_to(self.stock).as_posix(),offset=0))
        self.assertEqual(answer['sha256'],file_sha(self.source))
        self.assertIn('observed_kernel',answer['content'])
        answer=self.call(dict(kind='list_stock',prefix='python/sglang/',offset=0))
        self.assertIn(self.source.relative_to(self.stock).as_posix(),answer['files'])
        answer=self.call(dict(kind='search_stock',prefix='python/sglang/',query='observed_kernel',offset=0))
        self.assertEqual(answer['total_matches'],1)

    def test_absolute_paths_traversal_symlinks_and_binary_reads_refused(self):
        (self.stock/'python/sglang/kernels/alias.cu').symlink_to(self.root/'outside')
        (self.stock/'python/sglang/kernels/library.so').write_bytes(b'not executable fixture')
        for name in ('../controller/test.py','/tmp/secret','python/sglang/kernels/alias.cu',
                'python/sglang/kernels/library.so','.git/config'):
            with self.subTest(name=name),self.assertRaises((ValueError,OSError)):
                self.call(dict(kind='read_stock',path=name,offset=0))

    def test_workspace_cuda_write_and_sha_bound_append(self):
        self.call(dict(kind='write_file',path='scratch/candidate.cu',content='first\n'))
        path=self.work/'scratch/candidate.cu';digest=file_sha(path)
        self.call(dict(kind='append_file',path='scratch/candidate.cu',expected_sha256=digest,content='second\n'))
        self.assertEqual(path.read_text(),'first\nsecond\n')
        with self.assertRaises(ValueError):
            self.call(dict(kind='append_file',path='scratch/candidate.cu',expected_sha256=digest,content='duplicate'))
        with self.assertRaises(ValueError):
            self.call(dict(kind='write_file',path='inputs/rules.txt',content='changed'))
        self.call(dict(kind='write_file',path='scratch/source.py.stock',content='source evidence'))
        answer=self.call(dict(kind='list_stock',prefix='',offset=0))
        self.assertIn(self.source.relative_to(self.stock).as_posix(),answer['files'])
        answer=self.call(dict(kind='search_stock',prefix=self.source.relative_to(self.stock).as_posix(),query='observed_kernel',offset=0))
        self.assertEqual(answer['total_matches'],1)

    def test_extended_cpu_still_denies_network_subprocess_and_protected_files(self):
        self.call(dict(kind='write_file',path='scratch/check.py',content='''import socket,subprocess
from pathlib import Path
for operation in (lambda: socket.socket(),lambda: subprocess.run(["/bin/true"]),lambda: Path("/etc/passwd").read_text()):
    try: operation()
    except (PermissionError,OSError): pass
    else: raise AssertionError("escaped research boundary")
print("BOUNDARY_PASS")
'''))
        result=self.call(dict(kind='run_python',path='scratch/check.py'))
        self.assertEqual(result['exit_code'],0,result['stderr'])
        self.assertTrue(result['landlock_applied'] and result['seccomp_applied'])
        self.assertIn('BOUNDARY_PASS',result['stdout'])


class OpenSourceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=candidate_fixture.SourceCandidateTests();self.fixture.setUp()
        self.addCleanup(self.fixture.temporary.cleanup)
        self.patch=copy.deepcopy(self.fixture.patch);self.patch['schema']='source-option-v2'

    def test_more_than_eight_edits_and_new_cuda_file_default_to_stock(self):
        for number in range(9):
            self.patch['edits'].append(dict(path=f'python/sglang/kernels/new_{number}.cu',
                base_sha256=None,find='',replace='__global__ void fixture_kernel() {}\n'))
        self.fixture.patch_path.write_text(json.dumps(self.patch))
        bundle=self.fixture.root/'extended'
        manifest=build_bundle(self.fixture.base,self.fixture.patch_path,bundle)
        self.assertEqual(len(manifest['changed_files']),10)
        self.assertFalse(candidate_arm(bundle)['option_enabled'])
        self.assertEqual(candidate_arm(bundle)['engine'],str(self.fixture.stock))
        self.assertTrue(candidate_arm(bundle,enabled=True)['option_enabled'])
        self.assertEqual(load_bundle(bundle),manifest)
        (bundle/'engine/python/sglang/kernels/new_0.cu').write_text('changed')
        with self.assertRaises(ValueError):load_bundle(bundle)

    def test_new_file_must_not_overwrite_existing_source_or_escape_runtime(self):
        for name in (self.fixture.path,'../controller/test.py','python/sglang/srt/probe.sh'):
            value=copy.deepcopy(self.patch)
            value['edits']=[dict(path=name,base_sha256=None,find='',replace='fixture')]
            with self.subTest(name=name),self.assertRaises(ValueError):
                apply_edits(self.fixture.stock,value)

    def test_v1_still_refuses_cuda_files_and_more_than_eight_edits(self):
        value=copy.deepcopy(self.fixture.patch);value['edits']*=9
        with self.assertRaises(ValueError):validate_patch(value)
        value=copy.deepcopy(self.fixture.patch);value['edits'][0]['path']='python/sglang/kernels/fixture.cu'
        with self.assertRaises(ValueError):validate_patch(value)

    def test_profile_budget_is_bound_to_explicit_new_stage_limits(self):
        from exp.profile_resource import check_budget
        from harness.engine_research import Budget
        limits=dict(gpu_seconds=57600,wall_seconds=43200,concurrent_gpus=4)
        budget=Budget(self.fixture.root/'resource-state.json',limits=limits)
        with self.assertRaises(ValueError):check_budget(budget,self.fixture.root/'job')
        self.assertEqual(check_budget(budget,self.fixture.root/'job',limits=limits)['concurrent_gpus'],4)
        with self.assertRaises(ValueError):check_budget(budget,self.fixture.root/'job',limits={})


class OpenPlanTests(unittest.TestCase):
    def test_workspace_read_replay_preserves_raw_log_sha_with_crlf(self):
        from harness.master_open_audit import workspace_read
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'inputs').mkdir()
            raw=b'line one\r\nline two\r\n'
            (root/'inputs/runtime.log').write_bytes(raw)
            answer=workspace_read(dict(path='inputs/runtime.log',offset=0),root,{})
            self.assertEqual(answer['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(answer['content'],'line one\nline two\n')

    def test_export_audit_checks_copied_contents_not_only_source_digest(self):
        from harness.master_open_audit import verify_export
        from harness.runtime_feedback import export_runtime
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);experiment=root/'experiment';experiment.mkdir()
            (experiment/'request.json').write_text('{"role_thread":"own"}')
            (experiment/'remote.log').write_text('actual startup evidence')
            target=root/'export'
            export_runtime(experiment,target,authorized_root=root,owner_thread='own')
            self.assertEqual(verify_export(target/'index.json',root,owner_thread='own'),2)
            (target/'remote.log').write_text('changed evidence')
            with self.assertRaises(ValueError):verify_export(target/'index.json',root,owner_thread='own')

    def test_runtime_gap_check_decodes_native_json_and_rejects_unrelated_stop(self):
        from exp.master_open_continue import recorded_runtime_gap
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);direction=root/'direction-d1';direction.mkdir()
            path=direction/'research-result.json'
            path.write_text(json.dumps({'conclusion':'详细远端日志未能通过research授权路径读取'}))
            self.assertTrue(recorded_runtime_gap(root))
            path.write_text(json.dumps({'conclusion':'完整日志已读取；没有收益，停止'}))
            self.assertFalse(recorded_runtime_gap(root))

    def test_continuation_uses_cumulative_expanded_limits_without_reset(self):
        from exp.source_autonomy import choose
        from unittest.mock import patch
        counters=dict(actions=600,cpu_runs=100,gpu_attempts=3)
        proposed=dict(decision='explore',allocation=dict(actions=100,cpu_runs=20,gpu_attempts=1))
        with tempfile.TemporaryDirectory() as temporary,patch('exp.source_autonomy.ask',return_value=proposed):
            self.assertEqual(choose({},'review',counters,Path(temporary),
                limits=dict(actions=1200,cpu_runs=256,gpu_attempts=16)),proposed)
        self.assertEqual(counters,dict(actions=600,cpu_runs=100,gpu_attempts=3))

    def test_continuation_direction_does_not_receive_other_direction_context(self):
        from exp.master_open_continue import Context
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);parent=root/'parent';parent.mkdir()
            (parent/'evidence.json').write_text('{"initial":{"baseline":"public fixture"}}')
            context=Context.__new__(Context);context.parent=parent;context.root=root;context.pin='a'*40
            context.shared_profiles={}
            work=root/'work';work.mkdir()
            role=dict(manifest={'work':str(work)})
            packet=dict(assignment={'brief':'own assignment'},original_stages={'other':'not shared'})
            with patch('exp.master_open_continue.roles.session',return_value=role) as created:
                context.session(root/'direction','direction',packet,10,2)
            shared=created.call_args.args[2]
            self.assertNotIn('original_stages',shared)
            self.assertEqual(shared['evidence'],{'baseline':'public fixture'})

    def test_full_runtime_feedback_preserves_root_error_and_owner_boundary(self):
        from harness.runtime_feedback import export_runtime
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'experiment';directory.mkdir()
            (directory/'request.json').write_text('{"role_thread":"own"}')
            log=directory/'remote/round-01/candidate.launcher.log';log.parent.mkdir(parents=True)
            log.write_text('ValueError: nonsecret actual root error\n')
            with self.assertRaisesRegex(ValueError,'ownership'):
                export_runtime(directory,root/'wrong',authorized_root=root,owner_thread='other')
            value=export_runtime(directory,root/'export',authorized_root=root,owner_thread='own')
            self.assertEqual(len(value['files']),2)
            self.assertEqual((root/'export/remote/round-01/candidate.launcher.log').read_text(),log.read_text())

    def test_open_audit_cannot_turn_active_campaign_into_completion(self):
        from harness.master_open_audit import audit
        from exp.master_open import LIMITS
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'manifest.json').write_text(json.dumps(dict(schema='broad-master-research-v1',limits=LIMITS,
                controller_immutable=True,sealed_authorized=False,launch_sources={})))
            (root/'pipeline-result.json').write_text('{"status":"running"}')
            with patch('harness.master_open_audit.verify_evidence'),self.assertRaisesRegex(ValueError,'not completed normally'):
                audit(root)

    def test_append_authorship_is_reconstructed_not_trusted_from_reported_sha(self):
        from harness.open_research import record_authored_text
        import hashlib
        contents={}
        first=dict(kind='write_file',path='scratch/check.py',content='first')
        digest=hashlib.sha256(b'first').hexdigest()
        self.assertEqual(record_authored_text(first,{'sha256':digest},contents),digest)
        second=dict(kind='append_file',path='scratch/check.py',expected_sha256=digest,content='second')
        with self.assertRaises(ValueError):record_authored_text(second,{'sha256':'0'*64},contents)
        self.assertEqual(contents['scratch/check.py'],'first')
        combined=hashlib.sha256(b'firstsecond').hexdigest()
        self.assertEqual(record_authored_text(second,{'sha256':combined},contents),combined)

    def plan(self):
        from harness.master_decisions import AXES
        card=dict(id='d1',mechanism='Hypothesis requiring source evidence',evidence=['own actual source receipt'],
            potential_net_gain='unknown; cost must be measured',added_cost='selector and submission',
            unknowns=['runtime path'],cheapest_test='source analysis before GPU',priority='diagnose first')
        return dict(assessment=dict(axes={axis:'Historical evidence with explicit limits' for axis in AXES},
            opportunities=[card,dict(card,id='d2')],decision_basis='compare total cost rather than acceptance alone'),
            directions=[dict(id='d1',brief='independent source diagnosis',allocation=dict(actions=120,cpu_runs=24,gpu_attempts=0))])

    def test_master_can_choose_one_cpu_direction_or_stop_without_fabricating_gain(self):
        from exp.master_open import validate_open_plan
        value=self.plan()
        self.assertEqual(len(validate_open_plan(value)),1)
        value['directions']=[]
        self.assertEqual(validate_open_plan(value),[])

    def test_direction_must_come_from_compared_opportunities_and_shared_budget(self):
        from exp.master_open import validate_open_plan
        for field,value in [('id','notCompared'),('allocation',dict(actions=900,cpu_runs=1,gpu_attempts=1))]:
            plan=self.plan();plan['directions'][0][field]=value
            with self.assertRaises(ValueError):validate_open_plan(plan)

    def test_admission_rejects_forged_or_changed_command(self):
        from exp.master_open import OpenCampaign,LIMITS
        from harness.engine_research import Budget
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'job';directory.mkdir()
            (directory/'request.json').write_text('{"mode":"source-research"}')
            source=directory/'source.tar';source.write_bytes(b'fixture')
            (directory/'trusted-admission.json').write_text('{"approved":true,"plan":{"command":["forged"]}}')
            campaign=OpenCampaign.__new__(OpenCampaign)
            campaign.budget=Budget(root/'resource-state.json',limits=LIMITS);campaign.limits=LIMITS
            with self.assertRaisesRegex(ValueError,'admission identity'):
                campaign.admit(directory,source,['trusted','command'],600,2)
            self.assertEqual(campaign.budget.read()['jobs'],[])
