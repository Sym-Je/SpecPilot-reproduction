import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from harness.source_replay import own_replay, verify_replay


class SourceReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.directory=self.root/'direction';self.directory.mkdir()
        (self.directory/'manifest.json').write_text(json.dumps({'role':'direction'}))
        record=self.directory/'tools-01/action-001';record.mkdir(parents=True)
        self.content='print("own previous script")\n'
        digest=hashlib.sha256(self.content.encode()).hexdigest()
        request=dict(threadId='own-thread',turnId='own-turn',callId='own-call',tool='research',namespace=None,
            arguments={'action':dict(kind='write_file',path='scratch/check.py',content=self.content)})
        response=dict(success=True,contentItems=[dict(type='inputText',text=json.dumps(dict(status='completed',sha256=digest)))])
        (record/'request.json').write_text(json.dumps(request))
        (record/'response.json').write_text(json.dumps(response))
        rows=[dict(direction='server',message=dict(id=1,method='item/tool/call',params=request)),
            dict(direction='client',message=dict(id=1,result=response))]
        (self.directory/'wire.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))

    def test_replays_only_native_own_files_and_preserves_authorship(self):
        work=self.root/'work';work.mkdir()
        replay=own_replay(self.directory,work)
        self.assertEqual((work/'scratch/check.py').read_text(),self.content)
        self.assertEqual(verify_replay(replay,'direction'),{'scratch/check.py':hashlib.sha256(self.content.encode()).hexdigest()})

    def test_cannot_relabel_another_role(self):
        replay=own_replay(self.directory,self.root/'work')
        with self.assertRaises(ValueError):verify_replay(replay,'Master')

    def test_mutated_native_wire_is_rejected(self):
        replay=own_replay(self.directory,self.root/'work')
        with (self.directory/'wire.jsonl').open('a') as destination:destination.write('{}\n')
        with self.assertRaises(ValueError):verify_replay(replay,'direction')

    def test_receipt_sha_cannot_be_replaced(self):
        replay=own_replay(self.directory,self.root/'work')
        replay['files']['scratch/check.py']['sha256']='0'*64
        with self.assertRaises(ValueError):verify_replay(replay,'direction')

    def test_repeated_continuation_keeps_original_author_wire(self):
        first=own_replay(self.directory,self.root/'first-work')
        next_role=self.root/'next-role';next_role.mkdir()
        (next_role/'manifest.json').write_text(json.dumps(dict(role='direction',own_replay=first)))
        (next_role/'wire.jsonl').write_text('')
        second=own_replay(next_role,self.root/'second-work')
        self.assertEqual(verify_replay(second,'direction'),verify_replay(first,'direction'))
        self.assertEqual((self.root/'second-work/scratch/check.py').read_text(),self.content)

    def test_chunked_source_recovery_preserves_all_native_appends(self):
        record=self.directory/'tools-01/action-002';record.mkdir()
        chunk='print("appended own code")\n'
        expected=hashlib.sha256(self.content.encode()).hexdigest()
        digest=hashlib.sha256((self.content+chunk).encode()).hexdigest()
        request=dict(threadId='own-thread',turnId='own-turn',callId='append-call',tool='research',namespace=None,
            arguments={'action':dict(kind='append_file',path='scratch/check.py',expected_sha256=expected,content=chunk)})
        response=dict(success=True,contentItems=[dict(type='inputText',text=json.dumps(dict(status='completed',sha256=digest)))])
        (record/'request.json').write_text(json.dumps(request));(record/'response.json').write_text(json.dumps(response))
        with (self.directory/'wire.jsonl').open('a') as destination:
            for row in [dict(direction='server',message=dict(id=2,method='item/tool/call',params=request)),
                    dict(direction='client',message=dict(id=2,result=response))]:destination.write(json.dumps(row)+'\n')
        replay=own_replay(self.directory,self.root/'chunk-work')
        self.assertEqual((self.root/'chunk-work/scratch/check.py').read_text(),self.content+chunk)
        self.assertEqual(verify_replay(replay,'direction')['scratch/check.py'],digest)
