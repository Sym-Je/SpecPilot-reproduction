"""Freeze development-only replay inputs. Never opens validation files."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA = ROOT / 'datasets/speculative-training/ctrip/20261109/benchmark-v1-100/dev'
BUCKETS = ('short', 'mid', 'long')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def bucket(n):
    return 'short' if n <= 16384 else 'mid' if n <= 32768 else 'long'


def prepare(check=False):
    plan = json.loads((OUT / 'plan.json').read_text())
    assert sha(DATA / 'requests.jsonl') == plan['dev_requests_sha256']
    assert sha(DATA / 'aiperf-inputs.json') == plan['dev_aiperf_sha256']
    rows = [json.loads(l) for l in (DATA / 'requests.jsonl').open()]
    assert len(rows) == len({r['metadata']['group_id'] for r in rows}) == 60
    directory = OUT / 'baseline-inputs'
    if not check:
        directory.mkdir(exist_ok=False)
    cases = []
    for label in BUCKETS:
        source = [r for r in rows if bucket(r['metadata']['input_tokens']) == label]
        assert len(source) == 20
        single = []
        for kind in ('answer', 'tool_call'):
            subset = [r for r in source if r['metadata']['target_kind'] == kind]
            subset.sort(key=lambda r: (-r['metadata']['reference_reasoning_tokens'], r['id']))
            single += [subset[0], subset[-1]]
        for concurrency in (1, 8, 32):
            selected = single if concurrency == 1 else source
            repeats = 2 if concurrency == 32 else 1
            entries = []
            expected = {}
            for repeat in range(repeats):
                for row in selected:
                    payload = copy.deepcopy(row['request'])
                    if not payload.get('tools'):
                        payload.pop('tools', None)
                    assert payload['max_tokens'] == 8192 and payload['reasoning_effort'] == 'high'
                    assert not payload.get('ignore_eos', False)
                    session_id = row['id'] + f'-repeat{repeat}'
                    entries.append({'session_id': session_id, 'payloads': [payload]})
                    expected[session_id] = {'source_id': row['id'], 'input_tokens': row['metadata']['input_tokens']}
            path = directory / f'{label}-c{concurrency}.json'
            data = {'data': entries}
            if check:
                assert json.loads(path.read_text()) == data
            else:
                write(path, data)
            cases.append({'name': f'{label}-c{concurrency}', 'stratum': label,
                          'concurrency': concurrency, 'request_count': len(entries),
                          'warmups': 1 if concurrency == 1 else 2,
                          'input_path': str(path), 'input_sha256': sha(path), 'requests': expected})
    result = {'split': 'dev', 'validation_opened': False, 'unique_dev_groups': 60,
              'request_normalization': 'Omit empty tools arrays; tokenization checked unchanged for all seven dev rows.',
              'cases': cases, 'formal_requests': sum(c['request_count'] for c in cases)}
    if check:
        assert result == json.loads((OUT / 'baseline-input-manifest.json').read_text())
    else:
        write(OUT / 'baseline-input-manifest.json', result)
    print(json.dumps({'pass': True, 'cases': len(cases), 'formal_requests': result['formal_requests'],
                      'dev_groups': 60, 'validation_opened': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    prepare(parser.parse_args().check)
