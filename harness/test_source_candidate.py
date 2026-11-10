import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from harness.build_engine import tree_sha
from harness.candidate import make_spec
from harness.source_candidate import apply_edits, build_bundle, candidate_arm, cpu_receipt, file_sha, load_bundle, read_patch, validate_action


class SourceCandidateTests(unittest.TestCase):
    def test_kernel_device_minor_is_not_a_virtual_cuda_ordinal(self):
        from exp.source_research import kernel_device_minor
        information = ['GPU UUID: GPU-fixture\nDevice Minor: 6\n', 'GPU UUID: GPU-other\nDevice Minor: 7\n']
        self.assertEqual(kernel_device_minor(information, 'GPU-fixture'), 6)
        with self.assertRaises(ValueError):
            kernel_device_minor(information, 'GPU-absent')
        with self.assertRaises(ValueError):
            kernel_device_minor(information + information, 'GPU-fixture')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stock = self.root / 'stock'
        self.path = 'python/sglang/srt/speculative/probe.py'
        source = self.stock / self.path
        source.parent.mkdir(parents=True)
        source.write_text('def value():\n    return 8\n')
        (self.stock / 'lab').mkdir()
        (self.stock / 'lab/stock.py').write_text('STOCK = True\n')
        (self.stock / 'TREE_SHA').write_text(tree_sha(self.stock) + '\n')
        config = self.root / 'config.json'
        config.write_text('{"stock":{"block_size":8}}')
        self.base = make_spec(self.stock, config, '/models/target', '/models/draft', 'a' * 40)
        self.patch = dict(schema='source-option-v1', option_id='fixture-only', edits=[
            dict(path=self.path, base_sha256=file_sha(source), find='return 8', replace='return 9')])
        self.patch_path = self.root / 'patch.json'
        self.patch_path.write_text(json.dumps(self.patch))

    def test_disabled_option_does_not_import_or_select_candidate_source(self):
        bundle = self.root / 'bundle'
        manifest = build_bundle(self.base, self.patch_path, bundle)
        disabled = candidate_arm(bundle)
        enabled = candidate_arm(bundle, enabled=True)
        self.assertEqual(disabled['engine'], str(self.stock))
        self.assertEqual(disabled['tree_sha'], self.base['stock_tree_sha'])
        self.assertEqual(enabled['tree_sha'], manifest['candidate_tree_sha'])
        self.assertNotEqual(enabled['tree_sha'], disabled['tree_sha'])
        self.assertIn('return 8', (self.stock / self.path).read_text())
        self.assertIn('return 9', (bundle / 'engine' / self.path).read_text())
        with self.assertRaises(ValueError):
            candidate_arm(bundle, enabled=1)

    def test_reproducible_source_bundle(self):
        first = build_bundle(self.base, self.patch_path, self.root / 'one')
        second = build_bundle(self.base, self.patch_path, self.root / 'two')
        self.assertEqual(first, second)

    def test_path_escape_and_nonruntime_edits_refused(self):
        for name in ('../controller/x.py', 'python/sglang/srt/../launch.py',
                     'python/sglang/launch_server.py', '/tmp/source.py', 'python/sglang/srt/new.sh'):
            patch = copy.deepcopy(self.patch)
            patch['edits'][0]['path'] = name
            self.patch_path.write_text(json.dumps(patch))
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_patch(self.patch_path)

    def test_anchors_stock_identity_syntax_and_noop_refused(self):
        for changes in (dict(find='absent'), dict(base_sha256='0' * 64),
                        dict(replace='return ('), dict(replace='return 8')):
            patch = copy.deepcopy(self.patch)
            patch['edits'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises((ValueError, SyntaxError)):
                apply_edits(self.stock, patch)

    def test_symlink_and_missing_target_refused(self):
        target = self.stock / self.path
        content = target.read_text()
        target.unlink()
        outside = self.root / 'outside.py'
        outside.write_text(content)
        target.symlink_to(outside)
        with self.assertRaises(ValueError):
            apply_edits(self.stock, self.patch)

    def test_source_tampering_refused(self):
        bundle = self.root / 'bundle'
        build_bundle(self.base, self.patch_path, bundle)
        (bundle / 'engine' / self.path).write_text('CORRUPTED = True\n')
        with self.assertRaises(ValueError):
            load_bundle(bundle)

    def test_startup_change_cannot_be_disguised_as_source_option(self):
        base = make_spec(self.stock, self.root / 'config.json', '/models/target', '/models/draft', 'a' * 40, value=12)
        with self.assertRaises(ValueError):
            build_bundle(base, self.patch_path, self.root / 'bundle')

    def test_request_cannot_grant_extra_resources_or_shell(self):
        action = dict(kind='run_source', patch='scratch/option.json', self_check='scratch/check.py',
            per_suite=1, max_new_tokens=2048, reason='fixture rationale')
        validate_action(action)
        for change in (dict(command='shell'), dict(image='other'), dict(per_suite=True),
                       dict(patch='../x.json'), dict(max_new_tokens=64), dict(kind='run_engine')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_action(dict(action, **change))

    def test_cpu_receipt_requires_current_patch_and_current_check(self):
        work = self.root / 'work'
        (work / 'scratch').mkdir(parents=True)
        patch = work / 'scratch/option.json'
        patch.write_text(self.patch_path.read_text())
        check = work / 'scratch/check.py'
        check.write_text('print("fixture")\n')
        action = dict(kind='run_source', patch='scratch/option.json', self_check='scratch/check.py',
            per_suite=1, max_new_tokens=256, reason='fixture')
        record = self.root / 'records/tools-01/action-001/response.json'
        record.parent.mkdir(parents=True)
        value = dict(exit_code=0, code_sha256=file_sha(check), workspace_file_sha256={
            action['patch']: file_sha(patch), action['self_check']: file_sha(check)})
        record.write_text(json.dumps(dict(success=True, contentItems=[dict(text=json.dumps(value))])))
        self.assertEqual(cpu_receipt(work, self.root / 'records', action)['files'][action['patch']], file_sha(patch))
        patch.write_text(patch.read_text() + '\n')
        with self.assertRaises(ValueError):
            cpu_receipt(work, self.root / 'records', action)

    def test_new_stage_budget_cannot_inherit_old_resource_ceiling(self):
        from exp.source_resource import stage_budget
        from harness.engine_research import Budget
        path = self.root / 'source-budget.json'
        budget = stage_budget(path)
        self.assertEqual(budget.read()['gpu_seconds'], 57600)
        self.assertEqual(budget.read()['wall_seconds'], 43200)
        self.assertEqual(budget.read()['concurrent_gpus'], 2)
        with self.assertRaises(ValueError):
            Budget(path)
        with self.assertRaises(ValueError):
            budget.reserve('too-many', 4, 1)


if __name__ == '__main__':
    unittest.main()
