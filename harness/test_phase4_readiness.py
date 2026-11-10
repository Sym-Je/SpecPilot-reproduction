import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from controller.http_transport import sha_ids
from exp import phase4_run
from exp.p3_pair_run import SUITES
from harness import test_p5_scored_forcing as scored_tests


class Phase4ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.private = [dict(id='private-short', suite='private-fixture', turn=0,
                             input_ids=[91], input_sha256=sha_ids([91]))]
        self.public = []
        artifacts = {}
        for suite_index, suite in enumerate(SUITES):
            path = self.root / 'assets/upstream/dev' / (suite + '.jsonl')
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = []
            for index in range(5):
                token = suite_index * 5 + index + 1
                rows.append(dict(id=f'{suite}-{index}', turns=[str(token)]))
                if index < 4:
                    self.public.append(dict(id=f'{suite}-{index}', suite=suite, turn=0,
                        input_ids=[2, token], input_sha256=sha_ids([2, token])))
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            artifacts[path.relative_to(self.root).as_posix()] = phase4_run.reference(path)
        self.frozen = dict(artifacts=artifacts, launch_protocol={'model_path': '/fixture-target'},
            arms=[dict(name='stock', tree_sha='a' * 64)], gpus=[{'index': 0}, {'index': 1}])

    def tokenizer(self):
        return SimpleNamespace(apply_chat_template=lambda messages, **options: [2, int(messages[0]['content'])])

    def test_fixed_public_twenty_are_independent_of_private_requests(self):
        factory = SimpleNamespace(from_pretrained=lambda target, **options: self.tokenizer())
        with patch.object(phase4_run, 'ROOT', self.root), patch.dict(
                sys.modules, transformers=SimpleNamespace(AutoTokenizer=factory)):
            requests = phase4_run.load_readiness_requests(self.frozen)
        self.assertEqual(requests, self.public)
        self.assertEqual(len(requests), 20)
        self.assertNotIn(self.private[0]['id'], [row['id'] for row in requests])

    def test_public_dev_sources_are_in_execution_archive_closure(self):
        names = phase4_run.execution_sources()
        for suite in SUITES:
            self.assertIn(f'assets/upstream/dev/{suite}.jsonl', names)

    def test_public_dev_source_drift_or_missing_freeze_is_rejected(self):
        factory = SimpleNamespace(from_pretrained=lambda target, **options: self.tokenizer())
        for change in ('missing', 'changed'):
            frozen = copy.deepcopy(self.frozen)
            name = f'assets/upstream/dev/{SUITES[0]}.jsonl'
            if change == 'missing':
                del frozen['artifacts'][name]
            else:
                frozen['artifacts'][name]['sha256'] = '0' * 64
            with self.subTest(change=change), patch.object(phase4_run, 'ROOT', self.root), patch.dict(
                    sys.modules, transformers=SimpleNamespace(AutoTokenizer=factory)):
                with self.assertRaisesRegex(ValueError, 'public dev'):
                    phase4_run.load_readiness_requests(frozen)

    def run_score_fixture(self, *, fail_readiness=False):
        events = []
        fixture = self
        class Campaign:
            def __init__(self, directory, scorer, evidence_root):
                self.directory = directory
            def generate(self, cohort, requests, client, identity, cap):
                events.append(('generate', cohort, copy.deepcopy(requests), cap))
                return [str(self.directory / cohort / row['id']) for row in requests], {}, {}
            def save_trace(self, cohort, request, output, identity, segments):
                events.append(('timed', cohort, copy.deepcopy(request), output, segments))
                return str(self.directory / cohort / request['id'])
            def audit(self, cohort, paths, delta):
                events.append(('audit', cohort, paths))
                return []
        class Client:
            def __init__(self, *arguments):
                pass
            def scorer_identity(self, tree):
                return {'tree_sha': tree}
            def server_identity(self, tree):
                return {'tree_sha': tree}
        def fresh(campaign, directory, arms, gpus, environment, requests):
            events.append(('readiness', copy.deepcopy(requests)))
            self.assertEqual(requests, fixture.public)
            if fail_readiness:
                raise ValueError('no actual AR request reached the registered injection boundary')
            return {name: [str(directory / name / row['id']) for row in requests]
                    for name in ('stock', 'ar', 'stock_long', 'healthy_stock', 'healthy_segmented', 'faulty')}
        records = {}
        for cap in (2048, 4096):
            records[cap, 'candidate'] = [dict(finished_unix=10 + number, pairs=[{
                key: dict(output_ids=[token], generator={'tree_sha': 'a' * 64},
                          raw_evidence={'path': f'/fixture/timed-{cap}-{number}-{key}', 'sha256': 'b' * 64})
                for key, token in (('a', 3), ('b', 4))}]) for number in (1, 2)]
        runtime = phase4_run.LiveRuntime(dict(target='/fixture-target', draft='/fixture-draft',
            stock_engine='/fixture-stock', stock_tree_sha='a' * 64), self.frozen)
        with patch.object(phase4_run, 'load_readiness_requests', return_value=self.public), \
                patch('harness.candidate.check_inputs'), \
                patch.object(phase4_run, 'reference', side_effect=lambda path: {'path': str(path), 'sha256': 'c' * 64}), \
                patch.object(phase4_run, 'launch'), patch.object(phase4_run, 'check_ports'), \
                patch.object(phase4_run, 'wait_for_idle', return_value=[]), patch.object(phase4_run, 'NativeClient', Client), \
                patch.object(phase4_run, 'Campaign', Campaign), \
                patch.object(phase4_run, 'fresh_generations', side_effect=fresh), \
                patch.object(phase4_run, 'head_process', return_value={'traces': ['/fixture/head']}), \
                patch.object(phase4_run, 'checked_head'), \
                patch.object(phase4_run, 'calibrate_delta', return_value={'delta': 0}) as calibrate, \
                patch.object(phase4_run, 'validate_science', return_value={'scientific_ready': True}):
            if fail_readiness:
                with self.assertRaisesRegex(ValueError, 'injection boundary'):
                    runtime.score(self.root, self.private, records)
                return events, None, None, []
            forcing, science = runtime.score(self.root, self.private, records)
            return events, forcing, science, calibrate.call_args_list

    def test_private_early_eos_does_not_select_readiness_or_replace_timed_forcing(self):
        events, forcing, science, calibrations = self.run_score_fixture()
        self.assertEqual([event for event in events if event[0] == 'readiness'], [('readiness', self.public)])
        actual = [event for event in events if event[0] == 'generate']
        self.assertEqual([(event[2], event[3]) for event in actual], [(self.private, 2048), (self.private, 4096)])
        timed = [event for event in events if event[0] == 'timed']
        self.assertEqual(len(timed), 8)
        self.assertTrue(all(event[2] == self.private[0] for event in timed))
        self.assertEqual([event[3] for event in timed], [[3], [4]] * 4)
        self.assertTrue(all('/fixture/timed-' in event[4][0]['path'] for event in timed))
        self.assertEqual([(entry['cap'], entry['round']) for entry in forcing],
                         [(2048, 1), (2048, 2), (4096, 1), (4096, 2)])
        for entry in forcing:
            self.assertTrue(all('private-short' in source['path'] for source in entry['ar']))
        self.assertEqual(len(calibrations), 5)
        for call in calibrations[1:]:
            self.assertTrue(all('private-short' in path for paths in call.args for path in paths))
        evidence = json.loads(Path(science['path']).read_text())
        self.assertEqual(evidence['readiness_protocol'], 'fixed-public-dev-readiness-v1')
        self.assertEqual(json.loads(Path(evidence['reference']['path']).read_text()), {'requests': self.public})

    def test_no_eligible_public_probe_is_still_a_hard_failure(self):
        events, _, _, _ = self.run_score_fixture(fail_readiness=True)
        self.assertFalse(any(event[0] == 'generate' for event in events))
        self.assertFalse((self.root / 'scoring/science.json').exists())

    def science_fixture(self, *, tail_tokens=1024):
        helper = scored_tests.ScoredForcingTests()
        helper.root, helper.counter = self.root, 0
        frozen = copy.deepcopy(self.frozen)
        frozen['launch_protocol']['model_path'] = '/model'
        frozen['artifacts'].update({name: {'sha256': value * 64} for name, value in
            (('controller/head_reference.py', 'a'), ('target_config', 'b'), ('target_index', 'c'))})
        def trace(request, output, mismatches=None, role='stock', segments=None):
            path = helper.trace(output, mismatches=mismatches, role=role,
                request_id=request['id'], prompt=request['input_ids'])
            value = json.loads(path.read_text())
            raw = json.loads(Path(value['raw_evidence']['path']).read_text())
            raw['started_unix'] = 20
            value['raw_evidence'] = helper.save(raw)
            if segments is None:
                generation = json.loads(Path(value['generation_segments'][0]['path']).read_text())
                generation.update(started_unix=20)
                generation['request']['sampling_params'] = dict(max_new_tokens=2048, ignore_eos=False)
                generation['response']['meta_info']['finish_reason'] = {
                    'type': 'length' if len(output) == 2048 else 'stop'}
                value['generation_segments'] = [helper.save(generation)]
            else:
                value['generation_segments'] = segments
            return helper.save(value)
        cohorts = {name: [] for name in
            ('stock', 'ar', 'stock_long', 'healthy_stock', 'healthy_segmented', 'faulty', 'equivalent_head')}
        for index, request in enumerate(self.public):
            length = 2048 if index == 0 else 4
            for name in ('stock', 'healthy_stock'):
                cohorts[name].append(trace(request, [4] * length, {2: (6, .1)}))
            cohorts['ar'].append(trace(request, [4, 4, 6] + [4] * (length - 3), role='ar'))
        request = self.public[0]
        prefix = [4, 4, 6] + [4] * 2045
        first = json.loads(Path(cohorts['ar'][0]['path']).read_text())['generation_segments'][0]
        for name in ('healthy_segmented', 'faulty'):
            tokens = [7 if name == 'faulty' else 4] * tail_tokens
            parameters = dict(max_new_tokens=2048, ignore_eos=False)
            if name == 'faulty':
                parameters['logit_bias'] = {str(token): 2 for token in range(0, 248320, 7)}
            tail = helper.save(dict(http_status=200, started_unix=20,
                request=dict(input_ids=request['input_ids'] + prefix, sampling_params=parameters),
                response=dict(output_ids=tokens, meta_info=dict(completion_tokens=len(tokens)))))
            mismatches = {index: (8, 2) for index in range(2048, 2048 + tail_tokens)} if name == 'faulty' else None
            cohorts[name].append(trace(request, prefix + tokens, mismatches, role='ar', segments=[first, tail]))
        cohorts['stock_long'].append(trace(request, [4] * (2048 + tail_tokens), {2: (6, .1)}))
        head_identity = dict(shape=[248320, 5120], checkpoint='/model', compute_dtype='torch.float32',
            checkpoint_dtype='torch.bfloat16', tf32=False, chunks=8, reversed_accumulation=True,
            tensor_sha256='d' * 64, source_sha256='a' * 64, config_sha256='b' * 64, index_sha256='c' * 64)
        checks = []
        for request in self.public[::4]:
            output, segments, steps = [], [], []
            for index, token in enumerate([4, 4, 6]):
                raw = helper.save(dict(http_status=200, started_unix=20,
                    request=dict(input_ids=request['input_ids'] + output, return_hidden_states='last',
                        return_logprob=True, sampling_params={'max_new_tokens': 1}),
                    response=dict(output_ids=[token], meta_info=dict(completion_tokens=1))))
                steps.append(dict(index=index, raw_evidence=raw, prefix_sha256=sha_ids(request['input_ids'] + output),
                    native_token=token, reverse_token=token, native_logprob_error=0,
                    native_choice_margin=0, max_logit_difference=0))
                segments.append(raw)
                output.append(token)
            source = trace(request, output, role='ar', segments=segments)
            value = json.loads(Path(source['path']).read_text())
            value['head_reduction_control'] = dict(head_identity=head_identity, steps=steps)
            cohorts['equivalent_head'].append(helper.save(value))
            checks.extend(steps)
        science = dict(phase4_sha256='f' * 64, readiness_protocol='fixed-public-dev-readiness-v1',
            reference=helper.save(dict(requests=self.public)), cohorts=cohorts, audits={},
            preflight=helper.save(dict(mode='preflight', tokens=1, head_identity=head_identity, checks=checks[:1])),
            control=helper.save(dict(mode='control', tokens=len(checks), head_identity=head_identity, checks=checks,
                traces=[source['path'] for source in cohorts['equivalent_head']])))
        return helper, frozen, science

    def validate_fixture(self, helper, frozen, science):
        with patch.object(phase4_run, 'load_readiness_requests', return_value=self.public):
            return phase4_run.validate_science(helper.save(science), root=self.root, frozen=frozen,
                phase4_sha256='f' * 64, not_before=10)

    def test_real_controller_recomputes_public_health_fault_head_and_post2048(self):
        helper, frozen, science = self.science_fixture()
        result = self.validate_fixture(helper, frozen, science)
        self.assertTrue(result['scientific_ready'])
        self.assertEqual(result['post2048_tokens'], 1024)
        for name in ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head'):
            self.assertTrue(result['verdicts'][name]['correctness_passed'])
        self.assertTrue(result['verdicts']['faulty']['event_flagged'])
        self.assertFalse(result['verdicts']['faulty']['correctness_passed'])
        self.assertFalse(result['t3_passed'])
        self.assertFalse(result['promoted'])
        self.assertFalse(result['ledger_eligible'])

    def test_public_readiness_cannot_be_replaced_by_private_or_partial_evidence(self):
        helper, frozen, science = self.science_fixture()
        for change in ('reference', 'protocol', 'missing', 'reordered', 'fault', 'prompt', 'raw'):
            altered = copy.deepcopy(science)
            if change == 'reference':
                altered['reference'] = helper.save(dict(requests=self.private))
            if change == 'protocol':
                altered['readiness_protocol'] = 'private-readiness'
            if change == 'missing':
                altered['cohorts']['stock'].pop()
            if change == 'reordered':
                altered['cohorts']['healthy_stock'].reverse()
            if change == 'fault':
                altered['cohorts']['faulty'] = []
            if change in ('prompt', 'raw'):
                value = json.loads(Path(altered['cohorts']['ar'][0]['path']).read_text())
                if change == 'prompt':
                    value['request_id'] = self.private[0]['id']
                else:
                    value['raw_evidence']['sha256'] = '0' * 64
                altered['cohorts']['ar'][0] = helper.save(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate_fixture(helper, frozen, altered)

    def test_post2048_coverage_still_requires_at_least_1024_actual_tokens(self):
        helper, frozen, science = self.science_fixture(tail_tokens=512)
        result = self.validate_fixture(helper, frozen, science)
        self.assertFalse(result['scientific_ready'])
        self.assertEqual(result['post2048_tokens'], 512)
        self.assertTrue(result['verdicts']['faulty']['event_flagged'])
        self.assertFalse(result['verdicts']['faulty']['correctness_passed'])

    def test_healthy_failure_is_recomputed_not_replaced_by_reported_success(self):
        helper, frozen, science = self.science_fixture()
        request = self.public[0]
        path = helper.trace([4] * 2048, {index: (8, 2) for index in range(3, 1027)},
            request_id=request['id'], prompt=request['input_ids'])
        trace = json.loads(path.read_text())
        raw = json.loads(Path(trace['raw_evidence']['path']).read_text())
        raw['started_unix'] = 20
        trace['raw_evidence'] = helper.save(raw)
        science['cohorts']['healthy_stock'][0] = helper.save(trace)
        science.update(scientific_ready=True, runtime_passed=True)
        result = self.validate_fixture(helper, frozen, science)
        self.assertFalse(result['scientific_ready'])
        self.assertFalse(result['verdicts']['healthy_stock']['correctness_passed'])
        self.assertTrue(result['verdicts']['healthy_stock']['event_flagged'])
        self.assertEqual(result['post2048_tokens'], 1024)


if __name__ == '__main__':
    unittest.main()
