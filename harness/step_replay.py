"""CPU reconstruction of observed stock chains, not a controller or best-tree oracle."""

from collections import deque
import hashlib
import json
from pathlib import Path

from controller.http_transport import sha_ids
from controller.scored_forcing import read_reference


def integer(value):
    if type(value) is not int or value<0:
        raise ValueError('nonnegative integer required')
    return value


def tokens(values,*,empty=False):
    if not isinstance(values,list) or (not values and not empty):
        raise ValueError('token list required')
    return [integer(value) for value in values]


def read_stream(reference,root):
    path=Path(reference['path']).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('observer stream escapes evidence root')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=reference['sha256']:
        raise ValueError('observer stream checksum mismatch')
    events=[json.loads(line) for line in payload.decode().splitlines()]
    if not events or any(row['sequence']!=index or row['pid']!=events[0]['pid']
                         for index,row in enumerate(events)):
        raise ValueError('incomplete process stream')
    return events


def verify_block(event):
    candidates=tokens(event['candidates'])
    predictions=tokens(event['target_pred'])
    if len(candidates)!=8 or len(predictions)!=8:
        raise ValueError('only the frozen block8 linear path is supported')
    accepted=0
    for candidate,prediction in zip(candidates[1:],predictions[:-1]):
        if candidate!=prediction:
            break
        accepted+=1
    bonus=predictions[accepted]
    committed=candidates[1:accepted+1]+[bonus]
    if (integer(event['accepted'])!=accepted or integer(event['bonus'])!=bonus or
            integer(event['commit_len'])!=len(committed) or tokens(event['committed_ids'])!=committed):
        raise ValueError('observed acceptance differs from independent greedy reconstruction')
    return accepted,committed


def replay_request(events,*,expected_output,expected_input_sha=None):
    if not events:
        raise ValueError('missing step observations')
    expected_output=tokens(expected_output)
    identity=(events[0]['pid'],events[0]['rid'],events[0]['input_sha256'])
    if expected_input_sha is not None and identity[2]!=expected_input_sha:
        raise ValueError('observer request input differs from native HTTP')
    previous=-1
    pending=deque()
    output=[]
    histogram=[0]*8
    steps=correct=observed=0
    first=final=None
    for event in events:
        if (event.get('schema')!='stock-step-v1' or
                (event['pid'],event['rid'],event['input_sha256'])!=identity or
                integer(event['sequence'])<=previous):
            raise ValueError('observer identity/order changed')
        previous=event['sequence']
        if event['kind']=='verify':
            accepted,committed=verify_block(event)
            pending.append((event,accepted,committed))
            observed+=1
            continue
        if event['kind']!='commit' or final is not None:
            raise ValueError('unexpected commit or post-finish mutation')
        actual=tokens(event['output_ids'])
        if event['phase']=='prefill':
            if first is not None or len(actual)!=1:
                raise ValueError('one initial prefill token required')
            first=event
            output=actual
        elif event['phase']=='decode':
            if first is None or not pending:
                raise ValueError('decode commit lacks its observed verification')
            worker,accepted,committed=pending.popleft()
            if worker['candidates'][0]!=output[-1]:
                raise ValueError('verification does not continue the actual committed prefix')
            output+=committed
            steps+=1
            correct+=accepted
            histogram[accepted]+=1
        else:
            raise ValueError('unknown scheduler phase')
        native_hist=tokens(event['histogram'],empty=True)
        if (len(native_hist)>8 or actual!=output or integer(event['verify_ct'])!=steps or
                integer(event['correct_drafts'])!=correct or native_hist+[0]*(8-len(native_hist))!=histogram):
            raise ValueError('native commit/counters differ from replayed path')
        for field in ('max_new_tokens','top_k','ignore_eos','eos_ids','stop_ids','stop_strings'):
            if event[field]!=first[field]:
                raise ValueError('request termination/sampling changed')
        if event['top_k']!=1 or event['stop_strings'] or event['ignore_eos'] is not False:
            raise ValueError('only natural greedy token termination is supported')
        if event['finish_reason'] is not None:
            final=event
        elif event['finished_len'] is not None:
            raise ValueError('unfinished request unexpectedly clipped')
    if first is None or final is None:
        raise ValueError('missing initial or final scheduler observation')
    cap=integer(final['max_new_tokens'])
    if cap<=0:
        raise ValueError('empty generation cap')
    stop_ids=set(tokens(final['eos_ids'],empty=True)+tokens(final['stop_ids'],empty=True))
    stop=next((index+1 for index,token in enumerate(output) if token in stop_ids),None)
    if stop is not None and stop<=cap:
        end=stop
        if final['finish_reason']!=dict(type='stop',matched=output[stop-1]):
            raise ValueError('native token-stop differs from the first recorded stop token')
    else:
        end=cap
        if final['finish_reason']!=dict(type='length',length=cap) or len(output)<cap:
            raise ValueError('native length-stop differs from the recorded token cap')
    if final['finished_len']!=end or output[:end]!=expected_output:
        raise ValueError('replayed final output differs from native HTTP')
    previous_token=output[-1]
    for worker,accepted,committed in pending:
        if worker['candidates'][0]!=previous_token:
            raise ValueError('uncommitted overlap tail does not continue the prior worker output')
        previous_token=committed[-1]
    return dict(replay_passed=True,seed_tokens=len(first['output_ids']),observed_verify_steps=observed,
        committed_verify_steps=steps,uncommitted_verify_steps=len(pending),correct_drafts=correct,
        untrimmed_output_tokens=len(output),output_tokens=end,tail_clip_tokens=len(output)-end,
        output_sha256=sha_ids(expected_output),tau_best_available=False,
        scope='observed greedy stock linear chain; no best-tree oracle, losslessness or promotion')


def replay_bound(events,generation,*,root):
    packet=read_reference(generation,root)
    body,response=packet.get('request',{}),packet.get('response',{})
    if (packet.get('http_status')!=200 or body.get('sampling_params')!=
            dict(temperature=0.0,top_k=1,max_new_tokens=2048) or
            any(event['rid']!=body.get('rid') for event in events)):
        raise ValueError('step stream is not bound to the native greedy generation')
    output=response['output_ids']
    report=replay_request(events,expected_output=output,expected_input_sha=sha_ids(body['input_ids']))
    final=next(event for event in reversed(events) if event['kind']=='commit')
    metadata=response['meta_info']
    if (metadata['completion_tokens']!=report['output_tokens'] or metadata['spec_verify_ct']!=report['committed_verify_steps'] or
            metadata['spec_num_correct_drafts']!=report['correct_drafts'] or
            metadata['finish_reason']!=final['finish_reason'] or
            metadata['spec_correct_drafts_histogram']!=final['histogram']):
        raise ValueError('observed request final counters differ from native HTTP')
    return report
