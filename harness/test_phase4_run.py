from contextlib import contextmanager, nullcontext
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from controller.scored_forcing import read_reference
from controller.sealed_protocol import CAPS, PHASES, _frozen, _round, freeze_candidate
from exp import phase4_run
from exp import phase4_resource
from exp import source_research
from harness import test_sealed_protocol as protocol_tests
from harness import test_source_candidate as source_tests
from harness.candidate import expected_arguments, make_spec
from harness.source_candidate import build_bundle


class Phase4RunTests(unittest.TestCase):
    def setUp(self):
        self.helper = protocol_tests.SealedProtocolTests()
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)

    def cpu_private_boundary(self, mode):
        source = source_tests.SourceCandidateTests()
        source.setUp()
        self.addCleanup(source.doCleanups)
        directory = source.root / 'private-output'
        directory.mkdir(mode=0o700)
        arm = dict(name='stock', block=8, tree_sha=source.base['stock_tree_sha'], engine=str(source.stock), env={})
        server = phase4_run.PrivateSourceServer(arm, dict(index=0, uuid='GPU-fixture'), 30100, directory,
            dict(PATH=os.environ.get('PATH', ''), SP_TARGET='/fixture-target', SP_DRAFT='/fixture-draft'))
        original_popen = subprocess.Popen
        program = '''import json,os,stat,sys
payload=json.loads(sys.stdin.read())
if sys.argv[1]=='empty':
    sys.exit(17)
if sys.argv[1]=='malformed':
    os.write(payload['ready_fd'],b'{')
    sys.exit(18)
receipt=dict(event='SOURCE_BOUNDARY_READY',uid=payload['uid'],denied={'fixture_only':True},landlock_applied=True,seccomp_applied=True)
os.write(payload['ready_fd'],json.dumps(receipt).encode())
'''
        def child(command, **options):
            return original_popen([sys.executable, '-I', '-B', '-c', program, mode], **options)
        previous_umask = os.umask(0o077)
        try:
            with patch.object(phase4_run.os, 'geteuid', return_value=0), \
                    patch.object(phase4_run.os, 'chown') as chown, \
                    patch.object(source_research, 'device_paths', return_value=([], None)), \
                    patch.object(source_research.shutil, 'which', return_value=sys.executable), \
                    patch.object(phase4_run.subprocess, 'Popen', side_effect=child):
                server.start()
                chown.assert_called_once_with(server.sandbox / 'cache', 0, 60010)
        finally:
            os.umask(previous_umask)
            self.addCleanup(server.stop)
        return server, directory

    def test_umask077_private_boundary_permissions_and_cpu_ready(self):
        server, directory = self.cpu_private_boundary('ready')
        sandbox = server.sandbox
        expected = {'allowed.txt': 0o444, 'canary.txt': 0o600, 'trusted-bootstrap': 0o755,
                    'trusted-bootstrap/trusted_source_cache.py': 0o444, 'cache': 0o710, 'cache/work': 0o700}
        for name, mode in expected.items():
            with self.subTest(name=name):
                self.assertEqual(stat.S_IMODE((sandbox / name).stat().st_mode) & 0o777, mode)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode) & 0o777, 0o700)
        self.assertEqual(stat.S_IMODE((directory / 'stock.boundary.json').stat().st_mode) & 0o777, 0o600)
        payload = json.loads((directory / 'stock.sandbox.json').read_text())
        self.assertNotIn(str(directory), payload['readonly'])
        self.assertNotIn(str(phase4_run.ROOT), payload['readonly'])
        self.assertEqual((sandbox / 'trusted-bootstrap/trusted_source_cache.py').read_bytes(),
                         (phase4_run.ROOT / 'harness/source_cache.py').read_bytes())

    def test_private_boundary_empty_or_malformed_pipe_is_explicit(self):
        for mode in ('empty', 'malformed'):
            with self.subTest(mode=mode):
                try:
                    self.cpu_private_boundary(mode)
                except RuntimeError as error:
                    self.assertIsInstance(error, phase4_run.BoundaryHandshakeError)
                    self.assertRegex(str(error), 'boundary.*READY')
                    output = self.helper.base / f'public-error-{mode}'
                    output.mkdir(mode=0o755)
                    (output / 'private').mkdir(mode=0o700)
                    request = self.helper.save({'fixture': 'non-sensitive startup metadata'})
                    with patch.dict(os.environ, SP_PHASE4_SOURCE_SHA='a' * 64):
                        report = phase4_resource.publish_safe_error(request['path'], output, error)
                    public = json.loads(Path(report['path']).read_text())
                    self.assertEqual(public['error_type'], 'BoundaryHandshakeError')
                    self.assertTrue(any(frame['file'] == 'exp/phase4_run.py' and frame['function'] == 'start'
                                        for frame in public['frames']))
                else:
                    self.fail('missing/malformed READY cannot authorize a source server')

    def prepared_runtime(self, *, fail_at=None, fail_exit=False, science=None, speedup=1.2, fault=False):
        helper = self.helper
        helper.fixture(speedup=speedup, fault=fault)
        Path(helper.opened['path']).unlink()
        calls = []
        class Runtime:
            active = False
            @contextmanager
            def guard(self):
                calls.append('guard-enter')
                self.active = True
                try:
                    yield {'kind': 'CPU fixture, not kernel/GPU proof'}
                finally:
                    calls.append('guard-exit')
                    self.active = False
                    if fail_exit:
                        raise RuntimeError('fixture cleanup failed')
            def measure(self, arms, requests, directory, cap, number):
                if not self.active:
                    raise AssertionError('request access outside controller guard')
                phase = 'candidate' if arms[0]['name'] == 'stock' else (
                    'null-pre' if sum(isinstance(call, tuple) and call[:2] == (cap, 'null-pre')
                                      for call in calls) < 2 else 'null-post')
                calls.append((cap, phase, number))
                if len([call for call in calls if isinstance(call, tuple)]) == fail_at:
                    raise RuntimeError('fixture server failed')
                return copy.deepcopy(helper.records[cap, phase][number - 1])
            def score(self, root, requests, records):
                if not self.active:
                    raise AssertionError('score outside guard')
                if len(records) != 6:
                    raise AssertionError('score interfered with performance')
                calls.append('score')
                return helper.forcing, science
        return Runtime(), calls

    def test_exact_schedule_private_open_and_recomputed_schema(self):
        runtime, calls = self.prepared_runtime()
        original = phase4_run.open_phase4
        def opened(*arguments):
            self.assertTrue(runtime.active)
            self.assertEqual(calls, ['guard-enter'])
            return original(*arguments)
        with patch.object(phase4_run, 'open_phase4', opened):
            receipt = phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        result = read_reference(receipt, self.helper.root)
        expected = [(cap, phase, number) for cap in CAPS for phase in PHASES for number in (1, 2)]
        self.assertEqual(calls, ['guard-enter'] + expected + ['score', 'guard-exit'])
        self.assertTrue(result['protocol']['protocol_evidence_passed'])
        self.assertEqual(result['runtime_status'], 'blocked')
        self.assertIn('FP32', result['missing'][0])
        for flag in ('t3_passed', 'promoted', 'ledger_eligible'):
            self.assertFalse(result[flag])

    def test_guard_failure_never_opens_requests(self):
        runtime, calls = self.prepared_runtime()
        @contextmanager
        def failed_guard():
            raise RuntimeError('fixture no kernel isolation')
            yield
        runtime.guard = failed_guard
        with patch.object(phase4_run, 'open_phase4') as opened, self.assertRaises(RuntimeError):
            phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        opened.assert_not_called()
        self.assertFalse((self.helper.root / 'phase4.json').exists())

    def test_complete_performance_rejection_preserves_all_evidence(self):
        runtime, calls = self.prepared_runtime(speedup=1.0, science={'path': '/fixture/science', 'sha256': 'a' * 64})
        with patch.object(phase4_run, 'validate_science', return_value={'scientific_ready': True}):
            receipt = phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        result = read_reference(receipt, self.helper.root)
        self.assertTrue(result['execution_completed'])
        self.assertTrue(result['protocol_verified'])
        self.assertTrue(result['scientific_ready'])
        self.assertTrue(result['correctness_passed'])
        self.assertFalse(result['performance_passed'])
        self.assertFalse(result['protocol']['protocol_evidence_passed'])
        self.assertEqual(result['runtime_status'], 'scientific-rejection')
        self.assertEqual(len([entry for entry in calls if isinstance(entry, tuple)]), 12)
        self.assertTrue(Path(result['evidence']['path']).is_file())
        self.assertFalse(result['t3_passed'])

    def test_complete_correctness_rejection_is_not_infrastructure_failure(self):
        runtime, calls = self.prepared_runtime(fault=True, science={'path': '/fixture/science', 'sha256': 'a' * 64})
        with patch.object(phase4_run, 'validate_science', return_value={'scientific_ready': True}):
            receipt = phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        result = read_reference(receipt, self.helper.root)
        self.assertTrue(result['execution_completed'])
        self.assertFalse(result['correctness_passed'])
        self.assertEqual(result['runtime_status'], 'scientific-rejection')
        self.assertFalse(result['t3_passed'])

    def test_stock_control_complete_expected_rejection_never_authorizes_t3(self):
        helper = self.helper
        helper.arms = [helper.arms[0], dict(helper.arms[0], name='candidate', option_enabled=False)]
        helper.root = helper.base / 'stock-control'
        helper.freeze = freeze_candidate(helper.root, **dict(helper.freeze_args, arms=helper.arms),
                                          purpose='controller-negative-control')
        runtime, calls = self.prepared_runtime(speedup=1.0, science={'path': '/fixture/science', 'sha256': 'a' * 64})
        with patch.object(phase4_run, 'validate_science', return_value={'scientific_ready': True}):
            receipt = phase4_run.execute_schedule(helper.freeze, helper.request_file, runtime)
        result = read_reference(receipt, helper.root)
        self.assertEqual(result['runtime_status'], 'maintenance-stock-control-complete')
        self.assertTrue(result['execution_completed'])
        self.assertTrue(result['expected_rejection'])
        self.assertFalse(result['performance_passed'])
        self.assertFalse(result['protocol']['protocol_evidence_passed'])
        self.assertFalse(result['t3_passed'])

    def test_control_requires_actual_stock_arms_not_renamed_candidate(self):
        with self.assertRaisesRegex(ValueError, 'canonical stock'):
            freeze_candidate(self.helper.base / 'forged-control', **self.helper.freeze_args,
                             purpose='controller-negative-control')

    def test_failed_round_or_cleanup_cannot_write_complete_runtime_receipt(self):
        runtime, calls = self.prepared_runtime(fail_at=3)
        with self.assertRaisesRegex(RuntimeError, 'server failed'):
            phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        self.assertNotIn('score', calls)
        self.assertEqual(calls[-1], 'guard-exit')
        self.assertFalse((self.helper.root / 'runtime-result.json').exists())

    def test_failed_guard_cleanup_with_full_evidence_has_no_complete_receipt(self):
        runtime, calls = self.prepared_runtime(fail_exit=True)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        self.assertEqual(calls[-1], 'guard-exit')
        self.assertFalse((self.helper.root / 'runtime-result.json').exists())

    def test_uploaded_runtime_or_scientific_passed_is_not_a_preflight(self):
        runtime, calls = self.prepared_runtime(science=self.helper.save(dict(
            runtime_passed=True, scientific_ready=True, preflight={'passed': True})))
        with self.assertRaisesRegex(ValueError, 'current Phase4'):
            phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        self.assertFalse((self.helper.root / 'runtime-result.json').exists())

    def test_bad_request_id_cannot_escape_private_trace_directory(self):
        runtime, calls = self.prepared_runtime()
        self.helper.requests[0]['id'] = '../leak'
        self.helper.request_file.write_text(json.dumps(self.helper.requests))
        with self.assertRaisesRegex(ValueError, 'safe file stems'):
            phase4_run.execute_schedule(self.helper.freeze, self.helper.request_file, runtime)
        self.assertNotIn('score', calls)

    def test_network_namespace_capability_failure_is_fail_closed(self):
        with patch.object(phase4_run.os, 'geteuid', return_value=1234):
            with self.assertRaisesRegex(RuntimeError, 'optional network enhancement'):
                with phase4_run.private_network():
                    self.fail('must not enter')
        libc = SimpleNamespace(unshare=lambda flags: -1)
        with patch.object(phase4_run.os, 'geteuid', return_value=0), patch.object(
                phase4_run.threading, 'active_count', return_value=1), patch.object(
                phase4_run.ctypes, 'CDLL', return_value=libc):
            with self.assertRaisesRegex(OSError, 'CLONE_NEWNET enhancement unavailable'):
                with phase4_run.private_network():
                    self.fail('must not enter')

    def test_default_runtime_does_not_require_or_claim_network_isolation(self):
        root, frozen = _frozen(self.helper.freeze)
        runtime = phase4_run.LiveRuntime(dict(target='/fixture', draft='/draft',
            stock_engine='/fixture-engine', stock_tree_sha='a' * 64), frozen)
        with patch.object(phase4_run, 'private_network', side_effect=OSError('unshare unavailable')) as network, \
                patch.object(phase4_run, 'wait_for_idle', return_value=self.helper.gpus), \
                patch.object(phase4_run, 'gpu_lock', side_effect=lambda gpu: nullcontext()), \
                patch.object(phase4_run, 'source_uids_idle') as idle, \
                patch.object(phase4_run, 'check_ports'), \
                patch.object(phase4_run.os, 'geteuid', return_value=1234):
            with runtime.guard() as identity:
                self.assertFalse(identity['network_isolated'])
                self.assertFalse(identity['research_shutdown_verified'])
            network.assert_not_called()
            idle.assert_called_once()

    def test_explicit_network_enhancement_is_not_silently_downgraded(self):
        root, frozen = _frozen(self.helper.freeze)
        runtime = phase4_run.LiveRuntime(dict(target='/fixture', draft='/draft',
            stock_engine='/fixture-engine', stock_tree_sha='a' * 64), frozen, isolate_network=True)
        with patch.object(phase4_run, 'private_network', side_effect=OSError('enhancement unavailable')) as network, \
                patch.object(phase4_run, 'wait_for_idle') as gpus:
            with self.assertRaisesRegex(OSError, 'enhancement unavailable'):
                with runtime.guard():
                    self.fail('must not claim the requested enhancement')
            network.assert_called_once()
            gpus.assert_not_called()

    def test_missing_stopped_receipt_is_not_normalized_as_success(self):
        directory = self.helper.root / 'native'
        directory.mkdir()
        (directory / 'complete.json').write_text(json.dumps(dict(round=1, pairs=1)))
        assignment = dict(arm={'name': 'stock'})
        (directory / 'deployment.json').write_text(json.dumps(dict(assignments=[assignment])))
        (directory / 'stock.process.json').write_text(json.dumps(dict(pid=1, start_ticks=2)))
        with self.assertRaises(FileNotFoundError):
            phase4_run.normalize_round(directory, cap=2048, number=1, started_unix=time.time())

    def test_real_tmp_bundle_and_all_runtime_sources_are_frozen_before_open(self):
        source = source_tests.SourceCandidateTests()
        source.setUp()
        self.addCleanup(source.doCleanups)
        target = source.root / 'target'
        target.mkdir()
        (target / 'config.json').write_text('{}')
        (target / 'model.safetensors.index.json').write_text('{}')
        base = make_spec(source.stock, source.root / 'config.json', str(target),
                         str(source.root / 'draft'), 'a' * 40)
        bundle = source.root / 'candidate-bundle'
        build_bundle(base, source.patch_path, bundle)
        research = source.root / 'research'
        research.mkdir()
        freeze = phase4_run.freeze_bundle(bundle, source.root / 'controller', gpus=self.helper.gpus,
            seen_input_hashes=[], research_roots=[research])
        root, frozen, actual = phase4_run.check_bundle(bundle, freeze)
        self.assertEqual(actual, base)
        self.assertTrue(all(name in frozen['artifacts'] for name in phase4_run.SOURCES))
        self.assertFalse((root / 'phase4.json').exists())
        (target / 'config.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'artifact drifted'):
            phase4_run.check_bundle(bundle, freeze)

    def test_head_checks_require_bound_native_packets_and_numerical_evidence(self):
        root, frozen = _frozen(self.helper.freeze)
        frozen['artifacts'].update({name: {'sha256': value * 64} for name, value in
            (('controller/head_reference.py', 'a'), ('target_config', 'b'), ('target_index', 'c'))})
        raw = self.helper.save(dict(http_status=200, started_unix=10,
            request=dict(input_ids=[2, 3], return_hidden_states='last', return_logprob=True,
                         sampling_params={'max_new_tokens': 1}), response={'output_ids': [4]}))
        head = dict(mode='preflight', tokens=1, head_identity=dict(shape=[248320, 5120],
            checkpoint='/fixture', compute_dtype='torch.float32', checkpoint_dtype='torch.bfloat16',
            tf32=False, chunks=8, reversed_accumulation=True, tensor_sha256='d' * 64,
            source_sha256='a' * 64, config_sha256='b' * 64, index_sha256='c' * 64),
            checks=[dict(raw_evidence=raw, prefix_sha256=phase4_run.sha_ids([2, 3]), native_token=4,
                reverse_token=4, native_logprob_error=0, native_choice_margin=0, max_logit_difference=0)])
        phase4_run.checked_head(self.helper.save(head), root=root, frozen=frozen, mode='preflight', not_before=9)
        for change in ('margin', 'raw', 'prefix', 'source', 'time', 'empty'):
            altered = copy.deepcopy(head)
            if change == 'margin': altered['checks'][0]['max_logit_difference'] = .01
            if change == 'raw': altered['checks'][0]['raw_evidence']['sha256'] = '0' * 64
            if change == 'prefix': altered['checks'][0]['prefix_sha256'] = '0' * 64
            if change == 'source': altered['head_identity']['source_sha256'] = '0' * 64
            if change == 'empty': altered['checks'] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                phase4_run.checked_head(self.helper.save(altered), root=root, frozen=frozen,
                                       mode='preflight', not_before=11 if change == 'time' else 9)

    def test_actual_cpu_http_run_round_normalizes_to_strict_protocol(self):
        helper = self.helper
        base = dict(target='/fixture', draft='/draft')
        serial = []
        class Server:
            def __init__(self, arm, gpu, port, output_dir, environment):
                self.arm, self.gpu, self.port, self.directory = arm, gpu, port, output_dir
                serial.append(len(serial) + 1)
                self.process = SimpleNamespace(pid=10000 + serial[-1])
                self.start_ticks = serial[-1]
            def start(self):
                arguments = expected_arguments(base, self.arm['block'])
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
                        self.send({'server_args': arguments})
                    def do_POST(self):
                        json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        time.sleep(.03)
                        self.send(dict(output_ids=[9, 10], meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1, finish_reason={'type': 'stop'})))
                self.http = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
                self.thread = threading.Thread(target=self.http.serve_forever)
                self.thread.start()
                (self.directory / f'{self.arm["name"]}.process.json').write_text(json.dumps(
                    dict(pid=self.process.pid, start_ticks=self.start_ticks)))
            def wait_ready(self, timeout):
                pass
            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
                (self.directory / f'{self.arm["name"]}.stopped.json').write_text('{"stopped":true}')
        class Telemetry:
            def __init__(self, servers, gpus, path, **options):
                self.servers, self.gpus, self.path = servers, gpus, path
                self.stop = threading.Event()
            def __enter__(self):
                def capture():
                    with self.path.open('x') as destination:
                        while not self.stop.is_set():
                            snapshot = dict(time_unix=time.time(), gpus=[dict(gpu,
                                clocks_sm_mhz=1000, clocks_mem_mhz=1000, temperature_c=40, power_w=100)
                                for gpu in self.gpus], arms={server.arm['name']: [dict(pid=server.process.pid,
                                start_ticks=server.start_ticks)] for server in self.servers})
                            destination.write(json.dumps(snapshot) + '\n')
                            destination.flush()
                            self.stop.wait(.003)
                self.thread = threading.Thread(target=capture)
                self.thread.start()
                return self
            def __exit__(self, *errors):
                self.stop.set()
                self.thread.join()
        ports = None
        for start in range(36000, 37000, 10):
            try:
                phase4_run.check_ports([start, start + 4])
                ports = [start, start + 4]
                break
            except OSError:
                continue
        self.assertIsNotNone(ports)
        directory = helper.root / 'http-round'
        def factory(name, url, **options):
            return phase4_run.TimedSourceArm(name, url, directory=directory, spec=base, **options)
        started = time.time()
        with patch('exp.p3_pair_run.Telemetry', Telemetry):
            phase4_run.run_round(helper.arms, helper.gpus, ports, 0, helper.requests, directory, {},
                4096, 1, 10, server_factory=Server, arm_factory=factory, stable_null=True)
        record = phase4_run.normalize_round(directory, cap=4096, number=1, started_unix=started)
        root, frozen = _frozen(helper.freeze)
        assignments, pairs = _round(record, cap=4096, phase='candidate', number=1, root=root,
            frozen=frozen, requests=helper.requests, used_processes=set())
        self.assertEqual(len(assignments), 2)
        self.assertEqual(pairs[0]['a']['output_ids'], [9, 10])
        self.assertEqual(pairs[0]['a']['max_new_tokens'], 4096)


if __name__ == '__main__':
    unittest.main()
