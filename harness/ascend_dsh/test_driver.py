import unittest
from activity_watchdog import ProgressDeadline
from research_broker import Broker
from research_driver import parse_answer


class DriverTests(unittest.TestCase):
    def test_no_progress_fails_but_tokens_extend_deadline(self):
        watch = ProgressDeadline(0)
        a = {'generated': 10, 'running': 2, 'waiting': 1}
        watch.observe(a, 0); watch.observe(a, 299)
        with self.assertRaises(TimeoutError): watch.observe(a, 301)
        b = ProgressDeadline(0); b.observe(a, 0)
        a['generated'] += 1; b.observe(a, 299); b.observe(a, 598)
        with self.assertRaises(TimeoutError): b.observe(a, 600)

    def test_wall_deadline_applies_to_idle_aiperf(self):
        a = {'generated': 10, 'running': 0, 'waiting': 0}
        watch = ProgressDeadline(0); watch.observe(a, 0); watch.observe(a, 3500)
        with self.assertRaises(TimeoutError): watch.observe(a, 3601)

    def test_probe_and_master_do_not_have_npu_capability(self):
        for mode in ('probe', 'master'):
            broker = object.__new__(Broker); broker.mode = mode
            self.assertNotIn('launch_experiment', broker.names())
            self.assertNotIn('submit_patch', broker.names())
        self.assertIn('run_cpu', broker.names() if mode == 'probe' else Broker.names(type('B', (), {'mode': 'probe'})()))

    def test_json_answer_parser_rejects_prose(self):
        self.assertEqual(parse_answer('```json\n{"x":1}\n```'), {'x': 1})
        for text in ('prose {"x":1}', '[]', '{"x":1} trailing'):
            with self.assertRaises((ValueError, TypeError)): parse_answer(text)
