import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from harness.acceptance_evidence import estimate_conditional, summarize_native


def sha(value):
    return hashlib.sha256(value).hexdigest()


class AcceptanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = dict(tree_sha='a' * 64, server_args=dict(
            speculative_algorithm='DFLASH', speculative_num_draft_tokens=4,
            model_path='/public/target', speculative_draft_model_path='/public/draft'))

    def capture(self, name='one', histogram=None, emitted=None):
        histogram = [1, 0, 1, 1] if histogram is None else histogram
        steps = sum(histogram)
        accepted = sum(index * count for index, count in enumerate(histogram))
        emitted = accepted + steps if emitted is None else emitted
        directory = self.root / name
        (directory / 'native').mkdir(parents=True)
        ids = [10, 20]
        input_sha = sha(json.dumps(ids, separators=(',', ':')).encode())
        self.metadata = dict(completion_tokens=emitted, prompt_tokens=len(ids),
            num_retractions=0, spec_verify_ct=steps, spec_accepted_drafts=accepted,
            spec_num_correct_drafts=accepted, spec_proposed_drafts=3 * steps,
            spec_num_proposed_drafts=3 * steps, spec_accept_histogram=histogram,
            spec_correct_drafts_histogram=list(histogram),
            spec_accept_rate=accepted / (3 * steps), spec_accept_length=emitted / steps,
            finish_reason=dict(type='stop', matched=99))
        self.packet = dict(url='http://localhost:30500/generate', http_status=200,
            request=dict(input_ids=ids, sampling_params=dict(temperature=0, top_k=1,
                max_new_tokens=100, ignore_eos=False)),
            response=dict(output_ids=[30] * (emitted - 1) + [99], meta_info=self.metadata))
        identity_packet = dict(url='http://localhost:30500/get_server_info', http_status=200,
            request=None, response=dict(self.baseline['server_args']))
        generation = self.write(directory / 'native/generation.json', self.packet)
        identity = self.write(directory / 'native/identity.json', identity_packet)
        self.manifest = dict(schema='stock-profile-capture-v1',
            arm=dict(name='stock', option_enabled=False, env={}, block=4,
                tree_sha=self.baseline['tree_sha']),
            identity=dict(evidence=identity, **copy.deepcopy(self.baseline)),
            request=dict(id=name, input_ids=ids, input_sha256=input_sha),
            preset=dict(mode='canonical-stock-graph', max_new_tokens=100),
            generation=generation,
            files={'native/generation.json': generation['sha256'],
                   'native/identity.json': identity['sha256']})
        self.reference = dict(self.write(directory / 'manifest.json', self.manifest),
                              input_sha256=input_sha)
        return copy.deepcopy(self.reference)

    def write(self, path, value):
        content = json.dumps(value, sort_keys=True).encode()
        path.write_bytes(content)
        return dict(path=str(path), sha256=sha(content))

    def refresh(self):
        directory = Path(self.reference['path']).parent
        self.manifest['generation'] = self.write(directory / 'native/generation.json', self.packet)
        self.manifest['files']['native/generation.json'] = self.manifest['generation']['sha256']
        self.reference.update(self.write(directory / 'manifest.json', self.manifest))
        return copy.deepcopy(self.reference)

    def summarize(self, references):
        return summarize_native(references, canonical_stock=self.baseline)

    def test_weighted_counts_and_request_distribution(self):
        first = self.capture()
        second = self.capture('two', [0, 2, 0, 0])
        result = self.summarize([first, second])
        aggregate = result['aggregate']
        self.assertEqual(aggregate['reported_accepted_draft_tokens'], 7)
        self.assertEqual(aggregate['verify_steps'], 5)
        self.assertEqual(aggregate['emitted_tokens'], 12)
        self.assertEqual(aggregate['accepted_draft_histogram'], [1, 2, 1, 1])
        self.assertAlmostEqual(aggregate['mean_accepted_drafts_per_verify'], 7 / 5)
        self.assertAlmostEqual(aggregate['request_mean_accepted_drafts_per_verify'], (5 / 3 + 1) / 2)
        self.assertEqual(len(result['requests']), 2)
        self.assertEqual(len(result['sources']), 6)
        self.assertIn('verify', result['weighting'])
        self.assertIn('reported_accepted_draft_tokens', result['units'])

    def test_tail_first_token_eos_are_not_invented(self):
        reference = self.capture(emitted=6)
        result = self.summarize([reference])
        row = result['requests'][0]
        self.assertEqual(row['reported_accepted_draft_tokens'], 5)
        self.assertAlmostEqual(row['mean_accepted_drafts_per_verify'], 5 / 3)
        self.assertEqual(row['emitted_tokens_per_verify'], 2)
        self.assertEqual(row['native_spec_accept_length'], 2)
        self.assertAlmostEqual(row['nominal_tokens_per_verify'], 8 / 3)
        self.assertEqual(row['conditional_uncommitted_tokens'], 2)
        self.assertIsNone(row['committed_accepted_draft_tokens'])
        self.assertIsNone(row['first_token_contribution'])
        self.assertTrue(row['matched_stop_id_is_last_output'])
        self.assertIn('EOS', ' '.join(result['unknowns']))
        self.assertIn('not an ideal oracle', result['scope'])

    def test_all_zero_accepted_is_valid_not_missing(self):
        result = self.summarize([self.capture(histogram=[3, 0, 0, 0])])
        self.assertEqual(result['aggregate']['reported_accepted_draft_tokens'], 0)
        self.assertEqual(result['aggregate']['mean_accepted_drafts_per_verify'], 0)

    def test_every_input_sha_and_native_sha_are_bound(self):
        for target in ('manifest', 'native', 'identity', 'input', 'manifest_input'):
            with self.subTest(target=target):
                reference = self.capture(target)
                if target in ('manifest', 'native', 'identity'):
                    path = reference['path'] if target == 'manifest' else (
                        self.manifest['generation']['path'] if target == 'native'
                        else self.manifest['identity']['evidence']['path'])
                    with Path(path).open('ab') as output:
                        output.write(b' ')
                elif target == 'input':
                    reference['input_sha256'] = 'b' * 64
                else:
                    self.manifest['request']['input_sha256'] = 'b' * 64
                    reference = self.refresh()
                with self.assertRaises(ValueError):
                    self.summarize([reference])

    def test_malformed_missing_and_invalid_counts_rejected(self):
        changes = [(key, value) for key in ('spec_verify_ct', 'completion_tokens',
                    'spec_accepted_drafts', 'spec_proposed_drafts', 'spec_accept_length',
                    'spec_accept_rate') for value in (True, float('nan'), float('inf'), -1)]
        changes += [('spec_verify_ct', 0), ('completion_tokens', 0),
                    ('spec_proposed_drafts', 0), ('spec_accept_length', 0),
                    ('spec_accept_histogram', [True, 0, 1, 1]),
                    ('spec_accept_histogram', [1, 0, 1]),
                    ('spec_accept_histogram', [1, -1, 1, 1])]
        for index, (key, value) in enumerate(changes):
            with self.subTest(key=key, value=value):
                self.capture(str(index))
                self.metadata[key] = value
                with self.assertRaises(ValueError):
                    self.summarize([self.refresh()])
        for index, key in enumerate(tuple(self.metadata)):
            with self.subTest(missing=key):
                self.capture('missing-' + str(index))
                del self.metadata[key]
                with self.assertRaises(ValueError):
                    self.summarize([self.refresh()])

    def test_inconsistent_workload_and_aliases_rejected(self):
        changes = [('spec_num_correct_drafts', 4), ('spec_num_proposed_drafts', 8),
                   ('spec_accepted_drafts', 4), ('spec_verify_ct', 4),
                   ('spec_correct_drafts_histogram', [1, 1, 0, 1]),
                   ('spec_accept_rate', .9), ('spec_accept_length', 99),
                   ('prompt_tokens', 3), ('num_retractions', 1)]
        for index, (key, value) in enumerate(changes):
            with self.subTest(key=key):
                self.capture(str(index))
                self.metadata[key] = value
                with self.assertRaises(ValueError):
                    self.summarize([self.refresh()])
        self.capture('ids')
        self.packet['response']['output_ids'].pop()
        with self.assertRaises(ValueError):
            self.summarize([self.refresh()])
        self.capture('input-ids')
        self.packet['request']['input_ids'][0] = 11
        with self.assertRaises(ValueError):
            self.summarize([self.refresh()])

    def test_mixed_baseline_options_sampling_and_warmup_rejected(self):
        first = self.capture()
        for index, target in enumerate(('tree', 'option', 'block', 'args', 'mode', 'sampling', 'max')):
            with self.subTest(target=target):
                self.capture(str(index))
                if target == 'tree':
                    self.manifest['arm']['tree_sha'] = 'b' * 64
                elif target == 'option':
                    self.manifest['arm']['option_enabled'] = True
                elif target == 'block':
                    self.manifest['arm']['block'] = 8
                elif target == 'args':
                    self.manifest['identity']['server_args']['model_path'] = '/other'
                elif target == 'mode':
                    self.manifest['preset']['mode'] = 'other'
                elif target == 'sampling':
                    self.packet['request']['sampling_params']['temperature'] = .7
                else:
                    self.packet['request']['sampling_params']['max_new_tokens'] = 32
                with self.assertRaises(ValueError):
                    self.summarize([first, self.refresh()])

    def test_duplicates_empty_and_path_escape_rejected(self):
        reference = self.capture()
        for references in ([], [reference, reference]):
            with self.assertRaises(ValueError):
                self.summarize(references)
        self.manifest['generation']['path'] = str(self.root / 'outside.json')
        with self.assertRaises(ValueError):
            self.summarize([self.refresh_without_packet()])

    def test_same_native_response_cannot_be_counted_via_two_manifests(self):
        reference = self.capture()
        alias = dict(self.write(self.root / 'one/alias.json', self.manifest),
                     input_sha256=reference['input_sha256'])
        with self.assertRaises(ValueError):
            self.summarize([reference, alias])

    def test_manifest_identity_must_match_actual_server(self):
        self.capture()
        path = Path(self.manifest['identity']['evidence']['path'])
        packet = json.loads(path.read_bytes())
        packet['response']['model_path'] = '/different'
        identity = self.write(path, packet)
        self.manifest['identity']['evidence'] = identity
        self.manifest['files']['native/identity.json'] = identity['sha256']
        with self.assertRaises(ValueError):
            self.summarize([self.refresh_without_packet()])

    def test_file_index_mismatch_missing_source_and_missing_pin_rejected(self):
        for target in ('index', 'source', 'pin'):
            with self.subTest(target=target):
                self.capture(target)
                if target == 'index':
                    self.manifest['files']['native/generation.json'] = 'c' * 64
                elif target == 'source':
                    Path(self.manifest['generation']['path']).unlink()
                else:
                    del self.manifest['generation']['sha256']
                with self.assertRaises(ValueError):
                    self.summarize([self.refresh_without_packet()])

    def refresh_without_packet(self):
        self.reference.update(self.write(Path(self.reference['path']), self.manifest))
        return copy.deepcopy(self.reference)

    def test_http_errors_and_raw_response_disagreement_rejected(self):
        self.capture()
        self.packet['http_status'] = 500
        with self.assertRaises(ValueError):
            self.summarize([self.refresh()])
        self.capture('raw')
        raw = json.dumps({'error': 'different response'}).encode()
        self.packet.update(response_bytes_base64=base64.b64encode(raw).decode(),
                           response_bytes_sha256=sha(raw))
        with self.assertRaises(ValueError):
            self.summarize([self.refresh()])

    def test_valid_and_tampered_raw_response_binding(self):
        self.capture()
        raw = json.dumps(self.packet['response']).encode()
        self.packet.update(response_bytes_base64=base64.b64encode(raw).decode(),
                           response_bytes_sha256=sha(raw))
        self.assertEqual(self.summarize([self.refresh()])['aggregate']['verify_steps'], 3)
        self.packet['response_bytes_sha256'] = 'd' * 64
        with self.assertRaises(ValueError):
            self.summarize([self.refresh()])

    def test_no_stop_token_or_length_finish_does_not_manufacture_eos(self):
        self.capture()
        self.metadata['finish_reason'] = dict(type='length', length=8)
        row = self.summarize([self.refresh()])['requests'][0]
        self.assertIsNone(row['matched_stop_id_is_last_output'])
        self.assertIsNone(row['committed_accepted_draft_tokens'])


class ConditionalEstimateTests(unittest.TestCase):
    def estimate(self, **kwargs):
        return estimate_conditional(assumptions=['same emitted workload and decoding regime'], **kwargs)

    def test_conditioned_cost_extra_and_slowdown(self):
        result = self.estimate(tau_ratio=1.5, step_cost_ratio=1.1, extra_step_cost_ratio=.2)
        self.assertAlmostEqual(result['conditional_decode_speedup'], 1.5 / 1.3)
        self.assertTrue(result['assumptions'])
        self.assertIsNone(result['end_to_end_speedup'])
        result = self.estimate(tau_ratio=1.2, step_cost_ratio=1, extra_step_cost_ratio=.5)
        self.assertAlmostEqual(result['conditional_decode_speedup'], .8)

    def test_unknown_cost_never_implies_free_work(self):
        for kwargs in ({}, dict(step_cost_ratio=1), dict(extra_step_cost_ratio=0)):
            with self.subTest(kwargs=kwargs):
                result = self.estimate(tau_ratio=1.5, **kwargs)
                self.assertIsNone(result['conditional_decode_speedup'])
                self.assertTrue(result['unknowns'])

    def test_invalid_numbers_and_assumptions(self):
        for key in ('tau_ratio', 'step_cost_ratio', 'extra_step_cost_ratio'):
            invalid = [True, float('nan'), float('inf'), -1]
            if key != 'extra_step_cost_ratio':
                invalid.append(0)
            for value in invalid:
                kwargs = dict(tau_ratio=1.2, step_cost_ratio=1, extra_step_cost_ratio=0)
                kwargs[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.estimate(**kwargs)
        with self.assertRaises(ValueError):
            estimate_conditional(tau_ratio=1.2, assumptions=[])


if __name__ == '__main__':
    unittest.main()
