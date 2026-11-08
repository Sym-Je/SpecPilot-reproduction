"""Blind, deterministic public-source sampling; never reads existing sealed data."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
import io
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.http_transport import sha_ids
from exp.p3_pair_run import SUITES, write_json

SEED = '261102501'
DOMAINS = SUITES + ['chinese-qa', 'science-qa', 'summary', 'json-extraction', 'dialogue']
SOURCES = {
    'gsm8k': ('openai/grade-school-math', 'grade_school_math/data/test.jsonl', 'MIT'),
    'math500': ('openai/prm800k', 'prm800k/math_splits/test.jsonl', 'MIT'),
    'humaneval': ('openai/human-eval', 'data/HumanEval.jsonl.gz', 'MIT'),
    'mbpp': ('google-research/google-research', 'mbpp/mbpp.jsonl', 'CC-BY-4.0'),
    'mt-bench': ('lm-sys/FastChat', 'fastchat/llm_judge/data/mt_bench/question.jsonl', 'Apache-2.0'),
    'chinese-qa': ('ymcui/cmrc2018', 'data/cmrc2018_dev.json', 'CC-BY-SA-4.0'),
    'science-qa': ('allenai/OpenBookQA', 'Data/Main/test.jsonl', 'Apache-2.0'),
    'summary': ('tatsu-lab/stanford_alpaca', 'alpaca_data.json', 'CC-BY-NC-4.0'),
    'json-extraction': ('rajpurkar/SQuAD-explorer', 'dataset/dev-v1.1.json', 'CC-BY-SA-4.0'),
    'dialogue': ('tatsu-lab/stanford_alpaca', 'alpaca_data.json', 'CC-BY-NC-4.0'),
}
REVISIONS = {
    'openai/grade-school-math': '3101c7d5072418e28b9008a6636bde82a006892c',
    'openai/prm800k': '7ecc794703b2877f63226f2477a49b34f9b25163',
    'openai/human-eval': 'b9453e8f1865df0a0057a1383767caa400acfbcf',
    'google-research/google-research': '0eebfd403ba438bfd14cb70b9b24a7745c997083',
    'lm-sys/FastChat': '587d5cfa1609a43d192cedb8441cac3c17db105d',
    'ymcui/cmrc2018': 'c0eb1b6ba219847457e6af3180da722bbeb656af',
    'allenai/OpenBookQA': 'b51971646e9371a61508d9953fc706645e194a71',
    'tatsu-lab/stanford_alpaca': '761dc5bfbdeeffa89b8bff5d038781a4055f796a',
    'rajpurkar/SQuAD-explorer': 'eee5fdbf62f8613a7812b03419e6b29617b74fd1',
}


@lru_cache(maxsize=512)
def normalize(text):
    return ''.join(character for character in unicodedata.normalize('NFKC', text).casefold()
                   if character.isalnum())


@lru_cache(maxsize=512)
def grams(text):
    return {text[index:index + 5] for index in range(max(1, len(text) - 4))}


def duplicate(prompt, others):
    normal = normalize(prompt)
    shingles = grams(normal)
    for other in others:
        candidate = normalize(other)
        if normal == candidate or (min(len(normal), len(candidate)) >= 20 and
                                   (normal in candidate or candidate in normal)):
            return True
        if min(len(normal), len(candidate)) / max(1, len(normal), len(candidate)) < .75:
            continue
        reference = grams(candidate)
        if len(shingles & reference) / max(1, len(shingles | reference)) >= .8:
            return True
    return False


def key(row):
    return hashlib.sha256((SEED + '|' + row['suite'] + '|' + row['source_id']).encode()).hexdigest()


def select(pool, excluded_prompts, excluded_ids, count):
    eligible, selected = [], []
    for row in sorted(pool, key=key):
        if row['source_id'] in excluded_ids or not 0 < len(row['input_ids']) <= 8192 or duplicate(row['prompt'], excluded_prompts):
            continue
        eligible.append(row)
    if len(eligible) < count:
        raise ValueError('insufficient unique requests after full-dev exclusion')
    eligible.sort(key=lambda row: (len(row['input_ids']), key(row)))
    panel = []
    for band, candidates in (('short', eligible[:len(eligible)//2]), ('long', eligible[len(eligible)//2:])):
        chosen = []
        for row in sorted(candidates, key=key):
            if not duplicate(row['prompt'], [item['prompt'] for item in selected + chosen]):
                chosen.append(row)
            if len(chosen) == count//2:
                break
        if len(chosen) != count//2:
            raise ValueError('insufficient input-length stratum')
        selected.extend(dict(row, input_band=band) for row in chosen)
        panel.extend(row['source_id'] for row in chosen[:2])
    return selected, panel


def source_rows(domain, rows):
    items = []
    if domain == 'chinese-qa':
        rows = [dict(id=qa['query_id'],question=qa['query_text'],answers=[dict(text=answer) for answer in qa['answers']],
                     context=article['context_text']) for article in rows for qa in article['qas']]
    elif domain == 'json-extraction':
        rows = [dict(qa, context=paragraph['context']) for article in rows['data']
                for paragraph in article['paragraphs'] for qa in paragraph['qas']]
    for index, row in enumerate(rows):
        item = dict(suite=domain, source_id=str(index), thinking_required=True)
        if domain == 'gsm8k':
            item.update(prompt=row['question'] + '\nPlease reason step by step and put your final answer in \\boxed{}.',
                        metric='numeric', answer=row['answer'])
        elif domain == 'math500':
            item.update(prompt=row['problem'] + '\nPlease reason step by step and put your final answer in \\boxed{}.',
                        metric='numeric', answer=row.get('answer', row.get('solution', '')))
        elif domain == 'humaneval':
            item.update(source_id=row['task_id'], prompt='Complete the following Python function. Return Python code.\n'+row['prompt'],
                metric='code', code_prompt=row['prompt'], entry_point=row['entry_point'], canonical=row['canonical_solution'],
                tests=row['test'] + '\ncheck(' + row['entry_point'] + ')')
        elif domain == 'mbpp':
            item.update(source_id=str(row['task_id']), prompt=row['text']+'\nReturn Python code.\n'+'\n'.join(row['test_list']),
                metric='code', canonical=row['code'], tests='\n'.join(row.get('test_imports', []) + row['test_list']))
        elif domain == 'mt-bench':
            item.update(source_id=str(row['question_id']), prompt=row['turns'][0], metric='ungraded')
        elif domain == 'chinese-qa':
            item.update(source_id=str(row['id']), prompt='阅读文章，回答问题，只输出简短答案。\n文章：'+row['context']+'\n问题：'+row['question'],
                        metric='qa', answers=[answer['text'] for answer in row['answers']])
        elif domain == 'science-qa':
            answers = {answer['label']: answer['text'] for answer in row['question']['choices']}
            item.update(source_id=str(row['id']), prompt=row['question']['stem']+'\nOptions:\n'+
                '\n'.join(label+': '+answer for label, answer in answers.items())+'\nReturn only the exact text of the correct option.',
                metric='qa', answers=[answers[row['answerKey']]])
        elif domain == 'summary':
            if not re.search(r'\bsummari[sz]e\b|\bsummary\b',row['instruction'],re.I) or not row['input'].strip():
                continue
            item.update(prompt=row['instruction']+'\n\n'+row['input'], metric='rouge_l', answer=row['output'])
        elif domain == 'json-extraction':
            item.update(source_id=str(row['id']), prompt='Extract the answer from the passage. Return only a JSON object with one string key "answer".\nPassage: '+
                row['context']+'\nQuestion: '+row['question'], metric='json', answers=[answer['text'] for answer in row['answers']])
        elif domain == 'dialogue':
            if row['input'].strip() or re.search(r'\b(code|python|math|calculate|equation|summari[sz]e)\b',row['instruction'],re.I):
                continue
            item.update(prompt=row['instruction'], metric='ungraded')
        if item.get('answers') == [] or not item.get('prompt', '').strip():
            continue
        items.append(item)
    return items


def download_sources(directory, cache=None):
    import requests

    specifications = list(dict.fromkeys((repo, name) for repo, name, _ in SOURCES.values()))
    if cache is not None:
        old = {(item['repo'],item['filename']):item for item in json.loads((cache/'sources.json').read_text())}
        sources=[]
        for repo,filename in specifications:
            item=old[repo,filename]
            content=Path(item['path']).read_bytes()
            if item['revision'] != REVISIONS[repo] or hashlib.sha256(content).hexdigest() != item['sha256']:
                raise ValueError('cached pinned source changed')
            destination=directory/Path(item['path']).name
            destination.write_bytes(content)
            sources.append(dict(item,path=str(destination)))
        write_json(directory/'sources.json',sources)
        return {(item['repo'],item['filename']):item for item in sources}
    def fetch(specification):
        repo, filename = specification
        session = requests.Session()
        session.trust_env = False
        session.proxies = {'https': 'http://10.51.6.1:6890', 'http': 'http://10.51.6.1:6890'}
        revision = REVISIONS[repo]
        url = 'https://raw.githubusercontent.com/'+repo+'/'+revision+'/'+filename
        if repo == 'allenai/OpenBookQA':
            url = 'https://ai2-public-datasets.s3.amazonaws.com/open-book-qa/OpenBookQA-V1-Sep2018.zip'
        response = session.get(url, timeout=180)
        response.raise_for_status()
        if response.content.startswith(b'version https://git-lfs.github.com/spec/v1'):
            oid = re.search(rb'oid sha256:([a-f0-9]{64})', response.content).group(1).decode()
            url = 'https://media.githubusercontent.com/media/'+repo+'/'+revision+'/'+filename
            response = session.get(url, timeout=180)
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != oid:
                raise ValueError('Git LFS content differs from pinned pointer')
        content = response.content
        download_sha = hashlib.sha256(content).hexdigest()
        destination = directory / (repo.replace('/', '--') + '--' + Path(filename).name)
        if repo == 'allenai/OpenBookQA':
            if download_sha != '82368cf05df2e3b309c17d162e10b888b4d768fad6e171e0a041954c8553be46':
                raise ValueError('official OpenBookQA archive changed before sampling')
            destination.with_suffix('.zip').write_bytes(content)
            content = zipfile.ZipFile(io.BytesIO(content)).read('OpenBookQA-V1-Sep2018/Data/Main/test.jsonl')
        destination.write_bytes(content)
        return dict(repo=repo, filename=filename, revision=revision, url=url, path=str(destination),
                    sha256=hashlib.sha256(content).hexdigest(), download_sha256=download_sha, bytes=len(content))
    with ThreadPoolExecutor(9) as pool:
        sources = list(pool.map(fetch, specifications))
    write_json(directory / 'sources.json', sources)
    return {(item['repo'], item['filename']): item for item in sources}


def prepare(private, public, source_cache=None):
    from transformers import AutoTokenizer

    os.umask(0o077)
    private.mkdir(mode=0o700)
    public.mkdir(mode=0o700)
    originals = [json.loads(line) for suite in SUITES
                 for line in (ROOT / 'assets/upstream/dev' / (suite + '.jsonl')).read_text().splitlines() if line]
    if len(originals) != 100:
        raise ValueError('all one hundred known author dev items are required')
    excluded = [row['turns'][0] for row in originals]
    sources = download_sources(private,source_cache)
    tokenizer = AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B', local_files_only=True)
    all_items, panels, counts = [], [], {}
    for domain in DOMAINS:
        repo, filename, license_name = SOURCES[domain]
        source = sources[repo, filename]
        content = Path(source['path']).read_bytes()
        if filename.endswith('.gz'):
            content = gzip.decompress(content)
        decoded = content.decode()
        rows = [json.loads(line) for line in decoded.splitlines() if line] if '.jsonl' in filename else json.loads(decoded)
        pool = source_rows(domain, rows)
        for item in pool:
            encoded = tokenizer.apply_chat_template([dict(role='user', content=item['prompt'])],
                add_generation_prompt=True, tokenize=True, enable_thinking=True)
            item['input_ids'] = list(encoded if isinstance(encoded, list) else encoded['input_ids'])
        old_ids = {str(row.get('task_id', row['id'].removeprefix(domain+'-'))) for row in originals if row['suite'] == domain}
        items, panel = select(pool, excluded + [item['prompt'] for item in all_items], old_ids, 20)
        for item in items:
            item.update(id=domain+'-'+hashlib.sha256((repo+'|'+item['source_id']).encode()).hexdigest()[:16],
                        input_sha256=sha_ids(item['input_ids']), turn=0)
        panels.extend(item['id'] for item in items if item['source_id'] in panel)
        all_items.extend(items)
        counts[domain] = dict(pool=len(pool), selected=len(items), short=10, long=10, panel=4,
                             min_prompt_tokens=min(len(item['input_ids']) for item in items),
                             max_prompt_tokens=max(len(item['input_ids']) for item in items), license=license_name)
    requests = [{key:item[key] for key in ('id','suite','turn','input_ids','input_sha256','input_band')} for item in all_items]
    write_json(private / 'dataset.json', dict(requests=requests, items=all_items, panel_ids=panels, seed=SEED,
               excluded_author_dev=100, sources=list(sources.values())))
    summary = dict(prepared=True, unique_requests=200, author_dev_excluded=100, panel_unique_requests=40,
        caps=[2048,256,4096], seed=SEED, domains=counts,
        dataset_sha256=hashlib.sha256((private / 'dataset.json').read_bytes()).hexdigest(),
        sources=[{key:value for key,value in source.items() if key != 'path'} for source in sources.values()],
        blindness='agent did not inspect selected questions or answers; same-UID covenant, not independent-party isolation',
        limitations=['public data may have been seen by author or pretraining', 'input bands relative within domain',
                    'MT/dialogue semantic quality ungraded', 'not the paper sealed split'])
    write_json(public / 'preparation.json', summary)
    print(json.dumps(dict(prepared=True, requests=200, panel=40, dataset_sha256=summary['dataset_sha256'])), flush=True)


def verify_prepared(private,public):
    from transformers import AutoTokenizer
    dataset=json.loads((private/'dataset.json').read_text())
    summary=json.loads((public/'preparation.json').read_text())
    originals=[json.loads(line) for suite in SUITES for line in (ROOT/'assets/upstream/dev'/(suite+'.jsonl')).read_text().splitlines() if line]
    if len(originals)!=100 or len(dataset['items'])!=200 or len(set(dataset['panel_ids']))!=40:
        raise ValueError('wrong exclusion, unique-request or panel coverage')
    if summary['dataset_sha256'] != hashlib.sha256((private/'dataset.json').read_bytes()).hexdigest():
        raise ValueError('dataset differs from public frozen identity')
    tokenizer=AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',local_files_only=True)
    seen=[row['turns'][0] for row in originals]
    for item,request in zip(dataset['items'],dataset['requests']):
        if duplicate(item['prompt'],seen):
            raise ValueError('known-author or internal near duplicate')
        seen.append(item['prompt'])
        old_ids={str(row.get('task_id',row['id'].removeprefix(item['suite']+'-'))) for row in originals if row['suite']==item['suite']}
        if item['source_id'] in old_ids:
            raise ValueError('known-author source identity reused')
        encoded=tokenizer.apply_chat_template([dict(role='user',content=item['prompt'])],add_generation_prompt=True,tokenize=True,enable_thinking=True)
        encoded=list(encoded if isinstance(encoded,list) else encoded['input_ids'])
        if encoded!=request['input_ids'] or item['id']!=request['id'] or sha_ids(encoded)!=request['input_sha256']:
            raise ValueError('independent retokenization mismatch')
    if len({item['id'] for item in dataset['items']})!=200:
        raise ValueError('reused request identity')
    for domain in DOMAINS:
        items=[item for item in dataset['items'] if item['suite']==domain]
        if (len(items)!=20 or sum(item['input_band']=='short' for item in items)!=10 or
                sum(item['id'] in dataset['panel_ids'] for item in items)!=4 or
                sum(item['id'] in dataset['panel_ids'] and item['input_band']=='short' for item in items)!=2):
            raise ValueError('wrong domain/input-stratum panel coverage')
    for source in dataset['sources']:
        if source['revision']!=REVISIONS[source['repo']] or hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('pinned public source changed')
    return dict(passed=True,known_author_dev_checked=100,unique_requests=200,panel=40,
                exact_and_near_overlap=0,independent_retokenization_passed=True,source_sha256_passed=True,
                dataset_sha256=summary['dataset_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private', type=Path, required=True)
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--source-cache',type=Path)
    args = parser.parse_args()
    prepare(args.private.resolve(), args.public.resolve(),args.source_cache)
