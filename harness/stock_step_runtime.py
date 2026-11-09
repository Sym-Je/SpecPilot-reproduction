"""Opt-in private stock observations; never changes tensors or native counters."""

import hashlib
import json
import os
from pathlib import Path
import threading
import time


_LOCK=threading.Lock()
_SEQUENCES={}
_RUNTIME_SHA=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _directory():
    value=os.environ.get('SPECPILOT_STEP_TRACE_DIR')
    if not value:
        return None
    directory=Path(value)
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError('observer requires an existing absolute private directory')
    if directory.stat().st_mode & 0o077:
        raise ValueError('observer directory must be private')
    return directory


def _emit(directory,request,kind,**values):
    input_ids=list(request.origin_input_ids)
    checksum=hashlib.sha256(json.dumps(input_ids,separators=(',',':')).encode()).hexdigest()
    pid=os.getpid()
    path=directory/f'{pid}.jsonl'
    with _LOCK:
        key=(str(directory),pid)
        sequence=_SEQUENCES.get(key,0)
        if sequence==0 and path.exists():
            raise ValueError('observer refuses an existing process stream')
        row=dict(schema='stock-step-v1',pid=pid,sequence=sequence,time_ns=time.time_ns(),
                 rid=request.rid,input_sha256=checksum,kind=kind,runtime_path=str(Path(__file__).resolve()),
                 runtime_sha256=_RUNTIME_SHA,tree_sha=os.environ.get('SP_TREE_SHA'),**values)
        payload=(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n').encode()
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        try:
            position=0
            while position<len(payload):
                written=os.write(descriptor,payload[position:])
                if written<=0:
                    raise OSError('observer stream write made no progress')
                position+=written
        finally:
            os.close(descriptor)
        _SEQUENCES[key]=sequence+1


def observe_verify(batch,candidates,target_pred,accepted,commit_lens,bonus,out_tokens):
    directory=_directory()
    if directory is None:
        return
    if target_pred is None or any(request.grammar is not None for request in batch.reqs):
        raise ValueError('observer supports only greedy linear stock without grammar')
    arrays=[tensor.detach().cpu().tolist() for tensor in
            (candidates,target_pred,accepted,commit_lens,bonus,out_tokens)]
    if any(len(array)!=len(batch.reqs) for array in arrays):
        raise ValueError('observer request/tensor batch mismatch')
    for index,request in enumerate(batch.reqs):
        candidate,prediction,correct,length,extra,committed=[array[index] for array in arrays]
        _emit(directory,request,'verify',candidates=candidate,target_pred=prediction,
            accepted=correct,commit_len=length,bonus=extra,committed_ids=committed[:length])


def observe_commit(request,phase):
    directory=_directory()
    if directory is None:
        return
    if request.grammar is not None:
        raise ValueError('observer does not support grammar')
    parameters=request.sampling_params
    _emit(directory,request,'commit',phase=phase,output_ids=list(request.output_ids),
        finished_len=request.finished_len,
        finish_reason=request.finished_reason.to_json() if request.finished_reason is not None else None,
        verify_ct=request.spec_verify_ct,correct_drafts=request.spec_num_correct_drafts,
        histogram=list(request.spec_correct_drafts_histogram),max_new_tokens=parameters.max_new_tokens,
        temperature=parameters.temperature,top_k=parameters.top_k,ignore_eos=parameters.ignore_eos,
        eos_ids=sorted(request.eos_token_ids or []),stop_ids=sorted(parameters.stop_token_ids or []),
        stop_strings=bool(parameters.stop_strs or parameters.stop_regex_strs))
