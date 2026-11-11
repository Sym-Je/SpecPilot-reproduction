"""Bounded recorded-ID observations, never inferred graph-node or source ownership."""

from collections import defaultdict
import math

from harness.skill_diagnostics import bounded_input_dims


INPUT_TYPES=frozenset(('float', 'double', 'half', 'bfloat16', 'Float', 'Double', 'Half',
    'BFloat16', 'long int', 'int', 'short int', 'unsigned char', 'char', 'bool',
    'Long', 'Int', 'Bool', 'Scalar', 'Tensor', '', 'c10::BFloat16', 'c10::Half'))


def numeric_id(arguments, field):
    value=arguments.get(field)
    return value if type(value) is int and value>=0 else None


def cpu_observation(event):
    arguments=event.get('args',{})
    dimensions=arguments.get('Input Dims')
    types=arguments.get('Input type')
    return dict(operator=event['name'][:160],
        input_dims=dimensions if bounded_input_dims(dimensions) else None,
        input_types=types if isinstance(types,list) and len(types)<=128 and
            all(isinstance(value,str) and value in INPUT_TYPES for value in types) else None,
        scope='Recorded CPU fields; not certified module, consumer, device dtype or kernel workload.')


def observed_kernel_links(events, trace_sha256, kernel, offset=0):
    if not isinstance(kernel,str) or not 1<=len(kernel)<=2048 or '\n' in kernel:
        raise ValueError('bounded exact kernel name required')
    if type(offset) is not int or offset<0:
        raise ValueError('kernel offset must be a nonnegative integer')
    runtimes=defaultdict(list); operators=defaultdict(list); selected=[]
    for index,event in enumerate(events):
        if not isinstance(event,dict) or event.get('ph')!='X':
            continue
        arguments=event.get('args',{})
        if not isinstance(arguments,dict):
            continue
        if event.get('cat') in ('cuda_runtime','cuda_driver'):
            correlation=numeric_id(arguments,'correlation')
            if correlation is not None: runtimes[correlation].append(index)
        elif event.get('cat')=='cpu_op':
            external=numeric_id(arguments,'External id')
            if external is not None: operators[(event.get('pid'),external)].append(index)
        elif event.get('cat')=='kernel' and event.get('name')==kernel:
            start,duration=event.get('ts'),event.get('dur')
            if any(type(value) not in (int,float) or not math.isfinite(value) for value in (start,duration)) or duration<0:
                raise ValueError('finite kernel timing required')
            selected.append(index)
    if offset>len(selected):
        raise ValueError('kernel offset exceeds matching event count')
    calls=[]
    for index in selected[offset:offset+8]:
        event=events[index]; arguments=event['args']
        correlation=numeric_id(arguments,'correlation')
        matches=runtimes.get(correlation,[]) if correlation is not None else []
        graph=any((numeric_id(arguments,field) or 0)>0 for field in ('graph id','graph node id'))
        call=dict(kernel_event_index=index,correlation=correlation,
            external_id=numeric_id(arguments,'External id'),runtime_event_indices=matches[:8],
            runtime_matches=len(matches),cpu_event_indices=[],cpu_operator=None,
            graph_replay_or_node=graph,ts_us=event['ts'],duration_us=event['dur'])
        if len(matches)!=1:
            call['link_status']='ambiguous_runtime' if matches else 'missing_runtime'
        else:
            runtime=events[matches[0]]
            runtime_name=runtime.get('name','')
            call['runtime_name']=runtime_name[:160] if isinstance(runtime_name,str) and runtime_name.startswith(('cuda','cu')) else None
            graph=graph or (isinstance(runtime_name,str) and 'Graph' in runtime_name)
            call['graph_replay_or_node']=graph
            external=numeric_id(runtime['args'],'External id')
            candidates=operators.get((runtime.get('pid'),external),[]) if external is not None else []
            call['cpu_event_indices']=candidates[:8]
            call['cpu_matches']=len(candidates)
            if graph:
                call['link_status']='graph_launch_only'
            elif external is not None and call['external_id'] is not None and external!=call['external_id']:
                call['link_status']='conflicting_external_ids'
            elif len(candidates)==1:
                operator=events[candidates[0]]
                if isinstance(operator.get('name'),str) and operator['name'].startswith('aten::'):
                    call['link_status']='unique_recorded_ids'
                    call['cpu_operator']=cpu_observation(operator)
                else:
                    call['link_status']='unsupported_cpu_operator'
            else:
                call['link_status']='ambiguous_cpu' if candidates else 'missing_cpu'
        calls.append(call)
    return dict(trace_sha256=trace_sha256,kernel=kernel,offset=offset,kernel_count=len(selected),
        kernel_work_us=math.fsum(events[index]['dur'] for index in selected),calls=calls,
        next_offset=offset+8 if offset+8<len(selected) else None,
        module_attribution_validated=False,stage_attribution_validated=False,exposed_time_us=None,
        scope='Recorded ID matches only; ambiguous IDs are not resolved by time proximity. '
            'Graph launches do not certify node operators/shapes. No critical path, normal timing or gain inference.')
