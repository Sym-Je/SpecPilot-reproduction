"""Conservative Phase 0 coverage; missing denominators never become neutral factors."""

from collections import defaultdict

from costmodel.observations import factor_coverage, trace_observation


def coverage(*,conditional_replay=None,kernel_coverage=0.):
    if not 0<=kernel_coverage<=1:
        raise ValueError('invalid coverage')
    result=factor_coverage()
    result.update(conditional_replay=conditional_replay,identified_floor_work_fraction=kernel_coverage,
                  paper_definition='main text section 3.1 equation 4; 60% dense peak / 90% bandwidth',
                  appendix_definition='appendix B historical values use oracle and full peak; not mixed')
    if conditional_replay is not None:
        result['factors']['tau']['missing']='runtime-best budget and independent live tree target consistency; bounded replay reported separately'
    return result


def kernel_class(name):
    value=name.lower()
    if any(word in value for word in ('gemm','gemv','cutlass','cublas','matmul')):
        return 'dense_linear'
    if any(word in value for word in ('gdn','gated_delta','delta_rule','fused_recurrent','causal_conv')):
        return 'recurrent'
    if any(word in value for word in ('flash_fwd','flashattention','flash_attention','paged_attention','decode_attention')):
        return 'attention'
    if any(word in value for word in ('topk','top_k','argmax','sampling','selector','score_edges','sample_path')):
        return 'selection'
    if any(word in value for word in ('rms','layer_norm','layernorm','rotary','rope','silu','gelu')):
        return 'norm_position_activation'
    return 'other_unknown'


def profile_report(events):
    observation=trace_observation(events)
    classes=defaultdict(lambda:dict(count=0,kernel_sum_us=0.,floor_us=None))
    for event in events:
        if event.get('ph')=='X' and event.get('cat')=='kernel':
            row=classes[kernel_class(event.get('name',''))]
            row['count']+=1
            row['kernel_sum_us']+=event['dur']
    return dict(observation=observation,classes=dict(sorted(classes.items())),
                class_rule='ordered kernel-name heuristic; unrecognized names retained; not a byte/FLOP workload model',
                full_floor_available=False)
