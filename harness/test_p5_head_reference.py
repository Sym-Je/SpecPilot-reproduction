import unittest

import numpy as np


class HeadReductionTests(unittest.TestCase):
    def test_same_fp32_weights_and_hidden_state_with_reordered_reduction(self):
        from controller.head_reference import reduce_head
        weight = np.arange(96, dtype=np.float32).reshape(6, 16) / 97
        hidden = np.linspace(-1, 1, 16, dtype=np.float32)
        direct = reduce_head(weight, hidden, chunks=1)
        reverse = reduce_head(weight, hidden, chunks=8, reverse=True)
        np.testing.assert_allclose(direct, reverse, atol=1e-5, rtol=1e-5)
        self.assertEqual(direct.dtype, np.float32)
        self.assertEqual(reverse.dtype, np.float32)

    def test_reduction_rejects_invalid_dimensions_or_chunk_counts(self):
        from controller.head_reference import reduce_head
        weight, hidden = np.ones((3, 8), np.float32), np.ones(8, np.float32)
        for invalid_weight, invalid_hidden, chunks in ((weight, hidden, 0), (weight, hidden, 9),
                                                       (weight, hidden[:7], 2)):
            with self.assertRaises(ValueError): reduce_head(invalid_weight, invalid_hidden, chunks=chunks)
