import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import cache_metadata_diag as diag


class MetadataTests(unittest.TestCase):
    def config(self):
        spec=NS(block_size=4096,tokens_per_state=128,prefix_cacheable=True,
                non_causal=False,non_causal_multi_token_decode=False,dtype='torch.bfloat16')
        group=NS(layer_names=['model.layers.0.attn'],kv_cache_spec=spec,is_eagle_group=False)
        return NS(num_blocks=100,kv_cache_groups=[group],kv_cache_tensors=[])

    def test_default_off_does_not_install(self):
        with patch.dict(os.environ,{},clear=True):
            before=list(sys.meta_path)
            self.assertFalse(diag.install());self.assertEqual(before,sys.meta_path)

    def test_metadata_excludes_values_and_support_claims(self):
        class Canary:
            def __str__(self):raise AssertionError('No arbitrary object conversion')
            def cpu(self):raise AssertionError('No device copy')
            def tolist(self):raise AssertionError('No tensor values')
        cfg=self.config();cfg.kv_cache_groups[0].kv_cache_spec.secret=Canary()
        cfg.kv_cache_groups[0].kv_cache_spec.head_size=Canary()
        row=diag.cache_plan(cfg)
        self.assertNotIn('secret',json.dumps(row))
        self.assertIsNone(row['groups'][0]['spec']['fields']['head_size'])
        self.assertFalse(row['enabled_state_restoration_validated'])
        self.assertEqual(row['groups'][0]['spec']['fields']['block_size'],4096)

    def test_hard_group_bound_explicitly_marks_incomplete(self):
        cfg=self.config();cfg.kv_cache_groups*=diag.MAX_GROUPS+1
        row=diag.cache_plan(cfg)
        self.assertTrue(row['truncated']);self.assertLessEqual(len(row['groups']),diag.MAX_GROUPS)

    def test_wrapper_preserves_identity_calls_and_original_exception(self):
        seen=[];sentinel=object()
        class Original:
            def initialize_kv_cache(self,*args,**kwargs):
                seen.append(1)
                if kwargs.get('fail'):raise ValueError('original failure')
                return sentinel
        module=NS(__name__='vllm_ascend.worker.model_runner_v1',NPUModelRunner=Original)
        with patch.object(diag,'capture_worker',side_effect=RuntimeError('observer failure')):
            diag.patch_module(module)
            self.assertIs(Original().initialize_kv_cache(self.config()),sentinel)
            with self.assertRaisesRegex(ValueError,'original failure'):
                Original().initialize_kv_cache(self.config(),fail=True)
        self.assertEqual(len(seen),2)

    def test_private_atomic_output_has_fixed_bound_and_no_live_object_repr(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PREFIX_CACHE_METADATA_DIR':tmp}),patch.object(diag,'_emitted',0):
            diag.emit('worker',{'groups':[]})
            files=list(Path(tmp).glob('*.json'));self.assertEqual(len(files),1)
            self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
            self.assertFalse(json.loads(files[0].read_text())['enabled_state_restoration_validated'])


if __name__=='__main__':unittest.main()
