"""Bounded research decisions; observations and execution remain broker-owned."""

import copy
import re

from harness.master_proposal import AXES, text, texts


LIMITS = dict(actions=240, cpu_runs=32, model_turns=16, wall_seconds=1800, directions=2)
MASTER_ALLOCATION = dict(actions=96, cpu_runs=16)
KINDS = frozenset(('compare','revise','observe','dispatch','continue','stop'))


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[a-z][a-z0-9-]{0,35}',value):
        raise ValueError('bounded lowercase opportunity/evidence ID required')
    return value


def validate_decision(action, state):
    if not isinstance(action,dict) or action.get('kind') not in KINDS:
        raise ValueError('only research decisions allowed; no GPU, shell or execution command authority')
    kind = action['kind']
    fields = {'kind','reason','based_on'}
    if kind in ('compare','revise'):
        fields |= {'opportunities','axis_assessments'}
    elif kind == 'observe':
        fields |= {'evidence'}
    elif kind in ('dispatch','continue'):
        fields |= {'id','brief','allocation'}
    if set(action) != fields:
        raise ValueError('decision fields differ from the requested schema')
    text(action['reason'])
    based = action['based_on']
    if not isinstance(based,list) or len(based)>16 or len(set(based))!=len(based) or any(value not in state.evidence for value in based):
        raise ValueError('decision references evidence that has not been delivered')
    if kind in ('compare','revise'):
        axes = action['axis_assessments']
        if not isinstance(axes,dict) or set(axes)!=AXES:
            raise ValueError('all four research dimensions require an assessment')
        for value in axes.values():
            text(value)
        cards = action['opportunities']
        if not isinstance(cards,list) or not 2<=len(cards)<=6:
            raise ValueError('compare two to six opportunities, not a single predetermined answer')
        seen=set()
        for card in cards:
            if not isinstance(card,dict) or set(card)!={'id','axis','mechanism','potential_gain','added_cost','unknowns','cheapest_check','priority','evidence'}:
                raise ValueError('opportunity needs mechanism, benefit, added cost, uncertainty and cheapest evidence')
            identity=identifier(card['id'])
            if identity in seen or card['axis'] not in AXES or card['priority'] not in ('explore','diagnose','defer'):
                raise ValueError('unique opportunity ID, recognized axis and explicit priority required')
            seen.add(identity)
            for field in ('mechanism','potential_gain','added_cost','cheapest_check'):
                text(card[field])
            texts(card['unknowns'])
            references=card['evidence']
            if not isinstance(references,list) or not references or any(value not in state.evidence for value in references):
                raise ValueError('opportunity needs delivered evidence, not an invented source')
        if kind=='revise' and not any(value in state.feedback_ids for value in based):
            raise ValueError('revision must explicitly acknowledge actual feedback')
    elif kind=='observe':
        if action['evidence'] not in state.evidence:
            raise ValueError('observation must select a registered evidence ID')
    elif kind in ('dispatch','continue'):
        identity=identifier(action['id'])
        if identity not in state.opportunities:
            raise ValueError('compare opportunities before assigning a direction')
        text(action['brief'])
        allocation=action['allocation']
        if (not isinstance(allocation,dict) or set(allocation)!={'actions','cpu_runs'} or
                any(type(allocation[key]) is not int or not 0<=allocation[key]<=maximum
                    for key,maximum in (('actions',64),('cpu_runs',8))) or
                (kind=='dispatch' and allocation['actions']==0)):
            raise ValueError('direction allocation exceeds the CPU-only role envelope')
        if kind=='continue':
            own_feedback={'direction-'+identity+'-'+str(number).zfill(2)
                for number in range(1,state.directions.get(identity,{}).get('returns',0)+1)}
            if not own_feedback.intersection(based):
                raise ValueError('continuation must reference its own returned feedback')
    return action


class DecisionState:
    def __init__(self,evidence):
        self.evidence=copy.deepcopy(evidence)
        self.feedback_ids=set()
        self.opportunities={}
        self.directions={}
        self.axis_assessments={}
        self.events=[]
        self.revisions=0
        self.stopped=False

    def snapshot(self):
        return dict(evidence=copy.deepcopy(self.evidence),feedback_ids=sorted(self.feedback_ids),
            opportunities=copy.deepcopy(self.opportunities),directions=copy.deepcopy(self.directions),
            axis_assessments=copy.deepcopy(self.axis_assessments),events=copy.deepcopy(self.events),
            revisions=self.revisions,stopped=self.stopped,gpu_authorized=False)

    def apply(self,action):
        if self.stopped:
            raise ValueError('research is already stopped')
        validate_decision(action,self)
        updated=copy.deepcopy(self)
        updated._apply(copy.deepcopy(action))
        self.__dict__.update(updated.__dict__)
        return self.events[-1]

    def _apply(self,action):
        kind=action['kind']
        if kind in ('compare','revise'):
            self.opportunities={card['id']:card for card in action['opportunities']}
            self.axis_assessments=action['axis_assessments']
            self.revisions+=kind=='revise'
        elif kind in ('dispatch','continue'):
            identity=action['id']
            if kind=='dispatch':
                if identity in self.directions or len(self.directions)>=LIMITS['directions']:
                    raise ValueError('new direction already exists or role limit exhausted')
                self.directions[identity]=dict(allocated=dict(actions=0,cpu_runs=0),used=dict(actions=0,cpu_runs=0),
                    pending=False,returns=0)
            elif identity not in self.directions:
                raise ValueError('continue requires an existing direction, not a fresh role')
            direction=self.directions[identity]
            if direction['pending']:
                raise ValueError('direction must return before being reassigned')
            for key,value in action['allocation'].items():
                direction['allocated'][key]+=value
                if MASTER_ALLOCATION[key]+sum(item['allocated'][key] for item in self.directions.values())>LIMITS[key]:
                    raise ValueError('cumulative CPU allocations exceed this stage; no reset or implicit extension')
            direction['pending']=True
        elif kind=='stop':
            if any(value['pending'] for value in self.directions.values()):
                raise ValueError('cannot stop with an unreturned CPU direction')
            self.stopped=True
        self.events.append(dict(kind='decision',action=action))

    def deliver(self,identity,value,*,source):
        identifier(identity)
        if self.stopped or identity in self.evidence:
            raise ValueError('feedback evidence is immutable and cannot be delivered after stop')
        packet=dict(value=copy.deepcopy(value),source=copy.deepcopy(source),historical_reuse=True)
        self.evidence[identity]=packet
        self.feedback_ids.add(identity)
        self.events.append(dict(kind='feedback',id=identity,packet=packet))

    def return_direction(self,identity,result,used):
        if identity not in self.directions or not self.directions[identity]['pending']:
            raise ValueError('CPU feedback requires a pending direction')
        updated=copy.deepcopy(self)
        direction=updated.directions[identity]
        if set(used)!={'actions','cpu_runs'}:
            raise ValueError('actual CPU accounting fields required')
        for key,value in used.items():
            if type(value) is not int or value<0 or direction['used'][key]+value>direction['allocated'][key]:
                raise ValueError('direction actual use exceeds cumulative allocation')
            direction['used'][key]+=value
        direction['pending']=False
        direction['returns']+=1
        evidence_id='direction-'+identity+'-'+str(direction['returns']).zfill(2)
        packet=dict(value=copy.deepcopy(result),historical_reuse=False)
        updated.evidence[evidence_id]=packet
        updated.feedback_ids.add(evidence_id)
        updated.events.append(dict(kind='direction_feedback',id=identity,evidence_id=evidence_id,result=result,used=used))
        self.__dict__.update(updated.__dict__)
        return evidence_id
