"""Resume an admitted direction only after its unique experiment restores stock."""
import fcntl
import json
from pathlib import Path
import subprocess
import time

from prepare_baseline import ROOT,OUT,write
from experiment_lifecycle import wait_final


def main():
    role='cont-d4-sparse-attention-runtime-work'
    folder=OUT/'experiments'/f'{role}-cpu-work-two-step-v1'
    with (folder/'resume.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record=folder/'research-resume.json'
        if record.exists():return
        while True:
            state=wait_final(folder/'state.json',60)
            if state['status'] in ('complete','failed') and not state.get('cleanup_pending'):break
        if not state.get('baseline_restored'):
            write(record,{'status':'requires_baseline_recovery','experiment_state':state});return
        research=json.loads((OUT/'research/state.json').read_text())
        if research.get('validation_opened') or research.get('active_role')!=role:
            write(record,{'status':'not_resumed_research_scope_changed'});return
        with (OUT/'research/resume-after-admitted-diagnostic.log').open('ab') as log:
            process=subprocess.Popen([str(ROOT/'.dsh-venv/bin/python'),str(OUT/'continue_research.py'),'--resume'],
                cwd=OUT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        import psutil
        write(OUT/'research/supervisor.json',{'pid':process.pid,'birth':psutil.Process(process.pid).create_time(),
              'started_epoch':time.time(),'kind':'research_after_admitted_diagnostic'})
        write(record,{'status':'research_resumed','pid':process.pid,'started_epoch':time.time(),
                      'experiment_status':state['status'],'baseline_restored':True})


if __name__=='__main__':main()
