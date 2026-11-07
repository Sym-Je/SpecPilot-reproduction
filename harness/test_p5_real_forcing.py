import json
from pathlib import Path
import unittest

from harness import test_p5_scored_forcing as scored_tests


class InjectionCoverageTests(unittest.TestCase):
    def fixture(self):
        helper = scored_tests.ScoredForcingTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        path = helper.trace([4] * 2056, role='ar')
        trace = json.loads(path.read_text())
        prompt = trace['prompt_ids']
        first = helper.save({'http_status': 200, 'request': {'input_ids': prompt,
            'sampling_params': {'max_new_tokens': 2048}}, 'response': {'output_ids': [4] * 2048,
            'meta_info': {'completion_tokens': 2048, 'finish_reason': {'type': 'length'}}}})
        second = helper.save({'http_status': 200, 'request': {'input_ids': prompt + [4] * 2048,
            'sampling_params': {'max_new_tokens': 2048, 'logit_bias': {str(token): 2 for token in range(0, 28, 7)}}},
            'response': {'output_ids': [4] * 8, 'meta_info': {'completion_tokens': 8}}})
        trace['generation_segments'] = [first, second]
        return helper, Path(helper.save(trace)['path'])

    def test_actual_post2048_native_bias_is_required(self):
        from controller.scored_forcing import validate_injected_generation
        helper, path = self.fixture()
        result = validate_injected_generation(path, evidence_root=helper.root, vocabulary_size=28)
        self.assertEqual(result['post2048_tokens'], 8)
        self.assertEqual(result['bias'], 2)
        self.assertEqual(result['stride'], 7)

    def test_short_or_missing_bias_does_not_count_as_real_fault_coverage(self):
        from controller.scored_forcing import validate_injected_generation
        helper, path = self.fixture()
        trace = json.loads(path.read_text())
        trace['generation_segments'] = trace['generation_segments'][:1]
        invalid = Path(helper.save(trace)['path'])
        with self.assertRaises(ValueError):
            validate_injected_generation(invalid, evidence_root=helper.root, vocabulary_size=28)


class RealRunContractTests(unittest.TestCase):
    def test_continuation_requires_prebound_source_inventory_and_rejects_later_mutation(self):
        from exp.p5_real_run import verify_generation_inventory
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'old'
            source.mkdir()
            artifact = source / 'trace.json'
            artifact.write_text('{}')
            inventory = root / 'inventory.json'
            inventory.write_text(json.dumps(dict(source_directory=str(source),
                files={'trace.json': hashlib.sha256(artifact.read_bytes()).hexdigest()})))
            expected = hashlib.sha256(inventory.read_bytes()).hexdigest()
            self.assertEqual(verify_generation_inventory(inventory, expected)['source_directory'], str(source))
            artifact.write_text('{"changed":true}')
            with self.assertRaises(ValueError): verify_generation_inventory(inventory, expected)
            with self.assertRaises(ValueError): verify_generation_inventory(inventory, '0' * 64)

    def test_explicit_evidence_roots_allow_bound_continuation_not_arbitrary_siblings(self):
        from controller.scored_forcing import read_bound
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second, third = [root / name for name in ('first', 'second', 'third')]
            for directory in (first, second, third):
                directory.mkdir()
                (directory / 'source.json').write_text('{"ok": true}')
            self.assertTrue(read_bound(first / 'source.json', (first, second))[0]['ok'])
            self.assertTrue(read_bound(second / 'source.json', (first, second))[0]['ok'])
            with self.assertRaises(ValueError): read_bound(third / 'source.json', (first, second))

    def test_eos_at_the_boundary_is_not_injection_coverage(self):
        from exp.p5_real_run import eligible_requests
        requests = [{'id': 'early'}, {'id': 'eos'}, {'id': 'long'}]
        generated = {'early': {'output_ids': [1], 'meta_info': {'finish_reason': {'type': 'stop'}}},
                     'eos': {'output_ids': [1] * 2048, 'meta_info': {'finish_reason': {'type': 'stop'}}},
                     'long': {'output_ids': [1] * 2048, 'meta_info': {'finish_reason': {'type': 'length'}}}}
        self.assertEqual([row['id'] for row in eligible_requests(requests, generated)], ['long'])

    def test_final_rejection_is_not_hidden_as_an_evaluator_failure_or_acceptance(self):
        from exp.p5_real_run import final_acceptance
        healthy = {'correctness_passed': True}
        verdicts = {name: healthy for name in ('healthy_stock', 'healthy_ar', 'healthy_segmented', 'equivalent_head')}
        verdicts.update(faulty={'correctness_passed': False, 'event_flagged': True}, author_final={'correctness_passed': False})
        result = final_acceptance(verdicts, post2048_tokens=1024)
        self.assertTrue(result['judge_ready'])
        self.assertFalse(result['author_final_correctness_passed'])
        self.assertFalse(result['next_stage_allowed'])
        self.assertFalse(final_acceptance(verdicts, post2048_tokens=0)['judge_ready'])
