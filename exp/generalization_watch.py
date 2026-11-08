"""Read-only lifecycle monitor; only the public status directory is inspected."""

import argparse
import datetime
import json
from pathlib import Path
import time

from kubernetes import client,config


def watch(uuid,public,record):
    config.load_kube_config()
    core,custom=client.CoreV1Api(),client.CustomObjectsApi()
    deadline=time.monotonic()+32400
    with record.with_suffix('.jsonl').open('x') as history:
        while time.monotonic()<deadline:
            snapshot=dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),uuid=uuid)
            try:
                job=custom.get_namespaced_custom_object('batch.volcano.sh','v1alpha1','qiji','jobs',uuid)
                pod=core.read_namespaced_pod(uuid+'-master-0','qiji')
                snapshot.update(job_phase=job.get('status',{}).get('state',{}).get('phase'),
                    actual_queue=job['spec'].get('queue'),pod_phase=pod.status.phase,pod_uid=pod.metadata.uid,
                    job_retry_count=job.get('status',{}).get('retryCount'),node=pod.spec.node_name,containers=[])
                for container in pod.status.container_statuses or []:
                    terminated,running=container.state.terminated,container.state.running
                    snapshot['containers'].append(dict(name=container.name,restart_count=container.restart_count,
                        exit_code=terminated.exit_code if terminated else None,reason=terminated.reason if terminated else None,
                        started_at=str(terminated.started_at if terminated else running.started_at if running else None),
                        finished_at=str(terminated.finished_at) if terminated else None))
                if pod.status.phase in ('Succeeded','Failed'):
                    record.with_suffix('.pod.log').write_text(core.read_namespaced_pod_log(pod.metadata.name,'qiji',timestamps=True))
            except client.exceptions.ApiException as error:
                snapshot['query_error_status']=error.status
            status=public/'exit-status'
            events=public/'events.jsonl'
            try:
                if status.exists():snapshot['script_exit']=status.read_text().strip()
                if events.exists():
                    lines=events.read_text().splitlines()
                    if lines:snapshot['public_progress']=json.loads(lines[-1])
            except (PermissionError,json.JSONDecodeError) as error:
                snapshot['public_status_error']=type(error).__name__
            history.write(json.dumps(snapshot)+'\n');history.flush()
            record.with_suffix('.latest.json').write_text(json.dumps(snapshot,indent=2))
            print(json.dumps(snapshot),flush=True)
            if snapshot.get('pod_phase') in ('Succeeded','Failed'):
                record.with_suffix('.final.json').write_text(json.dumps(snapshot,indent=2))
                break
            time.sleep(30)
        else:
            raise TimeoutError('monitor deadline; inspect existing job before any further submission')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uuid');parser.add_argument('public',type=Path);parser.add_argument('record',type=Path)
    args=parser.parse_args()
    watch(args.uuid,args.public,args.record)
