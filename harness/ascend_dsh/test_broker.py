import json
from pathlib import Path
import shlex
import tempfile
import unittest

from research_broker import Broker, local_path, execute_python
from experiment_runner import make_launch, validate_config
from prepare_baseline import OUT


class BrokerTests(unittest.TestCase):
    def test_parent_and_absolute_and_symlink_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / 'scratch'; work.mkdir()
            (work / 'escape').symlink_to(Path(tmp))
            for name in ('../validation', '/etc/passwd', 'escape/secret', 'a/../../file'):
                with self.assertRaises(ValueError): local_path(work, name)

    def test_installed_source_reading_is_available(self):
        broker = object.__new__(Broker)
        for tree in ('vllm', 'vllm_ascend'):
            p = broker.source(tree, '__init__.py')
            self.assertTrue(p.is_file())
            self.assertTrue(p.read_text())

    def test_resource_and_sampling_changes_rejected(self):
        for config in ({'model': 'other'}, {'temperature': 1}, {'tensor_parallel_size': 16},
                       {'dataset_split': 'validation'}, {'additional_config': {'ascend_log_path': '/tmp/escape'}},
                       {'additional_config': {'enable_sparse_li_c4': True}},
                       {'max_num_seqs': 1000}, {'num_speculative_tokens': True}):
            with self.assertRaises(ValueError): validate_config(config)

    def test_default_launch_is_stock_and_runner_stays_mrv1(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_launch({}, Path(tmp))
            original = next(l[5:] for l in (OUT / 'launch-mrv1.sh').read_text().splitlines() if l.startswith('exec '))
            actual = next(l[5:] for l in p.read_text().splitlines() if l.startswith('exec '))
            self.assertEqual(shlex.split(original), shlex.split(actual))
            self.assertIn('export VLLM_USE_V2_MODEL_RUNNER=0', p.read_text())

    def test_only_requested_flag_is_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_launch({'max_num_batched_tokens': 4096, 'additional_config': {'enable_prefill_mc2': True}}, Path(tmp))
            argv = shlex.split(next(l[5:] for l in p.read_text().splitlines() if l.startswith('exec ')))
            self.assertEqual(argv[argv.index('--max-num-batched-tokens') + 1], '4096')
            extra = json.loads(argv[argv.index('--additional-config') + 1])
            self.assertTrue(extra['enable_prefill_mc2'])
            self.assertFalse(extra['ascend_compilation_config']['enable_static_kernel'])

    def test_cpu_exit_status_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); work = base / 'scratch'; work.mkdir()
            for code in (0, 7):
                (work / 'exit.py').write_text('import sys\nsys.exit(' + str(code) + ')\n')
                result = execute_python(work, 'exit.py', base / ('exit-' + str(code)))
                self.assertEqual(result['exit_code'], code)

    def test_cpu_sandbox_denies_outside_read_and_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); work = base / 'scratch'; work.mkdir()
            canary = base / 'unrelated-canary.txt'; canary.write_text('non-secret-canary')
            program = work / 'probe.py'
            (work / 'input.json').write_text('{"value": 6}')
            program.write_text('import socket, os, json\nfrom pathlib import Path\n'
                f'checks=[]\ntry:\n Path({str(canary)!r}).read_text()\n checks.append(False)\nexcept (PermissionError, FileNotFoundError): checks.append(True)\n'
                'try:\n socket.socket()\n checks.append(False)\nexcept PermissionError: checks.append(True)\n'
                'try:\n Path("new.txt").write_text("no")\n checks.append(False)\nexcept PermissionError: checks.append(True)\n'
                'try:\n os.fork()\n checks.append(False)\nexcept PermissionError: checks.append(True)\n'
                'try:\n os.chroot(".")\n checks.append(False)\nexcept PermissionError: checks.append(True)\n'
                'assert os.getuid()==65534\nassert json.loads(Path("input.json").read_text())["value"]==6\n'
                'print(checks)\nassert checks==[True]*5\n')
            result = execute_python(work, 'probe.py', base / 'execution')
            self.assertEqual(result['exit_code'], 0, result)
            self.assertTrue(result['chroot_applied'] and result['seccomp_applied'])
            self.assertEqual(result['dropped_uid'], 65534)
            self.assertEqual(canary.read_text(), 'non-secret-canary')


if __name__ == '__main__': unittest.main()
