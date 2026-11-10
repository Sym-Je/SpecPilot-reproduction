"""CPU-only acceptance preregistered in docs/experiments/coverage-review-20261110.md."""

import copy
import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from controller.phase4_final import trusted_metadata, validate_shutdown
from agents.exploration import object_sha
from exp import skill_rsi_continue as continuation
from harness.engine_research import save
from harness import test_skill_rsi_audit as fixtures
from harness.research_protocol import ResearchBroker


class CoverageReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SkillRsiAuditTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.output = self.root / 'coverage-review-01'
        clock = patch.object(continuation.time, 'time', return_value=1100)
        clock.start()
        self.addCleanup(clock.stop)
        self.replay = patch('harness.skill_rsi_audit.replay_feedback',
            side_effect=lambda path, request:self.fixture.replays[str(path)])
        self.replay.start()
        self.addCleanup(self.replay.stop)
        self.originals = continuation.roles.COMMON, continuation.roles.ACTION_LIMIT, continuation.roles.RUN_LIMITS
        self.identities = {name:continuation.sha(self.root / name) for name in
                           ('pipeline-result.json', 'feedback.json', 'resource-state.json', 'counters.json')}

    def session(self, directory, kind, packet, actions, runs):
        directory.mkdir(mode=0o700)
        save(directory / 'packet.json', packet)
        bootstrap = continuation.codex_boundary.subprocess.Popen(
            [sys.executable, '-c', 'import sys; sys.stdin.read()'], stdin=subprocess.PIPE)
        bootstrap.communicate()
        process = continuation.research_boundary.subprocess.Popen(
            [sys.executable, '-c', 'import sys; sys.stdin.read()'], stdin=subprocess.PIPE,
            start_new_session=True)
        def close():
            if not process.stdin.closed:
                process.stdin.close()
            process.wait(timeout=5)
        return dict(directory=directory, number=0, thread={'thread': {'id': 'fixture-master'}},
                    client=SimpleNamespace(process=process, close=close))

    def turn(self, decision):
        def answer(role, prompt, counters):
            role['number'] += 1
            counters['model_turns'] += 1
            save(role['directory'] / f'turn-{role["number"]:02d}-response.json', decision)
            return decision
        return answer

    def run_review(self, decision):
        with patch.object(continuation.roles, 'session', side_effect=self.session) as session, \
                patch.object(continuation.roles, 'turn', side_effect=self.turn(decision)) as turn, \
                patch.object(continuation.Budget, 'reserve', side_effect=AssertionError('GPU forbidden')):
            result = continuation.review(self.root, self.output)
        self.assertEqual(session.call_count, 1)
        self.assertEqual(turn.call_count, 1)
        self.assertEqual(self.originals, (continuation.roles.COMMON, continuation.roles.ACTION_LIMIT,
                                        continuation.roles.RUN_LIMITS))
        for name, identity in self.identities.items():
            self.assertEqual(continuation.sha(self.root / name), identity)
        registry = trusted_metadata(result['shutdown_registry'], os.geteuid())
        self.assertEqual(validate_shutdown(registry, broker_uid=os.geteuid(), opened_unix=continuation.time.time()), 2)
        self.assertFalse(result['sealed_used'])
        self.assertFalse(result['controller_accepted'])
        self.assertEqual(result['gpu_jobs_submitted'], 0)
        return result

    def test_stop_schema_and_native_closure_preserve_parent_budget(self):
        result = self.run_review(dict(decision='stop', review=[], reason='No credible gain; retain stop.'))
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['controller_handoff'], [])
        self.assertEqual(result['counters_after']['model_turns'], result['counters_before']['model_turns'] + 1)

    def test_review_unknown_correctness_item_is_only_handoff(self):
        result = self.run_review(dict(decision='review', review=[self.fixture.diagnostic.name],
                                      reason='Independent correctness coverage may clarify complementarity.'))
        self.assertEqual(result['status'], 'controller_review_requested')
        self.assertEqual(result['controller_handoff'][0]['id'], self.fixture.diagnostic.name)
        self.assertFalse(result['integration_executed'])
        self.assertFalse(result['kernel_executed'])

    def test_invalid_decisions_are_rejected(self):
        for value in (None, {}, dict(decision='stop', review=['measured'], reason='x'),
                      dict(decision='review', review=[], reason='x'),
                      dict(decision='review', review=['unknown'], reason='x'),
                      dict(decision='review', review=['measured', 'measured'], reason='x'),
                      dict(decision='review', review=['measured'], reason=''),
                      dict(decision='review', review=['measured'], reason='x', accepted=True)):
            with self.subTest(value=value), self.assertRaises(continuation.ModelResponseError):
                continuation.validate_decision(value, {'measured': {}})

    def test_prepare_replays_only_shared_diagnostics_and_master_context(self):
        private = self.root / 'direction-d1/private-reasoning.txt'
        private.write_text('DO NOT SHARE PRIVATE REASONING')
        packet, candidates, counts = continuation.prepare(self.root, self.output)
        self.assertEqual(set(candidates), {self.fixture.diagnostic.name})
        self.assertNotIn(private.read_text(), str(packet))
        self.assertTrue(packet['parent_audit']['engineering_evidence_verified'])
        self.assertEqual(packet['shared_budget_path'], str(self.root / 'resource-state.json'))
        self.assertEqual(counts, self.fixture.result['counters'])
        self.assertEqual(len(packet['previous_master_decisions']), 1)

    def test_prepare_refuses_existing_or_external_output(self):
        self.output.mkdir()
        for output in (self.output, self.root.parent / 'coverage-review-foreign'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                continuation.prepare(self.root, output)

    def test_second_review_is_rejected_without_new_native_process(self):
        self.run_review(dict(decision='stop', review=[], reason='retain stop'))
        with patch.object(continuation.roles, 'session') as session, self.assertRaisesRegex(ValueError, 'already claimed'):
            continuation.review(self.root, self.root / 'coverage-review-02')
        session.assert_not_called()

    def test_zero_remaining_turns_rejected_before_native_birth(self):
        packet, candidates, counts = continuation.prepare(self.root, self.output)
        counts = dict(counts, model_turns=96)
        with patch.object(continuation, 'prepare', return_value=(packet, candidates, counts)), \
                patch.object(continuation.roles, 'session') as session, self.assertRaises(ValueError):
            continuation.review(self.root, self.output)
        session.assert_not_called()

    def test_session_initialization_failure_still_records_birth_and_exit(self):
        def failed_session(*arguments):
            self.session(*arguments)
            raise RuntimeError('synthetic native initialization failed')
        with patch.object(continuation.roles, 'session', side_effect=failed_session), \
                self.assertRaisesRegex(RuntimeError, 'initialization failed'):
            continuation.review(self.root, self.output)
        result = continuation.load(self.output / 'coverage-result.json')
        self.assertEqual(result['status'], 'needs_attention')
        self.assertTrue(result['role_processes_closed'])
        self.assertEqual(len(result['process_members']), 2)
        registry = trusted_metadata(result['shutdown_registry'], os.geteuid())
        self.assertEqual(validate_shutdown(registry, broker_uid=os.geteuid(), opened_unix=continuation.time.time()), 2)

    def test_native_uncertainty_is_not_retried(self):
        with patch.object(continuation.roles, 'session', side_effect=self.session), \
                patch.object(continuation.roles, 'turn', side_effect=ValueError('native protocol uncertain')) as turn, \
                self.assertRaisesRegex(ValueError, 'native protocol uncertain'):
            continuation.review(self.root, self.output)
        self.assertEqual(turn.call_count, 1)
        self.assertEqual(continuation.load(self.output / 'coverage-result.json')['status'], 'needs_attention')

    def test_model_schema_repair_is_bounded(self):
        with patch.object(continuation.roles, 'session', side_effect=self.session), \
                patch.object(continuation.roles, 'turn', side_effect=self.turn({'decision': 'invalid'})) as turn, \
                self.assertRaises(continuation.ModelResponseError):
            continuation.review(self.root, self.output)
        self.assertEqual(turn.call_count, 3)


class CoverageRepairTests(unittest.TestCase):
    setUp = CoverageReviewTests.setUp
    session = CoverageReviewTests.session

    def native_turn(self, decision, *, legacy=False, missing_page=False, no_help=False):
        def answer(role, prompt, counters):
            directory = role['directory']
            saved_root = self.fixture.root
            self.fixture.root = directory.parent
            try:
                self.fixture.role('master', 'Master', decision)
            finally:
                self.fixture.root = saved_root
            manifest = continuation.load(directory / 'manifest.json')
            packet = continuation.load(directory / 'packet.json')
            packet['fixture_padding'] = '非敏感长输入' * 3000
            evidence = directory / 'work/inputs/evidence.json'
            save(evidence, packet)
            manifest.update(evidence_sha256=continuation.sha(evidence), research_packet_sha256=object_sha(packet))
            work = directory / 'work'
            if getattr(self, 'external_work', False):
                external = self.root / ('native-work-' + directory.parent.name)
                shutil.move(str(work), str(external))
                work = external
                manifest['work'] = str(work)
            save(directory / 'manifest.json', manifest)
            broker = ResearchBroker(work, directory / 'tools-01', 'thread-master', 'turn-master', max_actions=32)
            wire = [json.loads(line) for line in (directory / 'wire.jsonl').read_text().splitlines()]
            calls = []
            def tool(action):
                request = dict(threadId='thread-master', turnId='turn-master', tool='research', namespace=None,
                               callId=str(broker.actions + 1), arguments={'action': action})
                identity = 100 + broker.actions
                response = broker.handle(request)
                calls.extend([dict(direction='server', message=dict(id=identity, method='item/tool/call', params=request)),
                              dict(direction='client', message=dict(id=identity, result=response))])
                return json.loads(response['contentItems'][0]['text'])
            if not legacy and not no_help:
                tool({'kind': 'help'})
            offset = 0
            while offset is not None:
                page = tool(dict(kind='read_file', path='inputs/evidence.json', offset=offset))
                offset = page['next_offset']
                if legacy or missing_page:
                    break
            if legacy:
                tool(dict(kind='read_file', path='inputs/evidence.json', offset=12000, limit=24000))
                tool(dict(kind='run_python', code='print("not executed")'))
            wire[4:4] = calls
            (directory / 'wire.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in wire))
            counters['model_turns'] += 1
            counters['usage_updates'] += 1
            counters['actions'] += broker.actions
            counters['cpu_runs'] += broker.runs
            role.update(number=1, thread={'thread': {'id': 'thread-master'}})
            return decision
        return answer

    def prior(self):
        decision = dict(decision='stop', review=[], reason='Input truncated; this is not full scientific coverage.')
        with patch.object(continuation.roles, 'session', side_effect=self.session), \
                patch.object(continuation.roles, 'turn', side_effect=self.native_turn(decision, legacy=True)):
            result = continuation.review(self.root, self.output)
        self.prior_hashes = {str(path):continuation.sha(path) for path in self.output.rglob('*') if path.is_file()}
        self.prior_hashes[str(self.root / 'coverage-review-claim.json')] = continuation.sha(self.root / 'coverage-review-claim.json')
        return result

    def repair(self, decision=None, **options):
        decision = decision or dict(decision='stop', review=[], reason='After complete context, retain stop autonomously.')
        output = self.root / 'coverage-review-repair-01'
        with patch.object(continuation.roles, 'session', side_effect=self.session), \
                patch.object(continuation.roles, 'turn', side_effect=self.native_turn(decision, **options)), \
                patch.object(continuation.Budget, 'reserve', side_effect=AssertionError('GPU forbidden')):
            result = continuation.review(self.root, output, repair_from=self.output)
        for path, digest in self.prior_hashes.items():
            self.assertEqual(continuation.sha(path), digest)
        for name, digest in self.identities.items():
            self.assertEqual(continuation.sha(self.root / name), digest)
        registry = trusted_metadata(result['shutdown_registry'], os.geteuid())
        self.assertEqual(validate_shutdown(registry, broker_uid=os.geteuid(), opened_unix=1100), 2)
        return result

    def test_repair_carries_cumulative_counters_provenance_and_complete_pages(self):
        prior = self.prior()
        result = self.repair()
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['counters_before'], prior['counters_after'])
        self.assertEqual(result['counters_after']['model_turns'], prior['counters_after']['model_turns'] + 1)
        self.assertEqual(result['counters_after']['cpu_runs'], prior['counters_after']['cpu_runs'])
        self.assertEqual(result['counters_after']['gpu_attempts'], prior['counters_after']['gpu_attempts'])
        reading = result['input_reading']
        self.assertTrue(reading['complete'])
        self.assertEqual(reading['covered_chars'], reading['total_chars'])
        self.assertGreater(len(reading['pages']), 2)
        self.assertTrue(all(page['sha256'] == reading['sha256'] and page['verified'] for page in reading['pages']))
        provenance = continuation.load(self.root / 'coverage-review-repair-01/repair-provenance.json')
        self.assertTrue(any(not receipt['returned']['success'] for receipt in provenance['prior_tool_receipts']))
        self.assertEqual(set(provenance['engineering_fix_sources']),
                         {'agents/autonomy.py', 'harness/research_tools.py', 'exp/skill_rsi_continue.py'})

    def test_master_may_autonomously_request_review_without_any_gate_execution(self):
        self.prior()
        result = self.repair(dict(decision='review', review=[self.fixture.diagnostic.name], reason='Cover unknown correctness.'))
        self.assertEqual(result['status'], 'controller_review_requested')
        self.assertEqual(len(result['controller_handoff']), 1)
        self.assertEqual(result['gpu_jobs_submitted'], 0)
        self.assertFalse(result['controller_accepted'])

    def test_broker_workspace_outside_role_log_directory_is_supported(self):
        self.external_work = True
        self.prior()
        result = self.repair()
        self.assertEqual(result['status'], 'stopped')
        self.assertTrue(result['input_reading']['complete'])

    def test_missing_pages_are_incomplete_context_not_scientific_stop(self):
        self.prior()
        result = self.repair(missing_page=True)
        self.assertEqual(result['status'], 'incomplete_context')
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['controller_handoff'], [])

    def test_missing_help_is_incomplete_even_with_all_pages(self):
        self.prior()
        result = self.repair(no_help=True)
        self.assertEqual(result['status'], 'incomplete_context')

    def test_second_repair_rejected_without_native_start(self):
        self.prior()
        self.repair(missing_page=True)
        with patch.object(continuation.roles, 'session') as session, self.assertRaisesRegex(ValueError, 'already claimed'):
            continuation.review(self.root, self.root / 'coverage-review-repair-02', repair_from=self.output)
        session.assert_not_called()

    def test_prior_parent_sha_changes_rejected(self):
        self.prior()
        path = self.root / 'feedback.json'
        save(path, ['synthetic historical replacement'])
        with self.assertRaisesRegex(ValueError, 'parent evidence SHA'):
            continuation.repair_context(self.root, self.output)

    def test_prior_exit_and_native_counter_tamper_rejected(self):
        self.prior()
        path = self.output / 'coverage-result.json'
        original = continuation.load(path)
        for key, value in (('role_processes_closed', False), ('role_exit_code', 1),
                           ('counters_after', dict(original['counters_after'], cpu_runs=0)),
                           ('native_response_sha256', '0' * 64)):
            with self.subTest(key=key):
                changed = copy.deepcopy(original)
                changed[key] = value
                save(path, changed)
                with self.assertRaises(ValueError):
                    continuation.repair_context(self.root, self.output)
        save(path, original)

    def test_prior_tool_and_input_replacements_rejected(self):
        self.prior()
        for path in (self.output / 'master/tools-01/action-001/response.json',
                     self.output / 'master/work/inputs/evidence.json'):
            original = path.read_bytes()
            with self.subTest(path=path):
                save(path, {'synthetic': 'replacement'})
                with self.assertRaises(ValueError):
                    continuation.repair_context(self.root, self.output)
            path.write_bytes(original)

    def test_foreign_or_nested_repair_source_rejected(self):
        self.prior()
        for prior in (self.root.parent, self.output / 'master', self.root / 'coverage-review-unclaimed'):
            with self.subTest(prior=prior), self.assertRaises((ValueError, OSError)):
                continuation.repair_context(self.root, prior)

    def test_forged_page_sha_or_gap_cannot_claim_full_context(self):
        self.prior()
        self.repair()
        directory = self.root / 'coverage-review-repair-01/master'
        path = directory / 'tools-01/action-003/response.json'
        response = continuation.load(path)
        answer = json.loads(response['contentItems'][0]['text'])
        answer['sha256'] = '0' * 64
        response['contentItems'][0]['text'] = json.dumps(answer)
        save(path, response)
        reading = continuation.input_reading(directory)
        self.assertFalse(reading['complete'])
        self.assertTrue(any(not page['verified'] for page in reading['pages']))


if __name__ == '__main__':
    unittest.main()
