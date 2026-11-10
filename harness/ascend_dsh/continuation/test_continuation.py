import copy
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from experiment_runner import make_launch, validate_config
from prepare_baseline import OUT, ROOT, sha, write
from profile_workload import select_requests, export_quality
from research_broker import Broker


class ContinuationTests(unittest.TestCase):
    def test_every_supported_profile_scope_matches_frozen_requests(self):
        for concurrency in (1, 8, 32):
            for stratum in ('short', 'mid', 'long'):
                config = {'screen_concurrency': concurrency, 'profile_stratum': stratum}
                case, entries = select_requests(config)
                original = json.loads(Path(case['input_path']).read_text())['data'][:concurrency]
                self.assertEqual(len(entries), concurrency)
                self.assertEqual(case['stratum'], stratum)
                for actual, expected in zip(entries, original):
                    self.assertEqual(actual['session_id'], expected['session_id'])
                    payload = copy.deepcopy(expected['payloads'][0])
                    payload.update(stream=True, stream_options={'include_usage': True}, max_tokens=128)
                    self.assertEqual(actual['payloads'][0], payload)

    def test_changed_input_is_rejected_before_execution(self):
        manifest = json.loads((OUT / 'baseline-input-manifest.json').read_text())
        next(c for c in manifest['cases'] if c['name'] == 'mid-c1')['input_sha256'] = 'wrong'
        with self.assertRaisesRegex(AssertionError, 'Frozen dev input changed'):
            select_requests({}, manifest)

    def test_capture_window_reaches_actual_engine_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_launch({'screen_concurrency': 32, 'profile_stratum': 'long', 'profile_steps': 4}, Path(tmp), profile=True)
            argv = shlex.split(next(l[5:] for l in path.read_text().splitlines() if l.startswith('exec ')))
            config = json.loads(argv[argv.index('--profiler-config') + 1])
            self.assertEqual(config['max_iterations'], 4)
            self.assertTrue(config['ignore_frontend'])
            self.assertFalse(config['torch_profiler_with_stack'])
            self.assertNotIn('--enforce-eager', argv)

    def test_scope_validation_does_not_open_sampling_or_model_changes(self):
        for invalid in ({'profile_steps': 0}, {'profile_steps': True}, {'profile_steps': 33},
                        {'profile_stratum': 'validation'}, {'profile_phase': 'arbitrary'},
                        {'screen_concurrency': 64}, {'temperature': 1}, {'model': 'other'},
                        {'tensor_parallel_size': 16}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_config(invalid)

    def test_plain_launch_preserves_baseline_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = make_launch({}, Path(tmp)).read_text()
            self.assertEqual(actual, (OUT / 'launch-mrv1.sh').read_text())

    def test_cumulative_claude_ledger_is_shared_not_reset(self):
        old = ROOT / 'profiling/specpilot-ctrip-dsh-20261109/billing/state.json'
        self.assertTrue((OUT / 'billing/state.json').samefile(old))
        ledger = json.loads(old.read_text())
        self.assertEqual(ledger['limit_micro_usd'], 200_000_000)
        self.assertGreaterEqual(ledger['conservative_reserved_micro_usd'], 110_354_120)

    def test_quality_needs_all_ranks_and_no_loss_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'launch.sh').write_text('')
            for i in range(8):
                rank = directory / 'traces' / f'rank{i}_ascend_pt'
                rank.mkdir(parents=True)
                (rank / 'kernel_details.csv').write_text('Name,Duration(us)\nTestKernel,1.5\n')
                (rank / 'trace_view.json').write_text('{}')
            result = export_quality(directory)
            self.assertTrue(result['all_eight_ranks_complete'])
            (directory / 'traces/rank7_ascend_pt/trace_view.json').unlink()
            self.assertFalse(export_quality(directory)['all_eight_ranks_complete'])
            (directory / 'traces/rank7_ascend_pt/trace_view.json').write_text('{}')
            log = directory / 'server.log'; log.write_text('WARNING: TLV data lost\n')
            self.assertFalse(export_quality(directory, log)['all_eight_ranks_complete'])

    def test_second_experiment_is_denied_during_restoration(self):
        with tempfile.TemporaryDirectory() as tmp, patch('research_broker.OUT', Path(tmp)):
            root = Path(tmp)
            broker = Broker('serial-fixture', 'direction')
            folder = root / 'experiments/serial-fixture-first'
            folder.mkdir(parents=True)
            write(folder / 'state.json', {'status': 'failed', 'lock_acquired_epoch': 1})
            broker.state['experiments'] = ['serial-fixture-first']
            with self.assertRaisesRegex(RuntimeError, 'finish restoration'):
                broker.act('launch_experiment', {'id': 'second', 'mode': 'profile',
                                               'config': {'screen_concurrency': 32}})
            self.assertFalse((root / 'experiments/serial-fixture-second').exists())


if __name__ == '__main__':
    unittest.main()
