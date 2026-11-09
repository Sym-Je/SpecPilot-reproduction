import copy
from contextlib import ExitStack,nullcontext
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class HistoryCollectionTests(unittest.TestCase):
    def test_cpu_lifecycle_drives_both_fresh_rounds_and_all_progress_events(self):
        from exp.history_collect import run
        from exp.diagnosis import digest
        gpu=dict(index=0,uuid='fixture-gpu')
        with tempfile.TemporaryDirectory() as name,ExitStack() as stack:
            root=Path(name)/'private'
            public=Path(name)/'public'
            root.mkdir();public.mkdir()
            requests=self.pool()[:2]+self.pool()[6:8]
            manifest=dict(source_pin='fixture-pin',stock_spec=dict(target='fixture-target',draft='fixture-draft'),
                arm=dict(tree_sha='fixture-tree'),requests=requests,port=30240)
            (root/'manifest.json').write_text(json.dumps(manifest))
            stack.enter_context(patch.dict(os.environ,HISTORY_MANIFEST_SHA256=digest(root/'manifest.json')))
            overrides=dict(check_sources=None,clean_environment={},wait_for_idle=[gpu],check_ports=None,
                result_row=dict(fixture=True),audit=(dict(disposition='fixture-only'),dict(fixture=True)))
            for function,result in overrides.items():stack.enter_context(patch('exp.history_collect.'+function,return_value=result))
            stack.enter_context(patch('exp.history_collect.subprocess.check_output',return_value='fixture-pin'))
            stack.enter_context(patch('exp.history_collect.gpu_lock',return_value=nullcontext()))
            server=stack.enter_context(patch('exp.history_collect.ObservationServer'))
            client=stack.enter_context(patch('exp.history_collect.CapturedArm'))
            run(root,public)
            self.assertEqual(server.call_count,2)
            self.assertEqual(server.return_value.stop.call_count,2)
            self.assertEqual(client.return_value.step.call_count,18)
            events=[json.loads(line) for line in (public/'events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(row['phase']=='request-complete' for row in events),18)
            self.assertEqual(sum(row['phase']=='round-complete' for row in events),2)
            self.assertEqual(events[-1]['phase'],'gpu-work-complete')

    def pool(self):
        from controller.http_transport import sha_ids
        return [dict(id=f'{suite}-{index}',suite=suite,turn=0,input_ids=[index+offset],
            input_sha256=sha_ids([index+offset]),source_sha256=str(index+offset))
            for suite,offset in (('gsm8k',0),('humaneval',10)) for index in range(6)]

    def test_selection_is_frozen_and_independent_of_input_order(self):
        from exp.history_collect import select_requests
        pool=self.pool()
        selected=select_requests(pool,pool[:1])
        self.assertEqual(selected,select_requests(list(reversed(pool)),pool[:1]))
        self.assertEqual(len(selected),4)
        self.assertEqual({row['suite'] for row in selected},{'gsm8k','humaneval'})
        self.assertNotIn(pool[0],selected)

    def test_alias_and_normalized_source_duplicate_never_add_independence(self):
        from exp.history_collect import select_requests
        pool=self.pool()
        from controller.http_transport import sha_ids
        duplicate=dict(pool[0],id='alias',input_ids=[99],input_sha256=sha_ids([99]))
        selected=select_requests(pool+[duplicate],pool[:1])
        self.assertTrue(all(row['source_sha256']!=pool[0]['source_sha256'] for row in selected))

    def test_input_hash_tampering_and_short_pool_are_rejected(self):
        from exp.history_collect import select_requests
        pool=self.pool()
        pool[0]['input_sha256']='wrong'
        with self.assertRaises(ValueError):select_requests(pool,[])
        with self.assertRaises(ValueError):select_requests(self.pool()[:6],[])

    def observations(self):
        sequences=([0,0,1,0],[7,7,6,7],[3,3,3,4],[4,4,4,3])
        return dict(requests=[dict(request_group=f'probe-{index}',suite='gsm8k' if index<2 else 'humaneval',
            rounds=[dict(round=number,accepted_counts=list(sequence)) for number in (1,2)])
            for index,sequence in enumerate(sequences)])

    def test_screen_keeps_physical_repeats_together_and_has_no_speedup(self):
        from exp.history_collect import screen
        result=screen(self.observations())
        self.assertEqual(result['independent_requests'],4)
        self.assertEqual(result['physical_repeats_per_request'],2)
        self.assertIsNone(result['end_to_end_gain'])
        self.assertFalse(result['population_generalization_established'])
        self.assertTrue(all(not row['suite_fallback_to_global'] for row in result['per_request']))

    def test_test_request_never_fits_its_own_baseline(self):
        from exp.history_collect import screen
        values=self.observations()
        before=screen(values)['per_request'][0]['training_constants']
        for row in values['requests'][0]['rounds']:row['accepted_counts']=[7,6,7,6]
        self.assertEqual(before,screen(values)['per_request'][0]['training_constants'])

    def test_repeat_drift_and_insufficient_confirmation_are_rejected(self):
        from exp.history_collect import screen
        values=self.observations()
        values['requests'][0]['rounds'][1]['accepted_counts'][0]=2
        with self.assertRaises(ValueError):screen(values)
        values=self.observations()
        values['requests'].pop()
        with self.assertRaises(ValueError):screen(values)

    def test_ties_fail_the_fixed_strict_screen_without_rewriting_rules(self):
        from exp.history_collect import screen
        values=self.observations()
        for request in values['requests']:
            for row in request['rounds']:row['accepted_counts']=[3,3,3,3]
        result=screen(values)
        self.assertFalse(result['fixed_rule_screen_passed'])
        self.assertIsNone(result['end_to_end_gain'])

    def test_manifest_identity_is_checked_before_opening_any_private_generation(self):
        from exp.history_collect import audit,run
        with tempfile.TemporaryDirectory() as name,patch.dict(os.environ,HISTORY_MANIFEST_SHA256='wrong'):
            root=Path(name)
            (root/'manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'manifest identity'):audit(root)
            with self.assertRaisesRegex(ValueError,'selection identity'):run(root,root)

    def template(self):
        return dict(spec=dict(tasks=[dict(replicas=1,template=dict(spec=dict(
            containers=[dict(resources=dict(limits={'nvidia.com/gpu':1}),volumeMounts=[])],volumes=[])))]))

    def test_mount_is_readonly_and_budget_has_hard_deadline_no_retry(self):
        from exp.history_northjob import with_model_mount
        original=self.template()
        updated=with_model_mount(original)
        self.assertEqual(original,self.template())
        self.assertEqual(updated['spec']['maxRetry'],0)
        self.assertEqual(updated['spec']['policies'],[dict(events=['PodEvicted','PodFailed'],action='AbortJob')])
        pod=updated['spec']['tasks'][0]['template']['spec']
        self.assertEqual(pod['activeDeadlineSeconds'],1560)
        self.assertTrue(pod['containers'][0]['volumeMounts'][0]['readOnly'])
        self.assertTrue(pod['volumes'][0]['persistentVolumeClaim']['readOnly'])

    def test_adapter_rejects_extra_resources_and_duplicate_mount(self):
        from exp.history_northjob import with_model_mount
        for mutate in (lambda value:value['spec']['tasks'][0].update(replicas=2),
                lambda value:value['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['limits'].update({'nvidia.com/gpu':2}),
                lambda value:value['spec']['tasks'][0]['template']['spec']['containers'][0]['volumeMounts'].append(dict(mountPath='/gpfs/models'))):
            value=copy.deepcopy(self.template())
            mutate(value)
            with self.assertRaises(ValueError):with_model_mount(value)


if __name__=='__main__':
    unittest.main()
