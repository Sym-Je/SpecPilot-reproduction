"""Frozen author-product sampling diagnostics, never a distributional correctness verdict."""

import math

from controller.stats import stratified_geomean_ci


TEMPERATURES=(0.,.7,1.)
SEEDS=(0,1)
SUITES=('gsm8k','math500','humaneval','mbpp','mt-bench')


def parameters(temperature,seed):
    if (type(temperature) not in (int,float) or not math.isfinite(temperature) or temperature not in TEMPERATURES or
            type(seed) is not int or seed not in SEEDS):
        raise ValueError('unregistered temperature or seed')
    return dict(temperature=float(temperature),top_k=1 if temperature==0 else -1,top_p=1.,sampling_seed=seed)


def non_argmax_count(response):
    metadata=response.get('meta_info',{})
    chosen=metadata.get('output_token_logprobs')
    tops=metadata.get('output_top_logprobs')
    if not isinstance(chosen,list) or not isinstance(tops,list) or len(chosen)!=len(tops):
        return None
    count=0
    for selected,alternatives in zip(chosen,tops):
        if not selected or selected[0] is None or not alternatives:
            continue
        probabilities=[row[0] for row in alternatives if row and type(row[0]) in (int,float)]
        if probabilities and max(probabilities)>selected[0]+1e-6:
            count+=1
    return count


def validate_measurement(row,packet,input_ids,temperature,seed):
    from controller.http_transport import sha_ids
    expected=dict(parameters(temperature,seed),max_new_tokens=2048)
    metadata=packet.get('response',{}).get('meta_info',{})
    if (packet.get('http_status')!=200 or packet['request'].get('input_ids')!=input_ids or
            packet['request'].get('sampling_params')!=expected or
            row['output_ids']!=packet['response'].get('output_ids') or row['tokens']!=len(row['output_ids']) or
            row['tokens']!=metadata.get('completion_tokens') or row['completion_tokens']!=row['tokens'] or
            row['input_sha256']!=sha_ids(input_ids) or row['output_sha256']!=sha_ids(row['output_ids']) or
            row['finish_reason']!=metadata.get('finish_reason',{}).get('type')):
        raise ValueError('timed packet binding differs')
    values=(row['latency_ms'],row['tokens_per_s'],row['latency_s'])
    if any(type(value) not in (int,float) or not math.isfinite(value) or value<=0 for value in values):
        raise ValueError('invalid latency or throughput')
    if not math.isclose(row['tokens_per_s'],row['tokens']/(row['latency_ms']/1000),rel_tol=1e-12) or not math.isclose(row['latency_s'],row['latency_ms']/1000,rel_tol=1e-12):
        raise ValueError('throughput differs from token/elapsed time')
    clock=row['client_timing']
    elapsed=(clock['step_end_ns']-clock['step_start_ns'])/1e6
    if not 0<=elapsed-row['latency_ms']<5:
        raise ValueError('latency differs from native client monotonic interval')


def summarize(pairs,requests):
    if len(requests)!=20 or len({row['id'] for row in requests})!=20:
        raise ValueError('twenty independent requests required')
    expected={(number,item['id']+f'@s{seed}') for item in requests for seed in SEEDS for number in (1,2)}
    actual=[(pair['round'],pair['id']) for pair in pairs]
    if len(actual)!=len(set(actual)) or set(actual)!=expected:
        raise ValueError('missing or repeated request/seed/round pair')
    grouped={row['id']:[] for row in requests}
    for pair in pairs:
        values=[pair[arm]['tokens_per_s'] for arm in ('a','b')]
        if any(type(value) not in (int,float) or not math.isfinite(value) or value<=0 for value in values):
            raise ValueError('invalid throughput')
        grouped[pair['id'].rsplit('@s',1)[0]].append(math.log(values[1]/values[0]))
    means={key:sum(values)/len(values) for key,values in grouped.items()}
    suites={suite:[means[row['id']] for row in requests if row['suite']==suite] for suite in SUITES}
    if any(len(values)!=4 for values in suites.values()):
        raise ValueError('four requests per suite required')
    return dict(interval=stratified_geomean_ci(suites),per_suite={key:math.exp(sum(values)/len(values)) for key,values in suites.items()},
        independent_requests=20,pairs=len(pairs),per_request_log_ratio=means,metric='final/stock output token rate',
        seed_repeats_clustered=True,physical_rounds_clustered=True,ledger_eligible=False,distributional_correctness_tested=False)
