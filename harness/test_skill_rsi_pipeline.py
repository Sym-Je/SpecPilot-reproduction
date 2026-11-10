"""Maintainer safety regressions; known unpatched runner gaps must fail.

Acceptance registered before implementation:
/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python -B -m unittest
harness.test_skill_rsi_pipeline -v
Output: logs/skills-rsi-20261110-b01/controller-tests/pipeline-review.log
No model, GPU, submission, real research patch, or protected evaluation data.
"""

import copy
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from controller.dev_campaign import correctness_reference
from exp import skill_rsi
from harness.engine_research import save
from harness.source_candidate import build_bundle, candidate_arm, file_sha
from harness import test_source_candidate as source_fixtures


class PipelineReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        with patch.object(skill_rsi.subprocess, 'check_output', return_value='a' * 40 + '\n'):
            self.campaign = skill_rsi.Campaign(self.root, self.root / 'inputs', self.root / 'tools')
        self.role = dict(directory=self.root / 'role', actions=20, runs=3, number=1,
            manifest=dict(work=str(self.root / 'work'), role='direction'),
            thread={'thread': {'id': 'synthetic-role'}}, counters=dict(self.campaign.counters))
        self.role['directory'].mkdir()
        scratch = self.root / 'work/scratch'
        scratch.mkdir(parents=True)
        save(scratch / 'option.json', {'fixture': 'non-scientific placeholder'})
        (scratch / 'check.py').write_text('pass\n')
        save(self.role['directory'] / 'turn-01-response.json', {'fixture': True})
        self.action = dict(kind='run_source', patch='scratch/option.json', self_check='scratch/check.py',
                           per_suite=1, max_new_tokens=256, reason='synthetic pipeline control-flow review')
        self.allocation = dict(actions=20, cpu_runs=3, gpu_attempts=1)

    def explore(self, responses, experiment):
        prompts = []
        def ask(role, prompt):
            prompts.append(prompt)
            return next(responses)
        with patch.object(self.campaign, 'open_role', return_value=self.role), \
                patch.object(self.campaign, 'ask', side_effect=ask), \
                patch.object(self.campaign, 'experiment', side_effect=experiment) as execute:
            result = self.campaign.explore('direction-fixture', 'direction', {}, self.allocation, 'start')
        return result, prompts, execute.call_count

    def test_failed_remote_feedback_reaches_same_role_for_self_repair(self):
        responses = iter([dict(action=self.action), dict(action={'kind': 'finish'}, candidate=False)])
        result, prompts, calls = self.explore(responses,
            lambda *args: dict(status='failed', controller_accepted=False, log_tail='synthetic NameError: missing_symbol'))
        self.assertEqual(calls, 1)
        self.assertIn('missing_symbol', prompts[1])
        self.assertIn('自己复核/修复', prompts[1])
        self.assertFalse(result['response']['candidate'])

    def test_validation_failure_is_feedback_not_immediate_campaign_abort(self):
        responses = iter([dict(action=self.action), dict(action={'kind': 'finish'})])
        _, prompts, calls = self.explore(responses, lambda *args: (_ for _ in ()).throw(ValueError('CPU SHA stale')))
        self.assertEqual(calls, 1)
        self.assertIn('CPU SHA stale', prompts[1])
        self.assertIn('rejected', prompts[1])

    def test_uncertain_submission_runtime_error_is_not_retried(self):
        responses = iter([dict(action=self.action), dict(action=self.action)])
        with self.assertRaisesRegex(RuntimeError, 'reservation held'):
            self.explore(responses, lambda *args: (_ for _ in ()).throw(RuntimeError('reservation held')))

    def test_model_response_parse_error_gets_bounded_format_self_repair(self):
        with patch.object(self.campaign, 'open_role', return_value=self.role), \
                patch.object(self.campaign, 'ask', side_effect=[skill_rsi.ModelResponseError('invalid response JSON'),
                    dict(action={'kind': 'finish'})]) as ask:
            result = self.campaign.explore('direction-fixture', 'direction', {}, self.allocation, 'start')
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(result['response']['action']['kind'], 'finish')

    def test_actual_model_parser_error_is_classified_without_retrying_native_value_errors(self):
        self.campaign.budget.read = lambda: dict(started=10**12, wall_seconds=86400)
        def malformed(*args):
            return skill_rsi.roles.response_object('not JSON')
        with patch.object(skill_rsi.roles, 'turn', side_effect=malformed):
            with self.assertRaises(skill_rsi.ModelResponseError):
                self.campaign.ask(self.role, 'fixture')
        with patch.object(skill_rsi.roles, 'turn', side_effect=ValueError('one complete JSON response required')) as turn:
            with self.assertRaises(ValueError) as failure:
                self.campaign.model_response(self.role, 'fixture')
        self.assertNotIsInstance(failure.exception, skill_rsi.ModelResponseError)
        self.assertEqual(turn.call_count, 1)

    def test_model_format_repair_stops_after_three_attempts(self):
        with patch.object(self.campaign, 'ask', side_effect=skill_rsi.ModelResponseError('format only')) as ask:
            with self.assertRaises(skill_rsi.ModelResponseError):
                self.campaign.model_response(self.role, 'fixture')
        self.assertEqual(ask.call_count, 3)

    def test_native_runtime_failure_is_not_a_format_retry(self):
        with patch.object(self.campaign, 'ask', side_effect=RuntimeError('native turn timed out')) as ask:
            with self.assertRaisesRegex(RuntimeError, 'native turn timed out'):
                self.campaign.model_response(self.role, 'fixture')
        self.assertEqual(ask.call_count, 1)

    def test_unsubmitted_validation_rejections_do_not_consume_local_gpu_allocation(self):
        responses = iter([dict(action=self.action)] * 3 + [dict(action={'kind': 'finish'})])
        archive = self.root / 'fixture.tar'
        archive.write_bytes(b'synthetic archive, never submitted')
        def reserved(directory, source, budget):
            budget.reserve(directory.name, 2, 100)
            budget.update(directory.name, terminal='Failed', terminated=True, charged_gpu_seconds=10)
            return dict(status='failed', controller_accepted=False)
        with patch.object(self.campaign, 'open_role', return_value=self.role), \
                patch.object(self.campaign, 'ask', side_effect=lambda *args:next(responses)), \
                patch.object(skill_rsi, 'cpu_receipt', side_effect=[ValueError('stale CPU receipt'),
                    ValueError('stale CPU receipt'), {'fixture': True}]) as receipt, \
                patch.object(skill_rsi, 'read_patch', return_value={'option_id': 'fixture-only'}), \
                patch.object(skill_rsi, 'freeze', return_value=archive), \
                patch.object(skill_rsi, 'execute', side_effect=reserved) as execute:
            self.campaign.explore('direction-fixture', 'direction', {}, self.allocation, 'start')
        self.assertEqual(receipt.call_count, 3)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.campaign.counters['gpu_attempts'], 1)

    def test_parallel_other_role_reservations_do_not_consume_this_role_allocation(self):
        directory = self.root / 'synthetic-other-role'
        directory.mkdir()
        save(directory / 'request.json', dict(mode='source-research', role_thread='another-role'))
        self.campaign.budget.reserve(directory.name, 2, 100)
        self.assertEqual(self.campaign.reserved_jobs('source-research', self.role), [])

    def test_post_execution_validation_errors_consume_local_gpu_allocation(self):
        responses = iter([dict(action=self.action)] * 3 + [dict(action={'kind': 'finish'})])
        prompts = []
        def ask(role, prompt):
            prompts.append(prompt)
            return next(responses)
        def executed_then_rejected(directory, archive, budget):
            budget.reserve(directory.name, 2, 100)
            budget.update(directory.name, terminal='Completed', terminated=True, charged_gpu_seconds=10)
            raise ValueError('synthetic post-GPU independent audit mismatch')
        archive = self.root / 'fixture.tar'
        archive.write_bytes(b'synthetic archive, never submitted')
        with patch.object(self.campaign, 'open_role', return_value=self.role), \
                patch.object(self.campaign, 'ask', side_effect=ask), \
                patch.object(skill_rsi, 'cpu_receipt', return_value={'fixture': True}), \
                patch.object(skill_rsi, 'read_patch', return_value={'option_id': 'fixture-only'}), \
                patch.object(skill_rsi, 'freeze', return_value=archive), \
                patch.object(skill_rsi, 'execute', side_effect=executed_then_rejected) as execute:
            self.campaign.explore('direction-fixture', 'direction', {}, self.allocation, 'start')
        self.assertEqual(self.allocation['gpu_attempts'], 1)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.campaign.counters['gpu_attempts'], 1)
        self.assertEqual(len(self.campaign.budget.read()['jobs']), 1)
        self.assertIn('audit mismatch', prompts[1])

    def test_gate_has_separate_controller_job_accounting(self):
        directory = self.root / 'sp-skillrsi-fixture-candidate'
        directory.mkdir()
        for name in ('patch.json', 'cpu-receipt.json', 'feedback.json'):
            save(directory / name, {'fixture': True})
        (directory / 'self-check.py').write_text('pass\n')
        save(directory / 'request.json', dict(action=self.action, patch_sha256=file_sha(directory / 'patch.json')))
        self.campaign.completed.append(directory)
        archive = self.root / 'fixture.tar'
        archive.write_bytes(b'synthetic archive, never submitted')
        def fake_execute(gate, source, budget):
            budget.reserve(gate.name, 2, 100)
            budget.update(gate.name, terminal='Completed', terminated=True, charged_gpu_seconds=10)
            return dict(status='completed', controller_accepted=False)
        with patch.object(skill_rsi, 'freeze', return_value=archive), \
                patch.object(skill_rsi, 'execute', side_effect=fake_execute):
            self.campaign.gate(directory)
        self.assertEqual(len(self.campaign.budget.read()['jobs']), 1)
        self.assertEqual(self.campaign.counters['gpu_attempts'], 0)
        self.assertEqual(self.campaign.counters.get('controller_jobs', 0), 1)

    def run_handoff(self, *, integration_accepted):
        paths = {label: self.root / ('sp-skillrsi-fixture-' + label + '-01')
                 for label in ('direction-d1', 'direction-d2', 'integration')}
        packets = {}
        process = SimpleNamespace(pid=0, returncode=None)
        process.poll = lambda: process.returncode
        def close():
            process.returncode = 0
        client = SimpleNamespace(process=process, close=close)
        def open_role(label, kind, packet, actions=120, runs=24):
            role = dict(directory=self.root / label, client=client)
            self.campaign.opened.append(role)
            return role
        def explore(label, kind, packet, allocation, prompt, comparison_base=None):
            packets[label] = copy.deepcopy(packet)
            if label in paths:
                directory = paths[label]
                directory.mkdir()
                save(directory / 'patch.json', {'fixture_identity': label})
                save(directory / 'feedback.json', {'fixture': label})
                self.campaign.completed.append(directory)
            return dict(label=label, response={'action': {'kind': 'finish'}})
        def gate(directory):
            accepted = directory == paths['direction-d1'] or (integration_accepted and directory == paths['integration'])
            return dict(diagnostic_request=str(directory), controller_accepted=accepted,
                        controller_verdict={'correctness': {'correctness_passed': True}})
        directions = [dict(id=name, brief='synthetic independent hypothesis',
                           allocation=dict(actions=5, cpu_runs=1, gpu_attempts=1)) for name in ('d1', 'd2')]
        responses = iter([dict(directions=directions),
            dict(review=[str(paths['direction-d1']), str(paths['direction-d2'])]),
            dict(baseline=str(paths['direction-d1'])), dict(review=[str(paths['integration'])])] +
            ([dict(baseline=str(paths['integration']))] if integration_accepted else []) +
            [dict(review=[]), dict(decision='stop')])
        save(self.root / 'preflight-result.json', dict(status='completed', preflight=True))
        with patch.object(self.campaign, 'packet', return_value={'fixture': True}), \
                patch.object(self.campaign, 'open_role', side_effect=open_role), \
                patch.object(self.campaign, 'explore', side_effect=explore), \
                patch.object(self.campaign, 'gate', side_effect=gate), \
                patch.object(self.campaign, 'ask', side_effect=lambda *args: next(responses)), \
                patch.multiple(skill_rsi.roles, COMMON=skill_rsi.roles.COMMON,
                               ACTION_LIMIT=skill_rsi.roles.ACTION_LIMIT, RUN_LIMITS=skill_rsi.roles.RUN_LIMITS):
            result = self.campaign.run()
        self.assertEqual(result['status'], 'research_complete')
        self.assertFalse(result['sealed_completed'])
        self.assertFalse(result['promoted'])
        return paths, packets

    def test_kernel_packet_includes_accepted_fallback_stack_patch_and_provenance(self):
        paths, packets = self.run_handoff(integration_accepted=False)
        kernel = packets['kernel']
        self.assertEqual(kernel['comparison_stack'], str(paths['direction-d1']))
        shared = [candidate['id'] for candidate in kernel['shared_candidates']]
        self.assertIn(paths['direction-d1'].name, shared)
        selected = next(candidate for candidate in kernel['shared_candidates'] if candidate['id'] == paths['direction-d1'].name)
        self.assertTrue(selected['provenance'])
        self.assertEqual(selected['patch_sha256'], file_sha(paths['direction-d1'] / 'patch.json'))
        self.assertEqual(kernel['selected_stack']['diagnostic_source'], str(paths['direction-d1']))
        self.assertTrue(kernel['selected_stack']['controller_gate']['controller_accepted'])

    def test_accepted_integration_is_shared_and_used_as_kernel_comparison(self):
        paths, packets = self.run_handoff(integration_accepted=True)
        kernel = packets['kernel']
        self.assertEqual(kernel['comparison_stack'], str(paths['integration']))
        self.assertIn(paths['integration'].name, [candidate['id'] for candidate in kernel['shared_candidates']])

    def test_canonical_correctness_identity_does_not_follow_comparison_stack(self):
        comparison = dict(tree_sha='b' * 64, block=8, engine='/synthetic/current-stack', env={})
        campaign = dict(reference_tree_sha='a' * 64, candidate_arms=[comparison],
                        null_arms=[dict(comparison), dict(comparison)])
        self.assertEqual(correctness_reference(campaign), ('a' * 64, True))

    def test_default_off_tree_selector_runs_original_stock_not_candidate(self):
        fixture = source_fixtures.SourceCandidateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.root / 'bundle'
        build_bundle(fixture.base, fixture.patch_path, bundle)
        disabled = candidate_arm(bundle)
        enabled = candidate_arm(bundle, enabled=True)
        self.assertEqual(runpy.run_path(str(Path(disabled['engine']) / fixture.path))['value'](), 8)
        self.assertEqual(runpy.run_path(str(Path(enabled['engine']) / fixture.path))['value'](), 9)

    def test_started_campaign_fails_closed_without_automatic_recovery_or_resubmit(self):
        save(self.root / 'pipeline-result.json', {'status': 'needs_attention', 'error': 'synthetic timeout'})
        self.campaign.budget.reserve('synthetic-held-job', 2, 100)
        before = self.campaign.budget.read()
        with patch.object(skill_rsi.subprocess, 'check_output', return_value='a' * 40 + '\n'):
            reopened = skill_rsi.Campaign(self.root, self.root / 'inputs', self.root / 'tools')
        with patch.object(skill_rsi.roles, 'session') as session, self.assertRaisesRegex(ValueError, 'checkpoint recovery'):
            reopened.run()
        session.assert_not_called()
        self.assertEqual(reopened.budget.read(), before)


if __name__ == '__main__':
    unittest.main()
