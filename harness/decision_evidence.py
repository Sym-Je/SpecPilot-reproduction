"""Explicit public-stock evidence for a CPU-only decision rehearsal."""

import json
from pathlib import Path
from types import SimpleNamespace

from exp.master_autonomy import MasterCampaign
from exp.phase4_run import reference
from harness.engine_research import save


def load(path):
    return json.loads(Path(path).read_text())


def prepare(root, repository):
    root,repository=Path(root).resolve(),Path(repository).resolve()
    previous=repository/'logs/master-proposal-20261111-a01'
    readiness=previous/'sp-masterprop-20261111-a01-preflight01'
    diagnostic=previous/'sp-masterprop-20261111-a01-direction-d1-01'
    baseline=MasterCampaign.baseline_stats(SimpleNamespace(preflight=readiness))
    if baseline!=load(previous/'baseline-statistics-independent.json'):
        raise ValueError('historical stock counters differ from independent native replay')
    result=load(diagnostic/'feedback.json')
    if result.get('status')!='completed' or result.get('controller_accepted') is not False:
        raise ValueError('the rehearsal requires the actual nonpromoted public diagnostic')
    patch=load(diagnostic/'patch.json')
    inputs=root/'inputs'
    inputs.mkdir(mode=0o700)
    save(inputs/'baseline.json',baseline)
    save(inputs/'stock-profile.json',load(previous/'initial-profile-input.json'))
    save(inputs/'tools.json',load(previous/'tools.json'))
    candidate=dict(option_id=patch['option_id'],paths=[edit['path'] for edit in patch['edits']],
        mechanism='Historical stock accept/bonus scalar-prefix loop replaced with vector first-mismatch reduction',
        source=reference(diagnostic/'patch.json'),
        provenance='explicitly shared previous public patch; reuse, not an independent discovery')
    public=dict(baseline=dict(aggregate=baseline['aggregate'],unknowns=baseline['unknowns'],
            source=reference(inputs/'baseline.json'),historical_reuse=True),
        profile=dict(shape_status='unknown',stage_attribution_validated=False,normal_step_wall_cost='unknown',
            evidence_id_for_bbuf='stock',source=reference(inputs/'stock-profile.json'),historical_reuse=True),
        historical_candidate=candidate)
    public['historical-candidate']=public.pop('historical_candidate')
    selected=('status','geomean','lower','upper','n_pairs','n_requests','rounds','lossless_verified','controller_accepted','scope')
    feedback={key:result[key] for key in selected}
    feedback.update(option_id=patch['option_id'],provenance='actual previous public diagnostic; not a new measurement')
    evidence=dict(initial=public,historical_feedback=feedback,feedback_source=reference(diagnostic/'feedback.json'),
        previous_request=reference(diagnostic/'request.json'),previous_audit=reference(previous/'closeout-audit-03.json'),
        baseline=reference(inputs/'baseline.json'),profile=reference(inputs/'stock-profile.json'),tools=reference(inputs/'tools.json'))
    save(root/'evidence.json',evidence)
    return evidence


def verify(root):
    root=Path(root).resolve()
    evidence=load(root/'evidence.json')
    for key in ('feedback_source','previous_request','previous_audit','baseline','profile','tools'):
        expected=evidence[key]
        path=Path(expected['path'])
        if path.is_symlink() or reference(path)!=expected:
            raise ValueError('frozen public evidence changed: '+key)
    result=load(evidence['feedback_source']['path'])
    for key,value in evidence['historical_feedback'].items():
        if key not in ('option_id','provenance') and result.get(key)!=value:
            raise ValueError('historical feedback differs from the original actual measurement')
    candidate=evidence['initial']['historical-candidate']
    if reference(candidate['source']['path'])!=candidate['source']:
        raise ValueError('historical public patch identity changed')
    if load(evidence['baseline']['path'])['aggregate']!=evidence['initial']['baseline']['aggregate']:
        raise ValueError('baseline opportunity map was altered')
    return evidence
