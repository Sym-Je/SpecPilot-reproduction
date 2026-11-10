"""Aggregate an exported kernel CSV by operator type, without summing overlap twice."""
import argparse
import collections
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


def union_duration(intervals):
    total = 0
    end = None
    for start, stop in sorted(intervals):
        if end is None or start >= end:
            total += stop - start
        elif stop > end:
            total += stop - end
        end = stop if end is None else max(end, stop)
    return total


def summarize(source):
    groups = collections.defaultdict(list)
    with source.open(newline='') as stream:
        for row in csv.DictReader(stream):
            try:
                start, duration = Decimal(row['Start Time(us)']), Decimal(row['Duration(us)'])
            except (InvalidOperation, TypeError):
                continue
            if not start.is_finite() or not duration.is_finite() or duration < 0:
                raise ValueError('Negative kernel duration')
            groups[row['Type']].append((start, start + duration))
    all_intervals = [x for values in groups.values() for x in values]
    if not all_intervals:
        raise ValueError('No kernel events in export')
    span = max(x[1] for x in all_intervals) - min(x[0] for x in all_intervals)
    rows = [{'operator_type': name, 'calls': len(values),
             'summed_kernel_us': sum(b-a for a, b in values),
             'operator_union_us': union_duration(values),
             'max_kernel_us': max(b-a for a, b in values),
             'rank_kernel_span_us': span,
             'scope': 'One rank; overlapping operator families; not critical-path share or speedup'}
            for name, values in groups.items()]
    rows.sort(key=lambda row: row['summed_kernel_us'], reverse=True)
    destination = source.with_name('kernel_type_summary.csv')
    with destination.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    print(summarize(args.source))
