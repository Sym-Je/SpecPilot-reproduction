import csv
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from summarize_kernels import summarize, union_duration


class SummaryTests(unittest.TestCase):
    def test_containment_overlap_and_disjoint_intervals(self):
        self.assertEqual(union_duration([(0, 4), (1, 2), (3, 8), (10, 12)]), 10)

    def test_large_clock_timestamps_do_not_round_short_kernel_durations(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'kernel_details.csv'
            p.write_text('Type,Start Time(us),Duration(us)\nA,1794287000000000.001,0.003\nA,1794287000000000.002,0.003\nB,1794287000000000.010,0.005\n')
            with summarize(p).open() as stream:
                rows = {row['operator_type']: row for row in csv.DictReader(stream)}
            self.assertEqual(Decimal(rows['A']['summed_kernel_us']), Decimal('0.006'))
            self.assertEqual(Decimal(rows['A']['operator_union_us']), Decimal('0.004'))
            self.assertEqual(Decimal(rows['A']['rank_kernel_span_us']), Decimal('0.014'))


if __name__ == '__main__':
    unittest.main()
