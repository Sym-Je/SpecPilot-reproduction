import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from final_validation import freeze_candidate, open_validation, make_cases


class ValidationTests(unittest.TestCase):
    def test_no_heldout_file_access_before_freeze(self):
        with patch('builtins.open', side_effect=AssertionError('Unexpected file access')):
            with self.assertRaises(AssertionError):
                open_validation({'research_stopped': False, 'validation_opened': False}, Path('/unused'))

    def test_running_research_cannot_freeze(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(AssertionError):
                freeze_candidate({'status': 'researching', 'validation_opened': False}, Path(t))
            self.assertEqual(list(Path(t).iterdir()), [])

    def test_unfinished_or_unmeasured_candidate_cannot_freeze(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            role = root / 'research/roles/d1'; role.mkdir(parents=True)
            (role / 'broker-state.json').write_text('{"experiments":["e1"]}')
            e = root / 'experiments/e1'; e.mkdir(parents=True)
            (e / 'state.json').write_text('{"status":"running"}')
            (e / 'request.json').write_text('{"mode":"benchmark","split":"dev","config":{}}')
            research = {'status': 'research_finished', 'validation_opened': False,
                        'master_decision': {'candidate': {'experiment_id': 'e1', 'config': {}}},
                        'rounds': [{'role': 'd1'}]}
            with self.assertRaises(AssertionError): freeze_candidate(research, root)
            self.assertFalse((root / 'candidate-freeze.json').exists())

    def test_fixed_selection_and_all_forty_coverage(self):
        rows = []
        for n, count in ((1000, 14), (20000, 13), (40000, 13)):
            for index in range(count):
                identifier = f'{n}-{index:02}'
                rows.append({'id': identifier, 'metadata': {'group_id': identifier, 'input_tokens': n},
                             'request': {'temperature': 0, 'max_tokens': 8192, 'reasoning_effort': 'high', 'tools': []}})
        with tempfile.TemporaryDirectory() as t:
            cases = make_cases(list(reversed(rows)), Path(t) / 'inputs')
            self.assertEqual(len(cases), 9)
            ids = {v['source_id'] for c in cases if c['concurrency'] == 8 for v in c['requests'].values()}
            self.assertEqual(ids, {r['id'] for r in rows})
            self.assertEqual(sum(c['request_count'] for c in cases), 142)
            for case in cases:
                data = json.loads(Path(case['input_path']).read_text())['data']
                self.assertTrue(all('tools' not in r['payloads'][0] for r in data))
                self.assertEqual(len(data), case['request_count'])
            self.assertTrue(all('tools' in r['request'] for r in rows))
