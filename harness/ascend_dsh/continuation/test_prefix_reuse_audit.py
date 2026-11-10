import unittest
from prefix_reuse_audit import reuse_ceiling


class PrefixTests(unittest.TestCase):
    def test_identical_prompt_still_retains_one_uncached_suffix(self):
        r=reuse_ceiling([[1,2,3,4],[1,2,3,4]],2)
        self.assertEqual(r['reusable_prefix_tokens_upper_bound'],2)
        self.assertEqual(r['exact_repeated_request_reuse_tokens'],2)

    def test_different_prompts_share_only_complete_common_blocks(self):
        r=reuse_ceiling([[1,2,3,4],[1,2,5,6],[9,2,3,4]],2)
        self.assertEqual(r['reusable_prefix_tokens_upper_bound'],2)
        self.assertEqual(r['exact_repeated_request_reuse_tokens'],0)
        self.assertEqual(r['retained_suffix_tokens_lower_bound'],10)


if __name__=='__main__':unittest.main()
