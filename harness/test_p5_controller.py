from fractions import Fraction
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from controller.http_transport import Arm, HttpPairBench
from controller.stats import binom_one_sided, bootstrap_ci, paired_ci
from controller.token_force import judge_forcing
from exp import p3_pair_run as runner
from exp import p5_readiness_audit as audit
from harness.test_p3_pair_run import FakeBench, FakeServer


class StatisticalContractTests(unittest.TestCase):
    def test_binomial_matches_small_exact_enumeration(self):
        for total in range(1, 15):
            for count in range(total + 1):
                for probability in (Fraction(1, 10), Fraction(1, 2), Fraction(9, 10)):
                    expected = sum(Fraction(math.comb(total, index)) * probability ** index
                                   * (1 - probability) ** (total - index)
                                   for index in range(count, total + 1))
                    self.assertAlmostEqual(binom_one_sided(count, total, float(probability)),
                                           float(expected), places=11)

    def test_binomial_long_sequences_and_endpoints(self):
        self.assertEqual(binom_one_sided(0, 4096, .0072), 1.0)
        self.assertEqual(binom_one_sided(0, 0, .5), 1.0)
        self.assertEqual(binom_one_sided(1, 100000, 0), 0.0)
        self.assertEqual(binom_one_sided(100000, 100000, 1), 1.0)
        self.assertAlmostEqual(binom_one_sided(1, 100000, 1e-6),
                               -math.expm1(100000 * math.log1p(-1e-6)), places=10)
        self.assertGreater(binom_one_sided(2048, 4096, .5), .5)
        self.assertLess(binom_one_sided(2048, 4096, .5), .51)

    def test_binomial_invalid_parameters_are_rejected(self):
        for arguments in ((-1, 10, .5), (11, 10, .5), (0, -1, .5),
                          (1.5, 10, .5), (0, 10, -1), (0, 10, 2),
                          (0, 10, float('nan')), (0, 10, float('inf'))):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                binom_one_sided(*arguments)

    def test_paired_ci_rejects_nonpositive_and_nonfinite_measurements(self):
        for value in (0, -1, float('nan'), float('inf')):
            for left, right in (([value], [1]), ([1], [value])):
                with self.subTest(left=left, right=right), self.assertRaises(ValueError):
                    paired_ci(left, right)

    def test_bootstrap_rejects_invalid_inputs(self):
        for values, options in (([float('nan')], {}), ([float('inf')], {}),
                                ([1], {'iters': 0}), ([1], {'alpha': 0}),
                                ([1], {'alpha': .5})):
            with self.subTest(values=values, options=options), self.assertRaises(ValueError):
                bootstrap_ci(values, **options)


class ForcingContractTests(unittest.TestCase):
    def test_empty_and_incomplete_samples_are_rejected(self):
        for base, candidate in (([], []), ([[]], [[]]), ([[1]], [[]]),
                                ([[1, 2]], [[1]]), ([[1]], [[1, 2]])):
            with self.subTest(base=base, candidate=candidate), self.assertRaises(ValueError):
                judge_forcing(base, candidate)

    def test_identical_long_sequence_does_not_crash(self):
        result = judge_forcing([[1] * 4096], [[1] * 4096])
        self.assertTrue(result.lossless)
        self.assertEqual(result.n, 4096)

    def test_rate_rule_uses_lower_bound_not_uncertainty_width(self):
        result = judge_forcing([[1] * 1000], [[2] * 1000])
        self.assertTrue(result.rate_flagged)
        self.assertTrue(result.event_flagged)
        self.assertFalse(result.lossless)

    def test_invalid_tokens_and_baseline_parameters_are_rejected(self):
        for token in (-1, True, 1.5):
            with self.subTest(token=token), self.assertRaises(ValueError):
                judge_forcing([[token]], [[token]])
        for options in ({'base_rate': -1}, {'base_rate': float('nan')},
                        {'delta': -1}, {'delta': float('inf')}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                judge_forcing([[1]], [[1]], **options)

    def test_token_lists_never_claim_real_margin_aware_evidence(self):
        result = judge_forcing([[1]], [[1]]).to_dict()
        self.assertFalse(result['ledger_eligible'])
        self.assertEqual(result['scope'], 'token-list diagnostic; not teacher-forced scoring')


class PerformanceContractTests(unittest.TestCase):
    def compare(self, gain, identical=True, noise=0):
        bench = HttpPairBench(Arm('a', ''), Arm('b', ''))
        fixture = {'a_tps': [100.0], 'b_tps': [100.0 * (1 + gain)],
                   'rounds': [{'a': {'output_sha256': 'a'},
                               'b': {'output_sha256': 'a' if identical else 'b'}}]}
        with patch.object(bench, 'run_pair', return_value=fixture):
            return bench.compare([1], max_new=1, noise=noise)

    def test_divergence_requires_both_thresholds(self):
        self.assertFalse(self.compare(.025, identical=False)['promoted'])
        self.assertTrue(self.compare(.04, identical=False)['promoted'])
        self.assertFalse(self.compare(.04, identical=False, noise=.02)['promoted'])
        self.assertTrue(self.compare(.025, identical=True)['promoted'])

    def test_invalid_noise_is_rejected_before_requests(self):
        for noise in (-1, float('nan'), float('inf')):
            bench = HttpPairBench(Arm('a', ''), Arm('b', ''))
            with patch.object(bench, 'run_pair') as measure:
                with self.assertRaises(ValueError):
                    bench.compare([1], 1, noise=noise)
            measure.assert_not_called()


class NullOrchestrationTests(unittest.TestCase):
    def test_null_instance_names_and_launch_modes_are_separate(self):
        arguments = runner.parse_args(['stock', 'stock', '--out-dir', '/unused'])
        self.assertEqual(arguments.arms, ['stock-a', 'stock-b'])
        arms, config = runner.arm_specs(arguments.arms, runner.clean_environment())
        self.assertEqual(arms[0]['engine'], arms[1]['engine'])
        self.assertEqual(arms[0]['tree_sha'], arms[1]['tree_sha'])
        for arm in arms:
            self.assertEqual(arm['block'], config['stock']['block_size'])
            self.assertEqual(arm['env'], {})
            server = runner.Server(arm, {'uuid': 'synthetic-gpu'}, 31000, Path('/unused'), {})
            command, environment = server.launch_spec()
            self.assertEqual(command[2], 'stock')
            self.assertIn(arm['name'], environment['P3_SERVER_LOG'])

    def test_null_rounds_have_distinct_files_and_physical_gpu_swaps(self):
        arms = [{'name': name, 'launch_arm': 'stock', 'block': 8,
                 'tree_sha': 'synthetic', 'engine': '/synthetic/stock'}
                for name in ('stock-a', 'stock-b')]
        gpus = [{'index': index, 'uuid': f'synthetic-{index}'} for index in (0, 1)]
        requests = [{'id': 'one', 'suite': 'suite', 'input_ids': [1],
                     'input_sha256': runner.sha_ids([1])}]
        FakeServer.events = []
        FakeServer.fail_arm = FakeBench.fail_request = None
        with tempfile.TemporaryDirectory() as directory:
            for index in (0, 1):
                output = Path(directory) / f'round-{index}'
                pairs = runner.run_round(arms, gpus, [31000, 31010], index,
                                        requests, output, {}, 2048, 1, 30,
                                        server_factory=FakeServer, bench_factory=FakeBench)
                for arm in arms:
                    self.assertTrue((output / f'{arm["name"]}.jsonl').is_file())
                self.assertEqual(pairs[0]['a']['gpu_uuid'], gpus[index]['uuid'])
        self.assertEqual(len([event for event in FakeServer.events if event[0] == 'stop']), 4)

    def test_other_duplicate_arms_remain_rejected(self):
        for name in ('ar', 'final'):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                runner.parse_args([name, name, '--out-dir', '/unused'])

    def test_all_original_readiness_counterexamples_are_fixed(self):
        result = audit.audit()
        self.assertEqual(result['failed_checks'], [])
        self.assertTrue(result['contract_checks_passed'])
        self.assertFalse(result['production_ready'])


if __name__ == '__main__':
    unittest.main()
