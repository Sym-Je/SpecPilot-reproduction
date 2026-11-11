"""Prepare unchanged public dev tasks with continuous, irrelevant text prefixes."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controller.http_transport import sha_ids
from exp.long_context_resource import command, feedback
from exp.engine_resource import execute
from exp.p3_pair_run import arm_specs, clean_environment, load_requests
from harness.engine_research import Budget, save
from harness.gpu_autonomy import digest
from harness.prefix_context import CONDITIONS, PROTOCOL, SUITES, text_sha, validate

LOCAL_FILES = ('exp/long_context.py', 'exp/prefix_context_resource.py', 'exp/prefix_context_quality.py',
    'harness/prefix_context.py', 'harness/test_prefix_context.py')
BOOKS = ('moby-dick', 'war-and-peace', 'middlemarch')


def tokenize(directory):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B', local_files_only=True)
    originals = load_requests(2, SUITES, tokenizer)
    indexed = {}
    for suite in SUITES:
        for line in (ROOT / 'assets/upstream/dev' / (suite + '.jsonl')).read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                indexed[item['id']] = item
    documents = []
    tokens = {}
    for name in BOOKS:
        path = directory / (name + '.txt')
        tokens[name] = tokenizer.encode(path.read_text(), add_special_tokens=False)
        documents.append(dict(name=name, path=str(path), sha256=digest(path)))
    marker = 'SPEC_PREFIX_QUESTION_MARKER_54D13'
    rendered = tokenizer.apply_chat_template([dict(role='user', content=marker)], tokenize=False,
        add_generation_prompt=True, enable_thinking=True)
    before, after = rendered.split(marker)
    prefix_ids = tokenizer.encode(before, add_special_tokens=False)
    bases, requests = [], []
    for original in originals:
        item = indexed[original['id']]
        question = item['turns'][0]
        suffix_text = '\n\n-----\n\n' + question + after
        suffix_ids = tokenizer.encode(suffix_text, add_special_tokens=False)
        assert tokenizer.decode(suffix_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False) == suffix_text
        name = BOOKS[int(hashlib.sha256(original['id'].encode()).hexdigest(), 16) % len(BOOKS)]
        needed = int(CONDITIONS[-1]) - len(prefix_ids) - len(suffix_ids)
        if needed < 1 or len(tokens[name]) < needed:
            raise ValueError('public document is too short or original question too long')
        base = dict(original, question=question, question_sha256=text_sha(question), document=name,
            question_suffix_ids=suffix_ids, chat_prefix_ids=prefix_ids, document_prefix_ids=tokens[name][:needed])
        bases.append(base)
        for condition in CONDITIONS:
            if condition == 'original':
                input_ids = original['input_ids']
            else:
                count = int(condition) - len(prefix_ids) - len(suffix_ids)
                if count < 1:
                    raise ValueError('original question does not fit requested input length')
                input_ids = prefix_ids + tokens[name][:count] + suffix_ids
            requests.append(dict(id=original['id'] + '-ctx-' + condition, base_id=original['id'], suite=original['suite'],
                condition=condition, context_tokens=len(input_ids), input_ids=input_ids, input_sha256=sha_ids(input_ids),
                question_sha256=base['question_sha256']))
    requests.sort(key=lambda item: (CONDITIONS.index(item['condition']), SUITES.index(item['suite']), item['base_id']))
    data = dict(protocol=PROTOCOL, base_requests=bases, requests=requests, documents=documents)
    validate(data)
    save(directory / 'data.json', data)
    print(json.dumps(dict(original_lengths=[len(item['input_ids']) for item in originals], prepared_requests=len(requests))))


def prepare(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    previous = ROOT / 'logs/long-context-20261111-a01/sp-longctx-20261111-a01'
    previous_record = json.loads((previous / 'request.json').read_text())
    for document in previous_record['documents']:
        source = Path(document['path'])
        if source.stem not in BOOKS or digest(source) != document['sha256']:
            raise ValueError('previously frozen public book identity differs')
        shutil.copyfile(source, directory / source.name)
    subprocess.run(['/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python', '-B',
        str(Path(__file__).resolve()), 'tokenize', '--directory', str(directory)], check=True, cwd=ROOT, timeout=300)
    data = json.loads((directory / 'data.json').read_text())
    pin = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '--', 'exp', 'harness', 'controller', 'agents',
        'assets/upstream/dev', 'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'], cwd=ROOT, text=True).splitlines()
    names = sorted({name for name in names if Path(name).suffix in ('.py', '.sh', '.json', '.jsonl')} | set(LOCAL_FILES))
    hashes = {}
    with tarfile.open(directory / 'source.tar', 'w') as archive:
        for name in names:
            payload = (ROOT / name).read_bytes() if name in LOCAL_FILES else subprocess.check_output(['git', 'show', pin + ':' + name], cwd=ROOT)
            hashes[name] = hashlib.sha256(payload).hexdigest()
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(payload))
    arms, config = arm_specs(['stock', 'final'], clean_environment())
    save(directory / 'request.json', dict(data, action=dict(per_suite=2, max_new_tokens=2048), arms=arms,
        source_pin=pin, models=config['models'], source_archive=dict(path=str(directory / 'source.tar'),
            sha256=digest(directory / 'source.tar'), files=hashes)))
    print(json.dumps(dict(prepared=True, submitted=False, requests=50, conditions=CONDITIONS)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'tokenize', 'plan', 'execute', 'resume'))
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--deadline', type=int, default=7200)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.command == 'prepare':
        prepare(directory)
        return
    if args.command == 'tokenize':
        tokenize(directory)
        return
    if not 600 <= args.deadline <= 7200:
        raise ValueError('deadline outside bounded adapter range')
    if args.command == 'plan':
        import shlex
        print(shlex.join(command(directory / 'request.json', directory / 'source.tar', directory / 'remote', directory.name, args.deadline)))
        return
    budget = Budget(directory.parent / 'resource-state.json', limits=dict(gpu_seconds=28800, wall_seconds=43200, concurrent_gpus=2))
    result = execute(directory, directory / 'source.tar', budget, resume_only=args.command == 'resume',
        command_factory=command, feedback_loader=feedback, deadline=args.deadline)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
