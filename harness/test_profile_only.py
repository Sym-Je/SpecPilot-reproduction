"""Acceptance registered before production implementation.

python -B -m unittest harness.test_profile_only -v
First red: logs/stock-profile-autonomy-20261111-a01/skill-tests/profile-only-red.log
Regression: python -B -m unittest harness.test_profile_only
harness.test_skill_diagnostics harness.test_skill_rsi -v
Only non-sensitive tmp traces/CPU fixtures; no capture/model/GPU requests.
Observed facts acceptance: same command; profile-shape-facts-red.log precedes implementation.
Paging acceptance: same command; profile-shape-paging-red.log precedes implementation.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness import skill_broker, skill_diagnostics as diagnostics


class ProfileOnlyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.trace = self.root / 'trace.json'
        self.config = self.root / 'config.json'
        self.events = [dict(ph='X', cat='kernel', name='first', pid=0, tid=1, ts=0, dur=10),
                       dict(ph='X', cat='kernel', name='second', pid=0, tid=2, ts=5, dur=10),
                       dict(ph='X', cat='gpu_memcpy', name='copy', pid=0, tid=1, ts=0, dur=100)]
        diagnostics.write_json(self.trace, {'traceEvents': self.events})
        diagnostics.write_json(self.config, {'fixture': 'not a real model'})
        self.manifest = dict(protocol='stock-profile-only-inputs-v1', scope='authorized-stock',
            trace=self.reference(self.trace), config=self.reference(self.config), workload=None)
        self.manifest_path = self.root / 'manifest.json'
        diagnostics.write_json(self.manifest_path, self.manifest)
        self.tools = self.root / 'tools.json'
        diagnostics.write_json(self.tools, dict(root=str(self.root / 'upstream'), revision='fixture'))
        self.access = skill_broker.SkillAccess('direction', {'profile-01': self.manifest_path}, self.tools, self.root / 'cache')
        self.calls = []

    def reference(self, path):
        return dict(path=str(path), sha256=diagnostics.sha256(path))

    def run_tool(self, root, tool, arguments, output):
        self.calls.append(tool)
        if tool not in ('extract', 'profiler'):
            raise AssertionError('profile-only must never execute ' + tool)
        if tool == 'extract':
            diagnostics.write_json(output / 'extract.stdout.txt', dict(pid='0', count=2, work_us=20,
                busy_us=15, span_us=15, stage_work_us={'unknown': 20}, upstream_activity={'count': 3}))
        else:
            (output / 'profiler.stdout.txt').write_text('synthetic profiler report')
        (output / (tool + '.stderr.txt')).write_text('')
        return dict(exit_code=0, timed_out=False, output_sha256={
            stream:diagnostics.sha256(output / (tool + '.' + stream + '.txt')) for stream in ('stdout', 'stderr')})

    def analyze(self, name='output', run=None):
        with patch.object(diagnostics, 'checked_tools', return_value=self.root / 'upstream'), \
                patch.object(diagnostics, 'run_tool', side_effect=self.run_tool if run is None else run):
            return diagnostics.analyze(self.manifest_path, self.tools, self.root / name)

    def dispatch(self, skill, record, access=None):
        with patch.object(skill_broker, 'checked_tools', return_value=self.root / 'upstream'), \
                patch.object(diagnostics, 'checked_tools', return_value=self.root / 'upstream'), \
                patch.object(diagnostics, 'run_tool', side_effect=self.run_tool):
            return (self.access if access is None else access).dispatch(self.root,
                dict(kind='run_skill', skill=skill, evidence='profile-01'), self.root / record)

    def test_explicit_profile_only_accepts_unknown_shape_without_defaults(self):
        trace, config, shape = diagnostics.checked_manifest(self.manifest)
        self.assertEqual((trace, config), (self.trace, self.config))
        self.assertIsNone(shape)

    def test_profile_only_rejects_every_non_null_shape_and_extra_fields(self):
        for workload in ({}, 0, False, 'unknown', dict(phase='unknown'),
                         dict(phase='target-verify', batch_size=1, verify_rows=8, prefix_kv=118, shape_evidence='guess')):
            with self.subTest(workload=workload), self.assertRaises(ValueError):
                diagnostics.checked_manifest(dict(self.manifest, workload=workload))
        for changes in (dict(shape=[1, 8]), dict(command='shell'), dict(scope='author-final'), dict(protocol='unknown')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                diagnostics.checked_manifest(dict(self.manifest, **changes))

    def test_legacy_v1_still_requires_real_explicit_shape(self):
        with self.assertRaises(ValueError):
            diagnostics.checked_manifest(dict(self.manifest, protocol='stock-diagnostic-inputs-v1'))
        shape = dict(phase='target-verify', batch_size=1, verify_rows=8, prefix_kv=118, shape_evidence='synthetic fixture')
        self.assertEqual(diagnostics.checked_manifest(dict(self.manifest,
            protocol='stock-diagnostic-inputs-v1', workload=shape))[2], shape)

    def test_profile_only_analysis_runs_only_extract_and_profiler(self):
        result = self.analyze()
        self.assertEqual(self.calls, ['extract', 'profiler'])
        self.assertTrue(result['engineering_passed'])
        self.assertEqual(result['tools']['compute']['status'], 'unavailable')
        self.assertEqual(result['tools']['pipeline']['status'], 'unavailable')
        self.assertNotIn('output_sha256', result['tools']['compute'])
        self.assertFalse((self.root / 'output/compute.stdout.txt').exists())
        self.assertFalse(result['stage_attribution_validated'])
        self.assertIsNone(result['formal_ceiling'])
        self.assertFalse(result['controller_accepted'])
        self.assertFalse(result['ledger_eligible'])
        self.assertEqual(result['gpu_submissions'], 0)
        self.assertIsNone(result['input_identity']['workload'])

    def test_extract_or_profiler_failure_is_not_success(self):
        for failing in ('extract', 'profiler'):
            def run(root, tool, arguments, output):
                receipt = self.run_tool(root, tool, arguments, output)
                if tool == failing:
                    receipt['exit_code'] = 1
                return receipt
            with self.subTest(tool=failing):
                self.assertFalse(self.analyze('failed-' + failing, run=run)['engineering_passed'])

    def test_profile_only_still_rejects_wrong_kernel_counts_and_invalid_trace(self):
        def run(root, tool, arguments, output):
            receipt = self.run_tool(root, tool, arguments, output)
            if tool == 'extract':
                value = json.loads((output / 'extract.stdout.txt').read_text())
                value['count'] = 3
                diagnostics.write_json(output / 'extract.stdout.txt', value)
            return receipt
        with self.assertRaisesRegex(ValueError, 'count'):
            self.analyze(run=run)
        diagnostics.write_json(self.trace, {'traceEvents': [self.events[-1]]})
        self.manifest['trace'] = self.reference(self.trace)
        diagnostics.write_json(self.manifest_path, self.manifest)
        with self.assertRaisesRegex(ValueError, 'no CUDA kernel'):
            self.analyze('no-kernel')

    def test_profile_only_does_not_bypass_sha_or_symlink_checks(self):
        link = self.root / 'link.json'
        link.symlink_to(self.config)
        changed = dict(self.manifest, config=self.reference(link))
        with self.assertRaises(ValueError):
            diagnostics.checked_manifest(changed)
        self.trace.write_text('synthetic replacement')
        with self.assertRaises(ValueError):
            diagnostics.checked_manifest(self.manifest)

    def test_registered_profile_can_run_profiler_and_reuse_cache_without_compute_file(self):
        first = self.dispatch('profiler', 'first')
        second = self.dispatch('profiler', 'second')
        self.assertEqual(first['status'], 'completed')
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(self.calls, ['extract', 'profiler'])
        self.assertFalse(any((self.root / 'cache').glob('*/compute.stdout.txt')))

    def test_compute_and_pipeline_are_unavailable_without_estimates_or_fake_outputs(self):
        for skill in ('compute', 'pipeline'):
            with self.subTest(skill=skill):
                answer = self.dispatch(skill, skill)
                self.assertEqual(answer['status'], 'unavailable')
                self.assertTrue(answer['reason'])
                self.assertNotIn('estimate', answer)
                self.assertFalse(answer['independent_discovery'])
        self.assertEqual(self.calls, ['extract', 'profiler'])
        self.assertFalse(any((self.root / 'cache').glob('*/compute.stdout.txt')))

    def test_cached_kernel_statistics_are_recomputed_from_authorized_trace(self):
        self.dispatch('profiler', 'first')
        cached = next((self.root / 'cache').glob('*/result.json'))
        value = json.loads(cached.read_text())
        value['kernel_statistics']['0']['work_us'] = 999999999
        diagnostics.write_json(cached, value)
        with self.assertRaisesRegex(ValueError, 'kernel statistics'):
            self.dispatch('profiler', 'second')

    def test_only_real_executed_tool_outputs_are_rechecked(self):
        self.dispatch('profiler', 'first')
        cache = next((self.root / 'cache').glob('*/result.json')).parent
        for name in ('extract.stdout.txt', 'extract.stderr.txt', 'profiler.stdout.txt', 'profiler.stderr.txt'):
            path = cache / name
            original = path.read_bytes()
            path.write_text('synthetic tamper')
            with self.subTest(output=name), self.assertRaisesRegex(ValueError, 'cached tool output SHA'):
                self.dispatch('profiler', 'tampered-' + name)
            path.write_bytes(original)

    def test_missing_executed_receipt_cannot_be_relabelled_unavailable_in_cache(self):
        self.dispatch('profiler', 'first')
        path = next((self.root / 'cache').glob('*/result.json'))
        original = json.loads(path.read_text())
        for tool in ('extract', 'profiler'):
            changed = copy.deepcopy(original)
            changed['tools'][tool] = dict(status='unavailable', reason='synthetic tamper')
            diagnostics.write_json(path, changed)
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                self.dispatch('profiler', 'tampered-' + tool)
        diagnostics.write_json(path, original)

    def test_evidence_registration_is_trusted_map_only_not_role_paths(self):
        for action in (dict(kind='run_skill', skill='profiler', evidence=str(self.manifest_path)),
                       dict(kind='run_skill', skill='profiler', evidence='profile-01', path=str(self.manifest_path))):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.access.dispatch(self.root, action, self.root / 'untrusted')
        evidence = {}
        old = skill_broker.SkillAccess('direction', evidence, self.tools, self.root / 'cache')
        evidence['profile-01'] = self.manifest_path
        with self.assertRaises(ValueError):
            self.dispatch('profiler', 'not-registered', access=old)
        rebuilt = skill_broker.SkillAccess('direction', evidence, self.tools, self.root / 'cache')
        self.assertEqual(self.dispatch('profiler', 'registered', access=rebuilt)['status'], 'completed')

    def shape_events(self, events):
        if self.trace.suffix == '.gz':
            import gzip
            with gzip.open(self.trace, 'wt') as stream:
                json.dump(dict(traceEvents=self.events + events), stream)
        else:
            diagnostics.write_json(self.trace, dict(traceEvents=self.events + events))
        self.manifest['trace'] = self.reference(self.trace)
        diagnostics.write_json(self.manifest_path, self.manifest)

    def test_observed_cpu_dims_are_indexed_trace_facts_not_workload_certification(self):
        self.shape_events([
            dict(ph='X', cat='cpu_op', name='aten::mm',
                args={'Input Dims': [[8, 16], [16, 32]], 'Call stack': 'synthetic/file.py:12'}),
            dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[8, 16], [16, 32]]}),
            dict(ph='X', cat='kernel', name='verify_rows_999', pid=0, ts=20, dur=1,
                args={'Input Dims': [[999]], 'Call stack': 'not a CPU op'}),
            dict(ph='X', cat='user_annotation', name='target-verify', args={'Input Dims': [[777]]})])
        facts = diagnostics.observed_shape_facts(diagnostics.read_trace(self.trace), self.manifest['trace']['sha256'])
        self.assertEqual(facts['status'], 'observed')
        self.assertEqual(facts['trace_sha256'], self.manifest['trace']['sha256'])
        self.assertEqual(facts['source_fields'], ['args.Input Dims', 'args.Call stack'])
        self.assertEqual(facts['cpu_op_events'], 2)
        self.assertEqual(facts['events_with_input_dims'], 2)
        self.assertEqual(facts['events_with_stack'], 1)
        self.assertFalse(facts['cost_model_input_certified'])
        self.assertFalse(facts['stage_attribution_validated'])
        signature = facts['signatures'][0]
        self.assertEqual(signature['operator'], 'aten::mm')
        self.assertEqual(signature['input_dims'], [[8, 16], [16, 32]])
        self.assertEqual(signature['event_count'], 2)
        self.assertEqual(signature['first_event_indices'], [3, 4])
        self.assertEqual(signature['events_with_stack'], 1)
        self.assertNotIn('verify_rows', facts)
        self.assertNotIn('phase', signature)
        self.assertNotIn('kernel', signature)
        self.assertNotIn('synthetic/file.py', json.dumps(facts))

    def test_observed_shape_and_stack_are_unknown_without_exact_cpu_fields(self):
        events = [dict(ph='X', cat='kernel', args={'Input Dims': [[8]], 'Call stack': 'ignored'}),
            dict(ph='X', cat='cpu_op', name='aten::mm', args={'input_shapes': [[8]], 'stack': 'ignored'}),
            dict(ph='X', cat='cpu_op', name='aten::empty', args={'Input Dims': [], 'Call stack': ''}),
            dict(ph='B', cat='cpu_op', name='aten::mm', args={'Input Dims': [[9]]})]
        facts = diagnostics.observed_shape_facts(events, 'a' * 64)
        self.assertEqual(facts['status'], 'unknown')
        self.assertEqual(facts['stack_status'], 'unknown')
        self.assertEqual(facts['cpu_op_events'], 2)
        self.assertEqual(facts['events_with_stack'], 0)
        self.assertEqual(facts['signatures'], [])

    def test_observed_stack_presence_does_not_fabricate_input_dims(self):
        facts = diagnostics.observed_shape_facts([
            dict(ph='X', cat='cpu_op', name='aten::mm', args={'Call stack': ['synthetic frame']})], 'b' * 64)
        self.assertEqual(facts['status'], 'unknown')
        self.assertEqual(facts['stack_status'], 'observed')
        self.assertEqual(facts['events_with_stack'], 1)
        self.assertEqual(facts['signatures'], [])

    def test_observed_shape_signatures_and_event_indices_are_bounded_with_total_counts(self):
        events = [dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[signature, 4]]})
                  for signature in range(20) for occurrence in range(4)]
        facts = diagnostics.observed_shape_facts(events, 'c' * 64)
        self.assertEqual(facts['cpu_op_events'], 80)
        self.assertEqual(facts['events_with_input_dims'], 80)
        self.assertEqual(len(facts['signatures']), 16)
        self.assertEqual(facts['unrepresented_shape_events'], 16)
        self.assertTrue(facts['truncated'])
        for signature in facts['signatures']:
            self.assertEqual(signature['event_count'], 4)
            self.assertEqual(len(signature['first_event_indices']), 3)
            self.assertTrue(signature['event_indices_truncated'])

    def test_observed_shape_values_and_names_cannot_make_unbounded_payloads(self):
        invalid = [['guessed'], [[True]], [[-1]], [[1 << 100]], [[1] * 300], [[[[[[1]]]]]]]
        events = [dict(ph='X', cat='cpu_op', name='aten::bad', args={'Input Dims': value}) for value in invalid]
        events.append(dict(ph='X', cat='cpu_op', name='x' * 10000, args={'Input Dims': [[0, 8], []]}))
        facts = diagnostics.observed_shape_facts(events, 'd' * 64)
        self.assertEqual(facts['rejected_input_dims_events'], len(invalid))
        self.assertEqual(len(facts['signatures']), 1)
        self.assertLessEqual(len(facts['signatures'][0]['operator']), 160)
        self.assertTrue(facts['truncated'])
        self.assertLess(len(json.dumps(facts)), 6000)

    def test_profile_only_result_and_cached_profiler_expose_same_source_bound_facts(self):
        import gzip
        events = self.events + [dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[8, 16]]})]
        self.trace = self.root / 'trace.json.gz'
        with gzip.open(self.trace, 'wt') as stream:
            json.dump(dict(traceEvents=events), stream)
        self.manifest['trace'] = self.reference(self.trace)
        diagnostics.write_json(self.manifest_path, self.manifest)
        result = self.analyze()
        facts = result['observed_shape_facts']
        first = self.dispatch('profiler', 'shape-first')
        second = self.dispatch('profiler', 'shape-cached')
        self.assertEqual(first['observed_shape_facts'], facts)
        self.assertEqual(second['observed_shape_facts'], facts)
        self.assertTrue(second['cached'])
        self.assertIsNone(result['input_identity']['workload'])
        self.assertEqual(result['tools']['compute']['status'], 'unavailable')
        self.assertEqual(result['tools']['pipeline']['status'], 'unavailable')
        self.assertFalse((self.root / 'output/compute.stdout.txt').exists())
        self.shape_events([dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[32, 64]]})])
        changed = self.dispatch('profiler', 'shape-changed')
        self.assertFalse(changed['cached'])
        self.assertNotEqual(changed['observed_shape_facts']['trace_sha256'], facts['trace_sha256'])
        self.assertEqual(changed['observed_shape_facts']['signatures'][0]['input_dims'], [[32, 64]])

    def test_observed_shape_cache_tamper_or_omission_is_rejected(self):
        self.shape_events([dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[8]]})])
        self.dispatch('profiler', 'shape-original')
        path = next((self.root / 'cache').glob('*/result.json'))
        original = json.loads(path.read_text())
        for replacement in ('omitted', 'dims', 'sha'):
            changed = copy.deepcopy(original)
            if replacement == 'omitted':
                del changed['observed_shape_facts']
            elif replacement == 'dims':
                changed['observed_shape_facts']['signatures'][0]['input_dims'] = [[999]]
            else:
                changed['observed_shape_facts']['trace_sha256'] = '0' * 64
            diagnostics.write_json(path, changed)
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, 'observed shape'):
                self.dispatch('profiler', 'shape-tampered-' + replacement)

    def test_legacy_v1_does_not_add_observed_shape_facts_or_change_compute(self):
        self.manifest.update(protocol='stock-diagnostic-inputs-v1', workload=dict(
            phase='target-verify', batch_size=1, verify_rows=8, prefix_kv=118, shape_evidence='CPU fixture'))
        diagnostics.write_json(self.manifest_path, self.manifest)
        def run(root, tool, arguments, output):
            if tool != 'compute':
                return self.run_tool(root, tool, arguments, output)
            self.calls.append(tool)
            diagnostics.write_json(output / 'compute.stdout.txt', {})
            (output / 'compute.stderr.txt').write_text('')
            return dict(exit_code=0, timed_out=False)
        result = self.analyze(run=run)
        self.assertNotIn('observed_shape_facts', result)
        self.assertEqual(self.calls, ['extract', 'profiler', 'compute'])
        self.assertEqual(result['input_identity']['workload'], self.manifest['workload'])

    def test_shape_pages_expose_late_mm_signatures_without_duplicates_or_inference(self):
        events = [dict(ph='X', cat='cpu_op', name='aten::empty' if index < 16 else 'aten::mm',
            args={'Input Dims': [[index, 16]]}) for index in range(35)]
        events.append(copy.deepcopy(events[17]))
        pages = [diagnostics.observed_shape_facts(events, 'a' * 64, offset=offset) for offset in (0, 16, 32)]
        self.assertEqual([page['offset'] for page in pages], [0, 16, 32])
        self.assertEqual([page['next_offset'] for page in pages], [16, 32, None])
        self.assertEqual([len(page['signatures']) for page in pages], [16, 16, 3])
        signatures = [item for page in pages for item in page['signatures']]
        self.assertEqual([item['input_dims'][0][0] for item in signatures], list(range(35)))
        self.assertEqual(signatures[17]['event_count'], 2)
        self.assertEqual(signatures[17]['first_event_indices'], [17, 35])
        self.assertEqual(signatures[17]['operator'], 'aten::mm')
        for page in pages:
            self.assertEqual(page['total_signatures'], 35)
            self.assertEqual(page['events_with_input_dims'], 36)
            self.assertEqual(page['trace_sha256'], 'a' * 64)
            self.assertFalse(page['cost_model_input_certified'])
            self.assertFalse(page['stage_attribution_validated'])
        self.assertEqual(diagnostics.observed_shape_facts(events, 'a' * 64), pages[0])

    def test_shape_page_offsets_are_strict_and_end_page_is_empty(self):
        events = [dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[8]]})]
        for offset in (-1, True, False, 1.0, '0', None, 2):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                diagnostics.observed_shape_facts(events, 'a' * 64, offset=offset)
        end = diagnostics.observed_shape_facts(events, 'a' * 64, offset=1)
        self.assertEqual(end['signatures'], [])
        self.assertIsNone(end['next_offset'])
        self.assertEqual(end['total_signatures'], 1)
        empty = diagnostics.observed_shape_facts([], 'a' * 64)
        self.assertEqual(empty['status'], 'unknown')
        self.assertEqual(empty['total_signatures'], 0)
        self.assertIsNone(empty['next_offset'])

    def test_shape_read_is_authorized_read_only_without_tools_cache_or_compute(self):
        self.shape_events([dict(ph='X', cat='cpu_op', name='aten::mm', args={'Input Dims': [[index, 16]]})
                           for index in range(20)])
        before = {path:diagnostics.sha256(path) for path in self.root.iterdir() if path.is_file()}
        with patch.object(skill_broker, 'analyze') as analyze, patch.object(skill_broker, 'run_tool') as execute:
            answer = self.access.dispatch(self.root, dict(kind='read_profile_shapes', evidence='profile-01', offset=16),
                self.root / 'shape-page')
        self.assertEqual(answer['status'], 'completed')
        self.assertEqual(answer['kind'], 'read_profile_shapes')
        self.assertEqual(answer['role'], 'direction')
        self.assertEqual(answer['evidence'], 'profile-01')
        self.assertEqual(answer['observed_shape_facts']['offset'], 16)
        self.assertEqual(len(answer['observed_shape_facts']['signatures']), 4)
        self.assertEqual(answer['observed_shape_facts']['trace_sha256'], self.manifest['trace']['sha256'])
        self.assertFalse(answer['independent_discovery'])
        self.assertEqual(answer['gpu_submissions'], 0)
        self.assertEqual(json.loads((self.root / 'shape-page/result.json').read_text()), answer)
        self.assertEqual(before, {path:diagnostics.sha256(path) for path in self.root.iterdir() if path.is_file()})
        self.assertFalse((self.root / 'cache').exists())
        analyze.assert_not_called()
        execute.assert_not_called()

    def test_shape_read_rejects_extra_fields_unregistered_paths_bad_offsets_and_other_role_ids(self):
        base = dict(kind='read_profile_shapes', evidence='profile-01', offset=0)
        actions = [dict(base, path=str(self.trace)), dict(base, limit=16), dict(base, skill='compute'),
                   dict(base, evidence=str(self.manifest_path)), dict(base, evidence='other-role-profile'),
                   dict(base, offset=True), dict(base, offset=-1), dict(base, offset=1),
                   {key:value for key, value in base.items() if key != 'offset'}]
        for number, action in enumerate(actions):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.access.dispatch(self.root, action, self.root / f'invalid-page-{number}')
        other = skill_broker.SkillAccess('kernel', {}, self.tools, self.root / 'cache')
        with self.assertRaises(ValueError):
            other.dispatch(self.root, base, self.root / 'other-role-page')

    def test_shape_read_preserves_sha_checks_and_legacy_v1_boundary(self):
        action = dict(kind='read_profile_shapes', evidence='profile-01', offset=0)
        self.trace.write_text('changed')
        with self.assertRaises(ValueError):
            self.access.dispatch(self.root, action, self.root / 'tampered-page')
        self.shape_events([])
        self.manifest.update(protocol='stock-diagnostic-inputs-v1', workload=dict(
            phase='target-verify', batch_size=1, verify_rows=8, prefix_kv=118, shape_evidence='CPU fixture'))
        diagnostics.write_json(self.manifest_path, self.manifest)
        with self.assertRaises(ValueError):
            self.access.dispatch(self.root, action, self.root / 'legacy-page')

    def test_list_skills_advertises_exact_shape_read_schema_and_cpu_cost(self):
        catalog = self.access.dispatch(self.root, dict(kind='list_skills'), self.root / 'unused')
        advertised = catalog['actions']['read_profile_shapes']
        self.assertEqual(advertised['schema'], dict(kind='read_profile_shapes', evidence='<authorized evidence ID>', offset=0))
        self.assertEqual(advertised['cpu_runs_per_call'], 1)
        self.assertEqual(advertised['page_size'], 16)
        self.assertFalse(advertised['additional_fields_allowed'])

    def test_each_shape_page_and_repeated_page_consumes_one_cpu_budget_slot(self):
        from harness.research_protocol import ResearchBroker
        broker = ResearchBroker(self.root, self.root / 'paging-records', 'thread', 'turn',
            max_actions=4, max_runs=2, dispatcher=self.access.dispatch)
        def call(number, **extra):
            return broker.handle(dict(threadId='thread', turnId='turn', tool='research', namespace=None,
                callId=str(number), arguments=dict(action=dict(kind='read_profile_shapes', evidence='profile-01', offset=0, **extra))))
        self.assertTrue(call(1)['success'])
        self.assertEqual(broker.runs, 1)
        self.assertTrue(call(2)['success'])
        self.assertEqual(broker.runs, 2)
        exhausted = call(3)
        self.assertFalse(exhausted['success'])
        self.assertIn('CPU run budget exhausted', exhausted['contentItems'][0]['text'])
        self.assertEqual(broker.runs, 2)
        self.assertFalse((self.root / 'paging-records/action-003/execution').exists())

    def test_rejected_shape_action_cannot_bypass_cpu_attempt_accounting(self):
        from harness.research_protocol import ResearchBroker
        broker = ResearchBroker(self.root, self.root / 'rejected-paging', 'thread', 'turn',
            max_actions=2, max_runs=1, dispatcher=self.access.dispatch)
        request = dict(threadId='thread', turnId='turn', tool='research', namespace=None, callId='bad',
            arguments=dict(action=dict(kind='read_profile_shapes', evidence='profile-01', offset=0, path=str(self.trace))))
        self.assertFalse(broker.handle(request)['success'])
        self.assertEqual(broker.runs, 1)


if __name__ == '__main__':
    unittest.main()
