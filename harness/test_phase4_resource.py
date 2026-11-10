from contextlib import nullcontext
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

from controller import sealed_cohort as cohort
from controller.http_transport import sha_ids
from controller.sealed_protocol import _save, freeze_candidate
from controller.scored_forcing import read_reference
from controller.stats import stratified_geomean_ci
from exp import phase4_resource as resource
from exp.phase4_run import execution_sources, reference
from harness.engine_research import Budget
from harness import test_source_candidate as source_tests
from harness.candidate import make_spec
from harness.source_candidate import build_bundle


class CohortTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('pool', 'dev', 'used', 'control', 'research'):
            (self.root / name).mkdir(mode=0o700)
        entries = []
        for number in range(8):
            request = dict(id=f'opaque-{number}', suite='a' if number < 4 else 'b', turn=0,
                           input_ids=[100, number], input_sha256=sha_ids([100, number]))
            source = _save(self.root / 'pool' / f'record-{number}.json', request)
            entries.append(dict(id=request['id'], suite=request['suite'], input_sha256=request['input_sha256'], request=source))
        self.entries = entries
        self.pool = _save(self.root / 'pool/index.json', dict(schema=cohort.INDEX, kind='pool',
                         prompt_protocol_sha256='a' * 64, entries=entries))
        self.dev = _save(self.root / 'dev/index.json', dict(schema=cohort.INDEX, kind='dev',
            prompt_protocol_sha256='a' * 64, entries=[{key: entry[key] for key in ('id', 'suite', 'input_sha256')}
                                                     for entry in (entries[0], entries[4])]))
        self.used = _save(self.root / 'used/index.json', dict(schema=cohort.INDEX, kind='used',
            prompt_protocol_sha256='a' * 64, entries=[{key: entries[1][key] for key in ('id', 'suite', 'input_sha256')}]))
        self.exclusions = cohort.build_exclusions(self.root / 'control/exclusions.json',
                                                  dev_indexes=[self.dev], used_indexes=[self.used])
        self.plan = cohort.plan_cohort(self.root / 'control/plan.json', pool_index=self.pool,
            exclusions=self.exclusions, counts={'a': 1, 'b': 1}, seed='registered-seed')

    def freeze(self, omit_hashes=False):
        return freeze_candidate(self.root / 'run', artifacts={'cohort_plan': self.plan['path']},
            arms=[dict(name=name, block=8, tree_sha=letter * 64, env={}) for name, letter in
                  (('stock', 'a'), ('candidate', 'b'))], launch_protocol={'model_path': '/fixture'},
            gpus=[dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0, 1)],
            seen_input_hashes=[] if omit_hashes else cohort.load_exclusions(self.exclusions)['input_hashes'],
            research_roots=[self.root / 'research'])

    def test_blind_selection_excludes_all_dev_and_used_and_replay_checks_originals(self):
        frozen = self.freeze()
        with patch.object(cohort, 'read_reference', wraps=read_reference) as reader:
            selection = cohort.select_cohort(frozen)
            self.assertTrue(all('record-' not in call.args[0]['path'] for call in reader.call_args_list))
        requests = cohort.materialize_cohort(frozen, selection)
        value = read_reference(requests, self.root)
        rejected = set(cohort.load_exclusions(self.exclusions)['input_hashes'])
        self.assertTrue(all(request['input_sha256'] not in rejected for request in value))
        self.assertEqual([request['id'] for request in value], ['phase4-000000', 'phase4-000001'])
        summary = cohort.verify_cohort(frozen, selection, requests)
        self.assertEqual(summary['excluded_records'], 3)
        self.assertEqual(summary['selected'], 2)
        self.assertNotIn('input_ids', json.dumps(summary))

    def test_omitted_dev_hashes_and_index_drift_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'omitted dev/used'):
            cohort.select_cohort(self.freeze(omit_hashes=True))

    def test_blind_selection_is_stable_across_private_directory_relocation(self):
        directory = self.root / 'different-job-private-pool'
        directory.mkdir(mode=0o700)
        entries = []
        for number, entry in enumerate(self.entries):
            request = read_reference(entry['request'], self.root)
            entries.append(dict(entry, request=_save(directory / f'copy-{number}.json', request)))
        relocated = _save(directory / 'index.json', dict(schema=cohort.INDEX, kind='pool',
                         prompt_protocol_sha256='a' * 64, entries=entries))
        plan = read_reference(self.plan, self.root)
        for number in range(12):
            left = dict(plan, seed=f'fixed-before-retry-{number}')
            right = dict(left, pool_index=relocated)
            before = cohort._choose(left)[0]
            after = cohort._choose(right)[0]
            with self.subTest(seed=left['seed']):
                self.assertEqual([{key: entry[key] for key in ('id', 'suite', 'input_sha256')} for entry in before],
                                 [{key: entry[key] for key in ('id', 'suite', 'input_sha256')} for entry in after])

    def test_empty_dev_and_inconsistent_prompt_protocol_are_rejected(self):
        with self.assertRaises(ValueError):
            cohort.build_exclusions(self.root / 'control/empty.json', dev_indexes=[])
        value = json.loads(Path(self.used['path']).read_text())
        value['prompt_protocol_sha256'] = 'b' * 64
        other = _save(self.root / 'used/other.json', value)
        with self.assertRaisesRegex(ValueError, 'protocols differ'):
            cohort.build_exclusions(self.root / 'control/bad.json', dev_indexes=[self.dev], used_indexes=[other])

    def test_insufficient_pool_and_request_substitution_fail_closed(self):
        value = json.loads(Path(self.plan['path']).read_text())
        value['counts'] = {'a': 99}
        Path(self.plan['path']).write_text(json.dumps(value))
        Path(self.plan['path']).chmod(0o600)
        self.plan = reference(self.plan['path'])
        with self.assertRaisesRegex(ValueError, 'insufficient unseen'):
            cohort.select_cohort(self.freeze())

    def test_selected_request_corruption_and_wide_permissions_are_rejected(self):
        frozen = self.freeze()
        selection = cohort.select_cohort(frozen)
        selected = read_reference(selection, self.root)['chosen'][0]
        path = Path(selected['request']['path'])
        original = path.read_bytes()
        path.write_text('{}')
        with self.assertRaises(ValueError): cohort.materialize_cohort(frozen, selection)
        path.write_bytes(original)
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only'): cohort.materialize_cohort(frozen, selection)

    def generated_fixture(self):
        from exp.p3_pair_run import SUITES
        model = self.root / 'model'
        model.mkdir()
        (model / 'tokenizer.json').write_text('{}')
        dev_sources = {}
        for suite in SUITES:
            path = self.root / 'dev' / f'{suite}.jsonl'
            path.write_text('\n'.join(json.dumps(dict(id=f'{suite}-{number}', turns=[f'old {suite} {number}']))
                                      for number in range(20)))
            dev_sources[suite] = reference(path)
        new_prompts = [hashlib.sha256(f'fixture-{number}'.encode()).hexdigest() for number in range(8)]
        used = _save(self.root / 'used/all.json', dict(requests=[dict(suite='gsm8k',
            input_sha256=sha_ids(list(new_prompts[0].encode())))]))
        spec = dict(source_catalog_sha256=cohort.source_catalog_sha256(), dev_sources=dev_sources,
            used_sources=[used], source_cache=None, pool_per_suite=8, counts={'gsm8k': 2}, seed='fixed-before-source-load')
        frozen = freeze_candidate(self.root / 'generated-freeze', artifacts={'source': self.plan['path']},
            arms=[dict(name=name, block=8, tree_sha=letter * 64, env={}) for name, letter in
                  (('stock', 'a'), ('candidate', 'b'))], launch_protocol={'model_path': str(model)},
            gpus=[dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0, 1)],
            seen_input_hashes=[], research_roots=[self.root / 'research'])
        class Tokenizer:
            def apply_chat_template(self, messages, **options):
                return list(messages[0]['content'].encode())
        def download(directory, cache=None):
            from exp.generalization_data import SOURCES, REVISIONS
            repo, filename, license_name = SOURCES['gsm8k']
            path = directory / 'fixture.jsonl'
            path.write_text('{}\n')
            return {(repo, filename): dict(path=str(path), repo=repo, filename=filename,
                        revision=REVISIONS[repo], sha256=reference(path)['sha256'])}
        rows = [dict(source_id=str(100 + number), prompt=prompt) for number, prompt in enumerate(new_prompts)]
        return frozen, spec, Tokenizer(), download, rows

    def test_root_job_generates_indexes_without_manual_private_pool(self):
        frozen, spec, tokenizer, download, rows = self.generated_fixture()
        with patch('exp.generalization_data.download_sources', download), patch('exp.generalization_data.source_rows', return_value=rows):
            value = cohort.generate_indexes(frozen, self.root / 'generated', spec, tokenizer=tokenizer)
        dev = read_reference(value['dev_indexes'][0], self.root)
        pool = read_reference(value['pool_index'], self.root)
        self.assertEqual(len(dev['entries']), 100)
        self.assertEqual(len(pool['entries']), 7)
        self.assertNotIn(sha_ids(list(rows[0]['prompt'].encode())), [entry['input_sha256'] for entry in pool['entries']])
        self.assertEqual(pool['source_catalog_sha256'], spec['source_catalog_sha256'])
        self.assertTrue(all('input_ids' not in entry for entry in dev['entries']))
        self.assertEqual(Path(value['pool_index']['path']).stat().st_mode & 0o777, 0o600)

    def test_generation_rejects_partial_original_dev_before_download(self):
        frozen, spec, tokenizer, download, rows = self.generated_fixture()
        path = Path(spec['dev_sources']['gsm8k']['path'])
        path.write_text(path.read_text().splitlines()[0])
        spec['dev_sources']['gsm8k'] = reference(path)
        with patch('exp.generalization_data.download_sources') as fetch, self.assertRaisesRegex(ValueError, '100 original'):
            cohort.generate_indexes(frozen, self.root / 'generated', spec, tokenizer=tokenizer)
        fetch.assert_not_called()

    def test_public_preparation_builds_cache_refs_without_access_to_private_tree(self):
        from exp.generalization_data import REVISIONS, SOURCES
        sources = [dict(repo=repo, filename=filename, revision=REVISIONS[repo], sha256='a' * 64)
                   for repo, filename in sorted({(repo, filename) for repo, filename, license_name in SOURCES.values()})]
        preparation = _save(self.root / 'control/public-preparation.json', dict(sources=sources, dataset_sha256='b' * 64))
        private = '/controller-only-do-not-stat/generalization-data'
        with patch.object(cohort, 'read_reference', wraps=read_reference) as reads:
            refs = cohort.cache_from_public(preparation, private, self.root / 'metadata-cache')
        self.assertEqual([call.args[0] for call in reads.call_args_list], [preparation])
        self.assertEqual(refs['used_sources'], [dict(path=private + '/dataset.json', sha256='b' * 64)])
        cache = read_reference(refs['source_cache'], self.root)
        self.assertEqual(len(cache), 9)
        self.assertTrue(all(item['path'].startswith(private + '/' + item['repo'].replace('/', '--') + '--') for item in cache))
        self.assertNotIn('input_ids', json.dumps(cache))

    def test_cached_pinned_sources_are_copied_and_sha_drift_rejected_without_network(self):
        from exp.generalization_data import REVISIONS, SOURCES, download_sources
        old = self.root / 'old-private-fixture'
        old.mkdir(mode=0o700)
        metadata = []
        for repo, filename in sorted({(repo, filename) for repo, filename, license_name in SOURCES.values()}):
            path = old / (repo.replace('/', '--') + '--' + Path(filename).name)
            path.write_bytes(b'non-sensitive fixture source only')
            metadata.append(dict(repo=repo, filename=filename, revision=REVISIONS[repo], sha256=reference(path)['sha256']))
        public = _save(self.root / 'control/cache-public.json', dict(sources=metadata, dataset_sha256='c' * 64))
        refs = cohort.cache_from_public(public, str(old), self.root / 'cache-metadata')
        target = self.root / 'downloads'
        target.mkdir(mode=0o700)
        with patch('requests.Session') as session:
            copied = download_sources(target, cache=Path(refs['source_cache']['path']).parent)
        session.assert_not_called()
        self.assertEqual(len(copied), 9)
        self.assertTrue(all(Path(item['path']).parent == target for item in copied.values()))
        Path(next(iter(copied.values()))['path']).unlink()
        original = next(old.iterdir())
        original.write_bytes(b'corrupted')
        with patch('requests.Session') as session, self.assertRaisesRegex(ValueError, 'cached pinned source changed'):
            download_sources(target, cache=Path(refs['source_cache']['path']).parent)
        session.assert_not_called()


class ResourceTests(unittest.TestCase):
    def setUp(self):
        helper = source_tests.SourceCandidateTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.root = helper.root
        target = self.root / 'target'
        target.mkdir()
        (target / 'config.json').write_text('{}')
        (target / 'model.safetensors.index.json').write_text('{}')
        base = make_spec(helper.stock, self.root / 'config.json', str(target), '/draft', 'a' * 40)
        self.bundle = self.root / 'bundle'
        build_bundle(base, helper.patch_path, self.bundle)
        self.budget = Budget(self.root / 'resource-state.json', limits=resource.LIMITS)
        self.registry = _save(self.root / 'registry.json', dict(schema='controller-research-process-registry-v1',
            host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), roles=[]))
        self.cohort = dict(pool_index={'path': '/controller-only/pool.json', 'sha256': 'a' * 64},
            dev_indexes=[{'path': '/controller-only/dev.json', 'sha256': 'b' * 64}], used_indexes=[],
            counts={'fixture': 1}, seed='fixed-before-reveal')
        self.job = self.root / 'phase4-fixture'

    def prepare(self, **options):
        def archive(directory):
            path = directory / 'source.tar'
            path.write_bytes(b'CPU fixture archive, never submitted')
            _save(directory / 'source-identity.json', dict(archive=reference(path)))
            return path
        with patch.object(resource, 'archive_source', archive):
            parameters = dict(dev_manifest={'path': '/controller-dev/manifest.json', 'sha256': 'd' * 64})
            parameters.update(options)
            return resource.prepare(self.job, bundle=self.bundle, cohort=self.cohort, shutdown_registry=self.registry,
                research_roots=[self.root / 'research'], budget=self.budget, **parameters)

    def test_prepare_only_generates_command_and_uses_existing_budget(self):
        value = self.prepare()
        self.assertFalse(value['submission_performed'])
        self.assertEqual(self.budget.read()['jobs'], [])
        plan = json.loads((self.job / 'plan.json').read_text())
        command = plan['command']
        self.assertEqual(command[command.index('--k8s-priority') + 1], '3')
        self.assertEqual(command[command.index('--gpu-per-node') + 1], '2')
        self.assertNotIn('--privileged', command)
        self.assertNotIn('input_ids', json.dumps(plan))

    def test_explicit_control_purpose_and_four_hour_ceiling_are_frozen(self):
        self.prepare(maintenance_stock_control=True, dev_manifest=None, deadline=14400)
        record = json.loads((self.job / 'request.json').read_text())
        self.assertEqual(record['purpose'], 'controller-negative-control')
        self.assertTrue(record['maintenance_stock_control'])
        self.assertEqual(record['deadline'], 14400)
        from harness.source_candidate import load_bundle
        identity = load_bundle(self.bundle)
        self.assertEqual(record['candidate_tree_sha'], identity['stock_tree_sha'])
        self.assertEqual(record['bundle_candidate_tree_sha'], identity['candidate_tree_sha'])
        self.assertNotEqual(record['candidate_tree_sha'], record['bundle_candidate_tree_sha'])
        self.assertEqual(self.budget.read()['jobs'], [])
        with self.assertRaisesRegex(ValueError, 'fixed deadline'):
            self.prepare(deadline=14401)
        with self.assertRaisesRegex(ValueError, 'immutable controller reference'):
            self.prepare(dev_manifest=None)

    def test_control_rejects_original_optimization_tree_as_measured_identity(self):
        self.prepare(maintenance_stock_control=True, dev_manifest=None)
        record = json.loads((self.job / 'request.json').read_text())
        self.assertEqual(resource._request_identity(record), record['candidate_tree_sha'])
        wrong = dict(record, candidate_tree_sha=record['bundle_candidate_tree_sha'])
        with self.assertRaisesRegex(ValueError, 'actual measured tree'):
            resource._request_identity(wrong)
        with self.assertRaisesRegex(ValueError, 'actual measured tree'):
            resource._request_identity(record, dict(purpose=record['purpose'], arms=[{}, dict(tree_sha='0' * 64)]))

    def test_extended_deadline_still_reserves_remaining_unique_budget(self):
        from harness.engine_research import save
        self.prepare(deadline=14400)
        state = self.budget.read()
        state['jobs'].append(dict(name='old-fixture', gpus=2, seconds=50000, terminated=True,
                                 charged_gpu_seconds=100000))
        save(self.budget.path, state)
        with patch('exp.engine_resource.query', return_value=[]), patch('exp.engine_resource.subprocess.run') as submit:
            with self.assertRaisesRegex(ValueError, 'budget would be exceeded'):
                resource.execute(self.job, self.job / 'source.tar', self.budget)
        submit.assert_not_called()

    def test_bounded_template_accepts_14400_without_privileged_or_pod_priority(self):
        template = dict(spec=dict(priorityClassName='higher-priority-job', tasks=[dict(replicas=1,
            template=dict(spec=dict(containers=[dict(resources=dict(limits={'nvidia.com/gpu': '2'}))])))]))
        result = resource.bounded_template(template, 14400)
        pod = result['spec']['tasks'][0]['template']['spec']
        self.assertEqual(pod['activeDeadlineSeconds'], 14400)
        self.assertNotIn('priorityClassName', pod)
        self.assertNotIn('securityContext', pod['containers'][0])
        with self.assertRaises(ValueError): resource.bounded_template(template, 14401)

    def test_execute_injects_same_budget_and_redacts_failure_logs(self):
        self.prepare()
        with patch('exp.engine_resource.execute', return_value=dict(status='failed', log_tail='PRIVATE REQUEST BODY')) as execute:
            result = resource.execute(self.job, self.job / 'source.tar', self.budget, resume_only=True)
        self.assertIs(execute.call_args.args[2], self.budget)
        self.assertTrue(execute.call_args.kwargs['resume_only'])
        self.assertNotIn('PRIVATE REQUEST BODY', json.dumps(result))
        self.assertFalse(result['t3_passed'])

    def test_active_research_or_changed_plan_prevents_resource_execution(self):
        self.prepare()
        current = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        registry = dict(schema='controller-research-process-registry-v1',
            host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            roles=[dict(role='fixture', pid=os.getpid(), start_ticks=int(current[19]))])
        active = _save(self.root / 'active-registry.json', registry)
        with self.assertRaisesRegex(ValueError, 'still present'): resource.research_stopped(active)
        value = json.loads((self.job / 'request.json').read_text())
        value['deadline'] = 3600
        (self.job / 'request.json').write_text(json.dumps(value))
        with patch('exp.engine_resource.execute') as execute, self.assertRaisesRegex(ValueError, 'predeclared resource plan'):
            resource.execute(self.job, self.job / 'source.tar', self.budget)
        execute.assert_not_called()

    def test_wrong_budget_path_or_limits_are_rejected(self):
        self.prepare()
        other = Budget(self.root / 'other-budget.json', limits=resource.LIMITS)
        with self.assertRaisesRegex(ValueError, 'unique stage Budget'):
            resource.execute(self.job, self.job / 'source.tar', other)
        wrong = Budget(self.root / 'wrong-budget.json')
        with self.assertRaisesRegex(ValueError, '32h'): resource.checked_budget(wrong, wrong.path)

    def test_priority_is_job_spec_not_pod_field(self):
        job = dict(spec=dict(priorityClassName='higher-priority-job', tasks=[dict(template=dict(spec=dict(
            containers=[dict(securityContext={})])))]))
        with patch('kubernetes.config.load_kube_config'), patch('kubernetes.client.CustomObjectsApi') as api:
            api.return_value.get_namespaced_custom_object.return_value = job
            self.assertEqual(resource._deployment('job-fixture')['priority_class'], 'higher-priority-job')
            job['spec']['priorityClassName'] = 'wrong'
            with self.assertRaises(ValueError): resource._deployment('job-fixture')

    def test_archive_includes_transitive_and_dynamic_sources_but_no_request_data(self):
        directory = self.root / 'archive'
        directory.mkdir(mode=0o700)
        path = resource.archive_source(directory)
        with tarfile.open(path) as archive:
            names = set(archive.getnames())
        for name in ('harness/source_cache.py', 'harness/experiment_executor.py', 'controller/landlock.py',
                     'controller/head_reference.py', 'controller/sealed_cohort.py', 'exp/phase4_remote.sh',
                     'harness/skill_rsi_audit.py', 'controller/phase4_final.py'):
            self.assertIn(name, names)
        self.assertTrue(set(execution_sources()).issubset(names))
        self.assertFalse(any(name.startswith(('eval/', 'logs/')) for name in names))

    def test_feedback_requires_terminal_and_forbids_nested_raw_data(self):
        self.prepare()
        output = self.job / 'remote'
        output.mkdir()
        record = json.loads((self.job / 'request.json').read_text())
        summary = dict(protocol=resource.PROTOCOL, request_sha256=reference(self.job / 'request.json')['sha256'],
            source_sha256=reference(self.job / 'source.tar')['sha256'], candidate_tree_sha=record['candidate_tree_sha'],
            cohort=dict(counts={'fixture': 1}, selected=1, pool_records=5, excluded_records=4, prompt_protocol_sha256='a' * 64),
            protocol_evidence_passed=True, scientific_ready=True, runtime_status='evidence-ready-awaiting-independent-final',
            judge_regression=dict(healthy_controls_passed=True, faulty_event_rejected=True,
                                  post2048_tokens=1024, injection_coverage_passed=True),
            purpose='scientific-candidate', execution_completed=True, protocol_verified=True,
            expected_rejection=False, correctness_passed=True, performance_passed=True,
            private_evidence_seal_sha256='e' * 64, private_replay_sha256='f' * 64,
            sealed_file_count=123, post_terminal_t3_finalizer_executed=False,
            caps=[dict(cap=cap, interval=stratified_geomean_ci({'fixture': [.1]}), threshold=.01, noise=0,
                       correctness_passed=True) for cap in (2048, 4096)],
            t3_passed=False, promoted=False, ledger_eligible=False, controller_accepted=False)
        def write(value):
            (output / 'replay-summary.json').write_text(json.dumps(value))
            (output / 'result.json').write_text(json.dumps(dict(value, recompute_sha256=reference(output / 'replay-summary.json')['sha256'])))
        write(summary)
        with self.assertRaises(FileNotFoundError): resource.feedback(output, record)
        (self.job / 'lifecycle-final.json').write_text(json.dumps(dict(uuid='job-fixture', phase='Completed', pods={
            'pod-uid': dict(phase='Succeeded', exit_code=0, restarts=0, finished_at='2026-11-10T00:00:00Z')})))
        self.assertFalse(resource.feedback(output, record)['t3_passed'])
        summary['cohort']['input_ids'] = [1, 2]
        write(summary)
        with self.assertRaisesRegex(ValueError, 'aggregate'): resource.feedback(output, record)

    def test_judge_aggregate_never_exports_private_trace_or_request_fields(self):
        verdicts = {name: dict(correctness_passed=True, request_id='PRIVATE', raw_evidence='PRIVATE')
                    for name in ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head')}
        verdicts['faulty'] = dict(correctness_passed=False, event_flagged=True, raw_evidence='PRIVATE')
        result = resource.judge_aggregate(dict(verdicts=verdicts, post2048_tokens=1234))
        self.assertEqual(result, dict(healthy_controls_passed=True, faulty_event_rejected=True,
                                     post2048_tokens=1234, injection_coverage_passed=True))
        self.assertNotIn('PRIVATE', json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'aggregate'):
            resource.checked_judge_aggregate(dict(result, raw_evidence='PRIVATE'))
        with self.assertRaisesRegex(ValueError, 'coverage'):
            resource.checked_judge_aggregate(dict(result, post2048_tokens=100))

    def test_job_local_replay_seals_closed_evidence_not_live_logs_and_never_t3(self):
        from controller.phase4_final import identity
        private = self.root / 'private-replay'
        private.mkdir(mode=0o700)
        producer = dict(identity(), pid=99999999)
        _save(private / 'execution.json', dict(controller_identity=producer))
        evidence = _save(private / 'fixture-evidence.json', dict(non_sensitive_fixture=[1, 2, 3]))
        (private / 'controller.log').write_text('not exported, may still be open')
        (private / 'replay.log').write_text('live child log')
        summary = dict(t3_passed=False, promoted=False, ledger_eligible=False, execution_completed=True,
                       expected_rejection=True, performance_passed=False)
        with patch.object(resource, 'replay_private', return_value=summary) as replayer:
            seal = resource.write_private_replay(private)
        replayer.assert_called_once_with(private)
        sealed = read_reference(seal, self.root)
        self.assertEqual(sealed['files']['fixture-evidence.json'], evidence['sha256'])
        self.assertEqual(sealed['files']['recomputed.json'], reference(private / 'recomputed.json')['sha256'])
        self.assertNotIn('controller.log', sealed['files'])
        self.assertNotIn('replay.log', sealed['files'])
        self.assertNotIn('job-evidence-seal.json', sealed['files'])
        self.assertFalse(sealed['post_terminal_t3_finalizer_executed'])
        self.assertFalse(sealed['t3_passed'])
        self.assertEqual(sealed['replay_identity']['uid'], os.geteuid())
        with self.assertRaises(FileExistsError): resource.write_private_replay(private)

    def test_job_local_replay_rejects_same_process_or_different_controller_uid(self):
        from controller.phase4_final import identity
        private = self.root / 'invalid-replay'
        private.mkdir(mode=0o700)
        path = private / 'execution.json'
        _save(path, dict(controller_identity=identity()))
        with patch.object(resource, 'replay_private') as replayer, self.assertRaisesRegex(ValueError, 'independent process'):
            resource.write_private_replay(private)
        replayer.assert_not_called()
        path.unlink()
        _save(path, dict(controller_identity=dict(identity(), uid=os.geteuid() + 1)))
        with self.assertRaisesRegex(ValueError, 'original controller UID'):
            resource.write_private_replay(private)

    def test_root_error_exports_only_code_frames_and_sha_not_exception_text(self):
        from controller.phase4_final import identity
        self.prepare(maintenance_stock_control=True, dev_manifest=None)
        output = self.job / 'remote'
        output.mkdir(mode=0o755)
        private = output / 'private'
        private.mkdir(mode=0o700)
        _save(private / 'execution.json', dict(controller_identity=dict(identity(), pid=99999999)))
        secret = 'PRIVATE_REQUEST_BODY_REQUEST_ID_OUTPUT_/controller/private/data'
        with patch.dict(os.environ, SP_PHASE4_SOURCE_SHA=reference(self.job / 'source.tar')['sha256']), \
                patch.object(resource, 'replay_private', side_effect=ValueError(secret)):
            try:
                resource.write_private_replay(private)
            except ValueError as error:
                report = resource.publish_safe_error(self.job / 'request.json', output, error)
        public = resource.safe_error_feedback(output)
        self.assertEqual(public['error_type'], 'ValueError')
        self.assertNotIn(secret, Path(report['path']).read_text())
        self.assertTrue(any(frame['file'] == 'exp/phase4_resource.py' for frame in public['frames']))
        self.assertEqual(public['private_trace_sha256'], reference(private / 'error-trace.json')['sha256'])
        self.assertIn(secret, (private / 'error-trace.json').read_text())
        self.assertEqual((private / 'error-trace.json').stat().st_mode & 0o777, 0o600)
        record = json.loads((self.job / 'request.json').read_text())
        with patch('exp.engine_resource.execute', return_value=dict(status='failed', log_tail=secret)):
            result = resource.execute(self.job, self.job / 'source.tar', self.budget, resume_only=True)
        self.assertEqual(result['safe_error'], public)
        self.assertNotIn(secret, json.dumps(result))
        public['frames'][0]['file'] = '/controller/private/request.json'
        (output / 'error.json').write_text(json.dumps(public))
        with self.assertRaisesRegex(ValueError, 'safe code frame'):
            resource.safe_error_feedback(output)


class JudgeAggregateIndependentTests(unittest.TestCase):
    """Preregistered independent CPU acceptance, before adding test methods:

    python -B -m unittest
    harness.test_phase4_resource.JudgeAggregateIndependentTests -v
    Log: logs/skills-rsi-20261110-b01/controller-tests/judge-aggregate-independent-first.log
    Non-sensitive temporary fixtures only; no model/GPU or existing fixture changes.
    Reject missing/extra fields, invalid types, coverage/readiness inconsistency,
    and wire/replay tampering; preserve false outcomes without scientific promotion.
    """

    def aggregate(self, **changes):
        return dict(dict(healthy_controls_passed=True, faulty_event_rejected=True,
                         post2048_tokens=1024, injection_coverage_passed=True), **changes)

    def summary(self):
        return dict(protocol=resource.PROTOCOL, request_sha256='a' * 64, source_sha256='b' * 64,
            candidate_tree_sha='c' * 64, purpose='controller-negative-control',
            cohort=dict(counts={'fixture': 1}, selected=1, pool_records=5, excluded_records=4,
                        prompt_protocol_sha256='d' * 64),
            protocol_evidence_passed=False, scientific_ready=True, execution_completed=True,
            runtime_status='maintenance-stock-control-complete', protocol_verified=True,
            expected_rejection=True, correctness_passed=True, performance_passed=False,
            judge_regression=self.aggregate(), private_evidence_seal_sha256='e' * 64,
            private_replay_sha256='f' * 64, sealed_file_count=10, post_terminal_t3_finalizer_executed=False,
            caps=[dict(cap=cap, interval=stratified_geomean_ci({'fixture': [1.0]}), threshold=.01,
                       noise=0, correctness_passed=True) for cap in (2048, 4096)],
            t3_passed=False, promoted=False, ledger_eligible=False, controller_accepted=False)

    def test_exact_four_fields_and_missing_or_additional_fields(self):
        valid = self.aggregate()
        self.assertEqual(resource.checked_judge_aggregate(valid), valid)
        for key in valid:
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError, 'aggregate'):
                resource.checked_judge_aggregate({name:value for name, value in valid.items() if name != key})
        for key in ('request_id', 'input_ids', 'output_ids', 'raw_evidence', 'verdicts', 'extra'):
            with self.subTest(extra=key), self.assertRaisesRegex(ValueError, 'aggregate'):
                resource.checked_judge_aggregate(dict(valid, **{key:'SYNTHETIC_PRIVATE_MARKER'}))
        for value in (None, [], 'true', 1):
            with self.subTest(container=value), self.assertRaisesRegex(ValueError, 'aggregate'):
                resource.checked_judge_aggregate(value)

    def test_boolean_flags_reject_numeric_string_and_container_coercion(self):
        for key in ('healthy_controls_passed', 'faulty_event_rejected', 'injection_coverage_passed'):
            for value in (0, 1, 1.0, 'true', 'false', None, [], {}):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'aggregate'):
                    resource.checked_judge_aggregate(self.aggregate(**{key:value}))

    def test_post2048_count_is_nonnegative_integer_not_boolean(self):
        for value in (-1, True, False, 1024.0, '1024', None, [], float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'aggregate'):
                resource.checked_judge_aggregate(self.aggregate(post2048_tokens=value))

    def test_coverage_boundary_cannot_be_forged_in_either_direction(self):
        for count in (0, 1, 1023, 1024, 2048):
            expected = count >= 1024
            value = self.aggregate(post2048_tokens=count, injection_coverage_passed=expected)
            with self.subTest(count=count):
                self.assertEqual(resource.checked_judge_aggregate(value), value)
                with self.assertRaisesRegex(ValueError, 'coverage'):
                    resource.checked_judge_aggregate(dict(value, injection_coverage_passed=not expected))

    def test_summary_readiness_is_exact_conjunction_not_an_independent_bool(self):
        for healthy in (False, True):
            for faulty in (False, True):
                for covered in (False, True):
                    summary = self.summary()
                    summary['judge_regression'] = self.aggregate(healthy_controls_passed=healthy,
                        faulty_event_rejected=faulty, post2048_tokens=1024 if covered else 1023,
                        injection_coverage_passed=covered)
                    summary['scientific_ready'] = healthy and faulty and covered
                    with self.subTest(healthy=healthy, faulty=faulty, covered=covered):
                        resource._aggregate(summary, {'fixture': 1})
                        summary['scientific_ready'] = not summary['scientific_ready']
                        with self.assertRaisesRegex(ValueError, 'readiness differs'):
                            resource._aggregate(summary, {'fixture': 1})

    def test_export_requires_every_healthy_control_and_real_fault_rejection(self):
        verdicts = {name:dict(correctness_passed=True) for name in
                    ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head')}
        verdicts['faulty'] = dict(event_flagged=True, correctness_passed=False)
        for name in ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head'):
            changed = copy.deepcopy(verdicts)
            changed[name]['correctness_passed'] = False
            with self.subTest(unhealthy=name):
                self.assertFalse(resource.judge_aggregate(dict(verdicts=changed, post2048_tokens=1024))['healthy_controls_passed'])
        for flagged, passed in ((False, False), (False, True), (True, True), (True, False)):
            changed = copy.deepcopy(verdicts)
            changed['faulty'] = dict(event_flagged=flagged, correctness_passed=passed)
            with self.subTest(event=flagged, correct=passed):
                actual = resource.judge_aggregate(dict(verdicts=changed, post2048_tokens=1024))
                self.assertEqual(actual['faulty_event_rejected'], flagged and not passed)

    def test_summary_rejects_nested_raw_fields_and_ill_typed_readiness(self):
        for value in (dict(self.aggregate(), raw_evidence='SYNTHETIC_PRIVATE_MARKER'),
                      self.aggregate(healthy_controls_passed=1), self.aggregate(post2048_tokens=True)):
            summary = self.summary()
            summary['judge_regression'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'aggregate'):
                resource._aggregate(summary, {'fixture': 1})
        for value in (0, 1, 'true', None):
            summary = self.summary()
            summary['scientific_ready'] = value
            with self.subTest(readiness=value), self.assertRaises(ValueError):
                resource._aggregate(summary, {'fixture': 1})

    def test_feedback_rejects_tampering_even_when_public_replay_is_rehashed(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        output = directory / 'remote'
        output.mkdir()
        (directory / 'request.json').write_text('{"fixture":true}')
        (directory / 'source.tar').write_bytes(b'non-sensitive hash fixture; never executed')
        (directory / 'lifecycle-final.json').write_text(json.dumps(dict(uuid='job-fixture', phase='Completed',
            pods={'fixture':dict(phase='Succeeded', exit_code=0, restarts=0, finished_at='2026-11-10T00:00:00Z')})))
        summary = self.summary()
        summary.update(request_sha256=reference(directory / 'request.json')['sha256'],
                       source_sha256=reference(directory / 'source.tar')['sha256'])
        record = dict(candidate_tree_sha=summary['candidate_tree_sha'], purpose=summary['purpose'],
                      cohort={'counts': {'fixture': 1}})
        def write(value):
            (output / 'replay-summary.json').write_text(json.dumps(value))
            (output / 'result.json').write_text(json.dumps(dict(value,
                recompute_sha256=reference(output / 'replay-summary.json')['sha256'])))
        write(summary)
        self.assertFalse(resource.feedback(output, record)['t3_passed'])
        changed = json.loads((output / 'result.json').read_text())
        changed['judge_regression']['healthy_controls_passed'] = False
        (output / 'result.json').write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'trusted request/source/recompute'):
            resource.feedback(output, record)
        for regression in (self.aggregate(healthy_controls_passed=False),
                           self.aggregate(faulty_event_rejected=False), self.aggregate(post2048_tokens=1023),
                           dict(self.aggregate(), input_ids=[1, 2])):
            with self.subTest(regression=regression):
                write(dict(summary, judge_regression=regression))
                with self.assertRaisesRegex(ValueError, 'aggregate|readiness|coverage'):
                    resource.feedback(output, record)

    def test_export_does_not_mutate_or_forward_private_verdict_payload(self):
        verdicts = {name:dict(correctness_passed=True, request_id='SYNTHETIC_PRIVATE_MARKER', output_ids=[17, 18])
                    for name in ('healthy_stock', 'ar', 'healthy_segmented', 'equivalent_head')}
        verdicts['faulty'] = dict(event_flagged=True, correctness_passed=False, raw_evidence='SYNTHETIC_PRIVATE_MARKER')
        science = dict(verdicts=verdicts, post2048_tokens=2048, input_ids=[11, 12])
        before = copy.deepcopy(science)
        result = resource.judge_aggregate(science)
        self.assertEqual(science, before)
        self.assertEqual(set(result), set(self.aggregate()))
        self.assertNotIn('SYNTHETIC_PRIVATE_MARKER', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
