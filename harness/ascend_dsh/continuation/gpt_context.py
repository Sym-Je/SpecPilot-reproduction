"""Bounded, attributed checkpoints when native context exceeds admission size.

The complete native trajectory remains intact. Session rollover retains the
same broker identity, allocations, scratch and cumulative budget; no NPU replay.
"""
import hashlib
import json
from pathlib import Path
import time

from prepare_baseline import write, sha


def bounded_prompt(prompt):
    if len(prompt) <= 24000:
        return prompt
    return prompt[:12000] + '\n[Middle of long request omitted; its final task/schema follows.]\n' + prompt[-12000:]


def input_limit_failure(result):
    return any(event.get('type') == 'turn/end'
        and 'Request exceeds input byte limit' in event.get('data', {}).get('reason', {}).get('error', {}).get('message', '')
        for event in result.get('events', []))


def rotate_session(root, role, previous_session, original_prompt, receipt_sha256):
    directory = root / 'research-gpt/session-routing'
    directory.mkdir(parents=True, exist_ok=True)
    route_path = directory / (role + '.json')
    prior = json.loads(route_path.read_text()) if route_path.exists() else {}
    generation = prior.get('generation', 0) + 1
    session_id = f'{role}-gpt-c{generation}'
    folder = root / 'research/roles' / role
    broker = json.loads((folder / 'broker-state.json').read_text()) if (folder / 'broker-state.json').exists() else {}
    records = [json.loads(line) for line in (folder / 'broker.jsonl').read_text().splitlines()] if (folder / 'broker.jsonl').exists() else []
    inventory = []
    for item in records[-120:]:
        args = item.get('arguments', {})
        inventory.append({'id':item.get('id'), 'tool':item.get('tool'),
            'arguments':{k:v for k,v in args.items() if k != 'content'},
            'source_sha256':item.get('result',{}).get('sha256'), 'error':item.get('error')})
    recent = []
    for item in records[-6:]:
        encoded = json.dumps(item, ensure_ascii=False)
        recent.append({'record_excerpt':encoded[:8000], 'excerpt_truncated':len(encoded)>8000})
    scratch = []
    for path in sorted((folder/'scratch').rglob('*'))[-8:]:
        if not path.is_file() or path.is_symlink() or path.suffix not in ('.py','.json','.patch'):
            continue
        content = path.read_text(errors='replace')
        scratch.append({'path':str(path.relative_to(folder/'scratch')), 'sha256':sha(path),
                        'content':content[:6000], 'excerpt_truncated':len(content)>6000})
    experiments = []
    for eid in broker.get('experiments', []):
        path = root/'experiments'/eid/'state.json'
        if path.exists():
            state = json.loads(path.read_text())
            row = {k:state[k] for k in ('id','status','error','restore_error','baseline_restored','completed_epoch','comparison') if k in state}
            row['request'] = {k:state.get('request',{}).get(k) for k in ('config','mode')}
            row['state_sha256'] = sha(path)
            experiments.append(row)
    checkpoint = {'origin':'trusted_context_rollover_not_independent_rediscovery',
        'previous_session':previous_session, 'prior_receipt_sha256':receipt_sha256,
        'original_prompt':bounded_prompt(original_prompt), 'original_prompt_truncated':len(original_prompt)>24000,
        'original_prompt_sha256':hashlib.sha256(original_prompt.encode()).hexdigest(),
        'broker_state_unchanged':broker, 'completed_action_inventory':inventory,
        'recent_tool_receipts':recent, 'own_scratch':scratch, 'owned_experiments':experiments,
        'instruction':'Continue the same allocated task and return its requested JSON. Do not repeat completed experiments/source reads or reset allocations. Reuse evidence with attribution. Full original native logs remain preserved; omitted facts are unknown, not negative evidence. Existing scratch can be executed by its saved path. Read completed owned profiles through the broker if needed.'}
    checkpoint_path = directory/f'{role}-checkpoint-{generation}.json'
    write(checkpoint_path, checkpoint)
    if checkpoint_path.stat().st_size > 180000:
        raise RuntimeError('Checkpoint too large; preserve it for explicit supervision')
    routing = {'session_id':session_id,'generation':generation,'previous_session':previous_session,
               'checkpoint_path':str(checkpoint_path.relative_to(root)), 'checkpoint_sha256':sha(checkpoint_path),
               'created_epoch':time.time()}
    write(route_path,routing)
    return routing
