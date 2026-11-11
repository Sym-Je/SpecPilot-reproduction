import copy
import json
from pathlib import Path
import tempfile
import unittest

from harness.profile_links import observed_kernel_links
from harness.skill_broker import SkillAccess
from harness.skill_diagnostics import sha256


def fixture():
    return [
        dict(cat='cpu_op', ph='X', name='aten::mm', pid=3, tid=4,
             args={'External id': 17, 'Input Dims': [[8, 16], [16, 32]],
                   'Input type': ['BFloat16', 'BFloat16'], 'Concrete Inputs': ['SECRET'],
                   'Call stack': '/private/SECRET'}),
        dict(cat='cuda_runtime', ph='X', name='cudaLaunchKernel', pid=3, tid=4,
             args={'correlation': 22, 'External id': 17}),
        dict(cat='kernel', ph='X', name='gemm', pid=0, tid=8, ts=10, dur=2,
             args={'correlation': 22, 'External id': 17, 'stream': 8}),
    ]


class ProfileLinkTests(unittest.TestCase):
    def facts(self, events=None, offset=0):
        return observed_kernel_links(fixture() if events is None else events, 'a'*64, 'gemm', offset)

    def test_unique_ids_preserve_observations_not_certified_ownership(self):
        result=self.facts()
        self.assertEqual(result['kernel_count'], 1)
        self.assertEqual(result['kernel_work_us'], 2)
        call=result['calls'][0]
        self.assertEqual(call['kernel_event_index'], 2)
        self.assertEqual(call['runtime_event_indices'], [1])
        self.assertEqual(call['cpu_event_indices'], [0])
        self.assertEqual(call['cpu_operator']['input_dims'], [[8,16],[16,32]])
        self.assertFalse(result['module_attribution_validated'])
        self.assertIsNone(result['exposed_time_us'])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_graph_replay_never_assigns_launch_cpu_shape_to_graph_node(self):
        events=fixture(); events[2]['args']['graph id']=9
        call=self.facts(events)['calls'][0]
        self.assertTrue(call['graph_replay_or_node'])
        self.assertIsNone(call['cpu_operator'])
        self.assertEqual(call['link_status'], 'graph_launch_only')
        events[2]['args'].pop('graph id')
        events[1]['name']='cudaGraphLaunch'
        self.assertEqual(self.facts(events)['calls'][0]['link_status'], 'graph_launch_only')

    def test_duplicate_correlations_missing_ids_and_cpu_ambiguity_are_explicit(self):
        events=fixture(); events.append(copy.deepcopy(events[1]))
        self.assertEqual(self.facts(events)['calls'][0]['link_status'], 'ambiguous_runtime')
        events=fixture(); events[2]['args'].pop('correlation')
        self.assertEqual(self.facts(events)['calls'][0]['link_status'], 'missing_runtime')
        events=fixture(); events.append(copy.deepcopy(events[0]))
        self.assertEqual(self.facts(events)['calls'][0]['link_status'], 'ambiguous_cpu')

    def test_conflicting_external_ids_do_not_silently_link(self):
        events=fixture(); events[2]['args']['External id']=18
        call=self.facts(events)['calls'][0]
        self.assertEqual(call['link_status'], 'conflicting_external_ids')
        self.assertIsNone(call['cpu_operator'])

    def test_non_aten_duplicate_is_counted_but_never_exposed(self):
        events=fixture(); events.append(dict(events[0],name='PRIVATE_CUSTOM_NAME'))
        call=self.facts(events)['calls'][0]
        self.assertEqual(call['link_status'],'ambiguous_cpu')
        self.assertEqual(call['cpu_matches'],2)
        events=fixture(); events[0]['name']='PRIVATE_CUSTOM_NAME'
        call=self.facts(events)['calls'][0]
        self.assertEqual(call['link_status'],'unsupported_cpu_operator')
        self.assertNotIn('PRIVATE_CUSTOM_NAME',json.dumps(call))

    def test_bounded_pagination_includes_event_indices_and_empty_terminal_page(self):
        events=fixture()+[dict(fixture()[2], ts=20+index) for index in range(9)]
        first=self.facts(events)
        self.assertEqual(len(first['calls']), 8)
        self.assertEqual(first['next_offset'], 8)
        self.assertEqual(len(self.facts(events,8)['calls']), 2)
        self.assertEqual(self.facts(events,10)['calls'], [])
        with self.assertRaises(ValueError): self.facts(events,11)
        with self.assertRaises(ValueError): self.facts(events,True)

    def test_unrecorded_shapes_and_unknown_types_remain_unknown(self):
        events=fixture(); events[0]['args']['Input Dims']='SECRET'
        events[0]['args']['Input type']=['SECRET']
        operator=self.facts(events)['calls'][0]['cpu_operator']
        self.assertIsNone(operator['input_dims'])
        self.assertIsNone(operator['input_types'])
        self.assertNotIn('SECRET',json.dumps(operator))

    def test_nonfinite_timing_and_invalid_selector_rejected(self):
        events=fixture(); events[2]['dur']=float('nan')
        with self.assertRaises(ValueError): self.facts(events)
        with self.assertRaises(ValueError): observed_kernel_links(fixture(),'a'*64,'',0)

    def test_broker_authorization_hash_identity_and_no_host_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); trace=root/'trace.json'; config=root/'config.json'
            trace.write_text(json.dumps(dict(traceEvents=fixture())))
            config.write_text('{}')
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(protocol='stock-profile-only-inputs-v1',scope='authorized-stock',
                trace=dict(path=str(trace),sha256=sha256(trace)),config=dict(path=str(config),sha256=sha256(config)),workload=None)))
            access=SkillAccess('Master',{'stock':manifest},root/'unused',root/'cache')
            action=dict(kind='read_kernel_links',evidence='stock',kernel='gemm',offset=0)
            answer=access.dispatch(root,action,root/'result')
            self.assertEqual(answer['observations']['kernel_count'],1)
            for changed in (dict(action,evidence='other'),dict(action,path=str(trace))):
                with self.assertRaises(ValueError): access.dispatch(root,changed,root/'rejected')
            trace.write_text('[]')
            with self.assertRaises(ValueError): access.dispatch(root,action,root/'tampered')

    def test_link_reads_consume_cpu_quota_and_help_advertises_exact_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            access=SkillAccess('Master',{},root/'unused',root/'cache')
            help_result=access.dispatch(root,dict(kind='help'),root/'help')
            self.assertEqual(help_result['actions']['read_kernel_links'],dict(kind='read_kernel_links',
                evidence='<authorized evidence ID>',kernel='<exact kernel name>',offset=0))
            broker=access.factory()(root,root/'records','thread','turn',max_runs=0)
            result=broker.handle(dict(threadId='thread',turnId='turn',tool='research',namespace=None,
                callId='one',arguments=dict(action=dict(kind='read_kernel_links',evidence='stock',kernel='gemm',offset=0))))
            self.assertFalse(result['success'])
            self.assertIn('CPU run budget exhausted',result['contentItems'][0]['text'])
            self.assertEqual(broker.runs,0)


if __name__=='__main__':
    unittest.main()
