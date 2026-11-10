from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_broker import Broker, normalize_source_prefix


class SearchTests(unittest.TestCase):
    def test_root_qualified_and_relative_searches_find_the_same_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'; (source / 'ops').mkdir(parents=True)
            (source / 'ops/example.py').write_text('class HcPre: pass\n')
            with patch('research_broker.OUT', root), patch('research_broker.SOURCE_ROOTS', {'vllm_ascend': source}):
                broker = Broker('search-fixture', 'direction')
                results = [broker.act('search_source', {'tree': 'vllm_ascend', 'prefix': prefix, 'query': 'HcPre'})['result']
                           for prefix in ('ops', 'vllm_ascend/ops', 'vllm_ascend')]
                self.assertTrue(all(r['searched_files'] == 1 for r in results))
                self.assertTrue(all(r['matches'] == results[0]['matches'] for r in results))

    def test_prefix_alias_never_allows_escape(self):
        for prefix in ('/etc', '../outside', 'vllm_ascend/../outside'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                normalize_source_prefix('vllm_ascend', prefix)

    def test_empty_path_and_empty_literal_match_have_distinct_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'source'; source.mkdir()
            (source / 'one.py').write_text('alpha = 1\n')
            with patch('research_broker.OUT', root), patch('research_broker.SOURCE_ROOTS', {'vllm': source}):
                broker = Broker('empty-fixture', 'direction')
                no_files = broker.act('search_source', {'tree': 'vllm', 'prefix': 'missing', 'query': 'alpha'})['result']
                no_match = broker.act('search_source', {'tree': 'vllm', 'prefix': '', 'query': 'alpha beta'})['result']
                self.assertEqual(no_files['searched_files'], 0)
                self.assertEqual(no_match['searched_files'], 1)
                self.assertIn('exact phrase', no_match['search_guidance'])


if __name__ == '__main__':
    unittest.main()
