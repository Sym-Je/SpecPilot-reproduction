import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from harness.autonomy_integrity import check


class IntegrityTests(unittest.TestCase):
    def fixture(self,root):
        work=root/'work/one'
        (work/'inputs').mkdir(parents=True)
        (root/'executions/T001').mkdir(parents=True)
        (root/'evidence.json').write_text('{}')
        (work/'inputs/evidence.json').write_text('{}')
        (work/'test.py').write_text('print(1)')
        (root/'executions/T001/stderr').write_bytes(b'SP_ISOLATION_READY\n')
        (root/'state.json').write_text(json.dumps(dict(tasks=dict(one=dict(files={
            'test.py':hashlib.sha256(b'print(1)').hexdigest()})))))
        return work

    def test_issued_evidence_and_authored_files_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            self.fixture(root)
            self.assertEqual(check(root)['workspace_inputs_verified'],1)

    def test_consumed_input_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work=self.fixture(root)
            (work/'inputs/evidence.json').write_text('{"edited":true}')
            with self.assertRaisesRegex(ValueError,'consumed input'):check(root)

    def test_file_changes_extra_files_and_missing_bootstrap_are_rejected(self):
        for fault in ('code','extra','bootstrap'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);work=self.fixture(root)
                if fault=='code':(work/'test.py').write_text('print(2)')
                elif fault=='extra':(work/'untracked.txt').write_text('extra')
                else:(root/'executions/T001/stderr').write_text('missing')
                with self.assertRaises(ValueError):check(root)


if __name__=='__main__':
    unittest.main()
