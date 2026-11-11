"""Read-only historical CUDA graph provenance, with explicit recorded-ID matching."""

from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path

from harness.skill_diagnostics import bounded_input_dims,read_trace


def read_bound(reference,root):
    path=Path(reference['path'])
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('graph evidence path is outside its authorized root')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('graph evidence SHA changed')
    return json.loads(raw)


def tensor_shapes(value,path='tensor'):
    if isinstance(value,dict):
        if set(('shape','dtype','device')).issubset(value):
            shape=value['shape'];dtype=value['dtype'];device=value['device']
            if (not bounded_input_dims(shape) or any(type(size) is not int for size in shape) or
                    dtype not in ('torch.bfloat16','torch.float16','torch.float32','torch.float64','torch.int64',
                                  'torch.int32','torch.int16','torch.int8','torch.uint8','torch.bool') or
                    device not in ('cpu','cuda:0')):
                raise ValueError('unsupported captured tensor descriptor')
            return [dict(field=path,shape=shape,dtype=dtype,device=device)]
        return [row for key,item in value.items() if isinstance(key,str) for row in tensor_shapes(item,path+'.'+key)]
    if isinstance(value,list):
        return [row for index,item in enumerate(value) for row in tensor_shapes(item,path+'.'+str(index))]
    return []


def checked_exec(record,original):
    if (record['schema']!='graph-provenance-v1' or original['schema']!=record['schema'] or
            record['pid']!=original['pid'] or record['tree_sha']!=original['tree_sha'] or
            type(record['exec_id']) is not int or record['exec_id']<=0):
        raise ValueError('graph capture/exec identity differs')
    expected=json.loads(json.dumps(original))
    for operation in expected['operations']:
        for node in operation['nodes']:
            if node['node_id']>>32!=node['graph_id']:raise ValueError('unverified original node encoding')
            node.update(graph_id=record['exec_id'],node_id=(record['exec_id']<<32)|(node['node_id']&0xffffffff))
    for node in expected['unassigned_nodes']:
        if node['node_id']>>32!=node['graph_id']:raise ValueError('unverified original node encoding')
        node.update(graph_id=record['exec_id'],node_id=(record['exec_id']<<32)|(node['node_id']&0xffffffff))
    for key in ('operations','unassigned_nodes','instrumentation'):
        if record[key]!=expected[key]:raise ValueError('recorded exec mapping changed tensor/operation provenance')


def node_index(records):
    result={}
    for record in records:
        for operation in record['operations']:
            name=operation['name']
            if not isinstance(name,str) or len(name)>300 or not name.startswith(('aten::','module:sglang.','module:torch.nn.','function:sglang.','triton:sglang.')):
                raise ValueError('unregistered static operation label')
            observed=dict(operation=name,tensors=tensor_shapes(dict(inputs=operation['inputs'],outputs=operation['outputs'])))
            for node in operation['nodes']:
                key=tuple(node[field] for field in ('device','graph_id','node_id'))
                if any(type(value) is not int or value<0 for value in key) or key[1]==0 or key[2]==0 or key in result:
                    raise ValueError('invalid or duplicate graph node identity')
                result[key]=observed
    return result


def summarize(events,nodes):
    groups={};unmapped=Counter();total=0;work=[]
    for index,event in enumerate(events):
        if event.get('cat')!='kernel' or event.get('ph')!='X':continue
        duration=event.get('dur')
        if type(duration) not in (int,float) or not math.isfinite(duration) or duration<0:
            raise ValueError('invalid recorded kernel duration')
        total+=1;work.append(duration)
        arguments=event.get('args',{})
        key=tuple(arguments.get(field) for field in ('device','graph id','graph node id'))
        operation=nodes.get(key) if all(type(value) is int for value in key) else None
        if operation is None:
            unmapped[event['name']]+=1
            continue
        identity=(event['name'],json.dumps(operation,sort_keys=True))
        if identity not in groups:groups[identity]=dict(kernel=event['name'],**operation,count=0,work_us=0.,first_event_index=index)
        groups[identity]['count']+=1;groups[identity]['work_us']+=duration
    return dict(kernel_count=total,kernel_work_us=math.fsum(work),mapped_kernel_count=sum(row['count'] for row in groups.values()),
        unmatched_kernel_count=sum(unmapped.values()),unmatched_names=dict(unmapped),
        groups=sorted(groups.values(),key=lambda row:-row['work_us']),exposed_time_us=None,
        scope='Recorded node-ID association to captured descriptors; no critical-path or speedup inference.')


def export_graph_context(directory):
    directory=Path(directory).resolve()
    references=json.loads((directory/'metadata-files.json').read_text())
    authorized={row['path']:row for row in references};records=[]
    for reference in references:
        path=Path(reference['path'])
        if path.parent.name=='graph-nodes' and path.name.endswith('-exec.json'):
            record=read_bound(reference,directory)
            if record['original']['path'] not in authorized or record['original']!=authorized[record['original']['path']]:
                raise ValueError('original graph source not in recorded metadata index')
            original=read_bound(record['original'],directory);checked_exec(record,original)
            records.append(record)
    if not records:raise ValueError('no recorded graph exec mapping')
    nodes=node_index(records);traces=[]
    for reference in json.loads((directory/'traces.json').read_text()):
        path=Path(reference['path'])
        if 'runtime-profile' not in path.parts:continue
        if path.is_symlink() or not path.resolve().is_relative_to(directory):raise ValueError('trace path escaped root')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=reference['sha256']:raise ValueError('trace SHA changed')
        summary=summarize(read_trace(path),nodes)
        summary.update(source=reference)
        traces.append(summary)
    if not traces:raise ValueError('no runtime profile')
    return dict(captured_nodes=len(nodes),capture_records=len(records),traces=traces,
        graph_mapping_assumption='Recorded PyTorch2.13 exec-id high32/node low32 convention; checked against original capture records.',
        historical_reuse=True,global_floor_certified=False,profile_time_is_normal_timing=False)
