"""Independent diagnostic coverage review; never manufactures missing ceiling factors."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from controller.scored_forcing import read_reference
from exp.diagnosis import digest
from exp.stock_profile import profile_state
from harness.ceiling_build import RUNTIME,check_bundle
from harness.step_replay import read_stream


def review(directory):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    request=json.loads(Path(manifest['request_path']).read_text())
    origin=request['original_manifest']
    if digest(origin['path'])!=origin['sha256']:
        raise ValueError('original public-dev manifest identity changed')
    original=json.loads(Path(origin['path']).read_text())
    if original['requests']!=manifest['requests'] or original['stock_spec']!=manifest['stock_spec']:
        raise ValueError('new capture did not use the frozen original stock protocol')
    result=json.loads((directory/'result.json').read_text())
    built=check_bundle(directory/'bundle')
    observed_rows=0
    for number in (1,2):
        root=directory/'enabled'/f'round-{number:02d}'
        for reference in json.loads((root/'streams.json').read_text()):
            for row in read_stream(reference,directory):
                if (row['runtime_path']!=str(directory/'bundle/engine'/RUNTIME) or
                        row['runtime_sha256']!=built['files'][RUNTIME] or row['tree_sha']!=built['observer_tree_sha']):
                    raise ValueError('loaded observer provenance differs from frozen bundle')
                observed_rows+=1
    classes=defaultdict(lambda:dict(count=0,kernel_sum_us=0.,floor_us=None))
    total=busy=qualified=floor=0.
    stages=defaultdict(float)
    for trace in result['profiles']:
        observation=trace['observation']
        total+=observation['kernel_sum_us']
        busy+=observation['single_device_busy_us'] or 0.
        qualified+=observation['nominal_matmul_floors']['observed_kernel_sum_us']
        floor+=observation['nominal_matmul_floors']['nominal_floor_sum_us']
        for stage,value in observation['stages']['kernel_us'].items():
            stages[stage]+=value
        for name,row in trace['classes'].items():
            classes[name]['count']+=row['count']
            classes[name]['kernel_sum_us']+=row['kernel_sum_us']
    for row in classes.values():
        row['summed_work_share']=row['kernel_sum_us']/total
    profiles=json.loads((directory/'profiles.json').read_text())
    windows=[]
    for sample in profiles['records']:
        root=directory/'profiles'/f'round-{sample["round"]:02d}'
        stop=read_reference(sample['stop_control'],directory)
        state=profile_state(stop,sample.get('stop_state_log'),root)
        if not ((state['http_success'] and 'stop_error' not in sample) or state['explicitly_not_running'] or
                state['native_inactive_log_verified']):
            raise ValueError('profiler inactive state not independently proved')
        trace_rows=[row for row in result['profiles'] if row['id']==sample['id'] and row['round']==sample['round']]
        annotations=sum(row['observation']['stages']['stage_annotation_counts'].get('VERIFY',0) for row in trace_rows)
        count=sample['row']['spec_verify_ct']
        windows.append(dict(id=sample['id'],round=sample['round'],committed_verify_steps=count,
            verify_annotations=annotations,verify_count_covered=count<=annotations<=count+1,
            termination=sample['row']['finish_reason'],same_output_as_unprofiled=True))
    measured=defaultdict(list)
    for mode in ('disabled','enabled'):
        for number in (1,2):
            root=directory/mode/f'round-{number:02d}'
            for line in (root/'pairs.jsonl').read_text().splitlines():
                pair=json.loads(line)
                row=pair['a']
                measured[row['id']].append(dict(latency_ms=row['latency_ms'],tokens=row['tokens'],
                    reported_verify_steps=row['spec_verify_ct'],gpu=row['gpu_uuid']))
    tau=result['conditional_replay']
    return dict(schema='phase0-review-v1',evidence_result_sha256=digest(directory/'result.json'),
        runtime_provenance_rows_verified=observed_rows,
        diagnostic_stage_completed=True,full_paper_phase0_completed=False,
        conditional_replay=tau,
        conditional_best_first_gain={budget:value/tau['stock_tau'] for budget,value in tau['best_first_tau'].items()},
        conditional_oracle_gain=tau['oracle_tau']/tau['stock_tau'],
        full_request_profile_count_check=dict(passed=sum(row['verify_count_covered'] for row in windows),total=len(windows),windows=windows,
            caveat='annotation/committed-counter coverage with at most one overlap tail; not per-kernel step mapping'),
        kernel_classes=dict(sorted(classes.items())),kernel_sum_ms=total/1000,gpu_busy_sum_ms=busy/1000,
        stage_work_shares={name:value/total for name,value in sorted(stages.items())},
        stage_work_aggregation='pooled summed kernel work over the declared request/repeat set; not wall-time fractions or equal-request means',
        nominal_mm_subset=dict(work_coverage=qualified/total,floor_sum_ms=floor/1000,
            cold_tensor_scenario_only=True,measured_dram_bytes=False,not_a_full_pass_floor=True),
        unprofiled_stock_requests={name:dict(rows=len(values),median_latency_ms=statistics.median(row['latency_ms'] for row in values),
            tokens=[row['tokens'] for row in values],reported_verify_steps=[row['reported_verify_steps'] for row in values]) for name,values in measured.items()},
        factor_coverage=result['factor_coverage'],
        missing=['best runtime node budget with node-dependent costs',
                 'independent live tree/target consistency beyond frozen stock-continuation replay',
                 'all-class byte/FLOP workload including recurrent state, attention and graph-hidden operations',
                 'matched uninstrumented step wall/GPU timing with overlap and prefill accounting'],
        conclusion='bounded algorithmic acceptance surface and full-request kernel observations, not complete ceiling or autonomous optimization evidence')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(review(args.directory),sort_keys=True,allow_nan=False))


if __name__=='__main__':
    main()
