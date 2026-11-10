"""CPU tests for legacy shutdown and future birth/exit tools, NOT finalizer acceptance."""

from contextlib import ExitStack, contextmanager
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

from controller import phase4_final as final
from controller.sealed_protocol import _private, _save
from exp import phase4_resource as resource
from exp import codex_boundary
from exp.phase4_run import reference
from harness import skill_rsi_audit as audit
from harness import test_skill_rsi_audit as audit_fixtures
from harness import test_source_candidate as source_fixtures
from harness.engine_research import Budget
from harness.source_candidate import build_bundle


class LegacyShutdownTests(unittest.TestCase):
    def setUp(self):
        helper = audit_fixtures.SkillRsiAuditTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper
        self.root = helper.root
        helper.role('direction-d3', 'direction', {'action': {'kind': 'finish'}})
        helper.snapshots()
        original_home = self.root / 'fake-codex-home'
        original_home.mkdir(mode=0o700)
        (original_home / 'auth.json').write_text('{"fixture":"not a credential"}')
        (original_home / 'config.toml').write_text('model="fixture"\nmodel_provider="fixture"\n'
            '[model_providers.fixture]\nname="fixture"\nrequires_openai_auth=true\nwire_api="responses"\n')
        for name in helper.role_counts:
            prior = audit.load(self.root / name / 'manifest.json')
            with patch.dict(os.environ, CODEX_HOME=str(original_home)):
                manifest = codex_boundary.prepare(self.root / ('prepared-' + name))
            self.addCleanup(shutil.rmtree, Path(manifest['work']).parent)
            for filename in ('rules.txt', 'evidence.json'):
                shutil.copyfile(Path(prior['work']) / 'inputs' / filename, Path(manifest['work']) / 'inputs' / filename)
            manifest.update(role=prior['role'], research_packet_sha256=prior['research_packet_sha256'],
                rules_sha256=audit.sha(Path(manifest['work']) / 'inputs/rules.txt'),
                evidence_sha256=audit.sha(Path(manifest['work']) / 'inputs/evidence.json'))
            helper.write(self.root / name / 'manifest.json', manifest)
        for process in helper.result['role_processes'].values():
            child = subprocess.Popen([sys.executable, '-B', '-c', 'pass'])
            child.wait(timeout=10)
            process['pid'] = child.pid
        helper.write(self.root / 'pipeline-result.json', helper.result)
        script = b'fixture_host = True\n'
        archive_path = helper.diagnostic / 'source.tar'
        with tarfile.open(archive_path, 'a') as archive:
            member = tarfile.TarInfo('exp/skill_rsi.py')
            member.size = len(script)
            archive.addfile(member, io.BytesIO(script))
        source_identity = audit.load(helper.diagnostic / 'source-identity.json')
        source_identity['files']['exp/skill_rsi.py'] = hashlib.sha256(script).hexdigest()
        source_identity['archive_sha256'] = audit.sha(archive_path)
        helper.write(helper.diagnostic / 'source-identity.json', source_identity)
        pending = audit.load(helper.diagnostic / 'pending.json')
        pending['source_sha256'] = audit.sha(archive_path)
        helper.write(helper.diagnostic / 'pending.json', pending)
        (self.root / 'host-start-skill-rsi.py').write_bytes(script)
        helper.write(self.root / 'host-loaded-identity.json', dict(pid=99999999, hot_reload=False,
            archive=str(archive_path), copy=str(self.root / 'host-start-skill-rsi.py'), script_sha256=hashlib.sha256(script).hexdigest()))
        self.proof = self.root / 'trusted-shutdown'
        self.proof.mkdir(mode=0o700)

    def observe(self, **options):
        with patch.object(audit, 'replay_feedback', side_effect=lambda path, request: self.helper.replays[str(path)]) as replay:
            result = final.observe_legacy_shutdown(self.root, self.proof, **options)
        self.assertGreater(replay.call_count, 0)
        return result

    def append_bound_reservation(self, proof):
        source = source_fixtures.SourceCandidateTests()
        source.setUp()
        self.addCleanup(source.doCleanups)
        bundle = source.root / 'bundle'
        build_bundle(source.base, source.patch_path, bundle)
        job = self.root / 'phase4-next-control'
        cohort = dict(pool_index={'path': '/controller-private/pool.json', 'sha256': 'a' * 64},
            dev_indexes=[{'path': '/controller-private/dev.json', 'sha256': 'b' * 64}], used_indexes=[],
            counts={'fixture': 1}, seed='fixed')
        def archive(directory):
            path = directory / 'source.tar'
            path.write_bytes(b'CPU-only current request archive fixture')
            _save(directory / 'source-identity.json', dict(archive=reference(path)))
            return path
        budget = Budget(self.root / 'resource-state.json', limits=resource.LIMITS)
        with patch.object(resource, 'archive_source', archive):
            resource.prepare(job, bundle=bundle, cohort=cohort, shutdown_registry=proof,
                research_roots=[self.root / 'master'], budget=budget, deadline=600, maintenance_stock_control=True)
        state = audit.load(budget.path)
        state['jobs'].append(dict(name=job.name, gpus=2, seconds=1800, reserved_unix=final.time.time(),
                                 terminated=False, create_calls=0))
        self.helper.write(budget.path, state)
        return reference(job / 'request.json')

    @contextmanager
    def unavailable_host_tmp(self, receipt):
        value = final.trusted_metadata(receipt, os.geteuid())
        roots = [Path(role['contexts'][1]) for role in value['roles']]
        with ExitStack() as patches:
            for name in ('stat', 'lstat', 'read_bytes', 'read_text', 'open', 'resolve', 'iterdir'):
                original = getattr(Path, name)
                def absent(path, *arguments, _original=original, **options):
                    if any(path == root or path.is_relative_to(root) for root in roots):
                        raise FileNotFoundError('fixture: broker host tmp is absent on GPU node')
                    return _original(path, *arguments, **options)
                patches.enter_context(patch.object(Path, name, absent))
            patches.enter_context(patch.object(final, '_legacy_roles', side_effect=AssertionError('remote must not stat host roles')))
            patches.enter_context(patch.object(final, '_legacy_proc_observation', side_effect=AssertionError('remote must not inspect host proc')))
            patches.enter_context(patch.object(final, 'identity', side_effect=AssertionError('remote proof validation must not reobserve host identity')))
            yield

    def test_independent_native_audit_and_real_host_observation_allow_control_only(self):
        self.assertFalse((self.root / 'source.tar').exists())
        self.assertFalse((self.root / 'source-identity.json').exists())
        receipt = self.observe()
        value = final.trusted_metadata(receipt, os.geteuid())
        self.assertEqual(value['schema'], final.LEGACY)
        self.assertTrue(value['historical_birth_identity_unavailable'])
        self.assertEqual(len(value['roles']), 6)
        self.assertTrue(all('start_ticks' not in role for role in value['roles']))
        self.assertEqual(value['proc_observation']['matches'], [])
        result = resource.research_stopped(receipt, maintenance_stock_control=True)
        self.assertEqual(result['roles_checked'], 6)
        self.assertEqual(Path(receipt['path']).stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, 'negative-control-only'):
            resource.research_stopped(receipt)

    def test_preserved_host_copy_and_per_request_archive_sha_drift_are_rejected(self):
        archive = self.helper.diagnostic / 'source.tar'
        original = archive.read_bytes()
        archive.write_bytes(original + b'archive drift')
        with self.assertRaisesRegex(ValueError, 'archive SHA'):
            self.observe()
        archive.write_bytes(original)
        (self.root / 'host-start-skill-rsi.py').write_text('changed after preservation')
        with self.assertRaisesRegex(ValueError, 'host-loaded source copy'):
            self.observe()

    def test_preserved_repo_relative_paths_resolve_on_remote_without_repo_root_assumption(self):
        path = self.root / 'host-loaded-identity.json'
        value = audit.load(path)
        value['archive'] = str(Path(self.root.name) / self.helper.diagnostic.name / 'source.tar')
        value['copy'] = str(Path(self.root.name) / 'host-start-skill-rsi.py')
        self.helper.write(path, value)
        receipt = self.observe()
        self.assertEqual(final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(),
            maintenance_stock_control=True)['roles_checked'], 6)

    def test_remote_control_passes_without_any_old_tmp_and_still_rejects_shared_or_receipt_drift(self):
        receipt = self.observe()
        wire = self.root / 'kernel/wire.jsonl'
        original = wire.read_bytes()
        with self.unavailable_host_tmp(receipt):
            result = final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True)
            self.assertEqual(result['roles_checked'], 6)
            self.assertTrue(result['historical_birth_identity_unavailable'])
            with wire.open('ab') as stream:
                stream.write(b'\n')
            with self.assertRaisesRegex(ValueError, 'snapshot drifted'):
                final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True)
            wire.write_bytes(original)
            with Path(receipt['path']).open('ab') as stream:
                stream.write(b' ')
            with self.assertRaisesRegex(ValueError, 'metadata/SHA'):
                final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True)

    def test_actual_prepare_workspace_shape_rejects_symlink_and_broad_arbitrary_paths(self):
        path = self.root / 'kernel/manifest.json'
        manifest = audit.load(path)
        self.assertTrue(Path(manifest['work']).parent.name.startswith('specpilot-codex-role-'))
        manifest['home'] = '/tmp'
        self.helper.write(path, manifest)
        with self.assertRaisesRegex(ValueError, 'common parent'):
            self.observe()

    def test_additional_coverage_registry_is_mandatory_closed_and_separately_bound(self):
        directory = self.root / 'coverage-review-01/processes'
        directory.mkdir(mode=0o700, parents=True)
        with self.assertRaisesRegex(ValueError, 'additional coverage-review'):
            self.observe()
        members = []
        for role in ('coverage-bootstrap', 'coverage-native-Master'):
            process = subprocess.Popen([sys.executable, '-B', '-c', 'import sys;sys.stdin.read()'], stdin=subprocess.PIPE)
            try:
                birth = final.record_birth(process, role, directory)
                process.stdin.close()
                ended = final.record_exit(process, birth, directory, timeout=10)
                members.append(dict(birth=birth, exit=ended))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        registry = final.close_registry(directory, members)
        receipt = self.observe(extra_shutdown_registries=[registry])
        result = final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True)
        self.assertEqual(result['roles_checked'], 6)
        self.assertEqual(result['additional_processes_checked'], 2)
        self.assertEqual(result['processes_checked'], 8)
        self.assertTrue(result['historical_birth_identity_unavailable'])
        with self.unavailable_host_tmp(receipt):
            self.assertEqual(final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(),
                maintenance_stock_control=True)['additional_processes_checked'], 2)
        with Path(members[0]['exit']['path']).open('ab') as stream:
            stream.write(b' ')
        with self.assertRaisesRegex(ValueError, 'metadata/SHA'):
            final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True)

    def test_any_old_pid_exists_rejects_without_birth_guessing(self):
        self.helper.result['role_processes']['master']['pid'] = os.getpid()
        self.helper.write(self.root / 'pipeline-result.json', self.helper.result)
        with self.assertRaisesRegex(ValueError, 'PID still exists'):
            self.observe()
        self.assertFalse((self.proof / 'legacy-shutdown.json').exists())

    def test_residual_session_process_rejects_even_when_all_old_pids_are_gone(self):
        manifest = audit.load(self.root / 'kernel/manifest.json')
        process = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(60)'],
            cwd=manifest['work'], env=dict(os.environ, CODEX_HOME=manifest['home']))
        try:
            with self.assertRaisesRegex(ValueError, 'workspace/session execution process remains'):
                self.observe()
        finally:
            process.terminate()
            process.wait(timeout=10)

    def test_missing_role_nonzero_exit_and_native_tamper_are_rejected(self):
        original = copy.deepcopy(self.helper.result)
        for change in ('missing', 'exit', 'native'):
            value = copy.deepcopy(original)
            if change == 'missing':
                value['role_processes'].pop('kernel')
            elif change == 'exit':
                value['role_processes']['kernel']['exit_code'] = -9
            else:
                path = self.root / 'kernel/turn-01-native.json'
                native = audit.load(path)
                native['turn']['status'] = 'failed'
                self.helper.write(path, native)
            self.helper.write(self.root / 'pipeline-result.json', value)
            with self.assertRaises(ValueError):
                self.observe()
        self.assertFalse((self.proof / 'legacy-shutdown.json').exists())

    def test_remote_checks_broker_uid_source_sha_and_original_native_binding(self):
        receipt = self.observe()
        kwargs = dict(broker_uid=os.geteuid(), maintenance_stock_control=True)
        self.assertEqual(final.validate_legacy_shutdown(receipt, **kwargs)['roles_checked'], 6)
        with self.assertRaisesRegex(ValueError, 'trusted producer UID'):
            final.validate_legacy_shutdown(receipt, **dict(kwargs, broker_uid=os.geteuid() + 1))
        changed = final.trusted_metadata(receipt, os.geteuid())
        changed['audit_sources']['harness/skill_rsi_audit.py'] = '0' * 64
        altered = _save(self.proof / 'changed-source.json', changed)
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            final.validate_legacy_shutdown(altered, **kwargs)
        with (self.root / 'kernel/wire.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'snapshot drifted'):
            final.validate_legacy_shutdown(receipt, **kwargs)

    def test_unknown_new_reservation_cannot_follow_frozen_snapshot(self):
        receipt = self.observe()
        state = audit.load(self.root / 'resource-state.json')
        state['jobs'].append(dict(name='phase4-controller-only-reservation', gpus=2, seconds=1000))
        self.helper.write(self.root / 'resource-state.json', state)
        with self.assertRaisesRegex(ValueError, 'explicitly bound current request'):
            final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(),
                maintenance_stock_control=True, check_current_host=True)

    def test_terminal_extension_and_current_bound_reservation_use_fixed_public_snapshot(self):
        before = {name: audit.sha(self.root / name) for name in ('pipeline-result.json', 'counters.json', 'feedback.json')}
        extension = self.helper.extension()
        public = extension / 'remote/error.json'
        self.helper.write(public, {'fixture': 'safe aggregate only'})
        private = extension / 'remote/private'
        private.mkdir(mode=0o700)
        (private / 'must-not-read.json').write_text('private fixture never needed by prefix observation')
        original_read = Path.read_bytes
        def shared_only(path):
            if path.is_relative_to(private):
                raise AssertionError('legacy observer must not read extension private evidence')
            return original_read(path)
        with patch.object(Path, 'read_bytes', shared_only):
            receipt = self.observe()
        value = final.trusted_metadata(receipt, os.geteuid())
        historical = final.trusted_metadata(value['historical_resource_state'], os.geteuid())
        frozen = final.trusted_metadata(value['resource_state'], os.geteuid())
        self.assertEqual(len(historical['jobs']), 3)
        self.assertEqual(len(frozen['jobs']), 4)
        self.assertIn(str(public), value['original_files'])
        pending = self.append_bound_reservation(receipt)
        with self.unavailable_host_tmp(receipt), patch.object(Path, 'read_bytes', shared_only):
            result = final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(),
                maintenance_stock_control=True, pending_request=pending)
        self.assertEqual(result['roles_checked'], 6)
        self.assertEqual(before, {name: audit.sha(self.root / name) for name in before})
        valid = audit.load(self.root / 'resource-state.json')
        changed = copy.deepcopy(valid)
        changed['jobs'].append(dict(changed['jobs'][-1], name='unknown-other-control'))
        self.helper.write(self.root / 'resource-state.json', changed)
        with self.assertRaisesRegex(ValueError, 'explicitly bound current request'):
            final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True, pending_request=pending)
        changed = copy.deepcopy(valid)
        changed['jobs'][0]['charged_gpu_seconds'] += 1
        self.helper.write(self.root / 'resource-state.json', changed)
        with self.assertRaisesRegex(ValueError, 'unchanged frozen observed prefix'):
            final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True, pending_request=pending)
        self.helper.write(self.root / 'resource-state.json', valid)
        self.helper.write(public, {'fixture': 'changed public evidence'})
        with self.assertRaisesRegex(ValueError, 'snapshot drifted'):
            final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True, pending_request=pending)

    def test_observation_rejects_active_or_unknown_controller_extensions(self):
        directory = self.helper.extension()
        state = audit.load(self.root / 'resource-state.json')
        state['jobs'][-1]['terminated'] = False
        self.helper.write(self.root / 'resource-state.json', state)
        with self.assertRaisesRegex(ValueError, 'active|uncertain'):
            self.observe()
        state['jobs'][-1]['terminated'] = True
        self.helper.write(self.root / 'resource-state.json', state)
        request = audit.load(directory / 'request.json')
        self.helper.refresh_extension_request(directory, dict(request, maintenance_stock_control=False))
        with self.assertRaisesRegex(ValueError, 'non-stock-control extension'):
            self.observe()

    def test_remote_scientific_route_rejects_legacy_before_loading_private_pool(self):
        receipt = self.observe()
        metadata = _save(self.proof / 'fixture-bundle.json', {})
        request = _save(self.proof / 'fixture-request.json', dict(protocol=resource.PROTOCOL, mode='phase4-controller',
            bundle_manifest=metadata, shutdown_registry=receipt, research_roots=[str(self.root / 'master')],
            broker_uid=os.geteuid(), maintenance_stock_control=False))
        output = self.root / 'remote-fixture'
        output.mkdir(mode=0o700)
        (output / 'private').mkdir(mode=0o700)
        with patch.object(resource, 'generate_indexes') as generate, self.assertRaisesRegex(ValueError, 'negative-control-only'):
            resource.remote(Path(request['path']), output)
        generate.assert_not_called()

    def test_remote_does_not_claim_proc_observation_of_another_host(self):
        receipt = self.observe()
        current = final.identity()
        with patch.object(final, 'identity', return_value=dict(current, host_boot_id='different-host')):
            self.assertEqual(final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(),
                maintenance_stock_control=True)['roles_checked'], 6)
            with self.assertRaisesRegex(ValueError, 'original broker host'):
                final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(),
                    maintenance_stock_control=True, check_current_host=True)

    def test_owner_permissions_and_private_uid_are_not_relaxed(self):
        receipt = self.observe()
        path = Path(receipt['path'])
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            final.validate_legacy_shutdown(receipt, broker_uid=os.geteuid(), maintenance_stock_control=True)
        with patch('controller.sealed_protocol.os.geteuid', return_value=os.geteuid() + 1):
            with self.assertRaisesRegex(ValueError, 'controller-owned'):
                _private(self.proof, directory=True)


class BirthReceiptTests(unittest.TestCase):
    def test_new_broker_records_actual_child_birth_and_wait_exit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = subprocess.Popen([sys.executable, '-B', '-c', 'import sys;sys.stdin.read()'], stdin=subprocess.PIPE)
            try:
                birth = final.record_birth(process, 'fixture-role', root)
                process.stdin.close()
                ended = final.record_exit(process, birth, root, timeout=10)
                registry = final.close_registry(root, [dict(birth=birth, exit=ended)])
                value = final.trusted_metadata(registry, os.geteuid())
                self.assertEqual(final.validate_shutdown(value, broker_uid=os.geteuid(), opened_unix=final.time.time()), 1)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main()
