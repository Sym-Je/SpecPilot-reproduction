from pathlib import Path
import json


def export_observations(directory):
    """Postprocess bounded worker receipts, outside the serving processes."""
    import csv
    from prepare_baseline import sha
    directory=Path(directory)
    rows=[];sources=[]
    for path in sorted((directory/'work-metadata').glob('worker-*.json')):
        if path.is_symlink() or path.stat().st_size>65536:raise ValueError('Invalid metadata receipt')
        data=json.loads(path.read_text());records=data['records']
        if len(records)>4:raise ValueError('Diagnostic record bound exceeded')
        sources.append({'path':path.name,'sha256':sha(path),'records':len(records)})
        rows.extend(records)
    ranks={r.get('rank') for r in rows}
    complete=ranks==set(range(8)) and all(sum(r.get('rank')==rank for r in rows)<=4 for rank in ranks)
    destination=directory/'traces/cpu_work_metadata.csv'
    if rows:
        with destination.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
            writer.writerows({k:json.dumps(v) if isinstance(v,list) else v for k,v in row.items()} for row in rows)
    return {'status':'complete' if complete else 'partial','rank_count':len(ranks),'records':len(rows),
            'receipts':sources,'csv_path':'cpu_work_metadata.csv' if rows else None,
            'coverage':'CPU scheduler/metadata work only; selected tiling, device-task identity and dependency exposure unresolved'}
