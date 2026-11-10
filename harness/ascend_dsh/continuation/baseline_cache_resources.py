"""Extract rounded numeric observations from the restored baseline startup log.

No device calls, source/configuration changes, request contents or enabled-APC
certification. Logged allocation figures are not a complete peak-HBM bound.
"""
import hashlib
import json
from pathlib import Path
import re
from prepare_baseline import OUT,write,sha


def parse_resources(text):
    pattern=re.compile(r'\(Worker_TP(\d+)_EP(\d+) pid=\d+\).*?Actual usage: '
        r'([\d.]+) GiB for weights, ([\d.]+) GiB for peak activation, '
        r'([\d.]+) GiB for non-torch memory, ([\d.]+) GiB for NPU graph memory\.'
        r'.*?Current KV cache memory: ([\d.]+) GiB\. After warmup: '
        r'torch reserved memory ([\d.]+) GiB, torch allocated memory ([\d.]+) GiB\.')
    names=('weights','peak_activation','non_torch','graph','kv_cache','torch_reserved','torch_allocated')
    rows={}
    for match in pattern.finditer(text):
        tp,ep=map(int,match.group(1,2))
        if not 0<=tp<8 or ep!=tp:continue
        rows[tp]={'tp_rank':tp,'ep_rank':ep,**{name+'_gib_rounded':float(v) for name,v in zip(names,match.groups()[2:])}}
    capacities=re.findall(r'NPU KV cache size: ([\d,]+) tokens',text)
    flags=re.findall(r"(?:enable_prefix_caching['\"]?\s*[:=]\s*)(True|False)",text)
    resolved_flags=set(flags)
    return {'scope':'Logged startup observations of unchanged TP8/DP1/EP8 baseline; all GiB figures rounded by stock logger, not raw allocator sizes',
        'all_eight_resource_rows_present':set(rows)==set(range(8)),
        'rank_rows':[rows[k] for k in sorted(rows)],
        'logged_prefix_caching_enabled':resolved_flags=={'True'} if len(resolved_flags)==1 else None,
        'logged_cache_capacity_tokens':int(capacities[-1].replace(',','')) if capacities else None,
        'cache_group_specs':None,'effective_hit_alignment':None,'enabled_cache_support':None,
        'limitations':['Cache capacity is a stock aggregate log value, not a per-group physical capacity or residency proof.',
            'Startup resource rows are historical observations; loading/graph transients and alternate topology peaks are not bounded.',
            'Disabled-cache metadata cannot establish enabled-cache restoration or numerical correctness.',
            'No prompts, request IDs, token IDs, raw log lines or tensor contents are exported.']}


def main():
    folder=OUT/'experiments/cont-d4-sparse-attention-runtime-work-cpu-work-two-step-v1/restored-baseline'
    log=folder/'server.log';raw=log.read_bytes()
    snapshot=OUT/'research/baseline-cache-log-snapshot.txt';snapshot.write_bytes(raw)
    result=parse_resources(raw.decode(errors='replace'))
    result.update(origin='trusted passive log extraction; no new NPU execution',source_log_sha256=hashlib.sha256(raw).hexdigest(),
                  source_snapshot_bytes=len(raw),source_scope='Captured immutable byte extent of a live append-only startup/service log',
                  source_owner_receipt_sha256=sha(folder/'owner.json'))
    write(OUT/'research/baseline-cache-resources.json',result)
    print(json.dumps({'all_eight_resource_rows_present':result['all_eight_resource_rows_present'],
        'rank_count':len(result['rank_rows']),'logged_prefix_caching_enabled':result['logged_prefix_caching_enabled'],
        'logged_cache_capacity_tokens':result['logged_cache_capacity_tokens']}))


if __name__=='__main__':main()
