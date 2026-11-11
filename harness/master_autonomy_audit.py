"""Offline replay of Master source proposals, forecasts and tool provenance."""

import argparse
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

from exp import autonomy
from exp.master_autonomy import MasterCampaign
from harness.acceptance_evidence import estimate_conditional
from harness.master_proposal import validate_axes, validate_estimate_review, validate_proposals
from harness.master_research import MasterAccess
from harness import profile_autonomy_audit as base
from harness import skill_rsi_audit as native


KINDS = frozenset(('get_baseline_stats', 'estimate_scenario', 'search_stock', 'search_public', 'read_public'))


def replay_tool(action, answer, execution, access):
    kind = action['kind']
    if kind in ('search_public', 'read_public'):
        from harness.research_knowledge import _query, _url, audit_record
        proof = audit_record(execution)
        base.require(proof.get('valid') is True and len(proof['receipts']) == 1,
                     'public knowledge raw receipt failed independent replay')
        path = base.public_path(answer['receipt_path'], Path(execution))
        base.require(str(path) == proof['receipts'][0]['receipt_path'], 'public receipt was substituted')
        receipt = base.load(path)
        try:
            canonical = _query(action['query']) if kind == 'search_public' else _url(action['url'])
        except Exception:
            canonical = None
        base.require(receipt['operation'] == kind and receipt['input'] == canonical,
                     'public knowledge request differs from actual native action')
        expected = dict(receipt['result'], status='completed' if receipt['result']['status'] == 'ok' else 'unavailable')
    else:
        base.require(base.load(Path(execution) / 'result.json') == answer, 'Master tool execution receipt differs')
        if kind == 'get_baseline_stats':
            expected = dict(status='completed', kind=kind, statistics=access.baseline_loader(), formal_ceiling=None,
                scope='SHA-bound public stock counters; profiled timings are not normal serving performance')
        elif kind == 'estimate_scenario':
            expected = dict(status='completed', kind=kind, formal_ceiling=None,
                scenario=estimate_conditional(**{key:value for key,value in action.items() if key != 'kind'}))
        elif kind == 'search_stock':
            expected = access.search_stock(action)
        else:
            raise ValueError('unrecognized Master evidence tool')
    base.require(answer == expected, 'Master tool differs from independent source/measurement/model replay')


def audit(root):
    root = base.public_path(root)
    verified = base._audit(root, minimum_directions=1)
    pipeline = base.load(root / 'profile-campaign-result.json')
    preflight = base.public_path(pipeline['preflight_directory'], root)
    baseline_loader = lambda:MasterCampaign.baseline_stats(SimpleNamespace(preflight=preflight))
    counts = Counter()
    masters = base.master_directories(root)
    roles = [path for path in (*masters, *sorted(root.glob('direction-*')), root / 'integration', root / 'kernel') if path.is_dir()]
    for directory in roles:
        kind = base.load(directory / 'manifest.json')['role']
        access = MasterAccess(kind, {}, root / 'tools.json', root / 'skill-cache',
            baseline_loader=baseline_loader, stock=autonomy.STOCK)
        for request_path in sorted(directory.glob('tools-*/action-*/request.json')):
            action = base.load(request_path)['arguments']['action']
            returned = base.load(request_path.parent / 'response.json')
            if action.get('kind') not in KINDS or not returned['success']:
                continue
            answer = json.loads(returned['contentItems'][0]['text'])
            replay_tool(action, answer, request_path.parent / 'execution', access)
            counts[action['kind']] += 1
            if kind == 'Master':
                counts['master_' + action['kind']] += 1
            if action['kind'] in ('search_public', 'read_public'):
                counts['knowledge_' + answer['status']] += 1
    plan_path = root / 'master-plan.json'
    substantive, reviewed, directions = False, False, []
    if plan_path.is_file():
        plan = base.load(plan_path)
        base.require(set(plan) == {'assessments', 'directions'}, 'Master plan has no four-axis source proposal structure')
        active_master = masters[-1]
        validate_axes(plan['assessments'], active_master)
        directions = validate_proposals(dict(directions=plan['directions']), active_master, autonomy.STOCK)
        role, responses, origins = native.audit_role(root, active_master, allow_format_retries=True)
        base.require(any(item['value'] == plan for item in responses.values()), 'source proposal lacks native Master provenance')
        substantive = True
        if pipeline['status'] == 'research_complete':
            response = base.load(root / 'master-estimate-review.json')
            base.require(response == pipeline['master_final'], 'Master forecast review differs from final native decision')
            feedback = base.load(root / 'feedback.json') if (root / 'feedback.json').is_file() else []
            validate_estimate_review(response, {item['id']:item for item in directions}, feedback)
            reviewed = True
    elif pipeline['status'] == 'research_complete':
        raise ValueError('completed research has no source-level Master proposal')
    completed_direction = 0
    for job in pipeline['resource_state']['jobs']:
        path = root / job['name']
        request = base.load(path / 'request.json')
        if (request['mode'] == 'source-research' and '-direction-' in path.name and
                base.load(path / 'feedback.json')['status'] == 'completed'):
            completed_direction += 1
    closure = base.load(root / 'process-closure.json')
    posthoc = bool(closure.get('posthoc_observation'))
    return dict(verified, master_source_proposals_verified=substantive, proposals=len(directions),
        process_closure_mode='posthoc-maintainer-observation' if posthoc else 'parent-owned-registries',
        phase4_preopen_clearance=False,
        forecast_revision_verified=reviewed, completed_direction_source_diagnostics=completed_direction,
        proposal_execution_feedback_chain_completed=substantive and reviewed and completed_direction > 0,
        tool_replays=dict(counts), reasonable_or_effective_optimization_not_automatically_certified=True,
        scope='Master provenance, prospective estimates and real feedback only; no automatic scientific-validity or speedup claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
