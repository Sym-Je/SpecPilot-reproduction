import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from harness.e2e_context import export_context


class EndToEndContextTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.profile=self.root/'profile';self.timing=self.root/'timing'
        self.profile.mkdir();self.timing.mkdir()
        self.tree='a'*64
        files={}
        for arm in ('target','draft'):
            path=self.profile/f'inputs/{arm}/config.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(model_type='fixture',hidden_size=16,vocab_size=32,private_note='do not export')))
            files[str(path.relative_to(self.profile))]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest=dict(identity=dict(tree_sha=self.tree,server_args=dict(dtype='bfloat16',model_path='/not/for/roles')),files=files)
        (self.profile/'manifest.json').write_text(json.dumps(self.manifest))
        for ordinal in (1,2):
            directory=self.timing/f'round-{ordinal:02d}';directory.mkdir()
            raw=directory/'stock-raw/one.json';raw.parent.mkdir();raw.write_text('{}')
            row=dict(arm='stock',tree_sha=self.tree,round=ordinal,prompt_tokens=4,completion_tokens=8,
                tokens=8,latency_s=1.0,tokens_per_s=8.0,spec_verify_ct=2,tau=4.0,max_new_tokens=256,
                output_ids=[1,2],item=dict(prompt='not for roles'),generator=dict(server_args=self.manifest['identity']['server_args']),
                raw_evidence=dict(path=str(raw),sha256=hashlib.sha256(raw.read_bytes()).hexdigest()))
            (directory/'stock.jsonl').write_text(json.dumps(row)+'\n')

    def test_exports_only_bound_stock_metadata_without_workload_conflation(self):
        value=export_context(self.profile,self.timing,canonical_tree=self.tree)
        self.assertEqual(value['model_configs']['draft']['hidden_size'],16)
        self.assertEqual(len(value['normal_requests']),2)
        text=json.dumps(value)
        for forbidden in ('private_note','output_ids','not for roles','/not/for/roles'):
            self.assertNotIn(forbidden,text)
        self.assertFalse(value['normal_requests_are_profile_workload'])
        self.assertIsNone(value['critical_path_fractions'])

    def test_modified_configuration_is_rejected(self):
        (self.profile/'inputs/draft/config.json').write_text('{}')
        with self.assertRaises(ValueError): export_context(self.profile,self.timing,canonical_tree=self.tree)

    def test_nonstock_timing_is_rejected(self):
        path=self.timing/'round-01/stock.jsonl';row=json.loads(path.read_text());row['arm']='candidate'
        path.write_text(json.dumps(row)+'\n')
        with self.assertRaises(ValueError): export_context(self.profile,self.timing,canonical_tree=self.tree)

    def test_changed_raw_source_is_rejected(self):
        (self.timing/'round-01/stock-raw/one.json').write_text('{"changed":true}')
        with self.assertRaises(ValueError): export_context(self.profile,self.timing,canonical_tree=self.tree)

    def test_redacted_model_paths_still_participate_in_identity_validation(self):
        path=self.timing/'round-01/stock.jsonl';row=json.loads(path.read_text())
        row['generator']['server_args']['model_path']='/different/model'
        path.write_text(json.dumps(row)+'\n')
        with self.assertRaises(ValueError): export_context(self.profile,self.timing,canonical_tree=self.tree)
