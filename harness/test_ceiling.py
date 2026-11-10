import copy
import itertools
import math
from pathlib import Path
import tempfile
import unittest


class CeilingTests(unittest.TestCase):
    def lattice(self):
        return dict(candidate_ids=[[10,11],[20,21],[30,31]],
                    scores=[[[2.,1.],[2.,1.]],[[0.,2.],[3.,0.]],[[2.,0.],[0.,3.]]])

    def test_best_first_matches_exhaustive(self):
        from harness.ceiling_replay import best_first, log_probabilities
        lattice=self.lattice()
        probabilities=log_probabilities(lattice['candidate_ids'],lattice['scores'])
        paths=[]
        for depth in range(1,4):
            for path in itertools.product(range(2),repeat=depth):
                score=sum(probabilities[index][path[index-1] if index else 0][child]
                          for index,child in enumerate(path))
                paths.append((score,path))
        expected=[path for score,path in sorted(paths,key=lambda row:(-row[0],row[1]))]
        for budget in range(1,16):
            actual=best_first(lattice['candidate_ids'],lattice['scores'],budget)
            self.assertEqual(actual,expected[:budget-1])
            self.assertTrue(all(path[:-1] in actual for path in actual if len(path)>1))

    def test_replay_bounds_and_greedy(self):
        from harness.ceiling_replay import replay_lattice
        lattice=self.lattice()
        result=replay_lattice(**lattice,target=[10,20,31,99],chain=[10,21,31],budgets=[1,2,4,8,16])
        self.assertEqual(result['stock_tau'],2)
        self.assertEqual(result['oracle_tau'],4)
        self.assertEqual(result['best_first_tau']['1'],1)
        self.assertEqual(result['best_first_tau']['16'],4)
        self.assertTrue(all(1<=value<=4 for value in result['best_first_tau'].values()))
        with self.assertRaises(ValueError):
            replay_lattice(**lattice,target=[10,20],chain=[10,21,31],budgets=[8])
        with self.assertRaises(ValueError):
            replay_lattice(**lattice,target=[10,20,31,99],chain=[11,21,31],budgets=[8])

    def test_lattice_faults(self):
        from harness.ceiling_replay import best_first
        original=self.lattice()
        for kind in ('duplicate','nan','shape','positive_infinity'):
            lattice=copy.deepcopy(original)
            if kind=='duplicate':
                lattice['candidate_ids'][0][1]=10
            elif kind=='shape':
                lattice['scores'][1].pop()
            else:
                lattice['scores'][1][0][0]=math.nan if kind=='nan' else math.inf
            with self.assertRaises(ValueError):
                best_first(**lattice,budget=8)

    def test_unknown_factors_stay_unknown(self):
        from costmodel.ceiling import coverage
        result=coverage(conditional_replay=dict(stock_tau=4,best_tau=6),kernel_coverage=.8)
        self.assertFalse(result['complete'])
        self.assertIsNone(result['ceiling'])
        self.assertTrue(all(value['value'] is None for value in result['factors'].values()))

    def test_disabled_runtime_does_not_touch_tensors(self):
        from unittest.mock import patch
        from harness.ceiling_runtime import observe_lattice
        with patch.dict('os.environ',{},clear=True):
            observe_lattice(None,None,None,None,None,None,None,None,None)

    def test_build_is_insertion_only_and_default_off(self):
        from harness.ceiling_build import instrument_worker
        stock=Path('/gpfs/users/jixinpeng/specpilot_data/work/engines/h100_c1_qwen38-27b_dflash2-stock')
        if not stock.exists():
            self.skipTest('authorized H100 stock tree unavailable')
        worker=(stock/'python/sglang/srt/speculative/dflash_worker_v2.py').read_text()
        modified=instrument_worker(worker)
        self.assertIn('SPECPILOT_CEILING_TRACE_DIR',modified)
        self.assertIn('observe_lattice',modified)
        compile(modified,'observer','exec')
        with self.assertRaises(ValueError):
            instrument_worker(modified)

    def test_bound_real_shape_stream_and_faults(self):
        from harness.ceiling_replay import replay_events
        from harness.test_p12_step_replay import StepReplayTests
        initial,verify,final=StepReplayTests().fixture()
        initial.update(tree_sha='fixture',output_ids=[1],max_new_tokens=17,eos_ids=[])
        events=[initial]
        for step in range(2):
            anchor=1+step*8
            worker=dict(verify,tree_sha='fixture',sequence=1+step*3,
                candidates=list(range(anchor,anchor+8)),target_pred=list(range(anchor+1,anchor+9)),
                accepted=7,bonus=anchor+8,commit_len=8,committed_ids=list(range(anchor+1,anchor+9)))
            lattice=dict(worker,kind='lattice',sequence=worker['sequence']+1,
                candidate_ids=[[anchor+position+1+index*100 for index in range(16)] for position in range(7)],
                scores=[[[1.]+[0.]*15 for predecessor in range(16)] for position in range(7)])
            commit=dict(initial,sequence=worker['sequence']+2,phase='decode',output_ids=list(range(1,anchor+9)),
                verify_ct=step+1,correct_drafts=(step+1)*7,histogram=[0]*7+[step+1])
            if step==1:
                commit.update(finished_len=17,finish_reason=dict(type='length',length=17))
            events.extend([worker,lattice,commit])
        result=replay_events(events,list(range(1,18)))
        self.assertEqual(result['eligible_steps'],2)
        self.assertEqual(result['stock_tau'],8.)
        self.assertEqual(result['oracle_tau'],8.)
        for kind in ('missing','score','candidate','accepted','identity','output'):
            altered=copy.deepcopy(events)
            expected=list(range(1,18))
            if kind=='missing':
                del altered[2]
            elif kind=='score':
                altered[2]['scores'][0][0][0]=math.nan
            elif kind=='candidate':
                altered[2]['candidate_ids'][0][0]=altered[2]['candidate_ids'][0][1]
            elif kind=='accepted':
                altered[1]['accepted']=6
            elif kind=='identity':
                altered[2]['rid']='other'
            else:
                expected[-1]=999
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                replay_events(altered,expected)

    def test_prepare_never_submits_or_initializes_resources(self):
        from unittest.mock import patch
        from exp import ceiling_resource
        with tempfile.TemporaryDirectory() as temporary:
            with patch('sys.argv',['ceiling_resource','prepare','--directory',temporary,'--inputs','unused']),\
                    patch.object(ceiling_resource,'prepare') as prepare,\
                    patch.object(ceiling_resource,'execute') as execute,\
                    patch.object(ceiling_resource,'Budget') as budget:
                ceiling_resource.main()
            prepare.assert_called_once()
            execute.assert_not_called()
            budget.assert_not_called()

    def test_profile_classification_is_not_floor_coverage(self):
        from costmodel.ceiling import profile_report
        events=[dict(ph='X',cat='kernel',ts=0.,dur=10.,name='cublas_gemm',args=dict(device=0)),
                dict(ph='X',cat='kernel',ts=5.,dur=10.,name='unknown_fused',args=dict(device=0))]
        result=profile_report(events)
        self.assertFalse(result['full_floor_available'])
        self.assertEqual(result['observation']['single_device_busy_us'],15.)
        self.assertEqual(result['observation']['kernel_sum_us'],20.)
        self.assertEqual(set(result['classes']),{'dense_linear','other_unknown'})
        self.assertTrue(all(row['floor_us'] is None for row in result['classes'].values()))

    def test_observer_identity_uses_its_frozen_tree_without_weakening_check(self):
        from exp.ceiling_run import arm_spec
        from harness.candidate import check_identity,expected_arguments
        spec=dict(target='/target',draft='/draft',stock_tree_sha='stock-tree')
        arms=[dict(name='stock',tree_sha='stock-tree'),dict(name='observer',tree_sha='observer-tree')]
        observer=arm_spec(spec,arms,'observer')
        check_identity(dict(tree_sha='observer-tree',server_args=expected_arguments(spec,8)),observer,8)
        self.assertEqual(spec['stock_tree_sha'],'stock-tree')
        with self.assertRaises(ValueError):
            check_identity(dict(tree_sha='stock-tree',server_args=expected_arguments(spec,8)),observer,8)


if __name__=='__main__':
    unittest.main()
