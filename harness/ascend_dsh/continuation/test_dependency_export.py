import unittest
import tempfile
from pathlib import Path
import csv
import json
from unittest.mock import patch
from profile_dependency_export import query_quant,paired_scale


class DependencyTests(unittest.TestCase):
    def test_master_gets_only_explicit_shared_profile_read_capability(self):
        from research_broker import Broker
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'research').mkdir()
            with patch('research_broker.OUT',root):
                self.assertNotIn('read_profile',Broker('before-export','master').names())
                (root/'research/profile-export-access.json').write_text(json.dumps({'shared_profile_csvs':{'completed':{'export.csv':'pin'}}}))
                broker=Broker('after-export','master')
                self.assertIn('read_profile',broker.names())
                self.assertNotIn('launch_experiment',broker.names())
                self.assertNotIn('run_cpu',broker.names())

    def test_large_event_exports_are_split_without_dropping_rows(self):
        from profile_dependency_export import ShardedCsv
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);writer=ShardedCsv(root/'flows.csv',['id','name'],limit=80)
            for i in range(20):writer.writerow({'id':i,'name':'test-flow'})
            writer.close()
            rows=[]
            for p in root.glob('*.csv'):
                with p.open() as stream:rows+=list(csv.DictReader(stream))
            self.assertEqual(sorted(int(r['id']) for r in rows),list(range(20)))
            self.assertGreater(len(list(root.glob('*.csv'))),1)

    def quant(self):
        return {'Type':'DynamicQuant','Input Shapes':'"8186,64,128"','Output Shapes':'"8186,64,128;8186,64"',
                'Stream ID':'2','Start Time(us)':'1794287447345047.438','Duration(us)':'380.214'}

    def test_query_shape_does_not_match_other_quantization(self):
        self.assertTrue(query_quant(self.quant()))
        self.assertFalse(query_quant(self.quant()|{'Input Shapes':'"8186,4096"'}))
        self.assertFalse(query_quant({'Type':'hcom_allReduce_','Input Shapes':'N/A'}))

    def test_scale_pair_requires_stream_shape_and_nonoverlap(self):
        row={'Type':'Muls','Output Shapes':'"523904,128"','Stream ID':'2',
             'Start Time(us)':'1794287447344891.732','Duration(us)':'155.606'}
        self.assertTrue(paired_scale(row,self.quant()))
        self.assertFalse(paired_scale(row|{'Stream ID':'10'},self.quant()))
        self.assertFalse(paired_scale(row|{'Output Shapes':'"8186,64"'},self.quant()))
        self.assertFalse(paired_scale(row|{'Duration(us)':'156'},self.quant()))
        self.assertFalse(paired_scale(None,self.quant()))


if __name__=='__main__':unittest.main()
