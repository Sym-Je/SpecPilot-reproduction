"""Real DSH sessions with a native budget hook and restricted broker tools.

SpecPilot's outer scheduler allocates roles; native DSH tool loops call the broker.
The DSH native session log is the model trajectory; this is not claimed to be
DSH's native goal scheduler. Model code runs only in the isolated CPU worker.
"""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import re
import signal
import time

from budget import HERE, MODEL, credential


def plain(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    return value


def call(session_id, prompt, system, max_tokens=4096, *, prefix='research', patch=None, deadline_seconds=600):
    from deepseek_harness import DeepSeekHarness
    assert re.fullmatch(r'[a-z0-9-]{1,96}', session_id)
    directory = HERE / prefix
    home, work, results = directory / 'dsh-home', directory / 'workspace', directory / 'calls'
    for p in (home, work, results): p.mkdir(mode=0o700, parents=True, exist_ok=True)
    for key in list(os.environ):
        if key.lower().endswith('_proxy'): del os.environ[key]
    os.environ['NO_PROXY'] = '*'; os.environ['no_proxy'] = '*'
    secret = credential()
    before = list(home.rglob('session.v4.jsonl'))
    exists = any(p.parent.name == session_id for p in before)
    call_id = f'{session_id}-{time.time_ns()}'
    started = time.time()
    # SDK's ordinary request timeout does not bound later stream activity.
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('DSH activity deadline')))
    signal.alarm(deadline_seconds)
    try:
        with DeepSeekHarness(
            dsh_home=str(home), cwd=str(work), profile='sdk-minimal',
            provider='deepseek-official', model=MODEL, max_tokens=max_tokens,
            base_url='https://northgate.xiaobei.top/v1', api_key=secret,
            env={'DSH_SYSTEM_PROMPT': system, 'DSH_CONTEXT_WINDOW': '131072', 'SP_ROLE_ID': session_id},
            patches=(str(patch or HERE / 'research.patch.yml'),),
        ) as harness:
            session = harness.resume_session(session_id) if exists else harness.start_session(session_id)
            result = session.run(prompt)
        signal.alarm(0)
        record = {'call_id': call_id, 'session_id': session_id, 'model': MODEL,
                  'started_epoch': started, 'completed_epoch': time.time(), 'resumed': exists,
                  'result': plain(result), 'sdk': '0.2.1rc2', 'api_route': 'direct NorthGate HTTPS'}
        text = json.dumps(record, ensure_ascii=False, indent=2, default=plain)
        assert secret not in text
        (results / f'{call_id}.json').write_text(text + '\n')
        assert result.finish_reason == 'completed', result.finish_reason
        return result.final_response, record
    finally:
        signal.alarm(0)


def probe():
    first, r1 = call('budget-trajectory-probe',
        'Reply with exactly this JSON object: {"probe":"ctrip-budget-v1","nonce":"c39c8a1d"}.',
        'You are testing a bounded model transport. No tools. Return only the requested JSON.',
        max_tokens=256, prefix='preflight')
    assert json.loads(first) == {'probe': 'ctrip-budget-v1', 'nonce': 'c39c8a1d'}
    second, r2 = call('budget-trajectory-probe',
        'Return exactly a JSON object with the same nonce from the previous turn and no other fields.',
        'You are testing a bounded model transport. No tools. Return only the requested JSON.',
        max_tokens=256, prefix='preflight')
    assert json.loads(second) == {'nonce': 'c39c8a1d'}
    assert r2['resumed']
    events = []
    for p in (HERE / 'preflight/dsh-home').rglob('session.v4.jsonl'):
        events += [json.loads(l) for l in p.open() if l.strip()]
    headers = [e['data']['header'] for e in events if e.get('type') == 'request/header']
    assert headers and all(not h.get('tools') for h in headers)
    billing = json.loads((HERE / 'billing/state.json').read_text())
    reservations = list(billing['reservations'].values())
    assert len(reservations) == 2
    assert all(r['status'] == 'settled_without_refund' for r in reservations)
    assert all(r['request']['model'] == MODEL for r in reservations)
    report = {'passed': True, 'model': MODEL, 'native_sessions': 1, 'model_calls': 2,
              'native_tools': 0, 'fresh_process_resume': True, 'budget_reservations': 2,
              'reserved_usd': billing['conservative_reserved_micro_usd'] / 1e6,
              'observed_shared_gateway_delta_usd': billing['observed_gateway_delta_micro_usd'] / 1e6,
              'research_started': False, 'note': 'Only a non-data transport/budget preflight.'}
    (HERE / 'dsh-budget-preflight.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('probe',))
    parser.parse_args()
    probe()
