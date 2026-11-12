"""Bind a Master dev-review request to a completed direction source experiment."""

import json
from pathlib import Path
import re

from exp.source_resource import execute
from harness.engine_research import save
from harness.source_candidate import file_sha


def request_gate(root, decision, feedbacks, budget, pin, freeze, *, executor=execute, job_prefix='sp-source-20261110-a01'):
    name = decision.get('request_directory')
    if not isinstance(name, str):
        raise ValueError('Master must identify a completed source experiment')
    original = Path(name).absolute()
    eligible = [row for row in feedbacks if row.get('status') == 'completed' and
        row.get('protocol') == 'source-option-research-v1' and not row.get('preflight') and
        row.get('request_directory') == str(original)]
    if len(eligible) != 1 or original.parent != root or not re.fullmatch(re.escape(job_prefix)+'-[0-9]{2}', original.name):
        raise ValueError('controller review must reference this stage actual measured source candidate')
    request = json.loads((original / 'request.json').read_text())
    if request['patch_sha256'] != file_sha(original / 'patch.json'):
        raise ValueError('measured patch changed before controller request')
    gate = root / (original.name + '-gate')
    gate.mkdir(mode=0o700)
    (gate / 'patch.json').write_bytes((original / 'patch.json').read_bytes())
    for name in ('cpu-receipt.json', 'self-check.py'):
        (gate / name).write_bytes((original / name).read_bytes())
    request.update(mode='source-controller', source_pin=pin,
        action=dict(request['action'], per_suite=6, max_new_tokens=2048),
        diagnostic_request=str(original), diagnostic_feedback_sha256=file_sha(original / 'feedback.json'))
    save(gate / 'request.json', request)
    if job_prefix.startswith('sp-treeadapter-'):
        from exp.tree_adapter import submit_gate
        executor=submit_gate
    return executor(gate, freeze(gate), budget)
