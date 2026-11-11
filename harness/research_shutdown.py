"""Post-hoc engineering observation, never a Phase 4 pre-open clearance."""

import json
import os
from pathlib import Path
import time

from controller.phase4_final import identity, trusted_metadata
from exp.phase4_run import reference
from harness.engine_research import save


def inspect_members(root, closure):
    root = Path(root).resolve()
    owner = (root/'process-closure.json').stat().st_uid
    state = json.loads((root/'resource-state.json').read_text())
    members = closure.get('process_members', [])
    if not members or closure.get('role_processes_closed') is not True:
        raise ValueError('actual closed process inventory is required')
    observed = time.time()
    current = identity()
    seen, paths, parents = set(), set(), set()
    for member in members:
        for field in ('birth', 'exit'):
            path = Path(member[field]['path'])
            if path != path.resolve() or not path.is_relative_to(root/'processes'):
                raise ValueError('process receipt escaped its recorded directory')
            paths.add(path)
        birth = trusted_metadata(member['birth'], owner)
        ended = trusted_metadata(member['exit'], owner)
        child = birth['identity']
        key = tuple(child[field] for field in ('host_boot_id','pid_namespace_inode','pid','start_ticks'))
        if (key in seen or birth.get('schema') != 'controller-process-birth-v1' or not birth.get('role') or
                child['start_ticks'] < 1 or child['parent_pid'] < 1 or
                ended.get('schema') != 'controller-process-exit-v1' or ended.get('birth') != member['birth'] or
                type(ended.get('returncode')) is not int or ended['returncode'] != 0 or
                not state['started'] <= birth['observed_unix'] <= ended['reaped_unix'] <= observed <=
                    state['started']+state['wall_seconds']):
            raise ValueError('actual process birth/exit identity or chronology mismatch')
        seen.add(key)
        parents.add(child['parent_pid'])
        if (child['host_boot_id'],child['pid_namespace_inode']) == (current['host_boot_id'],current['pid_namespace_inode']):
            try:
                live = identity(child['pid'])
            except (FileNotFoundError,ProcessLookupError):
                continue
            if live['start_ticks'] == child['start_ticks']:
                raise ValueError('recorded research process is still live')
    recorded = {path.resolve() for pattern in ('birth-*.json','exit-*.json')
        for path in (root/'processes').rglob(pattern)}
    if paths != recorded:
        raise ValueError('orphan or omitted process receipt')
    return dict(verified_processes=len(seen), broker_parent_pids=sorted(parents),
        phase4_preopen_clearance=False, closure_mode='posthoc-maintainer-observation')


def observe_shutdown(root):
    root = Path(root).resolve()
    path = root/'process-closure.json'
    closure = json.loads(path.read_text())
    if 'posthoc_observation' in closure:
        raise ValueError('post-hoc closure observation already recorded')
    exit_status = root/'campaign-recovery-exit-status'
    if exit_status.read_text().strip() != '1':
        raise ValueError('preserved failed campaign exit is required')
    inspected = inspect_members(root,closure)
    destination = root/'processes/closure-observation'
    destination.mkdir(mode=0o700)
    failure = destination/'original-process-closure.json'
    with failure.open('xb') as output:
        output.write(path.read_bytes())
    proof = dict(schema='research-posthoc-shutdown-v1', original_failure=reference(failure),
        failed_exit_status=reference(exit_status), observed_unix=time.time(), observer=identity(),
        members=closure['process_members'], inspection=inspected,
        scope='Historical engineering shutdown verification only; not a controller pre-open registry or sealed clearance')
    target = destination/'observation.json'
    descriptor = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as output:
        json.dump(proof,output,indent=2,sort_keys=True)
        output.write('\n')
    closure['posthoc_observation'] = reference(target)
    save(path,closure)
    return proof


def verify_observation(root, closure):
    root = Path(root).resolve()
    owner = (root/'process-closure.json').stat().st_uid
    expected = root/'processes/closure-observation/observation.json'
    if closure.get('posthoc_observation') != reference(expected):
        raise ValueError('post-hoc observer proof path or SHA differs')
    proof = trusted_metadata(closure['posthoc_observation'],owner)
    original = root/'processes/closure-observation/original-process-closure.json'
    status = root/'campaign-recovery-exit-status'
    if (proof.get('schema') != 'research-posthoc-shutdown-v1' or proof.get('original_failure') != reference(original) or
            proof.get('failed_exit_status') != reference(status) or status.read_text().strip() != '1' or
            proof.get('members') != closure['process_members'] or proof['observer']['uid'] != owner or
            not proof['observed_unix'] <= time.time() or
            json.loads(original.read_text()).get('process_members') != closure['process_members']):
        raise ValueError('post-hoc closure does not preserve the actual failed closeout')
    actual = inspect_members(root,closure)
    if actual != proof['inspection'] or actual['phase4_preopen_clearance'] is not False:
        raise ValueError('post-hoc observer summary differs from actual receipts')
    return dict(actual,observed_unix=proof['observed_unix'])
