"""Offline, bounded exports from completed dev traces; never launches NPUs."""
import argparse
import collections
import csv
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from prepare_baseline import OUT, ROOT, write, sha
from summarize_kernels import union_duration

EXPERIMENT = 'cont-d1-graph-mode-c32-step-attribution-cont-d1-graph-c32-prefillwindow'


def shape(value):
    first = value.strip('"').split(';')[0]
    return tuple(int(x) for x in first.split(',')) if first else ()


def query_quant(row):
    if row['Type'] != 'DynamicQuant':
        return False
    dims = shape(row['Input Shapes'])
    return row['Type'] == 'DynamicQuant' and len(dims) == 3 and dims[-2:] == (64, 128)


def paired_scale(previous, quant):
    return (previous is not None and previous['Type'] in ('Muls','Mul')
        and previous['Stream ID'] == quant['Stream ID']
        and shape(previous['Output Shapes']) == (shape(quant['Input Shapes'])[0]*64, 128)
        and Decimal(previous['Start Time(us)']) + Decimal(previous['Duration(us)']) <= Decimal(quant['Start Time(us)']))


def csv_write(path, rows, columns):
    with path.open('w', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=columns);writer.writeheader();writer.writerows(rows)


class ShardedCsv:
    def __init__(self,path,columns,limit=60*1024**2):
        self.path,self.columns,self.limit=path,columns,limit
        self.part=0;self.file=None;self._open()

    def _open(self):
        self.part+=1
        path=self.path if self.part==1 else self.path.with_name(f'{self.path.stem}.part{self.part}.csv')
        self.file=path.open('w',newline='')
        self.writer=csv.DictWriter(self.file,fieldnames=self.columns);self.writer.writeheader()

    def writerow(self,row):
        self.writer.writerow(row)
        if self.file.tell()>self.limit:
            self.file.close();self._open()

    def close(self):self.file.close()


def export_kernel_csv(source, destination):
    with source.open() as stream:
        rows=list(csv.DictReader(stream))
    streams=collections.defaultdict(list)
    for row in rows:streams[row['Stream ID']].append(row)
    pairs=[];neighbors=[];intervals=[];groups=collections.defaultdict(list)
    cols=['Stream ID','Task ID','Type','Name','Start Time(us)','Duration(us)',
          'Input Shapes','Input Data Types','Output Shapes','Output Data Types','Context ID']
    for stream, items in streams.items():
        items.sort(key=lambda r:Decimal(r['Start Time(us)']))
        for i,row in enumerate(items):
            if not query_quant(row):continue
            previous=items[i-1] if i else None
            scale=previous if paired_scale(previous,row) else None
            n=shape(row['Input Shapes'])[0];elements=n*64*128;quant_rows=n*64
            qstart=Decimal(row['Start Time(us)']);qdur=Decimal(row['Duration(us)'])
            sstart=Decimal(scale['Start Time(us)']) if scale else None
            sdur=Decimal(scale['Duration(us)']) if scale else Decimal(0)
            pair={'stream':stream,'quant_task':row['Task ID'],'query_rows':n,
                'quant_start_us':str(qstart),'quant_duration_us':str(qdur),
                'preceding_scale_task':scale['Task ID'] if scale else '',
                'scale_start_us':str(sstart) if scale else '', 'scale_duration_us':str(sdur) if scale else '',
                'paired_by_same_stream_adjacency_and_shapes':bool(scale),
                'potential_intermediate_read_write_bytes':4*elements if scale else '',
                'ideal_fused_interface_bytes':3*elements+2*quant_rows if scale else '',
                'phase':'unresolved','layer':'unresolved','valid_vs_padded_rows':'unresolved',
                'critical_path_exposure_us':'unresolved'}
            pairs.append(pair);groups[n].append(pair)
            intervals.append((qstart,qstart+qdur))
            if scale:intervals.append((sstart,sstart+sdur))
            for offset,neighbor in enumerate(items[max(0,i-6):i+13],start=max(0,i-6)-i):
                neighbors.append({'quant_task':row['Task ID'],'neighbor_offset':offset,
                                  **{k:neighbor.get(k,'') for k in cols}})
    if not pairs:raise RuntimeError('No shape-matched query quantization calls')
    csv_write(destination/'query_pairs.csv',pairs,list(pairs[0]))
    csv_write(destination/'query_neighbors.csv',neighbors,list(neighbors[0]))
    summaries=[]
    for n,items in sorted(groups.items()):
        summaries.append({'query_rows':n,'calls':len(items),
            'paired_scaling_calls':sum(x['paired_by_same_stream_adjacency_and_shapes'] for x in items),
            'scale_service_us':str(sum(Decimal(x['scale_duration_us'] or '0') for x in items)),
            'quant_service_us':str(sum(Decimal(x['quant_duration_us']) for x in items)),
            'conditional_removable_payload_bytes':sum(x['potential_intermediate_read_write_bytes'] or 0 for x in items),
            'scope':'shape/adjacency matched; source linkage and phase unresolved; service is not speedup'})
    csv_write(destination/'query_shape_summary.csv',summaries,list(summaries[0]))
    span=max(Decimal(x['Start Time(us)'])+Decimal(x['Duration(us)']) for x in rows)-min(Decimal(x['Start Time(us)']) for x in rows)
    return {'query_quant_calls':len(pairs),'paired_scaling_calls':sum(bool(x['preceding_scale_task']) for x in pairs),
            'affected_operator_union_us':str(union_duration(intervals)), 'rank_kernel_span_us':str(span),
            'source_sha256':sha(source), 'shape_summary':summaries}


def export_timeline(source,destination):
    import ijson
    columns=['ph','name','cat','pid','tid','ts','dur','id','scope','binding_point','correlation_args']
    counts=collections.Counter(); total=0
    paths={kind:destination/(kind+'.csv') for kind in ('flows','event_markers','phase_markers')}
    writers={k:ShardedCsv(p,columns) for k,p in paths.items()}
    try:
        opener=gzip.open if source.suffix=='.gz' else open
        with opener(source,'rb') as f:
            for event in ijson.items(f,'item'):
                total+=1;name=event.get('name','');lower=name.lower();kind=None
                if event.get('ph') in ('s','f','t'):kind='flows'
                elif ('event' in lower and ('record' in lower or 'wait' in lower)) or 'synchronize' in lower:kind='event_markers'
                elif any(s in lower for s in ('profilerstep','prefill','decode','verify','draft')):kind='phase_markers'
                if not kind:continue
                args={k:v for k,v in event.get('args',{}).items()
                    if any(s in k.lower() for s in ('task','stream','correlation','sequence','step','model','external'))
                    and isinstance(v,(str,int,float,Decimal))}
                row={k:event.get(k,'') for k in columns[:-3]}
                row.update(scope=event.get('scope',''),binding_point=event.get('bp',''),
                           correlation_args=json.dumps(args,default=str))
                writers[kind].writerow(row);counts[kind]+=1
    finally:
        for writer in writers.values():writer.close()
    return {'timeline_sha256':sha(source),'events_scanned':total,'exported_event_counts':dict(counts),
            'scope':'Raw observed flow/marker records; flow categories may be CPU-device launch correlations, not NPU dependency edges. No DAG or phase assignment is inferred.'}


def main(resume=False):
    os.nice(10)
    area=OUT/'research/profile-dependency-export';area.mkdir(parents=True,exist_ok=True)
    state={'status':'exporting','pid':os.getpid(),'started_epoch':time.time(),'source_sha256':sha(__file__),'ranks':[]}
    if (area/'state.json').exists():
        write(area/f'previous-state-{time.time_ns()}.json',json.loads((area/'state.json').read_text()))
    write(area/'state.json',state)
    folder=OUT/'experiments'/EXPERIMENT
    original=json.loads((folder/'state.json').read_text())
    quality=json.loads((folder/'profile-quality.json').read_text())
    assert original['status']=='complete' and original['baseline_restored']
    assert quality['all_eight_ranks_complete'] and not quality['warnings']
    sources=sorted((folder/'traces').rglob('kernel_details.csv'));assert len(sources)==8
    shared={EXPERIMENT:{}}
    try:
        for source in sources:
            destination=source.parent/'dependency_export'
            timeline=source.parent/'trace_view.json.gz'
            if not timeline.exists():timeline=source.parent/'trace_view.json'
            manifest=destination/'manifest.json'
            if manifest.exists():
                row=json.loads(manifest.read_text())
                assert row['source_sha256']==sha(source) and row['timeline_sha256']==sha(timeline)
            else:
                if destination.exists():
                    destination.rename(destination.with_name('dependency_export-incomplete-'+str(time.time_ns())))
                destination.mkdir()
                row={'rank_directory':source.parent.parent.name,**export_kernel_csv(source,destination)}
                row.update(export_timeline(timeline,destination))
                write(manifest,row)
            for p in sorted(destination.glob('*.csv')):
                shared[EXPERIMENT][str(p.relative_to(folder/'traces'))]=sha(p)
            state['ranks'].append(row);write(area/'state.json',state)
            print(json.dumps({'rank':row['rank_directory'],'query_calls':row['query_quant_calls'],'timeline_events':row['events_scanned']}),flush=True)
        state.update(status='complete',completed_epoch=time.time(),quality_source_sha256=sha(folder/'profile-quality.json'),
            artifact_scope='Read-only completed dev artifacts, no NPU launch or model modification',
            limitations=['Shapes, exact timestamps and same-stream ordering are exposed; tensor storage identity is not established.',
                'Input/context tensor values and valid/padded row counts are not in these CSVs.',
                'Flow and phase markers are exported verbatim where present, without claiming complete step/layer/phase or critical-path coverage.',
                'Affected operator union is diagnostic service, not an achievable speedup or proof of exposed time.'])
        write(area/'state.json',state)
        write(OUT/'research/profile-export-access.json',{'shared_profile_csvs':shared,'summary':state,'summary_sha256':sha(area/'state.json')})
        if resume:
            current=json.loads((OUT/'research/state.json').read_text())
            assert current['status']=='needs_harness_capability' and current['next_round']==3 and not current['validation_opened']
            with (OUT/'research/resume-after-profile-capability.log').open('ab') as log:
                process=subprocess.Popen([str(ROOT/'.dsh-venv/bin/python'),str(OUT/'continue_research.py'),'--resume'],cwd=OUT,
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            import psutil
            write(OUT/'research/supervisor.json',{'pid':process.pid,'birth':psutil.Process(process.pid).create_time(),
                'started_epoch':time.time(),'reason':'Completed existing-profile export; resume scientific Master review'})
    except BaseException as error:
        state.update(status='needs_attention',error=repr(error));write(area/'state.json',state);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resume-research',action='store_true')
    main(parser.parse_args().resume_research)
