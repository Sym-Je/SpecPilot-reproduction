"""Conservative terminal receipts when a preempted Pod has already disappeared."""

from datetime import datetime
import math


def preemption_receipt(job, events, *, live_pods, observed_end_unix, gpus):
    phase = job.get('status', {}).get('state', {}).get('phase')
    uuid = job['metadata']['name']
    proofs = [event for event in events if event.get('reason') == 'JobPreempted' and event.get('involved_name') == uuid]
    if phase not in ('Aborted', 'Failed', 'Terminated') or live_pods != 0 or not proofs:
        return None
    if type(gpus) is not int or not 1 <= gpus <= 8 or not math.isfinite(observed_end_unix):
        raise ValueError('explicit positive GPU count and observation time required')
    created = datetime.fromisoformat(job['metadata']['creationTimestamp'].replace('Z', '+00:00')).timestamp()
    terminal = datetime.fromisoformat(job['status']['state']['lastTransitionTime'].replace('Z', '+00:00')).timestamp()
    if not created <= terminal <= observed_end_unix:
        raise ValueError('preemption observation timestamps are inconsistent')
    return dict(uuid=uuid, phase=phase, reason='JobPreempted', container_exit_code=None,
        terminal_job_and_pod_absence_confirmed=True, observed_end_unix=observed_end_unix,
        conservative_gpu_seconds=math.ceil((observed_end_unix-created)*gpus),
        charging_rule='creation through confirmed absence observation; not an invented container finish time',
        events=proofs)
