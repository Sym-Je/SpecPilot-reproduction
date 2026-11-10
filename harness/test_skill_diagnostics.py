import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness import skill_diagnostics as diagnostics


class SkillDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.trace = self.root / 'stock.json'
        self.config = self.root / 'config.json'
        self.trace.write_text(json.dumps(dict(traceEvents=self.events())))
        self.config.write_text('{}')
        self.manifest = dict(protocol='stock-diagnostic-inputs-v1', scope='authorized-stock',
            trace=self.identity(self.trace), config=self.identity(self.config),
            workload=dict(phase='target-verify', batch_size=1, verify_rows=8, prefix_kv=118,
                shape_evidence='synthetic fixture, not a model measurement'))

    def identity(self, path):
        return dict(path=str(path), sha256=diagnostics.sha256(path))

    def events(self):
        return [dict(ph='X', cat='kernel', pid=0, name='first', ts=0, dur=10),
                dict(ph='X', cat='kernel', pid=0, name='second', ts=5, dur=10),
                dict(ph='X', cat='gpu_memcpy', pid=0, name='copy', ts=0, dur=100)]

    def test_work_busy_and_span_are_distinct_and_exclude_memcpy(self):
        result = diagnostics.kernel_statistics(self.events())['0']
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['work_us'], 20)
        self.assertEqual(result['busy_us'], 15)
        self.assertEqual(result['span_us'], 15)

    def test_gpu_processes_are_not_merged_into_one_busy_union(self):
        events = self.events() + [dict(ph='X', cat='kernel', pid=1, name='other', ts=0, dur=30)]
        result = diagnostics.kernel_statistics(events)
        self.assertEqual(result['0']['busy_us'], 15)
        self.assertEqual(result['1']['busy_us'], 30)

    def test_invalid_trace_timestamps_and_empty_kernels_rejected(self):
        with self.assertRaises(ValueError):
            diagnostics.kernel_statistics([])
        for value in (-1, float('nan'), float('inf'), '10', True):
            events = self.events()
            events[0]['dur'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                diagnostics.kernel_statistics(events)

    def test_crosscheck_rejects_count_sum_union_span_and_gpu_changes(self):
        reference = diagnostics.kernel_statistics(self.events())
        observed = dict(reference['0'], pid='0')
        self.assertTrue(diagnostics.crosscheck(reference, observed)['passed'])
        for field, value in (('count', 3), ('work_us', 21), ('busy_us', 16), ('span_us', 16), ('pid', '1')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagnostics.crosscheck(reference, dict(observed, **{field: value}))

    def test_input_hash_changes_rejected_before_output_creation(self):
        self.trace.write_text('changed')
        with self.assertRaises(ValueError):
            diagnostics.checked_manifest(self.manifest)

    def test_evidence_symlink_rejected(self):
        link = self.root / 'linked.json'
        link.symlink_to(self.trace)
        with self.assertRaises(ValueError):
            diagnostics.checked_file(dict(path=str(link), sha256=self.manifest['trace']['sha256']))

    def test_relative_url_sealed_and_config_paths_rejected(self):
        for name in ('trace.json', 'https://example.org/trace.json', '/unused/eval/sealed/trace.json',
                     '/unused/.config/trace.json', str(self.root / '..' / 'trace.json')):
            with self.subTest(name=name), self.assertRaises(ValueError):
                diagnostics.checked_file(dict(path=name, sha256='0' * 64))

    def test_unknown_fields_and_nonstock_scope_rejected(self):
        diagnostics.checked_manifest(self.manifest)
        for changes in (dict(command='shell'), dict(url='http://localhost'), dict(scope='author-final')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                diagnostics.checked_manifest(dict(self.manifest, **changes))

    def test_explicit_verify_shape_cannot_use_implicit_bs1_defaults(self):
        for field, value in (('verify_rows', 0), ('verify_rows', True), ('prefix_kv', None),
                             ('batch_size', 2), ('shape_evidence', ''), ('phase', 'decode')):
            record = copy.deepcopy(self.manifest)
            record['workload'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                diagnostics.checked_manifest(record)

    def test_tool_revision_and_files_are_pinned(self):
        snapshot = self.root / 'tools'
        snapshot.mkdir()
        script = snapshot / 'tool.py'
        script.write_text('print("fixture")\n')
        lock = self.root / 'lock.json'
        diagnostics.write_json(lock, dict(revision='fixed', files={'tool.py': diagnostics.sha256(script)}))
        record = dict(root=str(snapshot), revision='fixed')
        with patch.object(diagnostics, 'LOCK', lock):
            self.assertEqual(diagnostics.checked_tools(record), snapshot)
            with self.assertRaises(ValueError):
                diagnostics.checked_tools(dict(record, revision='main'))
            script.write_text('print("changed")\n')
            with self.assertRaises(ValueError):
                diagnostics.checked_tools(record)

    def test_extra_executable_dependency_rejected(self):
        snapshot = self.root / 'tools'
        snapshot.mkdir()
        (snapshot / 'sitecustomize.py').write_text('')
        lock = self.root / 'lock.json'
        diagnostics.write_json(lock, dict(revision='fixed', files={}))
        with patch.object(diagnostics, 'LOCK', lock), self.assertRaises(ValueError):
            diagnostics.checked_tools(dict(root=str(snapshot), revision='fixed'))

    def test_unknown_tool_cannot_start_process(self):
        with patch.object(diagnostics.subprocess, 'Popen') as process, self.assertRaises(ValueError):
            diagnostics.run_tool(self.root, 'shell', [], self.root)
        process.assert_not_called()

    def test_worker_rejects_network_before_any_connection(self):
        script = self.root / diagnostics.ENTRYPOINTS['profiler']
        script.parent.mkdir(parents=True)
        script.write_text('import socket\nsocket.socket()\n')
        result = diagnostics.run_tool(self.root, 'profiler', [], self.root)
        self.assertNotEqual(result['exit_code'], 0)
        self.assertIn('deny network', (self.root / 'profiler.stderr.txt').read_text())

    def test_worker_rejects_nested_process(self):
        script = self.root / diagnostics.ENTRYPOINTS['compute']
        script.parent.mkdir(parents=True)
        script.write_text('import subprocess\nsubprocess.run(["/bin/true"])\n')
        result = diagnostics.run_tool(self.root, 'compute', [], self.root)
        self.assertNotEqual(result['exit_code'], 0)

    def test_worker_timeout_is_failure(self):
        script = self.root / diagnostics.ENTRYPOINTS['compute']
        script.parent.mkdir(parents=True)
        script.write_text('import time\ntime.sleep(30)\n')
        result = diagnostics.run_tool(self.root, 'compute', [], self.root, timeout=.1)
        self.assertTrue(result['timed_out'])
        self.assertNotEqual(result['exit_code'], 0)

    def test_analysis_is_diagnostic_and_missing_layer_evidence_stays_unknown(self):
        manifest, tools = self.root / 'manifest.json', self.root / 'tools.json'
        diagnostics.write_json(manifest, self.manifest)
        diagnostics.write_json(tools, dict(root=str(self.root), revision='fixture'))
        def run(root, tool, arguments, output):
            if tool == 'extract':
                diagnostics.write_json(output / 'extract.stdout.txt', dict(
                    pid='0', count=2, work_us=20, busy_us=15, span_us=15,
                    stage_work_us={'all': 20}, upstream_activity={'count': 3}))
            return dict(exit_code=0, timed_out=False)
        with patch.object(diagnostics, 'checked_tools', return_value=self.root), patch.object(diagnostics, 'run_tool', side_effect=run):
            result = diagnostics.analyze(manifest, tools, self.root / 'output')
        self.assertTrue(result['engineering_passed'])
        self.assertFalse(result['controller_accepted'])
        self.assertFalse(result['ledger_eligible'])
        self.assertFalse(result['stage_attribution_validated'])
        self.assertIsNone(result['formal_ceiling'])
        self.assertEqual(result['gpu_submissions'], 0)
        self.assertEqual(result['tools']['pipeline']['status'], 'not_run_unverified_layer_boundaries')

    def test_existing_or_protected_output_cannot_be_overwritten(self):
        manifest, tools = self.root / 'manifest.json', self.root / 'tools.json'
        diagnostics.write_json(manifest, self.manifest)
        diagnostics.write_json(tools, {})
        for output, exception in ((self.root, FileExistsError), (self.root / 'controller' / 'output', ValueError)):
            with self.subTest(output=output), patch.object(diagnostics, 'checked_tools', return_value=self.root), patch.object(diagnostics, 'run_tool') as run:
                with self.assertRaises(exception):
                    diagnostics.analyze(manifest, tools, output)
                run.assert_not_called()

    def test_single_and_two_gpu_commands_request_higher_priority_before_user_command(self):
        from exp.engine_resource import command
        from exp.gpu_autonomy import prepare_submission
        request = self.root / 'request.json'
        request.write_text('{}')
        archive = self.root / 'source.tar'
        archive.write_bytes(b'fixture')
        two = command(request, archive, self.root / 'remote', 'fixture-two', 1800)
        one = prepare_submission(self.root, archive, self.root / 'remote', 'fixture-one',
            dict(pod_deadline_seconds=900))['command']
        for arguments in (one, two):
            index = arguments.index('--k8s-priority')
            self.assertEqual(arguments[index + 1], '3')
            self.assertLess(index, len(arguments) - 2)
            self.assertNotIn('--k8s-no-reclaim', arguments)


if __name__ == '__main__':
    unittest.main()
