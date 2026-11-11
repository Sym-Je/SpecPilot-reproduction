import math
import unittest

from harness.acceptance_headroom import structural_limit, expected_progress, cost_scenario, finite_lattice_prior


class AcceptanceHeadroomTests(unittest.TestCase):
    def test_node_budget_includes_anchor_and_branching_cannot_create_depth(self):
        self.assertEqual(structural_limit(7,8)['max_progress'],8)
        self.assertEqual(structural_limit(7,128)['max_progress'],8)
        self.assertEqual(structural_limit(31,8)['max_progress'],8)
        self.assertEqual(structural_limit(0,1)['max_accepted_drafts'],0)

    def test_remaining_output_and_first_token_are_not_part_of_steady_state_bound(self):
        result=structural_limit(7,8)
        self.assertFalse(result['includes_prefill_seed_or_tail'])
        self.assertFalse(result['runtime_budget_optimal'])

    def test_tail_sum_not_independent_per_position_acceptance(self):
        self.assertEqual(expected_progress([1,1,1]),4)
        self.assertEqual(expected_progress([0,0,0]),1)
        self.assertAlmostEqual(expected_progress([0.8,0.4,0.2]),2.4)
        for values in ([0.4,0.8],[-1],[math.nan],[True]):
            with self.subTest(values=values),self.assertRaises(ValueError): expected_progress(values)

    def test_cost_can_reverse_larger_acceptance_and_prefill_dilutes_gain(self):
        self.assertLess(cost_scenario(4,6,2,0)['request_speedup'],1)
        self.assertAlmostEqual(cost_scenario(4,6,1,0)['request_speedup'],1.5)
        self.assertAlmostEqual(cost_scenario(4,6,1,0.5)['request_speedup'],1.2)
        self.assertEqual(cost_scenario(4,6,1.5,0)['request_speedup'],1)

    def test_invalid_structural_or_cost_assumptions_reject(self):
        for depth,nodes in ((True,8),(-1,8),(7,0),(1,False)):
            with self.subTest(depth=depth,nodes=nodes),self.assertRaises(ValueError):structural_limit(depth,nodes)
        for arguments in ((0,6,1,0),(4,math.inf,1,0),(4,6,-1,0),(4,6,1,1.1)):
            with self.subTest(arguments=arguments),self.assertRaises(ValueError):cost_scenario(*arguments)

    def test_finite_lattice_evidence_keeps_scope_and_break_even_cost_separate(self):
        replay=dict(stock_tau=4,oracle_tau=6,best_first_tau={'8':4.2,'16':5},eligible_steps=12,
            tail_steps_excluded=2,aggregation='equal request then repeat')
        prior=finite_lattice_prior(replay,independent_requests=10,repeats=2)
        self.assertEqual(prior['curve']['16']['step_cost_ratio_break_even'],1.25)
        self.assertEqual(prior['structural']['max_progress'],8)
        self.assertFalse(prior['global_oracle'])
        self.assertFalse(prior['actual_tree_execution'])
        self.assertIsNone(prior['optimal_runtime_budget'])
        self.assertEqual(prior['independent_requests'],10)
        self.assertEqual(prior['physical_repeats'],2)
        replay['oracle_tau']=9
        with self.assertRaises(ValueError):finite_lattice_prior(replay,independent_requests=10,repeats=2)


if __name__=='__main__':unittest.main()
