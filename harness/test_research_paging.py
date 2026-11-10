"""CPU-only paging acceptance preregistered in coverage-review-20261110.md."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agents.autonomy import validate_action
from harness.research_protocol import ResearchBroker


class ResearchPagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.work = self.root / 'work'
        (self.work / 'inputs').mkdir(parents=True)
        self.content = '非敏感分页fixture\n' * 2500
        self.path = self.work / 'inputs/evidence.json'
        self.path.write_text(self.content)
        self.broker = ResearchBroker(self.work, self.root / 'tools', 'thread', 'turn', max_actions=64)

    def call(self, action):
        response = self.broker.handle(dict(threadId='thread', turnId='turn', tool='research', namespace=None,
            callId=str(self.broker.actions + 1), arguments={'action': action}))
        return response['success'], json.loads(response['contentItems'][0]['text'])

    def test_help_examples_use_valid_exact_fields(self):
        success, answer = self.call({'kind': 'help'})
        self.assertTrue(success)
        for action in answer['actions'].values():
            validate_action(action)
        self.assertEqual(answer['actions']['read_file']['offset'], 0)
        self.assertEqual(set(answer['actions']['run_python']), {'kind', 'path'})

    def test_unicode_full_paging_same_sha_and_contiguous_offsets(self):
        offset, pages = 0, []
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        while offset is not None:
            success, answer = self.call(dict(kind='read_file', path='inputs/evidence.json', offset=offset))
            self.assertTrue(success)
            self.assertEqual(answer['offset'], offset)
            self.assertEqual(answer['sha256'], digest)
            self.assertEqual(answer['total_chars'], len(self.content))
            pages.append(answer['content'])
            offset = answer['next_offset']
        self.assertGreater(len(pages), 2)
        self.assertEqual(''.join(pages), self.content)

    def test_default_offset_is_first_page_not_false_eof(self):
        success, answer = self.call(dict(kind='read_file', path='inputs/evidence.json'))
        self.assertTrue(success)
        self.assertEqual(answer['content'], self.content[:12000])
        self.assertEqual(answer['next_offset'], 12000)

    def test_exact_end_returns_empty_eof(self):
        success, answer = self.call(dict(kind='read_file', path='inputs/evidence.json', offset=len(self.content)))
        self.assertTrue(success)
        self.assertEqual(answer['content'], '')
        self.assertIsNone(answer['next_offset'])

    def test_invalid_and_out_of_bounds_offsets_rejected(self):
        for offset in (-1, True, False, 1.5, '12000', None, len(self.content) + 1):
            with self.subTest(offset=offset):
                success, answer = self.call(dict(kind='read_file', path='inputs/evidence.json', offset=offset))
                self.assertFalse(success)
                self.assertEqual(answer['status'], 'rejected')

    def test_extra_fields_and_inline_python_rejected(self):
        for action in (dict(kind='help', extra=True),
                       dict(kind='read_file', path='inputs/evidence.json', offset=0, limit=24000),
                       dict(kind='run_python', code='print(1)'),
                       dict(kind='run_python', path='scratch/check.py', source='print(1)')):
            with self.subTest(action=action):
                success, answer = self.call(action)
                self.assertFalse(success)
                self.assertEqual(answer['status'], 'rejected')

    def test_workspace_escape_and_symlinks_rejected(self):
        outside = self.root / 'outside.txt'
        outside.write_text('synthetic outside boundary')
        (self.work / 'inputs/link.txt').symlink_to(outside)
        for path in ('../outside.txt', str(outside), 'inputs/link.txt'):
            with self.subTest(path=path):
                success, _ = self.call(dict(kind='read_file', path=path, offset=0))
                self.assertFalse(success)


if __name__ == '__main__':
    unittest.main()
