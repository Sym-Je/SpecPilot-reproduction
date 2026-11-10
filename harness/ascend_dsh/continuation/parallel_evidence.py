"""Bounded, explicitly attributed supervisor and parallel-research feedback."""
import json
from pathlib import Path

from prepare_baseline import sha


def shared_updates(root, *, analysis_only=False):
    if analysis_only:
        return {}  # Independent analysts receive only their frozen brief.
    root = Path(root)
    result = {'scope': 'Attributed shared evidence; proposals are not measured gains or independent rediscoveries.'}
    review = root / 'research/supervisor-d2-attribution-review.json'
    if review.is_file() and review.stat().st_size <= 16384:
        data = json.loads(review.read_text())
        result['supervisor_review'] = {'source_sha256': sha(review),
            'origin': data['origin'], 'corrections': data['corrections']}
    reports = []
    for path in sorted((root / 'research/parallel/roles').glob('*/result.json'))[-6:]:
        if path.parent.name.startswith('parallel-master-'):
            continue
        if path.is_symlink() or path.stat().st_size > 32768:
            continue
        record = json.loads(path.read_text())
        if record.get('status') != 'complete':
            continue
        report = record['report']
        reports.append({'role': path.parent.name, 'source_sha256': sha(path),
                        'measured_gain': False, 'report': report})
    result['parallel_reports'] = reports
    return result
