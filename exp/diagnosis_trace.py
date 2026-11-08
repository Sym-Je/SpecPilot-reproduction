"""CPU-only interpretation of explicit public trace stages, not kernel-name guesses."""

import argparse
from bisect import bisect_right
from collections import Counter,defaultdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from exp.diagnosis import digest,publish

STAGE=re.compile(r'^step\[(EXTEND|DRAFT|VERIFY|DECODE)(?:\s|\])')


def stage_summary(events):
    threads=defaultdict(list)
    stage_counts=Counter()
    kernels=[]
    launches=[]
    for event in events:
        if (event.get('ph')!='X' or type(event.get('dur')) not in (int,float)
                or not math.isfinite(event['dur']) or event['dur']<0):
            continue
        category=event.get('cat','')
        match=STAGE.match(event.get('name','')) if category in ('user_annotation','cpu_op','python_function') else None
        if match:
            phase=match.group(1)
            stage_counts[phase]+=1
            threads[event.get('pid'),event.get('tid')].append((event['ts'],event['ts']+event['dur'],phase))
        if category=='kernel': kernels.append(event)
        if category in ('cuda_runtime','cuda_driver') and 'correlation' in event.get('args',{}): launches.append(event)
    indexes={}
    for thread,scopes in threads.items():
        scopes.sort()
        maximum=-math.inf
        maxima=[]
        for start,end,phase in scopes:
            maximum=max(maximum,end)
            maxima.append(maximum)
        indexes[thread]=(scopes,[scope[0] for scope in scopes],maxima)
    correlations=defaultdict(list)
    ambiguous=0
    for launch in launches:
        phases=set()
        index=indexes.get((launch.get('pid'),launch.get('tid')))
        if index:
            scopes,starts,maxima=index
            position=bisect_right(starts,launch['ts'])-1
            while position>=0 and maxima[position]>=launch['ts']:
                start,end,phase=scopes[position]
                if start<=launch['ts']<end: phases.add(phase)
                position-=1
        if len(phases)>1: ambiguous+=1
        correlations[launch['args']['correlation']].append(next(iter(phases)) if len(phases)==1 else None)
    duration=defaultdict(float)
    count=Counter()
    for kernel in kernels:
        phases=correlations.get(kernel.get('args',{}).get('correlation'),[])
        unique=set(phases)
        phase=next(iter(unique)) if phases and len(unique)==1 and None not in unique else 'UNATTRIBUTED'
        duration[phase]+=kernel['dur']
        count[phase]+=1
    total=sum(duration.values())
    return dict(kernel_total_us=total,kernel_events=len(kernels),kernel_us=dict(duration),kernel_count=dict(count),
        stage_annotation_counts=dict(stage_counts),unattributed_kernel_us=duration['UNATTRIBUTED'],
        unattributed_fraction=duration['UNATTRIBUTED']/total if total else None,ambiguous_launches=ambiguous,
        method='exact step[MODE ...] annotation + same-thread CPU launch + native correlation; unknown remains unassigned',
        scope='summed kernel duration, not end-to-end wall-time share; EXTEND is input-extension annotation, not isolated pure prefill')


def analyze(private,out):
    root=json.loads((private/'manifest.json').read_text())
    records=json.loads((private/'profiles/records.json').read_text())
    reports=[]
    for record in records:
        if record['kind']!='torch-profile': continue
        summaries=[]
        for trace in record.get('traces',[]):
            path=Path(trace['path'])
            if digest(path)!=trace['sha256']:
                raise ValueError('trace differs from preserved GPU evidence')
            opener=gzip.open if path.name.endswith('.gz') else open
            with opener(path,'rt') as source: document=json.load(source)
            events=document['traceEvents'] if isinstance(document,dict) else document
            summaries.append(dict(trace_sha256=trace['sha256'],stages=stage_summary(events)))
        reports.append({key:record[key] for key in ('round','arm','language','budget','status')}|dict(traces=summaries))
    if len(reports)!=16 or any(row['status']!='captured' or not row['traces'] for row in reports):
        raise ValueError('stage interpretation requires all sixteen captured probes')
    result=dict(profile_source_pin=root['source_pin'],profile_manifest_sha256=digest(private/'manifest.json'),
        mapper_source_sha256=digest(Path(__file__)),original_trace_mapper_sha256=digest(ROOT/'exp/diagnosis.py'),
        profiles=reports,registry='post-observation diagnostic grammar, not a primary endpoint or acceptance-rule change',
        limitations=['one synthetic card, two languages, 512 input; physical repeats are not new examples',
            'instrumented kernel time excluded from formal performance','does not normalize TLV accept counters',
            'no kernel-name-based attribution; unknown and ambiguous correlations retained'])
    publish(out,result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='': raise ValueError('trace analysis must explicitly disable CUDA')
    analyze(args.private,args.out)
