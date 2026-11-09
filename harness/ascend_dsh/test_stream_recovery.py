import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import resume_claude

RECORD = {'call_id': 'fixture', 'result': {'finish_reason': 'error', 'events': [
    {'type': 'turn/end', 'data': {'reason': {'kind': 'error', 'error': {
        'code': 'SERVER', 'message': 'The upstream model stopped sending for 60s partway through the response. Please retry later.'}}}}]}}


class StreamRecoveryTests(unittest.TestCase):
    def test_only_confirmed_upstream_stall_is_retried(self):
        self.assertTrue(resume_claude.transient_stream_stall(RECORD))
        for code, message in [('SERVER', 'budget exhausted'), ('AUTH', 'stopped sending for 60s')]:
            x = {'result': {'finish_reason': 'error', 'events': [{'type': 'turn/end', 'data': {
                'reason': {'error': {'code': code, 'message': message}}}}]}}
            self.assertFalse(resume_claude.transient_stream_stall(x))

    def test_retry_resumes_with_short_prompt_and_retains_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); role = root / 'research/roles/test'; role.mkdir(parents=True)
            with patch.object(resume_claude, 'OUT', root), \
                 patch.object(resume_claude, 'latest_call', return_value=RECORD), \
                 patch.object(resume_claude, 'patch_for', return_value=root / 'patch.yml'), \
                 patch.object(resume_claude.time, 'sleep'), \
                 patch.object(resume_claude, 'call', side_effect=[AssertionError('error'), ('{"decision":"stop"}', {'call_id':'success'})]) as call:
                answer = resume_claude.invoke('test', 'master', 'original large context')
            self.assertEqual(answer['decision'], 'stop'); self.assertEqual(call.call_count, 2)
            self.assertNotIn('original large context', call.call_args_list[1].args[1])
            self.assertIn('charged_reservation_retained', (role / 'transport-retries.jsonl').read_text())

    def test_retry_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); role = root / 'research/roles/test'; role.mkdir(parents=True)
            with patch.object(resume_claude, 'OUT', root), \
                 patch.object(resume_claude, 'latest_call', return_value=RECORD), \
                 patch.object(resume_claude, 'patch_for', return_value=root / 'patch.yml'), \
                 patch.object(resume_claude.time, 'sleep'), \
                 patch.object(resume_claude, 'call', side_effect=AssertionError('error')) as call:
                with self.assertRaises(AssertionError): resume_claude.invoke('test', 'master', 'context')
            self.assertEqual(call.call_count, 3)
            self.assertEqual(len((role / 'transport-retries.jsonl').read_text().splitlines()), 2)


if __name__ == '__main__': unittest.main()
