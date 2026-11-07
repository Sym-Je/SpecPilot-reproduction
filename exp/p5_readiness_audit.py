"""Read-only synthetic interface audit, not a correctness or promotion gate."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from controller.http_transport import Arm, HttpPairBench
from controller.token_force import judge_forcing
from exp.p3_pair_run import parse_args as pair_args


def forcing_probe(name, base, candidate, expectation):
    try:
        result = judge_forcing(base, candidate)
        passed = {'reject': not result.lossless, 'accept': result.lossless,
                  'rate_flagged': result.rate_flagged}[expectation]
        observed = result.to_dict()
    except Exception as error:
        passed = expectation == 'reject' and isinstance(error, ValueError)
        observed = {'exception': type(error).__name__, 'message': str(error)}
    return {'name': name, 'expectation': expectation, 'passed': passed,
            'observed': observed}


def divergence_probe():
    bench = HttpPairBench(Arm('synthetic-a', ''), Arm('synthetic-b', ''))
    fixture = {'a_tps': [100.0], 'b_tps': [102.5],
               'rounds': [{'a': {'output_sha256': 'synthetic-a'},
                           'b': {'output_sha256': 'synthetic-b'}}]}
    with patch.object(bench, 'run_pair', return_value=fixture):
        result = bench.compare([1], max_new=1, noise=0.0, reps=2)
    return {'name': 'divergent_output_below_three_percent',
            'expectation': 'no promotion at synthetic 2.5% gain with differing output',
            'passed': not result['promoted'], 'observed': result,
            'scope': 'synthetic fixture, no HTTP request or GPU measurement'}


def null_entrypoint_probe():
    captured = io.StringIO()
    with redirect_stderr(captured):
        try:
            arguments = pair_args(['stock', 'stock', '--out-dir', '/unused-plan-only'])
            observed = {'arms': arguments.arms, 'execute': arguments.execute}
            passed = not arguments.execute
        except SystemExit as error:
            passed = False
            observed = {'exit_code': error.code, 'stderr': captured.getvalue()}
    return {'name': 'stock_null_entrypoint',
            'expectation': 'non-executing plan for two independent stock instances',
            'passed': passed, 'observed': observed,
            'scope': 'CLI reachability only; does not validate a null session'}


def audit():
    probes = [
        forcing_probe('empty_requests', [], [], 'reject'),
        forcing_probe('empty_tokens', [[]], [[]], 'reject'),
        forcing_probe('truncated_output', [[1, 2, 3]], [[1, 2]], 'reject'),
        forcing_probe('extended_output', [[1, 2]], [[1, 2, 3]], 'reject'),
        forcing_probe('missing_output', [[1, 2, 3]], [[]], 'reject'),
        forcing_probe('identical_long_output', [[1] * 4096], [[1] * 4096], 'accept'),
        forcing_probe('complete_divergence_rate_rule', [[1] * 1000],
                      [[2] * 1000], 'rate_flagged'),
        divergence_probe(),
        null_entrypoint_probe(),
    ]
    sources = ['controller/token_force.py', 'controller/stats.py',
               'controller/http_transport.py', 'exp/p3_pair_run.py',
               'exp/p5_readiness_audit.py', 'docs/02-acceptance.md',
               'docs/11-reproduction-plan.md']
    return {'created_utc': datetime.now(timezone.utc).isoformat(),
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                            text=True).strip(),
            'working_tree_short': subprocess.check_output(
                ['git', 'status', '--short'], cwd=ROOT, text=True).splitlines(),
            'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in sources},
            'scope': 'synthetic CPU interface audit only; not real forcing or noise calibration',
            'gpu_tasks_submitted': 0, 'ledger_eligible': False,
            'production_ready': False,
            'real_evidence_pending': ['same-prefix stock-engine FP32-head scorer and margins',
                                      'stock mismatch and delta calibration',
                                      'real post-2048 logit-bias fault rejection',
                                      'equivalent-reduction false-rejection control',
                                      'fresh dual-server stock null sessions with GPU swaps',
                                      'maintainer-confirmed statistics and promotion integration'],
            'checks': probes,
            'contract_checks_passed': all(probe['passed'] for probe in probes),
            'failed_checks': [probe['name'] for probe in probes if not probe['passed']]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    arguments = parser.parse_args(argv)
    with arguments.out.open('x') as destination:
        result = audit()
        json.dump(result, destination, indent=2, ensure_ascii=False, allow_nan=False)
        destination.write('\n')
    for probe in result['checks']:
        print(f'{"PASS" if probe["passed"] else "FAIL"}: {probe["name"]}')
    print('NOT READY: synthetic probes cannot authorize real promotion, sealed or RSI')
    print(f'evidence={arguments.out}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
