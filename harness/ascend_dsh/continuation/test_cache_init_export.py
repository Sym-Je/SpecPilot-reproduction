import copy
import unittest
from cache_init_export import analyze_snapshots


class ExportTests(unittest.TestCase):
    def records(self):
        plan={'groups':[{'group_index':0,'layers':['model.layers.0.attn']}],
              'config':{'num_blocks':100},'truncated':False}
        rows=[{'stage':'worker_initialized','pid':100+i,'ordinal':0,
            'data':dict(copy.deepcopy(plan),distributed_rank=i,distributed_world_size=8,
                effective_worker_config={'cache':{'enable_prefix_caching':False}})} for i in range(8)]
        rows+=[{'stage':'core_initialized','pid':1,'ordinal':0,'data':{'plan':copy.deepcopy(plan),
                  'effective_core_config':{'cache':{'enable_prefix_caching':False}}}},
               {'stage':'manager_initialized','pid':1,'ordinal':1,
                'data':{'enable_caching':False,'group_count':1,'truncated':False}}]
        return rows

    def test_complete_disabled_metadata_never_certifies_enabled_support(self):
        report=analyze_snapshots(self.records())
        self.assertTrue(report['structural_capture_complete'])
        self.assertFalse(report['enabled_state_restoration_validated'])
        self.assertEqual(report['rank_count'],8)
        self.assertEqual(report['runner_submitted_generation_requests'],0)

    def test_missing_rank_overflow_or_enabled_flag_invalidates_phase1(self):
        for kind in ('missing','overflow','enabled'):
            rows=self.records()
            if kind=='missing':rows.pop(0)
            elif kind=='overflow':rows.append({'stage':'overflow','data':{'truncated':True}})
            else:rows[0]['data']['effective_worker_config']['cache']['enable_prefix_caching']=True
            with self.subTest(kind=kind):self.assertFalse(analyze_snapshots(rows)['structural_capture_complete'])

    def test_unexpected_stage_or_nonfinal_plan_cannot_pass(self):
        rows=self.records();rows.append({'stage':'unexpected','data':{}})
        self.assertFalse(analyze_snapshots(rows)['structural_capture_complete'])
        rows=self.records();rows[8]['data']['plan']['config']['num_blocks']=99
        self.assertFalse(analyze_snapshots(rows)['structural_capture_complete'])


if __name__=='__main__':unittest.main()
