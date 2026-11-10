import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from experiment_runner import make_launch
from research_broker import Broker


class InitModeTests(unittest.TestCase):
    def test_metadata_mode_keeps_stock_model_argv_and_uses_isolated_bootstrap(self):
        from prepare_baseline import OUT
        with tempfile.TemporaryDirectory() as tmp:
            path=make_launch({'cache_init_metadata':True},Path(tmp),initialization_only=True)
            actual=next(x for x in path.read_text().splitlines() if x.startswith('exec '))
            stock=next(x for x in (OUT/'launch-mrv1.sh').read_text().splitlines() if x.startswith('exec '))
            self.assertEqual(shlex.split(actual),shlex.split(stock))
            self.assertIn('PREFIX_CACHE_METADATA_ENABLE=1',path.read_text())
            self.assertTrue((Path(tmp)/'cache-init-runtime/cache_metadata_diag.py').is_file())
            self.assertTrue((Path(tmp)/'cache-init-runtime/network_guard.py').is_file())

    def test_phase1_cannot_enable_cache_generate_or_combine_instrumentation(self):
        for config,kwargs in [({'cache_init_metadata':True},{}),
                ({'cache_init_metadata':True,'enable_prefix_caching':True},{'initialization_only':True}),
                ({'cache_init_metadata':True,'cpu_work_metadata':True},{'initialization_only':True}),
                ({'cache_init_metadata':True},{'profile':True,'initialization_only':True})]:
            with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):
                make_launch(config,Path(tmp),**kwargs)

    def test_unadmitted_role_cannot_submit_initialization_mode(self):
        with tempfile.TemporaryDirectory() as tmp,patch('research_broker.OUT',Path(tmp)):
            broker=Broker('unadmitted','direction')
            with self.assertRaisesRegex(ValueError,'admission'):
                broker.act('launch_experiment',{'id':'init','mode':'cache_init','config':{'cache_init_metadata':True}})
            self.assertFalse((Path(tmp)/'experiments').exists())

    def test_runner_submits_no_generation_and_restores_after_capture_failure(self):
        import experiment_runner as runner
        from prepare_baseline import write,sha
        for valid in (True,False):
            with self.subTest(valid=valid),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);out=root/'runtime';out.mkdir();folder=out/'experiments/fixture';folder.mkdir(parents=True)
                (root/'evaluation').mkdir();(root/'deployment/selected').mkdir(parents=True)
                write(out/'installed-engine-source-manifest.json',{})
                write(out/'baseline-state.json',{'status':'complete'})
                write(root/'deployment/selected/selection.json',{'selected_mode':'MRV1-fixed-DSpark-K7','owner_pid':1,'owner_create_time':1.0})
                write(folder/'request.json',{'split':'dev','mode':'cache_init','config':{'cache_init_metadata':True},
                    'source_sha256':sha(runner.__file__),'execution_pins':{},
                    'installed_engine_manifest_sha256':sha(out/'installed-engine-source-manifest.json')})
                with patch.object(runner,'OUT',out),patch.object(runner,'ROOT',root), \
                        patch.object(runner.signal,'signal'),patch.object(runner.shutil,'disk_usage',return_value=NS(free=10*1024**3)), \
                        patch.object(runner,'metrics',return_value={'running':0,'waiting':0}), \
                        patch.object(runner,'make_launch',return_value=folder/'launch.sh') as builder, \
                        patch.object(runner,'launch',side_effect=[{'pid':2,'birth':2.0},{'pid':3,'birth':3.0}]) as launch, \
                        patch.object(runner,'stop_owned'),patch.object(runner,'wait_health'), \
                        patch.object(runner,'run_screen',side_effect=AssertionError('Generation forbidden')) as generation, \
                        patch('cache_init_export.export_initialization',return_value={'structural_capture_complete':valid}):
                    if valid:runner.run('fixture')
                    else:
                        with self.assertRaisesRegex(AssertionError,'Incomplete cache metadata'):runner.run('fixture')
                    generation.assert_not_called();self.assertTrue(builder.call_args.kwargs['initialization_only'])
                    self.assertEqual(launch.call_count,2)
                state=json.loads((folder/'state.json').read_text())
                self.assertTrue(state['baseline_restored'])
                self.assertEqual(state['status'],'complete' if valid else 'failed')


if __name__=='__main__':unittest.main()
