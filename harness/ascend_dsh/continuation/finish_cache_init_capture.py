"""Publish one terminal initialization capture after restoration; no model calls."""
import fcntl
import json
import time
from prepare_baseline import OUT,write
from experiment_lifecycle import wait_final,finalized


def main():
    folder=OUT/'experiments/capability-cache-init-off-plan-v1'
    with (folder/'watcher.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            state=wait_final(folder/'state.json',60)
            if finalized(state):break
            write(folder/'watcher-state.json',{'status':'waiting_for_terminal_restoration','epoch':time.time(),
                  'experiment_status':state['status'],'phase':state.get('phase')})
        primary=json.loads((OUT/'research/state.json').read_text())
        assert primary['active_role']=='capability-cache-init-off' and not primary['validation_opened']
        before=json.loads((OUT/'research/before-cache-init-capture.json').read_text())
        receipt={'origin':'trusted initialization-only capability capture, not scientific optimization result',
                 'id':folder.name,'epoch':time.time(),'status':state['status'],
                 'baseline_restored':state.get('baseline_restored'),
                 'error':state.get('error'),'cache_initialization':state.get('cache_initialization'),
                 'runner_submitted_generation_requests':state.get('runner_submitted_generation_requests'),
                 'full_prefix_capability_ready':False,'enabled_support_validated':False}
        before.setdefault('initialization_capability_captures',[]).append(receipt)
        if state.get('lock_acquired_epoch') and state.get('baseline_restored') is not True:
            before.update(status='needs_attention',error='Initialization capture did not restore baseline')
        write(OUT/'research/cache-init-observations.json',receipt)
        write(OUT/'research/state.json',before)
        write(OUT/'research/supervisor.json',json.loads((OUT/'research/supervisor-before-cache-init-capture.json').read_text()))
        write(folder/'watcher-state.json',{'status':'complete','epoch':time.time(),'primary_status':before['status'],
              'full_prefix_capability_ready':False})


if __name__=='__main__':main()
