"""Offline GPU request inspection. No model isolation claim or submission authority."""

import hashlib
from pathlib import Path
import re

from agents.exploration import object_sha
from harness.experiment_executor import local_path


def fields(value,expected):
    if not isinstance(value,dict) or set(value)!=set(expected):
        raise ValueError('unknown or missing request fields')


def text(value,limit=4096):
    if not isinstance(value,str) or not value.strip() or len(value.encode())>limit:
        raise ValueError('bounded nonempty text required')


def hex_digest(value,length):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None


def inspect_file(work,entry,python=False):
    fields(entry,('path','sha256'))
    if not hex_digest(entry['sha256'],64):raise ValueError('invalid file digest')
    path=local_path(work,entry['path'])
    if str(Path(entry['path']))!=entry['path']:raise ValueError('noncanonical request path')
    if not path.is_file() or (python and path.suffix!='.py'):
        raise ValueError('existing regular file with expected type required')
    limit=32768 if python else 1048576
    with path.open('rb') as stream:payload=stream.read(limit+1)
    if len(payload)>limit:raise ValueError('request file exceeds offline inspection limit')
    digest=hashlib.sha256(payload).hexdigest()
    if digest!=entry['sha256']:raise ValueError('request file digest mismatch')
    return dict(path=entry['path'],sha256=digest,bytes=len(payload))


def inspect_request(work,request,current_pin):
    fields(request,('schema','direction_id','hypothesis','source_pin','script','acceptance',
        'inputs','resources','proposed_image','stop_condition'))
    if request['schema']!='autonomy-gpu-request-v1':raise ValueError('invalid request schema')
    direction=request['direction_id']
    if not isinstance(direction,str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}',direction) or direction=='master':
        raise ValueError('direction-owned request required')
    text(request['hypothesis']);text(request['stop_condition'])
    if not hex_digest(current_pin,40) or request['source_pin']!=current_pin:
        raise ValueError('request does not match broker source pin')
    resources=request['resources']
    fields(resources,('nodes','gpus_per_node','gpu_type','wall_minutes','memory_gib'))
    for key,limit in (('nodes',1),('gpus_per_node',8),('wall_minutes',60),('memory_gib',256)):
        if type(resources[key]) is not int or not 1<=resources[key]<=limit:
            raise ValueError('resource outside single-node request interface bounds, not an authorized budget')
    if resources['gpu_type']!='h100':raise ValueError('only H100 requests are in scope')
    image=request['proposed_image']
    if image is not None and (not isinstance(image,str) or len(image)>512 or
            re.fullmatch('[A-Za-z0-9][A-Za-z0-9./:_-]*@sha256:[0-9a-f]{64}',image) is None):
        raise ValueError('image proposal must be an immutable digest; proposal is not approval')
    inputs=request['inputs']
    if not isinstance(inputs,list) or len(inputs)>16:raise ValueError('bounded input file list required')
    files=[inspect_file(work,request['script'],python=True),inspect_file(work,request['acceptance'],python=True)]
    files.extend(inspect_file(work,entry) for entry in inputs)
    if len({row['path'] for row in files})!=len(files):raise ValueError('duplicate request files')
    total=resources['nodes']*resources['gpus_per_node']
    return dict(schema='autonomy-gpu-preflight-v1',status='blocked',direction_id=direction,
        request_sha256=object_sha(request),source_pin=current_pin,files=files,
        requested_total_gpus=total,requested_gpu_minutes=total*resources['wall_minutes'],
        submission_allowed=False,submitted=False,process_started=False,gpu_test_passed=None,
        job_uuid=None,gpu_submissions=0,source_freeze_verified=False,controller_handoff_eligible=False,
        blockers=['backend_tool_boundary_unenforced','stage_gpu_authorization_missing',
            'gpu_executor_not_connected','execution_source_not_frozen'],
        scope='offline point-in-time file checks only; no execution, resource approval or controller acceptance')
