import json
from pathlib import Path
import tempfile
import unittest

from harness.engine_observations import enrich, observe


class EngineObservationTests(unittest.TestCase):
    def test_delivery_adds_evidence_without_changing_scientific_feedback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);role=root/'direction-01';record=role/'tools-01/action-001'
            record.mkdir(parents=True);(record/'request.json').write_text(json.dumps({'threadId':'own'}))
            experiment=root/'request-01';experiment.mkdir()
            (experiment/'request.json').write_text(json.dumps({'role_thread':'own'}))
            path=root/'work/inputs/source-feedback-01.json';path.parent.mkdir(parents=True)
            (role/'manifest.json').write_text(json.dumps({'work':str(root/'work')}))
            logs=experiment/'remote/round-01';logs.mkdir(parents=True)
            (logs/'candidate.launcher.log').write_text('TREE_COMMIT literal data\n')
            original=dict(request_directory=str(experiment),status='completed',geomean=0.9,controller_accepted=False)
            path.write_text(json.dumps(original))
            self.assertTrue(enrich(root,role,path))
            delivered=json.loads(path.read_text())
            observations=delivered.pop('supplemental_runtime_observations')
            relative=observations['candidate_logs'][0]['workspace_path']
            self.assertEqual((root/'work'/relative).read_text(),'TREE_COMMIT literal data\n')
            self.assertEqual(delivered,original)
            self.assertFalse(enrich(root,role,path))

    def test_runtime_evidence_cannot_cross_direction_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);role=root/'direction-01';record=role/'tools-01/action-001'
            record.mkdir(parents=True);(record/'request.json').write_text(json.dumps({'threadId':'own'}))
            experiment=root/'request-01';experiment.mkdir()
            (experiment/'request.json').write_text(json.dumps({'role_thread':'other'}))
            path=root/'feedback.json';path.write_text(json.dumps({'request_directory':str(experiment)}))
            with self.assertRaises(ValueError):enrich(root,role,path)

    def test_observations_do_not_certify_lossless_or_reinterpret_marker_strings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'remote/round-01';directory.mkdir(parents=True)
            row=dict(id='public-dev',a={'output_ids':[1,2]},b={'output_ids':[1,3]})
            (directory/'pairs.jsonl').write_text(json.dumps(row)+'\n')
            (directory/'candidate.launcher.log').write_text('TREE_VERIFY parent=0\nTREE_COMMIT node=1\n')
            value=observe(root)
            self.assertEqual(value['exact_output_matches'],0)
            self.assertEqual(value['pairs'][0]['first_difference'],1)
            self.assertEqual(value['candidate_logs'][0]['marker_tokens']['TREE_VERIFY'],1)
            self.assertFalse(value['lossless_certified'])
            self.assertFalse(value['branch_state_equivalence_certified'])

    def test_missing_runtime_is_not_a_passing_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            value=observe(temporary)
            self.assertEqual(value['paired_outputs'],0)
            self.assertEqual(value['candidate_logs'],[])
