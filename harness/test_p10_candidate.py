import copy
import json
from pathlib import Path
import tempfile
import unittest


class CandidateTests(unittest.TestCase):
    def setUp(self):
        from harness.build_engine import tree_sha
        from harness.candidate import make_spec
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stock = self.root / 'stock'
        (self.stock / 'python').mkdir(parents=True)
        (self.stock / 'lab').mkdir()
        (self.stock / 'python/module.py').write_text('stock fixture\n')
        (self.stock / 'TREE_SHA').write_text(tree_sha(self.stock) + '\n')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(dict(stock=dict(block_size=8))))
        self.spec = make_spec(self.stock, self.config, '/target', '/draft', 'a' * 40)

    def build(self, spec=None):
        from harness.candidate import build_bundle
        bundle = self.root / 'bundle'
        build_bundle(spec or self.spec, bundle)
        return bundle

    def test_default_and_noop_on_preserve_stock_block_and_tree(self):
        from harness.candidate import candidate_arm
        bundle = self.build()
        for enabled in (False, True):
            arm = candidate_arm(bundle, enabled=enabled)
            self.assertEqual(arm['block'], 8)
            self.assertEqual(arm['tree_sha'], self.spec['stock_tree_sha'])
            self.assertEqual(arm['name'], 'candidate')
            self.assertEqual(arm['env'], {})

    def test_enabled_startup_option_is_not_silently_ignored(self):
        from harness.candidate import candidate_arm, make_spec
        spec = make_spec(self.stock, self.config, '/target', '/draft', 'a' * 40, value=4)
        bundle = self.build(spec)
        self.assertEqual(candidate_arm(bundle, enabled=False)['block'], 8)
        self.assertEqual(candidate_arm(bundle, enabled=True)['block'], 4)

    def test_spec_mutation_and_unknown_fields_are_rejected(self):
        from harness.candidate import validate_spec
        for key, value in [('stock_default', 4), ('value', 4), ('unrecognized', True)]:
            spec = copy.deepcopy(self.spec)
            spec[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_spec(spec)

    def test_boolean_and_invalid_budgets_are_rejected(self):
        from harness.candidate import make_spec
        for value in (True, 0, -1, 2.5, '8', 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_spec(self.stock, self.config, '/target', '/draft', 'a' * 40, value=value)

    def test_config_drift_is_rejected(self):
        from harness.candidate import build_bundle
        self.config.write_text('{}')
        with self.assertRaises(ValueError):
            build_bundle(self.spec, self.root / 'bundle')

    def test_stock_tamper_is_detected_even_with_unchanged_marker(self):
        from harness.candidate import build_bundle
        (self.stock / 'python/module.py').write_text('changed')
        with self.assertRaises(ValueError):
            build_bundle(self.spec, self.root / 'bundle')

    def test_candidate_tamper_is_detected(self):
        from harness.candidate import candidate_arm
        bundle = self.build()
        (bundle / 'engine/python/module.py').write_text('changed')
        with self.assertRaises(ValueError):
            candidate_arm(bundle, enabled=False)

    def test_build_cannot_overwrite_existing_evidence(self):
        from harness.candidate import build_bundle
        bundle = self.build()
        with self.assertRaises(FileExistsError):
            build_bundle(self.spec, bundle)

    def test_symlink_is_rejected(self):
        from harness.candidate import make_spec
        (self.stock / 'python/link').symlink_to(self.config)
        with self.assertRaises(ValueError):
            make_spec(self.stock, self.config, '/target', '/draft', 'a' * 40)

    def test_internal_relative_file_link_is_preserved_and_hashed(self):
        from harness.build_engine import tree_sha
        from harness.candidate import make_spec,candidate_arm
        (self.stock / 'python/link').symlink_to('module.py')
        checksum = tree_sha(self.stock)
        (self.stock / 'TREE_SHA').write_text(checksum+'\n')
        spec = make_spec(self.stock,self.config,'/target','/draft','a'*40)
        bundle = self.build(spec)
        self.assertTrue((bundle / 'engine/python/link').is_symlink())
        self.assertEqual(candidate_arm(bundle)['tree_sha'],checksum)

    def test_mode_must_be_explicit_boolean(self):
        from harness.candidate import candidate_arm
        bundle = self.build()
        with self.assertRaises(ValueError):
            candidate_arm(bundle, enabled='false')

    def test_launch_environment_cannot_inherit_final_or_wrong_models(self):
        from harness.candidate import candidate_arm, launch_environment
        bundle = self.build()
        arm = candidate_arm(bundle, enabled=False)
        environment = launch_environment(dict(SPECPILOT_BAD='1', SP_KIND='final',
            SP_TARGET='/wrong', DRAFT_TOKENS='32'), arm, self.spec, 'gpu-0', 30100)
        self.assertNotIn('SPECPILOT_BAD', environment)
        self.assertEqual(environment['SP_TARGET'], '/target')
        self.assertEqual(environment['SP_KIND'], 'stock')
        self.assertEqual(environment['DRAFT_TOKENS'], '8')

    def test_server_identity_must_match_actual_launch(self):
        from harness.candidate import check_identity, expected_arguments
        identity = dict(tree_sha=self.spec['stock_tree_sha'], server_args=expected_arguments(self.spec, 8))
        check_identity(identity, self.spec, 8)
        for key, value in [('model_path', '/wrong'), ('speculative_num_draft_tokens', 32),
                           ('dtype', 'float32'), ('enable_fp32_lm_head', True)]:
            changed = copy.deepcopy(identity)
            changed['server_args'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_identity(changed, self.spec, 8)

    def test_receipt_tamper_is_rejected(self):
        from harness.candidate import candidate_arm
        bundle = self.build()
        (bundle / 'build.json').write_text('{}')
        with self.assertRaises(ValueError):
            candidate_arm(bundle)

    def test_candidate_launch_uses_snapshot_and_effective_option(self):
        from exp.candidate_smoke import CandidateServer, serve_command
        from harness.candidate import candidate_arm, make_spec
        spec = make_spec(self.stock,self.config,'/target','/draft','a'*40,value=4)
        bundle = self.build(spec)
        arm = candidate_arm(bundle,enabled=True)
        server = CandidateServer(arm,dict(uuid='gpu-0'),30100,self.root,{})
        command, environment = server.launch_spec()
        self.assertTrue(command[1].endswith('candidate_serve.sh'))
        self.assertEqual(environment['SP_ENGINE'],str(bundle / 'engine'))
        self.assertEqual(environment['DRAFT_TOKENS'],'4')
        argv = serve_command(spec,4,'/python',30100)
        self.assertEqual(argv[argv.index('--speculative-num-draft-tokens')+1],'4')
        self.assertNotIn('--enable-fp32-lm-head',argv)

    def test_non_noop_value_cannot_be_run_as_noop_smoke(self):
        from exp.candidate_smoke import smoke_manifest
        from harness.candidate import make_spec
        spec = make_spec(self.stock,self.config,'/target','/draft','a'*40,value=4)
        bundle = self.build(spec)
        with self.assertRaises(ValueError):
            smoke_manifest(bundle,[],[],[])

    def test_real_http_modes_swap_gpus_and_reject_missing_or_changed_evidence(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        from controller.http_transport import sha_ids
        from exp.candidate_smoke import run_modes, smoke_manifest, validate_smoke
        from exp.p3_pair_run import check_ports, write_json
        from harness.candidate import expected_arguments
        bundle = self.build()
        requests = [dict(id=suite, suite=suite, input_ids=[2, index], input_sha256=sha_ids([2,index]))
                    for index,suite in enumerate(('gsm8k','math500','humaneval','mbpp','mt-bench'))]
        gpus = [dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0,1)]
        serial = []
        specification = self.spec
        class FakeServer:
            def __init__(self, arm, gpu, port, output_dir, environment):
                self.arm, self.port, self.root = arm, port, output_dir
                self.number = len(serial) + 1
                serial.append(self.number)
            def start(self):
                arguments = expected_arguments(specification, self.arm['block'])
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args):
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
                        json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        self.send(dict(output_ids=[9,10], meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1, finish_reason=dict(type='stop'))))
                self.http = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
                self.thread = threading.Thread(target=self.http.serve_forever)
                self.thread.start()
                write_json(self.root / f'{self.arm["name"]}.process.json', dict(pid=self.number, start_ticks=self.number))
                if self.arm['name'] == 'candidate':
                    write_json(self.root / 'candidate.runtime.json',dict(pid=self.number,block=self.arm['block'],
                        spec_sha256=specification['spec_sha256'],module_origin=str(bundle / 'engine/python/module.py')))
            def wait_ready(self, timeout):
                pass
            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
                write_json(self.root / f'{self.arm["name"]}.stopped.json', dict(stopped=True))
        for port in range(36000,37000,10):
            try:
                check_ports([port,port+4])
                break
            except OSError:
                continue
        directory = self.root / 'run'
        directory.mkdir()
        manifest = smoke_manifest(bundle,gpus,requests,[port,port+4])
        write_json(directory / 'manifest.json',manifest)
        run_modes(directory,manifest,{},server_factory=FakeServer)
        result = validate_smoke(directory,require_scores=False)
        self.assertEqual(result['pairs'],20)
        self.assertEqual(len(serial),8)
        self.assertFalse(result['promoted'])
        round_dir = directory / 'disabled/round-01'
        runtime_path = round_dir / 'candidate.runtime.json'
        runtime_bytes = runtime_path.read_bytes()
        runtime = json.loads(runtime_bytes)
        runtime['module_origin'] = '/wrong/python/module.py'
        runtime_path.write_text(json.dumps(runtime))
        with self.assertRaises(ValueError):
            validate_smoke(directory,require_scores=False)
        runtime_path.write_bytes(runtime_bytes)
        original = (round_dir / 'complete.json').read_bytes()
        (round_dir / 'complete.json').write_text('{}')
        with self.assertRaises(ValueError):
            validate_smoke(directory,require_scores=False)
        (round_dir / 'complete.json').write_bytes(original)
        packets = sorted((round_dir / 'candidate-raw').glob('*.json'))
        packet = json.loads(packets[-1].read_text())
        packet['response']['output_ids'] = [99]
        packets[-1].write_text(json.dumps(packet))
        with self.assertRaises(ValueError):
            validate_smoke(directory,require_scores=False)


if __name__ == '__main__':
    unittest.main()
