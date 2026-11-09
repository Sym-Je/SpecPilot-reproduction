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
from gpt_handoff import continue_research, experiment_receipts, read
from prepare_baseline import OUT, write, sha
from research_driver import SYSTEM, parse_answer, patch_for


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
    response, receipt = call(role, prompt, system, max_tokens=8192,
                             patch=patch_for(role, mode), deadline_seconds=10800)
    value = parse_answer(response)
    write(OUT / 'research/roles' / role / ('answer-recovered-' + str(time.time_ns()) + '.json'),
          {'answer': value, 'call_id': receipt['call_id']})
    return value


def run(cached_call=None):
    with (OUT / 'research/driver.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read(OUT / 'research/state.json')
        assert state['status'] == 'stopped_with_error'
        if cached_call:
            assert state['error'].startswith('JSONDecodeError:')
        else:
            assert state['error'] == 'AssertionError: max-tokens'
        assert state['validation_opened'] is False and not (OUT / 'candidate-freeze.json').exists()
        assert not read(OUT / 'billing/state.json').get('budget_exhausted')
        experiment_receipts(state['active_role'])
        checkpoint = OUT / 'research' / ('claude-format-checkpoint.json' if cached_call else 'claude-truncated-checkpoint.json')
        assert not checkpoint.exists(), 'Recovery is explicit, never an unbounded retry loop'
        write(checkpoint, state)
        def resume_invoke(role, mode, prompt):
            nonlocal cached_call
            if cached_call:
                path = OUT / 'research/calls' / cached_call
                assert path.parent == OUT / 'research/calls' and path.name == cached_call
                record = read(path)
                assert record['session_id'] == role and record['model'] == 'claude-opus-5-5'
                assert record['result']['finish_reason'] == 'completed' and mode == 'direction'
                value, repair = cached_answer(record['result']['final_response'])
                write(OUT / 'research/roles' / role / 'answer-recovered-format.json',
                      {'answer': value, 'call_id': record['call_id'], 'receipt_sha256': sha(path),
                       'source': 'Previously completed model answer; format recovery only, no additional API call.',
                       'format_repair': repair})
                cached_call = None
                return value
            return invoke(role, mode, prompt)
        continue_research(state, target_model='claude-opus-5-5', invoke_role=resume_invoke)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(); parser.add_argument('--cached-call')
    run(parser.parse_args().cached_call)
