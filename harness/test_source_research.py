from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from controller.http_transport import sha_ids
from exp.p3_pair_run import SUITES, check_ports, run_round
from exp.source_research import SourceCapturedArm, audit
from harness.candidate import expected_arguments
from harness.source_candidate import build_bundle, candidate_arm, file_sha


class SourceResearchTests(unittest.TestCase):
    def test_actual_http_pair_replay_and_tamper_refusal(self):
        from harness.test_source_candidate import SourceCandidateTests
        fixture = SourceCandidateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        directory = root / 'remote'
        directory.mkdir()
        bundle = directory / 'bundle'
        build_bundle(fixture.base, fixture.patch_path, bundle)
        (root / 'patch.json').write_bytes(fixture.patch_path.read_bytes())
        (root / 'self-check.py').write_text('print("fixture check")\n')
        (root / 'cpu-receipt.json').write_text('{"fixture":true}\n')
        action = dict(kind='run_source', patch='scratch/option.json', self_check='scratch/check.py',
            per_suite=1, max_new_tokens=2048, reason='HTTP protocol fixture, not a scientific candidate')
        request = dict(mode='source-research', source_pin='a' * 40, action=action,
            patch_sha256=file_sha(root / 'patch.json'), self_check_sha256=file_sha(root / 'self-check.py'),
            cpu_receipt_sha256=file_sha(root / 'cpu-receipt.json'))
        (root / 'request.json').write_text(json.dumps(request))
        (root / 'source.tar').write_bytes(b'fixed trusted source fixture')
        arms = [dict(name='stock', block=8, tree_sha=fixture.base['stock_tree_sha'],
                    engine=str(fixture.stock), env={}), candidate_arm(bundle, enabled=True)]
        requests = [dict(id=suite, suite=suite, input_ids=[2, index], input_sha256=sha_ids([2, index]))
            for index, suite in enumerate(SUITES)]
        gpus = [dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0, 1)]
        ports = None
        for attempt in range(100):
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            try:
                check_ports([port, port + 2])
                ports = [port, port + 2]
                break
            except OSError:
                continue
        self.assertIsNotNone(ports)
        manifest = dict(action=action, source_pin='a' * 40, base=fixture.base, bundle=str(bundle), requests=requests,
            gpus=gpus, arms=arms, ports=ports, request_sha256=file_sha(root / 'request.json'),
            source_archive_sha256=file_sha(root / 'source.tar'))
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        serial = []

        class FixtureServer:
            def __init__(self, arm, gpu, port, output_dir, environment):
                self.arm, self.port, self.root = arm, port, output_dir
                self.number = len(serial) + 1
                serial.append(self.number)

            def start(self):
                arguments = expected_arguments(fixture.base, 8)

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *arguments):
                        pass

                    def send(self, value):
                        payload = json.dumps(value).encode()
                        self.send_response(200)
                        self.send_header('Content-Length', str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)

                    def do_GET(self):
                        self.send(arguments)

                    def do_POST(self):
                        self.rfile.read(int(self.headers['Content-Length']))
                        self.send(dict(output_ids=[9, 10], meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1, finish_reason=dict(type='stop'))))

                self.http = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
                self.thread = threading.Thread(target=self.http.serve_forever)
                self.thread.start()
                (self.root / f'{self.arm["name"]}.process.json').write_text(json.dumps(
                    dict(pid=self.number, start_ticks=self.number)))
                (self.root / f'{self.arm["name"]}.boundary.json').write_text(json.dumps(
                    dict(denied=dict(fixture=True), uid=60010 if self.arm['name'] == 'stock' else 60011)))

            def wait_ready(self, timeout):
                pass

            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
                (self.root / f'{self.arm["name"]}.stopped.json').write_text('{"stopped":true}')

        with patch('exp.p3_pair_run.Telemetry', side_effect=lambda *arguments, **options: nullcontext()):
            for number in (0, 1):
                round_dir = directory / f'round-{number + 1:02d}'
                def factory(name, url, **options):
                    return SourceCapturedArm(name, url, directory=round_dir, spec=fixture.base, **options)
                run_round(arms, gpus, ports, number, requests, round_dir, {}, 2048, 2, 3,
                    server_factory=FixtureServer, arm_factory=factory, stable_null=True)
        first = audit(directory)
        self.assertEqual(first['n_pairs'], 10)
        self.assertFalse(first['controller_accepted'])
        self.assertFalse(first['lossless_verified'])
        self.assertEqual(first, audit(directory))
        for relative in ('round-02/deployment.json', 'round-01/stock.stopped.json',
                         'round-02/candidate.boundary.json', 'round-01/warmup.jsonl', 'round-02/pairs.jsonl'):
            path = directory / relative
            original = path.read_bytes()
            path.write_text('{}\n')
            with self.subTest(path=relative), self.assertRaises((ValueError, KeyError, TypeError)):
                audit(directory)
            path.write_bytes(original)
        for name in ('patch.json', 'self-check.py', 'cpu-receipt.json', 'source.tar', 'request.json'):
            path = root / name
            original = path.read_bytes()
            path.write_bytes(b'changed')
            with self.subTest(path=name), self.assertRaises((ValueError, KeyError)):
                audit(directory)
            path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
