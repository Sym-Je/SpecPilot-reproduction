import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from harness.diagnostic_archive import frozen_audit


class DiagnosticArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.output=self.root/'remote';self.output.mkdir()
        self.files={'exp/__init__.py':b'', 'exp/ceiling_run.py':b'def audit(directory):\n    return {"diagnostic": True}\n'}
        self.write()

    def write(self,extra=None):
        path=self.root/'source.tar'
        with tarfile.open(path,'w') as archive:
            for name,raw in self.files.items():
                info=tarfile.TarInfo(name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
            if extra is not None:archive.addfile(extra,io.BytesIO(b''))
        record=dict(source_archive=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            files={name:hashlib.sha256(raw).hexdigest() for name,raw in self.files.items()}))
        (self.root/'request.json').write_text(json.dumps(record))
        (self.output/'result.json').write_text(json.dumps(dict(diagnostic=True)))

    def test_exact_archive_executes_only_approved_cpu_audit_and_rechecks_result(self):
        answer=frozen_audit(self.output,'exp.ceiling_run')
        self.assertEqual(answer['result'],dict(diagnostic=True))
        self.assertTrue(answer['source_archive_verified'])
        (self.output/'result.json').write_text('{}')
        with self.assertRaises(ValueError):frozen_audit(self.output,'exp.ceiling_run')

    def test_archive_tamper_and_unapproved_entry_reject(self):
        with self.assertRaises(ValueError):frozen_audit(self.output,'exp.ceiling_run.run')
        (self.root/'source.tar').write_bytes(b'bad')
        with self.assertRaises(ValueError):frozen_audit(self.output,'exp.ceiling_run')

    def test_duplicate_traversal_and_links_reject_before_execution(self):
        for name in ('exp/ceiling_run.py','../escape.py','/tmp/escape.py'):
            with self.subTest(name=name):
                self.write(tarfile.TarInfo(name))
                with self.assertRaises(ValueError):frozen_audit(self.output,'exp.ceiling_run')
        extra=tarfile.TarInfo('link');extra.type=tarfile.SYMTYPE;extra.linkname='/tmp'
        self.write(extra)
        with self.assertRaises(ValueError):frozen_audit(self.output,'exp.ceiling_run')


if __name__=='__main__':unittest.main()
