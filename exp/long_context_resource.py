"""Freeze public long documents and use the existing bounded NorthJob execution unit."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from exp.engine_resource import command as engine_command, execute
from exp.long_context import CAP, LENGTHS, PROTOCOL, audit, validate_requests
from exp.p3_pair_run import arm_specs, clean_environment
from controller.http_transport import sha_ids
from harness.engine_research import Budget, save
from harness.gpu_autonomy import digest

DOCUMENTS = (('moby-dick', 2701), ('war-and-peace', 2600), ('middlemarch', 145))
LOCAL_FILES = ('exp/long_context.py', 'exp/long_context_resource.py', 'exp/long_context_remote.sh',
               'harness/test_long_context.py')


def command(request, source, output, name, deadline):
    bootstrap = ROOT / 'exp/long_context_remote.sh'
    result = engine_command(request, source, output, name, deadline)
    result[-1] = shlex.join(['env', 'SP_LONGCTX_BOOTSTRAP_SHA=' + digest(bootstrap),
        'SP_LONGCTX_SOURCE_SHA=' + digest(source), 'SP_LONGCTX_REQUEST_SHA=' + digest(request),
        'bash', str(bootstrap), str(request), str(source), str(output), str(deadline)])
    return result


def tokenize(directory):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained('/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B', local_files_only=True)
    marker = 'SPECPILOT_DOCUMENT_CONTENT_3B1F77'
    prompt = ('Read the following continuous excerpt from a novel.\n\n' + marker +
        '\n\nSummarize the narrative presented so far. Identify the central characters, important events, '
        'relationships and unresolved conflicts supported by this excerpt. Do not assume events outside it.')
    rendered = tokenizer.apply_chat_template([dict(role='user', content=prompt)], tokenize=False,
        add_generation_prompt=True, enable_thinking=True)
    prefix_text, suffix_text = rendered.split(marker)
    prefix = tokenizer.encode(prefix_text, add_special_tokens=False)
    suffix = tokenizer.encode(suffix_text, add_special_tokens=False)
    requests = []
    documents = []
    for name, identifier in DOCUMENTS:
        path = directory / f'{name}.txt'
        tokens = tokenizer.encode(path.read_text(), add_special_tokens=False)
        if len(tokens) < max(LENGTHS) - len(prefix) - len(suffix):
            raise ValueError('document is too short; do not repeat text: ' + name)
        documents.append(dict(name=name, url=f'https://www.gutenberg.org/ebooks/{identifier}.txt.utf-8',
            path=str(path), sha256=digest(path), document_tokens=len(tokens)))
        for length in LENGTHS:
            input_ids = prefix + tokens[:length - len(prefix) - len(suffix)] + suffix
            requests.append(dict(id=f'{name}-ctx-{length}', suite='novel-summary', document=name,
                context_tokens=length, input_ids=input_ids, input_sha256=sha_ids(input_ids)))
    requests.sort(key=lambda item: (item['context_tokens'], item['document']))
    validate_requests(requests)
    save(directory / 'data.json', dict(requests=requests, documents=documents,
        tokenizer=tokenizer.__class__.__name__, thinking=True, max_new_tokens=CAP))


def prepare(directory):
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, identifier in DOCUMENTS:
        with urllib.request.urlopen(f'https://www.gutenberg.org/ebooks/{identifier}.txt.utf-8', timeout=90) as response:
            payload = response.read(16 * 1024 * 1024)
        if len(payload) < 600000 or b'Gutenberg' not in payload[:10000]:
            raise ValueError('unexpected public book response: ' + name)
        (directory / f'{name}.txt').write_bytes(payload)
    subprocess.run(['/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python', '-B',
        str(Path(__file__).resolve()), 'tokenize', '--directory', str(directory)], cwd=ROOT, timeout=300, check=True)
    data = json.loads((directory / 'data.json').read_text())
    pin = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '--', 'exp', 'harness', 'controller',
        'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'], cwd=ROOT, text=True).splitlines()
    names = sorted(set(name for name in names if Path(name).suffix in ('.py', '.sh', '.json')) | set(LOCAL_FILES))
    hashes = {}
    with tarfile.open(directory / 'source.tar', 'w') as archive:
        for name in names:
            payload = (ROOT / name).read_bytes() if name in LOCAL_FILES else subprocess.check_output(
                ['git', 'show', pin + ':' + name], cwd=ROOT)
            hashes[name] = hashlib.sha256(payload).hexdigest()
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(payload))
    arms, config = arm_specs(['stock', 'final'], clean_environment())
    save(directory / 'request.json', dict(protocol=PROTOCOL, action=dict(per_suite=3, max_new_tokens=CAP),
        **data, arms=arms, source_pin=pin, source_archive=dict(path=str(directory / 'source.tar'),
            sha256=digest(directory / 'source.tar'), files=hashes), models=config['models']))
    print(json.dumps(dict(prepared=True, submitted=False, requests=len(data['requests']), lengths=LENGTHS)), flush=True)


def feedback(output, record):
    result = audit(output)
    if result != json.loads((output / 'result.json').read_text()):
        raise ValueError('independent long-context replay differs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'tokenize', 'plan', 'execute', 'resume'))
    parser.add_argument('--directory', type=Path, required=True)
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
        raise ValueError('deadline outside existing adapter bounds')
    if args.command == 'plan':
        print(shlex.join(command(directory / 'request.json', directory / 'source.tar', directory / 'remote',
            directory.name, args.deadline)))
        return
    budget = Budget(directory.parent / 'resource-state.json', limits=dict(
        gpu_seconds=28800, wall_seconds=43200, concurrent_gpus=2))
    result = execute(directory, directory / 'source.tar', budget, resume_only=args.command == 'resume',
        command_factory=command, feedback_loader=feedback, deadline=args.deadline)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
