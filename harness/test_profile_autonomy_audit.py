"""CPU acceptance registered before implementation.

python -B -m unittest harness.test_profile_autonomy_audit -v
Logs: logs/stock-profile-autonomy-20261111-a01/skill-tests/profile-autonomy-audit-*.log
Only synthetic native wire, lifecycle and trusted replay fixtures; no GPU/model requests.
"""

import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch

from controller.phase4_final import REGISTRY, identity
from exp import engine_resource, profile_resource, source_resource
from harness import skill_rsi_audit as legacy
from harness import skill_diagnostics as diagnostics
from harness import test_skill_rsi_audit as fixtures

try:
    from harness import profile_autonomy_audit as auditor
except ImportError:
    auditor = None


class ProfileAutonomyAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SkillRsiAuditTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.write = self.fixture.write
        self.entries = []
        self.profile_replays = {}
        self.preflight = self.root / 'sp-fixture-preflight-ok'
        self.initial = self.root / 'initial-profile.json'
        self.convert_profile(self.preflight)
        self.normalize_jobs()
        self.write(self.initial, self.profile_replays[str(self.preflight / 'remote')]['profile_inputs'][0])
        self.snapshot()

    def reference(self, path):
        return dict(path=str(path), sha256=legacy.sha(path))

    def convert_profile(self, directory, binding=None):
        output = directory / 'remote'
        trace, config = output / 'trace.json', output / 'config.json'
        self.write(trace, dict(traceEvents=[dict(ph='X', cat='kernel', name='fixture', ts=0, dur=1, pid=0),
            dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[8, 16]]})]))
        self.write(config, dict(fixture='not a real model'))
        action = dict(workload_id='gsm8k:0', preset='graph-128', reason='non-sensitive CPU audit fixture')
        capture = dict(schema='stock-profile-capture-v1', action=action, base_spec=self.reference(config),
            bundle=None, source_archive=self.reference(directory / 'source.tar'),
            dev_sources={suite:self.reference(config) for suite in ('gsm8k', 'math500', 'humaneval', 'mbpp', 'mtbench')})
        from exp.p3_pair_run import SUITES
        capture['dev_sources'] = {suite:self.reference(config) for suite in SUITES}
        request = dict(protocol=profile_resource.PROTOCOL, mode='stock-profile', action=action, capture=capture,
            budget_path=str(self.root / 'resource-state.json'), role_binding=binding, deadline=2700, gpus=1)
        self.write(directory / 'request.json', request)
        manifest = dict(protocol='stock-profile-only-inputs-v1', scope='authorized-stock',
            trace=self.reference(trace), config=self.reference(config), workload=None)
        independent = dict(protocol='stock-profile-capture-v1', capture_completed=True, option_enabled=False,
            shape_status='unknown', stage_attribution_validated=False, controller_accepted=False,
            ledger_eligible=False, promoted=False, workload=None, profile_inputs=[manifest])
        self.profile_replays[str(output)] = independent
        self.write(output / 'result.json', independent)
        self.write(directory / 'feedback.json', dict(independent, status='completed',
            uuid=next(row['uuid'] for row in self.fixture.jobs if row['name'] == directory.name)))

    def normalize_jobs(self):
        for row in self.fixture.jobs:
            directory = self.root / row['name']
            request = legacy.load(directory / 'request.json')
            profile = request['mode'] == 'stock-profile'
            deadline = 2700 if profile else {'source-preflight':1200, 'source-research':3600,
                                            'source-controller':7200}[request['mode']]
            row.update(gpus=1 if profile else 2, seconds=deadline + 1200, submission_code=200)
            bootstrap = 'exp/profile_remote.sh' if profile else 'exp/source_remote.sh'
            content = (Path(__file__).resolve().parents[1] / bootstrap).read_bytes()
            with tarfile.open(directory / 'source.tar', 'w') as archive:
                member = tarfile.TarInfo(bootstrap)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            source_ref = self.reference(directory / 'source.tar')
            self.write(directory / 'source-identity.json', dict(archive=source_ref,
                archive_sha256=source_ref['sha256'], files={bootstrap:hashlib.sha256(content).hexdigest()}))
            if profile:
                request['capture']['source_archive'] = source_ref
                self.write(directory / 'request.json', request)
                output = directory / 'remote'
                self.write(output / 'request.json', request['capture'])
                self.write(directory / 'resource-binding.json', dict(request=self.reference(directory / 'request.json'),
                    source=source_ref, capture=request['capture'], result_sha256=legacy.sha(output / 'result.json')))
            factory = profile_resource.command if profile else source_resource.command
            command = factory(directory / 'request.json', directory / 'source.tar', directory / 'remote', directory.name, deadline)
            pending = dict(name=directory.name, total_gpus=row['gpus'], nodes=1, gpu_per_node=row['gpus'],
                deadline_seconds=deadline, image=engine_resource.IMAGE,
                command=command, request_sha256=legacy.sha(directory / 'request.json'), source_sha256=source_ref['sha256'])
            self.write(directory / 'pending.json', pending)
            self.write(directory / 'submit.txt', dict(code=200))
            self.write(directory / 'submit-exit.json', dict(exit_code=0, create_calls=1))
            lifecycle = legacy.load(directory / 'lifecycle-final.json')
            for pod in lifecycle['pods'].values():
                pod.update(phase='Failed' if pod['exit_code'] else 'Succeeded', restarts=0)
            self.write(directory / 'lifecycle-final.json', lifecycle)
            if profile:
                self.write(directory / 'plan.json', dict(request=self.reference(directory / 'request.json'),
                    source=source_ref, total_gpus=1, deadline=2700, budget_path=request['budget_path'], command=command))

    def snapshot(self):
        state = dict(started=1000, **profile_resource.LIMITS, jobs=copy.deepcopy(self.fixture.jobs))
        counts = {key:sum(values[key] for values in self.fixture.role_counts.values())
                  for key in ('actions', 'cpu_runs', 'model_turns', 'usage_updates')}
        research = sum(legacy.load(self.root / row['name'] / 'request.json')['mode'] == 'source-research'
                       for row in self.fixture.jobs)
        gates = sum(legacy.load(self.root / row['name'] / 'request.json')['mode'] == 'source-controller'
                    for row in self.fixture.jobs)
        counts.update(actions=counts['actions'] + research + len(self.entries), gpu_attempts=research, controller_jobs=gates)
        processes, members = {}, []
        broker = identity()
        for number, name in enumerate(self.fixture.role_counts, 1):
            child = dict(broker, pid=1073741824 + number, parent_pid=broker['pid'], start_ticks=number)
            birth = self.root / 'processes' / f'birth-{number}.json'
            self.write(birth, dict(schema='controller-process-birth-v1', role='CPU fixture ' + name,
                identity=child, observed_unix=1045))
            birth.chmod(0o600)
            ended = self.root / 'processes' / f'exit-{number}.json'
            self.write(ended, dict(schema='controller-process-exit-v1', birth=self.reference(birth),
                returncode=0, reaped_unix=1190))
            ended.chmod(0o600)
            members.append(dict(birth=self.reference(birth), exit=self.reference(ended)))
            processes[name] = dict(pid=child['pid'], exit_code=0)
        registry = self.root / 'processes/shutdown-registry.json'
        self.write(registry, dict(schema=REGISTRY, broker=broker, members=members, closed_unix=1200))
        registry.chmod(0o600)
        self.write(self.root / 'process-closure.json', dict(role_processes_closed=True, process_members=members,
            shutdown_registry=self.reference(registry)))
        result = dict(status='research_complete', counters=counts, resource_state=state,
            role_processes_closed=True, role_processes=processes, master_final=self.fixture.final,
            controller_accepted=False, promoted=False, sealed_completed=False, real_engine_rsi_completed=False,
            preflight_directory=str(self.preflight), initial_evidence=self.reference(self.initial),
            profile_requests=self.entries, prior_sealed_reused=False)
        self.write(self.root / 'resource-state.json', state)
        self.write(self.root / 'pipeline-result.json', {key:value for key, value in result.items()
            if key not in ('profile_requests', 'prior_sealed_reused', 'preflight_directory', 'initial_evidence')})
        self.write(self.root / 'profile-campaign-result.json', result)
        self.write(self.root / 'profile-requests.json', self.entries)
        self.write(self.root / 'counters.json', counts)
        self.write(self.root / 'feedback.json', self.fixture.reported)

    def add_profile(self):
        action = dict(kind='request_stock_profile', workload_id='gsm8k:0', preset='graph-128',
            reason='non-sensitive CPU audit fixture')
        self.fixture.role('direction-d2', 'direction', dict(action=action))
        response = self.root / 'direction-d2/turn-01-response.json'
        binding = dict(role='direction-d2', thread='thread-direction-d2', turn=1, response=self.reference(response))
        name = 'sp-fixture-profile-01'
        self.fixture.job(name, 'source-preflight')
        directory = self.root / name
        self.convert_profile(directory, binding)
        request = legacy.load(directory / 'request.json')
        result = dict(status='completed', evidence_ids=['profile-01-00'], cached=False, workload_id='gsm8k:0',
            preset='graph-128', shape_status='unknown', stage_attribution_validated=False, controller_accepted=False,
            provenance='new trusted canonical-stock observation, not a candidate or acceptance')
        self.entries.append(dict(directory=str(directory), role_binding=binding, action=request['action'], result=result))
        self.write(self.root / 'profile-evidence/direction-d2/profile-01-00.json',
            self.profile_replays[str(directory / 'remote')]['profile_inputs'][0])
        self.normalize_jobs()
        self.snapshot()
        return directory

    def check(self):
        self.assertIsNotNone(auditor, 'new read-only auditor is not implemented yet')
        with patch.object(auditor, 'replay_profile_feedback', side_effect=lambda output, record:self.profile_replays[str(output)]) as profiles, \
                patch.object(auditor, 'replay_source_feedback', side_effect=lambda output, record:self.fixture.replays[str(output)]) as source, \
                patch.object(auditor, 'validate_campaign', return_value=dict(joint_acceptance_passed=True)) as gate:
            result = auditor.audit(self.root)
        return result, profiles.call_count, source.call_count, gate.call_count

    def enable_profile_skill(self):
        self.fixture.enable_skill()
        path = self.root / 'skill-cache/fixture/result.json'
        cache = legacy.load(path)
        for tool in ('extract', 'profiler'):
            cache['tools'][tool]['timed_out'] = False
        cache['tools']['compute'] = dict(status='unavailable', reason='unknown shape')
        cache['tools']['pipeline'] = dict(status='unavailable', reason='no layer attribution')
        for stream in ('stdout', 'stderr'):
            (path.parent / f'compute.{stream}.txt').unlink()
        manifest = legacy.load(self.initial)
        events = diagnostics.read_trace(Path(manifest['trace']['path']))
        cache.update(input_identity=manifest, kernel_statistics=diagnostics.kernel_statistics(events),
            observed_shape_facts=diagnostics.observed_shape_facts(events, manifest['trace']['sha256']))
        self.write(path, cache)
        answer = dict(status='completed', role='direction', skill='profiler', evidence='stock',
            upstream=legacy.CATALOG['profiler']['upstream'], upstream_revision=cache['upstream_revision'],
            independent_discovery=False, result_sha256=legacy.sha(path),
            observed_shape_facts=cache['observed_shape_facts'], kernel_statistics=cache['kernel_statistics'],
            text='fixture', stage_attribution_validated=False)
        self.fixture.role('direction-d2', 'direction', dict(action=dict(kind='finish')), skill=answer)
        self.snapshot()

    def check_skill(self):
        with patch.object(legacy, 'ROOT', self.fixture.code_root), patch.object(diagnostics, 'LOCK', self.fixture.lock):
            return self.check()

    def replace_skill_identity(self, identity):
        directory = self.root / 'direction-d2'
        request_path = directory / 'tools-01/action-001/request.json'
        response_path = request_path.parent / 'response.json'
        request, response = legacy.load(request_path), legacy.load(response_path)
        request['arguments']['action']['evidence'] = identity
        answer = json.loads(response['contentItems'][0]['text'])
        answer['evidence'] = identity
        response['contentItems'][0]['text'] = json.dumps(answer)
        self.write(request_path, request)
        self.write(response_path, response)
        self.write(request_path.parent / 'execution/result.json', answer)
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        call_id = None
        for row in wire:
            if row['message'].get('method') == 'item/tool/call':
                row['message']['params'] = request
                call_id = row['message']['id']
        for row in wire:
            if row['direction'] == 'client' and row['message'].get('id') == call_id:
                row['message']['result'] = response
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))

    def enable_shape_page(self, offset=0):
        import shutil
        from harness.skill_broker import SkillAccess
        self.enable_profile_skill()
        directory = self.root / 'direction-d2'
        path = directory / 'tools-01/action-001/request.json'
        request = legacy.load(path)
        action = dict(kind='read_profile_shapes', evidence='stock', offset=offset)
        request['arguments']['action'] = action
        self.write(path, request)
        execution = path.parent / 'execution'
        shutil.rmtree(execution)
        access = SkillAccess('direction', {'stock':self.initial}, self.root / 'tools.json', self.root / 'unused-cache')
        answer = access.dispatch(self.root, action, execution)
        self.rewrite_shape_page_answer(answer)
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        for row in wire:
            if row['message'].get('method') == 'item/tool/call':
                row['message']['params'] = request
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
        self.snapshot()
        return answer

    def rewrite_shape_page_answer(self, answer):
        directory = self.root / 'direction-d2'
        path = directory / 'tools-01/action-001/response.json'
        returned = dict(success=True, contentItems=[dict(type='inputText', text=json.dumps(answer))])
        self.write(path, returned)
        self.write(path.parent / 'execution/result.json', answer)
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        call_id = next(row['message']['id'] for row in wire if row['message'].get('method') == 'item/tool/call')
        for row in wire:
            if row['direction'] == 'client' and row['message'].get('id') == call_id:
                row['message']['result'] = returned
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))

    def add_rejected_format_turn(self):
        directory = self.root / 'direction-d2'
        response = legacy.load(directory / 'turn-01-response.json')
        malformed = json.dumps(response) + '}'
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        for row in wire:
            message = row['message']
            if message.get('method') == 'item/completed':
                message['params']['item']['text'] = malformed
        native = legacy.load(directory / 'turn-01-native.json')
        native['texts'] = [malformed]
        self.write(directory / 'turn-01-native.json', native)
        (directory / 'turn-01-response.json').unlink()
        prompt = '模型JSON/协议格式未通过：one complete JSON response required。仅修复格式，保留自己的科学判断，重交完整JSON对象。'
        thread, turn = 'thread-direction-d2', 'turn-direction-d2-format-retry'
        completed = dict(id=turn, status='completed')
        wire.extend([
            dict(direction='client', message=dict(id=3, method='turn/start', params=dict(threadId=thread,
                input=[dict(type='text', text=prompt)]))),
            dict(direction='server', message=dict(id=3, result=dict(turn=dict(id=turn)))),
            dict(direction='server', message=dict(method='thread/tokenUsage/updated', params={})),
            dict(direction='server', message=dict(method='item/completed', params=dict(turnId=turn,
                item=dict(type='agentMessage', text=json.dumps(response))))),
            dict(direction='server', message=dict(method='turn/completed', params=dict(turn=completed)))])
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
        self.write(directory / 'turn-02-request.json', dict(prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
        self.write(directory / 'turn-02-native.json', dict(turn=completed, texts=[json.dumps(response)]))
        self.write(directory / 'turn-02-response.json', response)
        self.fixture.role_counts['direction-d2'].update(model_turns=2, usage_updates=2)
        self.snapshot()
        return directory

    def test_malformed_native_turn_requires_exact_native_format_retry(self):
        self.add_rejected_format_turn()
        result, profiles, source, gates = self.check()
        self.assertEqual(result['native_turns'], 6)
        self.assertEqual(result['format_rejections'], 1)

    def test_missing_valid_structured_response_is_not_a_format_rejection(self):
        (self.root / 'direction-d2/turn-01-response.json').unlink()
        with self.assertRaises(ValueError):
            self.check()

    def test_format_rejection_cannot_have_a_fabricated_structured_response(self):
        directory = self.add_rejected_format_turn()
        self.write(directory / 'turn-01-response.json', dict(action=dict(kind='finish')))
        with self.assertRaisesRegex(ValueError, 'format retry'):
            self.check()

    def test_format_retry_cannot_replace_failure_feedback_with_a_new_task(self):
        directory = self.add_rejected_format_turn()
        prompt = 'continue with another research task'
        self.write(directory / 'turn-02-request.json', dict(prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        for row in wire:
            if row['message'].get('method') == 'turn/start' and row['message'].get('id') == 3:
                row['message']['params']['input'] = [dict(type='text', text=prompt)]
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
        with self.assertRaisesRegex(ValueError, 'format retry'):
            self.check()

    def test_legacy_audit_does_not_implicitly_allow_format_retries(self):
        directory = self.add_rejected_format_turn()
        with self.assertRaisesRegex(ValueError, 'format retry'):
            legacy.audit_role(self.root, directory)

    def test_malformed_final_turn_cannot_be_silently_skipped(self):
        directory = self.add_rejected_format_turn()
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire[:-5]))
        for suffix in ('request', 'native', 'response'):
            (directory / f'turn-02-{suffix}.json').unlink()
        with self.assertRaisesRegex(ValueError, 'format retry'):
            self.check()

    def test_closed_stage_reuses_native_audit_and_counts_failed_preflight(self):
        before = {path:legacy.sha(path) for path in self.root.rglob('*') if path.is_file()}
        result, profiles, source, gates = self.check()
        self.assertTrue(result['engineering_evidence_verified'])
        self.assertEqual(result['scientific_roles'], 5)
        self.assertEqual(result['research_attempts'], 1)
        self.assertEqual(result['profile_gpu_jobs'], 0)
        self.assertEqual(result['terminated_gpu_jobs'], 3)
        self.assertEqual(result['failed_gpu_jobs'], 1)
        self.assertEqual(result['conservative_gpu_seconds'], 60)
        self.assertEqual((profiles, source, gates), (1, 1, 0))
        self.assertFalse(result['sealed_used'])
        self.assertFalse(result['real_engine_rsi_completed'])
        self.assertEqual(before, {path:legacy.sha(path) for path in self.root.rglob('*') if path.is_file()})

    def test_profile_request_binds_native_action_and_registers_same_role_evidence(self):
        self.add_profile()
        result, profiles, source, gates = self.check()
        self.assertEqual(result['profile_gpu_jobs'], 1)
        self.assertEqual(result['registered_profile_evidence'], 1)
        self.assertEqual(result['research_attempts'], 1)
        self.assertEqual(result['conservative_gpu_seconds'], 80)
        self.assertEqual(profiles, 2)

    def test_binding_thread_turn_response_and_action_replacements_rejected(self):
        self.add_profile()
        original = copy.deepcopy(self.entries)
        for key, value in [('thread', 'other-thread'), ('turn', 2), ('response', dict(path='/no-read', sha256='0' * 64))]:
            self.entries = copy.deepcopy(original)
            self.entries[0]['role_binding'][key] = value
            self.snapshot()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
        self.entries = copy.deepcopy(original)
        self.entries[0]['action']['workload_id'] = 'gsm8k:1'
        self.snapshot()
        with self.assertRaises(ValueError):
            self.check()

    def test_registered_manifest_cannot_be_replaced_or_moved_to_another_role(self):
        self.add_profile()
        path = self.root / 'profile-evidence/direction-d2/profile-01-00.json'
        original = path.read_bytes()
        self.write(path, dict(legacy.load(path), workload={'verify_rows':8}))
        with self.assertRaises(ValueError):
            self.check()
        path.write_bytes(original)
        path.rename(self.root / 'profile-evidence/profile-01-00.json')
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.check()

    def test_binding_sidecar_and_actual_capture_request_are_checked(self):
        directory = self.add_profile()
        for path in (directory / 'resource-binding.json', directory / 'remote/request.json'):
            original = path.read_bytes()
            self.write(path, dict(replaced=True))
            with self.subTest(path=path.name), self.assertRaises((ValueError, KeyError)):
                self.check()
            path.write_bytes(original)

    def test_active_or_uncertain_submission_is_never_a_closed_audit(self):
        original = copy.deepcopy(self.fixture.jobs)
        for change in (dict(terminated=False), dict(create_calls=0), dict(submission_code=500)):
            self.fixture.jobs = copy.deepcopy(original)
            self.fixture.jobs[-1].update(change)
            self.snapshot()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check()

    def test_request_archive_and_lifecycle_replacement_rejected(self):
        for path in (self.preflight / 'request.json', self.preflight / 'source.tar', self.preflight / 'lifecycle-final.json'):
            original = path.read_bytes()
            path.write_bytes(b'{}')
            with self.subTest(path=path.name), self.assertRaises((ValueError, KeyError, tarfile.TarError)):
                self.check()
            path.write_bytes(original)

    def test_gpu_charge_must_cover_runtime(self):
        self.fixture.jobs[-1]['charged_gpu_seconds'] = 1
        directory = self.root / self.fixture.jobs[-1]['name']
        lifecycle = legacy.load(directory / 'lifecycle-final.json')
        lifecycle['conservative_gpu_seconds'] = 1
        self.write(directory / 'lifecycle-final.json', lifecycle)
        self.snapshot()
        with self.assertRaises(ValueError):
            self.check()

    def test_new_limits_cannot_be_raised_or_old_budget_reused(self):
        for field, value in [('gpu_seconds', 115200), ('wall_seconds', 86400), ('concurrent_gpus', 4)]:
            self.snapshot()
            state = legacy.load(self.root / 'resource-state.json')
            state[field] = value
            self.write(self.root / 'resource-state.json', state)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check()

    def test_old_or_missing_preflight_provenance_is_not_guessed(self):
        for value in ('/old-stage/preflight', None):
            self.snapshot()
            result = legacy.load(self.root / 'profile-campaign-result.json')
            if value is None:
                del result['preflight_directory']
            else:
                result['preflight_directory'] = value
            self.write(self.root / 'profile-campaign-result.json', result)
            with self.subTest(value=value), self.assertRaises((ValueError, KeyError)):
                self.check()

    def test_initial_evidence_must_be_from_selected_new_preflight(self):
        manifest = legacy.load(self.initial)
        manifest['trace'] = manifest['config']
        self.write(self.initial, manifest)
        self.snapshot()
        with self.assertRaises(ValueError):
            self.check()

    def test_native_wire_and_cpu_receipt_are_independently_verified(self):
        path = self.root / 'direction-d1/tools-01/action-003/execution/stdout'
        path.write_text('changed CPU output')
        with self.assertRaises(ValueError):
            self.check()

    def test_role_exit_and_birth_sha_must_close_the_actual_native_roles(self):
        path = self.root / 'processes/exit-1.json'
        path.write_text('{}')
        with self.assertRaises(ValueError):
            self.check()

    def test_profile_and_research_counters_cannot_be_interchanged(self):
        self.add_profile()
        result = legacy.load(self.root / 'profile-campaign-result.json')
        result['counters']['gpu_attempts'] += 1
        self.write(self.root / 'profile-campaign-result.json', result)
        with self.assertRaises(ValueError):
            self.check()

    def test_failed_job_cannot_be_labelled_completed(self):
        directory = self.root / self.fixture.jobs[0]['name']
        feedback = legacy.load(directory / 'feedback.json')
        feedback['status'] = 'completed'
        self.write(directory / 'feedback.json', feedback)
        with self.assertRaises(ValueError):
            self.check()

    def test_unknown_mode_duplicate_job_and_orphan_submission_rejected(self):
        directory = self.root / self.fixture.jobs[-1]['name']
        original = (directory / 'request.json').read_bytes()
        record = legacy.load(directory / 'request.json')
        record['mode'] = 'phase4-controller'
        self.write(directory / 'request.json', record)
        with self.assertRaises(ValueError):
            self.check()
        (directory / 'request.json').write_bytes(original)
        self.fixture.jobs.append(copy.deepcopy(self.fixture.jobs[-1]))
        self.snapshot()
        with self.assertRaises(ValueError):
            self.check()
        self.fixture.jobs.pop()
        self.snapshot()
        self.write(self.root / 'unknown-submission/pending.json', {})
        with self.assertRaises(ValueError):
            self.check()

    def test_no_prior_sealed_claim_and_engineering_probe_not_science(self):
        self.write(self.root / 'native-tool-probe02/manifest.json', dict(role='direction'))
        result, profiles, source, gates = self.check()
        self.assertEqual(result['scientific_roles'], 5)
        value = legacy.load(self.root / 'profile-campaign-result.json')
        value['prior_sealed_reused'] = True
        self.write(self.root / 'profile-campaign-result.json', value)
        with self.assertRaises(ValueError):
            self.check()

    def test_completed_controller_calls_source_replay_and_independent_gate_validation(self):
        self.fixture.job('sp-fixture-gate', 'source-controller')
        self.normalize_jobs()
        self.snapshot()
        result, profiles, source, gates = self.check()
        self.assertEqual(result['controller_gate_attempts'], 1)
        self.assertEqual((profiles, source, gates), (1, 2, 1))
        self.assertFalse(result['controller_accepted'])

    def test_actual_profile_skill_receipt_is_audited_without_compute_or_gpu_execution(self):
        self.enable_profile_skill()
        result, profiles, source, gates = self.check_skill()
        self.assertEqual(result['skill_calls'], 1)
        self.assertEqual(result['skills_completed'], 1)
        self.assertEqual(result['cpu_budget_charges'], 2)
        self.assertFalse(result['sealed_used'])

    def test_self_consistent_cache_and_answer_kernel_statistics_tamper_rejected(self):
        self.enable_profile_skill()
        cache_path = self.root / 'skill-cache/fixture/result.json'
        cached = legacy.load(cache_path)
        process = next(iter(cached['kernel_statistics']))
        cached['kernel_statistics'][process]['work_us'] = 999999999
        self.write(cache_path, cached)
        response_path = self.root / 'direction-d2/tools-01/action-001/response.json'
        answer = json.loads(legacy.load(response_path)['contentItems'][0]['text'])
        answer.update(kernel_statistics=cached['kernel_statistics'], result_sha256=legacy.sha(cache_path))
        self.rewrite_shape_page_answer(answer)
        with self.assertRaisesRegex(ValueError, 'kernel statistics'):
            self.check_skill()

    def test_full_execution_argv_is_bound_not_only_sha_environment(self):
        for reservation in self.fixture.jobs:
            directory = self.root / reservation['name']
            pending_path = directory / 'pending.json'
            original = legacy.load(pending_path)
            for mutation in ('bootstrap', 'request', 'workspace'):
                with self.subTest(mode=legacy.load(directory / 'request.json')['mode'], mutation=mutation):
                    pending = copy.deepcopy(original)
                    if mutation == 'workspace':
                        pending['command'][pending['command'].index('--workspace') + 1] = '/tmp'
                    else:
                        import shlex
                        argv = shlex.split(pending['command'][-1])
                        if mutation == 'bootstrap':
                            argv[argv.index('bash') + 1] = '/bin/true'
                        else:
                            argv[-4] = str(directory / 'other-request.json')
                        pending['command'][-1] = shlex.join(argv)
                    self.write(pending_path, pending)
                    with self.assertRaisesRegex(ValueError, 'execution command'):
                        auditor.terminal_job(self.root, reservation, legacy.load(self.root / 'resource-state.json'))
                    self.write(pending_path, original)

    def test_new_profile_evidence_is_usable_only_on_a_later_native_turn_of_its_owner(self):
        import shutil
        self.enable_profile_skill()
        directory = self.root / 'direction-d2'
        answer = legacy.load(directory / 'tools-01/action-001/execution/result.json')
        shutil.rmtree(directory / 'tools-01')
        self.add_profile()
        manifest = legacy.load(self.root / 'profile-evidence/direction-d2/profile-01-00.json')
        cache_path = self.root / 'skill-cache/fixture/result.json'
        cache = legacy.load(cache_path)
        cache['input_identity'] = manifest
        self.write(cache_path, cache)
        answer.update(evidence='profile-01-00', result_sha256=legacy.sha(cache_path))
        thread, turn = 'thread-direction-d2', 'turn-direction-d2-profile-skill'
        prompt = 'synthetic same-role profile feedback'
        request = dict(threadId=thread, turnId=turn, callId='new-profile', namespace=None,
            tool='research', arguments=dict(action=dict(kind='run_skill', skill='profiler', evidence='profile-01-00')))
        returned = dict(success=True, contentItems=[dict(type='inputText', text=json.dumps(answer))])
        completed, value = dict(id=turn, status='completed'), dict(action=dict(kind='finish'))
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        wire.extend([
            dict(direction='client', message=dict(id=3, method='turn/start', params=dict(threadId=thread,
                input=[dict(type='text', text=prompt)]))),
            dict(direction='server', message=dict(id=3, result=dict(turn=dict(id=turn)))),
            dict(direction='server', message=dict(id=1003, method='item/tool/call', params=request)),
            dict(direction='client', message=dict(id=1003, result=returned)),
            dict(direction='server', message=dict(method='thread/tokenUsage/updated', params={})),
            dict(direction='server', message=dict(method='item/completed', params=dict(turnId=turn,
                item=dict(type='agentMessage', text=json.dumps(value))))),
            dict(direction='server', message=dict(method='turn/completed', params=dict(turn=completed)))])
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
        self.write(directory / 'turn-02-request.json', dict(prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
        self.write(directory / 'turn-02-native.json', dict(turn=completed, texts=[json.dumps(value)]))
        self.write(directory / 'turn-02-response.json', value)
        self.write(directory / 'tools-02/action-001/request.json', request)
        self.write(directory / 'tools-02/action-001/response.json', returned)
        self.write(directory / 'tools-02/action-001/execution/result.json', answer)
        self.fixture.role_counts['direction-d2'] = dict(actions=1, cpu_runs=1, model_turns=2, usage_updates=2)
        self.snapshot()
        result, profiles, source, gates = self.check_skill()
        self.assertEqual(result['registered_profile_evidence'], 1)
        self.assertEqual(result['skills_completed'], 1)
        self.assertEqual(profiles, 2)

    def test_skill_cannot_use_an_unregistered_or_other_role_evidence_id(self):
        self.enable_profile_skill()
        self.write(self.root / 'profile-evidence/direction-d1/profile-99-00.json', legacy.load(self.initial))
        self.replace_skill_identity('profile-99-00')
        with self.assertRaises(ValueError):
            self.check_skill()

    def test_skill_cache_and_observed_shapes_cannot_substitute_initial_evidence(self):
        self.enable_profile_skill()
        path = self.root / 'skill-cache/fixture/result.json'
        cache = legacy.load(path)
        cache['input_identity']['workload'] = dict(verify_rows=8)
        self.write(path, cache)
        with self.assertRaises(ValueError):
            self.check_skill()

    def test_total_gpu_cost_and_peak_concurrency_are_enforced(self):
        self.fixture.jobs[-1]['charged_gpu_seconds'] = 28800
        directory = self.root / self.fixture.jobs[-1]['name']
        lifecycle = legacy.load(directory / 'lifecycle-final.json')
        lifecycle['conservative_gpu_seconds'] = 28800
        self.write(directory / 'lifecycle-final.json', lifecycle)
        self.snapshot()
        with self.assertRaisesRegex(ValueError, 'GPU budget'):
            self.check()
        self.fixture.jobs[-1]['charged_gpu_seconds'] = 20
        lifecycle['conservative_gpu_seconds'] = 20
        self.write(directory / 'lifecycle-final.json', lifecycle)
        self.fixture.jobs[-1]['reserved_unix'] = 1035
        self.snapshot()
        with self.assertRaisesRegex(ValueError, 'GPU budget'):
            self.check()

    def test_replay_disagreement_does_not_pass_as_a_failed_or_skipped_check(self):
        self.profile_replays[str(self.preflight / 'remote')]['capture_completed'] = False
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_process_registry_does_not_fall_back_to_pid_only_claims(self):
        (self.root / 'process-closure.json').unlink()
        with self.assertRaises(ValueError):
            self.check()

    def test_profile_binding_bool_turn_is_not_an_integer_native_identity(self):
        self.add_profile()
        self.entries[0]['role_binding']['turn'] = True
        self.snapshot()
        with self.assertRaises(ValueError):
            self.check()

    def test_shape_page_is_recomputed_from_registered_trace_and_charged_once(self):
        self.enable_shape_page()
        result, profiles, source, gates = self.check_skill()
        self.assertEqual(result['cpu_budget_charges'], 2)
        self.assertEqual(result['skill_calls'], 0)
        self.assertFalse(result['sealed_used'])

    def test_shape_page_summary_tamper_rejected_even_with_consistent_wire_and_receipt(self):
        original = self.enable_shape_page()
        for field, value in [('input_dims', [[999]]), ('trace_sha256', '0' * 64), ('total_signatures', 900),
                             ('next_offset', 16), ('offset', 16), ('cost_model_input_certified', True)]:
            changed = copy.deepcopy(original)
            if field == 'input_dims':
                changed['observed_shape_facts']['signatures'][0][field] = value
            else:
                changed['observed_shape_facts'][field] = value
            self.rewrite_shape_page_answer(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check_skill()

    def test_shape_page_requires_real_execution_receipt_and_same_role_id(self):
        self.enable_shape_page()
        path = self.root / 'direction-d2/tools-01/action-001/execution/result.json'
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError):
            self.check_skill()
        path.write_bytes(original)
        self.replace_skill_identity('other-role-profile')
        with self.assertRaises(ValueError):
            self.check_skill()

    def test_nonzero_shape_page_replay_does_not_recompute_default_page(self):
        manifest = legacy.load(self.initial)
        trace = Path(manifest['trace']['path'])
        self.write(trace, dict(traceEvents=[dict(ph='X', cat='kernel', name='fixture', ts=0, dur=1, pid=0)] +
            [dict(ph='X', cat='cpu_op', name='aten::empty' if index < 16 else 'aten::mm',
                  args={'Input Dims': [[index, 16]]}) for index in range(20)]))
        manifest['trace'] = self.reference(trace)
        self.write(self.initial, manifest)
        independent = self.profile_replays[str(self.preflight / 'remote')]
        independent['profile_inputs'][0] = manifest
        self.write(self.preflight / 'remote/result.json', independent)
        uuid = next(row['uuid'] for row in self.fixture.jobs if row['name'] == self.preflight.name)
        self.write(self.preflight / 'feedback.json', dict(independent, status='completed', uuid=uuid))
        self.normalize_jobs()
        answer = self.enable_shape_page(offset=16)
        self.assertEqual(answer['observed_shape_facts']['signatures'][0]['operator'], 'aten::mm')
        self.assertEqual(answer['observed_shape_facts']['offset'], 16)
        result, profiles, source, gates = self.check_skill()
        self.assertEqual(result['cpu_budget_charges'], 2)


if __name__ == '__main__':
    unittest.main()
