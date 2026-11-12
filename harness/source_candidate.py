"""Freeze bounded, option-controlled edits against a pinned stock tree."""

import ast
import hashlib
import json
from pathlib import Path
import re
import shutil

from harness.build_engine import SKIP_DIRS, tree_sha
from harness.candidate import check_inputs, check_tree, digest, validate_spec
from harness.experiment_executor import local_path


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_patch(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4194304:
        raise ValueError('bounded regular source-option JSON required')
    patch = json.loads(path.read_text())
    if patch.get('schema') == 'source-option-v1' and path.stat().st_size > 131072:
        raise ValueError('legacy source-option JSON exceeds its original limit')
    return validate_patch(patch)


def validate_patch(patch):
    if (not isinstance(patch, dict) or set(patch) != {'schema', 'option_id', 'edits'} or
            patch['schema'] not in ('source-option-v1','source-option-v2') or not isinstance(patch['option_id'], str) or
            not re.fullmatch('[a-z][a-z0-9-]{0,63}', patch['option_id'])):
        raise ValueError('invalid source option manifest')
    extended = patch['schema'] == 'source-option-v2'
    if not isinstance(patch['edits'], list) or not 1 <= len(patch['edits']) <= (128 if extended else 8):
        raise ValueError('source edit count exceeds this option protocol')
    for edit in patch['edits']:
        if not isinstance(edit, dict) or set(edit) != {'path', 'base_sha256', 'find', 'replace'}:
            raise ValueError('unexpected source edit fields')
        name = edit['path']
        suffixes = ('.py','.cu','.cuh','.cpp','.cc','.c','.h','.hpp') if extended else ('.py',)
        creating = extended and edit['base_sha256'] is None
        if (not isinstance(name, str) or not name.startswith(('python/sglang/srt/', 'python/sglang/kernels/')) or
                not name.endswith(suffixes) or any(part in ('', '.', '..') or part.startswith('.') for part in name.split('/')) or
                (not creating and not re.fullmatch('[0-9a-f]{64}', str(edit['base_sha256'])))):
            raise ValueError('only declared stock runtime or kernel source files can be edited')
        if (not isinstance(edit['find'], str) or (edit['find'] != '' if creating else not edit['find']) or
                not isinstance(edit['replace'], str) or edit['find'] == edit['replace'] or
                len(edit['find'].encode()) + len(edit['replace'].encode()) > 32768):
            raise ValueError('bounded non-noop exact replacement required')
    return patch


def validate_action(action):
    fields = {'kind', 'patch', 'self_check', 'per_suite', 'max_new_tokens', 'reason'}
    if not isinstance(action, dict) or set(action) != fields or action['kind'] != 'run_source':
        raise ValueError('structured source-option experiment required')
    for field, suffix in [('patch', '.json'), ('self_check', '.py')]:
        name = action[field]
        if (not isinstance(name, str) or not name.startswith('scratch/') or not name.endswith(suffix) or
                any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError('bounded scratch patch and CPU self-check required')
    if type(action['per_suite']) is not int or not 1 <= action['per_suite'] <= 6:
        raise ValueError('invalid public dev coverage')
    if type(action['max_new_tokens']) is not int or action['max_new_tokens'] not in (256, 2048):
        raise ValueError('unsupported generation cap')
    if not isinstance(action['reason'], str) or not 1 <= len(action['reason']) <= 4000:
        raise ValueError('bounded falsifiable rationale required')
    return action


def cpu_receipt(work, records, action):
    validate_action(action)
    expected = {name: file_sha(local_path(work, name)) for name in (action['patch'], action['self_check'])}
    for path in sorted(Path(records).glob('tools-*/action-*/response.json'), reverse=True):
        response = json.loads(path.read_text())
        value = json.loads(response['contentItems'][0]['text'])
        if (response['success'] and value.get('exit_code') == 0 and
                value.get('code_sha256') == expected[action['self_check']] and
                all(value.get('workspace_file_sha256', {}).get(name) == sha for name, sha in expected.items())):
            return dict(path=str(path), sha256=file_sha(path), files=expected)
    raise ValueError('run successful CPU self-check after writing the current patch and self-check')


def apply_edits(stock, patch):
    validate_patch(patch)
    outputs = {}
    originals = {}
    for edit in patch['edits']:
        name = edit['path']
        source = local_path(stock, name)
        if patch['schema'] == 'source-option-v2' and edit['base_sha256'] is None:
            if source.exists() or name in outputs:
                raise ValueError('new source file must not overwrite an existing or previously created file')
            outputs[name] = edit['replace']
            originals[name] = None
            continue
        if not source.is_file() or source.stat().st_size > 1048576:
            raise ValueError('bounded existing stock file required')
        original = source.read_text()
        if file_sha(source) != edit['base_sha256']:
            raise ValueError('source edit is based on a different stock version')
        current = outputs.get(name, original)
        if current.count(edit['find']) != 1:
            raise ValueError('source edit anchor must occur exactly once')
        outputs[name] = current.replace(edit['find'], edit['replace'], 1)
        originals[name] = original
    if any(outputs[name] == originals[name] for name in outputs):
        raise ValueError('source edits cancel to a no-op')
    for name, content in outputs.items():
        if name.endswith('.py'):
            ast.parse(content, filename=name)
    return outputs


def build_bundle(base, patch_path, directory):
    check_inputs(base)
    if base['value'] != base['stock_default']:
        raise ValueError('source experiments must keep startup settings at stock')
    patch = read_patch(patch_path)
    outputs = apply_edits(base['stock_engine'], patch)
    directory = Path(directory).absolute()
    if directory.is_relative_to(Path(base['stock_engine'])):
        raise ValueError('source output cannot be inside stock')
    directory.mkdir(parents=True, exist_ok=False)
    engine = directory / 'engine'
    shutil.copytree(base['stock_engine'], engine, symlinks=True,
        ignore=shutil.ignore_patterns(*SKIP_DIRS, '*.pyc', '*.pyo'))
    for name, content in outputs.items():
        (engine / name).parent.mkdir(parents=True, exist_ok=True)
        (engine / name).write_text(content)
    checksum = tree_sha(engine)
    (engine / 'TREE_SHA').write_text(checksum + '\n')
    manifest = dict(schema='source-option-bundle-v1', base=base, patch=patch,
        option_default=False, stock_tree_sha=base['stock_tree_sha'], candidate_tree_sha=checksum,
        changed_files={name: file_sha(engine / name) for name in outputs})
    manifest['spec_sha256'] = digest(manifest)
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return load_bundle(directory)


def load_bundle(directory):
    directory = Path(directory).absolute()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if (set(manifest) != {'schema', 'base', 'patch', 'option_default', 'stock_tree_sha',
            'candidate_tree_sha', 'changed_files', 'spec_sha256'} or
            manifest['schema'] != 'source-option-bundle-v1' or manifest['option_default'] is not False or
            manifest['spec_sha256'] != digest({key: value for key, value in manifest.items() if key != 'spec_sha256'})):
        raise ValueError('source bundle manifest changed')
    base = validate_spec(manifest['base'])
    check_inputs(base)
    if manifest['stock_tree_sha'] != base['stock_tree_sha'] or base['value'] != 8:
        raise ValueError('source baseline/startup settings changed')
    check_tree(directory / 'engine', manifest['candidate_tree_sha'])
    outputs = apply_edits(base['stock_engine'], manifest['patch'])
    if manifest['changed_files'] != {name: hashlib.sha256(content.encode()).hexdigest() for name, content in outputs.items()}:
        raise ValueError('source edit receipt differs')
    stock_files = {path.relative_to(Path(base['stock_engine'])).as_posix(): path
        for path in Path(base['stock_engine']).rglob('*') if path.is_file() and
        path.name != 'TREE_SHA' and not any(part in SKIP_DIRS for part in path.parts) and path.suffix not in ('.pyc', '.pyo')}
    actual_files = {path.relative_to(directory / 'engine').as_posix() for path in (directory / 'engine').rglob('*')
        if path.is_file() and path.name != 'TREE_SHA' and not any(part in SKIP_DIRS for part in path.parts) and path.suffix not in ('.pyc', '.pyo')}
    if actual_files != set(stock_files) | set(outputs):
        raise ValueError('source bundle adds or removes unauthorized files')
    for name, source in stock_files.items():
        expected = manifest['changed_files'].get(name, file_sha(source))
        if file_sha(directory / 'engine' / name) != expected:
            raise ValueError('source bundle differs outside the declared edits')
    for name, expected in manifest['changed_files'].items():
        if file_sha(directory / 'engine' / name) != expected:
            raise ValueError('declared source file content changed')
    return manifest


def candidate_arm(directory, *, enabled=False):
    if type(enabled) is not bool:
        raise ValueError('source option mode must be an explicit boolean')
    manifest = load_bundle(directory)
    base = manifest['base']
    return dict(name='candidate', block=8,
        tree_sha=manifest['candidate_tree_sha'] if enabled else base['stock_tree_sha'],
        engine=str(Path(directory).absolute() / 'engine') if enabled else base['stock_engine'],
        env={}, option_enabled=enabled, source_option=manifest['patch']['option_id'],
        spec_sha256=manifest['spec_sha256'])
