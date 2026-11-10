from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from prepare_baseline import write,sha
from completed_profile_access import register


class AccessTests(unittest.TestCase):
    def fixture(self,root,split='dev'):
        folder=root/'experiments/complete-dev';(folder/'traces').mkdir(parents=True)
        (root/'research').mkdir()
        write(folder/'state.json',{'status':'complete','baseline_restored':True,'request':{'split':split}})
        write(folder/'profile-quality.json',{'all_eight_ranks_complete':True,'warnings':[]})
        return folder

    def test_only_safe_completed_csvs_are_shared_and_hashed(self):
        with tempfile.TemporaryDirectory() as tmp,patch('completed_profile_access.OUT',Path(tmp)):
            root=Path(tmp);folder=self.fixture(root)
            allowed=folder/'traces/cpu_work_metadata.csv';allowed.write_text('rank,count\n0,4\n')
            (folder/'traces/request_payloads.csv').write_text('private data')
            (folder/'traces/task_time.csv').symlink_to(folder/'traces/request_payloads.csv')
            write(root/'research/profile-export-access.json',{'shared_profile_csvs':{'old':{'old.csv':'oldhash'}}})
            shared=register(folder)
            self.assertEqual(shared,{'cpu_work_metadata.csv':sha(allowed)})
            import json
            data=json.loads((root/'research/profile-export-access.json').read_text())
            self.assertIn('old',data['shared_profile_csvs'])
            self.assertIsNone(data['additional_completed_profiles'][folder.name]['usage_csv'])

    def test_validation_and_unrestored_profiles_are_rejected(self):
        for split,restored in [('validation',True),('dev',False)]:
            with tempfile.TemporaryDirectory() as tmp,patch('completed_profile_access.OUT',Path(tmp)):
                folder=self.fixture(Path(tmp),split)
                write(folder/'state.json',{'status':'complete','baseline_restored':restored,'request':{'split':split}})
                with self.assertRaises(ValueError):register(folder)


if __name__=='__main__':unittest.main()
