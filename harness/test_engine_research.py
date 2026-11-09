import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.engine_research import Budget, validate_action


class EngineResearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.action = dict(kind='run_engine', value=4, per_suite=1, max_new_tokens=2048,
                           reason='falsifiable startup-option diagnostic')
        self.budget = Budget(self.root / 'budget.json', now=1000)

    def test_action_accepts_only_numeric_startup_option(self):
        self.assertEqual(validate_action(self.action), self.action)
        for field, value in [('value', True), ('value', 0), ('value', 65), ('value', '4'),
                             ('per_suite', True), ('per_suite', 7), ('max_new_tokens', 64),
                             ('reason', ''), ('kind', 'run_shell')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_action(dict(self.action, **{field: value}))
        for extra in ('command', 'image', 'path', 'source_overlay', 'gpu_budget', 'controller_accepted'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_action(dict(self.action, **{extra: 'untrusted'}))

    def test_feedback_schema_cannot_invert_throughput_and_latency(self):
        from harness.engine_research import feedback_metrics
        original = dict(protocol='startup-option-research-v1', geomean=.8, lower=.7, upper=.9)
        annotated = feedback_metrics(original)
        self.assertNotIn('metric_definition', original)
        self.assertEqual(annotated['geomean'], .8)
        self.assertEqual(annotated['metric_definition']['improvement_direction'], 'higher_is_better')
        self.assertTrue(annotated['metric_definition']['not_a_latency_ratio'])
        self.assertEqual(feedback_metrics(annotated), annotated)

    def test_controller_json_roundtrip_preserves_semantics_but_not_tampering(self):
        from harness.engine_research import json_record
        raw = dict(process_sessions=[(('stock', 10, 100), ('final', 11, 101))], interval=dict(lower=1.06))
        stored = json.loads(json.dumps(raw))
        self.assertNotEqual(raw, stored)
        self.assertEqual(json_record(raw), stored)
        stored['interval']['lower'] = 1.01
        self.assertNotEqual(json_record(raw), stored)

    def test_unknown_submission_resume_never_calls_create(self):
        from exp.engine_resource import execute
        request = dict(action=self.action)
        job = self.root / 'existing'
        job.mkdir()
        (job / 'request.json').write_text(json.dumps(request))
        (job / 'source.tar').write_bytes(b'old source')
        (job / 'pending.json').write_text('{}')
        (job / 'submitted.json').write_text('{"uuid":"job-old"}')
        self.budget.reserve('existing', 2, 100, now=1001)
        self.budget.update('existing', uuid='job-old', create_calls=1)
        with patch('exp.engine_resource.query', return_value=[]), patch('exp.engine_resource.subprocess.run') as run:
            with self.assertRaises(RuntimeError):
                execute(job, job / 'source.tar', self.budget, resume_only=True)
            run.assert_not_called()

    def test_stage_audit_rejects_incomplete_run(self):
        from harness.engine_research_audit import audit
        state = self.budget.read()
        (self.root / 'resource-state.json').write_text(json.dumps(state))
        (self.root / 'result.json').write_text(json.dumps(dict(status='running', resource_state=state)))
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_stage_audit_rejects_raised_resource_limits(self):
        from harness.engine_research_audit import audit
        state = dict(self.budget.read(), gpu_seconds=230401)
        (self.root / 'resource-state.json').write_text(json.dumps(state))
        (self.root / 'result.json').write_text(json.dumps(dict(status='completed', resource_state=state)))
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_recovery_keeps_original_budget_across_multiple_checkpoints(self):
        from exp.engine_autonomy import resume_resources
        first, second = self.root / 'first', self.root / 'second'
        first.mkdir()
        second.mkdir()
        original = self.root / 'budget.json'
        (first / 'recovery.json').write_text(json.dumps(dict(resource_path=str(original))))
        (second / 'recovery.json').write_text(json.dumps(dict(resource_path=str(resume_resources(first)))))
        self.assertEqual(resume_resources(second), original)
        (first / 'recovery.json').write_text(json.dumps(dict(resource_path=str(self.root / 'missing'))))
        with self.assertRaises(ValueError):
            resume_resources(first)
        self.assertFalse((self.root / 'missing').exists())

    def test_budget_reopening_cannot_raise_stage_limits(self):
        state = dict(self.budget.read(), gpu_seconds=230401)
        self.budget.path.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            Budget(self.budget.path)

    def test_recovery_feedback_keeps_all_original_jobs(self):
        from exp.engine_autonomy import lineage_feedback
        first, second, third = [self.root / name for name in ('first','second','third')]
        for root in (first,second,third):
            root.mkdir()
        (second / 'recovery.json').write_text(json.dumps(dict(prior_run=str(first))))
        (third / 'recovery.json').write_text(json.dumps(dict(prior_run=str(second))))
        for root, name in ((first,'sp-engine-first'),(second,'sp-engine-second')):
            job = root / name
            job.mkdir()
            (job / 'feedback.json').write_text(json.dumps(dict(uuid=name,status='completed')))
        self.assertEqual([row['uuid'] for row in lineage_feedback(third)], ['sp-engine-first','sp-engine-second'])
        (first / 'recovery.json').write_text(json.dumps(dict(prior_run=str(third))))
        with self.assertRaises(ValueError):
            lineage_feedback(third)

    def test_duplicate_name_is_rejected_after_restart(self):
        self.budget.reserve('one', 2, 4500, now=1001)
        restored = Budget(self.root / 'budget.json', now=2000)
        with self.assertRaises(ValueError):
            restored.reserve('one', 2, 4500, now=2000)
        self.assertEqual(restored.read()['started'], 1000)

    def test_uncertain_attempt_holds_full_reservation(self):
        self.budget.reserve('one', 8, 28000, now=1001)
        self.budget.update('one', create_calls=1)
        with self.assertRaises(ValueError):
            self.budget.reserve('two', 1, 100, now=1002)
        with self.assertRaises(ValueError):
            self.budget.update('one', charged_gpu_seconds=0)
        with self.assertRaises(ValueError):
            self.budget.update('one', create_calls=1)

    def test_wall_and_total_time_are_independent_limits(self):
        with self.assertRaises(ValueError):
            self.budget.reserve('late', 1, 3000, now=85000)
        with self.assertRaises(ValueError):
            self.budget.reserve('large', 8, 30000, now=1001)

    def test_only_terminal_receipt_releases_resources(self):
        self.budget.reserve('one', 8, 28000, now=1001)
        with self.assertRaises(ValueError):
            self.budget.update('one', terminated=True, charged_gpu_seconds=10)
        self.budget.update('one', terminal='Completed', terminated=True, charged_gpu_seconds=10)
        self.budget.reserve('two', 8, 28000, now=1100)
        with self.assertRaises(ValueError):
            self.budget.update('one', terminal='Failed', terminated=True, charged_gpu_seconds=0)

    def test_invalid_resource_types_are_rejected(self):
        for gpus, seconds in [(True, 100), (3, 100), (9, 100), (2, True), (2, 0)]:
            with self.subTest(gpus=gpus, seconds=seconds), self.assertRaises(ValueError):
                self.budget.reserve('bad', gpus, seconds, now=1001)

    def test_adapter_preserves_input_and_enforces_readonly_models(self):
        from exp.engine_northjob import bounded_template
        template = dict(spec=dict(tasks=[dict(replicas=1, template=dict(spec=dict(containers=[dict(
            resources=dict(limits={'nvidia.com/gpu': '2'}))]))) ]))
        previous = copy.deepcopy(template)
        result = bounded_template(template, 3600)
        self.assertEqual(template, previous)
        pod = result['spec']['tasks'][0]['template']['spec']
        self.assertEqual(pod['activeDeadlineSeconds'], 3600)
        self.assertEqual(pod['containers'][0]['resources']['limits']['nvidia.com/gpu'], '2')
        self.assertTrue(pod['containers'][0]['volumeMounts'][0]['readOnly'])
        self.assertEqual(result['spec']['maxRetry'], 0)
        self.assertEqual(result['spec']['policies'][0]['action'], 'AbortJob')
        for deadline in (True, 599, 7201):
            with self.assertRaises(ValueError):
                bounded_template(template, deadline)
        bad = copy.deepcopy(template)
        bad['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu'] = 8
        with self.assertRaises(ValueError):
            bounded_template(bad, 3600)

    def test_cli_is_trusted_and_explicit(self):
        from exp.engine_resource import command
        request, source = self.root / 'request.json', self.root / 'source.tar'
        request.write_text(json.dumps(self.action))
        source.write_bytes(b'archive fixture')
        cli = command(request, source, self.root / 'output', 'bounded-test', 3600)
        for flag, value in [('--gpu-per-node', '2'), ('--project', 'WeaverDev'),
                            ('--k8s-queue', 'qiji'), ('--k8s-namespace', 'qiji')]:
            self.assertEqual(cli[cli.index(flag) + 1], value)
        self.assertIn('@sha256:', cli[cli.index('--k8s-images') + 1])
        self.assertNotIn('source_overlay', cli[-1])

    def test_null_server_uses_stock_launcher_without_candidate_bundle(self):
        from exp.engine_research import ResearchServer, Server
        server = ResearchServer.__new__(ResearchServer)
        server.arm = dict(name='stock-a')
        with patch.object(Server, 'launch_spec', return_value=('trusted', {})) as launch:
            self.assertEqual(server.launch_spec(), ('trusted', {}))
            launch.assert_called_once()

    def test_actual_http_pair_audit_and_tamper_rejection(self):
        from contextlib import nullcontext
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        from controller.http_transport import sha_ids
        from exp.engine_research import audit
        from exp.candidate_smoke import CapturedArm
        from exp.p3_pair_run import SUITES, check_ports, run_round
        from harness.candidate import candidate_arm, expected_arguments
        from harness.test_p10_candidate import CandidateTests
        fixture = CandidateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.build()
        spec = fixture.spec
        request = self.root / 'request.json'
        action = dict(self.action, value=8)
        request.write_text(json.dumps(dict(action=action, source_pin='a' * 40)))
        source = self.root / 'source.tar'
        source.write_bytes(b'fixed fixture')
        directory = self.root / 'remote'
        directory.mkdir()
        arms = [dict(name='stock', block=8, tree_sha=spec['stock_tree_sha'], engine=str(fixture.stock), env={}),
                candidate_arm(bundle, enabled=True)]
        requests = [dict(id=suite, suite=suite, input_ids=[2,index], input_sha256=sha_ids([2,index]))
                    for index,suite in enumerate(SUITES)]
        gpus = [dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0,1)]
        from exp.engine_research import file_sha
        manifest = dict(action=action, source_pin='a' * 40, request_sha256=file_sha(request),
            source_archive_sha256=file_sha(source), requests=requests, gpus=gpus, arms=arms, bundle=str(bundle))
        serial = []
        class FakeServer:
            def __init__(self, arm, gpu, port, output_dir, environment):
                self.arm, self.port, self.root = arm, port, output_dir
                self.number = len(serial) + 1
                serial.append(self.number)
            def start(self):
                arguments = expected_arguments(spec, self.arm['block'])
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
                        self.send(dict(output_ids=[9,10], meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1, finish_reason=dict(type='stop'))))
                self.http = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
                self.thread = threading.Thread(target=self.http.serve_forever)
                self.thread.start()
                (self.root / f'{self.arm["name"]}.process.json').write_text(json.dumps(dict(pid=self.number, start_ticks=self.number)))
                if self.arm['name'] == 'candidate':
                    (self.root / 'candidate.runtime.json').write_text(json.dumps(dict(pid=self.number,
                        block=8, spec_sha256=spec['spec_sha256'], module_origin=str(bundle / 'engine/python/module.py'))))
            def wait_ready(self, timeout):
                pass
            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
                (self.root / f'{self.arm["name"]}.stopped.json').write_text('{"stopped":true}')
        for port in range(37000,38000,10):
            try:
                check_ports([port,port+2])
                break
            except RuntimeError:
                continue
        manifest['ports'] = [port,port+2]
        path = directory / 'manifest.json'
        path.write_text(json.dumps(manifest))
        with patch('exp.engine_research.FROZEN_STOCK_SHA', spec['stock_tree_sha']), patch(
                'exp.p3_pair_run.Telemetry', side_effect=lambda *arguments,**options:nullcontext()):
            for number in (0,1):
                root = directory / f'round-{number+1:02d}'
                def factory(name, url, **options):
                    return CapturedArm(name, url, directory=root, spec=spec, **options)
                run_round(arms,gpus,manifest['ports'],number,requests,root,{},2048,2,3,
                    server_factory=FakeServer, arm_factory=factory, stable_null=True)
            self.assertEqual(audit(directory)['n_pairs'], 10)
            for relative in ('round-02/deployment.json', 'round-01/stock.stopped.json',
                             'round-02/candidate.runtime.json', 'round-01/warmup.jsonl',
                             'round-02/pairs.jsonl'):
                changed = directory / relative
                original = changed.read_bytes()
                changed.write_text('{}\n')
                with self.subTest(path=relative), self.assertRaises((ValueError, KeyError)):
                    audit(directory)
                changed.write_bytes(original)
            request.write_text('{}')
            with self.assertRaises((ValueError, KeyError)):
                audit(directory)


if __name__ == '__main__':
    unittest.main()
