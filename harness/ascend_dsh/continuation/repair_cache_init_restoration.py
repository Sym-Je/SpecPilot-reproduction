"""Bounded stock-only restoration recovery under the machine lock; no API billing."""
import fcntl
import json
import time
import psutil
import shlex
from prepare_baseline import OUT,ROOT,write,sha
from run_baseline import launch,stop_owned,HTTP,URL
from startup_guard import fatal_graph_failure


def wait_ready(owner,log):
    deadline=time.monotonic()+1800
    while time.monotonic()<deadline:
        process=psutil.Process(owner['pid'])
        assert process.create_time()==owner['birth'] and process.status()!='zombie'
        if log.exists():
            with log.open('rb') as f:
                size=f.seek(0,2);f.seek(max(0,size-128*1024));tail=f.read().decode(errors='replace')
            if fatal_graph_failure(tail):raise RuntimeError('Confirmed stock baseline graph-init failure')
        try:
            if HTTP.get(URL+'/health',timeout=3).status_code==200:return
        except Exception:pass
        time.sleep(5)
    raise TimeoutError('Stock restoration deadline')


def existing_stock_owner():
    selection=json.loads((ROOT/'deployment/selected/selection.json').read_text())
    owner={'pid':selection['owner_pid'],'birth':selection['owner_create_time']}
    expected=shlex.split(next(line[5:] for line in (OUT/'launch-mrv1.sh').read_text().splitlines() if line.startswith('exec ')))
    try:
        process=psutil.Process(owner['pid'])
        matching=(process.create_time()==owner['birth'] and process.status()!='zombie'
                  and process.cmdline()[1:]==expected[1:]
                  and selection['selected_mode']=='MRV1-fixed-DSpark-K7')
    except psutil.NoSuchProcess:matching=False
    try:healthy=HTTP.get(URL+'/health',timeout=3).status_code==200
    except Exception:healthy=False
    if healthy:
        response=HTTP.get(URL+'/v1/models',timeout=5);response.raise_for_status()
        models=response.json()
        if not matching or not any(row.get('id')=='deepseek-v4-flash' for row in models.get('data',[])):
            raise RuntimeError('Existing live endpoint is not verified stock baseline; refuse duplicate launch')
        return owner
    if matching:
        raise RuntimeError('Existing selected stock process is still alive but unready; refuse duplicate launch')
    return None


def main():
    folder=OUT/'experiments/capability-cache-init-off-plan-v1'
    record={'status':'queued','origin':'trusted recovery of failed original baseline restoration',
            'baseline_script_sha256':sha(OUT/'launch-mrv1.sh'),'attempts':[],'model_api_calls':0}
    write(folder/'restoration-recovery.json',record)
    with (ROOT/'evaluation/npu-workload.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads((folder/'state.json').read_text());assert state['status']=='failed' and state.get('baseline_restored') is False
        write(folder/'state-before-restoration-recovery.json',state)
        record.update(status='recovering',lock_acquired_epoch=time.time());write(folder/'restoration-recovery.json',record)
        for index in range(1,3):
            assert sha(OUT/'launch-mrv1.sh')==record['baseline_script_sha256']
            attempt={'index':index,'started_epoch':time.time()};record['attempts'].append(attempt)
            directory=folder/f'restored-baseline-retry-{index}';owner=None
            try:
                owner=existing_stock_owner()
                if owner:attempt['reused_existing_stock']=True
                else:owner=launch(OUT/'launch-mrv1.sh',directory)
                attempt['owner']=owner
                write(folder/'restoration-recovery.json',record)
                wait_ready(owner,directory/'server.log')
            except Exception as error:
                attempt.update(status='failed',error=repr(error),completed_epoch=time.time())
                if owner and not attempt.get('reused_existing_stock'):
                    try:stop_owned(owner)
                    except psutil.NoSuchProcess:pass
                write(folder/'restoration-recovery.json',record)
                if index==2:record['status']='needs_attention';write(folder/'restoration-recovery.json',record);raise
                time.sleep(10);continue
            attempt.update(status='healthy',completed_epoch=time.time())
            selection=json.loads((ROOT/'deployment/selected/selection.json').read_text())
            selection.update(owner_pid=owner['pid'],owner_create_time=owner['birth'])
            write(ROOT/'deployment/selected/selection.json',selection)
            state=json.loads((folder/'state.json').read_text());state['baseline_restored']=True
            state['post_finalize_restoration_recovery']={'epoch':time.time(),'record':'restoration-recovery.json','owner':owner}
            write(folder/'state.json',state)
            record.update(status='recovered',completed_epoch=time.time());write(folder/'restoration-recovery.json',record)
            for _ in range(10):
                primary=json.loads((OUT/'research/state.json').read_text())
                if primary['active_role']=='cont-master-7':break
                time.sleep(1)
            assert primary['active_role']=='cont-master-7' and not primary['validation_opened']
            primary.setdefault('restoration_recoveries',[]).append({'epoch':time.time(),'experiment':folder.name,'owner':owner})
            primary.update(status='needs_harness_capability',needs_local_supervision=True)
            primary.pop('error',None);write(OUT/'research/state.json',primary)
            receipt=json.loads((OUT/'research/cache-init-observations.json').read_text())
            receipt['initial_restoration_failed']=True;receipt['baseline_restored']=True
            receipt['post_finalize_recovery']=state['post_finalize_restoration_recovery'];write(OUT/'research/cache-init-observations.json',receipt)
            return


if __name__=='__main__':main()
