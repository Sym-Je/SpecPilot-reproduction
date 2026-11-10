"""Bounded best-first replay on recorded candidates and a frozen target continuation."""

from collections import deque
import heapq
import math

from harness.step_replay import replay_request, verify_block


BUDGETS=(8,16,32,64,128)


def log_probabilities(candidate_ids,scores):
    if not isinstance(candidate_ids,list) or not 1<=len(candidate_ids)<=16:
        raise ValueError('bounded lattice depth required')
    width=len(candidate_ids[0])
    if not 1<=width<=16 or len(scores)!=len(candidate_ids):
        raise ValueError('bounded consistent lattice required')
    result=[]
    for candidates,rows in zip(candidate_ids,scores):
        if (len(candidates)!=width or len(set(candidates))!=width or
                any(type(value) is not int or value<0 for value in candidates) or len(rows)!=width):
            raise ValueError('invalid candidates or predecessor width')
        normalized=[]
        for row in rows:
            if len(row)!=width or any(type(value) not in (int,float) or not math.isfinite(value) for value in row):
                raise ValueError('invalid conditional scores')
            maximum=max(row)
            normalizer=math.log(sum(math.exp(value-maximum) for value in row))
            normalized.append([value-maximum-normalizer for value in row])
        result.append(normalized)
    return result


def best_first(candidate_ids,scores,budget):
    if type(budget) is not int or not 1<=budget<=256:
        raise ValueError('node budget includes the anchor and must be 1..256')
    probabilities=log_probabilities(candidate_ids,scores)
    queue=[(-value,(index,)) for index,value in enumerate(probabilities[0][0])]
    heapq.heapify(queue)
    selected=[]
    while queue and len(selected)<budget-1:
        negative,path=heapq.heappop(queue)
        selected.append(path)
        if len(path)<len(probabilities):
            for child,value in enumerate(probabilities[len(path)][path[-1]]):
                heapq.heappush(queue,(negative-value,path+(child,)))
    return selected


def replay_lattice(candidate_ids,scores,target,chain,budgets=BUDGETS):
    probabilities=log_probabilities(candidate_ids,scores)
    depth=len(candidate_ids)
    if len(target)<depth+1 or len(chain)!=depth:
        raise ValueError('complete target continuation plus bonus required')
    previous=0
    for candidates,rows,token in zip(candidate_ids,scores,chain):
        chosen=max(range(len(candidates)),key=lambda index:rows[previous][index])
        if token!=candidates[chosen]:
            raise ValueError('lattice greedy path differs from actual stock proposals')
        previous=chosen
    correct=0
    for actual,expected in zip(chain,target):
        if actual!=expected:
            break
        correct+=1
    oracle=[]
    for candidates,token in zip(candidate_ids,target):
        if token not in candidates:
            break
        oracle.append(candidates.index(token))
    values={}
    for budget in budgets:
        selected=set(best_first(candidate_ids,scores,budget))
        matched=0
        for length in range(1,len(oracle)+1):
            if tuple(oracle[:length]) not in selected:
                break
            matched=length
        values[str(budget)]=matched+1
    return dict(stock_tau=correct+1,oracle_tau=len(oracle)+1,best_first_tau=values,
                depth=depth,width=len(probabilities[0]))


def replay_events(events,output_ids):
    linear=[row for row in events if row['kind']!='lattice']
    chain_report=replay_request(linear,expected_output=output_ids)
    lattices={}
    previous=None
    for row in events:
        if row['kind']=='verify':
            previous=row
        elif row['kind']=='lattice':
            if previous is None or previous['sequence'] in lattices or row['sequence']!=previous['sequence']+1:
                raise ValueError('lattice/verify association changed')
            if any(row[key]!=previous[key] for key in ('pid','rid','input_sha256','tree_sha')):
                raise ValueError('lattice identity changed')
            lattices[previous['sequence']]=row
            previous=None
    verifies=[row for row in linear if row['kind']=='verify']
    if len(lattices)!=len(verifies):
        raise ValueError('missing or duplicated lattice')
    for verify in verifies:
        lattice=lattices[verify['sequence']]
        candidate_ids,scores=lattice['candidate_ids'],lattice['scores']
        log_probabilities(candidate_ids,scores)
        if len(candidate_ids)!=7 or any(len(values)!=16 for values in candidate_ids):
            raise ValueError('real replay requires frozen block8/top16')
        previous=0
        for candidates,values,token in zip(candidate_ids,scores,verify['candidates'][1:]):
            selected=max(range(16),key=lambda index:values[previous][index])
            if candidates[selected]!=token:
                raise ValueError('recorded lattice did not produce its associated stock chain')
            previous=selected
    pending=deque()
    reconstructed=[]
    committed=[]
    for row in linear:
        if row['kind']=='verify':
            pending.append(row)
        elif row['phase']=='prefill':
            reconstructed=list(row['output_ids'])
        else:
            verify=pending.popleft()
            offset=len(reconstructed)
            _,tokens=verify_block(verify)
            reconstructed.extend(tokens)
            committed.append((verify,offset))
    rows=[]
    excluded=0
    for verify,offset in committed:
        lattice=lattices[verify['sequence']]
        if len(lattice['candidate_ids'])!=7 or any(len(values)!=16 for values in lattice['candidate_ids']):
            raise ValueError('real replay requires frozen block8/top16')
        target=output_ids[offset:offset+8]
        if len(target)<8:
            excluded+=1
            continue
        accepted,_=verify_block(verify)
        if target[:accepted+1]!=verify['committed_ids']:
            raise ValueError('recorded target continuation disagrees with verified stock prefix')
        report=replay_lattice(lattice['candidate_ids'],lattice['scores'],target,verify['candidates'][1:])
        if report['stock_tau']!=accepted+1:
            raise ValueError('offline stock acceptance differs')
        rows.append(report)
    if not rows:
        raise ValueError('no complete live target continuations')
    return dict(linear=chain_report,eligible_steps=len(rows),tail_steps_excluded=excluded,
        stock_tau=sum(row['stock_tau'] for row in rows)/len(rows),
        oracle_tau=sum(row['oracle_tau'] for row in rows)/len(rows),
        best_first_tau={str(budget):sum(row['best_first_tau'][str(budget)] for row in rows)/len(rows) for budget in BUDGETS},
        scope='conditional block8/top16 lattice on recorded live-stock greedy continuations; not actual tree execution, best runtime budget or global oracle',
        live_tree_verified=False,best_runtime_budget_known=False)
