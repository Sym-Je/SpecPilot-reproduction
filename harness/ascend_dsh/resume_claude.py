"""One explicit recovery of a completed, output-truncated Claude direction.

No failed NPU experiment is rerun here, no allocation or spend is reset. The
original native sessions resume; Master still owns further scientific choices.
"""
import argparse
import fcntl
import json
import os
import re
import time

from dsh_call import call
from gpt_handoff import continue_research, experiment_receipts, read, MASTER_SCHEMA
from prepare_baseline import OUT, write, sha
from research_driver import SYSTEM, parse_answer, patch_for


def transient_stream_stall(record):
    if record.get('result', {}).get('finish_reason') != 'error': return False
    ends = [e for e in record['result'].get('events', []) if e.get('type') == 'turn/end']
    error = ends[-1].get('data', {}).get('reason', {}).get('error', {}) if ends else {}
    return error.get('code') == 'SERVER' and 'stopped sending for 60s' in error.get('message', '')


def latest_call(role, since=0):
    records = []
    for path in (OUT / 'research/calls').glob(role + '-*.json'):
        record = read(path)
        if record.get('session_id') == role and record.get('started_epoch', 0) >= since:
            records.append(record)
    assert records, 'No matching native call receipt'
    return max(records, key=lambda x: x['started_epoch'])


def cached_answer(text):
    try:
        return parse_answer(text), None
    except ValueError:
        # A completed response closed its root object one brace too early,
        # followed by additional root members. One syntactic deletion only;
        # no value changes, JSON guessing or model-generated repair.
        matches = list(re.finditer(r'(?m)^\{', text))
        assert len(matches) == 1, 'Ambiguous cached JSON boundary'
        start = matches[0].start(); candidate = text[start:]
        head, end = json.JSONDecoder().raw_decode(candidate)
        assert isinstance(head, dict) and candidate[end - 1] == '}'
        assert candidate[end:].startswith(',"experiments":'), 'Unsupported cached JSON repair'
        def unique(pairs):
            value = {}
            for key, item in pairs:
                assert key not in value, 'Duplicate JSON member'
                value[key] = item
            return value
        value = json.loads(candidate[:end - 1] + candidate[end:], object_pairs_hook=unique)
        assert all(value[k] == v for k, v in head.items()), 'Repair changed a value'
        assert all(k in value for k in ('status', 'hypothesis', 'cost_floor', 'experiments',
                                        'conclusion', 'candidate_config', 'limitations'))
        return value, {'operation': 'remove_one_premature_root_closing_brace', 'offset': start + end - 1,
                       'scientific_values_modified': False}


def invoke(role, mode, prompt):
    system = SYSTEM.replace('$500 task ceiling', '$200 total Claude ceiling')
    prompt += '\nKeep the final JSON concise (at most 1500 words). Return a final answer before the output cap. If tool allocation is exhausted, summarize existing evidence without further tool requests.'
    for attempt in range(3):
        started = time.time()
        try:
            response, receipt = call(role, prompt, system, max_tokens=8192,
                                     patch=patch_for(role, mode), deadline_seconds=10800)
            break
        except AssertionError:
            record = latest_call(role, since=started)
            if attempt == 2 or not transient_stream_stall(record): raise
            # Resume durable native history; do not replay the large original
            # prompt or reset broker actions, experiments or model reservations.
            path = OUT / 'research/roles' / role / 'transport-retries.jsonl'
            with path.open('a') as f:
                f.write(json.dumps({'epoch': time.time(), 'failed_call_id': record['call_id'],
                    'retry': attempt + 1, 'reason': 'upstream_stream_idle_timeout',
                    'charged_reservation_retained': True}) + '\n'); f.flush(); os.fsync(f.fileno())
            prompt = 'The upstream response stream was interrupted. Continue your unfinished turn using the existing session history and tool receipts. Do not repeat submitted experiments or reset any allocation. Return the requested concise final JSON.'
            time.sleep(3)
    value = parse_answer(response)
    write(OUT / 'research/roles' / role / ('answer-recovered-' + str(time.time_ns()) + '.json'),
          {'answer': value, 'call_id': receipt['call_id']})
    return value


def run(cached_call=None, resume_upstream=False, review_incomplete_stop=False):
    with (OUT / 'research/driver.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read(OUT / 'research/state.json')
        assert state['status'] == 'stopped_with_error'
        assert not (cached_call and resume_upstream)
        if review_incomplete_stop:
            assert cached_call and state['active_role'] == 'ctrip-master' and len(state['rounds']) < 3
            assert not any(x.get('request', {}).get('mode') == 'profile' and x.get('status') == 'complete'
                for x in (read(p) for p in (OUT / 'experiments').glob('*/state.json')))
        cleanup_recovery = state['error'] == 'AssertionError: Experiment cleanup not complete'
        if resume_upstream:
            assert state['error'] == 'AssertionError: error' and transient_stream_stall(latest_call(state['active_role']))
        elif cached_call:
            assert state['error'].startswith('JSONDecodeError:') or cleanup_recovery
        else:
            assert state['error'] == 'AssertionError: max-tokens'
        assert state['validation_opened'] is False and not (OUT / 'candidate-freeze.json').exists()
        assert not read(OUT / 'billing/state.json').get('budget_exhausted')
        experiment_receipts(state['active_role'])
        checkpoint_name = ('claude-coverage-checkpoint.json' if review_incomplete_stop else
                           'claude-upstream-checkpoint.json' if resume_upstream else
                           'claude-cleanup-checkpoint.json' if cleanup_recovery else
                           'claude-format-checkpoint.json' if cached_call else 'claude-truncated-checkpoint.json')
        checkpoint = OUT / 'research' / checkpoint_name
        assert not checkpoint.exists(), 'Recovery is explicit, never an unbounded retry loop'
        write(checkpoint, state)
        def resume_invoke(role, mode, prompt):
            nonlocal cached_call, resume_upstream, review_incomplete_stop
            if review_incomplete_stop:
                path = OUT / 'research/calls' / cached_call
                assert path.parent == OUT / 'research/calls' and path.name == cached_call and mode == 'master'
                record = read(path)
                assert record['session_id'] == role and record['result']['finish_reason'] == 'completed'
                proposed = parse_answer(record['result']['final_response'])
                assert proposed['decision'] == 'stop'
                prompt = '''Task-coverage correction from the supervisor: the user explicitly requested Ascend profiling to locate engine costs and establish achievable bounds before optimization. This campaign has no completed profiling experiment. The two finished directions investigated the same prefill-budget family. Their negative result does not establish that all authorized optimization space is exhausted. Missing bottleneck evidence is a reason to consider the explicitly available diagnostic profile mode, not evidence that no direction exists.
Review your proposed stop with that outstanding requirement in mind. You have one remaining direction slot, up to three serial NPU experiments, and unused Claude budget. Independently choose what to measure and how to interpret it; no particular bottleneck, code change or positive gain is prescribed. Reuse existing work with attribution, keep validation unseen, and do not repeat completed benchmarks just to spend budget. Your previous stop proposal remains archived and is not being represented as an accepted outcome.
''' + MASTER_SCHEMA
                write(OUT / 'research/master-stop-coverage-review.json', {
                    'source_call_id': record['call_id'], 'receipt_sha256': sha(path),
                    'proposed_decision': proposed, 'review_prompt': prompt,
                    'reason': 'Existing user-required profiling has not been performed in this campaign.',
                    'positive_result_required': False, 'epoch': time.time()})
                cached_call = None; review_incomplete_stop = False
            if resume_upstream:
                assert role == state['active_role']
                resume_upstream = False
                prompt = 'The previous response was interrupted by a confirmed upstream stream idle timeout. Continue that unfinished research turn from the native session history, preserving the existing decisions, tools and experiment receipts. Do not repeat completed experiments. Return the originally requested final JSON.'
            if cached_call:
                path = OUT / 'research/calls' / cached_call
                assert path.parent == OUT / 'research/calls' and path.name == cached_call
                record = read(path)
                assert record['session_id'] == role and record['model'] == 'claude-opus-5-5'
                assert record['result']['finish_reason'] == 'completed' and mode == 'direction'
                value, repair = cached_answer(record['result']['final_response'])
                write(OUT / 'research/roles' / role / ('answer-recovered-cleanup.json' if cleanup_recovery else 'answer-recovered-format.json'),
                      {'answer': value, 'call_id': record['call_id'], 'receipt_sha256': sha(path),
                       'source': 'Previously completed model answer; recovery without additional direction API call.',
                       'format_repair': repair})
                cached_call = None
                return value
            return invoke(role, mode, prompt)
        continue_research(state, target_model='claude-opus-5-5', invoke_role=resume_invoke)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(); parser.add_argument('--cached-call'); parser.add_argument('--resume-upstream', action='store_true')
    parser.add_argument('--review-incomplete-stop', action='store_true')
    args = parser.parse_args(); run(args.cached_call, args.resume_upstream, args.review_incomplete_stop)
