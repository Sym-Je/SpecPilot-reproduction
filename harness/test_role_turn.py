from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp import gpu_autonomy as roles


class RoleTurnTests(unittest.TestCase):
    def test_aborted_turn_keeps_consumed_tool_budget(self):
        broker=SimpleNamespace(actions=3,runs=1)
        client=SimpleNamespace(events=[],usage_updates=0,request=lambda *arguments:{'turn':{'id':'turn'}})
        def fail_receive(timeout):
            client.usage_updates=2
            raise RuntimeError('injected receive failure')
        client.receive=fail_receive
        role=dict(client=client,number=0,directory=Path('/unused'),manifest={'work':'/unused'},
            thread={'thread':{'id':'thread'}},actions=10,runs=4,broker_factory=lambda *arguments,**keywords:broker)
        counts=dict(model_turns=0,actions=0,cpu_runs=0,usage_updates=0)
        with patch.object(roles,'write'),patch.dict(roles.RUN_LIMITS,dict(model_turns=16,cpu_runs=32,usage_updates=512)):
            with self.assertRaisesRegex(RuntimeError,'injected receive failure'):
                roles.turn(role,'test',counts)
        self.assertEqual(counts,dict(model_turns=1,actions=3,cpu_runs=1,usage_updates=2))
        self.assertEqual((role['actions'],role['runs']),(7,3))

    def test_invalid_timeout_does_not_start_a_turn(self):
        role=dict(turn_timeout_seconds=901)
        with self.assertRaises(ValueError):
            roles.turn(role,'test',dict(model_turns=0))
