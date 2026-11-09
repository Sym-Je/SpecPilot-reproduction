"""Persistent admission for every native DSH model request; no network proxy.

Amounts are integer micro-USD. Reserve a deliberately high token-price ceiling
before dispatch. Reservations are NOT refunded, including failures/restarts.
Gateway usage is also checked cumulatively; concurrent use of the shared key
can only consume this task's remaining budget sooner, never increase it.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import time
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
MODEL = 'claude-opus-5-5'
LIMIT_MICRO_USD = 500_000_000
QUOTA_PER_USD = 500_000
INPUT_CEILING_USD_PER_M = 10
OUTPUT_CEILING_USD_PER_M = 50
MAX_REQUEST_BYTES = 512 * 1024
MAX_OUTPUT_TOKENS = 8192
GATEWAY = 'https://northgate.xiaobei.top'


def credential():
    value = os.environ.get('north_gate_claude_key')
    if value:
        return value
    for line in (Path.home() / '.bashrc').read_text().splitlines():
        if re.match(r'^\s*(?:export\s+)?north_gate_claude_key\s*=', line):
            parts = shlex.split(line.strip().removeprefix('export ').strip(), comments=True)
            if len(parts) == 1:
                value = parts[0].split('=', 1)[1]
                if value and '$' not in value and '`' not in value:
                    return value
    raise RuntimeError('Configured NorthGate credential unavailable')


def get_json(path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(GATEWAY + path,
        headers={'Authorization': 'Bearer ' + credential()})
    with opener.open(request, timeout=30) as response:
        return json.load(response)


def gateway_snapshot():
    status = get_json('/api/status')
    assert status['data']['quota_per_unit'] == QUOTA_PER_USD
    assert status['data']['quota_display_type'] == 'USD'
    usage = get_json('/api/usage/token/')
    assert usage['code'] is True
    total = usage['data']['total_used']
    assert type(total) is int and total >= 0
    logs = get_json('/api/log/token/')
    assert logs['success'] is True
    rows = logs['data']
    if isinstance(rows, dict):
        rows = rows.get('items', rows.get('logs', []))
    rows = [r for r in rows if r.get('model_name') == MODEL and r.get('quota', 0) > 0]
    assert rows, 'No actual gateway price evidence; refuse paid calls'
    # Gateway returns newest rows first. Keep only billing facts, no identities.
    row = rows[0]
    other = json.loads(row['other'])
    model_ratio, group_ratio = other['model_ratio'], other['group_ratio']
    assert other['model_price'] == -1 and other.get('user_group_ratio', -1) == -1
    assert model_ratio > 0 and group_ratio > 0
    base = model_ratio * group_ratio * 1_000_000 / QUOTA_PER_USD
    cache_write = max(1, other.get('cache_creation_ratio', 1), other.get('cache_creation_ratio_1h', 1))
    rates = {'input_ceiling_observed_usd_per_m': base * cache_write,
             'output_observed_usd_per_m': base * other['completion_ratio'],
             'model_ratio': model_ratio, 'group_ratio': group_ratio,
             'completion_ratio': other['completion_ratio']}
    assert rates['input_ceiling_observed_usd_per_m'] <= INPUT_CEILING_USD_PER_M
    assert rates['output_observed_usd_per_m'] <= OUTPUT_CEILING_USD_PER_M
    return {'epoch': time.time(), 'total_used_quota': total,
            'key_is_unlimited': usage['data']['unlimited_quota'], 'rates': rates,
            'note': 'Observed gateway billing rates, checked before every request; not an account-wide quota mutation.'}


def reserve_amount(input_bytes, max_tokens):
    if type(input_bytes) is not int or not 0 <= input_bytes <= MAX_REQUEST_BYTES:
        raise ValueError('Request exceeds input byte limit')
    if type(max_tokens) is not int or not 0 < max_tokens <= MAX_OUTPUT_TOKENS:
        raise ValueError('Request output cap invalid')
    # Count every UTF-8 byte as a token and add 8192 for provider framing.
    # Price ceilings include cache writes and exceed current observed rates.
    return ((input_bytes + 8192) * INPUT_CEILING_USD_PER_M
            + max_tokens * OUTPUT_CEILING_USD_PER_M + 10000)


class Budget:
    def __init__(self, directory=HERE / 'billing'):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.state_path = self.directory / 'state.json'

    def transact(self, action, payload, snapshot):
        with (self.directory / 'mutex').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.state_path.exists():
                state = json.loads(self.state_path.read_text())
            else:
                state = {'schema': 'northgate-budget-v1', 'model': MODEL,
                         'limit_micro_usd': LIMIT_MICRO_USD, 'reservations': {},
                         'start_gateway_quota': snapshot['total_used_quota'],
                         'conservative_reserved_micro_usd': 0, 'observed_gateway_delta_micro_usd': 0,
                         'created_epoch': time.time(), 'stopped': False}
            assert state['limit_micro_usd'] == LIMIT_MICRO_USD
            delta = snapshot['total_used_quota'] - state['start_gateway_quota']
            if delta < 0:
                raise RuntimeError('Gateway usage counter reset; refuse admission')
            state['observed_gateway_delta_micro_usd'] = max(
                state['observed_gateway_delta_micro_usd'], math.ceil(delta * 1_000_000 / QUOTA_PER_USD))
            state['latest_gateway_snapshot'] = snapshot
            if action == 'reserve':
                if state['stopped']:
                    raise RuntimeError('Budget stopped')
                assert payload['model'] == MODEL
                role_id = payload.get('role_id', 'unknown')
                if sum(r['request'].get('role_id', 'unknown') == role_id for r in state['reservations'].values()) >= 96:
                    raise RuntimeError('Per-role 96 model request limit reached')
                amount = reserve_amount(payload['input_bytes'], payload['max_tokens'])
                used = max(state['conservative_reserved_micro_usd'], state['observed_gateway_delta_micro_usd'])
                if used + amount > state['limit_micro_usd']:
                    raise RuntimeError('500 USD budget admission denied')
                rid = uuid.uuid4().hex
                row = {'id': rid, 'reserved_micro_usd': amount, 'request': payload,
                       'created_epoch': time.time(), 'status': 'reserved_before_dispatch'}
                state['reservations'][rid] = row
                state['conservative_reserved_micro_usd'] += amount
                result = {'reservation_id': rid, 'reserved_micro_usd': amount}
            elif action == 'settle':
                row = state['reservations'][payload['reservation_id']]
                assert row['status'] == 'reserved_before_dispatch', 'Duplicate settlement'
                row.update(status='settled_without_refund', usage=payload.get('usage'),
                           finish=payload.get('finish'), completed_epoch=time.time())
                result = {'reservation_id': row['id'], 'settled': True}
            elif action == 'status':
                result = {}
            else:
                raise ValueError('Unknown budget operation')
            used = max(state['conservative_reserved_micro_usd'], state['observed_gateway_delta_micro_usd'])
            state['stopped'] = used >= state['limit_micro_usd']
            state['last_updated_epoch'] = time.time()
            tmp = self.state_path.with_suffix('.tmp')
            with tmp.open('w') as f:
                json.dump(state, f, ensure_ascii=False, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
            tmp.replace(self.state_path)
            with (self.directory / 'events.jsonl').open('a') as f:
                f.write(json.dumps({'epoch': time.time(), 'action': action, 'result': result,
                                    'reserved_micro_usd': state['conservative_reserved_micro_usd'],
                                    'observed_gateway_delta_micro_usd': state['observed_gateway_delta_micro_usd']}) + '\n')
                f.flush(); os.fsync(f.fileno())
            return result | {'limit_usd': 500, 'reserved_usd': state['conservative_reserved_micro_usd'] / 1e6,
                             'gateway_delta_usd': state['observed_gateway_delta_micro_usd'] / 1e6,
                             'remaining_admission_usd': max(0, state['limit_micro_usd'] - used) / 1e6}


if __name__ == '__main__':
    import sys
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('reserve', 'settle', 'status'))
    args = parser.parse_args()
    payload = json.load(sys.stdin) if args.action != 'status' else {}
    print(json.dumps(Budget().transact(args.action, payload, gateway_snapshot())))
