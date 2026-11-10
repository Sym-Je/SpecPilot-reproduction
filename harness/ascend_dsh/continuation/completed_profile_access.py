"""Publish explicit read-only hashes for completed development profiles."""
import json
from pathlib import Path
from prepare_baseline import OUT,write,sha

NAMES={'kernel_details.csv','kernel_type_summary.csv','operator_counter_by_shape.csv',
       'cpu_work_metadata.csv','workload_activity_summary.csv','task_time.csv','step_trace_time.csv',
       'sparse_manifest_calls.csv','sparse_manifest_summary.csv','unavailable_fields.csv','replay_token_summary.csv'}


def register(folder):
    folder=Path(folder).resolve()
    if folder.parent!=(OUT/'experiments').resolve():raise ValueError('Outside trusted experiments')
    state=json.loads((folder/'state.json').read_text());quality=json.loads((folder/'profile-quality.json').read_text())
    if state['status']!='complete' or not state.get('baseline_restored') or state['request'].get('split')!='dev':
        raise ValueError('Only restored complete dev experiments may be shared')
    if not quality['all_eight_ranks_complete'] or quality['warnings']:raise ValueError('Incomplete profile')
    shared={str(p.relative_to(folder/'traces')):sha(p) for p in (folder/'traces').rglob('*.csv')
            if p.name in NAMES and not p.is_symlink() and p.stat().st_size<=64*1024**2}
    path=OUT/'research/profile-export-access.json'
    data=json.loads(path.read_text()) if path.exists() else {'shared_profile_csvs':{}}
    data['shared_profile_csvs'][folder.name]=shared
    data.setdefault('additional_completed_profiles',{})[folder.name]={
        'status':'complete','baseline_restored':True,'rank_count':8,
        'cpu_work_metadata':state.get('profile',{}).get('cpu_work_metadata'),
        'usage_csv':'replay_token_summary.csv' if (folder/'traces/replay_token_summary.csv').exists() else None,
        'missing_field_csv':'unavailable_fields.csv' if (folder/'traces/unavailable_fields.csv').exists() else None,
        'scope':'Attributed development observations; raw joins and on-disk manifest decoding do not prove complete execution provenance.'}
    write(path,data)
    return shared
