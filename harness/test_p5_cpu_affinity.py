import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp import p3_pair_run as runner


class CpuAffinityTests(unittest.TestCase):
    def test_option_is_explicit_and_only_stable_null(self):
        args = runner.parse_args(['stock', 'stock', '--rounds', '4', '--stable-null', '--pin-cpus', '--out-dir', '/unused'])
        self.assertTrue(args.pin_cpus)
        self.assertFalse(runner.parse_args(['ar', 'stock', '--out-dir', '/unused']).pin_cpus)
        with self.assertRaises(SystemExit):
            runner.parse_args(['ar', 'stock', '--pin-cpus', '--out-dir', '/unused'])

    def test_plan_uses_distinct_physical_cores_and_is_gpu_bound(self):
        from harness.cpu_affinity import plan_bindings
        topology = {number: (0, number % 24) for number in range(48)}
        processes = {name: [dict(pid=100 + index, comm='sglang::schedul', start_ticks=20,
                        allowed_cpus=list(range(48)))] for index, name in enumerate(('stock-a', 'stock-b'))}
        servers = [SimpleNamespace(arm={'name': name}, gpu={'uuid': gpu})
                   for name, gpu in (('stock-a', 'gpu-b'), ('stock-b', 'gpu-a'))]
        with patch('harness.cpu_affinity.cpu_topology', return_value=topology):
            plan = plan_bindings(servers, processes)
        self.assertEqual(plan['gpu-a']['main_cpu'], 2)
        self.assertEqual(plan['gpu-b']['main_cpu'], 11)
        self.assertFalse(set(plan['gpu-a']['worker_cpus']) & set(plan['gpu-b']['worker_cpus']))
        self.assertEqual(len(plan['gpu-a']['worker_cpus']), 8)
        with patch('harness.cpu_affinity.cpu_topology', return_value={number: (0, 0) for number in range(48)}):
            with self.assertRaises(ValueError):
                plan_bindings(servers, processes)

    def test_binding_only_modifies_owned_server_threads(self):
        from harness.cpu_affinity import apply_bindings
        allowed = sorted(os.sched_getaffinity(0))
        if len(allowed) < 2:
            self.skipTest('requires two allowed CPUs')
        original = set(allowed)
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen(['sleep', '30'])
            try:
                server = SimpleNamespace(process=process, arm={'name': 'stock-a'}, gpu={'uuid': 'gpu-a'})
                from harness.telemetry import Telemetry
                records = Telemetry([server], [], Path(directory) / 'unused').read_processes()
                plan = {'gpu-a': {'main_cpu': allowed[0], 'worker_cpus': [allowed[1]]}}
                with patch('harness.cpu_affinity.is_scheduler', return_value=True):
                    evidence = apply_bindings([server], plan)
                self.assertEqual(os.sched_getaffinity(process.pid), {allowed[0]})
                self.assertEqual(os.sched_getaffinity(0), original)
                self.assertEqual(evidence['stock-a']['scheduler_pid'], process.pid)
                self.assertEqual(evidence['stock-a']['start_ticks'], records['stock-a'][0]['start_ticks'])
            finally:
                process.terminate()
                process.wait()

    def test_thread_evidence_rejects_drift_or_missing_thread(self):
        from harness.cpu_affinity import check_thread_evidence
        policy = {'main_cpu': 3, 'worker_cpus': [4, 5], 'scheduler_pid': 100}
        processes = [{'pid': 100, 'thread_affinities': [{'tid': 100, 'allowed_cpus': [3]},
                       {'tid': 101, 'allowed_cpus': [4, 5]}]}]
        check_thread_evidence(processes, policy)
        for invalid in ([{'pid': 100, 'thread_affinities': []}],
                        [{'pid': 100, 'thread_affinities': [{'tid': 100, 'allowed_cpus': [3, 4]}]}],
                        [{'pid': 100, 'thread_affinities': [{'tid': 100, 'allowed_cpus': [3]},
                                                           {'tid': 101, 'allowed_cpus': [90]}]}]):
            with self.assertRaises(ValueError):
                check_thread_evidence(invalid, policy)

    def cpu_fixture(self):
        from harness.test_p5_stability import StableValidationTests
        helper = StableValidationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        manifest = json.loads((helper.root / 'manifest.json').read_text())
        manifest['cpu_pinning'] = True
        manifest['gpus'] = [{'uuid': f'gpu-{index}'} for index in (0, 1)]
        helper.write(helper.root / 'manifest.json', manifest)
        plan = {f'gpu-{index}': dict(main_cpu=index * 9,
                    worker_cpus=list(range(index * 9 + 1, index * 9 + 9)),
                    physical_cores=[[0, cpu] for cpu in range(index * 9, index * 9 + 9)]) for index in (0, 1)}
        helper.write(helper.root / 'cpu-plan.json', plan)
        for number in range(1, 5):
            current = helper.root / f'round-{number:02d}'
            deployment = json.loads((current / 'deployment.json').read_text())
            samples = [json.loads(line) for line in (current / 'telemetry.jsonl').read_text().splitlines()]
            bindings = {}
            for assignment in deployment['assignments']:
                arm, gpu = assignment['arm']['name'], assignment['gpu']['uuid']
                process = samples[0]['arms'][arm][0]
                bindings[arm] = dict(plan[gpu], gpu_uuid=gpu, scheduler_pid=process['pid'], start_ticks=process['start_ticks'])
                for sample in samples:
                    sample['arms'][arm][0]['thread_affinities'] = [{'tid': process['pid'], 'allowed_cpus': [plan[gpu]['main_cpu']]}]
            helper.write(current / 'cpu-binding-ready.json', bindings)
            helper.write(current / 'cpu-binding-measured.json', bindings)
            helper.rows(current / 'telemetry.jsonl', samples)
        return helper

    def test_cpu_validator_accepts_bound_evidence_without_changing_controller_ci(self):
        from controller.stability_validation import validate_stable
        from harness.cpu_affinity import validate_cpu_bound
        helper = self.cpu_fixture()
        original = validate_stable(helper.root)
        result = validate_cpu_bound(helper.root)
        self.assertTrue(result['cpu_binding_protocol_passed'])
        self.assertEqual(result['ci95'], original['ci95'])

    def test_cpu_validator_rejects_missing_binding_and_observed_drift(self):
        from harness.cpu_affinity import validate_cpu_bound
        helper = self.cpu_fixture()
        target = helper.root / 'round-01/cpu-binding-ready.json'
        target.unlink()
        with self.assertRaises(FileNotFoundError):
            validate_cpu_bound(helper.root)
        helper = self.cpu_fixture()
        target = helper.root / 'round-01/telemetry.jsonl'
        samples = [json.loads(line) for line in target.read_text().splitlines()]
        samples[0]['arms']['stock-a'][0]['thread_affinities'][0]['allowed_cpus'] = [900]
        helper.rows(target, samples)
        with self.assertRaises(ValueError):
            validate_cpu_bound(helper.root)

    def test_runner_binds_before_warmup_and_before_measurement(self):
        from harness.test_p3_pair_run import FakeBench, FakeServer
        class Bench(FakeBench):
            def __init__(self, *arms, **options):
                super().__init__(*arms)

        FakeServer.fail_arm = FakeBench.fail_request = None
        arms = [{'name': name, 'block': 8, 'tree_sha': 'synthetic', 'engine': '/unused'}
                for name in ('stock-a', 'stock-b')]
        gpus = [{'index': index, 'uuid': f'gpu-{index}'} for index in (0, 1)]
        requests = [{'id': 'one', 'suite': 'suite', 'input_ids': [1], 'input_sha256': runner.sha_ids([1])}]
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'Telemetry'), \
                patch('harness.cpu_affinity.owned_processes', return_value={}), \
                patch('harness.cpu_affinity.plan_bindings', return_value={'gpu-0': {'main_cpu': 2}}), \
                patch('harness.cpu_affinity.apply_bindings', return_value={'bound': True}) as apply:
            runner.run_round(arms, gpus, [31000, 31010], 0, requests, Path(directory) / 'round-01', {},
                2048, 2, 30, server_factory=FakeServer, bench_factory=Bench, stable_null=True, cpu_plan={})
            self.assertEqual(apply.call_count, 2)
            self.assertEqual(apply.call_args.kwargs['expected'], {'bound': True})
            self.assertTrue((Path(directory) / 'cpu-plan.json').exists())
