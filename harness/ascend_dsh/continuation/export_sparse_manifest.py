"""Offline exact-symbol kernel-manifest join; no suffix guessing or device use."""
import collections
import csv
from decimal import Decimal
import json
from pathlib import Path
from prepare_baseline import OUT,ROOT,write,sha
from completed_profile_access import register

EXPERIMENT='cont-d4-sparse-attention-runtime-work-cpu-work-two-step-v1'


def save_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    folder=OUT/'experiments'/EXPERIMENT
    state=json.loads((folder/'state.json').read_text())
    assert state['status']=='complete' and state['baseline_restored']
    manifest_root=ROOT/'.venv/lib/python3.12/site-packages/vllm_ascend/_cann_ops_custom/vendors/custom_transformer/op_impl/ai_core/tbe/kernel/ascend910b/sparse_attn_sharedkv'
    symbols={};manifest_receipts=[]
    for path in sorted(manifest_root.glob('*.json')):
        data=json.loads(path.read_text());binary=path.parent/(data['binFileName']+data['binFileSuffix'])
        receipt={'manifest_name':path.name,'manifest_sha256':sha(path),
                 'binary_sha256_now':sha(binary) if binary.exists() else None,
                 'binary_sha256_declared':data.get('sha256')}
        receipt['binary_matches_declared_now']=receipt['binary_sha256_now']==receipt['binary_sha256_declared']
        manifest_receipts.append(receipt)
        for kernel in data.get('kernelList',[]):
            symbols[kernel['kernelName']]={**receipt,'tiling_key':kernel['tilingKey'],'kernel_type':kernel['kernelType']}
    rank_receipts=[]
    for source in sorted((folder/'traces').rglob('task_time.csv')):
        details=source.with_name('kernel_details.csv');lookup=collections.defaultdict(list)
        with details.open() as f:
            for row in csv.DictReader(f):
                if row['Type']=='SparseAttnSharedkv':lookup[(row['Stream ID'],row['Task ID'])].append(row)
        rows=[]
        with source.open() as f:
            for task in csv.DictReader(f):
                name=task['kernel_name']
                if not name.startswith('SparseAttnSharedkv_'):continue
                manifest=symbols.get(name,{})
                candidates=lookup[(task['stream_id'],task['task_id'])]
                match=candidates[0] if len(candidates)==1 else None
                exact=bool(match and Decimal(match['Start Time(us)'])==Decimal(task['task_start(us)']))
                rows.append({'device_id':task['Device_id'],'stream_id':task['stream_id'],'task_id':task['task_id'],
                    'start_us':task['task_start(us)'].strip(),'duration_us':task['task_time(us)'],
                    'executed_symbol':name,'manifest_exact_symbol_match':bool(manifest),
                    'manifest_tiling_key':manifest.get('tiling_key'),'manifest_sha256':manifest.get('manifest_sha256'),
                    'binary_matches_declared_now':manifest.get('binary_matches_declared_now'),
                    'detail_join_unique_and_same_timestamp':exact,'input_shapes':match['Input Shapes'] if exact else None,
                    'input_dtypes':match['Input Data Types'] if exact else None,
                    'runtime_tile_dimensions':None,'layer_id':None,'executed_phase':None,
                    'scope':'Exact executed symbol -> current on-disk kernelList tilingKey. Does not prove launch-time binary bytes, runtime tile dimensions or CPU-step linkage.'})
        assert rows
        destination=source.with_name('sparse_manifest_calls.csv');save_csv(destination,rows)
        groups=collections.defaultdict(list)
        for row in rows:groups[(row['manifest_tiling_key'],row['executed_symbol'],row['input_shapes'])].append(row)
        summary=[]
        for (key,symbol,shape),items in groups.items():
            summary.append({'tiling_key_from_manifest':key,'executed_symbol':symbol,'input_shapes':shape,
                'calls':len(items),'duration_sum_us':str(sum(Decimal(r['duration_us']) for r in items)),
                'exact_detail_joins':sum(r['detail_join_unique_and_same_timestamp'] for r in items),
                'scope':'Diagnostic service only; task symbol selection is not runtime tile-dimension or critical-path coverage.'})
        save_csv(source.with_name('sparse_manifest_summary.csv'),summary)
        rank_receipts.append({'rank':source.parent.parent.name,'task_source_sha256':sha(source),'detail_source_sha256':sha(details),
            'calls':len(rows),'manifest_matches':sum(r['manifest_exact_symbol_match'] for r in rows),'exact_detail_joins':sum(r['detail_join_unique_and_same_timestamp'] for r in rows)})
    assert len(rank_receipts)==8
    missing=[{'field':name,'status':'unresolved','reason':reason} for name,reason in [
        ('launch_time_device_binary_bytes','Current manifest and binary bytes are hashed, but no launch-time .o identity receipt was captured.'),
        ('runtime_tile_dimensions','Manifest tilingKey identifies template selection, not runtime block/loop/workspace parameters.'),
        ('attention_layer_and_executed_phase','CPU preparation counters are not launch-linked layer/phase identifiers.'),
        ('valid_compressed_selections','No GPU selection tensor values were recorded; a shape/cap is not the valid selection count.'),
        ('unique_required_KV_rows','Requires actual selected rows and supported cache/reuse evidence.'),
        ('device_padding','CPU actual/input counts agree in observed builders; no direct per-device invocation validity map.'),
        ('genuine_dependency_DAG','Recorded host enqueue/dequeue flow is not a complete device dependency graph.'),
        ('cross_rank_timestamp_alignment','No explicit clock-offset calibration receipt was collected.')]]
    save_csv(folder/'traces/unavailable_fields.csv',missing)
    responses=json.loads((folder/'profile-responses.json').read_text());workload=json.loads((folder/'profile-workload.json').read_text())
    assert len(responses)==workload['request_count'] and all(isinstance(r.get('usage'),dict) for r in responses)
    metrics={'requests':len(responses),'prompt_tokens':sum(r['usage']['prompt_tokens'] for r in responses),
        'completion_tokens':sum(r['usage']['completion_tokens'] for r in responses),
        'completion_tokens_at_configured_cap':sum(r['usage']['completion_tokens']==workload['output_cap'] for r in responses),
        'configured_output_cap':workload['output_cap']}
    save_csv(folder/'traces/replay_token_summary.csv',[{'metric':k,'value':v,'scope':'Whole diagnostic replay; tokens at cap do not by themselves establish finish_reason or unprofiled throughput.'} for k,v in metrics.items()])
    write(folder/'sparse-manifest-export.json',{'status':'complete','origin':'trusted read-only offline join; no new NPU execution',
        'ranks':rank_receipts,'current_manifest_receipts':manifest_receipts,'replay_token_totals':metrics,
        'unavailable_fields':missing})
    shared=register(folder)
    print(json.dumps({'status':'complete','ranks':rank_receipts,'replay_token_totals':metrics,'shared_csvs':len(shared)}))


if __name__=='__main__':main()
