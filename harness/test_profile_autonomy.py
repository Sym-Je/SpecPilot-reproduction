"""Engineering fixes 3/4/5 CPU acceptance, registered before implementation.

python -B -m unittest harness.test_profile_autonomy harness.test_profile_resource -v
Stage skill-tests/profile-engineering-fixes-345-red.log preserves the first failure.
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exp.skill_rsi import Campaign
from exp import profile_autonomy


class ProfileCampaignConfigurationTests(unittest.TestCase):
    def test_new_campaign_uses_its_own_limits_and_serial_gpu_scheduling(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / 'inputs.json'
            inputs.write_text('{}')
            limits = dict(gpu_seconds=28800, wall_seconds=43200, concurrent_gpus=2)
            with patch('exp.skill_rsi.subprocess.check_output', return_value='a' * 40):
                campaign = Campaign(root, inputs, inputs, limits=limits,
                                    job_prefix='sp-profile-fixture', max_workers=1)
            self.assertEqual(campaign.budget.read()['gpu_seconds'], 28800)
            self.assertEqual(campaign.job_prefix, 'sp-profile-fixture')
            self.assertEqual(campaign.max_workers, 1)
            before = (root / 'resource-state.json').read_bytes()
            with patch('exp.skill_rsi.subprocess.check_output'), self.assertRaises(ValueError):
                Campaign(root, inputs, inputs)
            self.assertEqual((root / 'resource-state.json').read_bytes(), before)

    def test_job_prefix_never_accepts_paths_or_unbounded_parallelism(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for arguments in (dict(job_prefix='../escape'), dict(max_workers=3)):
                with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                    Campaign(root, root / 'inputs.json', root / 'tools.json', **arguments)


class ProfileObservationProtocolTests(unittest.TestCase):
    def observation_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        campaign = profile_autonomy.ProfileCampaign.__new__(profile_autonomy.ProfileCampaign)
        campaign.root, campaign.job_prefix = root, 'profile-fixture'
        campaign.inputs, campaign.tools = root / 'stock.json', root / 'tools.json'
        campaign.capture_template = dict(fixture='trusted fixed template')
        campaign.profile_requests, campaign.profile_cache = [], {}
        campaign.profile_allocations = {'direction-fixture': 2}
        campaign.profile_evidence = {'direction-fixture': {'stock': campaign.inputs}, 'other': {'stock': campaign.inputs}}
        campaign.counters = dict(actions=0)
        campaign.budget = Mock()
        campaign.check_capacity = Mock()
        campaign.reserved_jobs = Mock(return_value=[])
        trace, config = root / 'trace.json', root / 'config.json'
        trace.write_text('{}')
        config.write_text('{}')
        manifest = dict(protocol='stock-profile-only-inputs-v1', scope='authorized-stock', workload=None,
            trace=profile_autonomy.reference(trace), config=profile_autonomy.reference(config))
        campaign.profile_executor = Mock(return_value=dict(status='completed', profile_inputs=[manifest], shape_status='unknown'))
        role_dir = root / 'direction-fixture'
        role_dir.mkdir()
        action = dict(kind='request_stock_profile', workload_id='gsm8k:0', preset='graph-128', reason='test hypothesis')
        (role_dir / 'turn-01-response.json').write_text(json.dumps(dict(action=action)))
        role = dict(directory=role_dir, actions=20, number=1, manifest=dict(role='direction'),
                    thread=dict(thread=dict(id='native-fixture-thread')))
        return campaign, role, action, manifest

    def test_profile_action_rejects_paths_flags_and_unknown_workloads(self):
        action = dict(kind='request_stock_profile', workload_id='gsm8k:0', preset='graph-128', reason='inspect actual work')
        self.assertEqual(profile_autonomy.profile_action(action)['workload_id'], 'gsm8k:0')
        for changed in (dict(action, path='/eval/sealed'), dict(action, workload_id='../secret'),
                        dict(action, server_flags=['--disable-cuda-graph'])):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                profile_autonomy.profile_action(changed)

    def test_actual_profile_feedback_preserves_the_original_research_task(self):
        campaign = profile_autonomy.ProfileCampaign.__new__(profile_autonomy.ProfileCampaign)
        request = dict(action=dict(kind='request_stock_profile', workload_id='gsm8k:0', preset='graph-128', reason='check'))
        conclusion = dict(action=dict(kind='finish'), reason='insufficient verified shapes')
        with patch.object(Campaign, 'model_response', side_effect=[request, conclusion]) as native, \
                patch.object(campaign, 'collect_profile', return_value=dict(status='completed', evidence_ids=['profile-01-00'])):
            result = campaign.model_response({}, 'ORIGINAL_TASK_SCHEMA', action_required=True)
        self.assertEqual(result, conclusion)
        feedback = native.call_args_list[1].args[1]
        self.assertIn('ORIGINAL_TASK_SCHEMA', feedback)
        self.assertIn('profile-01-00', feedback)
        self.assertIn('实际profile反馈', feedback)

    def test_invalid_profile_request_is_feedback_not_a_human_research_decision(self):
        campaign = profile_autonomy.ProfileCampaign.__new__(profile_autonomy.ProfileCampaign)
        request = dict(action=dict(kind='request_stock_profile', path='/forbidden'))
        conclusion = dict(action=dict(kind='finish'))
        with patch.object(Campaign, 'model_response', side_effect=[request, conclusion]) as native:
            self.assertEqual(campaign.model_response({}, 'TASK'), conclusion)
        self.assertIn('rejected', native.call_args_list[1].args[1])

    def test_old_phase_profile_cannot_be_claimed_as_current_preflight(self):
        campaign = profile_autonomy.ProfileCampaign.__new__(profile_autonomy.ProfileCampaign)
        campaign.root = Path('/new-stage')
        campaign.preflight = Path('/old-stage/profile')
        with self.assertRaisesRegex(ValueError, 'this new stage'):
            campaign.validate_preflight()

    def test_completed_profile_registers_only_the_requesting_roles_evidence_and_reuses_it(self):
        campaign, role, action, manifest = self.observation_fixture()
        with patch.object(profile_autonomy, 'prepare') as prepare:
            first = campaign.collect_profile(role, action)
            second = campaign.collect_profile(role, action)
        prepare.assert_called_once()
        campaign.profile_executor.assert_called_once()
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(first['evidence_ids'], second['evidence_ids'])
        identity = first['evidence_ids'][0]
        self.assertNotIn(identity, campaign.profile_evidence['other'])
        path = campaign.profile_evidence['direction-fixture'][identity]
        self.assertEqual(json.loads(path.read_text()), manifest)
        access = role['broker_factory'].keywords['dispatcher'].__self__
        self.assertIn(identity, access.evidence)
        self.assertEqual(campaign.counters['actions'], 1)

    def test_profile_failure_returns_real_feedback_without_registering_incomplete_evidence(self):
        campaign, role, action, _ = self.observation_fixture()
        campaign.profile_executor.return_value = dict(status='failed', error='native profile failure')
        with patch.object(profile_autonomy, 'prepare'):
            result = campaign.collect_profile(role, action)
        self.assertEqual(result['error'], 'native profile failure')
        self.assertEqual(set(campaign.profile_evidence['direction-fixture']), {'stock'})

    def test_master_role_gpu_limit_blocks_profile_before_submission(self):
        campaign, role, action, _ = self.observation_fixture()
        campaign.reserved_jobs.return_value = ['source-attempt', 'profile-attempt']
        with patch.object(profile_autonomy, 'prepare') as prepare, self.assertRaisesRegex(ValueError, 'Master-assigned'):
            campaign.collect_profile(role, action)
        prepare.assert_not_called()
        campaign.profile_executor.assert_not_called()

    def preflight_fixture(self):
        campaign, role, action, manifest = self.observation_fixture()
        campaign.preflight = campaign.root / 'selected-preflight'
        campaign.preflight.mkdir()
        campaign.budget.path = campaign.root / 'resource-state.json'
        campaign.budget.read.return_value = dict(jobs=[dict(name=campaign.preflight.name,
            terminated=True, terminal='Completed', submission_code=200)])
        (campaign.preflight / 'request.json').write_text(json.dumps(dict(
            budget_path=str(campaign.budget.path), role_binding=None)))
        campaign.inputs.write_text(json.dumps(manifest))
        result = dict(capture_completed=True, option_enabled=False, profile_inputs=[manifest])
        return campaign, manifest, result

    def test_initial_manifest_must_match_selected_preflight_profile_inputs(self):
        campaign, manifest, result = self.preflight_fixture()
        unrelated = campaign.root / 'unrelated-config.json'
        unrelated.write_text('{}')
        changed = dict(manifest, config=profile_autonomy.reference(unrelated))
        campaign.inputs.write_text(json.dumps(changed))
        with patch.object(profile_autonomy, 'feedback', return_value=result), \
                self.assertRaisesRegex(ValueError, 'selected.*preflight'):
            campaign.validate_preflight()

    def test_missing_preflight_profile_inputs_cannot_authorize_initial_manifest(self):
        campaign, manifest, result = self.preflight_fixture()
        for replacement in (None, []):
            changed = dict(result)
            if replacement is None:
                del changed['profile_inputs']
            else:
                changed['profile_inputs'] = replacement
            with self.subTest(replacement=replacement), patch.object(profile_autonomy, 'feedback', return_value=changed), \
                    self.assertRaises(ValueError):
                campaign.validate_preflight()

    def test_any_exact_manifest_in_selected_preflight_can_initialize_profile_only(self):
        campaign, manifest, result = self.preflight_fixture()
        result['profile_inputs'].insert(0, dict(manifest, scope='unrelated fixture'))
        before = campaign.inputs.read_bytes()
        with patch.object(profile_autonomy, 'feedback', return_value=result):
            campaign.validate_preflight()
        self.assertEqual(campaign.inputs.read_bytes(), before)
        self.assertIsNone(json.loads(before)['workload'])

    def test_prepare_validation_failure_does_not_charge_or_register_an_action(self):
        campaign, role, action, manifest = self.observation_fixture()
        before = (dict(campaign.counters), role['actions'])
        with patch.object(profile_autonomy, 'prepare', side_effect=ValueError('synthetic prepare validation failure')), \
                self.assertRaisesRegex(ValueError, 'prepare validation'):
            campaign.collect_profile(role, action)
        self.assertEqual((campaign.counters, role['actions']), before)
        self.assertEqual(campaign.profile_requests, [])
        self.assertEqual(campaign.profile_cache, {})
        self.assertFalse((campaign.root / 'profile-requests.json').exists())
        self.assertFalse((campaign.root / 'counters.json').exists())
        campaign.profile_executor.assert_not_called()

    def test_partial_prepare_failure_preserves_artifacts_without_phantom_action_charge(self):
        campaign, role, action, manifest = self.observation_fixture()
        def partial(directory, capture, budget, **options):
            directory.mkdir()
            (directory / 'source.tar').write_bytes(b'CPU fixture of a partial prepare, not an executable archive')
            raise ValueError('synthetic failure after creating evidence')
        with patch.object(profile_autonomy, 'prepare', side_effect=partial), self.assertRaises(ValueError):
            campaign.collect_profile(role, action)
        self.assertEqual(campaign.counters['actions'], 0)
        self.assertEqual(role['actions'], 20)
        self.assertEqual(campaign.profile_requests, [])
        self.assertTrue((campaign.root / 'profile-fixture-profile-01/source.tar').is_file())
        campaign.profile_executor.assert_not_called()

    def test_post_reservation_error_keeps_action_and_uncertain_budget_reservation(self):
        from harness.engine_research import Budget
        campaign, role, action, manifest = self.observation_fixture()
        campaign.budget = Budget(campaign.root / 'resource-state.json', limits=profile_autonomy.LIMITS)
        def uncertain(directory, budget):
            budget.reserve(directory.name, 1, 3900)
            budget.update(directory.name, create_calls=1)
            raise ValueError('synthetic post-reservation receipt failure')
        campaign.profile_executor.side_effect = uncertain
        with patch.object(profile_autonomy, 'prepare'), self.assertRaisesRegex(ValueError, 'post-reservation'):
            campaign.collect_profile(role, action)
        self.assertEqual(campaign.counters['actions'], 1)
        self.assertEqual(role['actions'], 19)
        self.assertEqual(len(campaign.profile_requests), 1)
        self.assertEqual(json.loads((campaign.root / 'counters.json').read_text())['actions'], 1)
        row = campaign.budget.read()['jobs'][0]
        self.assertFalse(row['terminated'])
        self.assertEqual(row['create_calls'], 1)
        self.assertNotIn('charged_gpu_seconds', row)
        campaign.profile_executor.assert_called_once()


if __name__ == '__main__':
    unittest.main()
