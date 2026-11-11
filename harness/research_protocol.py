"""Identity-bound dynamic-tool dispatch with bounded, private audit records."""

import json
from pathlib import Path

from harness.research_tools import dispatch


class ResearchBroker:
    def __init__(self,work,records,thread,turn,max_actions=24,max_runs=4,dispatcher=None):
        self.work=Path(work)
        self.records=Path(records)
        self.records.mkdir(parents=True,exist_ok=False)
        self.thread=thread
        self.turn=turn
        self.max_actions=max_actions
        self.max_runs=max_runs
        self.actions=0
        self.runs=0
        self.calls=set()
        self.dispatcher=dispatch if dispatcher is None else dispatcher

    def handle(self,request):
        if (request.get('threadId')!=self.thread or request.get('turnId')!=self.turn or
                request.get('tool')!='research' or request.get('namespace') is not None):
            raise ValueError('tool request does not belong to the authorized role turn')
        call=request.get('callId')
        if not isinstance(call,str) or not call or len(call)>200 or call in self.calls:
            raise ValueError('missing or repeated tool call; do not replay uncertain actions')
        if self.actions>=self.max_actions:raise ValueError('research action budget exhausted')
        self.calls.add(call)
        self.actions+=1
        record=self.records/f'action-{self.actions:03d}'
        record.mkdir()
        (record/'request.json').write_text(json.dumps(request,indent=2)+'\n')
        try:
            arguments=request['arguments']
            if not isinstance(arguments,dict) or set(arguments)!={'action'}:raise ValueError('only an action is accepted')
            action=arguments['action']
            if isinstance(action,dict) and action.get('kind') in ('run_python','run_skill','read_profile_shapes'):
                if self.runs>=self.max_runs:raise ValueError('CPU run budget exhausted')
                self.runs+=1
            result=self.dispatcher(self.work,action,record/'execution')
            response=dict(success=True,contentItems=[dict(type='inputText',text=json.dumps(result))])
        except (ValueError,OSError,TypeError,KeyError) as error:
            response=dict(success=False,contentItems=[dict(type='inputText',text=json.dumps(dict(status='rejected',reason=str(error))))])
        (record/'response.json').write_text(json.dumps(response,indent=2)+'\n')
        return response
