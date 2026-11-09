"""Evidence-scoped observations, not a replacement for controller decisions."""

from collections import defaultdict
import math

from costmodel.floors import H100, floor_latency
from exp.diagnosis_trace import stage_summary


def interval_union(intervals):
    checked = []
    for start, end in intervals:
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (start,end))
                or end < start):
            raise ValueError('invalid trace interval')
        checked.append((start,end))
    total, previous = 0., None
    for start,end in sorted(checked):
        if previous is None:
            previous = (start,end)
        elif start <= previous[1]:
            previous = (previous[0],max(previous[1],end))
        else:
            total += previous[1]-previous[0]
            previous = (start,end)
    return total + (previous[1]-previous[0] if previous else 0)


def counter_observation(metadata, block=8):
    names = ('completion_tokens','spec_verify_ct','spec_accepted_drafts','spec_num_correct_drafts',
             'spec_proposed_drafts','spec_num_proposed_drafts','spec_accept_histogram',
             'spec_correct_drafts_histogram','spec_accept_rate','spec_accept_length')
    errors = ['missing '+name for name in names if name not in metadata]
    if not errors:
        for name in names[:6]:
            value = metadata[name]
            if type(value) is not int or value < 0:
                errors.append('invalid '+name)
        for name in names[6:8]:
            histogram = metadata[name]
            if (not isinstance(histogram,list) or len(histogram) != block or
                    any(type(value) is not int or value < 0 for value in histogram)):
                errors.append('invalid '+name)
        for name in names[8:]:
            value = metadata[name]
            if type(value) not in (int,float) or not math.isfinite(value):
                errors.append('invalid '+name)
    correct_mean = emitted_mean = clip = None
    if not errors:
        steps, tokens = metadata['spec_verify_ct'], metadata['completion_tokens']
        accepted, proposed = metadata['spec_accepted_drafts'], metadata['spec_proposed_drafts']
        histogram = metadata['spec_accept_histogram']
        weighted = sum(index*count for index,count in enumerate(histogram))
        tests = dict(positive_steps_and_tokens=steps>0 and tokens>0 and proposed>0,
            histogram_counts=sum(histogram)==steps, histogram_weight=weighted==accepted,
            correct_alias=accepted==metadata['spec_num_correct_drafts'],
            proposed_alias=proposed==metadata['spec_num_proposed_drafts'],
            histogram_alias=histogram==metadata['spec_correct_drafts_histogram'],
            fixed_stock_budget=proposed==(block-1)*steps)
        if steps>0 and proposed>0:
            tests.update(rate=math.isclose(metadata['spec_accept_rate'],accepted/proposed,rel_tol=1e-10,abs_tol=1e-10),
                emitted_length=math.isclose(metadata['spec_accept_length'],tokens/steps,rel_tol=1e-10,abs_tol=1e-10),
                conditional_tail_clip=0<=accepted+steps-tokens<block)
        errors.extend(name for name,passed in tests.items() if not passed)
        if not errors:
            correct_mean,emitted_mean,clip = accepted/steps,tokens/steps,accepted+steps-tokens
    return dict(algebra_consistent=not errors,errors=errors,
        reported_correct_drafts_per_verify=correct_mean,emitted_tokens_per_reported_verify=emitted_mean,
        reported_correct_draft_histogram=metadata['spec_accept_histogram'] if not errors else None,
        conditional_tail_clip_tokens=clip,per_step_token_lattice_available=False,
        semantics='native histogram and aliases checked algebraically; bonus/tail reconstruction is conditional, not an audited token lattice')


def matmul_scenario(event):
    name = event.get('name')
    arguments = event.get('args',{})
    shapes,types = arguments.get('Input Dims'),arguments.get('Input type')
    if name not in ('aten::mm','aten::bmm') or not isinstance(shapes,list) or len(shapes)<2:
        return None
    if not isinstance(types,list) or len(types)<2 or any(value not in ('c10::BFloat16','BFloat16','bfloat16') for value in types[:2]):
        return None
    left,right = shapes[:2]
    dimensions = 2 if name=='aten::mm' else 3
    if (not isinstance(left,list) or not isinstance(right,list) or len(left)!=dimensions or len(right)!=dimensions or
            any(type(value) is not int or value<=0 for value in left+right) or left[-1]!=right[-2]):
        return None
    if dimensions==3 and left[0]!=right[0]:
        return None
    batch = left[0] if dimensions==3 else 1
    rows,inner,columns = left[-2],left[-1],right[-1]
    flops = 2*batch*rows*inner*columns
    nbytes = 2*batch*(rows*inner+inner*columns+rows*columns)
    return dict(flops=flops,cold_tensor_io_bytes=nbytes,nominal_floor_us=1e6*floor_latency(H100,flops,nbytes),
        measured_dram_bytes=False,assumptions='BF16 dense mm/bmm; each input read and output written once from cold memory; 60% nominal dense peak, 90% nominal bandwidth')


def nominal_matmul_floors(events,kernels):
    operations = []
    for event in events:
        scenario = matmul_scenario(event)
        if scenario is not None and event.get('ph')=='X':
            interval_union([(event['ts'],event['ts']+event['dur'])])
            operations.append((event,scenario))
    correlations = defaultdict(set)
    for launch in events:
        if launch.get('ph')!='X' or launch.get('cat') not in ('cuda_runtime','cuda_driver'):
            continue
        correlation = launch.get('args',{}).get('correlation')
        if correlation is None:
            continue
        matches = [index for index,(event,_) in enumerate(operations)
            if (event.get('pid'),event.get('tid'))==(launch.get('pid'),launch.get('tid'))
            and event['ts']<=launch['ts']<event['ts']+event['dur']]
        correlations[correlation].update(matches if matches else [-1])
    durations = defaultdict(float)
    for kernel in kernels:
        candidates = correlations.get(kernel.get('args',{}).get('correlation'),set())
        if len(candidates)==1 and -1 not in candidates:
            durations[next(iter(candidates))] += kernel['dur']
    scenarios = [dict(operations[index][1],observed_kernel_sum_us=durations[index]) for index in sorted(durations)]
    return dict(eligible_ops=len(scenarios),flops=sum(row['flops'] for row in scenarios),
        cold_tensor_io_bytes=sum(row['cold_tensor_io_bytes'] for row in scenarios),
        nominal_floor_sum_us=sum(row['nominal_floor_us'] for row in scenarios),
        observed_kernel_sum_us=sum(row['observed_kernel_sum_us'] for row in scenarios),
        measured_dram_bytes=False,full_step_floor_available=False,
        scope='shape-qualified, uniquely correlated BF16 mm/bmm subset only; CUDA graph hidden shapes and all other kernels remain unknown')


def trace_observation(events):
    kernels = [event for event in events if event.get('ph')=='X' and event.get('cat')=='kernel']
    devices = defaultdict(list)
    for kernel in kernels:
        start,duration = kernel.get('ts'),kernel.get('dur')
        if (any(type(value) not in (int,float) or not math.isfinite(value) for value in (start,duration))
                or duration<0):
            raise ValueError('invalid GPU kernel interval')
        device = kernel.get('args',{}).get('device')
        key = str(device) if device is not None else 'unknown-device'
        devices[key].append((start,start+duration))
    busy = {key:interval_union(value) for key,value in sorted(devices.items())}
    single = next(iter(busy.values())) if len(busy)==1 and 'unknown-device' not in busy else None
    span = max(end for values in devices.values() for _,end in values)-min(start for values in devices.values() for start,_ in values) if kernels else None
    return dict(kernel_sum_us=sum(kernel['dur'] for kernel in kernels),gpu_busy_us_by_device=busy,
        single_device_busy_us=single,gpu_kernel_span_us=span,
        gpu_busy_interval_scope='GPU kernel intervals only; transfer and memset activity is excluded',
        stages=stage_summary(events),nominal_matmul_floors=nominal_matmul_floors(events,kernels),
        scope='profile-window GPU work, per-device busy union and span; not end-to-end fractions or unprofiled CPU overhead')


def factor_coverage():
    return dict(complete=False,ceiling=None,factors=dict(
        tau=dict(value=None,missing='same-lattice token proposals, target decisions and exact replay tau_best'),
        kernel=dict(value=None,missing='all kernel-class work/byte floors; shape-qualified nominal mm subset is insufficient and DRAM traffic is not measured'),
        overhead=dict(value=None,missing='matched unprofiled per-step wall time and GPU execution; do not divide unprofiled full requests by profiled early windows')))
