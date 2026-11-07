import copy
import json
import tempfile
import unittest
from pathlib import Path

from exp.p2_northjob import validate_smoke, with_model_mount


class NorthJobSmokeTests(unittest.TestCase):
    def template(self):
        return {'spec': {'tasks': [{'replicas': 1, 'template': {'spec': {
            'volumes': [{'name': 'home', 'persistentVolumeClaim': {'claimName': 'jixinpeng-pvc'}}],
            'containers': [{'resources': {'limits': {'nvidia.com/gpu': '2'}},
                            'volumeMounts': [{'name': 'home', 'mountPath': '/gpfs/users/jixinpeng'}]}]}}}]}}

    def test_read_only_subpath_and_original_untouched(self):
        original = self.template()
        saved = copy.deepcopy(original)
        result = with_model_mount(original)
        pod = result['spec']['tasks'][0]['template']['spec']
        self.assertEqual(original, saved)
        self.assertEqual(pod['volumes'][-1]['persistentVolumeClaim'],
                         {'claimName': 'share-readonly', 'readOnly': True})
        self.assertEqual(pod['containers'][0]['volumeMounts'][-1], {
            'name': 'specpilot-models', 'mountPath': '/gpfs/models', 'subPath': 'models', 'readOnly': True})

    def test_mount_collision_rejected(self):
        with self.assertRaisesRegex(ValueError, 'mount already exists'):
            with_model_mount(with_model_mount(self.template()))

    def test_volume_collision_rejected(self):
        template = self.template()
        template['spec']['tasks'][0]['template']['spec']['volumes'].append({'name': 'specpilot-models'})
        with self.assertRaisesRegex(ValueError, 'volume already exists'):
            with_model_mount(template)

    def test_wrong_resources_rejected(self):
        template = self.template()
        template['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu'] = '1'
        with self.assertRaisesRegex(ValueError, 'two H100'):
            with_model_mount(template)
        template = self.template()
        template['spec']['tasks'][0]['replicas'] = 2
        with self.assertRaisesRegex(ValueError, 'one node'):
            with_model_mount(template)

    def write_run(self, directory, swap=True):
        def write(path, value):
            path.write_text(json.dumps(value))

        write(directory / 'summary.json', {'arms': ['stock', 'final'], 'rounds': 2,
              'n_requests': 5, 'n_pairs': 10, 'max_new_tokens': 64})
        for round_number in (1, 2):
            round_dir = directory / f'round-{round_number:02d}'
            round_dir.mkdir()
            uuids = ['gpu-0', 'gpu-1']
            if round_number == 2 and swap:
                uuids.reverse()
            write(round_dir / 'complete.json', {'round': round_number, 'pairs': 5})
            write(round_dir / 'deployment.json', {'assignments': [
                {'arm': {'name': arm}, 'gpu': {'uuid': uuid}}
                for arm, uuid in zip(('stock', 'final'), uuids)]})
            pairs = [{'id': str(index), 'suite': str(index),
                      'a': {'arm': 'stock', 'gpu_uuid': uuids[0], 'input_sha256': str(index)},
                      'b': {'arm': 'final', 'gpu_uuid': uuids[1], 'input_sha256': str(index)}}
                     for index in range(5)]
            for filename, records in (('pairs', pairs), ('stock', [pair['a'] for pair in pairs]),
                                      ('final', [pair['b'] for pair in pairs])):
                (round_dir / f'{filename}.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in records))

    def test_complete_smoke_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.write_run(directory)
            self.assertEqual(validate_smoke(directory)['arm_rows'], 20)

    def test_no_physical_swap_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.write_run(directory, swap=False)
            with self.assertRaisesRegex(ValueError, 'not exchanged'):
                validate_smoke(directory)

    def test_failed_run_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'failed.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'recorded a failure'):
                validate_smoke(directory)

    def test_partial_arm_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.write_run(directory)
            (directory / 'round-02/final.jsonl').write_text('')
            with self.assertRaisesRegex(ValueError, 'canonical pairs'):
                validate_smoke(directory)

    def test_changed_request_content_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.write_run(directory)
            round_dir = directory / 'round-02'
            pairs = [json.loads(line) for line in (round_dir / 'pairs.jsonl').read_text().splitlines()]
            for key, arm in (('a', 'stock'), ('b', 'final')):
                pairs[0][key]['input_sha256'] = 'different-input'
                (round_dir / f'{arm}.jsonl').write_text(''.join(json.dumps(pair[key]) + '\n' for pair in pairs))
            (round_dir / 'pairs.jsonl').write_text(''.join(json.dumps(pair) + '\n' for pair in pairs))
            with self.assertRaisesRegex(ValueError, 'coverage changed'):
                validate_smoke(directory)


if __name__ == '__main__':
    unittest.main()
