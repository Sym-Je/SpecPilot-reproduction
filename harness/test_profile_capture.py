import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from exp import profile_capture
from exp.p3_pair_run import SUITES
from harness.candidate import digest, expected_arguments, make_spec
from harness import test_source_candidate as source_tests


class ProfileCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = source_tests.SourceCandidateTests()
        source.setUp()
        self.addCleanup(source.doCleanups)
        self.target, self.draft = self.root / 'target', self.root / 'draft'
        for model in (self.target, self.draft):
            model.mkdir()
            for name in ('config.json', 'tokenizer_config.json'):
                (model / name).write_text('{}')
            (model / 'model-00001-of-00001.safetensors').write_bytes(b'non-sensitive checkpoint identity fixture')
            (model / 'model.safetensors.index.json').write_text(json.dumps({
                'weight_map': {'fixture.weight': 'model-00001-of-00001.safetensors'}}))
        self.base = make_spec(source.stock, source.root / 'config.json', str(self.target), str(self.draft), 'a' * 40)
        self.base_path = self.root / 'base.json'
        self.base_path.write_text(json.dumps(self.base))
        self.repo = self.root / 'repo'
        (self.repo / 'exp').mkdir(parents=True)
        shutil.copyfile(Path(profile_capture.__file__), self.repo / 'exp/profile_capture.py')
        self.names = ['exp/profile_capture.py']
        dev_sources = {}
        for suite in SUITES:
            path = self.repo / f'assets/upstream/dev/{suite}.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(''.join(json.dumps(dict(id=f'{suite}-{index}', turns=[str(index + 3)])) + '\n'
                                    for index in range(4)))
            self.names.append(path.relative_to(self.repo).as_posix())
            dev_sources[suite] = profile_capture.reference(path)
        self.archive = self.root / 'source.tar'
        with tarfile.open(self.archive, 'w') as archive:
            for name in self.names:
                archive.add(self.repo / name, arcname=name, recursive=False)
        self.request = dict(schema='stock-profile-capture-v1', action=dict(
            workload_id='gsm8k:0', preset='graph-128', reason='CPU scheduling fixture only'),
            base_spec=profile_capture.reference(self.base_path), bundle=None,
            source_archive=profile_capture.reference(self.archive), dev_sources=dev_sources)
        self.request_path = self.root / 'request.json'
        self.request_path.write_text(json.dumps(self.request))
        self.output = self.root / 'output'

    def test_only_fixed_workload_and_preset_are_accepted(self):
        profile_capture.validate_action(self.request['action'])
        for key, value in (('workload_id', '../../sealed'), ('workload_id', 'gsm8k:4'),
                           ('preset', 'eager'), ('flags', ['--disable-cuda-graph']), ('reason', '')):
            action = dict(self.request['action'], **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                profile_capture.validate_action(action)
        with self.assertRaises(ValueError):
            profile_capture.validate_request(dict(self.request, environment={'X': 'Y'}))

    def test_profile_body_requires_all_three_native_capabilities(self):
        fields = ('output_dir', 'num_steps', 'record_shapes', 'with_stack', 'detailed_annotations', 'activities')
        schema = {'components': {'schemas': {'ProfileReq': {'properties': {name: {} for name in fields}}}}}
        body = profile_capture.profile_body(schema, self.root / 'trace')
        self.assertEqual(body['num_steps'], 128)
        for name in ('record_shapes', 'with_stack', 'detailed_annotations'):
            self.assertIs(body[name], True)
            changed = copy.deepcopy(schema)
            del changed['components']['schemas']['ProfileReq']['properties'][name]
            with self.subTest(name=name), self.assertRaises(ValueError):
                profile_capture.profile_body(changed, self.root / 'trace')

    def capture(self, *, bad_trace=False, stop_status=200, as_dict=False, inactive_log=False, offline_audit=False):
        fixture, calls = self, []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *arguments):
                pass
            def send(self, status, value, raw=False):
                body = value.encode() if raw else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'text/plain' if raw else 'application/json')
                self.end_headers()
                self.wfile.write(body)
            def do_GET(self):
                if self.path == '/openapi.json':
                    fields = ('output_dir', 'num_steps', 'record_shapes', 'with_stack', 'detailed_annotations', 'activities')
                    self.send(200, {'components': {'schemas': {'ProfileReq': {'properties': {key: {} for key in fields}}}}})
                else:
                    self.send(200, {'server_args': expected_arguments(fixture.base, 8)})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, body))
                if self.path == '/start_profile':
                    trace = Path(body['output_dir']) / 'fixture.trace.json'
                    events = [] if bad_trace else [dict(ph='X', cat='kernel', name='fixture_cuda_kernel',
                                                       pid=1, tid=2, ts=10, dur=2)]
                    trace.write_text(json.dumps({'traceEvents': events}))
                    self.send(200, 'Start profiling.\n', raw=True)
                elif self.path == '/stop_profile':
                    if inactive_log:
                        with (fixture.output / 'stock.launcher.log').open('a') as stream:
                            stream.write('RuntimeError: Profiling is not in progress. Call /start_profile first.\n')
                    self.send(stop_status, 'not running' if stop_status == 409 else 'Stop profiling.\n', raw=True)
                else:
                    self.send(200, dict(output_ids=[4, 5], meta_info=dict(completion_tokens=2,
                        finish_reason={'type': 'stop'})))
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.fixture_port = http.server_port
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        gpu = dict(index=0, uuid='GPU-fixture', name='H100 fixture', memory_used_mib=0, utilization=0)
        class Server:
            def __init__(self, arm, selected, port, output, environment):
                self.arm, self.gpu, self.output_dir = arm, selected, output
                self.sandbox = fixture.root / 'sandbox'
                self.sandbox.mkdir()
                self.work = self.sandbox / 'cache/work'
                self.work.mkdir(parents=True)
                self.process = None
            def start(self):
                (self.output_dir / 'stock.launcher.log').write_text('CPU fixture server, not a GPU execution\n')
                profile_capture.save_json(self.output_dir / 'stock.process.json', dict(pid=1234, start_ticks=56,
                    host_boot_id='fixture-boot'))
                profile_capture.save_json(self.output_dir / 'stock.boundary.json', dict(event='SOURCE_BOUNDARY_READY',
                    uid=60010, trusted_pipe=True, denied={'protected_read': True, 'protected_write': True,
                    'source_write': True, 'escape_session': True, 'root_filesystem': True},
                    landlock_applied=True, seccomp_applied=True, network_isolated=False))
                profile_capture.save_json(self.output_dir / 'stock.sandbox.json', dict(uid=60010,
                    scratch=str(self.sandbox / 'cache'), work=str(self.work), devices=['/dev/nvidia-fixture'],
                    readonly=[str(fixture.base['stock_engine']), str(fixture.target), str(fixture.draft)],
                    command=profile_capture.serve_command(fixture.base, 8, sys.executable, http.server_port),
                    environment={'CUDA_VISIBLE_DEVICES': 'GPU-fixture'}, engine_tree_sha=fixture.base['stock_tree_sha']))
            def wait_ready(self, timeout):
                pass
            def stop(self):
                profile_capture.save_json(self.output_dir / 'stock.stopped.json', dict(stopped=True, exit_code=-15))
            def cleanup(self):
                shutil.rmtree(self.sandbox)
        tokenizer = type('Tokenizer', (), {'apply_chat_template': lambda self, messages, **options: [2, int(messages[0]['content'])]})()
        factory = type('AutoTokenizer', (), {'from_pretrained': staticmethod(lambda *arguments, **options: tokenizer)})
        with patch.object(profile_capture, 'ROOT', self.repo), \
                patch.object(profile_capture, 'FROZEN_STOCK_SHA', self.base['stock_tree_sha']), \
                patch.object(profile_capture, 'execution_sources', return_value=tuple(self.names)), \
                patch.object(profile_capture.os, 'geteuid', return_value=0), \
                patch.object(profile_capture.os, 'chown'), \
                patch.object(profile_capture, 'wait_for_idle', return_value=[gpu]), \
                patch.object(profile_capture, 'gpu_lock'), patch.object(profile_capture, 'check_ports'), \
                patch.object(profile_capture, 'PORT', http.server_port), \
                patch.object(profile_capture, 'ProfileSourceServer', Server), \
                patch.dict(sys.modules, transformers=type('Transformers', (), {'AutoTokenizer': factory})):
            result = profile_capture.run(self.request if as_dict else self.request_path, self.output)
            for path in self.output.rglob('*'):
                path.chmod(0o755 if path.is_dir() else 0o644)
            self.output.chmod(0o755)
            def offline_reference(path):
                if any(Path(path).is_relative_to(model) for model in (self.target, self.draft)):
                    raise AssertionError('host audit must not reopen inaccessible live model files')
                return original_reference(path)
            original_reference = profile_capture.reference
            with patch.object(profile_capture, 'wait_for_idle', side_effect=AssertionError('audit must not query GPU')):
                if offline_audit:
                    with patch.object(profile_capture, 'reference', side_effect=offline_reference):
                        replay = profile_capture.audit(self.output)
                else:
                    replay = profile_capture.audit(self.output)
        return result, replay, calls

    def test_real_cpu_http_capture_is_profile_only_and_survives_scratch_cleanup(self):
        result, replay, calls = self.capture()
        self.assertEqual(result, replay)
        self.assertEqual(result['status'], 'completed')
        self.assertIsNone(result['workload'])
        self.assertEqual(result['shape_status'], 'unknown')
        self.assertFalse(result['controller_accepted'])
        self.assertFalse(result['option_enabled'])
        self.assertEqual(len(result['traces']), 1)
        self.assertTrue(Path(result['traces'][0]['path']).is_file())
        self.assertFalse((self.root / 'sandbox').exists())
        generations = [body for name, body in calls if name == '/generate']
        self.assertEqual([body['sampling_params']['max_new_tokens'] for body in generations], [32, 2048])
        self.assertTrue(all(body['input_ids'] == [2, 3] for body in generations))

    def test_auto_stopped_native_profile_is_not_a_missing_trace(self):
        result, replay, _ = self.capture(stop_status=409)
        self.assertEqual(result, replay)

    def test_resource_can_pass_a_trusted_capture_dictionary(self):
        result, replay, _ = self.capture(as_dict=True)
        self.assertEqual(result, replay)
        self.assertEqual(json.loads((self.output / 'request.json').read_text()), self.request)

    def test_single_file_draft_needs_no_index_and_audit_never_reopens_live_weights(self):
        (self.draft / 'model.safetensors.index.json').unlink()
        (self.draft / 'model-00001-of-00001.safetensors').unlink()
        weight = self.draft / 'model.safetensors'
        weight.write_bytes(b'non-sensitive single-file draft fixture')
        result, replay, _ = self.capture(offline_audit=True)
        self.assertEqual(result, replay)
        manifest = json.loads((self.output / 'manifest.json').read_text())
        checkpoint = manifest['checkpoints']['draft']
        self.assertEqual(checkpoint['layout'], 'single-safetensors')
        self.assertIsNone(checkpoint['index'])
        self.assertEqual(checkpoint['weights'][0]['sha256'], profile_capture.reference(weight)['sha256'])
        self.assertEqual(checkpoint['weights'][0]['size'], weight.stat().st_size)
        self.assertFalse(any(path.suffix == '.safetensors' for path in self.output.rglob('*')))
        self.assertEqual(result['model_identity_verification']['weights'], 'controller-recorded-sha256-size; offline-audit-receipt-only')

    def test_checkpoint_identity_hashes_large_weights_without_copying_them(self):
        model, destination = self.root / 'single-model', self.root / 'single-evidence'
        model.mkdir()
        (model / 'config.json').write_text('{}')
        weight = model / 'model.safetensors'
        weight.write_bytes(b'fixture' * 1024)
        with patch.object(profile_capture, 'FILE_LIMIT', 100):
            metadata, checkpoint = profile_capture.capture_model(model, destination)
        self.assertEqual(set(metadata), {'config.json'})
        self.assertEqual(checkpoint['weights'][0]['sha256'], profile_capture.reference(weight)['sha256'])
        self.assertFalse((destination / weight.name).exists())

    def test_checkpoint_layout_missing_shards_escape_and_empty_index_are_rejected(self):
        for change in ('missing', 'escape', 'empty'):
            model = self.root / ('bad-model-' + change)
            model.mkdir()
            (model / 'config.json').write_text('{}')
            weight_map = {} if change == 'empty' else {
                'fixture.weight': '../outside.safetensors' if change == 'escape' else 'missing.safetensors'}
            (model / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': weight_map}))
            with self.subTest(change=change), self.assertRaises((ValueError, FileNotFoundError)):
                profile_capture.capture_model(model, self.root / ('bad-evidence-' + change))

    def test_missing_config_or_checkpoint_is_not_a_model_identity(self):
        for missing in ('config', 'weights'):
            model = self.root / ('absent-' + missing)
            model.mkdir()
            if missing != 'config':
                (model / 'config.json').write_text('{}')
            if missing != 'weights':
                (model / 'model.safetensors').write_bytes(b'fixture')
            with self.subTest(missing=missing), self.assertRaises((ValueError, FileNotFoundError)):
                profile_capture.capture_model(model, self.root / ('absent-evidence-' + missing))

    def test_indexed_checkpoint_binds_every_unique_shard_without_copying_weights(self):
        second = self.target / 'model-00002-of-00002.safetensors'
        second.write_bytes(b'non-sensitive second shard')
        first = 'model-00001-of-00001.safetensors'
        (self.target / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {
            'first.weight': first, 'alias.weight': first, 'second.weight': second.name}}))
        metadata, checkpoint = profile_capture.capture_model(self.target, self.root / 'indexed-evidence')
        self.assertEqual(checkpoint['layout'], 'indexed-safetensors')
        self.assertEqual(len(checkpoint['weights']), 2)
        for weight in checkpoint['weights']:
            self.assertEqual(weight['sha256'], profile_capture.reference(weight['path'])['sha256'])
        self.assertIn('model.safetensors.index.json', metadata)
        self.assertFalse(list((self.root / 'indexed-evidence').glob('*.safetensors')))

    def test_capture_rejects_weight_source_stat_changes_before_acceptance(self):
        metadata, checkpoint = profile_capture.capture_model(self.draft, self.root / 'drift-evidence')
        weight = Path(checkpoint['weights'][0]['path'])
        weight.write_bytes(b'changed non-sensitive source')
        with self.assertRaisesRegex(ValueError, 'source identity changed'):
            profile_capture.check_model_sources({'draft': metadata}, {'draft': checkpoint})

    def test_offline_checkpoint_audit_requires_complete_sha_size_and_layout_receipts(self):
        metadata, checkpoint = profile_capture.capture_model(self.draft, self.root / 'receipt-evidence')
        read = lambda source: json.loads(Path(source['path']).read_text())
        profile_capture.audit_checkpoint(checkpoint, self.draft, metadata, read)
        for change in ('missing-weight', 'sha', 'size', 'layout', 'source-policy'):
            altered = copy.deepcopy(checkpoint)
            if change == 'missing-weight':
                altered['weights'] = []
            if change == 'sha':
                altered['weights'][0]['sha256'] = 'unverified'
            if change == 'size':
                altered['weights'][0]['size'] = True
            if change == 'layout':
                altered['layout'] = 'single-safetensors'
            if change == 'source-policy':
                altered['source_policy'] = 'self-reported-readonly'
            with self.subTest(change=change), self.assertRaises(ValueError):
                profile_capture.audit_checkpoint(altered, self.draft, metadata, read)

    def test_native_500_requires_the_exact_current_log_proof(self):
        result, replay, _ = self.capture(stop_status=500, inactive_log=True)
        self.assertEqual(result, replay)
        manifest = json.loads((self.output / 'manifest.json').read_text())
        self.assertIsNotNone(manifest['stop_control']['inactive_log'])

    def test_unproven_native_stop_error_does_not_publish_success(self):
        with self.assertRaisesRegex(ValueError, 'inactive-state proof'):
            self.capture(stop_status=500)
        self.assertFalse((self.output / 'result.json').exists())

    def test_single_device_mapping_never_grants_a_second_allocated_uuid(self):
        information = self.root / 'driver'
        (information / 'card').mkdir(parents=True)
        (information / 'card/information').write_text('GPU UUID: GPU-fixture\nDevice Minor: 6\n')
        original_path = Path
        def mapped_path(value):
            return information if str(value) == '/proc/driver/nvidia/gpus' else original_path(value)
        nvml = SimpleNamespace(nvmlInit=lambda: None, nvmlShutdown=lambda: None,
            nvmlDeviceGetHandleByUUID=lambda uuid: uuid, nvmlDeviceGetMinorNumber=lambda handle: 0)
        with patch.object(profile_capture, 'Path', side_effect=mapped_path), \
                patch.dict(sys.modules, pynvml=nvml), patch.dict(os.environ, NVIDIA_VISIBLE_DEVICES='GPU-fixture'):
            devices, _, layout = profile_capture.single_device_paths({'uuid': 'GPU-fixture'})
            self.assertIn('/dev/nvidia6', devices)
            self.assertNotIn('/dev/nvidia0', devices)
            self.assertEqual(layout['kernel_minor'], 6)
            with patch.dict(os.environ, NVIDIA_VISIBLE_DEVICES='GPU-fixture,GPU-other'), self.assertRaises(ValueError):
                profile_capture.single_device_paths({'uuid': 'GPU-fixture'})

    def test_umask077_probe_bootstrap_and_cpu_handshake_permissions(self):
        output = self.root / 'boundary'
        output.mkdir(mode=0o700)
        arm = dict(name='stock', block=8, tree_sha=self.base['stock_tree_sha'],
                   engine=self.base['stock_engine'], env={}, option_enabled=False)
        server = profile_capture.ProfileSourceServer(arm, {'uuid': 'GPU-fixture'}, 30500, output,
            dict(PATH=os.environ.get('PATH', ''), SP_TARGET=str(self.target), SP_DRAFT=str(self.draft)))
        original_popen = subprocess.Popen
        program = '''import json,os,sys
payload=json.load(sys.stdin)
receipt=dict(event='SOURCE_BOUNDARY_READY',uid=60010,denied={'cpu_fixture_only':True},landlock_applied=True,seccomp_applied=True)
os.write(payload['ready_fd'],json.dumps(receipt).encode())
'''
        def child(command, **options):
            return original_popen([sys.executable, '-I', '-B', '-c', program], **options)
        previous = os.umask(0o077)
        try:
            with patch.object(profile_capture.os, 'geteuid', return_value=0), \
                    patch.object(profile_capture.os, 'chown'), \
                    patch.object(profile_capture, 'single_device_paths', return_value=([], None, {})), \
                    patch.object(profile_capture.shutil, 'which', return_value=sys.executable), \
                    patch.object(profile_capture.subprocess, 'Popen', side_effect=child):
                server.start()
            expected = {'allowed.txt': 0o444, 'canary.txt': 0o600, 'trusted-bootstrap': 0o755,
                        'trusted-bootstrap/trusted_source_cache.py': 0o444, 'cache/work': 0o700}
            for name, mode in expected.items():
                self.assertEqual((server.sandbox / name).stat().st_mode & 0o777, mode)
            payload = json.loads((output / 'stock.sandbox.json').read_text())
            self.assertEqual(payload['uid'], 60010)
            self.assertNotIn(str(output), payload['readonly'])
            self.assertNotIn(str(profile_capture.ROOT), payload['readonly'])
            self.assertEqual(payload['environment']['TRITON_CACHE_MANAGER'], 'trusted_source_cache:SourceCacheManager')
        finally:
            os.umask(previous)
            server.stop()
            server.cleanup()

    def test_stock_option_or_source_changes_fail_before_gpu_start(self):
        changed = dict(self.base, value=16)
        changed['spec_sha256'] = digest({
            key: value for key, value in changed.items() if key != 'spec_sha256'})
        with patch.object(profile_capture, 'FROZEN_STOCK_SHA', self.base['stock_tree_sha']):
            with self.assertRaises(ValueError):
                profile_capture.check_base(changed, None)
            profile_capture.check_base(self.base, {'base': self.base, 'stock_tree_sha': self.base['stock_tree_sha'],
                'candidate_tree_sha': 'f' * 64, 'candidate_path': '/not/read/by/collector'})
        with patch.object(profile_capture, 'ROOT', self.repo), \
                patch.object(profile_capture, 'execution_sources', return_value=tuple(self.names)):
            (self.repo / 'exp/profile_capture.py').write_text('changed source\n')
            with self.assertRaises(ValueError):
                profile_capture.source_identity(self.archive)

    def test_empty_cuda_trace_is_not_success(self):
        with self.assertRaises(ValueError):
            self.capture(bad_trace=True)
        self.assertFalse((self.output / 'result.json').exists())

    def test_audit_rejects_changed_or_extra_artifacts(self):
        result, _, _ = self.capture()
        path = Path(result['traces'][0]['path'])
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaises(ValueError):
            profile_capture.audit(self.output)
        path.write_bytes(original)
        (self.output / 'extra.json').write_text('{}')
        with self.assertRaises(ValueError):
            profile_capture.audit(self.output)

    def test_resealed_statistics_generation_and_boundary_are_independently_recomputed(self):
        self.capture()
        original = json.loads((self.output / 'manifest.json').read_text())
        generation_path = Path(original['generation']['path'])
        generation = json.loads(generation_path.read_text())
        tokenizer = SimpleNamespace(apply_chat_template=lambda messages, **options: [2, int(messages[0]['content'])])
        factory = SimpleNamespace(from_pretrained=lambda *arguments, **options: tokenizer)
        for change, message in (('statistics', 'uploaded trace statistics'),
                                ('generation', 'actual profiled generation'), ('models', 'both model metadata')):
            altered = copy.deepcopy(original)
            if change == 'statistics':
                altered['traces'][0]['statistics']['kernel_count'] += 1
            if change == 'generation':
                packet = copy.deepcopy(generation)
                packet['response']['meta_info']['completion_tokens'] = 3
                generation_path.write_text(json.dumps(packet))
                altered['generation'] = profile_capture.reference(generation_path)
            if change == 'models':
                altered['models'] = {}
            altered['files'] = {name: profile_capture.reference(path)['sha256']
                for name, path in profile_capture.artifact_files(self.output).items()
                if name not in ('manifest.json', 'result.json')}
            (self.output / 'manifest.json').write_text(json.dumps(altered))
            with patch.object(profile_capture, 'ROOT', self.repo), \
                    patch.object(profile_capture, 'FROZEN_STOCK_SHA', self.base['stock_tree_sha']), \
                    patch.object(profile_capture, 'execution_sources', return_value=tuple(self.names)), \
                    patch.object(profile_capture, 'PORT', self.fixture_port), \
                    patch.dict(sys.modules, transformers=SimpleNamespace(AutoTokenizer=factory)):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                    profile_capture.audit(self.output)
            generation_path.write_text(json.dumps(generation))

    def test_deadline_watcher_rejects_without_claiming_gpu_success(self):
        output, staging = self.root / 'watch-output', self.root / 'watch-stage'
        output.mkdir()
        staging.mkdir()
        with self.assertRaisesRegex(ValueError, 'watcher rejected'):
            with profile_capture.ArtifactWatch(output, staging, SimpleNamespace(process=None),
                                               expires=time.monotonic() - 1):
                time.sleep(.3)

    def test_trace_symlinks_and_budget_overflow_are_rejected(self):
        staging = self.root / 'staging'
        staging.mkdir()
        outside = self.root / 'outside.json'
        outside.write_text('{}')
        (staging / 'trace.json').symlink_to(outside)
        with self.assertRaises(ValueError):
            profile_capture.copy_traces(staging, self.root / 'traces')
        (staging / 'trace.json').unlink()
        (staging / 'trace.json').write_bytes(b'X' * 4096)
        with patch.object(profile_capture, 'TOTAL_LIMIT', 100), self.assertRaises(ValueError):
            profile_capture.copy_traces(staging, self.root / 'traces')


if __name__ == '__main__':
    unittest.main()
