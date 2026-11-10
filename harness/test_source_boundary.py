import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SourceBoundaryTests(unittest.TestCase):
    def test_trusted_pipe_closed_before_later_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scratch = root / 'scratch'
            scratch.mkdir()
            source = root / 'source.txt'
            source.write_text('authorized\n')
            canary = root / 'canary.txt'
            canary.write_text('unchanged\n')
            ready_read, ready_write = os.pipe()
            payload = dict(cpu_probe=True, scratch=str(scratch), readonly=[str(source), sys.prefix], executables=[sys.executable],
                allowed_read=str(source), allowed_content='authorized\n', canary=str(canary), ready_fd=ready_write)
            child_code = ('from pathlib import Path\n'
                'try: Path(' + repr(str(canary)) + ').read_text()\n'
                'except PermissionError: print("child_boundary_inherited")\n'
                'else: raise RuntimeError("child escaped file boundary")')
            script = ('import json,os,sys,subprocess;sys.path.insert(0,' + repr(str(Path(__file__).resolve().parents[1])) + ');'
                'from harness.source_boundary import main;payload=json.load(sys.stdin);main(payload);'
                '\ntry: os.write(payload["ready_fd"],b"forged")'
                '\nexcept OSError: print("trusted_pipe_closed")\n'
                'subprocess.run([sys.executable,"-I","-B","-c",' + repr(child_code) + '],check=True)')
            process = subprocess.Popen([sys.executable, '-I', '-B', '-c', script], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(ready_write,), text=True)
            os.close(ready_write)
            stdout, stderr = process.communicate(json.dumps(payload), timeout=15)
            with os.fdopen(ready_read) as ready:
                receipt = json.loads(ready.read())
            self.assertEqual(process.returncode, 0, stderr)
            self.assertTrue(receipt['landlock_applied'])
            self.assertIn('trusted_pipe_closed', stdout)
            self.assertIn('child_boundary_inherited', stdout)

    def test_actual_file_and_process_denials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scratch = root / 'scratch'
            scratch.mkdir()
            allowed = root / 'source.txt'
            allowed.write_text('authorized\n')
            canary = root / 'protected.txt'
            canary.write_text('unchanged\n')
            payload = dict(cpu_probe=True, scratch=str(scratch), readonly=[str(allowed)],
                executables=[], allowed_read=str(allowed), allowed_content='authorized\n', canary=str(canary))
            process = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name('source_boundary.py'))],
                input=json.dumps(payload), capture_output=True, text=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            receipt = json.loads(process.stdout)
            self.assertTrue(receipt['landlock_applied'])
            self.assertTrue(receipt['seccomp_applied'])
            self.assertTrue(all(receipt['denied'].values()))
            self.assertFalse(receipt['network_isolated'])
            self.assertEqual(canary.read_text(), 'unchanged\n')
            self.assertEqual(allowed.read_text(), 'authorized\n')

    @unittest.skipIf(os.geteuid() == 0, 'requires non-root host to test mandatory production UID drop')
    def test_production_refuses_missing_uid_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = dict(scratch=temporary, uid=60010)
            process = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name('source_boundary.py'))],
                input=json.dumps(payload), capture_output=True, text=True, timeout=15)
            self.assertNotEqual(process.returncode, 0)
            self.assertNotIn('SOURCE_BOUNDARY_READY', process.stdout)


if __name__ == '__main__':
    unittest.main()
