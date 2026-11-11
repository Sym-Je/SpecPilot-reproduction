"""Engineering fixes 3/4/5 acceptance: run both profile resource/autonomy modules.

CPU-only synthetic fixtures; output in stage skill-tests/profile-engineering-fixes-345-*.log.
"""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp import engine_resource
from harness.engine_research import Budget


class ProfileGpuAccountingTests(unittest.TestCase):
    def test_single_gpu_reservation_and_submission_are_not_charged_as_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'profile-fixture'
            directory.mkdir()
            (directory / 'request.json').write_text(json.dumps(dict(action=dict(per_suite=1))))
            source = directory / 'source.tar'
            source.write_bytes(b'fixture archive')
            budget = Budget(root / 'resource-state.json', limits=dict(
                gpu_seconds=28800, wall_seconds=43200, concurrent_gpus=2))
            command = ['cli', 'create', '--nnodes', '1', '--gpu-per-node', '1']
            created = SimpleNamespace(stdout='{"code":200}', stderr='', returncode=0)
            with patch.object(engine_resource, 'query', side_effect=[[], [dict(name='job-fixture')]]), \
                    patch.object(engine_resource.subprocess, 'run', return_value=created), \
                    patch.object(engine_resource, 'monitor', return_value=dict(status='completed')):
                result = engine_resource.execute(directory, source, budget, gpus=1, deadline=1200,
                    command_factory=lambda *args: command)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(budget.read()['jobs'][0]['gpus'], 1)
            pending = json.loads((directory / 'pending.json').read_text())
            self.assertEqual(pending['total_gpus'], 1)
            self.assertEqual(pending['gpu_per_node'], 1)

    def test_invalid_gpu_count_is_rejected_before_submission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(engine_resource, 'query') as query, self.assertRaises(ValueError):
                engine_resource.execute(root, root / 'source.tar', None, gpus=3)
            query.assert_not_called()


class ProfileResourceContractTests(unittest.TestCase):
    def template(self, gpus=1):
        return dict(spec=dict(priorityClassName='higher-priority-job', tasks=[dict(replicas=1,
            template=dict(spec=dict(containers=[dict(resources=dict(limits={'nvidia.com/gpu': str(gpus)}),
                volumeMounts=[])], volumes=[])))]))

    def test_single_card_template_preserves_readonly_model_mount_and_deadline(self):
        from exp.profile_resource import bounded_template
        original = self.template()
        result = bounded_template(original, 2700)
        pod = result['spec']['tasks'][0]['template']['spec']
        self.assertEqual(pod['activeDeadlineSeconds'], 2700)
        self.assertEqual(pod['containers'][0]['resources']['limits']['nvidia.com/gpu'], '1')
        self.assertTrue(any(mount['mountPath'] == '/gpfs/models' and mount['readOnly']
                            for mount in pod['containers'][0]['volumeMounts']))
        self.assertFalse(original['spec']['tasks'][0]['template']['spec']['volumes'])
        with self.assertRaises(ValueError):
            bounded_template(self.template(2), 2700)

    def test_cli_is_single_card_and_explicitly_uses_the_confirmed_image_and_priority(self):
        from exp.profile_resource import command
        from exp.gpu_autonomy import IMAGE
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, source = root / 'request.json', root / 'source.tar'
            request.write_text('{}')
            source.write_bytes(b'fixture archive')
            command_line = command(request, source, root / 'output', 'profile-fixture', 2700)
        self.assertEqual(command_line[command_line.index('--gpu-per-node') + 1], '1')
        self.assertEqual(command_line[command_line.index('--k8s-priority') + 1], '3')
        self.assertEqual(command_line[command_line.index('--k8s-images') + 1], IMAGE)
        self.assertEqual(command_line[command_line.index('--project') + 1], 'WeaverDev')


class ProfileResourceIndependentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def unit(self, label='unit'):
        from exp import profile_resource
        root = self.root / label
        root.mkdir()
        directory = root / 'profile-fixture'
        directory.mkdir(mode=0o700)
        source = directory / 'source.tar'
        source.write_bytes(b'non-sensitive fixture archive')
        budget = Budget(root / 'resource-state.json', limits=profile_resource.LIMITS)
        record = dict(protocol=profile_resource.PROTOCOL, mode='stock-profile',
            action=dict(per_suite=1), capture=dict(fixture='public CPU only'),
            gpus=1, deadline=profile_resource.DEADLINE, budget_path=str(budget.path))
        (directory / 'request.json').write_text(json.dumps(record))
        return directory, source, budget, record

    def terminal(self, *, gpus=None):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import Mock
        directory, source, budget, record = self.unit()
        count = 2 if gpus is None else gpus
        created = datetime(2026, 11, 11, tzinfo=timezone.utc)
        finished = created + timedelta(seconds=73.25)
        ended = SimpleNamespace(started_at=created, finished_at=finished, exit_code=1)
        pod = SimpleNamespace(metadata=SimpleNamespace(uid='pod-fixture', name='fixture-pod'),
            spec=SimpleNamespace(node_name='fixture-node'), status=SimpleNamespace(phase='Failed',
                container_statuses=[SimpleNamespace(restart_count=0,
                    state=SimpleNamespace(running=None, terminated=ended))]))
        container = dict(resources=dict(limits={'nvidia.com/gpu': str(count)}),
            image=engine_resource.IMAGE, volumeMounts=[dict(mountPath='/gpfs/models', readOnly=True)])
        job = dict(metadata=dict(creationTimestamp=created.isoformat()),
            spec=dict(tasks=[dict(template=dict(spec=dict(activeDeadlineSeconds=1200,
                containers=[container])))], maxRetry=0, queue='qiji'),
            status=dict(state=dict(phase='Aborted'), retryCount=0))
        pods_api = Mock()
        pods_api.list_namespaced_pod.return_value = SimpleNamespace(items=[pod])
        pods_api.read_namespaced_pod_log.return_value = 'CPU fixture terminal failure'
        jobs_api = Mock()
        jobs_api.get_namespaced_custom_object.return_value = job
        command = ['fixture-cli', 'create', '--nnodes', '1', '--gpu-per-node', str(count)]
        options = {} if gpus is None else dict(gpus=gpus)
        with patch.object(engine_resource, 'query', side_effect=[[], [dict(name='job-fixture')]]), \
                patch.object(engine_resource.subprocess, 'run', return_value=SimpleNamespace(
                    stdout='{"code":200}', stderr='', returncode=0)) as submit, \
                patch('kubernetes.config.load_kube_config'), \
                patch('kubernetes.client.CoreV1Api', return_value=pods_api), \
                patch('kubernetes.client.CustomObjectsApi', return_value=jobs_api):
            result = engine_resource.execute(directory, source, budget, deadline=1200,
                command_factory=lambda *arguments: command, **options)
        submit.assert_called_once()
        self.assertEqual(result['status'], 'failed')
        row = budget.read()['jobs'][0]
        self.assertTrue(row['terminated'])
        self.assertEqual(row['terminal'], 'Aborted')
        self.assertEqual(row['gpus'], count)
        lifecycle = json.loads((directory / 'lifecycle-final.json').read_text())
        self.assertEqual(lifecycle['conservative_gpu_seconds'], row['charged_gpu_seconds'])
        return row

    def test_one_card_terminal_charge_is_ceil_one_times_observed_duration(self):
        self.assertEqual(self.terminal(gpus=1)['charged_gpu_seconds'], 74)

    def test_default_two_card_terminal_charge_is_ceil_two_times_observed_duration(self):
        self.assertEqual(self.terminal()['charged_gpu_seconds'], 147)

    def test_failed_pod_does_not_stat_an_unpublished_root_owned_result(self):
        original = Path.exists
        def exists(path):
            if path.name == 'result.json':
                raise PermissionError('synthetic root-owned failed output')
            return original(path)
        with patch.object(Path, 'exists', exists):
            self.assertEqual(self.terminal(gpus=1)['charged_gpu_seconds'], 74)

    def test_cli_resource_drift_rejects_before_reservation_or_create(self):
        for nodes, cards in [('2', '1'), ('1', '2')]:
            with self.subTest(nodes=nodes, cards=cards):
                directory, source, budget, record = self.unit('drift-' + nodes + cards)
                command = ['fixture-cli', '--nnodes', nodes, '--gpu-per-node', cards]
                with patch.object(engine_resource, 'query', return_value=[]), \
                        patch.object(engine_resource.subprocess, 'run') as submit, \
                        self.assertRaisesRegex(ValueError, 'CLI resources'):
                    engine_resource.execute(directory, source, budget, gpus=1,
                        command_factory=lambda *arguments: command)
                submit.assert_not_called()
                self.assertEqual(budget.read()['jobs'], [])
                self.assertFalse((directory / 'pending.json').exists())

    def test_uncertain_submission_and_timeout_keep_reservation_and_never_recreate(self):
        cases = [('missing-job', '{"code":200}', [], False),
                 ('missing-code', '{"code":500}', [dict(name='job-fixture')], False),
                 ('bad-uuid', '{"code":200}', [dict(name='not-a-job')], False),
                 ('timeout', '', [], True)]
        for label, content, matches, timeout in cases:
            with self.subTest(case=label):
                directory, source, budget, record = self.unit(label)
                command = ['fixture-cli', '--nnodes', '1', '--gpu-per-node', '1']
                response = SimpleNamespace(stdout=content, stderr='', returncode=0)
                error = engine_resource.subprocess.TimeoutExpired(command, 120) if timeout else None
                with patch.object(engine_resource, 'query', side_effect=[[], matches, []]), \
                        patch.object(engine_resource.subprocess, 'run', return_value=response,
                                     side_effect=error) as submit:
                    with self.assertRaises(RuntimeError):
                        engine_resource.execute(directory, source, budget, gpus=1,
                            command_factory=lambda *arguments: command)
                    retained = budget.read()
                    with self.assertRaisesRegex(ValueError, 'already reserved'):
                        engine_resource.execute(directory, source, budget, gpus=1,
                            command_factory=lambda *arguments: command)
                    with self.assertRaises(FileNotFoundError):
                        engine_resource.execute(directory, source, budget, gpus=1, resume_only=True,
                            command_factory=lambda *arguments: command)
                submit.assert_called_once()
                self.assertEqual(budget.read(), retained)
                self.assertEqual(retained['jobs'][0]['create_calls'], 1)
                self.assertFalse(retained['jobs'][0]['terminated'])
                self.assertNotIn('charged_gpu_seconds', retained['jobs'][0])

    def test_existing_job_is_not_reserved_or_resubmitted(self):
        directory, source, budget, record = self.unit()
        with patch.object(engine_resource, 'query', return_value=[dict(name='job-fixture')]), \
                patch.object(engine_resource.subprocess, 'run') as submit, \
                self.assertRaisesRegex(RuntimeError, 'already exists'):
            engine_resource.execute(directory, source, budget, gpus=1,
                command_factory=lambda *arguments: ['fixture-cli'])
        submit.assert_not_called()
        self.assertEqual(budget.read()['jobs'], [])

    def test_resume_rejects_request_source_and_gpu_identity_replacement(self):
        for replacement in ('request', 'source', 'gpus'):
            with self.subTest(replacement=replacement):
                directory, source, budget, record = self.unit(replacement)
                pending = dict(total_gpus=1, request_sha256=engine_resource.digest(directory / 'request.json'),
                    source_sha256=engine_resource.digest(source))
                if replacement == 'request':
                    (directory / 'request.json').write_text(json.dumps(dict(record, extra='changed')))
                elif replacement == 'source':
                    source.write_bytes(b'replaced source')
                else:
                    pending['total_gpus'] = 2
                (directory / 'pending.json').write_text(json.dumps(pending))
                (directory / 'submitted.json').write_text(json.dumps(dict(uuid='job-fixture', code=200)))
                budget.reserve(directory.name, 1, 1200)
                budget.update(directory.name, uuid='job-fixture', create_calls=1, submission_code=200)
                before = budget.read()
                with patch.object(engine_resource, 'query', return_value=[dict(name='job-fixture')]), \
                        patch.object(engine_resource, 'monitor') as monitor, \
                        patch.object(engine_resource.subprocess, 'run') as submit, \
                        self.assertRaisesRegex(RuntimeError, 'resume identity/source'):
                    engine_resource.execute(directory, source, budget, gpus=1, resume_only=True,
                        command_factory=lambda *arguments: ['fixture-cli'])
                monitor.assert_not_called()
                submit.assert_not_called()
                self.assertEqual(budget.read(), before)

    def test_profile_plan_rejects_frozen_request_or_archive_replacement(self):
        from exp import profile_resource
        for replacement in ('request', 'source'):
            with self.subTest(replacement=replacement):
                directory, source, budget, record = self.unit(replacement)
                plan = dict(request=profile_resource.reference(directory / 'request.json'),
                    source=profile_resource.reference(source))
                (directory / 'plan.json').write_text(json.dumps(plan))
                if replacement == 'source':
                    source.write_bytes(b'replaced source')
                else:
                    (directory / 'request.json').write_text(json.dumps(dict(record, capture={'changed': True})))
                with patch.object(profile_resource, 'engine_execute') as execute, \
                        self.assertRaisesRegex(ValueError, 'plan drifted'):
                    profile_resource.execute(directory, budget)
                execute.assert_not_called()
                self.assertEqual(budget.read()['jobs'], [])

    def bound_output(self):
        from exp import profile_resource
        directory, source, budget, record = self.unit()
        output = directory / 'remote'
        output.mkdir(mode=0o700)
        (output / 'request.json').write_text(json.dumps(record['capture']))
        (output / 'result.json').write_text(json.dumps(dict(status='completed', controller_accepted=False)))
        binding = dict(request=profile_resource.reference(directory / 'request.json'),
            source=profile_resource.reference(source), capture=record['capture'],
            result_sha256=profile_resource.reference(output / 'result.json')['sha256'])
        (directory / 'resource-binding.json').write_text(json.dumps(binding))
        return output, record, binding

    def test_matching_binding_dispatches_independent_collector_audit(self):
        from exp import profile_resource
        output, record, binding = self.bound_output()
        verdict = dict(status='completed', controller_accepted=False)
        with patch('exp.profile_capture.audit', return_value=verdict) as audit:
            self.assertEqual(profile_resource.feedback(output, record), verdict)
        audit.assert_called_once_with(output)
        self.assertFalse((output / 'resource-binding.json').exists())

    def test_missing_host_transformers_uses_fixed_cpu_replay_without_new_gpu_work(self):
        from exp import profile_resource
        output, record, _ = self.bound_output()
        verdict = dict(status='completed', controller_accepted=False)
        with patch('exp.profile_capture.audit', side_effect=ModuleNotFoundError('fixture', name='transformers')), \
                patch.object(profile_resource, 'cpu_replay', return_value=verdict) as cpu:
            self.assertEqual(profile_resource.feedback(output, record), verdict)
        cpu.assert_called_once_with(output)

    def test_other_missing_modules_are_not_silently_replaced_by_cpu_replay(self):
        from exp import profile_resource
        output, record, _ = self.bound_output()
        with patch('exp.profile_capture.audit', side_effect=ModuleNotFoundError('fixture', name='unexpected')), \
                patch.object(profile_resource, 'cpu_replay') as cpu, self.assertRaises(ModuleNotFoundError):
            profile_resource.feedback(output, record)
        cpu.assert_not_called()

    def test_binding_request_source_capture_and_result_replacement_rejected(self):
        from exp import profile_resource
        output, record, binding = self.bound_output()
        for field in ('request', 'source', 'capture', 'result_sha256'):
            changed = json.loads(json.dumps(binding))
            if field in ('request', 'source'):
                changed[field]['sha256'] = '0' * 64
            elif field == 'capture':
                changed[field] = dict(replaced=True)
            else:
                changed[field] = '0' * 64
            (output.parent / 'resource-binding.json').write_text(json.dumps(changed))
            with self.subTest(field=field), patch('exp.profile_capture.audit', return_value={}), \
                    self.assertRaises(ValueError):
                profile_resource.feedback(output, record)

    def test_actual_collector_request_cannot_differ_from_outer_capture(self):
        from exp import profile_resource
        output, record, binding = self.bound_output()
        (output / 'request.json').write_text(json.dumps(dict(replaced=True)))
        with patch('exp.profile_capture.audit') as audit, self.assertRaisesRegex(ValueError, 'frozen resource'):
            profile_resource.feedback(output, record)
        audit.assert_not_called()


class ProfilePublicPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'public-profile'
        self.output.mkdir(mode=0o700)
        self.output.chmod(0o700)
        self.inputs = self.output / 'inputs'
        self.inputs.mkdir(mode=0o700)
        self.inputs.chmod(0o700)
        self.artifact = self.inputs / 'trace.json'
        self.artifact.write_text('{"fixture":"non-sensitive"}')
        self.artifact.chmod(0o600)
        self.outside = self.root / 'unrelated-private-fixture'
        self.outside.mkdir(mode=0o700)
        self.outside.chmod(0o700)
        self.sentinel = self.outside / 'sentinel.txt'
        self.sentinel.write_text('synthetic unrelated data')
        self.sentinel.chmod(0o600)

    def mode(self, path):
        import stat
        return stat.S_IMODE(path.stat().st_mode)

    def test_public_profile_gets_host_readable_modes_without_changing_private_neighbors(self):
        from exp.profile_resource import publish_evidence
        publish_evidence(self.output)
        self.assertEqual(self.mode(self.output), 0o755)
        self.assertEqual(self.mode(self.inputs), 0o755)
        self.assertEqual(self.mode(self.artifact), 0o644)
        self.assertEqual(self.mode(self.outside), 0o700)
        self.assertEqual(self.mode(self.sentinel), 0o600)

    def test_remote_publishes_collector_output_and_keeps_binding_outside_inventory(self):
        from exp import profile_resource
        source = self.root / 'source.tar'
        source.write_bytes(b'CPU-only source fixture')
        request = self.root / 'request.json'
        capture = dict(fixture='non-sensitive public profile')
        request.write_text(json.dumps(dict(protocol=profile_resource.PROTOCOL,
            mode='stock-profile', gpus=1, capture=capture)))
        def collect(record, output):
            self.assertEqual(record, capture)
            self.assertEqual(output, self.output)
            for name, value in [('result.json', dict(status='completed')), ('request.json', record)]:
                path = output / name
                path.write_text(json.dumps(value))
                path.chmod(0o600)
        with patch('exp.profile_capture.run', side_effect=collect) as run, \
                patch.dict(profile_resource.os.environ, {
                    'SP_PROFILE_SOURCE_SHA': profile_resource.reference(source)['sha256'],
                    'SP_PROFILE_REQUEST_SHA': profile_resource.reference(request)['sha256']}):
            profile_resource.remote(request, self.output)
        run.assert_called_once_with(capture, self.output)
        self.assertEqual(self.mode(self.output), 0o755)
        self.assertEqual(self.mode(self.artifact), 0o644)
        self.assertEqual(self.mode(self.output / 'result.json'), 0o644)
        binding = json.loads((self.root / 'resource-binding.json').read_text())
        self.assertEqual(binding['request'], profile_resource.reference(request))
        self.assertEqual(binding['source'], profile_resource.reference(source))
        self.assertEqual(binding['result_sha256'], profile_resource.reference(self.output / 'result.json')['sha256'])
        self.assertFalse((self.output / 'resource-binding.json').exists())
        self.assertEqual(self.mode(self.sentinel), 0o600)

    def test_failed_public_capture_retains_host_readable_partial_evidence_without_success_binding(self):
        from exp import profile_resource
        request = self.root / 'request.json'
        request.write_text(json.dumps(dict(protocol=profile_resource.PROTOCOL,
            mode='stock-profile', gpus=1, capture={})))
        with patch('exp.profile_capture.run', side_effect=ValueError('synthetic missing checkpoint index')):
            with self.assertRaisesRegex(ValueError, 'missing checkpoint'):
                profile_resource.remote(request, self.output)
        self.assertEqual(self.mode(self.output), 0o755)
        self.assertEqual(self.mode(self.artifact), 0o644)
        self.assertFalse((self.root / 'resource-binding.json').exists())

    def test_symlink_file_or_directory_rejects_before_any_permission_change(self):
        from exp.profile_resource import publish_evidence
        for target in (self.sentinel, self.outside):
            link = self.output / 'link'
            link.symlink_to(target, target_is_directory=target.is_dir())
            try:
                with self.subTest(target=target.name), self.assertRaises(ValueError):
                    publish_evidence(self.output)
                self.assertEqual(self.mode(self.output), 0o700)
                self.assertEqual(self.mode(self.artifact), 0o600)
                self.assertEqual(self.mode(self.sentinel), 0o600)
                self.assertEqual(self.mode(self.outside), 0o700)
            finally:
                link.unlink()

    def test_special_file_rejects_before_any_permission_change(self):
        import os
        from exp.profile_resource import publish_evidence
        os.mkfifo(self.output / 'fixture-fifo', 0o600)
        with self.assertRaises(ValueError):
            publish_evidence(self.output)
        self.assertEqual(self.mode(self.output), 0o700)
        self.assertEqual(self.mode(self.artifact), 0o600)

    def test_protected_path_components_never_publish(self):
        from exp.profile_resource import publish_evidence
        for name in ('private', 'sealed', '.git', '.config'):
            path = self.root / name
            path.mkdir(mode=0o700)
            path.chmod(0o700)
            with self.subTest(component=name), self.assertRaises(ValueError):
                publish_evidence(path)
            self.assertEqual(self.mode(path), 0o700)

    def test_symlink_ancestor_cannot_publish_an_unregistered_target(self):
        from exp.profile_resource import publish_evidence
        alias = self.root / 'alias'
        alias.symlink_to(self.outside, target_is_directory=True)
        output = self.outside / 'profile'
        output.mkdir(mode=0o700)
        output.chmod(0o700)
        artifact = output / 'fixture.txt'
        artifact.write_text('non-sensitive private-path fixture')
        artifact.chmod(0o600)
        with self.assertRaises(ValueError):
            publish_evidence(alias / 'profile')
        self.assertEqual(self.mode(output), 0o700)
        self.assertEqual(self.mode(artifact), 0o600)


class ProfileCpuReplayReadOnlyTests(unittest.TestCase):
    def setUp(self):
        import io
        import tarfile
        from exp import profile_resource
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'remote'
        self.output.mkdir()
        self.result = dict(status='completed', capture_completed=True, controller_accepted=False)
        (self.output / 'result.json').write_text(json.dumps(self.result))
        self.runtime = self.root / 'remote.runtime-source'
        self.runtime.mkdir()
        content = b'pass\n'
        name = 'exp/fixture.py'
        path = self.runtime / name
        path.parent.mkdir()
        path.write_bytes(content)
        archive = self.root / 'source.tar'
        with tarfile.open(archive, 'w') as destination:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            destination.addfile(member, io.BytesIO(content))
        (self.root / 'source-identity.json').write_text(json.dumps(dict(
            archive=profile_resource.reference(archive), files={name:profile_resource.reference(path)['sha256']})))
        self.receipt = self.root / 'host-cpu-audit-runtime.json'

    def replay(self, *, changed_worker=False):
        from exp import profile_resource
        original_reference = profile_resource.reference
        original_is_file = Path.is_file
        python = Path('/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python')
        worker = profile_resource.ROOT / 'harness/profile_cpu_audit.py'
        observed = []
        def reference(path):
            path = Path(path)
            if path == python or path == python.resolve():
                return dict(path=str(path), sha256='e' * 64)
            value = original_reference(path)
            if path == worker:
                observed.append(value)
                if changed_worker and len(observed) > 1:
                    value = dict(value, sha256='f' * 64)
            return value
        response = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps(dict(
            result=self.result, runtime=dict(python='synthetic CPU runtime', cuda_visible_devices=''))))
        with patch.object(profile_resource, 'reference', side_effect=reference), \
                patch.object(Path, 'is_file', lambda path: True if path == python else original_is_file(path)), \
                patch.object(profile_resource.subprocess, 'run', return_value=response) as execute:
            result = profile_resource.cpu_replay(self.output)
        execute.assert_called_once()
        options = execute.call_args.kwargs
        self.assertEqual(options['env']['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(options['env']['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertTrue(options['check'])
        self.assertEqual(len(observed), 2)
        return result

    def test_cpu_replay_does_not_overwrite_existing_runtime_receipt_or_other_evidence(self):
        from exp.profile_resource import reference
        self.receipt.write_text('{"original":"synthetic immutable receipt"}\n')
        before = {path:reference(path)['sha256'] for path in self.root.rglob('*') if path.is_file()}
        information = self.receipt.stat()
        self.assertEqual(self.replay(), self.result)
        after = {path:reference(path)['sha256'] for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(self.receipt.stat().st_ino, information.st_ino)
        self.assertEqual(self.receipt.stat().st_mtime_ns, information.st_mtime_ns)

    def test_cpu_replay_does_not_create_metadata_when_no_runtime_receipt_exists(self):
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.replay(), self.result)
        self.assertFalse(self.receipt.exists())

    def test_cpu_replay_still_rejects_changed_worker_without_writing_a_receipt(self):
        self.receipt.write_text('original synthetic receipt')
        before = self.receipt.read_bytes()
        with self.assertRaisesRegex(ValueError, 'worker changed'):
            self.replay(changed_worker=True)
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_cpu_replay_still_rejects_frozen_runtime_drift_before_running_worker(self):
        from exp import profile_resource
        (self.runtime / 'exp/fixture.py').write_text('changed')
        with patch.object(profile_resource.subprocess, 'run') as execute, \
                self.assertRaisesRegex(ValueError, 'runtime source changed'):
            profile_resource.cpu_replay(self.output)
        execute.assert_not_called()
        self.assertFalse(self.receipt.exists())


if __name__ == '__main__':
    unittest.main()
