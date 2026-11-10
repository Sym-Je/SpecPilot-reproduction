"""Supervise one read-only DSH capability design; no device execution."""
import fcntl
import json
import time
from prepare_baseline import OUT,write,sha
from parallel_research import call_role


def main(role='capability-prefix-cache-preflight-design'):
    assert role in ('capability-prefix-cache-preflight-design','review-prefix-cache-init-metadata')
    area=OUT/'research/parallel/roles'/role
    with (area/'supervisor.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=json.loads((area/'primary-before.json').read_text())
        current=json.loads((OUT/'research/state.json').read_text())
        assert current['status']=='needs_harness_capability'
        assert current['active_role']==before['active_role']=='cont-master-7'
        assert not current['validation_opened'] and current['rounds']==before['rounds']
        current.update(status='researching',active_mode='capability_design',active_role=role,
                       pending_primary_role=before['active_role'])
        write(OUT/'research/state.json',current)
        failure=None
        try:
            request=json.loads((area/'request.json').read_text())
            call_role(role,'direction',request['prompt'])
        except BaseException as error:
            failure=repr(error)
            raise
        finally:
            after=json.loads((OUT/'research/state.json').read_text())
            assert after['active_role']==role and not after['validation_opened']
            receipt={'origin':'supervisor capability review, not primary Master decision',
                     'epoch':time.time(),'role':role,'error':failure,
                     'result_sha256':sha(area/'result.json') if (area/'result.json').exists() else None,
                     'npu_execution_authorized':False}
            before.setdefault('capability_design_reviews',[]).append(receipt)
            budget=json.loads((OUT/'billing-gpt/state.json').read_text())
            if budget.get('budget_exhausted'):before['status']='api_budgets_exhausted'
            elif failure:before.update(status='needs_attention',error=failure)
            write(OUT/'research/state.json',before)
            write(area/'supervisor-result.json',receipt)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--role',default='capability-prefix-cache-preflight-design',choices=('capability-prefix-cache-preflight-design','review-prefix-cache-init-metadata'))
    main(parser.parse_args().role)
