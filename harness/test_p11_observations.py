import math
import unittest


class ObservationTests(unittest.TestCase):
    def metadata(self):
        return dict(completion_tokens=64,spec_verify_ct=9,spec_accepted_drafts=57,
            spec_num_correct_drafts=57,spec_proposed_drafts=63,spec_num_proposed_drafts=63,
            spec_accept_histogram=[0,0,0,0,1,1,1,6],spec_correct_drafts_histogram=[0,0,0,0,1,1,1,6],
            spec_accept_rate=57/63,spec_accept_length=64/9)

    def test_intervals_use_union_not_kernel_sum(self):
        from costmodel.observations import interval_union
        self.assertEqual(interval_union([(0,10),(5,15),(20,25)]),20)
        self.assertEqual(interval_union([]),0)

    def test_invalid_intervals_are_rejected(self):
        from costmodel.observations import interval_union
        for intervals in [[(2,1)],[(0,math.nan)],[(0,math.inf)]]:
            with self.subTest(intervals=intervals), self.assertRaises(ValueError):
                interval_union(intervals)

    def test_multiple_devices_are_not_added_as_wall_time(self):
        from costmodel.observations import trace_observation
        events=[dict(ph='X',cat='kernel',name='unknown',ts=0,dur=10,args=dict(device=0)),
                dict(ph='X',cat='kernel',name='unknown',ts=0,dur=10,args=dict(device=1))]
        result=trace_observation(events)
        self.assertEqual(result['kernel_sum_us'],20)
        self.assertIsNone(result['single_device_busy_us'])
        self.assertEqual(result['gpu_busy_us_by_device'],{'0':10,'1':10})

    def test_unknown_kernel_name_never_implies_a_stage(self):
        from costmodel.observations import trace_observation
        result=trace_observation([dict(ph='X',cat='kernel',name='verify_fast',ts=0,dur=10,args=dict(device=0))])
        self.assertEqual(result['stages']['unattributed_kernel_us'],10)
        self.assertEqual(result['nominal_matmul_floors']['eligible_ops'],0)

    def test_histogram_correct_drafts_differ_from_emitted_progress(self):
        from costmodel.observations import counter_observation
        result=counter_observation(self.metadata())
        self.assertTrue(result['algebra_consistent'])
        self.assertAlmostEqual(result['reported_correct_drafts_per_verify'],57/9)
        self.assertAlmostEqual(result['emitted_tokens_per_reported_verify'],64/9)
        self.assertEqual(result['conditional_tail_clip_tokens'],2)
        self.assertFalse(result['per_step_token_lattice_available'])

    def test_missing_and_inconsistent_counters_remain_unknown(self):
        from costmodel.observations import counter_observation
        for metadata in [{},dict(self.metadata(),spec_verify_ct=10),dict(self.metadata(),spec_verify_ct=True)]:
            result=counter_observation(metadata)
            self.assertFalse(result['algebra_consistent'])
            self.assertIsNone(result['reported_correct_drafts_per_verify'])

    def test_missing_evidence_never_becomes_one_or_a_ceiling(self):
        from costmodel.observations import factor_coverage
        result=factor_coverage()
        self.assertFalse(result['complete'])
        self.assertIsNone(result['ceiling'])
        self.assertTrue(all(value['value'] is None for value in result['factors'].values()))

    def test_bf16_mm_roofline_is_a_subset_scenario_not_measured_dram(self):
        from costmodel.observations import matmul_scenario
        result=matmul_scenario(dict(name='aten::mm',args={'Input Dims':[[2,3],[3,4]],
            'Input type':['c10::BFloat16','c10::BFloat16']}))
        self.assertEqual(result['flops'],48)
        self.assertEqual(result['cold_tensor_io_bytes'],52)
        self.assertFalse(result['measured_dram_bytes'])
        self.assertIsNone(matmul_scenario(dict(name='mystery_mm_kernel',args={})))

    def test_negative_or_nonfinite_kernel_time_is_rejected(self):
        from costmodel.observations import trace_observation
        for duration in (-1,math.nan,math.inf):
            with self.assertRaises(ValueError):
                trace_observation([dict(ph='X',cat='kernel',name='anything',ts=0,dur=duration,args=dict(device=0))])


if __name__=='__main__':
    unittest.main()
