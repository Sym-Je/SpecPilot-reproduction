"""Trusted NorthJob execution; never accepts research shell commands."""

from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from exp.gpu_autonomy import IMAGE, ROOT
from harness.gpu_autonomy import digest, job_rows
from harness.engine_research import Budget, feedback_metrics, json_record, save

NORTHJOB = '/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/northjob'


def query(directory, name, label):
    process = subprocess.run([NORTHJOB, 'get', '--keyword', name, '--page-size', '100'],
                             capture_output=True, text=True, timeout=60)
    content = process.stdout + process.stderr
    (directory / label).write_text(content)
    if process.returncode:
        raise RuntimeError('task lookup failed; do not submit or retry')
    return job_rows(content, name)


def command(request, source, output, name, deadline):
    bootstrap = ROOT / 'exp/engine_research_remote.sh'
    user_command = shlex.join(['env', 'SP_ENGINE_BOOTSTRAP_SHA=' + digest(bootstrap),
        'SP_ENGINE_SOURCE_SHA=' + digest(source), 'SP_ENGINE_REQUEST_SHA=' + digest(request),
        'bash', str(bootstrap), str(request), str(source), str(output), str(deadline)])
    return ['env', f'SP_ENGINE_DEADLINE={deadline}', sys.executable, '-B', '-m', 'exp.engine_northjob',
        'create', '--job-name', name, '--project', 'WeaverDev', '--workspace', str(ROOT),
        '--nnodes', '1', '--nproc-per-node', '1', '--gpu-per-node', '2', '--gpu-resource', 'h100',
        '--mem-per-pod', '256', '--no-rdma', '--k8s-no-hostnetwork', '--k8s-namespace', 'qiji',
        '--k8s-queue', 'qiji', '--k8s-toleration',
        'key=task-type,operator=Equal,value=infra-dev-weaver,effect=NoSchedule',
        '--k8s-pvc-name', 'jixinpeng-pvc', '--k8s-pvc-mount-path', '/gpfs/users/jixinpeng',
        '--k8s-ttl', '86400', '--k8s-priority', '3', '--k8s-images', IMAGE, user_command]


def execute(directory, source, budget, *, resume_only=False, command_factory=None, feedback_loader=None, deadline=None):
    from kubernetes import client, config
    request = directory / 'request.json'
    record = json.loads(request.read_text())
    action = record['action']
    deadline = (3600 if action['per_suite'] <= 2 else 7200) if deadline is None else deadline
    name = directory.name
    output = directory / 'remote'
    cli = (command if command_factory is None else command_factory)(request, source, output, name, deadline)
    if resume_only:
        pending = json.loads((directory / 'pending.json').read_text())
        submitted = json.loads((directory / 'submitted.json').read_text())
        uuid = submitted['uuid']
        reservation = next(row for row in budget.read()['jobs'] if row['name'] == name)
        matches = query(directory, name, 'resume-query.txt')
        if (reservation.get('terminated') or reservation.get('uuid') != uuid or
                len(matches) != 1 or matches[0].get('name') != uuid or
                pending['request_sha256'] != digest(request) or pending['source_sha256'] != digest(source)):
            raise RuntimeError('resume identity/source differs; never recreate an existing task')
        return monitor(directory, budget, record, pending, uuid, feedback_loader=feedback_loader)
    if query(directory, name, 'pre-submit-query.txt'):
        raise RuntimeError('exact task name already exists; no new submission')
    budget.reserve(name, 2, deadline + 1200)
    pending = dict(name=name, total_gpus=2, nodes=1, gpu_per_node=2, gpu_type='H100',
        mode='bash', memory_gib=256, image=IMAGE, workspace=str(ROOT), deadline_seconds=deadline,
        priority_class='higher-priority-job',
        command=cli, shell_command=shlex.join(cli), request_sha256=digest(request), source_sha256=digest(source))
    save(directory / 'pending.json', pending)
    print(json.dumps(dict(event='PRE_SUBMIT', **pending)), flush=True)
    budget.update(name, create_calls=1)
    try:
        process = subprocess.run(cli, capture_output=True, text=True, timeout=120, cwd=ROOT)
        content = process.stdout + process.stderr
        returncode = process.returncode
    except subprocess.TimeoutExpired as error:
        content = ''.join(value.decode() if isinstance(value, bytes) else value or '' for value in (error.stdout, error.stderr))
        returncode = None
    (directory / 'submit.txt').write_text(content)
    save(directory / 'submit-exit.json', dict(exit_code=returncode, create_calls=1))
    matches = query(directory, name, 'post-submit-query.txt')
    if len(matches) != 1 or not re.search(r'''["']code["']\s*:\s*200''', content):
        raise RuntimeError('submission uncertain; reservation held, no automatic retry')
    uuid = matches[0].get('name')
    if not isinstance(uuid, str) or not re.fullmatch(r'job-[a-z0-9-]+', uuid):
        raise RuntimeError('UUID missing; reservation held')
    budget.update(name, uuid=uuid, submission_code=200)
    save(directory / 'submitted.json', dict(uuid=uuid, code=200, name=name))
    print(json.dumps(dict(event='SUBMITTED', uuid=uuid, name=name)), flush=True)
    return monitor(directory, budget, record, pending, uuid, feedback_loader=feedback_loader)


def monitor(directory, budget, record, pending, uuid, *, feedback_loader=None):
    from kubernetes import client, config
    name = pending['name']
    deadline = pending['deadline_seconds']
    output = directory / 'remote'
    config.load_kube_config()
    pods_api = client.CoreV1Api()
    jobs_api = client.CustomObjectsApi()
    started = next(row['reserved_unix'] for row in budget.read()['jobs'] if row['name'] == name)
    stop_sent = False
    observed = {}
    previous = directory / 'lifecycle-observed.json'
    if previous.is_file():
        history = json.loads(previous.read_text())
        if history['uuid'] != uuid:
            raise RuntimeError('monitor history belongs to another job')
        observed = history['pods']
    absent_terminal_since = None
    while time.time() - started < deadline + 780:
        job = jobs_api.get_namespaced_custom_object('batch.volcano.sh', 'v1alpha1', 'qiji', 'jobs', uuid)
        podspec = job['spec']['tasks'][0]['template']['spec']
        container = podspec['containers'][0]
        if (podspec['activeDeadlineSeconds'] != deadline or
                str(container['resources']['limits']['nvidia.com/gpu']) != '2' or container['image'] != IMAGE or
                not any(row.get('mountPath') == '/gpfs/models' and row.get('readOnly') for row in container['volumeMounts'])):
            raise RuntimeError('server resource/image/mount contract differs; reservation held')
        pods = pods_api.list_namespaced_pod('qiji', label_selector='volcano.sh/job-name=' + uuid).items
        for pod in pods:
            statuses = pod.status.container_statuses or []
            observed[pod.metadata.uid] = dict(name=pod.metadata.name, phase=pod.status.phase,
                node=pod.spec.node_name, restarts=sum(row.restart_count for row in statuses))
            if any(row.state.running for row in statuses):
                budget.update(name, started=True)
            if statuses and all(row.state.terminated for row in statuses):
                ended = statuses[0].state.terminated
                observed[pod.metadata.uid].update(exit_code=ended.exit_code,
                    started_at=ended.started_at.isoformat(), finished_at=ended.finished_at.isoformat())
        save(directory / 'lifecycle-observed.json', dict(uuid=uuid, pods=observed,
            job_phase=job.get('status', {}).get('state', {}).get('phase'), queue=job['spec'].get('queue')))
        phase = job.get('status', {}).get('state', {}).get('phase')
        if not pods and phase in ('Aborted', 'Failed', 'Terminated'):
            if absent_terminal_since is None:
                absent_terminal_since = time.time()
            elif time.time()-absent_terminal_since >= 5:
                from harness.ceiling_lifecycle import preemption_receipt
                events = pods_api.list_namespaced_event('qiji', field_selector='involvedObject.name='+uuid).items
                proofs = [dict(reason=event.reason, message=event.message,
                    involved_name=event.involved_object.name,
                    last_timestamp=str(event.last_timestamp)) for event in events]
                receipt = preemption_receipt(job, proofs, live_pods=0,
                    observed_end_unix=time.time(), gpus=pending['total_gpus'])
                if receipt is not None:
                    save(directory / 'preemption-proof.json', receipt)
                    save(directory / 'lifecycle-final.json', dict(uuid=uuid, phase=phase, pods=observed,
                        conservative_gpu_seconds=receipt['conservative_gpu_seconds'], queue=job['spec'].get('queue'),
                        container_exit_code=None, preemption_receipt=dict(path=str(directory / 'preemption-proof.json'),
                            sha256=digest(directory / 'preemption-proof.json'))))
                    budget.update(name, terminal=phase, terminated=True,
                        charged_gpu_seconds=receipt['conservative_gpu_seconds'])
                    feedback = dict(status='failed', uuid=uuid, controller_accepted=False, preempted=True,
                        container_exit_code=None, error='Confirmed job preemption and deleted Pod; partial evidence is not a complete experiment.')
                    save(directory / 'feedback.json', feedback)
                    print(json.dumps(dict(event='GPU_PREEMPTED', **feedback)), flush=True)
                    return feedback
        else:
            absent_terminal_since = None
        if (pods and all(pod.status.phase in ('Succeeded', 'Failed') for pod in pods) and
                phase in ('Completed', 'Failed', 'Aborted', 'Terminated') and
                all('finished_at' in row for row in observed.values())):
            created = datetime.fromisoformat(job['metadata']['creationTimestamp'].replace('Z', '+00:00'))
            finished = max(datetime.fromisoformat(row['finished_at']) for row in observed.values())
            charged = math.ceil(max(0, (finished - created).total_seconds()) * 2)
            save(directory / 'lifecycle-final.json', dict(uuid=uuid, phase=phase, pods=observed,
                conservative_gpu_seconds=charged, configured_max_retry=job['spec'].get('maxRetry'),
                retry_count=job.get('status', {}).get('retryCount'), queue=job['spec'].get('queue')))
            for pod in pods:
                (directory / f'{pod.metadata.name}.log').write_text(pods_api.read_namespaced_pod_log(pod.metadata.name, 'qiji', tail_lines=120))
            budget.update(name, terminal=phase, terminated=True, charged_gpu_seconds=charged)
            if (output / 'result.json').exists() and all(row['exit_code'] == 0 for row in observed.values()):
                if feedback_loader is not None:
                    feedback = feedback_loader(output, record)
                elif record.get('mode') == 'controller-dev':
                    from controller.dev_campaign import validate_campaign
                    feedback = json.loads((output / 'result.json').read_text())
                    verdict = json_record(validate_campaign(output))
                    if (verdict != feedback['controller_verdict'] or
                            feedback['controller_accepted'] != verdict['joint_acceptance_passed']):
                        raise RuntimeError('independent controller replay differs')
                else:
                    from exp.engine_research import audit
                    feedback = audit(output)
                    if feedback != json.loads((output / 'result.json').read_text()):
                        raise RuntimeError('independent paired-output audit differs')
                feedback.update(status='completed', uuid=uuid)
                feedback = feedback_metrics(feedback)
            else:
                feedback = dict(status='failed', uuid=uuid, controller_accepted=False,
                    error='No complete paired diagnostic. Original bounded remote tail follows.',
                    log_tail='\n'.join((directory / f'{pod.metadata.name}.log').read_text()[-8000:] for pod in pods))
            save(directory / 'feedback.json', feedback)
            print(json.dumps(dict(event='GPU_FINISHED', uuid=uuid, phase=phase,
                status=feedback['status'], conservative_gpu_seconds=charged)), flush=True)
            return feedback
        if not stop_sent and time.time() - started > deadline + 600:
            print(json.dumps(dict(event='STOP_OWN_JOB', uuid=uuid, reason='reserved execution/queue deadline reached')), flush=True)
            result = subprocess.run([NORTHJOB, 'delete', uuid, '--namespace', 'qiji'],
                                    capture_output=True, text=True, timeout=60)
            (directory / 'deadline-stop.txt').write_text(result.stdout + result.stderr)
            stop_sent = True
        print(json.dumps(dict(event='WAIT', uuid=uuid, phase=phase, pods=len(pods))), flush=True)
        time.sleep(20)
    raise RuntimeError('termination unconfirmed; reservation held; no further submission')
