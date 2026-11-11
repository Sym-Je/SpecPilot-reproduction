"""Registered CPU acceptance: python -B -m unittest harness.test_skill_rsi_audit -v.

Output: logs/skills-rsi-20261110-b01/controller-tests/skill-rsi-audit-tests.log.
Native wire, GPU lifecycle and tools are synthetic files; no model/GPU execution.
"""

from datetime import datetime, timezone
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from agents.exploration import object_sha
from harness import skill_rsi_audit as audit


class SkillRsiAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.jobs, self.reported, self.replays, self.role_counts = [], [], {}, {}
        self.patch = dict(schema='source-option-v1', option_id='synthetic-only', edits=[dict(
            path='python/sglang/srt/fixture.py', base_sha256='a' * 64, find='return 8', replace='return 9')])
        self.patch_text, self.check_text = json.dumps(self.patch), 'pass\n'
        self.action = dict(kind='run_source', patch='scratch/option.json', self_check='scratch/check.py',
                           per_suite=1, max_new_tokens=256, reason='non-sensitive fixture')
        self.diagnostic = self.root / 'sp-fixture-research'
        self.final = dict(decision='stop', review=[str(self.diagnostic)])
        self.role('master', 'Master', self.final)
        self.receipt = self.role('direction-d1', 'direction', {'action': self.action}, scientific=True)
        self.role('direction-d2', 'direction', {'action': {'kind': 'finish'}})
        self.role('integration', 'integration', {'action': {'kind': 'finish'}})
        self.role('kernel', 'kernel', {'action': {'kind': 'finish'}})
        self.job('sp-fixture-preflight-failed', 'source-preflight', failed=True)
        preflight = self.job('sp-fixture-preflight-ok', 'source-preflight')
        self.write(self.root / 'preflight-result.json', preflight)
        self.job(self.diagnostic.name, 'source-research')
        self.snapshots()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))

    def role(self, name, kind, value, *, scientific=False, skill=None):
        directory = self.root / name
        work, home = directory / 'work', directory / 'home'
        for path, content in ((directory / 'canary', 'safe'), (work / 'inputs/rules.txt', 'rules'),
                              (home / 'config.toml', 'fixture=true')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.write(work / 'inputs/evidence.json', {'fixture': True})
        manifest = dict(role=kind, canary=str(directory / 'canary'), work=str(work), home=str(home),
            canary_sha256=audit.sha(directory / 'canary'), rules_sha256=audit.sha(work / 'inputs/rules.txt'),
            config_sha256=audit.sha(home / 'config.toml'), evidence_sha256=audit.sha(work / 'inputs/evidence.json'),
            research_packet_sha256=object_sha({'fixture': True}))
        self.write(directory / 'manifest.json', manifest)
        thread, turn = 'thread-' + name, 'turn-' + name
        completed = dict(id=turn, status='completed')
        wire = []
        def row(direction, message):
            wire.append(dict(direction=direction, message=message))
        row('client', dict(id=1, method='thread/start', params={}))
        row('server', dict(id=1, result={'thread': {'id': thread}}))
        row('client', dict(id=2, method='turn/start', params=dict(threadId=thread, input=[dict(type='text', text='fixture')])) )
        row('server', dict(id=2, result={'turn': {'id': turn}}))
        self.write(directory / 'turn-01-request.json', dict(prompt='fixture', prompt_sha256=hashlib.sha256(b'fixture').hexdigest()))
        actions = []
        if scientific:
            actions = [dict(kind='write_file', path='scratch/option.json', content=self.patch_text),
                       dict(kind='write_file', path='scratch/check.py', content=self.check_text),
                       dict(kind='run_python', path='scratch/check.py')]
        if skill:
            actions.append(dict(kind='run_skill', skill=skill['skill'], evidence='stock'))
        receipt = None
        for number, action in enumerate(actions, 1):
            record = directory / 'tools-01' / f'action-{number:03d}'
            request = dict(threadId=thread, turnId=turn, tool='research', namespace=None,
                           callId=str(number), arguments={'action': action})
            if action['kind'] == 'write_file':
                answer = dict(status='completed', sha256=hashlib.sha256(action['content'].encode()).hexdigest())
            elif action['kind'] == 'run_python':
                execution = record / 'execution'
                execution.mkdir(parents=True, exist_ok=True)
                (execution / 'stdout').write_text('synthetic success')
                (execution / 'stderr').write_text('')
                result = dict(code_sha256=hashlib.sha256(self.check_text.encode()).hexdigest(), exit_code=0,
                    landlock_applied=True, seccomp_applied=True, gpu_submissions=0,
                    output_sha256={stream:audit.sha(execution / stream) for stream in ('stdout', 'stderr')})
                self.write(execution / 'result.json', result)
                answer = dict(result, workspace_file_sha256={
                    'scratch/option.json':hashlib.sha256(self.patch_text.encode()).hexdigest(),
                    'scratch/check.py':hashlib.sha256(self.check_text.encode()).hexdigest()})
            else:
                answer = skill
                self.write(record / 'execution/result.json', answer)
            response = dict(success=True, contentItems=[dict(type='inputText', text=json.dumps(answer))])
            self.write(record / 'request.json', request)
            self.write(record / 'response.json', response)
            row('server', dict(id=100 + number, method='item/tool/call', params=request))
            row('client', dict(id=100 + number, result=response))
            if action['kind'] == 'run_python':
                receipt = dict(path=str(record / 'response.json'), sha256=audit.sha(record / 'response.json'),
                               files=answer['workspace_file_sha256'])
        row('server', dict(method='thread/tokenUsage/updated', params={}))
        row('server', dict(method='item/completed', params=dict(turnId=turn,
            item=dict(type='agentMessage', text=json.dumps(value)))))
        row('server', dict(method='turn/completed', params={'turn': completed}))
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(item) + '\n' for item in wire))
        self.write(directory / 'turn-01-native.json', dict(turn=completed, texts=[json.dumps(value)]))
        self.write(directory / 'turn-01-response.json', value)
        self.role_counts[name] = dict(actions=len(actions), cpu_runs=int(scientific) + int(bool(skill)),
                                      model_turns=1, usage_updates=1)
        return receipt

    def job(self, name, mode, *, failed=False):
        directory = self.root / name
        directory.mkdir()
        request = dict(mode=mode, action=dict(per_suite=1, max_new_tokens=256))
        if mode in ('source-research', 'source-controller'):
            (directory / 'patch.json').write_text(self.patch_text)
            (directory / 'self-check.py').write_text(self.check_text)
            self.write(directory / 'cpu-receipt.json', self.receipt)
            request.update(action=self.action, role_thread='thread-direction-d1', role_turn=1,
                role_response_sha256=audit.sha(self.root / 'direction-d1/turn-01-response.json'),
                patch_sha256=audit.sha(directory / 'patch.json'), self_check_sha256=audit.sha(directory / 'self-check.py'),
                cpu_receipt_sha256=audit.sha(directory / 'cpu-receipt.json'))
        if mode == 'source-controller':
            request.update(action=dict(self.action, per_suite=6, max_new_tokens=2048),
                diagnostic_request=str(self.diagnostic), diagnostic_feedback_sha256=audit.sha(self.diagnostic / 'feedback.json'))
        self.write(directory / 'request.json', request)
        content = b'pass\n'
        with tarfile.open(directory / 'source.tar', 'w') as archive:
            member = tarfile.TarInfo('exp/synthetic.py')
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        self.write(directory / 'source-identity.json', dict(archive_sha256=audit.sha(directory / 'source.tar'),
            files={'exp/synthetic.py':hashlib.sha256(content).hexdigest()}))
        uuid = 'job-fixture-' + str(len(self.jobs))
        reserved = 1010 + len(self.jobs) * 20
        phase = 'Failed' if failed else 'Completed'
        self.jobs.append(dict(name=name, uuid=uuid, gpus=2, seconds=20, reserved_unix=reserved,
                             terminated=True, terminal=phase, create_calls=1, charged_gpu_seconds=20))
        self.write(directory / 'pending.json', dict(total_gpus=2, request_sha256=audit.sha(directory / 'request.json'),
                                                   source_sha256=audit.sha(directory / 'source.tar')))
        self.write(directory / 'submitted.json', dict(uuid=uuid, name=name, code=200))
        self.write(directory / 'lifecycle-final.json', dict(uuid=uuid, phase=phase, conservative_gpu_seconds=20,
            pods={'fixture-pod':dict(started_at=datetime.fromtimestamp(reserved, timezone.utc).isoformat(),
                finished_at=datetime.fromtimestamp(reserved + 10, timezone.utc).isoformat(), exit_code=1 if failed else 0)}))
        self.write(directory / 'pre-submit-query.txt', dict(total=0, data=[]))
        self.write(directory / 'post-submit-query.txt', dict(total=1, data=[dict(user_def_name=name, name=uuid)]))
        independent = dict(controller_accepted=False, preflight=mode == 'source-preflight', n_pairs=10)
        if mode == 'source-controller':
            independent = dict(controller_accepted=True, controller_verdict={'joint_acceptance_passed': True})
        self.replays[str(directory / 'remote')] = independent
        feedback = dict(status='failed', uuid=uuid, controller_accepted=False) if failed else dict(independent, status='completed', uuid=uuid)
        self.write(directory / 'feedback.json', feedback)
        if mode != 'source-preflight':
            self.reported.append(dict(feedback, request_directory=str(directory)))
        return feedback

    def snapshots(self):
        self.state = dict(started=1000, **audit.LIMITS, jobs=self.jobs)
        counts = {key:sum(values[key] for values in self.role_counts.values())
                  for key in ('actions', 'cpu_runs', 'model_turns', 'usage_updates')}
        counts['gpu_attempts'] = 1
        counts['actions'] += 1
        self.result = dict(status='research_complete', resource_state=self.state, counters=counts,
            role_processes_closed=True, role_processes={name:dict(pid=1, exit_code=0) for name in self.role_counts},
            master_final=self.final, controller_accepted=False, promoted=False, sealed_completed=False)
        self.write(self.root / 'resource-state.json', self.state)
        self.write(self.root / 'pipeline-result.json', self.result)
        self.write(self.root / 'counters.json', counts)
        self.write(self.root / 'feedback.json', self.reported)

    def check(self):
        with patch.object(audit, 'replay_feedback', side_effect=lambda path, request:self.replays[str(path)]) as replay, \
                patch.object(audit, 'validate_campaign', return_value={'joint_acceptance_passed': True}) as validate:
            result = audit.audit(self.root)
        return result, replay.call_count, validate.call_count

    def extension(self, *, failed=True):
        name = 'sp-fixture-stock-control'
        self.job(name, 'phase4-controller', failed=failed)
        directory = self.root / name
        bundle = self.root / 'stock-control-bundle'
        self.write(bundle / 'manifest.json', dict(stock_tree_sha='a' * 64, candidate_tree_sha='b' * 64))
        request = dict(protocol='controller-phase4-resource-v1', mode='phase4-controller',
            maintenance_stock_control=True, purpose='controller-negative-control', budget_path=str(self.root / 'resource-state.json'),
            bundle=str(bundle), bundle_manifest=dict(path=str(bundle / 'manifest.json'), sha256=audit.sha(bundle / 'manifest.json')),
            candidate_tree_sha='a' * 64, bundle_candidate_tree_sha='b' * 64)
        self.write(directory / 'request.json', request)
        pending = audit.load(directory / 'pending.json')
        pending['request_sha256'] = audit.sha(directory / 'request.json')
        self.write(directory / 'pending.json', pending)
        identity = audit.load(directory / 'source-identity.json')
        identity['archive'] = dict(path=str(directory / 'source.tar'), sha256=identity.pop('archive_sha256'))
        self.write(directory / 'source-identity.json', identity)
        self.write(directory / 'plan.json', dict(budget_path=request['budget_path'], gpus=2,
            request=dict(path=str(directory / 'request.json'), sha256=audit.sha(directory / 'request.json')),
            source=identity['archive']))
        lifecycle = audit.load(directory / 'lifecycle-final.json')
        lifecycle['phase'] = 'Aborted' if failed else 'Completed'
        for pod in lifecycle['pods'].values():
            pod.update(phase='Failed' if failed else 'Succeeded', restarts=0)
        self.write(directory / 'lifecycle-final.json', lifecycle)
        self.jobs[-1]['terminal'] = lifecycle['phase']
        self.jobs[-1]['submission_code'] = 200
        feedback = dict(status='failed' if failed else 'completed', uuid=self.jobs[-1]['uuid'],
            controller_accepted=False, t3_passed=False, promoted=False, ledger_eligible=False)
        self.write(directory / 'feedback.json', feedback)
        if not failed:
            self.write(directory / 'remote/result.json', {'fixture': 'aggregate only'})
            self.write(directory / 'remote/replay-summary.json', {'fixture': 'controller-only replay aggregate'})
        live = audit.load(self.root / 'resource-state.json')
        live['jobs'].append(dict(self.jobs[-1]))
        self.write(self.root / 'resource-state.json', live)
        return directory

    def refresh_extension_request(self, directory, request):
        self.write(directory / 'request.json', request)
        pending = audit.load(directory / 'pending.json')
        pending['request_sha256'] = audit.sha(directory / 'request.json')
        self.write(directory / 'pending.json', pending)
        plan = audit.load(directory / 'plan.json')
        plan['request']['sha256'] = pending['request_sha256']
        self.write(directory / 'plan.json', plan)

    def test_failed_controller_extension_keeps_science_prefix_and_live_totals_distinct(self):
        before = {name:audit.sha(self.root / name) for name in ('pipeline-result.json', 'counters.json', 'feedback.json')}
        self.extension()
        result, replays, gates = self.check()
        self.assertEqual(result['scientific_prefix']['terminated_gpu_jobs'], 3)
        self.assertEqual(result['scientific_prefix']['conservative_gpu_seconds'], 60)
        self.assertFalse(result['scientific_prefix']['sealed_used'])
        self.assertEqual(result['terminated_gpu_jobs'], 4)
        self.assertEqual(result['conservative_gpu_seconds'], 80)
        self.assertEqual(result['research_attempts'], 1)
        self.assertEqual(result['native_turns'], 5)
        self.assertEqual(replays, 2)
        self.assertEqual(gates, 0)
        extension = result['controller_extensions'][0]
        self.assertEqual(extension['status'], 'failed')
        self.assertEqual(extension['terminal'], 'Aborted')
        self.assertIsNone(extension['sealed_used'])
        self.assertFalse(extension['independently_replayed'])
        self.assertFalse(result['real_engine_rsi_completed'])
        self.assertEqual(before, {name:audit.sha(self.root / name) for name in before})

    def test_historical_gpu_edit_reorder_or_truncation_rejected(self):
        self.extension()
        original = audit.load(self.root / 'resource-state.json')
        variants = []
        edited = copy.deepcopy(original)
        edited['jobs'][0]['charged_gpu_seconds'] += 1
        variants.append(edited)
        reordered = copy.deepcopy(original)
        reordered['jobs'][0], reordered['jobs'][1] = reordered['jobs'][1], reordered['jobs'][0]
        variants.append(reordered)
        variants.append(dict(original, jobs=original['jobs'][:1]))
        for state in variants:
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, 'unchanged ordered prefix'):
                self.write(self.root / 'resource-state.json', state)
                self.check()

    def test_started_and_authorized_limits_cannot_change_with_extension(self):
        self.extension()
        original = audit.load(self.root / 'resource-state.json')
        for key in ('started', 'gpu_seconds', 'wall_seconds', 'concurrent_gpus'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'authorized limits'):
                self.write(self.root / 'resource-state.json', dict(original, **{key:original[key] + 1}))
                self.check()

    def test_duplicate_extension_name_or_uuid_rejected(self):
        self.extension()
        original = audit.load(self.root / 'resource-state.json')
        for key in ('name', 'uuid'):
            state = copy.deepcopy(original)
            state['jobs'][-1][key] = state['jobs'][0][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'duplicated'):
                self.write(self.root / 'resource-state.json', state)
                self.check()

    def test_unknown_or_scientific_extension_rejected(self):
        directory = self.extension()
        original = audit.load(directory / 'request.json')
        for change in (dict(mode='source-research'), dict(mode='unknown'), dict(maintenance_stock_control=False),
                       dict(purpose='scientific-candidate'), dict(protocol='unknown')):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'non-stock-control extension'):
                self.refresh_extension_request(directory, dict(original, **change))
                self.check()

    def test_active_or_uncertain_extension_rejected(self):
        self.extension()
        original = audit.load(self.root / 'resource-state.json')
        for change in (dict(terminated=False), dict(create_calls=0), dict(create_calls=2)):
            state = copy.deepcopy(original)
            state['jobs'][-1].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'active or submission uncertain'):
                self.write(self.root / 'resource-state.json', state)
                self.check()

    def test_extension_submission_lifecycle_and_archive_tamper_rejected(self):
        directory = self.extension()
        mutations = [('submitted.json', 'code', 500), ('submitted.json', 'uuid', 'wrong'),
                     ('lifecycle-final.json', 'uuid', 'wrong'), ('lifecycle-final.json', 'phase', 'Running'),
                     ('lifecycle-final.json', 'conservative_gpu_seconds', 0),
                     ('source-identity.json', 'archive', {'path':str(directory / 'source.tar'), 'sha256':'0' * 64})]
        for name, key, value in mutations:
            path = directory / name
            original = path.read_bytes()
            changed = audit.load(path)
            changed[key] = value
            with self.subTest(name=name, key=key), self.assertRaises(ValueError):
                self.write(path, changed)
                self.check()
            path.write_bytes(original)
        with (directory / 'source.tar').open('ab') as archive:
            archive.write(b'synthetic archive replacement')
        with self.assertRaises(ValueError):
            self.check()

    def test_extension_stock_identity_budget_and_plan_are_bound(self):
        directory = self.extension()
        original = audit.load(directory / 'request.json')
        for change in (dict(candidate_tree_sha='b' * 64), dict(budget_path=str(self.root / 'different-state.json'))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.refresh_extension_request(directory, dict(original, **change))
                self.check()

    def test_extension_completed_feedback_cannot_mask_failed_job(self):
        directory = self.extension()
        feedback = audit.load(directory / 'feedback.json')
        feedback['status'] = 'completed'
        self.write(directory / 'feedback.json', feedback)
        with self.assertRaisesRegex(ValueError, 'relabelled completed'):
            self.check()

    def test_completed_extension_only_replays_aggregate_not_private_body(self):
        directory = self.extension(failed=False)
        feedback = audit.load(directory / 'feedback.json')
        independent = {key:value for key, value in feedback.items() if key not in ('status', 'uuid')}
        (directory / 'private').mkdir()
        (directory / 'private/never-read.txt').write_text('synthetic private body; forbidden to this audit')
        original_load, original_sha = audit.load, audit.sha
        def guarded_load(path):
            self.assertNotIn('private', Path(path).parts)
            return original_load(path)
        def guarded_sha(path):
            self.assertNotIn('private', Path(path).parts)
            return original_sha(path)
        with patch.object(audit, 'replay_phase4_feedback', return_value=independent) as replay, \
                patch.object(audit, 'load', side_effect=guarded_load), patch.object(audit, 'sha', side_effect=guarded_sha):
            result, _, _ = self.check()
        self.assertEqual(replay.call_args.args[0], directory / 'remote')
        self.assertTrue(result['controller_extensions'][0]['independently_replayed'])
        self.assertFalse(result['scientific_prefix']['sealed_used'])

    def test_extension_is_included_in_total_cost_and_concurrency_ceiling(self):
        directory = self.extension()
        state = audit.load(self.root / 'resource-state.json')
        state['jobs'][-1]['charged_gpu_seconds'] = audit.LIMITS['gpu_seconds']
        self.write(self.root / 'resource-state.json', state)
        lifecycle = audit.load(directory / 'lifecycle-final.json')
        lifecycle['conservative_gpu_seconds'] = audit.LIMITS['gpu_seconds']
        self.write(directory / 'lifecycle-final.json', lifecycle)
        with self.assertRaisesRegex(ValueError, 'stage GPU budget exceeded'):
            self.check()

    def test_parallel_roles_probe_exclusion_preflight_and_failed_job_accounting(self):
        for name in ('probe', 'native-tool-probe', 'native-tool-probe02'):
            self.write(self.root / name / 'manifest.json', {'role': 'direction', 'engineering_probe': True})
        result, replayed, _ = self.check()
        self.assertEqual(result['scientific_roles'], 5)
        self.assertEqual(result['native_turns'], 5)
        self.assertEqual(result['preflight_gpu_jobs'], 2)
        self.assertEqual(result['research_attempts'], 1)
        self.assertEqual(result['failed_gpu_jobs'], 1)
        self.assertEqual(result['conservative_gpu_seconds'], 60)
        self.assertEqual(result['completed_diagnostics'], 1)
        self.assertEqual(replayed, 2)
        self.assertFalse(result['controller_accepted'])
        self.assertFalse(result['real_engine_rsi_completed'])

    def test_independent_gate_replayed_in_addition_to_source_feedback(self):
        self.job('sp-fixture-gate', 'source-controller')
        self.snapshots()
        result, replayed, gates = self.check()
        self.assertEqual(result['controller_gate_attempts'], 1)
        self.assertEqual(replayed, 3)
        self.assertEqual(gates, 1)

    def test_active_pipeline_is_not_reported_verified(self):
        self.result['status'] = 'running'
        self.write(self.root / 'pipeline-result.json', self.result)
        with self.assertRaisesRegex(ValueError, 'still running'):
            self.check()

    def test_native_tool_feedback_tamper_is_rejected(self):
        path = self.root / 'direction-d1/tools-01/action-001/response.json'
        value = audit.load(path)
        value['success'] = False
        self.write(path, value)
        with self.assertRaisesRegex(ValueError, 'native wire'):
            self.check()

    def test_role_turn_binding_is_not_replaced_by_an_equal_format_hash(self):
        path = self.diagnostic / 'request.json'
        request = audit.load(path)
        request['role_turn'] = 2
        self.write(path, request)
        with self.assertRaisesRegex(ValueError, 'thread/turn'):
            self.check()

    def test_scientific_patch_replacement_fails(self):
        (self.diagnostic / 'patch.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'scientific patch'):
            self.check()

    def test_parallel_cpu_budget_counters_are_recomputed(self):
        self.result['counters']['cpu_runs'] += 1
        self.write(self.root / 'pipeline-result.json', self.result)
        with self.assertRaisesRegex(ValueError, 'parallel native counter'):
            self.check()

    def test_gpu_exit_cannot_be_relabelled_success(self):
        path = self.diagnostic / 'lifecycle-final.json'
        value = audit.load(path)
        value['pods']['fixture-pod']['exit_code'] = 1
        self.write(path, value)
        with self.assertRaisesRegex(ValueError, 'relabelled completed'):
            self.check()

    def test_unconfirmed_termination_fails_closed(self):
        self.state['jobs'][0]['terminated'] = False
        self.write(self.root / 'resource-state.json', self.state)
        self.write(self.root / 'pipeline-result.json', dict(self.result, resource_state=self.state))
        with self.assertRaisesRegex(ValueError, 'active or submission uncertain'):
            self.check()

    def test_nonzero_role_exit_does_not_pass(self):
        self.result['role_processes']['kernel']['exit_code'] = -9
        self.write(self.root / 'pipeline-result.json', self.result)
        with self.assertRaisesRegex(ValueError, 'role exit'):
            self.check()

    def test_changed_independent_feedback_is_rejected(self):
        self.replays[str(self.diagnostic / 'remote')]['n_pairs'] = 999
        with self.assertRaisesRegex(ValueError, 'feedback replay differs'):
            self.check()

    def test_cross_role_cpu_receipt_cannot_replace_original_receipt(self):
        receipt = dict(self.receipt, path=str(self.root / 'direction-d2/tools-01/action-003/response.json'))
        target = Path(receipt['path'])
        self.write(target, audit.load(self.receipt['path']))
        self.write(self.diagnostic / 'cpu-receipt.json', receipt)
        request = audit.load(self.diagnostic / 'request.json')
        request['cpu_receipt_sha256'] = audit.sha(self.diagnostic / 'cpu-receipt.json')
        self.write(self.diagnostic / 'request.json', request)
        with self.assertRaises(ValueError):
            self.check()

    def test_budget_ceiling_cannot_be_raised_by_audit(self):
        self.state['gpu_seconds'] += 1
        self.write(self.root / 'resource-state.json', self.state)
        self.write(self.root / 'pipeline-result.json', dict(self.result, resource_state=self.state))
        with self.assertRaisesRegex(ValueError, 'authorized limits'):
            self.check()

    def test_engineering_probe_cannot_replace_missing_kernel_scientific_role(self):
        import shutil
        shutil.rmtree(self.root / 'kernel')
        self.result['role_processes'].pop('kernel')
        self.result['counters']['model_turns'] -= 1
        self.result['counters']['usage_updates'] -= 1
        self.write(self.root / 'pipeline-result.json', self.result)
        self.write(self.root / 'counters.json', self.result['counters'])
        self.write(self.root / 'native-tool-probe-kernel/manifest.json', {'role': 'kernel'})
        with self.assertRaisesRegex(ValueError, 'scientific stages skipped'):
            self.check()

    def test_tool_file_order_must_match_native_wire_authorship_order(self):
        path = self.root / 'direction-d1/wire.jsonl'
        wire = [json.loads(line) for line in path.read_text().splitlines()]
        positions = [index for index, row in enumerate(wire) if row['message'].get('method') == 'item/tool/call']
        wire[positions[0]], wire[positions[2]] = wire[positions[2]], wire[positions[0]]
        path.write_text(''.join(json.dumps(row) + '\n' for row in wire))
        with self.assertRaisesRegex(ValueError, 'record order'):
            self.check()

    def test_native_final_decision_cannot_be_replaced_by_a_summary(self):
        self.result['master_final'] = dict(decision='stop', reason='not in native wire')
        self.write(self.root / 'pipeline-result.json', self.result)
        with self.assertRaisesRegex(ValueError, 'native Master provenance'):
            self.check()

    def enable_skill(self):
        self.code_root = self.root / 'trusted-code'
        self.lock = self.code_root / 'harness/skill_tools.json'
        snapshot = self.root / 'upstream'
        snapshot.mkdir()
        (snapshot / 'worker.py').write_text('pass\n')
        revision = 'b' * 40
        self.write(self.lock, dict(revision=revision, files={'worker.py':audit.sha(snapshot / 'worker.py')}))
        self.write(self.root / 'tools.json', dict(root=str(snapshot), revision=revision))
        adapters = {}
        for name in ('harness/skill_diagnostics.py', 'harness/skill_worker.py', 'exp/skill_diagnostics.py'):
            target = self.code_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('pass\n')
            adapters[name] = audit.sha(target)
        cache = self.root / 'skill-cache/fixture/result.json'
        tools = {}
        for name in ('extract', 'profiler', 'compute'):
            outputs = {}
            for stream in ('stdout', 'stderr'):
                path = cache.parent / f'{name}.{stream}.txt'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
                outputs[stream] = audit.sha(path)
            tools[name] = dict(exit_code=0, output_sha256=outputs)
        self.write(cache, dict(engineering_passed=True, upstream_revision=revision, adapter_sources_sha256=adapters,
            tool_lock_sha256=audit.sha(self.lock), tools=tools))
        answer = dict(role='direction', skill='pipeline', evidence='stock', upstream_revision=revision,
            upstream=audit.CATALOG['pipeline']['upstream'], independent_discovery=False,
            status='unavailable', result_sha256=audit.sha(cache))
        self.role('direction-d2', 'direction', {'action': {'kind': 'finish'}}, skill=answer)
        self.snapshots()

    def check_skill(self):
        with patch.object(audit, 'ROOT', self.code_root), patch('harness.skill_diagnostics.LOCK', self.lock):
            return self.check()

    def test_unavailable_skill_charges_cpu_but_is_not_completed_skill(self):
        self.enable_skill()
        result, _, _ = self.check_skill()
        self.assertEqual(result['cpu_budget_charges'], 2)
        self.assertEqual(result['python_executions'], 1)
        self.assertEqual(result['skills_unavailable'], 1)
        self.assertEqual(result['skills_completed'], 0)

    def test_skill_snapshot_version_sha_and_cached_output_are_checked(self):
        self.enable_skill()
        (self.root / 'upstream/worker.py').write_text('changed\n')
        with self.assertRaisesRegex(ValueError, 'SHA differs'):
            self.check_skill()

    def test_skill_cached_output_replacement_fails(self):
        self.enable_skill()
        (self.root / 'skill-cache/fixture/compute.stdout.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'skill output SHA'):
            self.check_skill()

    def test_shape_page_native_call_consumes_cpu_without_counting_as_upstream_skill(self):
        self.role('direction-d2', 'direction', {'action': {'kind': 'finish'}},
            skill=dict(skill='profiler', status='completed', role='direction', evidence='stock'))
        directory = self.root / 'direction-d2'
        path = directory / 'tools-01/action-001/request.json'
        request = audit.load(path)
        request['arguments']['action'] = dict(kind='read_profile_shapes', evidence='stock', offset=0)
        self.write(path, request)
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        for row in wire:
            if row['message'].get('method') == 'item/tool/call':
                row['message']['params'] = request
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
        role, responses, origins = audit.audit_role(self.root, directory)
        self.assertEqual(role['counts']['actions'], 1)
        self.assertEqual(role['counts']['cpu_runs'], 1)
        self.assertEqual(role['counts']['skill_calls'], 0)

    def test_cpu_exhausted_shape_page_is_not_charged_as_executed_cpu(self):
        self.role('direction-d2', 'direction', {'action': {'kind': 'finish'}},
            skill=dict(skill='profiler', status='rejected', reason='CPU run budget exhausted'))
        directory = self.root / 'direction-d2'
        path = directory / 'tools-01/action-001/request.json'
        request = audit.load(path)
        request['arguments']['action'] = dict(kind='read_profile_shapes', evidence='stock', offset=0)
        self.write(path, request)
        returned = audit.load(path.parent / 'response.json')
        returned['success'] = False
        self.write(path.parent / 'response.json', returned)
        wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
        call_id = None
        for row in wire:
            if row['message'].get('method') == 'item/tool/call':
                row['message']['params'] = request
                call_id = row['message']['id']
        for row in wire:
            if row['direction'] == 'client' and row['message'].get('id') == call_id:
                row['message']['result'] = returned
        (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
        role, responses, origins = audit.audit_role(self.root, directory)
        self.assertEqual(role['counts']['actions'], 1)
        self.assertEqual(role['counts']['cpu_runs'], 0)


if __name__ == '__main__':
    unittest.main()
