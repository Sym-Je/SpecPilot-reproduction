"""Conditional Claude-to-GPT continuation; never spends GPT before exhaustion.

This supervisor does not restart the baseline, reset role allocations or inspect
held-out prompts. Every phase transition is durable. An uncertain GPT crash is
preserved for inspection, not automatically replayed as another paid run.
"""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time

from prepare_baseline import ROOT, OUT, write, sha
from research_driver import SYSTEM, parse_answer
from gpt_call import call
from gpt_budget import Budget, MODEL, gateway_snapshot, get_json
from experiment_lifecycle import cleanup_pending, wait_final, failure_diagnostics

MASTER_SCHEMA = '''Return a single JSON object {"decision":"run_direction" or "stop", "reason":string,
"direction":{"name":lowercase-short-slug,"objective":string,"required_evidence":string,
"cost_floor_plan":string,"max_experiments":integer 1..3,"max_actions":integer 10..120},
"candidate":null or {"config":object,"experiment_id":string}}. At most three directions
total across both model phases, including completed and interrupted ones. K tuning
has lower priority. A stop/no-gain conclusion is valid; do not consume budget just
because it remains. Use only dev evidence and explicitly attribute reused work.'''
DIRECTION_SCHEMA = '''Continue this allocated direction from its existing work. The broker role,
scratch, action count and experiment allocation are unchanged. Never relaunch an
experiment already recorded. Read trusted receipts; do not assume your predecessor's
theory or prose is correct. All NPU work remains serial. Measure a cost floor before
claiming headroom. Source patches remain proposals, not automatically deployed.
Return {"status":"candidate" or "no_gain" or "needs_admission" or "needs_evidence",
"hypothesis":string,"cost_floor":object,"experiments":array,"conclusion":string,
"candidate_config":object or null,"limitations":array}.'''


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def eligibility(ledger, research, *, validation_started=False, pending_experiments=False):
    if validation_started or research.get('validation_opened') or research.get('status') == 'research_finished':
        return 'finished_without_handoff'
    exhausted = ledger.get('budget_exhausted')
    if not exhausted:
        return 'needs_attention' if research.get('status') == 'stopped_with_error' else 'waiting_for_claude'
    if ledger.get('model') != 'claude-opus-5-5' or ledger.get('limit_micro_usd', 0) != 200_000_000:
        return 'needs_attention'
    if research.get('status') != 'stopped_with_error': return 'waiting_for_claude'
    if (research.get('stopped_epoch', 0) < exhausted['epoch']
            or research.get('active_role') != exhausted.get('role_id')):
        return 'needs_attention'
    return 'waiting_for_experiment_restoration' if pending_experiments else 'ready'


def experiment_receipts(role, root=OUT):
    broker = read(root / 'research/roles' / role / 'broker-state.json', {'actions': 0, 'experiments': []})
    evidence = []
    for eid in broker['experiments']:
        folder = root / 'experiments' / eid
        actual = read(folder / 'state.json')
        if actual and cleanup_pending(actual):
            # A direction may finish reporting while the runner is restoring.
            # Wait without another LLM call; preserve the completed report.
            actual = wait_final(folder / 'state.json', timeout=2100)
        assert actual and actual['status'] in ('complete', 'failed'), 'Experiment still active'
        if actual.get('lock_acquired_epoch'):
            assert actual.get('completed_epoch'), 'Experiment cleanup not complete'
            assert actual.get('baseline_restored') is True, 'Baseline restoration required'
        evidence.append(actual | failure_diagnostics(folder, actual))
    return broker, evidence


def recovery_plan(research, root=OUT):
    """Recover an interrupted direction using the original durable decision."""
    rounds = research['rounds']
    assert len({x['role'] for x in rounds}) == len(rounds) <= 3
    index = len(rounds) + 1
    decision = read(root / 'research' / f'master-decision-{index}.json')
    if decision and decision['decision'] == 'run_direction':
        spec = decision['direction']; role = f'ctrip-d{index}-{spec["name"]}'
        if research['active_role'] != role:
            assert research['active_role'] == 'ctrip-master', 'Inconsistent checkpoint'
        allocation = read(root / 'research/roles' / role / 'allocation.json')
        if allocation:
            assert allocation == {k: spec[k] for k in ('max_experiments', 'max_actions')}
        return {'index': index, 'decision': decision, 'resume_role': role, 'allocation': allocation}
    return {'index': index, 'decision': decision, 'resume_role': None, 'allocation': None}


def role_handoff(role, spec):
    directory = OUT / 'research/roles' / role
    broker, evidence = experiment_receipts(role)
    history = []
    log = directory / 'broker.jsonl'
    if log.exists():
        # Bounded original tool receipts, not an invented model summary. Complete
        # Claude/native trajectories remain on disk with a separate provenance link.
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        remaining = 90000
        for row in reversed(rows):
            encoded = json.dumps(row, ensure_ascii=False)
            if len(encoded) > remaining: continue
            history.insert(0, row); remaining -= len(encoded)
    paths = [p for p in (OUT / 'research/dsh-home').rglob('session.v4.jsonl') if p.parent.name == role]
    return {'direction': spec, 'broker_state': broker, 'trusted_experiments': evidence,
            'prior_tool_receipts': history, 'previous_trajectory': [
                {'path': str(p), 'sha256': sha(p), 'model': 'claude-opus-5-5'} for p in paths],
            'inherited_work': True, 'raw_validation_access': False}


def invoke(role, mode, prompt):
    system = SYSTEM.replace('Claude Opus 5.5', MODEL).replace('$500 task ceiling', '$500 GPT-phase ceiling')
    response, receipt = call(role, mode, prompt, system)
    value = parse_answer(response)
    path = OUT / 'research/roles' / role / ('answer-gpt-' + str(time.time_ns()) + '.json')
    write(path, {'answer': value, 'call_id': receipt['call_id']})
    return value


def context_for_master(state):
    evidence = []
    for row in state['rounds']:
        _, receipts = experiment_receipts(row['role'])
        evidence.append({'role': row['role'], 'receipts': receipts})
    return 'Continue the existing development campaign, not a new baseline. Prior work is reused and must be credited.\n' + json.dumps(
        {'completed_rounds': state['rounds'], 'trusted_evidence': evidence,
         'remaining_directions': 3 - len(state['rounds'])}) + '\n' + MASTER_SCHEMA


def continue_research(state, *, target_model=MODEL, invoke_role=None):
    invoke_role = invoke_role or invoke
    statefile = OUT / 'research/state.json'
    if target_model == MODEL:
        state['provider_handoff'] = {'from': 'claude-opus-5-5', 'to': MODEL, 'epoch': time.time(),
                                     'claude_limit_usd': 200, 'gpt_limit_usd': 500}
        state.update(status='researching', api_limit_usd=500, api_limit_scope='GPT phase only')
    else:
        assert target_model == 'claude-opus-5-5'
        state.setdefault('recoveries', []).append({'epoch': time.time(), 'reason': state.get('error'),
            'model': target_model, 'prior_actions_and_experiments_retained': True})
        state.update(status='researching', api_limit_usd=200, api_limit_scope='Claude total including previous calls')
    plan = recovery_plan(state)
    state.pop('error', None); state.pop('stopped_epoch', None)
    write(statefile, state)
    try:
        decision = plan['decision']
        for index in range(plan['index'], 4):
            if decision is None:
                state['active_role'] = 'ctrip-master'; write(statefile, state)
                decision = invoke_role('ctrip-master', 'master', context_for_master(state))
                write(OUT / 'research' / f'master-decision-{index}.json', decision)
            if decision['decision'] == 'stop':
                state.update(status='research_finished', master_decision=decision); break
            assert decision['decision'] == 'run_direction'
            spec = decision['direction']
            assert re.fullmatch(r'[a-z0-9-]{1,40}', spec['name'])
            assert type(spec['max_experiments']) is int and 1 <= spec['max_experiments'] <= 3
            assert type(spec['max_actions']) is int and 10 <= spec['max_actions'] <= 120
            role = f'ctrip-d{index}-{spec["name"]}'
            directory = OUT / 'research/roles' / role; directory.mkdir(parents=True, exist_ok=True)
            allocation = {k: spec[k] for k in ('max_experiments', 'max_actions')}
            if (directory / 'allocation.json').exists():
                assert read(directory / 'allocation.json') == allocation, 'Never reset a previous allocation'
            else: write(directory / 'allocation.json', allocation)
            state['active_role'] = role; write(statefile, state)
            handoff = role_handoff(role, spec)
            if target_model != MODEL:
                # Native Claude session already contains its own history; do not
                # duplicate all tool output into the same context window.
                handoff.pop('prior_tool_receipts', None)
            write(directory / ('gpt-handoff.json' if target_model == MODEL else 'claude-recovery.json'), handoff)
            report = invoke_role(role, 'direction', DIRECTION_SCHEMA + '\n' + json.dumps(handoff))
            experiment_receipts(role)  # Require cleanup before the next role.
            state['rounds'].append({'role': role, 'allocation': spec, 'report': report,
                                    'completed_by_model': target_model,
                                    'inherited_from_claude': target_model == MODEL and bool(handoff.get('prior_tool_receipts'))})
            write(statefile, state); decision = None
        if state['status'] == 'researching':
            state['active_role'] = 'ctrip-master'; write(statefile, state)
            review = invoke_role('ctrip-master', 'master', context_for_master(state) +
                '\nNo further direction may launch. Return decision=stop with a measured candidate or null.')
            assert review['decision'] == 'stop'
            state.update(status='research_finished', master_decision=review)
        state.update(completed_epoch=time.time(), final_validation_status='running_independently',
                     validation_opened_by_research=False)
        write(statefile, state)
        # Independent terminal stage; no model calls beyond this point.
        with (OUT / 'research/final-validation.log').open('xb') as log:
            result = subprocess.run([str(ROOT / '.venv/bin/python'), str(OUT / 'final_validation.py'),
                '--research-state', str(statefile)], stdout=log, stderr=subprocess.STDOUT, timeout=12 * 3600)
        final = read(OUT / 'final-validation/state.json', {})
        state.update(validation_opened=final.get('validation_opened', False), final_validation_exit_code=result.returncode,
                     final_validation_status='complete' if result.returncode == 0 else 'failed_preserved',
                     campaign_status='complete' if result.returncode == 0 else 'needs_attention')
        write(statefile, state)
    except BaseException as exc:
        state.update(status='stopped_with_error', error=f'{type(exc).__name__}: {exc}', stopped_epoch=time.time())
        write(statefile, state); raise


def status():
    handoff = read(OUT / 'handoff/state.json', {'status': 'not_armed'})
    fields = ('status', 'condition', 'claude_limit_usd', 'gpt_limit_usd', 'target_model', 'pid', 'error')
    report = {k: handoff[k] for k in fields if k in handoff}
    for name, directory in [('claude', 'billing'), ('gpt', 'billing-gpt')]:
        ledger = read(OUT / directory / 'state.json')
        report[name] = {k: ledger[k] for k in ('model', 'limit_micro_usd', 'conservative_reserved_micro_usd',
            'observed_gateway_delta_micro_usd') if k in ledger} if ledger else {'activated': False}
    print(json.dumps(report))


def supervise():
    directory = OUT / 'handoff'; directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / 'supervisor.lock').open('a+') as own_lock:
        fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = read(directory / 'state.json', {})
        assert previous.get('status') in (None, 'armed', 'needs_attention'), 'Existing GPT attempt: inspect before any continuation'
        if previous.get('status') == 'needs_attention':
            assert read(OUT / 'research/state.json')['status'] == 'researching', 'Resolve Claude failure before rearming'
            write(directory / ('previous-watcher-' + str(time.time_ns()) + '.json'), previous)
        assert read(OUT / 'gpt-offline-preflight.json')['passed'] is True
        models = get_json('/v1/models')
        assert MODEL in [x['id'] for x in models['data']]
        gateway_snapshot()  # Free metadata validation only; does not create the GPT spending ledger.
        record = {'status': 'armed', 'condition': 'waiting_for_claude', 'pid': os.getpid(),
                  'armed_epoch': previous.get('armed_epoch', time.time()), 'target_model': MODEL,
                  'claude_limit_usd': 200, 'gpt_limit_usd': 500,
                  'inference_before_handoff': False, 'watcher_sha256': sha(__file__)}
        write(directory / 'state.json', record)
        while True:
            research = read(OUT / 'research/state.json')
            ledger = read(OUT / 'billing/state.json')
            pending = False
            for p in (OUT / 'experiments').glob('*/state.json'):
                x = read(p)
                pending |= x.get('status') not in ('complete', 'failed') or bool(x.get('lock_acquired_epoch') and not x.get('completed_epoch'))
            frozen = (OUT / 'candidate-freeze.json').exists() or (OUT / 'final-validation/state.json').exists()
            condition = eligibility(ledger, research, validation_started=frozen, pending_experiments=pending)
            record['condition'] = condition; write(directory / 'state.json', record)
            if condition in ('finished_without_handoff', 'needs_attention'):
                record.update(status=condition, completed_epoch=time.time()); write(directory / 'state.json', record); return
            if condition == 'ready':
                with (OUT / 'research/driver.lock').open('a+') as driver_lock:
                    try: fcntl.flock(driver_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        time.sleep(10); continue
                    # Re-read after taking ownership; the old driver can no longer race.
                    research = read(OUT / 'research/state.json')
                    assert eligibility(ledger, research, validation_started=frozen) == 'ready'
                    for p in (OUT / 'research/roles').glob('*/broker-state.json'):
                        experiment_receipts(p.parent.name)
                    assert not (OUT / 'billing-gpt/state.json').exists(), 'Never reset a prior GPT phase'
                    write(directory / 'claude-checkpoint.json', copy.deepcopy(research))
                    Budget().transact('status', {}, gateway_snapshot())
                    record.update(status='gpt_running', activated_epoch=time.time()); write(directory / 'state.json', record)
                    try:
                        continue_research(research)
                        record.update(status='gpt_complete', completed_epoch=time.time())
                    except BaseException as exc:
                        record.update(status='gpt_stopped', error=f'{type(exc).__name__}: {exc}', completed_epoch=time.time())
                        raise
                    finally: write(directory / 'state.json', record)
                    return
            time.sleep(10)


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser(); p.add_argument('action', choices=('watch', 'status'))
    args = p.parse_args()
    status() if args.action == 'status' else supervise()
