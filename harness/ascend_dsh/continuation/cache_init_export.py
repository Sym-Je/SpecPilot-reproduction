"""Bounded export for caching-OFF initialization capture, without generation."""
import hashlib
import json
from pathlib import Path
import psutil
import stat
from prepare_baseline import write


def incomplete(value):
    if isinstance(value,dict):
        return value.get('truncated') is True or any(incomplete(v) for v in value.values())
    if isinstance(value,list):return any(incomplete(v) for v in value)
    return False


def analyze_snapshots(records):
    failures=[];workers={};cores=[];managers=[]
    for row in records:
        stage=row.get('stage','');data=row.get('data',{})
        if stage not in ('worker_initialized','core_initialized','manager_initialized'):
            failures.append('Unexpected observation stage')
        if incomplete(data) or stage=='overflow' or stage.endswith('_observer_error'):
            failures.append('Truncated/failed observation')
        if stage=='worker_initialized':
            rank=data.get('distributed_rank')
            if type(rank) is not int or rank not in range(8):failures.append('Invalid distributed rank');continue
            if rank in workers and workers[rank].get('pid')!=row.get('pid'):
                failures.append('Multiple worker processes for one rank')
            if rank not in workers or row.get('ordinal',-1)>workers[rank].get('ordinal',-1):workers[rank]=row
        elif stage=='core_initialized':cores.append(row)
        elif stage=='manager_initialized':managers.append(row)
    if set(workers)!=set(range(8)):failures.append('Missing rank manifests')
    if len(cores)!=1 or len(managers)!=1:failures.append('Require one core and one manager manifest')
    digests=set();group_counts=[]
    for rank,row in sorted(workers.items()):
        data=row['data'];groups=data.get('groups',[]);group_counts.append(len(groups))
        if data.get('distributed_world_size')!=8:failures.append('Unexpected world size')
        if data.get('effective_worker_config',{}).get('cache',{}).get('enable_prefix_caching') is not False:
            failures.append('Phase1 requires effective caching OFF')
        if not groups:failures.append('Missing groups')
        plan={key:data.get(key) for key in ('config','groups','planned_backings')}
        digests.add(hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest())
    if len(digests)>1:failures.append('Rank plans differ')
    if len(cores)==1:
        core=cores[0]['data']
        if core.get('effective_core_config',{}).get('cache',{}).get('enable_prefix_caching') is not False:
            failures.append('Core caching flag unresolved or enabled')
        if group_counts and len(core.get('plan',{}).get('groups',[]))!=group_counts[0]:
            failures.append('Core/worker group count differs')
        core_blocks=core.get('plan',{}).get('config',{}).get('num_blocks')
        if type(core_blocks) is not int or core_blocks<=0 or any(
                row['data'].get('config',{}).get('num_blocks')!=core_blocks for row in workers.values()):
            failures.append('Final core/worker block count unresolved or differs')
        core_layers={name for group in core.get('plan',{}).get('groups',[]) for name in group.get('layers',[])}
        if any({name for group in row['data'].get('groups',[]) for name in group.get('layers',[])}!=core_layers
                for row in workers.values()):failures.append('Core/worker layer coverage differs')
    if len(managers)==1:
        manager=managers[0]['data']
        if manager.get('enable_caching') is not False:failures.append('Manager caching flag unresolved or enabled')
        if group_counts and manager.get('group_count')!=group_counts[0]:failures.append('Manager/worker group count differs')
    return {'scope':'Initialization metadata only on unchanged caching-OFF baseline; no research generation submitted',
        'structural_capture_complete':not failures,'failures':sorted(set(failures)),
        'rank_count':len(workers),'group_counts_by_rank':group_counts,'rank_plan_sha256':sorted(digests),
        'effective_prefix_caching':False if not failures else None,
        'enabled_state_restoration_validated':False,'runner_submitted_generation_requests':0,
        'core_manifests':len(cores),'manager_manifests':len(managers),
        'limitations':['Structural completeness is not complete cache support or runtime correctness.',
            'Kernel tensor layout, actual ownership/residency, eviction and reset behavior remain unresolved.',
            'No request telemetry, token-equivalence result, throughput or speedup is produced.']}


def export_initialization(directory):
    directory=Path(directory);area=directory/'cache-init-metadata'
    assert not area.is_symlink() and area.resolve().parent==directory.resolve()
    assert stat.S_IMODE(area.stat().st_mode)==0o700,'Private precreated metadata directory required'
    paths=sorted(area.glob('*.json'))
    assert len(paths)<=40 and sum(p.stat().st_size for p in paths)<=8*1024**2,'Metadata bounds exceeded'
    owner=json.loads((directory/'candidate-service/owner.json').read_text());process=psutil.Process(owner['pid'])
    assert process.create_time()==owner['birth'],'Candidate PID identity mismatch'
    pids={p.pid for p in process.children(recursive=True)}|{process.pid}
    records=[];sources=[]
    for path in paths:
        assert not path.is_symlink() and path.stat().st_size<=256*1024
        raw=path.read_bytes();row=json.loads(raw)
        assert row.get('schema')=='prefix-cache-init-metadata/v1' and row.get('pid') in pids,'Unexpected metadata source'
        observed=psutil.Process(row['pid'])
        assert path.stat().st_uid==observed.uids().effective and stat.S_IMODE(path.stat().st_mode)==0o600
        assert path.stat().st_mtime>=owner['birth'] and path.name==f"metadata-{row['pid']}-{row['ordinal']}.json"
        records.append(row);sources.append({'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    report=analyze_snapshots(records);report['source_files']=sources
    report['process_manifest']=[{'pid':pid,'birth':psutil.Process(pid).create_time(),
        'stages':sorted({row['stage'] for row in records if row['pid']==pid}),
        'ranks':sorted({row['data']['distributed_rank'] for row in records if row['pid']==pid
            and row.get('stage')=='worker_initialized'})} for pid in sorted({row['pid'] for row in records})]
    write(directory/'cache-initialization-summary.json',report)
    return report
