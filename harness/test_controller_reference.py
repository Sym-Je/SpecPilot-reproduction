"""Synthetic reference separation checks; no GPU or model execution."""

import copy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from controller import dev_campaign
from controller.http_transport import sha_ids
from controller.scoring import NativeClient
from exp import dev_campaign as runner
from exp.p3_pair_run import summarize
from harness.baseline_validation import read_rows
from harness import test_controller_capabilities as capabilities


class ReferenceTests(unittest.TestCase):
    def build(self, *, separate=True, faulty=False, explicit=True):
        fixture = capabilities.CampaignCapabilitiesTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.baseline.root
        self.campaign = copy.deepcopy(fixture.campaign)
        self.campaign.update(started_unix=-1, source_sha256={'controller/head_reference.py': 'f' * 64})
        self.campaign['candidate_arms'][0]['tree_sha'] = 'b' * 64 if separate else 'a' * 64
        self.campaign['candidate_arms'][1]['tree_sha'] = 'c' * 64
        self.campaign['null_arms'] = [dict(self.campaign['candidate_arms'][0], name=name, launch_arm='stock')
                                      for name in ('stock-a', 'stock-b')]
        if explicit:
            self.campaign['reference_tree_sha'] = 'a' * 64
        seed = self.root / 'candidate'
        for phase in ('null-pre', 'null-post'):
            shutil.copytree(seed, self.root / phase)
        for phase_index, phase in enumerate(dev_campaign.PHASES):
            directory = self.root / phase
            arms = self.campaign['candidate_arms'] if phase == 'candidate' else self.campaign['null_arms']
            offset = phase_index * 10000
            manifest = dict(self.campaign, arms=arms, head=self.campaign['source_pin'], started_unix=offset)
            self.write(directory / 'manifest.json', manifest)
            all_pairs = []
            for number in (1, 2):
                root = directory / f'round-{number:02d}'
                deployment = json.loads((root / 'deployment.json').read_text())
                for assignment, arm in zip(deployment['assignments'], arms):
                    assignment['arm'] = arm
                self.write(root / 'deployment.json', deployment)
                pairs = read_rows(root / 'pairs.jsonl')
                for pair in pairs:
                    pair['started_unix'] += offset
                    pair['finished_unix'] += offset
                    for key, arm in zip(('a', 'b'), arms):
                        if phase != 'candidate':
                            sample = pair[key]
                            sample['latency_s'] = 2
                            start = sample['client_timing']['step_start_ns']
                            sample['client_timing']['body_complete_ns'] = start + 1999999999
                            sample['client_timing']['step_end_ns'] = start + 2000000000
                        output = [12] * 32 if separate else [9] * 32
                        if phase == 'candidate' and key == 'b':
                            output = [12 if faulty else 13] * 32
                        self.update_sample(pair[key], arm, offset, output)
                self.rows(root, pairs, arms)
                warmups = read_rows(root / 'warmup.jsonl')
                for row in warmups:
                    for key, arm in zip(('a', 'b'), arms):
                        self.update_sample(row[key], arm, offset, row[key]['output_ids'])
                self.write_rows(root / 'warmup.jsonl', warmups)
                events = read_rows(root / 'events.jsonl')
                for event in events:
                    event['time_unix'] += offset
                self.write_rows(root / 'events.jsonl', events)
                telemetry = read_rows(root / 'telemetry.jsonl')
                for snapshot in telemetry:
                    snapshot['time_unix'] += offset
                    previous = list(snapshot['arms'].values())
                    snapshot['arms'] = {arm['name']: processes for arm, processes in zip(arms, previous)}
                    for processes in snapshot['arms'].values():
                        for process in processes:
                            process['pid'] += offset
                            process['start_ticks'] += offset
                self.write_rows(root / 'telemetry.jsonl', telemetry)
                all_pairs.extend(pairs)
            summary = summarize(all_pairs, self.campaign['requests'], 2)
            summary.update(arms=[arm['name'] for arm in arms], max_new_tokens=2048, per_suite_requested=6,
                           completed_unix=offset + 3000)
            self.write(directory / 'summary.json', summary)
        self.write(self.root / 'manifest.json', self.campaign)
        self.launches = []
        self.active = {}
        self.score()
        return self.validate()

    def write(self, path, value):
        path.write_text(json.dumps(value, allow_nan=False))

    def write_rows(self, path, rows):
        path.write_text(''.join(json.dumps(row, allow_nan=False) + '\n' for row in rows))

    def rows(self, root, pairs, arms):
        self.write_rows(root / 'pairs.jsonl', pairs)
        for key, arm in zip(('a', 'b'), arms):
            self.write_rows(root / f'{arm["name"]}.jsonl', [pair[key] for pair in pairs])

    def update_sample(self, sample, arm, offset, output):
        raw = json.loads(Path(sample['raw_evidence']['path']).read_text())
        raw['response']['output_ids'] = output
        raw['response']['meta_info']['completion_tokens'] = len(output)
        raw['started_unix'] = sample['client_timing']['started_unix'] + offset
        arguments = dict(sample['generator']['server_args'], speculative_num_draft_tokens=arm['block'])
        sample.update(arm=arm['name'], block=arm['block'], tree_sha=arm['tree_sha'],
            output_ids=output, output_sha256=sha_ids(output), tokens=len(output), completion_tokens=len(output),
            tokens_per_s=len(output) / sample['latency_s'], raw_evidence=self.fixture.fixture.save(raw),
            generator=dict(tree_sha=arm['tree_sha'], server_args=arguments,
                evidence=self.fixture.fixture.save(dict(http_status=200, response={'server_args': arguments}))))
        sample['client_timing']['started_unix'] += offset
        for key in ('step_start_ns', 'http_open_start_ns', 'body_complete_ns', 'step_end_ns'):
            sample['client_timing'][key] += offset * 1000000000

    def specifications(self, names, environment):
        return [dict(name=name, tree_sha='a' * 64, block=0 if name == 'ar' else 8,
                     engine='/synthetic/canonical-stock', env={}) for name in names], {}

    def launch(self, arm, role, gpu, directory, environment, resources):
        self.launches.append((role, copy.deepcopy(arm)))
        self.active[30130 if role == 'scorer' else 30120] = role

    def client(self, url, directory):
        role = self.active[int(url.rsplit(':', 1)[1])]
        directory.mkdir(parents=True, exist_ok=True)
        fixture = self.fixture.fixture
        arguments = dict(model_path='/model', dtype='bfloat16', enable_fp32_lm_head=role == 'scorer',
            speculative_algorithm='DFLASH' if role == 'stock' else None,
            speculative_num_draft_tokens=8 if role == 'stock' else None,
            chunked_prefill_size=8192, enable_return_hidden_states=True, return_hidden_states_mode='last')

        class Client(NativeClient):
            def request(client, endpoint, body=None):
                if body is None:
                    response = {'server_args': arguments}
                elif role == 'scorer':
                    tokens = body['input_ids']
                    actual = [[None, tokens[0]]] + [[-.1, token] for token in tokens[1:]]
                    tops = [None] + [[[-.1, token]] for token in tokens[1:]]
                    for position, token in enumerate(tokens[2:], 2):
                        if (token == 9 and position == 3) or (token == 12 and position < 14):
                            actual[position][0] = -.2 if token == 9 else -2.1
                            tops[position] = [[-.1, 11]]
                    response = {'meta_info': dict(input_token_logprobs=actual, input_top_logprobs=tops)}
                else:
                    output = [9, 11] + [9] * 30 if role == 'ar' else [9] * 32
                    response = dict(output_ids=output,
                                    meta_info=dict(completion_tokens=32, finish_reason={'type': 'stop'}))
                client.last_evidence = fixture.save(dict(http_status=200, request=body,
                    response=response, started_unix=30000, finished_unix=30001))
                return response

        return Client(url, directory)

    def head(self, mode, directory, reference, tree):
        self.assertEqual(tree, 'a' * 64)
        directory.mkdir()
        result = dict(mode='preflight', tokens=1, native_reverse_token_differences=0,
            head_identity={'source_sha256': 'f' * 64},
            checks=[dict(native_logprob_error=0, native_choice_margin=0, max_logit_difference=0)])
        self.write(directory / 'result.json', result)
        return result

    def score(self):
        with patch.object(runner, 'arm_specs', self.specifications), patch.object(runner, 'launch', self.launch), \
                patch.object(runner, 'NativeClient', self.client), patch.object(runner, 'head_process', self.head), \
                patch.object(runner, 'wait_for_idle', return_value=self.campaign['gpus']), \
                patch.object(runner, 'check_ports'):
            runner.score_campaign(self.root, self.campaign, {})

    def validate(self):
        with patch('controller.null_validation.arm_specs', return_value=(self.campaign['null_arms'], {})):
            return dev_campaign.validate_campaign(self.root)

    def trace_path(self, cohort, index=0):
        return self.root / 'correctness' / cohort / f'{self.campaign["requests"][index]["id"]}.json'

    def test_legacy_without_reference_preserves_old_path(self):
        result = self.build(separate=False, explicit=False)
        self.assertTrue(result['joint_acceptance_passed'])
        self.assertNotIn('reference_tree_sha', result)
        self.assertFalse((self.root / 'correctness/reference-stock').exists())
        self.assertEqual([role for role, _ in self.launches], ['scorer', 'ar'])

    def test_explicit_canonical_comparator_needs_no_extra_generation(self):
        result = self.build(separate=False)
        self.assertTrue(result['joint_acceptance_passed'])
        self.assertFalse(result['independent_reference_stock'])
        self.assertFalse((self.root / 'correctness/reference-stock').exists())

    def test_optimized_comparator_uses_canonical_delta_and_stock_rate(self):
        result = self.build()
        self.assertTrue(result['joint_acceptance_passed'])
        self.assertEqual(result['reference_tree_sha'], 'a' * 64)
        self.assertTrue(result['independent_reference_stock'])
        self.assertEqual(result['deltas'], [.125, .125])
        self.assertEqual([counts['mismatches'] for counts in result['stock_counts']], [30, 30])
        self.assertEqual([counts['large_margin_events'] for counts in result['stock_counts']], [0, 0])
        self.assertEqual([role for role, _ in self.launches], ['scorer', 'ar', 'stock'])
        self.assertTrue(all(arm['engine'] == '/synthetic/canonical-stock' for _, arm in self.launches))
        self.assertFalse(result['promoted'])
        self.assertFalse(result['ledger_eligible'])

    def test_erroneous_comparison_stack_cannot_raise_candidate_tolerance(self):
        result = self.build(faulty=True)
        self.assertTrue(result['performance']['performance_passed'])
        self.assertFalse(result['joint_acceptance_passed'])
        self.assertEqual(result['deltas'], [.125, .125])
        self.assertTrue(all(verdict['event_flagged'] for verdict in result['correctness']['rounds']))

    def test_missing_reference_stock_fails_closed(self):
        self.build()
        self.trace_path('reference-stock').unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()

    def test_reference_identity_prompt_output_and_hash_cannot_be_replaced(self):
        self.build()
        path = self.trace_path('reference-stock')
        original = path.read_text()
        for change in ('generator', 'scorer', 'prompt', 'output', 'hash', 'generation_hash'):
            trace = json.loads(original)
            if change in ('generator', 'scorer'):
                trace[change]['tree_sha'] = 'b' * 64
            elif change == 'prompt':
                trace['prompt_ids'][0] = 8
            elif change == 'output':
                trace['output_ids'][0] = 8
            elif change == 'hash':
                trace['raw_evidence']['sha256'] = '0' * 64
            else:
                trace['generation_segments'][0]['sha256'] = '0' * 64
            self.write(path, trace)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate()
        path.write_text(original)

    def test_rehashed_reference_packet_must_use_registered_generation_protocol(self):
        self.build()
        path = self.trace_path('reference-stock')
        original = path.read_text()
        for change in ('bias', 'cap', 'timestamp', 'truncated_length'):
            trace = json.loads(original)
            packet = json.loads(Path(trace['generation_segments'][0]['path']).read_text())
            if change == 'bias':
                packet['request']['sampling_params']['logit_bias'] = {'7': 2}
            elif change == 'cap':
                packet['request']['sampling_params']['max_new_tokens'] = 4096
            elif change == 'timestamp':
                packet['started_unix'] = 1
            else:
                packet['response']['meta_info']['finish_reason']['type'] = 'length'
            trace['generation_segments'] = [self.fixture.fixture.save(packet)]
            self.write(path, trace)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate()
        path.write_text(original)

    def test_measured_comparator_forcing_remains_bound_to_timed_packet(self):
        self.build()
        path = self.trace_path('round-01-stock')
        trace = json.loads(path.read_text())
        packet = json.loads(Path(trace['generation_segments'][0]['path']).read_text())
        trace['generation_segments'] = [self.fixture.fixture.save(packet)]
        self.write(path, trace)
        with self.assertRaisesRegex(ValueError, 'exact original timed generation'):
            self.validate()

    def test_stored_calibration_cannot_report_comparison_stack_tolerance(self):
        self.build()
        path = self.root / 'correctness/round-01-delta.json'
        calibration = json.loads(path.read_text())
        calibration['delta'] = 2
        self.write(path, calibration)
        with self.assertRaisesRegex(ValueError, 'stored canonical calibration'):
            self.validate()

    def test_wrong_reference_teacher_or_ar_tree_is_rejected(self):
        self.build()
        path = self.trace_path('ar')
        trace = json.loads(path.read_text())
        trace['generator']['tree_sha'] = 'b' * 64
        self.write(path, trace)
        with self.assertRaisesRegex(ValueError, 'AR calibration'):
            self.validate()
        trace['generator']['tree_sha'] = 'a' * 64
        self.write(path, trace)
        for cohort in ('round-01-stock', 'round-01-final'):
            path = self.trace_path(cohort)
            original = path.read_text()
            trace = json.loads(original)
            trace['scorer']['tree_sha'] = 'b' * 64
            self.write(path, trace)
            with self.subTest(cohort=cohort), self.assertRaisesRegex(ValueError, 'canonical teacher'):
                self.validate()
            path.write_text(original)

    def test_biased_ar_cannot_inflate_canonical_delta(self):
        self.build()
        path = self.trace_path('ar')
        trace = json.loads(path.read_text())
        packet = json.loads(Path(trace['generation_segments'][0]['path']).read_text())
        packet['request']['sampling_params']['logit_bias'] = {'7': 2}
        trace['generation_segments'] = [self.fixture.fixture.save(packet)]
        self.write(path, trace)
        with self.assertRaisesRegex(ValueError, 'generation protocol'):
            self.validate()

    def test_comparison_null_requires_identical_outputs_between_instances(self):
        self.build()
        root = self.root / 'null-pre/round-01'
        pairs = read_rows(root / 'pairs.jsonl')
        self.update_sample(pairs[0]['b'], self.campaign['null_arms'][1], 0, [14] * 32)
        self.rows(root, pairs, self.campaign['null_arms'])
        with self.assertRaisesRegex(ValueError, 'comparison-null outputs differ'):
            self.validate()

    def test_session_reference_identity_cannot_drift(self):
        self.build()
        path = self.root / 'candidate/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['reference_tree_sha'] = 'b' * 64
        self.write(path, manifest)
        with self.assertRaisesRegex(ValueError, 'session deployment'):
            self.validate()

    def test_scorer_installation_must_match_frozen_reference_before_launch(self):
        self.build()
        shutil.rmtree(self.root / 'correctness')
        self.campaign['reference_tree_sha'] = 'd' * 64
        self.launches.clear()
        with self.assertRaisesRegex(ValueError, 'installed canonical'):
            self.score()
        self.assertEqual(self.launches, [])
        self.assertFalse((self.root / 'correctness').exists())

    def test_run_gate_records_spec_reference_not_comparison_sha(self):
        from exp import engine_dev_gate
        fixture = capabilities.SyntheticEvidenceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        config = root / 'config.json'
        self.write(config, {'models': {}})
        directory = root / 'gate'
        directory.mkdir()
        spec = dict(config_path=str(config), stock_tree_sha='a' * 64, target='/model', draft='/draft',
                    spec_sha256='e' * 64, value=8)
        arms = [dict(name=name, block=8, tree_sha=tree * 64, engine='/synthetic/stack', env={})
                for name, tree in (('stock', 'b'), ('candidate', 'c'))]
        record = dict(source_pin='d' * 40, action={'max_new_tokens': 2048})
        with patch.object(engine_dev_gate, 'ROOT', root), patch.object(engine_dev_gate, 'file_sha', return_value='f' * 64), \
                patch.object(engine_dev_gate, 'check_ports'), \
                patch.object(engine_dev_gate, 'run_round', side_effect=RuntimeError('fixture stop before GPU')):
            with self.assertRaisesRegex(RuntimeError, 'fixture stop'):
                engine_dev_gate.run_gate(directory, record, spec, arms, [], [dict(id=str(index)) for index in range(30)], {})
        manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertEqual(manifest['reference_tree_sha'], 'a' * 64)
        self.assertEqual(manifest['candidate_arms'][0]['tree_sha'], 'b' * 64)


if __name__ == '__main__':
    unittest.main()
