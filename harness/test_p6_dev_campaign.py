import copy
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from harness import test_p3_baseline_validation as baseline_tests
from harness import test_p5_scored_forcing as scored_tests


class DevCampaignTests(unittest.TestCase):
    def test_actual_http_rounds_capture_all_warmups_and_reject_missing_full_warmup(self):
        from controller.dev_campaign import validate_session
        from controller.http_transport import sha_ids
        from controller.paper_policy import measurement_protocol_id
        from exp import dev_campaign, p3_pair_run
        gpus = [dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0, 1)]
        ports = []
        for candidate in range(34000, 35000, 10):
            try:
                p3_pair_run.check_ports([candidate, candidate + 4])
                ports = [candidate, candidate + 4]
                break
            except OSError:
                continue
        self.assertTrue(ports)
        serial = []
        class Server:
            def __init__(self, arm, gpu, port, output_dir, environment):
                self.arm, self.gpu, self.port = arm, gpu, port
                self.number = len(serial) + 1
                serial.append(self.number)
            def start(self):
                arm = self.arm
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args): pass
                    def send(self, value):
                        payload = json.dumps(value).encode()
                        self.send_response(200)
                        self.send_header('Content-Length', str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    def do_GET(self):
                        self.send(dict(model_path='/model', dtype='bfloat16', enable_fp32_lm_head=False,
                            speculative_algorithm='DFLASH', speculative_num_draft_tokens=arm['block']))
                    def do_POST(self):
                        json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        time.sleep(.015)
                        self.send(dict(output_ids=[9, 10], meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1, finish_reason={'type': 'stop'})))
                self.http = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
                self.thread = threading.Thread(target=self.http.serve_forever)
                self.thread.start()
            def wait_ready(self, timeout): pass
            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
        class Telemetry:
            def __init__(self, servers, gpus, path, **options):
                self.servers, self.gpus, self.path = servers, gpus, path
                self.stop = threading.Event()
            def __enter__(self):
                def monitor():
                    with self.path.open('x') as output:
                        while not self.stop.is_set():
                            output.write(json.dumps(dict(time_unix=time.time(),
                                gpus=[dict(gpu, clocks_sm_mhz=1000, clocks_mem_mhz=1000,
                                           temperature_c=40, power_w=100) for gpu in self.gpus],
                                arms={server.arm['name']:[dict(pid=server.number, start_ticks=server.number,
                                      allowed_cpus='0-1')] for server in self.servers}))+'\n')
                            output.flush()
                            self.stop.wait(.02)
                self.thread = threading.Thread(target=monitor)
                self.thread.start()
                return self
            def __exit__(self, *args):
                self.stop.set()
                self.thread.join()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            requests = [dict(id=f'{suite}-{index}', suite=suite, turn=0, input_ids=[2, index],
                            input_sha256=sha_ids([2, index])) for suite in p3_pair_run.SUITES for index in range(6)]
            arms = [dict(name=name, block=block, tree_sha='a'*64, env={}) for name, block in (('stock',8),('final',32))]
            campaign = dict(directory=str(root), campaign_id='test', source_pin='b'*40, source_sha256={},
                campaign_protocol_version='dev-joint-v1', full_scale_warmup=True, synchronized_start=True,
                raw_capture=True, requests=requests, suites=p3_pair_run.SUITES, rounds=2, per_suite=6,
                max_new_tokens=2048, warmup=2, sampling=dict(temperature=0.0, top_k=1, enable_thinking=True),
                model_path='/model', declared_models={}, gpus=gpus, ports=ports, candidate_arms=arms,
                launch_protocol=dict(model_path='/model',dtype='bfloat16', enable_fp32_lm_head=False))
            campaign['protocol_id'] = measurement_protocol_id(campaign)
            original = p3_pair_run.run_round
            def run_round(*args, **options):
                return original(*args, **options, server_factory=Server)
            with patch('exp.dev_campaign.run_round', run_round), patch('exp.p3_pair_run.Telemetry',Telemetry), patch('exp.dev_campaign.wait_for_idle',return_value=gpus):
                dev_campaign.run_session(root/'candidate', campaign, {})
            validate_session(root/'candidate',campaign)
            warm = root/'candidate/round-01/warmup.jsonl'
            warm.write_text('\n'.join(warm.read_text().splitlines()[:-1])+'\n')
            with self.assertRaises(ValueError): validate_session(root/'candidate',campaign)

    def test_thirty_requests_require_explicit_protocol_without_relaxing_legacy(self):
        from harness.baseline_validation import validate_paired_run
        helper = baseline_tests.BaselineValidationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.fixture(per_suite=6)
        result, _, _ = validate_paired_run(helper.root, ['ar', 'stock'], per_suite=6)
        self.assertEqual(result['requests'], 30)
        self.assertEqual(result['pairs'], 60)
        with self.assertRaises(ValueError): validate_paired_run(helper.root, ['ar', 'stock'])

    def test_full_warmup_and_capture_mode_are_part_of_the_protocol_identity(self):
        from controller.paper_policy import measurement_protocol_id
        manifest = dict(model_path='/model', declared_models={}, sampling={}, requests=[], suites=[],
                        rounds=2, warmup=2, per_suite=6, max_new_tokens=2048, gpus=[],
                        campaign_protocol_version='dev-joint-v1', full_scale_warmup=True,
                        synchronized_start=True, raw_capture=True)
        changed = dict(manifest, full_scale_warmup=False)
        self.assertNotEqual(measurement_protocol_id(manifest), measurement_protocol_id(changed))

    def test_source_capture_is_real_and_its_disk_write_is_outside_elapsed_time(self):
        from controller.http_transport import Arm
        with tempfile.TemporaryDirectory() as temporary:
            arm = Arm('stock', 'http://test', raw_dir=Path(temporary) / 'raw')
            arm.begin_session()
            response = dict(output_ids=[9], meta_info={'completion_tokens': 1, 'finish_reason': {'type': 'stop'}})
            def post(url, body, timeout=3600, timing=None, capture=None):
                capture.update(url=url, request=body, response=response, http_status=200)
                return response
            original = Path.open
            def delayed_open(path, *args, **kwargs):
                if path.suffix == '.json': time.sleep(.05)
                return original(path, *args, **kwargs)
            with patch('controller.http_transport._post', post), patch.object(Path, 'open', delayed_open):
                started = time.perf_counter()
                result = arm.step([2, 3], 2048)
                wall = time.perf_counter() - started
            self.assertGreater(wall - result['latency_ms'] / 1000, .04)
            packet = json.loads(Path(result['raw_evidence']['path']).read_text())
            self.assertEqual(packet['response']['output_ids'], result['output_ids'])
            self.assertEqual(packet['request']['input_ids'], [2, 3])

    def test_phase_order_cannot_be_relabelled_after_measurement(self):
        from controller.dev_campaign import check_phase_order
        phases = [dict(started_unix=index * 10 + 1, completed_unix=index * 10 + 9) for index in range(3)]
        check_phase_order(phases)
        with self.assertRaises(ValueError): check_phase_order(list(reversed(phases)))

    def test_both_rounds_must_pass_and_both_are_bound_in_the_correctness_receipt(self):
        from controller.dev_campaign import combine_correctness
        good = {'correctness_passed': True, 'evidence_sha256': 'a' * 64}
        bad = dict(good, correctness_passed=False, evidence_sha256='b' * 64)
        self.assertTrue(combine_correctness([good, good])['correctness_passed'])
        self.assertFalse(combine_correctness([good, bad])['correctness_passed'])
        with self.assertRaises(ValueError): combine_correctness([good])

    def test_forcing_is_bound_to_the_actual_measured_output_not_a_replacement(self):
        from controller.dev_campaign import check_scored_measurements
        helper = scored_tests.ScoredForcingTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        path = helper.trace([4] * 8)
        trace = json.loads(path.read_text())
        row = dict(id='one', output_ids=trace['output_ids'], raw_evidence=trace['generation_segments'][0],
                   generator=trace['generator'])
        request = dict(id='one', input_ids=trace['prompt_ids'])
        check_scored_measurements([path], [row], [request], evidence_root=helper.root)
        replaced = copy.deepcopy(row)
        replaced['output_ids'][0] = 99
        with self.assertRaises(ValueError):
            check_scored_measurements([path], [replaced], [request], evidence_root=helper.root)
