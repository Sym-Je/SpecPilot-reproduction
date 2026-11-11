"""CPU-only public-answer proxies; generated code runs only in the existing sandbox."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from exp.generalization_quality import grade, run_code
from harness.engine_research import save


def quality_items(request):
    indexed = {}
    for suite in ('gsm8k', 'math500', 'humaneval', 'mbpp', 'mt-bench'):
        for line in (ROOT / 'assets/upstream/dev' / (suite + '.jsonl')).read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                indexed[item['id']] = item
    result = {}
    for base in request['base_requests']:
        item = indexed[base['id']]
        if item['turns'][0] != base['question']:
            raise ValueError('quality task is not the unchanged author question')
        quality = dict(id=base['id'], suite=base['suite'], thinking_required=True)
        if base['suite'] in ('gsm8k', 'math500'):
            quality.update(metric='numeric', answer=item['answer'])
        elif base['suite'] == 'humaneval':
            blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', item['turns'][0], re.S)
            if len(blocks) != 1:
                raise ValueError('public HumanEval prompt cannot be aligned')
            quality.update(metric='code', code_prompt=blocks[0], entry_point=item['entry_point'],
                canonical=item['canonical'], tests=item['test'] + '\ncheck(' + item['entry_point'] + ')')
        elif base['suite'] == 'mbpp':
            quality.update(metric='code', canonical=item['canonical'], tests='\n'.join(item.get('test_imports', []) + item['test_list']))
        else:
            quality.update(metric='ungraded')
        result[base['id']] = quality
    return result


def controls(items):
    checked = {name: run_code(item['canonical'], item['tests']) for name, item in items.items() if item['metric'] == 'code'}
    if len(checked) != 4 or any(value['status'] != 'pass' for value in checked.values()):
        raise ValueError('public reference implementations did not all pass sandbox tests: ' + json.dumps(checked))
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('controls', 'evaluate'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    unit = args.directory.resolve()
    request = json.loads((unit / 'request.json').read_text())
    items = quality_items(request)
    checked = controls(items)
    if args.command == 'controls':
        save(args.output, dict(reference_controls=checked, passed=True))
        print('four public code references passed existing CPU sandbox')
        return
    from transformers import AutoTokenizer
    from exp.long_context import check_request, read_pairs
    check_request(unit / 'request.json')
    tokenizer = AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B', local_files_only=True)
    indexed = {item['id']: item for item in request['requests']}
    rows = []
    groups = defaultdict(list)
    for pair in read_pairs(unit / 'remote'):
        base = indexed[pair['id']]['base_id']
        for key, role in (('a', 'stock'), ('b', 'final')):
            measured = pair[key]
            text = tokenizer.decode(measured['output_ids'], skip_special_tokens=False, clean_up_tokenization_spaces=False)
            verdict = grade(items[base], text)
            row = dict(id=pair['id'], base_id=base, suite=items[base]['suite'], condition=pair['condition'],
                round=pair['round'], arm=role, output_sha256=measured['output_sha256'], quality=verdict)
            rows.append(row)
            groups[(pair['condition'], role, items[base]['suite'])].append(row)
    summary = {}
    for (condition, role, suite), selected in groups.items():
        summary.setdefault(condition, {}).setdefault(role, {})[suite] = dict(
            scored_outputs=sum(row['quality']['score'] is not None for row in selected),
            score_mean=(sum(row['quality']['score'] for row in selected) / len(selected))
                if all(row['quality']['score'] is not None for row in selected) else None,
            answered=sum(bool(row['quality']['answered']) for row in selected), outputs=len(selected),
            independent_tasks=len({row['base_id'] for row in selected}))
    save(args.output, dict(reference_controls=checked, rows=rows, summary=summary,
        scope='small public-task proxies; repeated GPU rounds are not independent tasks; not a losslessness or noninferiority verdict'))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
