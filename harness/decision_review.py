"""Explicit engineering closeout, not a substitute for a normal research or scientific gate."""

import json
from pathlib import Path
import time

from controller.phase4_final import trusted_metadata, validate_shutdown
from exp.phase4_run import reference
from harness.decision_evidence import load
from harness.skill_rsi_audit import audit_role


def check_delivery(prompt,reports):
    context=json.JSONDecoder().raw_decode(prompt[prompt.index('{'):])[0]
    if context.get('direction_feedback')!=reports:
        raise ValueError('terminal Master did not actually receive the exact Direction reports')
    return context


def verify(root):
    root=Path(root)
    original=load(root/'result.json')
    if original.get('error')!='ValueError: CPU stage model/wall allocation exhausted; no GPU or implicit budget extension':
        raise ValueError('not the preserved scheduler stop')
    reports=[dict(source=reference(path),value=load(path)) for path in sorted(root.glob('direction-*/turn-*-response.json'))]
    if not reports:raise ValueError('no native Direction report')
    last=root/'final-review-03'
    context=check_delivery(load(last/'master/turn-01-request.json')['prompt'],reports)
    own=[load(path) for path in sorted((root/'master').glob('turn-*-response.json'))]
    if context.get('own_prior_responses')!=own:
        raise ValueError('Master own history differs')
    counts=dict(original['counters']);processes=0;reviews=[]
    for name in ('final-review','final-review-02','final-review-03'):
        directory=root/name
        wire=[json.loads(line)['message'] for line in (directory/'master/wire.jsonl').read_text().splitlines()]
        if (sum(row.get('method')=='turn/start' for row in wire)!=1 or
                any(row.get('method')=='item/tool/call' for row in wire)):
            raise ValueError('administrative review launched extra turns or tools')
        counts['model_turns']+=1
        counts['usage_updates']+=sum(row.get('method')=='thread/tokenUsage/updated' for row in wire)
        if name!='final-review-02':
            role,responses,origins=audit_role(directory,directory/'master',action_limits={1:0})
            if len(responses)!=1 or origins:raise ValueError('invalid review authorship')
            reviews.append(role)
        elif list((directory/'master').glob('turn-*-native.json')):
            raise ValueError('interrupted review falsely relabeled complete')
        path=directory/'processes/shutdown-registry.json'
        registry=trusted_metadata(reference(path),path.stat().st_uid)
        processes+=validate_shutdown(registry,broker_uid=path.stat().st_uid,opened_unix=time.time())
    result=load(last/'result.json')
    if (result['counters']!=counts or result['answer'].get('decision')!='stop' or
            result['answer'].get('gpu_request') is not None):
        raise ValueError('terminal review decision or cumulative charges differ')
    if any(counts[key]>maximum for key,maximum in (('actions',240),('cpu_runs',32),('model_turns',16),('usage_updates',512))):
        raise ValueError('terminal review exceeded cumulative research counters')
    resource=load(Path(load(root/'recovery.json')['prior_root'])/'resource-state.json')
    if resource['jobs'] or result['finished']>resource['started']+resource['wall_seconds']:
        raise ValueError('administrative review exceeded the overall authorization')
    return dict(master_review_delivered=True,master_decision=result['answer'],counters=counts,
        completed_reviews=2,interrupted_reviews=1,verified_processes=processes,
        original_scheduler_failure_preserved=True,normal_pipeline_completion=False,
        scientific_optimization_completed=False,gpu_submissions=0)
