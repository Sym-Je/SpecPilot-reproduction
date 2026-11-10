"""Synthetic controller contract checks, not GPU acceptance or promotion."""

import copy
import json
import math
from pathlib import Path
import unittest

from controller import dev_campaign, paper_policy, scored_forcing
from controller.http_transport import sha_ids
from exp.p3_pair_run import summarize
from harness import test_p3_baseline_validation as baseline_fixtures
from harness import test_p5_scored_forcing as scored_fixtures
from harness.baseline_validation import read_rows


class SyntheticEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scored_fixtures.ScoredForcingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def saved_trace(self, trace):
        return Path(self.fixture.save(trace)['path'])

    def judge(self, calibration, path):
        return scored_forcing.judge_scored_forcing(calibration, [path], evidence_root=self.root)

    def measured(self, path):
        trace = json.loads(path.read_text())
        row = dict(id=trace['request_id'], output_ids=copy.deepcopy(trace['output_ids']),
                   raw_evidence=copy.deepcopy(trace['generation_segments'][0]),
                   generator=copy.deepcopy(trace['generator']))
        request = dict(id=trace['request_id'], input_ids=copy.deepcopy(trace['prompt_ids']))
        return trace, row, request


class ForcingCapabilitiesTests(SyntheticEvidenceTests):
    def test_healthy_near_tie_passes_both_rules_without_promotion(self):
        calibration = self.fixture.calibration()
        healthy = self.fixture.trace([4] * 4096, {2: (6, .1)})
        verdict = self.judge(calibration, healthy)
        self.assertEqual(calibration['delta'], .125)
        self.assertTrue(verdict['correctness_passed'])
        self.assertFalse(verdict['rate_flagged'])
        self.assertFalse(verdict['event_flagged'])
        self.assertFalse(verdict['ledger_eligible'])

    def test_post2048_sparse_large_errors_trigger_event_but_not_rate(self):
        calibration = self.fixture.calibration()
        faults = {index: (6, 2) for index in range(2048, 2060)}
        path = self.fixture.trace([7] * 4096, faults)
        trace = json.loads(path.read_text())
        bias = {str(token): 2 for token in range(0, 28, 7)}
        trace['generation_segments'] = []
        for offset in (0, 2048):
            packet = dict(http_status=200,
                request=dict(input_ids=trace['prompt_ids'] + trace['output_ids'][:offset],
                    sampling_params=dict(max_new_tokens=2048, **({'logit_bias': bias} if offset else {}))),
                response=dict(output_ids=trace['output_ids'][offset:offset + 2048],
                    meta_info=dict(completion_tokens=2048, finish_reason={'type': 'length'})))
            trace['generation_segments'].append(self.fixture.save(packet))
        path = self.saved_trace(trace)
        injected = scored_forcing.validate_injected_generation(path, evidence_root=self.root, vocabulary_size=28)
        self.assertEqual(injected['post2048_tokens'], 2048)
        verdict = self.judge(calibration, path)
        self.assertEqual(verdict['large_margin_events'], 12)
        self.assertEqual(verdict['unexplained_events'], 12)
        self.assertEqual(verdict['explained_events'], [])
        self.assertFalse(verdict['rate_flagged'])
        self.assertTrue(verdict['event_flagged'])
        self.assertLess(verdict['event_p'], verdict['event_alpha'])
        self.assertFalse(verdict['correctness_passed'])
        self.assertFalse(verdict['ledger_eligible'])

    def test_rate_rule_independently_rejects_many_small_margin_errors(self):
        calibration = self.fixture.calibration()
        path = self.fixture.trace([4] * 4096, {index: (6, .1) for index in range(2048, 4096)})
        verdict = self.judge(calibration, path)
        self.assertTrue(verdict['rate_flagged'])
        self.assertFalse(verdict['event_flagged'])
        self.assertEqual(verdict['large_margin_events'], 0)
        self.assertFalse(verdict['correctness_passed'])

    def test_real_forcing_verdicts_gate_both_rounds_and_performance_together(self):
        calibration = self.fixture.calibration()
        good = self.judge(calibration, self.fixture.trace([4] * 4096, {2: (6, .1)}))
        second = self.judge(calibration, self.fixture.trace([4] * 4096, {2: (6, .1)}))
        bad = self.judge(calibration, self.fixture.trace([4] * 4096,
            {index: (6, 2) for index in range(2048, 2060)}))
        policy = PolicyCapabilitiesTests()
        accepted = policy.verdict(correctness=dev_campaign.combine_correctness([good, second]))
        rejected = policy.verdict(correctness=dev_campaign.combine_correctness([good, bad]))
        self.assertTrue(accepted['eligible_for_promotion'])
        self.assertTrue(rejected['performance_passed'])
        self.assertFalse(rejected['correctness_passed'])
        self.assertFalse(rejected['eligible_for_promotion'])
        self.assertFalse(accepted['promoted'])
        self.assertFalse(accepted['ledger_eligible'])

    def test_calibrated_delta_and_counts_cannot_be_rewritten_even_with_new_digest(self):
        calibration = self.fixture.calibration(32)
        healthy = self.fixture.trace([4] * 32)
        for field in ('delta', 'stock_counts'):
            altered = copy.deepcopy(calibration)
            if field == 'delta':
                altered['delta'] = 99
            else:
                altered['stock_counts']['mismatches'] = 32
            altered['evidence_sha256'] = scored_forcing.digest_record(altered)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.judge(altered, healthy)

    def test_calibration_source_hash_replacement_is_rejected(self):
        calibration = self.fixture.calibration(32)
        calibration['stock_sources'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.judge(calibration, self.fixture.trace([4] * 32))

    def test_candidate_cohort_cannot_be_missing_duplicated_or_reprompted(self):
        calibration = self.fixture.calibration(32)
        healthy = self.fixture.trace([4] * 32)
        invalid = ([], [healthy, healthy], [self.fixture.trace([4] * 32, request_id='other')],
                   [self.fixture.trace([4] * 32, prompt=[2, 8])])
        for paths in invalid:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                scored_forcing.judge_scored_forcing(calibration, paths, evidence_root=self.root)

    def test_actual_measured_generation_matches_forcing(self):
        path = self.fixture.trace([4] * 32)
        _, row, request = self.measured(path)
        self.assertIsNone(dev_campaign.check_scored_measurements(
            [path], [row], [request], evidence_root=self.root))

    def test_measured_tokens_generator_packet_and_prompt_cannot_be_substituted(self):
        path = self.fixture.trace([4] * 32)
        _, row, request = self.measured(path)
        for change in ('output', 'generator', 'packet', 'prompt', 'coverage'):
            measured, declared = copy.deepcopy(row), copy.deepcopy(request)
            if change == 'output':
                measured['output_ids'][0] = 99
            elif change == 'generator':
                measured['generator']['tree_sha'] = 'b' * 64
            elif change == 'packet':
                packet = scored_forcing.read_reference(measured['raw_evidence'], self.root)
                measured['raw_evidence'] = self.fixture.save(packet)
            elif change == 'prompt':
                declared['input_ids'] = [2, 8]
            with self.subTest(change=change), self.assertRaises(ValueError):
                dev_campaign.check_scored_measurements([path], [] if change == 'coverage' else [measured],
                    [declared], evidence_root=self.root)

    def test_each_raw_evidence_hash_is_checked(self):
        path = self.fixture.trace([4] * 32)
        original = json.loads(path.read_text())
        for field in ('scores', 'generation', 'scorer', 'generator'):
            trace = copy.deepcopy(original)
            references = dict(scores=trace['raw_evidence'], generation=trace['generation_segments'][0],
                              scorer=trace['scorer']['evidence'], generator=trace['generator']['evidence'])
            references[field]['sha256'] = '0' * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'checksum'):
                scored_forcing.load_score_trace(self.saved_trace(trace), evidence_root=self.root)

    def test_changed_packet_bytes_fail_even_when_trace_reference_is_unchanged(self):
        path = self.fixture.trace([4] * 32)
        trace = json.loads(path.read_text())
        packet_path = Path(trace['generation_segments'][0]['path'])
        packet_path.write_text(packet_path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            scored_forcing.load_score_trace(path, evidence_root=self.root)

    def test_rehashed_wrong_own_prefix_and_scores_still_fail_semantic_checks(self):
        path = self.fixture.trace([4] * 32)
        original = json.loads(path.read_text())
        for change in ('prefix', 'generation', 'score', 'explanation'):
            trace = copy.deepcopy(original)
            if change in ('prefix', 'generation'):
                reference = trace['raw_evidence'] if change == 'prefix' else trace['generation_segments'][0]
                packet = scored_forcing.read_reference(reference, self.root)
                packet['request']['input_ids'][0] = 99
                replacement = self.fixture.save(packet)
                if change == 'prefix':
                    trace['raw_evidence'] = replacement
                else:
                    trace['generation_segments'] = [replacement]
            elif change == 'score':
                trace['scores'][0]['margin'] = 99
            else:
                trace['scores'][0]['explained'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                scored_forcing.load_score_trace(self.saved_trace(trace), evidence_root=self.root)

    def test_evidence_cannot_escape_declared_root(self):
        path = self.fixture.trace([4] * 32)
        narrower = self.root / 'empty-evidence-root'
        narrower.mkdir()
        with self.assertRaisesRegex(ValueError, 'escapes'):
            scored_forcing.load_score_trace(path, evidence_root=narrower)


class CampaignCapabilitiesTests(SyntheticEvidenceTests):
    def setUp(self):
        super().setUp()
        self.baseline = baseline_fixtures.BaselineValidationTests()
        self.baseline.setUp()
        self.addCleanup(self.baseline.doCleanups)
        self.baseline.fixture(speedup=1.06, per_suite=6)
        self.session = self.baseline.root / 'candidate'
        self.session.mkdir()
        for path in self.baseline.root.iterdir():
            if path != self.session:
                path.rename(self.session / path.name)
        self.root = self.baseline.root / 'synthetic-evidence'
        self.root.mkdir()
        self.fixture.root = self.root
        manifest = json.loads((self.session / 'manifest.json').read_text())
        self.arms = [dict(name=name, block=block, tree_sha='a' * 64, env={})
                     for name, block in (('stock', 8), ('final', 32))]
        self.campaign = dict(manifest, directory=str(self.baseline.root), campaign_id='synthetic-controller',
            source_pin='b' * 40, source_sha256={}, model_path='/model', declared_models={},
            campaign_protocol_version='dev-joint-v1', full_scale_warmup=True,
            synchronized_start=True, raw_capture=True,
            gpus=[dict(index=index, uuid=f'gpu-{index}', name='synthetic-H100') for index in (0, 1)],
            ports=[34000, 34004], candidate_arms=self.arms,
            launch_protocol=dict(model_path='/model', dtype='bfloat16', enable_fp32_lm_head=False))
        self.campaign['protocol_id'] = paper_policy.measurement_protocol_id(self.campaign)
        manifest.update(self.campaign, arms=self.arms, head=self.campaign['source_pin'])
        self.write('manifest.json', manifest)
        pairs = []
        for number in (1, 2):
            root = self.session / f'round-{number:02d}'
            assignments = [dict(arm=arm, port=port, gpu=gpu) for arm, port, gpu in zip(
                self.arms, self.campaign['ports'], self.campaign['gpus'][::1 if number == 1 else -1])]
            self.write(f'round-{number:02d}/deployment.json', dict(assignments=assignments))
            base = number * 1000
            round_pairs = []
            for index, request in enumerate(self.campaign['requests']):
                started = base + 100 + index * 10
                round_pairs.append(dict(id=request['id'], suite=request['suite'], round=number,
                    started_unix=started, finished_unix=started + 3,
                    **{key: self.sample(request, assignment, number, 2048, started)
                       for key, assignment in zip(('a', 'b'), assignments)}))
            self.write_rows(root / 'pairs.jsonl', round_pairs)
            for key, arm in zip(('a', 'b'), self.arms):
                self.write_rows(root / f'{arm["name"]}.jsonl', [pair[key] for pair in round_pairs])
            (root / 'ar.jsonl').unlink()
            warmups = []
            for index, request in enumerate(self.campaign['requests'][:2] + self.campaign['requests']):
                phase = 'short' if index < 2 else 'full'
                warmups.append(dict(id=request['id'], phase=phase,
                    **{key: self.sample(request, assignment, number, 32 if phase == 'short' else 2048,
                                        base + 2 + index * 2)
                       for key, assignment in zip(('a', 'b'), assignments)}))
            self.write_rows(root / 'warmup.jsonl', warmups)
            self.write_rows(root / 'events.jsonl', [dict(event=event, time_unix=base + offset)
                for event, offset in (('servers_started', 0), ('servers_ready', 1), ('warmup_complete', 80))])
            self.write_rows(root / 'telemetry.jsonl', [dict(time_unix=timestamp,
                gpus=[dict(gpu, clocks_sm_mhz=1000, clocks_mem_mhz=1000, temperature_c=40, power_w=100)
                      for gpu in self.campaign['gpus']],
                arms={arm['name']: [dict(pid=number * 10 + index, start_ticks=number * 10 + index,
                                        allowed_cpus='0-1')] for index, arm in enumerate(self.arms)})
                for timestamp in (round_pairs[0]['started_unix'] + .01, round_pairs[-1]['finished_unix'] - .01)])
            pairs.extend(round_pairs)
        summary = summarize(pairs, self.campaign['requests'], 2)
        summary.update(arms=['stock', 'final'], max_new_tokens=2048, per_suite_requested=6)
        self.write('summary.json', summary)

    def write(self, relative, value):
        (self.session / relative).write_text(json.dumps(value, allow_nan=False))

    def write_rows(self, path, rows):
        path.write_text(''.join(json.dumps(row, allow_nan=False) + '\n' for row in rows))

    def sample(self, request, assignment, number, cap, started):
        arm = assignment['arm']
        throughput = 1 if arm['name'] == 'stock' else 1.06
        latency = 2 / throughput
        arguments = dict(self.campaign['launch_protocol'], speculative_algorithm='DFLASH',
                         speculative_num_draft_tokens=arm['block'])
        generator = dict(tree_sha=arm['tree_sha'], server_args=arguments,
                         evidence=self.fixture.save(dict(http_status=200, response={'server_args': arguments})))
        raw = self.fixture.save(dict(http_status=200,
            request=dict(input_ids=request['input_ids'],
                         sampling_params=dict(temperature=0.0, top_k=1, max_new_tokens=cap)),
            response=dict(output_ids=[9, 10], meta_info=dict(completion_tokens=2, finish_reason={'type': 'stop'}))))
        start_ns = int(started * 1e9)
        return dict(id=request['id'], suite=request['suite'], turn=0, round=number,
            arm=arm['name'], block=arm['block'], tree_sha=arm['tree_sha'], gpu_uuid=assignment['gpu']['uuid'],
            input_sha256=request['input_sha256'], output_ids=[9, 10], output_sha256=sha_ids([9, 10]),
            tokens=2, completion_tokens=2, max_new_tokens=cap, finish_reason='stop',
            tokens_per_s=throughput, latency_s=latency, generator=generator, raw_evidence=raw,
            client_timing=dict(step_start_ns=start_ns, http_open_start_ns=start_ns + 1,
                body_complete_ns=start_ns + int(latency * 1e9) - 1,
                step_end_ns=start_ns + int(latency * 1e9), started_unix=started,
                url=f'http://127.0.0.1:{assignment["port"]}/generate'))

    def validate(self):
        return dev_campaign.validate_session(self.session, self.campaign)

    def rewrite_round(self, number, update):
        root = self.session / f'round-{number:02d}'
        pairs = read_rows(root / 'pairs.jsonl')
        update(pairs)
        self.write_rows(root / 'pairs.jsonl', pairs)
        for key, arm in zip(('a', 'b'), self.arms):
            self.write_rows(root / f'{arm["name"]}.jsonl', [pair[key] for pair in pairs])

    def test_complete_synthetic_session_has_two_swapped_fresh_rounds(self):
        checked, _, _, rows = self.validate()
        self.assertEqual(checked['requests'], 30)
        self.assertEqual(checked['pairs'], 60)
        self.assertTrue(checked['physical_gpu_swap'])
        self.assertEqual(len(set(checked['process_sessions'])), 2)
        self.assertEqual([len(round_rows['b']) for round_rows in rows], [30, 30])
        self.assertFalse(checked['ledger_eligible'])

    def test_missing_round_completion_is_rejected(self):
        (self.session / 'round-02/complete.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()

    def test_incomplete_round_is_rejected(self):
        self.write('round-02/complete.json', dict(round=2, pairs=29))
        with self.assertRaisesRegex(ValueError, 'incomplete round'):
            self.validate()

    def test_missing_half_pair_is_rejected(self):
        path = self.session / 'round-02/final.jsonl'
        self.write_rows(path, read_rows(path)[:-1])
        with self.assertRaisesRegex(ValueError, 'arm rows'):
            self.validate()

    def test_no_physical_swap_is_rejected_even_with_consistent_rows(self):
        deployment = json.loads((self.session / 'round-02/deployment.json').read_text())
        for assignment, gpu in zip(deployment['assignments'], self.campaign['gpus']):
            assignment['gpu'] = gpu
        self.write('round-02/deployment.json', deployment)
        def unswap(pairs):
            for pair in pairs:
                pair['a']['gpu_uuid'], pair['b']['gpu_uuid'] = 'gpu-0', 'gpu-1'
        self.rewrite_round(2, unswap)
        with self.assertRaisesRegex(ValueError, 'GPUs were not exchanged'):
            self.validate()

    def test_single_gpu_cannot_be_relabelled_as_a_pair(self):
        deployment = json.loads((self.session / 'round-01/deployment.json').read_text())
        deployment['assignments'][1]['gpu'] = deployment['assignments'][0]['gpu']
        self.write('round-01/deployment.json', deployment)
        with self.assertRaisesRegex(ValueError, 'physical GPU assignment'):
            self.validate()

    def test_raw_measured_evidence_hash_replacement_is_rejected(self):
        self.rewrite_round(1, lambda pairs: pairs[0]['b']['raw_evidence'].update(sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.validate()

    def test_rehashed_native_packet_cannot_disagree_with_measured_output(self):
        def replace(pairs):
            sample = pairs[0]['b']
            packet = scored_forcing.read_reference(sample['raw_evidence'], self.root)
            packet['response']['output_ids'] = [8, 8]
            sample['raw_evidence'] = self.fixture.save(packet)
        self.rewrite_round(1, replace)
        with self.assertRaisesRegex(ValueError, 'original native HTTP packet'):
            self.validate()

    def test_full_pass_warmup_cannot_be_deleted(self):
        path = self.session / 'round-02/warmup.jsonl'
        self.write_rows(path, read_rows(path)[:-1])
        with self.assertRaisesRegex(ValueError, 'full-pass warmup'):
            self.validate()

    def test_second_round_must_use_fresh_server_processes(self):
        first = read_rows(self.session / 'round-01/telemetry.jsonl')[0]['arms']
        path = self.session / 'round-02/telemetry.jsonl'
        rows = read_rows(path)
        for row in rows:
            row['arms'] = first
        self.write_rows(path, rows)
        with self.assertRaisesRegex(ValueError, 'fresh round server'):
            self.validate()

    def test_summary_speedup_cannot_replace_recalculated_measurements(self):
        summary = json.loads((self.session / 'summary.json').read_text())
        summary['lower'] = summary['upper'] = summary['geomean'] = 10
        self.write('summary.json', summary)
        with self.assertRaisesRegex(ValueError, 'statistics differ'):
            self.validate()


class PolicyCapabilitiesTests(unittest.TestCase):
    def calibration(self, noise=.002):
        sessions = [dict(session_id=name, protocol_id='synthetic-protocol', source_sha256=digest * 64,
                         interval=dict(lower=1 - noise, geomean=1, upper=1 + noise))
                    for name, digest in (('pre', 'a'), ('post', 'b'))]
        return paper_policy.calibration_from_intervals(sessions, declared_sessions=['pre', 'post'],
            protocol_id='synthetic-protocol', campaign_id='synthetic-campaign', policy=paper_policy.POLICY)

    def correctness(self, passed=True):
        return dev_campaign.combine_correctness([
            dict(correctness_passed=passed, evidence_sha256='c' * 64),
            dict(correctness_passed=True, evidence_sha256='d' * 64)])

    def verdict(self, speedup=1.06, calibration=None, correctness=None, identical=True, groups=None):
        return paper_policy.candidate_verdict(
            groups={'suite': [math.log(speedup)] * 6} if groups is None else groups,
            calibration=self.calibration() if calibration is None else calibration,
            correctness=self.correctness() if correctness is None else correctness,
            protocol_id='synthetic-protocol', campaign_id='synthetic-campaign', output_identical=identical)

    def test_healthy_correct_candidate_passes_readiness_but_never_promotes(self):
        result = self.verdict()
        self.assertTrue(result['eligible_for_promotion'])
        self.assertFalse(result['promoted'])
        self.assertFalse(result['ledger_eligible'])

    def test_noisy_null_increases_threshold_instead_of_being_ignored(self):
        calibration = self.calibration(noise=.02)
        rejected = self.verdict(speedup=1.04, calibration=calibration)
        accepted = self.verdict(speedup=1.06, calibration=calibration)
        self.assertAlmostEqual(rejected['threshold'], .05)
        self.assertFalse(rejected['performance_passed'])
        self.assertTrue(accepted['performance_passed'])

    def test_noise_cannot_be_lowered_even_after_rehashing_calibration(self):
        for rehash in (False, True):
            calibration = self.calibration(noise=.02)
            calibration['noise'] = 0
            if rehash:
                calibration['evidence_sha256'] = paper_policy.record_digest(calibration)
            with self.subTest(rehash=rehash), self.assertRaises(ValueError):
                self.verdict(speedup=1.04, calibration=calibration)

    def test_missing_reordered_or_duplicate_null_sessions_are_rejected(self):
        for change in ('missing', 'reordered', 'duplicate'):
            calibration = self.calibration()
            if change == 'missing':
                calibration['sessions'].pop()
            elif change == 'reordered':
                calibration['sessions'].reverse()
            else:
                calibration['sessions'][1] = copy.deepcopy(calibration['sessions'][0])
            calibration['evidence_sha256'] = paper_policy.record_digest(calibration)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.verdict(calibration=calibration)

    def test_wrong_campaign_protocol_and_historical_replay_are_rejected(self):
        for field, value in (('protocol_id', 'other'), ('campaign_id', 'other'), ('historical_replay', True)):
            calibration = self.calibration()
            calibration[field] = value
            calibration['evidence_sha256'] = paper_policy.record_digest(calibration)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verdict(calibration=calibration)

    def test_divergent_output_keeps_three_percent_floor(self):
        self.assertTrue(self.verdict(speedup=1.02)['performance_passed'])
        result = self.verdict(speedup=1.02, identical=False)
        self.assertAlmostEqual(result['threshold'], .03)
        self.assertFalse(result['performance_passed'])

    def test_threshold_is_strictly_greater_not_greater_or_equal(self):
        calibration = self.calibration(noise=.125)
        result = self.verdict(speedup=1.26, calibration=calibration)
        self.assertEqual(result['interval']['lower'] - 1, result['threshold'])
        self.assertFalse(result['performance_passed'])

    def test_mean_speedup_cannot_replace_the_lower_confidence_bound(self):
        result = self.verdict(groups={'suite': [math.log(.8), math.log(1.6)]})
        self.assertGreater(result['interval']['geomean'] - 1, result['threshold'])
        self.assertLess(result['interval']['lower'] - 1, result['threshold'])
        self.assertFalse(result['eligible_for_promotion'])

    def test_bad_correctness_cannot_be_offset_by_large_speedup(self):
        result = self.verdict(speedup=10, correctness=self.correctness(False))
        self.assertTrue(result['performance_passed'])
        self.assertFalse(result['correctness_passed'])
        self.assertFalse(result['eligible_for_promotion'])

    def test_missing_round_and_malformed_correctness_hash_fail_closed(self):
        for verdicts in ([], [dict(correctness_passed=True, evidence_sha256='a' * 64)],
                         [dict(correctness_passed=True, evidence_sha256='bad')] * 2):
            with self.subTest(verdicts=verdicts), self.assertRaises(ValueError):
                dev_campaign.combine_correctness(verdicts)
        with self.assertRaises(ValueError):
            self.verdict(correctness=dict(correctness_passed=True, evidence_sha256='bad'))

    def test_nonfinite_empty_or_invalid_performance_samples_are_rejected(self):
        for groups in ({}, {'suite': []}, {'suite': [math.nan]}, {'suite': [math.inf]}):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                self.verdict(groups=groups)

    def test_low_level_policy_does_not_authenticate_correctness_receipt(self):
        receipt = self.correctness(False)
        receipt['correctness_passed'] = True
        self.assertTrue(self.verdict(correctness=receipt)['eligible_for_promotion'])

    def test_low_level_round_combiner_does_not_establish_distinct_round_identity(self):
        receipt = dict(correctness_passed=True, evidence_sha256='a' * 64)
        result = dev_campaign.combine_correctness([receipt, copy.deepcopy(receipt)])
        self.assertTrue(result['correctness_passed'])
        self.assertFalse(result['ledger_eligible'])


if __name__ == '__main__':
    unittest.main()
