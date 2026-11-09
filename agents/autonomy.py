"""Bounded research actions: the master owns allocation, the direction owns experiments."""

import re

from agents.exploration import require_text,references

LIMITS=dict(actions=24,runs=8)


def validate_budget(budget):
    if set(budget)!=set(LIMITS) or any(type(budget[key]) is not int or not 0<=budget[key]<=limit for key,limit in LIMITS.items()):
        raise ValueError('budget outside approved CPU-only ceiling')


def validate_plan(plan,evidence):
    directions=plan.get('directions')
    if not isinstance(directions,list) or not 1<=len(directions)<=2:raise ValueError('one or two directions required')
    if len({row['id'] for row in directions})!=len(directions):raise ValueError('duplicate direction')
    for row in directions:
        if row['id']=='master' or not re.fullmatch('[a-z][a-z0-9-]{0,63}',row['id']):raise ValueError('invalid direction id')
        require_text(row['hypothesis'])
        references(row['evidence_refs'],evidence)
        validate_budget(row['budget'])
    if any(sum(row['budget'][key] for row in directions)>limit for key,limit in LIMITS.items()):
        raise ValueError('combined allocation exceeds stage budget')


def validate_action(action):
    if not isinstance(action,dict):raise ValueError('action object required')
    required=dict(write_file={'kind','path','content'},read_file={'kind','path'},run_python={'kind','path'},
        list_stock={'kind','prefix','offset'},read_stock={'kind','path','offset'},
        finish={'kind','disposition','observations','tool_refs','limitations'})
    kind=action.get('kind')
    if kind not in required or set(action)!=required[kind]:raise ValueError('unknown or malformed action; GPU is not authorized')
    if kind=='write_file':
        if not isinstance(action['content'],str) or len(action['content'].encode())>32768:raise ValueError('file payload exceeds limit')
    if kind in ('list_stock','read_stock') and (type(action['offset']) is not int or action['offset']<0):
        raise ValueError('invalid source offset')
    if kind=='finish':
        if action['disposition'] not in ('stop','needs_evidence','candidate_pending_validation'):raise ValueError('invalid direction disposition')
        require_text(action['observations'])
        if not isinstance(action['limitations'],list) or not action['limitations']:raise ValueError('evidence limitations required')
