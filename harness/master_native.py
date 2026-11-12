"""Prepare a native inherited-permission Master and report post-task file changes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


ROOT=Path(__file__).resolve().parents[1]
RULES=('config.json','docs/02-acceptance.md','docs/06-gates.md','docs/09-p3-harness-validation.md',
    'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json')


def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')


def entry(path):
    metadata=path.lstat()
    common=dict(mode=stat.S_IMODE(metadata.st_mode))
    if path.is_symlink():return dict(common,kind='symlink',target=os.readlink(path))
    if not path.is_file():return dict(common,kind='nonregular')
    return dict(common,kind='file',size=metadata.st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def snapshot(root):
    root=Path(root).resolve();files={}
    for name in ('controller','ledger'):
        directory=root/name
        if directory.is_symlink():files[name]=entry(directory);continue
        if not directory.exists():continue
        for current,directories,names in os.walk(directory,followlinks=False):
            directories[:]=sorted(name for name in directories if name!='__pycache__')
            for name in directories+sorted(names):
                path=Path(current)/name
                if path.is_symlink() or not path.is_dir():files[path.relative_to(root).as_posix()]=entry(path)
    for name in RULES:
        path=root/name
        if path.exists() or path.is_symlink():files[name]=entry(path)
    return dict(files=files,scope=dict(trees=['controller','ledger'],rule_files=list(RULES)),
        sealed_or_credentials_scanned=False)


def prepare(root,directory):
    root=Path(root).resolve();directory=Path(directory).absolute()
    if directory.resolve().parent!=root/'logs':raise ValueError('new direct-child logs directory required')
    before=snapshot(root)
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    save(directory/'before.json',before)
    manifest=dict(schema='native-master-prompt-only-v1',repository=str(root),directory=str(directory),
        permission_mode='inherit-parent-native',role_specific_enforcement='prompt-only',fork_context=False,
        model_override=None,gpu_authorized=False,platform_sandbox_and_approvals_unchanged=True,
        before_sha256=hashlib.sha256((directory/'before.json').read_bytes()).hexdigest(),
        read_audit_limitation='File snapshots cannot establish that protected data was never read.')
    save(directory/'manifest.json',manifest)
    return manifest


def check(root,directory):
    root=Path(root).resolve();directory=Path(directory).resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    if (manifest['repository']!=str(root) or manifest['directory']!=str(directory) or
            hashlib.sha256((directory/'before.json').read_bytes()).hexdigest()!=manifest['before_sha256']):
        raise ValueError('post-task comparison does not match the original baseline')
    before=json.loads((directory/'before.json').read_text());after=snapshot(root)
    changed={name:dict(before=before['files'].get(name),after=after['files'].get(name))
        for name in sorted(set(before['files'])|set(after['files']))
        if before['files'].get(name)!=after['files'].get(name)}
    result=dict(schema='native-master-postcheck-v1',protected_files_unchanged=not changed,changed=changed,
        coverage=after['scope'],forbidden_reads_verified=False,read_compliance='not_proven_by_file_snapshot',
        platform_permission_equivalence='native inheritance; not an independently widened host permission',
        scientific_correctness_verified=False,performance_verified=False)
    save(directory/'after.json',after);save(directory/'postcheck.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','check'))
    parser.add_argument('--directory',type=Path,required=True)
    arguments=parser.parse_args()
    result=prepare(ROOT,arguments.directory) if arguments.command=='prepare' else check(ROOT,arguments.directory)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
