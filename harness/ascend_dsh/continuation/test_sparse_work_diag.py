import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace,ModuleType
import unittest
import json
from unittest.mock import patch
import sparse_work_diag as diag
from sparse_work_export import export_observations


class FakeArray:
    def __init__(self,values,device='cpu'):
        self.values=values;self.device=SimpleNamespace(type=device);self.shape=(len(values),)
    def tolist(self):
        if self.device.type!='cpu':raise AssertionError('Unexpected device read')
        return self.values


class DiagnosticTests(unittest.TestCase):
    def test_export_checks_all_eight_ranks_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'work-metadata').mkdir();(root/'traces').mkdir()
            for rank in range(8):
                (root/'work-metadata'/f'worker-{rank}.json').write_text(json.dumps({'records':[{'rank':rank,'query_start_loc_cpu':[0,5]}]}))
            self.assertEqual(export_observations(root)['status'],'complete')
            (root/'work-metadata/worker-7.json').unlink()
            self.assertEqual(export_observations(root)['status'],'partial')

    def test_launch_is_profile_only_and_keeps_stock_runtime_fallback(self):
        from experiment_runner import make_launch
        config={'cpu_work_metadata':True,'profile_steps':2,'profile_phase':'prefill','profile_stratum':'long'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaises(ValueError):make_launch(config,root,profile=False)
            with self.assertRaises(ValueError):make_launch(config|{'profile_steps':32},root,profile=True)
            path=make_launch(config,root,profile=True)
            self.assertIn('export SPARSE_WORK_DIAG_ENABLE=1',path.read_text())
            self.assertIn('${PYTHONPATH:-}',path.read_text())
            self.assertEqual((root/'diagnostic-runtime/sparse_work_diag.py').read_bytes(),Path(diag.__file__).read_bytes())

    def setUp(self):
        diag._armed=False;diag._step=0;diag._records.clear();diag._selected.clear()

    def test_default_off_leaves_import_hooks_unchanged(self):
        before=list(sys.meta_path)
        with patch.dict(os.environ,{'SPARSE_WORK_DIAG_ENABLE':'0'}):self.assertFalse(diag.install())
        self.assertEqual(sys.meta_path,before)

    def test_gpu_and_nonlength_payloads_are_never_read(self):
        self.assertIsNone(diag.cpu_lengths(FakeArray([4],device='npu')))
        self.assertIsNone(diag.cpu_lengths(FakeArray(['secret prompt'])))
        self.assertIsNone(diag.cpu_lengths(FakeArray(list(range(34)))))
        self.assertEqual(diag.cpu_lengths(FakeArray([0,5,9])),[0,5,9])

    def test_two_steps_two_ratios_bound_and_redacted_flush(self):
        torch=ModuleType('torch');torch.distributed=SimpleNamespace(is_initialized=lambda:True,get_rank=lambda:3)
        common=SimpleNamespace(num_reqs=2,num_actual_tokens=9,num_input_tokens=16,
            query_start_loc_cpu=FakeArray([0,5,9]),_seq_lens_cpu=FakeArray([10,20]),secret='private prompt')
        result=SimpleNamespace(num_prefills=2,num_decode_tokens=0)
        diag._armed=True
        with patch.dict(sys.modules,{'torch':torch,'torch.distributed':torch.distributed}):
            for step in range(1,6):
                diag._step=step
                for ratio in (4,128,4):diag.observe(SimpleNamespace(compressor_ratio=ratio),common,result)
        self.assertEqual(len(diag._records),4)
        self.assertEqual({r['target_scheduler_step'] for r in diag._records},{1,2})
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'SPARSE_WORK_DIAG_DIR':tmp}):
            diag.flush();text=next(Path(tmp).glob('worker-*.json')).read_text()
            self.assertNotIn('private prompt',text)
            self.assertIn('"selected_tiling": null',text)
            self.assertEqual(len(list(Path(tmp).glob('*.tmp'))),0)

    def test_wrapped_model_prepare_keeps_original_return_identity(self):
        value=object()
        class Runner:
            def _prepare_inputs(self,*args,**kwargs):return value
        module=SimpleNamespace(__name__='vllm_ascend.worker.model_runner_v1',NPUModelRunner=Runner)
        diag.patch_module(module)
        self.assertIs(Runner()._prepare_inputs(),value)
        self.assertEqual(diag._step,0)
        diag._armed=True
        self.assertIs(Runner()._prepare_inputs(),value)
        self.assertEqual(diag._step,1)


if __name__=='__main__':unittest.main()
