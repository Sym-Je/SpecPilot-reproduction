"""Reproducible offline aggregation of observed caching-OFF descriptors only."""
import collections
import json
from prepare_baseline import OUT,ROOT,write,sha


def main():
    folder=OUT/'experiments/capability-cache-init-off-plan-v1'
    report=json.loads((folder/'cache-initialization-summary.json').read_text())
    assert report['structural_capture_complete'] and report['rank_count']==8
    records=[(p,json.loads(p.read_text())) for p in sorted((folder/'cache-init-metadata').glob('*.json'))]
    worker_path,worker=max(((p,d) for p,d in records if d['stage']=='worker_initialized' and d['data']['distributed_rank']==0),key=lambda item:item[1]['ordinal'])
    manager_path,manager=next((p,d) for p,d in records if d['stage']=='manager_initialized')
    groups=[]
    for group in worker['data']['groups']:
        spec=group['spec'];leaves=[row['spec'] for row in spec.get('layer_specs',[])] or [spec]
        counts=collections.Counter()
        for leaf in leaves:
            geometry={key:leaf['fields'].get(key) for key in ('block_size','storage_block_size','tokens_per_state','sliding_window','dtype','page_size_bytes','prefix_cacheable','participates_in_prefix_caching','non_causal','non_causal_multi_token_decode')}
            counts[json.dumps(geometry,sort_keys=True)]+=1
        groups.append({'group_index':group['group_index'],'layer_count':len(group['layers']),
            'representative_model_layer':group['layers'][0] if group['layers'] else None,
            'spec_class':spec['class'],'is_eagle_group':group.get('is_eagle_group'),
            'declared_geometry_variants':[dict(json.loads(key),metadata_layers=value) for key,value in counts.items()]})
    names={'active_coordinator':'patch/platform/patch_kv_cache_coordinator.py',
           'block_size_resolver':'patch/platform/patch_kv_cache_utils.py'}
    source_root=ROOT/'.venv/lib/python3.12/site-packages/vllm_ascend'
    facts={'origin':'trusted offline descriptor aggregation; not model discovery or an optimization result',
        'derivation_source_sha256':sha(__file__),'experiment_id':folder.name,
        'structural_capture_complete':True,'rank_count':8,
        'worker_source_sha256':sha(worker_path),'manager_source_sha256':sha(manager_path),
        'observed_configuration':'Caching OFF, TP8/DP1/EP8, W8A8, DSpark K7',
        'rank0_cache_config':worker['data']['config'],'groups':groups,
        'actual_cpu_manager_metadata':manager['data'],
        'active_source_receipts':{key:{'tree':'vllm_ascend','path':name,'sha256':sha(source_root/name)} for key,name in names.items()},
        'enabled_state_restoration_validated':False,'full_prefix_capability_ready':False,
        'limitations':['OFF scheduler/hash geometry is not observed enabled-cache hit alignment. Enabling may select different hash geometry; use the actual Ascend resolver/coordinator.',
            'Planned pool blocks cannot be summed as independent per-group physical capacity; ownership and live residency remain unknown.',
            'No request contents, request/token IDs or tensor values. Model layer names are architecture metadata.',
            'No generation or cache hits were tested; request telemetry, eviction/reset and trusted OFF/ON comparison remain absent.',
            'Confirm restoration separately in the final trusted experiment and recovery receipts.']}
    assert len(groups)==6 and sum(row['layer_count'] for row in groups)==170
    write(OUT/'research/cache-init-group-facts.json',facts)
    print(json.dumps({'groups':len(groups),'rank_count':8,'source_pinned':True,'enabled_support_validated':False}))


if __name__=='__main__':main()
