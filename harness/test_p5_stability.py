import copy
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from controller import http_transport as transport
from exp import p3_pair_run as runner
from harness.test_p3_pair_run import FakeBench, FakeServer
from harness import test_p5_null_validation as null_tests


class StableProtocolTests(unittest.TestCase):
    def test_protocol_requires_stock_and_four_rounds(self):
        args = runner.parse_args(['stock', 'stock', '--stable-null', '--rounds', '4', '--out-dir', '/unused'])
        self.assertTrue(args.stable_null)
        for arguments in (['ar', 'stock', '--rounds', '4'], ['stock', 'stock', '--rounds', '2']):
            with self.assertRaises(SystemExit):
                runner.parse_args(arguments + ['--stable-null', '--out-dir', '/unused'])

    def test_timing_encloses_http_without_changing_default_output(self):
        payload = json.dumps({'output_ids': [4, 5], 'meta_info': {'completion_tokens': 2, 'spec_verify_ct': 1}}).encode()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = payload
        with patch.object(transport.urllib.request, 'urlopen', return_value=response):
            result = transport.Arm('stock', 'http://local', trace_timing=True).step([1], 2)
            plain = transport.Arm('stock', 'http://local').step([1], 2)
        timing = result['client_timing']
        values = [timing[key] for key in ('step_start_ns', 'http_open_start_ns', 'body_complete_ns', 'step_end_ns')]
        self.assertEqual(values, sorted(values))
        self.assertEqual(timing['url'], 'http://local/generate')
        self.assertNotIn('client_timing', plain)

    def test_synchronized_dispatch_uses_two_party_barrier(self):
        baseline, candidate = MagicMock(), MagicMock()
        baseline.step.return_value = candidate.step.return_value = {'tokens_per_s': 1, 'tau': 1}
        with patch('threading.Barrier') as barrier:
            transport.HttpPairBench(baseline, candidate, synchronized_start=True).run_pair([1], 2, swap=False)
        barrier.assert_called_once_with(2)
        self.assertEqual(barrier.return_value.wait.call_count, 2)

    def test_reversed_submission_does_not_reverse_arm_identity(self):
        self.assertEqual(transport.HttpPairBench._synchronized(lambda: 'a', lambda: 'b', reverse=True), ('a', 'b'))

    def test_full_pass_warmup_is_separate_and_port_gpu_assignments_cross(self):
        class Bench(FakeBench):
            calls = []

            def __init__(self, *arms, **options):
                super().__init__(*arms)
                self.assert_sync = options['synchronized_start']

            def run_pair(self, input_ids, max_new, **options):
                self.calls.append((max_new, options['rid']))
                return super().run_pair(input_ids, max_new, **options)

        class Server(FakeServer):
            def __init__(self, *arguments):
                super().__init__(*arguments)
                self.process = SimpleNamespace(pid=100 + self.gpu['index'])

        arms = [{'name': name, 'block': 8, 'tree_sha': 'synthetic', 'engine': '/synthetic'}
                for name in ('stock-a', 'stock-b')]
        gpus = [{'index': index, 'uuid': f'gpu-{index}'} for index in (0, 1)]
        requests = [{'id': 'one', 'suite': 'suite', 'input_ids': [1], 'input_sha256': runner.sha_ids([1])}]
        FakeServer.fail_arm = FakeBench.fail_request = None
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'Telemetry'):
            assigned = []
            for index in range(4):
                output = Path(directory) / f'round-{index}'
                runner.run_round(arms, gpus, [31000, 31010], index, requests, output, {},
                                 2048, 2, 30, server_factory=Server, bench_factory=Bench, stable_null=True)
                deployment = json.loads((output / 'deployment.json').read_text())
                assigned.append([(entry['gpu']['index'], entry['port']) for entry in deployment['assignments']])
                warmup = [json.loads(line) for line in (output / 'warmup.jsonl').read_text().splitlines()]
                self.assertEqual([row['phase'] for row in warmup], ['short', 'short', 'full'])
                self.assertEqual(len((output / 'pairs.jsonl').read_text().splitlines()), 1)
            self.assertEqual({row[0] for row in assigned}, {(0, 31000), (1, 31000), (0, 31010), (1, 31010)})
        self.assertEqual(len(Bench.calls), 16)
        self.assertEqual(sum(cap == 32 for cap, _ in Bench.calls), 8)

    def test_telemetry_is_mockable_and_retains_sampling_errors(self):
        from harness.telemetry import Telemetry
        with tempfile.TemporaryDirectory() as directory:
            monitor = Telemetry([], [], Path(directory) / 'telemetry.jsonl')
            with patch.object(monitor, 'read_gpus', return_value=[]), patch.object(monitor, 'read_processes', return_value={}):
                sample = monitor.sample()
            self.assertNotIn('error', sample)
            with patch.object(monitor, 'read_gpus', side_effect=RuntimeError('unavailable')):
                sample = monitor.sample()
            self.assertIn('unavailable', sample['error'])


class StableValidationTests(unittest.TestCase):
    def setUp(self):
        helper = null_tests.NullValidationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.root = helper.root
        for first, second in ((1, 3), (2, 4)):
            shutil.copytree(self.root / f'round-{first:02d}', self.root / f'round-{second:02d}')
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest.update(rounds=4, stable_null=True, ports=[30100, 30110])
        self.write(self.root / 'manifest.json', manifest)
        all_pairs = []
        for number in range(1, 5):
            root = self.root / f'round-{number:02d}'
            ports = [30100, 30110] if number <= 2 else [30110, 30100]
            deployment = json.loads((root / 'deployment.json').read_text())
            deployment.update(round=number, stable_null=True)
            for entry, port in zip(deployment['assignments'], ports):
                entry['port'] = port
            self.write(root / 'deployment.json', deployment)
            pairs = [json.loads(line) for line in (root / 'pairs.jsonl').read_text().splitlines()]
            for index, pair in enumerate(pairs):
                pair.update(round=number, started_unix=210 + index * 3, finished_unix=212 + index * 3)
                for key, port in zip(('a', 'b'), ports):
                    pair[key].update(round=number, latency_s=2, latency_ms=2000, client_timing={'step_start_ns': 1,
                        'http_open_start_ns': 2, 'body_complete_ns': 2000000000,
                        'step_end_ns': 2000000001, 'started_unix': pair['started_unix'],
                        'url': f'http://127.0.0.1:{port}/generate'})
            self.rows(root / 'pairs.jsonl', pairs)
            for key, name in (('a', 'stock-a'), ('b', 'stock-b')):
                self.rows(root / f'{name}.jsonl', [pair[key] for pair in pairs])
            warmup = []
            for phase, subset in (('short', pairs[:2]), ('full', pairs)):
                for pair in subset:
                    item = copy.deepcopy(pair)
                    item['phase'] = phase
                    for key in ('a', 'b'):
                        item[key]['max_new_tokens'] = 32 if phase == 'short' else 2048
                        item[key]['client_timing']['started_unix'] = 111 + len(warmup) * 3
                    warmup.append(item)
            self.rows(root / 'warmup.jsonl', warmup)
            self.write(root / 'complete.json', {'round': number, 'pairs': 20})
            self.rows(root / 'events.jsonl', [{'event': 'servers_started', 'time_unix': 100},
                       {'event': 'servers_ready', 'time_unix': 110},
                       {'event': 'warmup_complete', 'time_unix': 200},
                       {'event': 'requests_complete', 'time_unix': 300}])
            samples = [{'time_unix': timestamp, 'gpus': [{'uuid': f'gpu-{gpu}', 'clocks_sm_mhz': 1500,
                        'clocks_mem_mhz': 1500, 'temperature_c': 60, 'power_w': 200} for gpu in (0, 1)],
                        'arms': {name: [{'pid': 1000 + number * 10 + index, 'start_ticks': number,
                                         'allowed_cpus': [0, 1]}] for index, name in enumerate(('stock-a', 'stock-b'))}}
                       for timestamp in (225, 235)]
            self.rows(root / 'telemetry.jsonl', samples)
            all_pairs.extend(pairs)
        summary = runner.summarize(all_pairs, manifest['requests'], 4, iters=64)
        summary.update(arms=['stock-a', 'stock-b'], max_new_tokens=2048, per_suite_requested=4)
        self.write(self.root / 'summary.json', summary)

    def write(self, path, value):
        path.write_text(json.dumps(value))

    def rows(self, path, values):
        path.write_text(''.join(json.dumps(value) + '\n' for value in values))

    def validate(self):
        from controller.stability_validation import validate_stable
        return validate_stable(self.root)

    def test_four_rounds_remain_twenty_request_clusters(self):
        result = self.validate()
        self.assertEqual((result['requests'], result['pairs'], result['arm_rows'], result['rounds']), (20, 80, 160, 4))
        self.assertTrue(result['precision_passed'])
        self.assertFalse(result['ledger_eligible'])

    def test_missing_full_warmup_is_rejected(self):
        path = self.root / 'round-01/warmup.jsonl'
        path.write_text('\n'.join(path.read_text().splitlines()[:-1]) + '\n')
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_telemetry_coverage_is_rejected(self):
        self.rows(self.root / 'round-01/telemetry.jsonl', [])
        with self.assertRaises(ValueError):
            self.validate()

    def test_non_crossed_ports_are_rejected(self):
        path = self.root / 'round-03/deployment.json'
        value = json.loads(path.read_text())
        value['assignments'][0]['port'] = 30100
        self.write(path, value)
        with self.assertRaises(ValueError):
            self.validate()

    def test_narrow_biased_null_is_not_stable(self):
        from controller import stability_validation
        result = self.validate()
        result['interval'] = dict(result['interval'], lower=1.003, upper=1.004)
        with patch.object(stability_validation, 'validate_null', return_value=result):
            checked = self.validate()
        self.assertTrue(checked['precision_passed'])
        self.assertFalse(checked['centered'])
        self.assertFalse(checked['stable_passed'])

    def test_primary_timing_cannot_be_missing(self):
        root = self.root / 'round-01'
        pairs = list(map(json.loads, (root / 'pairs.jsonl').read_text().splitlines()))
        pairs[0]['a'].pop('client_timing')
        self.rows(root / 'pairs.jsonl', pairs)
        self.rows(root / 'stock-a.jsonl', [pair['a'] for pair in pairs])
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == '__main__':
    unittest.main()
