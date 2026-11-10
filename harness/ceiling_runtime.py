"""Opt-in lattice capture, deliberately excluded from performance measurements."""

import os

def observe_lattice(batch,candidates,target_pred,accepted,commit_lens,bonus,out_tokens,lattice_ids,lattice_scores):
    if not os.environ.get('SPECPILOT_CEILING_TRACE_DIR'):
        return
    from sglang.srt.speculative.specpilot_step_observer import _directory, _emit, observe_verify
    directory=_directory()
    if directory is None or os.environ['SPECPILOT_CEILING_TRACE_DIR']!=str(directory):
        raise ValueError('lattice and chain observations require the same private directory')
    observe_verify(batch,candidates,target_pred,accepted,commit_lens,bonus,out_tokens)
    ids=lattice_ids.detach().cpu().tolist()
    scores=lattice_scores.detach().float().cpu().tolist()
    if len(ids)!=len(batch.reqs) or len(scores)!=len(ids):
        raise ValueError('lattice batch mismatch')
    for index,request in enumerate(batch.reqs):
        _emit(directory,request,'lattice',candidate_ids=ids[index],scores=scores[index])
