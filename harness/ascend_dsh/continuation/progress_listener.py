"""Persistent local event journal and safe completed-dev CSV publication.

No model/API calls, device control, research decisions or notification claims.
The active chat consumes meaningful journal changes for user-facing updates.
"""
import fcntl
import hashlib
import json
import os
import time

import psutil
from prepare_baseline import OUT,write
from completed_profile_access import register


def snapshot():
    research=json.loads((OUT/'research/state.json').read_text())
    supervisor=json.loads((OUT/'research/supervisor.json').read_text())
    try:
        proc=psutil.Process(supervisor['pid'])
        alive=proc.status()!='zombie' and abs(proc.create_time()-supervisor['birth'])<0.1
    except psutil.NoSuchProcess:alive=False
    experiments=[]
    for p in sorted((OUT/'experiments').glob('*/state.json')):
        state=json.loads(p.read_text())
        experiments.append({'id':p.parent.name,'status':state.get('status'),'phase':state.get('phase'),
            'baseline_restored':state.get('baseline_restored'),'completed_epoch':state.get('completed_epoch')})
    return {'research_status':research['status'],'role':research['active_role'],'process_alive':alive,
        'rounds':len(research['rounds']),'validation_opened':research.get('validation_opened'),
        'error':research.get('error') if research['status']!='researching' else None,'experiments':experiments}


def main():
    area=OUT/'progress-listener';area.mkdir(exist_ok=True)
    with (area/'listener.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        previous=None;registered=set();errors={}
        while True:
            state=snapshot()
            for exp in state['experiments']:
                if exp['id'] in registered or exp['status']!='complete' or not exp['baseline_restored']:continue
                folder=OUT/'experiments'/exp['id']
                if not (folder/'profile-quality.json').exists():continue
                try:register(folder);registered.add(exp['id']);errors.pop(exp['id'],None)
                except (ValueError,OSError,KeyError) as error:errors[exp['id']]=repr(error)
            signature=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
            if signature!=previous:
                with (area/'events.jsonl').open('a') as log:
                    log.write(json.dumps({'epoch':time.time(),'snapshot':state},ensure_ascii=False)+'\n');log.flush()
                previous=signature
            write(area/'state.json',{'status':'listening','pid':os.getpid(),'updated_epoch':time.time(),
                'snapshot':state,'registered_profiles':sorted(registered),'publication_errors':errors,
                'notification_scope':'Local journal; user-facing updates require the active chat. No hosted push scheduler is available.'})
            time.sleep(30)


if __name__=='__main__':
    os.umask(0o077);main()
