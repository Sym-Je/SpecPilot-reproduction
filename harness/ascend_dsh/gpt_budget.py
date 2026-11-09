"""Separate USD 500 GPT phase. No proxy, no credential in configuration/logs.

The local ceiling is not an account-wide quota. Reservations deliberately exceed
standard model prices; the gateway's cumulative actual charge is checked as well.
Historical aggregate rates are evidence, not a provider price guarantee. Any
unexplained/rising observed rate or billing counter reset fails closed.
"""
import argparse
from decimal import Decimal, ROUND_CEILING
import json
import os
from pathlib import Path
import stat
import sys
import time
import urllib.request

from budget import Budget as PersistentBudget, HERE

MODEL = 'gpt-6.1-sol'
LIMIT_MICRO_USD = 500_000_000
GATEWAY = 'https://dreamwalk.club'
KEY_FILE = Path.home() / '.config/northinfer/credentials/dreamwalk.key'


def credential():
    assert stat.S_IMODE(KEY_FILE.stat().st_mode) == 0o600, 'Private key file permissions required'
    value = KEY_FILE.read_text().strip()
    assert value and '\n' not in value
    return value


def get_json(path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(GATEWAY + path, headers={'Authorization': 'Bearer ' + credential()})
    with opener.open(request, timeout=30) as response:
        return json.load(response, parse_float=Decimal)


def micro_usd(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError('Invalid gateway USD counter')
    return int((amount * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def parse_snapshot(data):
    assert data['isValid'] is True and data['unit'] == 'USD'
    total = micro_usd(data['usage']['total']['actual_cost'])
    rows = [r for r in data['model_stats'] if r['model'] == MODEL and Decimal(str(r['cost'])) > 0]
    assert rows, 'Missing historical billing evidence for the exact target model'
    actual = sum(Decimal(str(r['actual_cost'])) for r in rows)
    nominal = sum(Decimal(str(r['cost'])) for r in rows)
    ratio = actual / nominal
    assert 0 < ratio <= 1, 'Gateway multiplier exceeds verified standard-rate allowance'
    # Even without separating cached input, 10/50 USD per million must dominate
    # aggregate actual billing. Cache creation is counted as input again to be
    # conservative with providers that report overlapping token categories.
    input_count = sum(int(r['input_tokens']) + int(r.get('cache_creation_tokens', 0))
                      + int(r.get('cache_read_tokens', 0)) for r in rows)
    output_count = sum(int(r['output_tokens']) for r in rows)
    ceiling = Decimal(input_count * 10 + output_count * 50) / 1_000_000
    assert actual <= ceiling and input_count + output_count > 0, 'Observed billing exceeds reserve rates'
    return {'epoch': time.time(), 'total_used_quota': total, 'rates': {
        'historical_actual_to_nominal_ratio': str(ratio),
        'input_reserve_usd_per_m': 10, 'output_reserve_usd_per_m': 50},
        'note': 'Shared-key cumulative actual_cost; task-local cap, not gateway account quota.'}


def gateway_snapshot():
    return parse_snapshot(get_json('/v1/usage'))


class Budget(PersistentBudget):
    def __init__(self, directory=HERE / 'billing-gpt'):
        super().__init__(directory, model=MODEL, limit_micro_usd=LIMIT_MICRO_USD, quota_per_usd=1_000_000)


def activated():
    state = json.loads((HERE / 'handoff/state.json').read_text())
    assert state['status'] == 'gpt_running', 'GPT handoff not active'
    research = json.loads((HERE / 'research/state.json').read_text())
    assert research['status'] == 'researching' and not research.get('validation_opened')
    assert not (HERE / 'candidate-freeze.json').exists(), 'Research cannot restart after freeze'
    assert not (HERE / 'final-validation/state.json').exists(), 'No model call after held-out stage'
    exhausted = json.loads((HERE / 'billing/state.json').read_text())
    assert exhausted.get('budget_exhausted'), 'Claude budget has not exhausted'
    assert exhausted['model'] == 'claude-opus-5-5' and exhausted['limit_micro_usd'] <= 200_000_000


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser(); p.add_argument('action', choices=('reserve', 'settle', 'status'))
    args = p.parse_args()
    activated()  # Prevent an accidental manual paid probe before the handoff.
    payload = json.load(sys.stdin) if args.action != 'status' else {}
    print(json.dumps(Budget().transact(args.action, payload, gateway_snapshot())))
