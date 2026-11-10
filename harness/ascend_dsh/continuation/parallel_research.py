"""Two isolated DSH analysis lanes beside the serial NPU research driver.

Uses the existing locked cumulative ledgers. Never writes primary state, starts
an NPU experiment, activates GPT early, or opens held-out data. A scientific
Master allocates the topics; reports are attributed proposals for later testing.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from prepare_baseline import ROOT, OUT, write, sha
from research_driver import patch_for, parse_answer
from continue_research import SYSTEM, compact_receipts
from dsh_call import ProviderRefusal

AREA = OUT / 'research/parallel'


def validate_plan(plan):
    directions = plan.get('directions')
    if not isinstance(directions, list) or len(directions) != 2:
        raise ValueError('Exactly two parallel analysis directions required')
    names = set()
    for item in directions:
        name = item.get('name', '')
        if not re.fullmatch(r'[a-z0-9-]{1,40}', name) or name in names:
            raise ValueError('Unique bounded direction names required')
        names.add(name)
        if type(item.get('max_actions')) is not int or not 12 <= item['max_actions'] <= 40:
            raise ValueError('Action allocation outside 12..40')
        for key in ('objective', 'required_evidence', 'cost_floor_plan'):
            if not isinstance(item.get(key), str) or not 1 <= len(item[key]) <= 4000:
                raise ValueError('Missing bounded direction brief')
    return plan


def activate_gpt_phase(root):
    """Activate the already authorized shared phase after a durable denial.

    Does not rewrite the primary driver's model/state or cancel its in-flight
    work. A unique temporary file avoids collision with the legacy primary
    handoff writer; either may publish the same authorized phase atomically.
    """
    handoff = root / 'handoff'
    handoff.mkdir(exist_ok=True)
    with (handoff / 'activation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads((root / 'billing/state.json').read_text())
        if (not ledger.get('budget_exhausted') or ledger.get('model') != 'claude-opus-5-5'
                or not 0 < ledger.get('limit_micro_usd', 0) <= 200_000_000):
            raise RuntimeError('No durable authorized Claude budget denial')
        statefile = handoff / 'state.json'
        if statefile.exists() and json.loads(statefile.read_text()).get('status') == 'gpt_running':
            return
        record = {'status': 'gpt_running', 'activated_epoch': time.time(),
                  'claude_limit_usd': 200, 'gpt_limit_usd': 500,
                  'reason': 'Cumulative Claude admission budget exhausted',
                  'activated_by': 'trusted_parallel_scheduler',
                  'claude_ledger_sha256': sha(root / 'billing/state.json')}
        temporary = handoff / f'activation-{os.getpid()}-{time.time_ns()}.tmp'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(statefile)
        # Preserve the activation provenance if the primary later republishes.
        audit = root / 'research/parallel/gpt-activation.json'
        audit.parent.mkdir(parents=True, exist_ok=True)
        write(audit, record)


def route(root=OUT, *, activate=False):
    research = json.loads((root / 'research/state.json').read_text())
    if (research.get('validation_opened') or (root / 'candidate-freeze.json').exists()
            or (root / 'final-validation/state.json').exists()):
        raise RuntimeError('Parallel research cannot cross the validation boundary')
    if research.get('status') != 'researching':
        raise RuntimeError('Primary research requires supervision; preserve parallel checkpoint')
    claude = json.loads((root / 'billing/state.json').read_text())
    if not claude.get('budget_exhausted'):
        return 'claude-opus-5-5'
    if activate:
        activate_gpt_phase(root)
    handoff = root / 'handoff/state.json'
    if handoff.exists() and json.loads(handoff.read_text()).get('status') == 'gpt_running':
        gpt = root / 'billing-gpt/state.json'
        if gpt.exists() and json.loads(gpt.read_text()).get('budget_exhausted'):
            raise RuntimeError('GPT cumulative budget exhausted')
        return 'gpt-6.1-sol'
    return 'wait_for_primary_handoff'


def freeze_evidence():
    states = []
    shared = {}
    for path in sorted((OUT / 'experiments').glob('cont-d1-*/state.json')):
        state = json.loads(path.read_text())
        if state.get('status') != 'complete' or not state.get('baseline_restored'):
            continue
        states.append(state)
        trace = path.parent / 'traces'
        shared[path.parent.name] = {
            str(p.relative_to(trace)): sha(p)
            for p in sorted(trace.rglob('*.csv'))
            if p.name in ('kernel_details.csv', 'kernel_type_summary.csv', 'workload_activity_summary.csv')
            and not p.is_symlink() and p.stat().st_size <= 64 * 1024**2}
    if len(states) != 3:
        raise RuntimeError('Expected three finalized baseline profiles')
    review = json.loads((OUT / 'research/supervisor-d2-attribution-review.json').read_text())
    snapshot = {'origin': 'supervisor_shared_completed_dev_evidence',
                'created_epoch': time.time(), 'validation_opened': False,
                'profiles': compact_receipts(states), 'shared_profile_csvs': shared,
                'supervisor_corrections': review['corrections'],
                'already_in_flight': 'Shared-expert multistream overlap true; do not duplicate this experiment or its claimed attribution.',
                'constraints': 'Model/precision/topology/sampling fixed. K changes lower priority. No H100, quantization or holdout tasks.'}
    write(AREA / 'evidence.json', snapshot)
    return snapshot


def call_role(role, mode, prompt):
    original_prompt = prompt
    directory = AREA / 'roles' / role
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'run.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        final = directory / 'result.json'
        if final.exists() and json.loads(final.read_text()).get('status') == 'complete':
            return
        state = {'status': 'starting', 'role': role, 'pid': os.getpid(), 'started_epoch': time.time()}
        statefile = directory / 'state.json'
        prior_state = json.loads(statefile.read_text()) if statefile.exists() else {}
        if prior_state.get('error') == "AssertionError('max-tokens')":
            prompt = ('Continue this same session after the recorded max-token truncation. '
                      'Do not repeat completed source reads or analysis. Finish the requested concise JSON now, '
                      'using the existing evidence and original schema. Preserve unknown quantities as null.')
        truncation_retries = 0
        waiting_since = None
        try:
            while True:
                model = route(activate=True)
                state.update(status=model, updated_epoch=time.time())
                write(statefile, state)
                if model == 'wait_for_primary_handoff':
                    waiting_since = waiting_since or time.monotonic()
                    if time.monotonic() - waiting_since > 14400:
                        raise TimeoutError('Primary handoff not ready after four hours; no early GPT activation')
                    time.sleep(20)
                    continue
                try:
                    if model == 'claude-opus-5-5':
                        from dsh_call import call
                        answer, receipt = call(role, prompt, SYSTEM, max_tokens=8192,
                                              patch=patch_for(role, mode), deadline_seconds=7200)
                    else:
                        from gpt_call import call
                        answer, receipt = call(role, mode, prompt, SYSTEM, max_tokens=8192,
                                              deadline_seconds=7200)
                except ProviderRefusal:
                    raise
                except AssertionError as exc:
                    if str(exc) == 'max-tokens' and truncation_retries < 1:
                        truncation_retries += 1
                        state.setdefault('recoveries', []).append({'error': repr(exc), 'epoch': time.time()})
                        write(statefile, state)
                        prompt = ('Continue this same session after the recorded max-token truncation. '
                                  'Do not repeat completed source reads or analysis. Finish the original requested '
                                  'concise JSON now with the existing evidence; keep unknown quantities null.')
                        continue
                    ledger = json.loads((OUT / 'billing/state.json').read_text())
                    if model == 'claude-opus-5-5' and ledger.get('budget_exhausted'):
                        log = OUT / 'research/roles' / role / 'broker.jsonl'
                        history = log.read_text()[-24000:] if log.exists() else ''
                        prompt = original_prompt + '\nResume after budget handoff using prior role receipts; do not repeat completed work:\n' + history
                        continue
                    raise
                except Exception:
                    # Only a durable budget denial permits waiting for a model
                    # handoff. Provider refusal and unrelated faults are preserved.
                    ledger = json.loads((OUT / 'billing/state.json').read_text())
                    if model == 'claude-opus-5-5' and ledger.get('budget_exhausted'):
                        log = OUT / 'research/roles' / role / 'broker.jsonl'
                        history = log.read_text()[-24000:] if log.exists() else ''
                        prompt = original_prompt + '\nResume the same scope after budget handoff. Do not repeat completed source/CPU work. Prior role receipts:\n' + history
                        continue
                    raise
                report = parse_answer(answer)
                if mode == 'master':
                    validate_plan(report)
                if len(json.dumps(report).encode()) > 24000:
                    raise ValueError('Parallel report exceeds bounded feedback limit')
                write(final, {'status': 'complete', 'role': role, 'model': model,
                              'call_id': receipt['call_id'], 'completed_epoch': time.time(),
                              'measured_gain': False, 'report': report})
                state.update(status='complete', completed_epoch=time.time())
                write(statefile, state)
                return
        except BaseException as exc:
            state.update(status='needs_attention', error=repr(exc), updated_epoch=time.time())
            write(statefile, state)
            raise


def spawn(role, mode, prompt):
    directory = AREA / 'roles' / role
    directory.mkdir(parents=True, exist_ok=True)
    write(directory / 'request.json', {'role': role, 'mode': mode, 'prompt': prompt})
    with (directory / 'process.log').open('ab') as stream:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', role],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT,
            start_new_session=True)
    write(directory / 'process.json', {'pid': process.pid, 'created_epoch': time.time()})
    return process


def supervise(resume=False):
    AREA.mkdir(parents=True, exist_ok=True)
    with (AREA / 'driver.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = AREA / 'state.json'
        if path.exists() and not resume:
            raise RuntimeError('Existing parallel wave; inspect receipts rather than duplicate workers')
        previous = json.loads(path.read_text()) if path.exists() else None
        if previous:
            # Resuming is safe only after all recorded children have exited.
            for procfile in (AREA / 'roles').glob('*/process.json'):
                proc = json.loads(procfile.read_text())
                cmdline = Path(f'/proc/{proc["pid"]}/cmdline')
                try:
                    argv = cmdline.read_bytes().decode().split('\0')
                except FileNotFoundError:
                    continue
                if str(Path(__file__).resolve()) in argv:
                    raise RuntimeError('Recorded parallel worker still alive; do not duplicate')
            write(AREA / f'interrupted-state-{time.time_ns()}.json', previous)
        state = {'status': 'planning', 'pid': os.getpid(), 'started_epoch': time.time(),
                 'analysis_lanes': 2, 'npu_experiment_lanes': 1,
                 'shared_claude_limit_usd': 200, 'shared_gpt_limit_usd': 500,
                 'validation_opened': False, 'source_sha256': sha(__file__)}
        write(path, state)
        try:
            snapshot = json.loads((AREA / 'evidence.json').read_text()) if resume else freeze_evidence()
            # Large CSV inventory remains in allocations; the brief keeps only
            # the already compact profile summaries and attribution corrections.
            brief = {k: v for k, v in snapshot.items() if k != 'shared_profile_csvs'}
            planner = 'parallel-master-1'
            alloc = OUT / 'research/roles' / planner
            alloc.mkdir(parents=True, exist_ok=True)
            write(alloc / 'allocation.json', {'max_actions': 12, 'max_experiments': 0})
            prompt = ('The user now authorizes parallel research. Allocate exactly TWO distinct analysis-only directions '
                'alongside the existing serial NPU direction. Choose complementary topics from evidence, not a prescribed win. '
                'They can read pinned baseline CSVs and source, write scratch/default-off patch proposals, and run isolated CPU analysis. '
                'They cannot launch NPU experiments or alter serving. Avoid duplicating the active shared-expert overlap direction. '
                'No paid calls merely to poll another worker. Return JSON {"directions":[{"name":slug,"objective":string,'
                '"required_evidence":string,"cost_floor_plan":string,"max_actions":12..40}, ...]}. '
                'No need to launch experiments yourself. The two results will be reviewed by the serial scientific Master.\n'
                + json.dumps(brief))
            planner_process = spawn(planner, 'master', prompt)
            if planner_process.wait() != 0:
                raise RuntimeError('Parallel planner did not complete; see preserved native trajectory')
            result = json.loads((AREA / 'roles' / planner / 'result.json').read_text())
            plan = validate_plan(result['report'])
            write(AREA / 'plan.json', plan | {'origin_call_id': result['call_id']})
            processes = []
            for index, spec in enumerate(plan['directions'], 1):
                role = f'parallel-a{index}-{spec["name"]}'
                folder = OUT / 'research/roles' / role
                folder.mkdir(parents=True, exist_ok=True)
                write(folder / 'allocation.json', {'analysis_only': True, 'max_actions': spec['max_actions'],
                    'max_experiments': 0, 'shared_profile_csvs': snapshot['shared_profile_csvs']})
                prompt = ('Your independent parallel analysis brief:\n' + json.dumps(spec)
                    + '\nThis is source/trace/CPU research, with no NPU launch capability. Do not duplicate the active shared-expert overlap test. '
                    'Treat supplied prior evidence as attributed reuse. Other parallel reports are withheld. '
                    'At most one highest-value default-off proposal; alternatively state no justified proposal and evidence gaps. '
                    'Define affected workload/bytes/FLOPs, attainable floor and assumptions. Keep unknown rates/headroom null. '
                    'Return JSON {"status":"proposal"|"needs_evidence"|"no_proposal", "hypothesis":string,'
                    '"source_evidence":array,"cost_floor":object,"candidate":object|null,"acceptance_plan":array,'
                    '"requested_serial_experiments":array,"limitations":array}. This is not a measured gain. '
                    'Read source and relevant CSVs before concluding.\nShared completed dev evidence:\n' + json.dumps(brief)
                    + '\nPinned CSVs available via read_profile(id,path,offset):\n' + json.dumps(snapshot['shared_profile_csvs']))
                processes.append((role, spawn(role, 'direction', prompt)))
            state.update(status='analyzing', roles=[r for r, _ in processes])
            write(path, state)
            while any(p.poll() is None for _, p in processes):
                state['workers'] = {r: {'pid': p.pid, 'exit_code': p.poll()} for r, p in processes}
                state['updated_epoch'] = time.time()
                write(path, state)
                time.sleep(10)
            state.update(status='reports_ready' if all(p.returncode == 0 for _, p in processes) else 'needs_attention',
                         workers={r: {'pid': p.pid, 'exit_code': p.returncode} for r, p in processes},
                         completed_epoch=time.time())
            write(path, state)
        except BaseException as exc:
            state.update(status='needs_attention', error=repr(exc), updated_epoch=time.time())
            write(path, state)
            raise


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.worker:
        os.nice(10)
        if not re.fullmatch(r'[a-z0-9-]{1,80}', args.worker):
            raise ValueError('Invalid worker role')
        request = json.loads((AREA / 'roles' / args.worker / 'request.json').read_text())
        call_role(args.worker, request['mode'], request['prompt'])
    else:
        supervise(args.resume)
