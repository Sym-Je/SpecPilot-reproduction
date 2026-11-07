import copy
import json
import math
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from exp import p3_pair_run as runner


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return [ord(character) for character in messages[0]['content']]


class FakeServer:
    events = []
    fail_arm = None

    def __init__(self, arm, gpu, port, output_dir, environment):
        self.arm = arm
        self.gpu = gpu
        self.port = port
        self.started = False

    def start(self):
        self.started = True
        self.events.append(('start', self.arm['name'], self.gpu['index']))
        if self.arm['name'] == self.fail_arm:
            raise RuntimeError('synthetic startup failure')

    def wait_ready(self, timeout):
        self.events.append(('ready', self.arm['name'], self.gpu['index']))

    def stop(self):
        if self.started:
            self.events.append(('stop', self.arm['name'], self.gpu['index']))
            self.started = False


class FakeBench:
    fail_request = None

    def __init__(self, arm_a, arm_b):
        self.arm_a = arm_a
        self.arm_b = arm_b

    def run_pair(self, input_ids, max_new, warmup=0, swap=False, rid=''):
        if rid == self.fail_request:
            raise RuntimeError('synthetic request failure')
        if swap or warmup:
            raise AssertionError('controller logical swap/per-request warmup must be off')
        results = []
        for arm in (self.arm_a, self.arm_b):
            tokens = [5, 6]
            speed = 1.0 if arm.name == 'ar' else 4.0
            results.append({'tokens_per_s': speed, 'tokens': len(tokens),
                            'latency_ms': len(tokens) / speed * 1000,
                            'tau': None if arm.name == 'ar' else 2.0,
                            'spec_verify_ct': 0 if arm.name == 'ar' else 1,
                            'output_ids': tokens, 'output_sha256': runner.sha_ids(tokens),
                            'input_sha256': runner.sha_ids(input_ids),
                            'finish_reason': 'stop', 'server_e2e_s': 1.0,
                            'tau_source': 'per_verify_step'})
        return {'rounds': [{'a': results[0], 'b': results[1]}]}


class PairRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        FakeServer.events = []
        FakeServer.fail_arm = None
        FakeBench.fail_request = None
        self.gpus = [{'index': 0, 'uuid': 'synthetic-gpu-0'},
                     {'index': 1, 'uuid': 'synthetic-gpu-1'}]
        self.arms = [{'name': 'ar', 'block': 0, 'tree_sha': 'synthetic-stock',
                      'engine': '/synthetic/stock'},
                     {'name': 'stock', 'block': 8, 'tree_sha': 'synthetic-stock',
                      'engine': '/synthetic/stock'}]
        self.requests = [{'id': f'{suite}-{index}', 'suite': suite,
                          'input_ids': [index + 1],
                          'input_sha256': runner.sha_ids([index + 1])}
                         for suite in ('suite-a', 'suite-b') for index in range(2)]

    def run_round(self, round_index=0, requests=None):
        return runner.run_round(
            self.arms, self.gpus, [31000, 31010], round_index,
            self.requests if requests is None else requests,
            self.directory / f'round-{round_index + 1:02d}', {},
            max_new=2048, warmup=1, startup_timeout=30,
            server_factory=FakeServer, bench_factory=FakeBench)

    def test_physical_gpu_mapping_swaps_and_servers_are_fresh(self):
        first = self.run_round(0)
        second = self.run_round(1)
        starts = [event for event in FakeServer.events if event[0] == 'start']
        stops = [event for event in FakeServer.events if event[0] == 'stop']
        self.assertEqual(starts, [('start', 'ar', 0), ('start', 'stock', 1),
                                  ('start', 'ar', 1), ('start', 'stock', 0)])
        self.assertEqual(len(stops), 4)
        self.assertEqual(first[0]['a']['gpu_uuid'], 'synthetic-gpu-0')
        self.assertEqual(second[0]['a']['gpu_uuid'], 'synthetic-gpu-1')
        self.assertLess(FakeServer.events.index(('stop', 'stock', 1)),
                        FakeServer.events.index(('start', 'ar', 1)))

    def test_round_outputs_have_one_record_per_request_and_matching_inputs(self):
        pairs = self.run_round()
        self.assertEqual(len(pairs), len(self.requests))
        for arm in ('ar', 'stock'):
            rows = [json.loads(line) for line in
                    (self.directory / 'round-01' / f'{arm}.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), len(self.requests))
            self.assertEqual({row['id'] for row in rows},
                             {request['id'] for request in self.requests})
            self.assertTrue(all(row['max_new_tokens'] == 2048 for row in rows))
        for pair in pairs:
            self.assertEqual(pair['a']['input_sha256'], pair['b']['input_sha256'])
        self.assertEqual(len((self.directory / 'round-01' / 'pairs.jsonl')
                             .read_text().splitlines()), len(self.requests))

    def test_startup_failure_cleans_both_servers(self):
        FakeServer.fail_arm = 'stock'
        with self.assertRaisesRegex(RuntimeError, 'startup failure'):
            self.run_round()
        self.assertEqual(len([event for event in FakeServer.events if event[0] == 'stop']), 2)

    def test_failed_request_keeps_only_complete_prior_pairs(self):
        FakeBench.fail_request = 'round-1|suite-a-1'
        with self.assertRaisesRegex(RuntimeError, 'request failure'):
            self.run_round()
        pair_file = self.directory / 'round-01' / 'pairs.jsonl'
        self.assertEqual(len(pair_file.read_text().splitlines()), 1)
        self.assertEqual(len([event for event in FakeServer.events if event[0] == 'stop']), 2)
        self.assertFalse((self.directory / 'round-01' / 'complete.json').exists())

    def test_summary_is_geomean_and_rounds_are_not_independent_requests(self):
        pairs = self.run_round(0) + self.run_round(1)
        summary = runner.summarize(pairs, self.requests, 2, iters=2000)
        self.assertAlmostEqual(summary['geomean'], 4.0)
        self.assertAlmostEqual(summary['lower'], 4.0)
        self.assertAlmostEqual(summary['upper'], 4.0)
        self.assertEqual(summary['n_requests'], 4)
        self.assertEqual(summary['n_pairs'], 8)
        self.assertFalse(summary['ledger_eligible'])
        changed = copy.deepcopy(pairs)
        for pair in changed:
            pair['b']['tokens_per_s'] = 16.0 if pair['id'] == 'suite-a-0' else 1.0
        summary = runner.summarize(changed, self.requests, 2)
        self.assertAlmostEqual(summary['geomean'], math.pow(16, 0.25))

    def test_summary_rejects_missing_or_duplicate_pairs(self):
        pairs = self.run_round(0) + self.run_round(1)
        with self.assertRaises(ValueError):
            runner.summarize(pairs[:-1], self.requests, 2)
        with self.assertRaises(ValueError):
            runner.summarize(pairs + [pairs[0]], self.requests, 2)

    def test_summary_rejects_unequal_suite_coverage(self):
        requests = self.requests[:-1]
        pairs = self.run_round(0, requests) + self.run_round(1, requests)
        with self.assertRaisesRegex(ValueError, 'suite'):
            runner.summarize(pairs, requests, 2)

    def test_inherited_final_options_are_not_given_to_stock(self):
        with patch.dict('os.environ', {'SPECPILOT_D8R_TLV': '1',
                                       'SPECPILOT_DATA': '/synthetic/data'}):
            environment = runner.clean_environment()
        self.assertNotIn('SPECPILOT_D8R_TLV', environment)
        self.assertEqual(environment['SPECPILOT_DATA'], '/synthetic/data')

    def test_missing_suite_or_insufficient_items_is_rejected(self):
        suite_file = self.directory / 'suite-a.jsonl'
        suite_file.write_text(json.dumps({'id': 'one', 'suite': 'suite-a',
                                          'turns': ['hello']}) + '\n')
        with self.assertRaises(ValueError):
            runner.load_requests(2, ['suite-a'], FakeTokenizer(), self.directory)
        with self.assertRaises(FileNotFoundError):
            runner.load_requests(1, ['missing'], FakeTokenizer(), self.directory)

    def test_launch_reuses_single_arm_script_in_server_only_mode(self):
        server = runner.Server(self.arms[0], self.gpus[0], 31000, self.directory, {})
        command, environment = server.launch_spec()
        self.assertEqual(command[:2], ['bash', str(runner.ROOT / 'exp/p3_pair.sh')])
        self.assertEqual(command[2:5], ['ar', 'synthetic-gpu-0', '31000'])
        self.assertEqual(environment['P3_SERVER_ONLY'], '1')
        self.assertEqual(environment['SP_ENGINE'], '/synthetic/stock')
        self.assertEqual(environment['P3_SERVER_LOG'], str(self.directory / 'ar.server.log'))

    def test_cli_defaults_to_plan_and_rejects_invalid_rounds_or_ports(self):
        args = runner.parse_args(['ar', 'stock', '--out-dir', str(self.directory / 'out')])
        self.assertFalse(args.execute)
        for arguments in (['--rounds', '1'], ['--rounds', '3'], ['--gpus', '0', '0'],
                          ['--ports', '31000', '31001']):
            with self.assertRaises(SystemExit):
                runner.parse_args(['ar', 'stock', '--out-dir', str(self.directory / 'out')]
                                  + arguments)

    def test_port_probe_reuses_closed_server_with_time_wait(self):
        for attempt in range(20):
            with socket.socket() as listener, socket.socket() as adjacent:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
                if port == 65535:
                    continue
                try:
                    adjacent.bind(('127.0.0.1', port + 1))
                except OSError:
                    continue
                listener.listen()
                with socket.create_connection(listener.getsockname()) as client:
                    connection, address = listener.accept()
                    with connection:
                        connection.shutdown(socket.SHUT_WR)
                        self.assertEqual(client.recv(1), b'')
                listener.close()
                adjacent.close()
                runner.check_ports([port])
                return
        self.fail('could not reserve two adjacent ports')

    def test_port_probe_rejects_live_listener_with_reuseaddr(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaises(OSError):
                runner.check_ports([listener.getsockname()[1]])

    def test_existing_gpu_processes_are_rejected_without_being_killed(self):
        queries = ['0, synthetic-gpu-0, NVIDIA H100, 518, 60\n'
                   '1, synthetic-gpu-1, NVIDIA H100, 518, 60\n',
                   'synthetic-gpu-0, 59780\n']
        with patch.object(runner.subprocess, 'check_output', side_effect=queries), \
                patch.object(runner.os, 'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, 'existing compute processes'):
                runner.inspect_gpus([0, 1])
        kill.assert_not_called()

    def test_idle_wait_handles_delayed_gpu_release(self):
        with patch.object(runner, 'inspect_gpus', side_effect=[RuntimeError('busy'), self.gpus]), \
                patch.object(runner.time, 'sleep'):
            self.assertEqual(runner.wait_for_idle([0, 1]), self.gpus)

    def test_round_output_cannot_be_silently_reused(self):
        self.run_round()
        prior_events = list(FakeServer.events)
        with self.assertRaises(FileExistsError):
            self.run_round()
        self.assertEqual(FakeServer.events, prior_events)

    def test_real_controller_http_transport_with_synthetic_servers(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond({'model_path': 'synthetic-model'})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.server.seen.append(body)
                self.respond({'output_ids': [5, 6],
                              'meta_info': {'completion_tokens': 2, 'e2e_latency': 0.01,
                                            'spec_verify_ct': self.server.verify,
                                            'finish_reason': {'type': 'stop'}}})

            def respond(self, value):
                payload = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                pass

        http_servers = [ThreadingHTTPServer(('127.0.0.1', 0), Handler) for _ in self.arms]
        ports = [server.server_address[1] for server in http_servers]
        for server, verify in zip(http_servers, (0, 1)):
            server.verify = verify
            server.seen = []
            self.addCleanup(server.server_close)

        class HttpServer:
            def __init__(self, arm, gpu, port, output_dir, environment):
                self.server = http_servers[ports.index(port)]
                self.thread = None

            def start(self):
                self.thread = threading.Thread(target=self.server.serve_forever)
                self.thread.start()

            def wait_ready(self, timeout):
                pass

            def stop(self):
                self.server.shutdown()
                self.thread.join(timeout=5)

        pairs = runner.run_round(self.arms, self.gpus, ports, 0, self.requests,
                                 self.directory / 'http-round', {}, max_new=2048,
                                 warmup=1, startup_timeout=30, server_factory=HttpServer)
        self.assertEqual(len(pairs), len(self.requests))
        for server in http_servers:
            self.assertEqual(len(server.seen), len(self.requests) + 1)
            self.assertEqual(server.seen[0]['sampling_params']['max_new_tokens'], 32)
        self.assertEqual([body['input_ids'] for body in http_servers[0].seen],
                         [body['input_ids'] for body in http_servers[1].seen])


if __name__ == '__main__':
    unittest.main()
