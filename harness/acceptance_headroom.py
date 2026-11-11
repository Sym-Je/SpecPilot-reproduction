"""Conditional acceptance bounds; none of these quantities certify runtime speedup."""

import math


def positive(value,zero=False):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0 or (not zero and value==0):
        raise ValueError('finite positive number required')
    return value


def structural_limit(draft_depth,verify_nodes):
    if type(draft_depth) is not int or draft_depth<0 or type(verify_nodes) is not int or verify_nodes<1:
        raise ValueError('nonnegative draft depth and positive node budget required')
    maximum=min(draft_depth,verify_nodes-1)
    return dict(max_accepted_drafts=maximum,max_progress=maximum+1,
        draft_depth=draft_depth,verify_nodes_including_anchor=verify_nodes,
        includes_prefill_seed_or_tail=False,runtime_budget_optimal=False,
        assumptions=['One prefix-closed accepted path, one target/bonus per verify.',
            'Node budget includes the anchor; branches consume nodes, not extra accepted path length.',
            'Steady-state proposal bound, not committed request output after EOS/cap clipping.'])


def expected_progress(survival_tail):
    if not isinstance(survival_tail,list):raise ValueError('prefix survival probabilities required')
    previous=1
    for probability in survival_tail:
        positive(probability,zero=True)
        if probability>previous:raise ValueError('prefix survival tail must be nonincreasing within [0,1]')
        previous=probability
    return 1+math.fsum(survival_tail)


def cost_scenario(baseline_tau,candidate_tau,step_cost_ratio,prefill_fraction):
    baseline_tau=positive(baseline_tau);candidate_tau=positive(candidate_tau)
    step_cost_ratio=positive(step_cost_ratio);prefill_fraction=positive(prefill_fraction,zero=True)
    if prefill_fraction>1:raise ValueError('baseline prefill fraction must be within [0,1]')
    decode_ratio=step_cost_ratio*baseline_tau/candidate_tau
    return dict(request_speedup=1/(prefill_fraction+(1-prefill_fraction)*decode_ratio),
        step_cost_ratio_break_even=candidate_tau/baseline_tau,
        assumptions=['Equal output workload and unchanged prefill; steady-state approximation.',
            'Full step cost includes draft, tree selection, verify, commit and state maintenance.',
            'Input ratios are explicit assumptions, not measured performance or promotion.'])


def finite_lattice_prior(replay,*,independent_requests,repeats):
    for value in (independent_requests,repeats):
        if type(value) is not int or value<1:raise ValueError('positive independent request/repeat count required')
    stock=positive(replay['stock_tau']);oracle=positive(replay['oracle_tau'])
    if not 1<=stock<=oracle<=8:raise ValueError('block8 finite oracle/stock outside structural bounds')
    curve={};previous=1
    for budget,value in sorted(replay['best_first_tau'].items(),key=lambda item:int(item[0])):
        if not isinstance(budget,str) or not budget.isdecimal() or int(budget)<1:
            raise ValueError('anchor-inclusive node budget required')
        tau=positive(value)
        if not previous<=tau<=min(oracle,int(budget)):raise ValueError('finite replay curve outside nested tree bounds')
        previous=tau
        curve[budget]=dict(conditional_progress=tau,progress_ratio=tau/stock,step_cost_ratio_break_even=tau/stock,
            measured_step_cost=None,measured_speedup=None)
    return dict(structural=structural_limit(7,8),stock_conditional_progress=stock,
        finite_lattice_oracle_progress=oracle,finite_lattice_oracle_progress_ratio=oracle/stock,
        same_cohort_structural_progress_ratio=8/stock,
        structural_alternatives=[structural_limit(depth-1,depth) for depth in (8,16,32)],
        depth=7,candidates_per_position=16,curve=curve,independent_requests=independent_requests,
        physical_repeats=repeats,eligible_steps=replay['eligible_steps'],excluded_tail_steps=replay['tail_steps_excluded'],
        aggregation=replay['aggregation'],global_oracle=False,actual_tree_execution=False,optimal_runtime_budget=None,
        caveats=['Historical conditional replay on recorded stock continuations; not live tree verification.',
            'Oracle reads the future target path for evaluation, never for online tree selection.',
            'Scores restricted/normalized inside top16; not complete target-distribution probabilities.',
            'No support for extrapolation to deeper draft blocks or unseen request distributions.',
            'Best-first acceptance is not the maximum over all online policies; choose budget by full cost.',
            'Recorded stock continuation is not a proof of FP32-forcing equivalence; near-tie forks may change outcomes.'])
