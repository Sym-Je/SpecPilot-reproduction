"""Bounded monitor used by trusted experiments; no-progress is a failed run."""
import json
import time


class ProgressDeadline:
    def __init__(self, now, stalled_seconds=300, total_seconds=3600):
        self.started = self.last_progress = now
        self.previous = None
        self.stalled_seconds = stalled_seconds
        self.total_seconds = total_seconds

    def observe(self, activity, now):
        if now - self.started > self.total_seconds:
            raise TimeoutError('AIPerf cell wall-clock deadline')
        signature = (activity['generated'], activity['running'], activity['waiting'])
        if signature != self.previous:
            self.previous = signature; self.last_progress = now
        if activity['running'] + activity['waiting'] and now - self.last_progress > self.stalled_seconds:
            raise TimeoutError('No token or queue progress for 300 seconds; preserve failed trace')


def wait_aiperf(process, directory, metrics):
    deadline = ProgressDeadline(time.monotonic())
    with (directory / 'server-activity.jsonl').open('x') as file:
        while process.poll() is None:
            value = metrics()
            file.write(json.dumps(value) + '\n'); file.flush()
            deadline.observe(value, time.monotonic())
            time.sleep(5)
    return process.returncode
