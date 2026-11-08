import unittest


class TraceStageTests(unittest.TestCase):
    def test_explicit_dynamic_stage_annotations_attribute_correlated_kernels(self):
        from exp.diagnosis_trace import stage_summary
        events=[dict(ph='X',cat='user_annotation',name='step[DRAFT bs=1 g_sq=32]',ts=0,dur=100,pid=1,tid=2),
                dict(ph='X',cat='cuda_runtime',name='cudaLaunchKernel',ts=5,dur=1,pid=1,tid=2,args=dict(correlation=7)),
                dict(ph='X',cat='kernel',name='arbitrary',ts=10,dur=30,args=dict(correlation=7))]
        result=stage_summary(events)
        self.assertEqual(result['kernel_us']['DRAFT'],30)
        self.assertEqual(result['kernel_count']['DRAFT'],1)
        self.assertEqual(result['unattributed_kernel_us'],0)

    def test_overlapping_different_stages_are_not_guessed(self):
        from exp.diagnosis_trace import stage_summary
        events=[dict(ph='X',cat='user_annotation',name='step[DRAFT bs=1]',ts=0,dur=100,pid=1,tid=2),
                dict(ph='X',cat='user_annotation',name='step[VERIFY bs=1]',ts=1,dur=90,pid=1,tid=2),
                dict(ph='X',cat='cuda_driver',name='cuLaunchKernel',ts=5,dur=1,pid=1,tid=2,args=dict(correlation=7)),
                dict(ph='X',cat='kernel',name='draft_kernel',ts=10,dur=30,args=dict(correlation=7))]
        result=stage_summary(events)
        self.assertEqual(result['unattributed_kernel_us'],30)
        self.assertEqual(result['ambiguous_launches'],1)

    def test_unknown_extend_variant_and_missing_correlation_remain_unknown(self):
        from exp.diagnosis_trace import stage_summary
        events=[dict(ph='X',cat='user_annotation',name='step[DRAFT_EXTEND bs=1]',ts=0,dur=100,pid=1,tid=2),
                dict(ph='X',cat='kernel',name='verify_kernel',ts=10,dur=30,args={})]
        self.assertEqual(stage_summary(events)['unattributed_kernel_us'],30)

    def test_nested_same_stage_does_not_double_count_kernels(self):
        from exp.diagnosis_trace import stage_summary
        events=[dict(ph='X',cat='user_annotation',name='step[VERIFY bs=1]',ts=0,dur=100,pid=1,tid=2),
                dict(ph='X',cat='user_annotation',name='step[VERIFY bs=1]',ts=1,dur=90,pid=1,tid=2),
                dict(ph='X',cat='cuda_runtime',name='cudaLaunchKernel',ts=5,dur=1,pid=1,tid=2,args=dict(correlation=7)),
                dict(ph='X',cat='kernel',name='arbitrary',ts=10,dur=30,args=dict(correlation=7))]
        result=stage_summary(events)
        self.assertEqual(result['kernel_us']['VERIFY'],30)
        self.assertEqual(result['kernel_total_us'],30)


if __name__=='__main__': unittest.main()
