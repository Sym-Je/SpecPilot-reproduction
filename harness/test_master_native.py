import json
from pathlib import Path
import tempfile
import unittest

from harness.master_native import check,prepare,snapshot


class MasterNativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)/'repo';self.root.mkdir()
        for name in ('controller/judge.py','ledger/events.jsonl','docs/02-acceptance.md'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original\n')
        sealed=self.root/'eval/sealed';sealed.mkdir(parents=True)
        (sealed/'not-for-research.txt').write_text('never included in snapshots')
        self.directory=self.root/'logs/fixture'

    def test_unchanged_files_do_not_certify_no_forbidden_reads(self):
        prepare(self.root,self.directory)
        result=check(self.root,self.directory)
        self.assertTrue(result['protected_files_unchanged'])
        self.assertEqual(result['forbidden_reads_verified'],False)
        self.assertEqual(result['read_compliance'],'not_proven_by_file_snapshot')
        self.assertFalse(any('sealed' in name for name in snapshot(self.root)['files']))

    def test_detects_modification_deletion_and_new_ledger_record(self):
        prepare(self.root,self.directory)
        (self.root/'controller/judge.py').write_text('changed\n')
        (self.root/'docs/02-acceptance.md').unlink()
        (self.root/'ledger/new.jsonl').write_text('unapproved\n')
        result=check(self.root,self.directory)
        self.assertFalse(result['protected_files_unchanged'])
        self.assertEqual(set(result['changed']),{'controller/judge.py','docs/02-acceptance.md','ledger/new.jsonl'})

    def test_cannot_reset_baseline_or_follow_a_protected_symlink(self):
        prepare(self.root,self.directory)
        with self.assertRaises(FileExistsError):prepare(self.root,self.directory)
        (self.root/'controller/link.py').symlink_to(self.root/'eval/sealed/not-for-research.txt')
        entry=snapshot(self.root)['files']['controller/link.py']
        self.assertEqual(entry['kind'],'symlink')
        self.assertNotIn('sha256',entry)

    def test_prompt_only_mode_does_not_claim_a_hard_boundary(self):
        manifest=prepare(self.root,self.directory)
        self.assertEqual(manifest['permission_mode'],'inherit-parent-native')
        self.assertEqual(manifest['role_specific_enforcement'],'prompt-only')
        self.assertEqual(manifest['gpu_authorized'],False)
        self.assertFalse(manifest['fork_context'])
        self.assertEqual(json.loads((self.directory/'manifest.json').read_text()),manifest)


if __name__=='__main__':unittest.main()
