"""Trusted startup-option research protocol and persistent resource reservations."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import time


def validate_action(action):
    fields = {'kind', 'value', 'per_suite', 'max_new_tokens', 'reason'}
    if not isinstance(action, dict) or set(action) != fields or action['kind'] != 'run_engine':
        raise ValueError('only a structured startup-option experiment is supported')
    for name, lower, upper in [('value', 1, 64), ('per_suite', 1, 6)]:
        if type(action[name]) is not int or not lower <= action[name] <= upper:
            raise ValueError('invalid ' + name)
    if type(action['max_new_tokens']) is not int or action['max_new_tokens'] not in (256, 2048):
        raise ValueError('unsupported generation limit')
    if not isinstance(action['reason'], str) or not 1 <= len(action['reason']) <= 4000:
        raise ValueError('a bounded falsifiable research rationale is required')
    return action


def feedback_metrics(feedback):
    if feedback.get('protocol') != 'startup-option-research-v1':
        return dict(feedback)
    return dict(feedback, metric_definition=dict(
        measured_quantity='candidate_tokens_per_second / stock_tokens_per_second',
        unit='dimensionless throughput speedup', improvement_direction='higher_is_better',
        geomean='geometric mean of candidate/stock throughput; below one is slower',
        lower_upper='95% paired request-cluster bootstrap bounds on throughput speedup',
        not_a_latency_ratio=True,
        warning='candidate/stock latency is not this ratio; natural-EOS output lengths can differ'))


def json_record(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as destination:
        json.dump(value, destination, indent=2, sort_keys=True, allow_nan=False)
        destination.write('\n')
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


class Budget:
    def __init__(self, path, *, now=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock():
            if not self.path.exists():
                save(self.path, dict(started=time.time() if now is None else now,
                    wall_seconds=86400, gpu_seconds=230400, concurrent_gpus=8, jobs=[]))
            state = self.read()
            if (state['gpu_seconds'], state['wall_seconds'], state['concurrent_gpus']) != (230400, 86400, 8):
                raise ValueError('persisted authorized resource ceilings changed')

    @contextmanager
    def lock(self):
        with self.path.with_suffix('.lock').open('a') as destination:
            fcntl.flock(destination, fcntl.LOCK_EX)
            yield

    def read(self):
        return json.loads(self.path.read_text())

    def reserve(self, name, gpus, seconds, *, now=None):
        now = time.time() if now is None else now
        if type(gpus) is not int or gpus not in (1, 2, 4, 8) or type(seconds) is not int or seconds < 1:
            raise ValueError('invalid resource reservation')
        with self.lock():
            state = self.read()
            if any(row['name'] == name for row in state['jobs']):
                raise ValueError('name already reserved; never replay an uncertain submission')
            charged = sum(row.get('charged_gpu_seconds', row['gpus'] * row['seconds']) for row in state['jobs'])
            active = sum(row['gpus'] for row in state['jobs'] if not row.get('terminated'))
            if (now + seconds > state['started'] + state['wall_seconds'] or
                    charged + gpus * seconds > state['gpu_seconds'] or
                    active + gpus > state['concurrent_gpus']):
                raise ValueError('stage wall/GPU/concurrency budget would be exceeded')
            state['jobs'].append(dict(name=name, gpus=gpus, seconds=seconds,
                reserved_unix=now, terminated=False, create_calls=0))
            save(self.path, state)

    def update(self, name, **values):
        if set(values) - {'create_calls', 'uuid', 'submission_code', 'started', 'terminal', 'terminated', 'charged_gpu_seconds'}:
            raise ValueError('unsupported resource receipt')
        with self.lock():
            state = self.read()
            row = next(row for row in state['jobs'] if row['name'] == name)
            if row['terminated'] or (values.get('terminated') and not values.get('terminal')):
                raise ValueError('terminal resources require an immutable terminal receipt')
            if 'create_calls' in values and (row['create_calls'] or values['create_calls'] != 1):
                raise ValueError('create must be called exactly once')
            if 'charged_gpu_seconds' in values and (type(values['charged_gpu_seconds']) is not int or
                    values['charged_gpu_seconds'] < 0 or not values.get('terminated')):
                raise ValueError('only confirmed termination can release a reservation')
            row.update(values)
            save(self.path, state)
