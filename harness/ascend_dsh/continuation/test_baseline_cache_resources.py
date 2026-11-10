import json
import unittest
from baseline_cache_resources import parse_resources


class ResourceTests(unittest.TestCase):
    def line(self, rank):
        return (f'(Worker_TP{rank}_EP{rank} pid=100) INFO Actual usage: 39.13 GiB for weights, '
                '1.45 GiB for peak activation, 0.51 GiB for non-torch memory, '
                '0.75 GiB for NPU graph memory. Current KV cache memory: 13.77 GiB. '
                'After warmup: torch reserved memory 53.63 GiB, torch allocated memory 53.24 GiB.')

    def test_only_fixed_numeric_metadata_survives(self):
        text="enable_prefix_caching': False\nNPU KV cache size: 169,470 tokens, Maximum concurrency for 65,536 tokens per request: 2.59x\n"
        text+='\n'.join(self.line(i) for i in range(8))+'\nrequest_id=private prompt=DO_NOT_EXPORT'
        result=parse_resources(text)
        self.assertTrue(result['all_eight_resource_rows_present'])
        self.assertEqual(result['rank_rows'][0]['weights_gib_rounded'],39.13)
        self.assertEqual(result['logged_cache_capacity_tokens'],169470)
        self.assertFalse(result['logged_prefix_caching_enabled'])
        self.assertNotIn('DO_NOT_EXPORT',json.dumps(result))
        self.assertIsNone(result['enabled_cache_support'])

    def test_missing_ranks_or_unknown_flag_remain_unresolved(self):
        result=parse_resources(self.line(0))
        self.assertFalse(result['all_eight_resource_rows_present'])
        self.assertIsNone(result['logged_prefix_caching_enabled'])
        self.assertIsNone(result['logged_cache_capacity_tokens'])


if __name__=='__main__':unittest.main()
