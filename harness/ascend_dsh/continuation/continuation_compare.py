"""Pure host-output comparison for prospective bounded development diagnostics.

No model calls, files, sampling changes or device reads. Delivered text equality
is a finite observation, not token-level losslessness or an accuracy benchmark.
"""
import re


def text(value,budget):
    if value is None:return None
    if type(value) is not str:raise ValueError('Expected delivered text')
    budget[0]-=len(value)
    if budget[0]<0:raise ValueError('Delivered text bound exceeded')
    return value


def normalize(response):
    choices=response['choices'];usage=response['usage']
    if type(choices) is not list or len(choices)!=1:raise ValueError('One completed choice required')
    choice=choices[0];message=choice['message'];budget=[1024*1024]
    allowed={'role','content','reasoning','reasoning_content','tool_calls','refusal'}
    if type(message) is not dict or set(message)-allowed or message.get('role')!='assistant':
        raise ValueError('Unexpected delivered message schema')
    semantic={key:text(message.get(key),budget) for key in ('content','reasoning','reasoning_content','refusal')}
    calls=message.get('tool_calls') or []
    if type(calls) is not list or len(calls)>64:raise ValueError('Tool call bound/schema')
    semantic['tool_calls']=[]
    for call in calls:
        function=call['function']
        if call['type']!='function' or type(function.get('name')) is not str or type(function.get('arguments')) is not str:
            raise ValueError('Malformed function call')
        # IDs are generated protocol identifiers, not semantic function fields.
        semantic['tool_calls'].append({'type':'function','name':text(function['name'],budget),
                                       'arguments':text(function['arguments'],budget)})
    finish=choice['finish_reason']
    if type(finish) is not str or not finish:raise ValueError('Unfinished response')
    counts={'prompt_tokens':usage['prompt_tokens'],'completion_tokens':usage['completion_tokens'],
            'cached_tokens':usage['prompt_tokens_details']['cached_tokens']}
    if any(type(value) is not int or value<0 for value in counts.values()):raise ValueError('Invalid usage')
    if counts['cached_tokens']>counts['prompt_tokens']:raise ValueError('Invalid cache usage')
    return (semantic,finish,counts['completion_tokens']),counts


def compare_three_arms(off_first,off_repeat,candidate,protocol_signatures):
    report={'scope':'Finite comparison of host-delivered semantic fields, finish reasons and completion counts; no raw outputs exported',
        'capture_valid':False,'off_controls_reproducible':None,'candidate_matches_controls':None,
        'candidate_passes_finite_output_check':False,'requests':0,'token_totals':{},
        'global_accuracy_or_losslessness_certified':False,
        'limitations':['Caller must bind unchanged requests/order/model/precision/sampling/RNG protocol and genuine usage; supplied signatures alone cannot verify these.',
            'Generated tool-call IDs are ignored; function names/argument strings, content and reasoning remain exact.',
            'Finite delivered-output equality is not a global accuracy score, tensor-state proof or formal decoder correctness certificate.']}
    signatures=protocol_signatures
    if (not isinstance(signatures,(list,tuple)) or len(signatures)!=3
            or any(type(x) is not str or not re.fullmatch('[0-9a-f]{64}',x) for x in signatures)
            or len(set(signatures))!=1):
        return report|{'error':'protocol_mismatch_or_unbound'}
    arms=(off_first,off_repeat,candidate)
    if any(not isinstance(arm,(list,tuple)) for arm in arms):return report|{'error':'invalid_arm_schema'}
    if not 0<len(off_first)<=64 or len({len(arm) for arm in arms})!=1:
        return report|{'error':'empty_unmatched_or_unbounded_request_counts'}
    report['requests']=len(off_first)
    try:normalized=[[normalize(row) for row in arm] for arm in arms]
    except (KeyError,TypeError,ValueError,AttributeError):return report|{'error':'incomplete_or_invalid_delivered_capture'}
    if any(len({arm[index][1]['prompt_tokens'] for arm in normalized})!=1 for index in range(len(off_first))):
        return report|{'error':'input_token_count_mismatch'}
    if any(record[1]['cached_tokens']!=0 for arm in normalized[:2] for record in arm):
        return report|{'error':'off_controls_report_cached_tokens'}
    report['capture_valid']=True
    for name,arm in zip(('off_first','off_repeat','candidate'),normalized):
        report['token_totals'][name]={key:sum(row[1][key] for row in arm)
            for key in ('prompt_tokens','completion_tokens','cached_tokens')}
    controls=[x[0] for x in normalized[0]]==[x[0] for x in normalized[1]]
    report['off_controls_reproducible']=controls
    if controls:
        matches=[x[0] for x in normalized[0]]==[x[0] for x in normalized[2]]
        report['candidate_matches_controls']=matches
        report['candidate_passes_finite_output_check']=matches
    report['positive_cache_reuse_reported_by_usage']=report['token_totals']['candidate']['cached_tokens']>0
    return report
