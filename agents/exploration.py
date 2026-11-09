"""Evidence-bound proposal contracts and a CPU-only broker, never a controller."""

import hashlib
import json
import math
from pathlib import Path
import re


ROOT=Path(__file__).resolve().parents[1]
SOURCE_PATHS=('agents/exploration.py','agents/exploration_prompts.py','exp/exploration.py',
              'harness/test_p13_exploration.py')


def object_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    return {name:file_sha(ROOT/name) for name in SOURCE_PATHS}


def build_evidence(source_pin):
    paths={
        'E001':'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json',
        'E002':'logs/bottleneck-public-20261109-a02/analysis.json',
        'E003':'logs/bottleneck-public-20261109-a02/result.json',
        'E004':'logs/step-replay-public-20261109-a01/result.json'}
    loaded={name:json.loads((ROOT/path).read_text()) for name,path in paths.items()}
    config,analysis,counters,replay=[loaded[name] for name in paths]
    if config['stock']['block_size']!=8 or not counters['profile_capture_complete'] or replay['real_request_replays']!=6:
        raise ValueError('unexpected stock evidence protocol')
    evidence={
        'E001':dict(kind='deployment',data=dict(models=config['models'],stock=config['stock'],
            block_size=8,engine_version='SGLang v0.5.20',gpu='H100 80GB',concurrency=1,
            max_new_tokens=2048,natural_eos=True,stock_tree_sha='e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff')),
        'E002':dict(kind='profile',data={key:analysis[key] for key in (
            'independent_requests','profile_windows','equal_request_profile_window_kernel_work_share',
            'cumulative_kernel_ms','identifiable_mm_ops','identifiable_mm_cumulative_kernel_ms',
            'identifiable_mm_kernel_work_fraction','identifiable_mm_nominal_scenario_floor_ms','factor_coverage')},
            limitations=['early instrumented windows, not end-to-end time fractions',
                'nominal cold-I/O subset floor is not measured DRAM or all-kernel floor',
                'physical repeats are not independent requests']),
        'E003':dict(kind='counters',data=dict(independent_requests=10,
            suites={suite:{key:row[key] for key in ('independent_requests','timed_arm_rows','completion_tokens_mean',
                'stop_count','length_count','algebra_consistent_counter_rows','counter_rows',
                'native_correct_draft_histogram_work_counts')} for suite,row in counters['suites'].items()}),
            limitations=['histograms include only rows passing the historical conditional diagnostic; HumanEval has 4/8 rows',
                'the historical missing initial token was explained by E004, not a generation-error verdict']),
        'E004':dict(kind='linear-replay',data=dict(independent_requests=3,
            replays=[{key:row[key] for key in ('suite','role','round','seed_tokens','observed_verify_steps',
                'committed_verify_steps','uncommitted_verify_steps','correct_drafts','untrimmed_output_tokens',
                'output_tokens','tail_clip_tokens')} for row in replay['replays']]),
            limitations=['observed stock linear chains only, not an optimal-tree lattice',
                'observer synchronizes/copies/logs; its times are not unprofiled step times',
                'no matched end-to-end benefit from removing an overlap tail has been measured'])}
    for name in evidence:
        evidence[name]['source']=dict(path=paths[name],sha256=file_sha(ROOT/paths[name]))
    packet=dict(schema='exploration-evidence-v1',source_pin=source_pin,evidence=evidence,
        capabilities=dict(full_factors_available=False,tau_best_available=False,
            unprofiled_step_timing_available=False,controller_modification_allowed=False,
            gpu_submission_allowed=False,code_implementation_allowed=False),
        scope='first proposal only; no author final, registry, private prompts, generated text or sealed data')
    packet['evidence_sha256']=object_sha(packet)
    return packet


def validate_transport(receipt,request_sha):
    if (receipt.get('backend')!='codex-subagent-tool' or not receipt.get('agent_id') or
            receipt.get('request_sha256')!=request_sha or receipt.get('model_selection')!='inherited-default' or
            receipt.get('resolved_model_id') is not None):
        raise ValueError('missing real backend identity/request binding; exact model ID is not exposed')


def require_text(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('nonempty text required')


def references(values,allowed):
    if not isinstance(values,list) or any(value not in allowed for value in values):
        raise ValueError('unknown evidence/tool reference')


def validate_master(response,packet):
    if response.get('schema')!='master-plan-v1' or response.get('evidence_sha256')!=packet['evidence_sha256']:
        raise ValueError('master response is not bound to issued evidence')
    directions=response.get('directions')
    if not isinstance(directions,list) or not 1<=len(directions)<=2 or len({row['id'] for row in directions})!=len(directions):
        raise ValueError('one or two independently selected directions required')
    for direction in directions:
        if not re.fullmatch('[a-z][a-z0-9-]{0,63}',direction['id']) or direction['factor'] not in ('tau','kernel','overhead','ceiling_assumption','unknown'):
            raise ValueError('invalid direction identity/factor')
        for field in ('hypothesis','cheapest_test'):
            require_text(direction[field])
        references(direction['evidence_refs'],packet['evidence'])
        if not direction['evidence_refs']:
            raise ValueError('direction without evidence')
    if not isinstance(response.get('unknowns'),list):
        raise ValueError('master must record unknowns')


def validate_direction(response,packet,direction_id,tools):
    if (response.get('schema')!='direction-result-v1' or response.get('direction_id')!=direction_id or
            response.get('evidence_sha256')!=packet['evidence_sha256'] or response.get('implementation_ready') is not False or
            response.get('status') not in ('proposal','closed','needs_measurement')):
        raise ValueError('invalid direction result or attempted implementation authorization')
    references(response['evidence_refs'],packet['evidence'])
    references(response['tool_refs'],{row['id'] for row in tools})
    if response['status']=='closed' and not any(row['id'] in response['tool_refs'] and row['status']=='completed' for row in tools):
        raise ValueError('missing data is not experimentally closed')
    require_text(response['hypothesis'])
    if not isinstance(response.get('limitations'),list) or not response['limitations']:
        raise ValueError('direction must state evidence limits')
    estimate=response.get('net_headroom_estimate')
    if estimate is not None:
        if type(estimate) not in (int,float) or not math.isfinite(estimate) or estimate<0:
            raise ValueError('invalid hypothesis headroom')
        require_text(response.get('estimate_basis'))
    experiment=response['next_experiment']
    for field in ('procedure','kill_if'):
        require_text(experiment[field])
    minutes=experiment['budget_gpu_minutes']
    if type(minutes) not in (int,float) or not math.isfinite(minutes) or not 0<=minutes<=120:
        raise ValueError('experiment needs a finite bounded future budget; it is not authorized here')
    proposal=response.get('proposal')
    if proposal is not None:
        for field in ('mechanism','option','default_stock_argument','correctness_contract','implementation_scope'):
            require_text(proposal[field])
        if 'stock_default' not in proposal or 'candidate_value' not in proposal or not proposal.get('acceptance_commands'):
            raise ValueError('candidate needs a default-stock option and executable future acceptance')
    if response['status']=='proposal' and proposal is None:
        raise ValueError('proposal status needs an actual option proposal')


def run_cpu_tool(packet,request):
    if set(request)!={'name','arguments'} or not isinstance(request['arguments'],dict):
        raise ValueError('invalid CPU request')
    name,arguments=request['name'],request['arguments']
    common=dict(end_to_end_gain=None,controller_measurement=False)
    if name=='profile_coverage' and not arguments:
        profile=packet['evidence']['E002']['data']
        return dict(common,shape_qualified_kernel_work_fraction=profile['identifiable_mm_cumulative_kernel_ms']/profile['cumulative_kernel_ms'],
            kernel_factor=None,source_refs=['E002'],scope='shape-qualified kernel subset, not global efficiency or speedup')
    if name=='overlap_work' and not arguments:
        samples=packet['evidence']['E004']['data']['replays']
        return dict(common,samples=[dict(committed_verify_steps=row['committed_verify_steps'],
            uncommitted_verify_steps=row['uncommitted_verify_steps'],
            uncommitted_step_count_fraction=row['uncommitted_verify_steps']/(row['committed_verify_steps']+row['uncommitted_verify_steps']))
            for row in samples],source_refs=['E004'],scope='step-count fraction only; no critical-path latency inference')
    if name=='local_prefix_budget' and set(arguments)=={'suite','budget'}:
        budget=arguments['budget']
        if type(budget) is not int or not 2<=budget<=8:
            raise ValueError('only a prefix of the observed stock block8 is available')
        suite=arguments['suite']
        data=packet['evidence']['E003']['data']['suites']
        if suite not in data:
            raise ValueError('unknown suite')
        histogram=data[suite]['native_correct_draft_histogram_work_counts']
        if not isinstance(histogram,list) or len(histogram)!=8 or any(type(count) is not int or count<0 for count in histogram) or sum(histogram)<=0:
            raise ValueError('missing native local-prefix histogram')
        return dict(common,suite=suite,budget=budget,reported_verify_work_count=sum(histogram),
            mean_local_emitted_tokens=sum((min(index,budget-1)+1)*count for index,count in enumerate(histogram))/sum(histogram),
            full_counterfactual_trajectory_available=False,source_refs=['E003'],
            scope='same observed local prefixes only, work-weighted covered rows; excludes initial token, termination, redrafting and cost changes')
    raise ValueError('CPU broker refuses unknown tools, shell, GPU and file access')
