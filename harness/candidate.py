"""Versioned startup-option candidates; no source overlays or promotion authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from harness.build_engine import SKIP_DIRS, _skip, tree_sha


FIELDS = {'schema', 'candidate_id', 'kind', 'option', 'stock_default', 'value',
          'stock_engine', 'stock_tree_sha', 'config_path', 'config_sha256',
          'target', 'draft', 'source_pin', 'spec_sha256'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) != FIELDS:
        raise ValueError('unexpected candidate manifest fields')
    if (spec['schema'] != 'startup-candidate-v1' or spec['kind'] != 'startup-option' or
            spec['candidate_id'] != 'draft-budget-probe' or spec['option'] != 'draft_tokens' or
            type(spec['stock_default']) is not int or spec['stock_default'] != 8 or
            type(spec['value']) is not int or not 1 <= spec['value'] <= 64):
        raise ValueError('unsupported candidate option or invalid budget')
    for name, length in [('stock_tree_sha', 64), ('config_sha256', 64), ('source_pin', 40), ('spec_sha256', 64)]:
        if not isinstance(spec[name], str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', spec[name]):
            raise ValueError('invalid candidate identity')
    for name in ('stock_engine', 'config_path', 'target', 'draft'):
        if not isinstance(spec[name], str) or not Path(spec[name]).is_absolute():
            raise ValueError('candidate paths must be absolute')
    if spec['spec_sha256'] != digest({key: value for key, value in spec.items() if key != 'spec_sha256'}):
        raise ValueError('candidate manifest digest changed')
    return spec


def check_tree(directory, expected):
    directory = Path(directory)
    if directory.is_symlink() or not all((directory / name).is_dir() for name in ('python', 'lab')):
        raise ValueError('missing concrete engine directories')
    for path in directory.rglob('*'):
        if _skip(path.relative_to(directory)) or not path.is_symlink():
            continue
        try:
            safe = (not path.readlink().is_absolute() and path.resolve().is_relative_to(directory.resolve())
                    and path.resolve().is_file())
        except RuntimeError:
            safe = False
        if not safe:
            raise ValueError('engine symlinks must resolve to internal relative files')
    if (directory / 'TREE_SHA').read_text().strip() != expected or tree_sha(directory) != expected:
        raise ValueError('engine content differs from its bound canonical hash')


def make_spec(stock_engine, config_path, target, draft, source_pin, *, value=8):
    stock_engine, config_path = Path(stock_engine).absolute(), Path(config_path).absolute()
    expected = (stock_engine / 'TREE_SHA').read_text().strip()
    check_tree(stock_engine, expected)
    config = json.loads(config_path.read_text())
    if config.get('stock', {}).get('block_size') != 8:
        raise ValueError('this adapter requires the frozen H100 stock block size 8')
    spec = dict(schema='startup-candidate-v1', candidate_id='draft-budget-probe', kind='startup-option',
                option='draft_tokens', stock_default=8, value=value, stock_engine=str(stock_engine),
                stock_tree_sha=expected, config_path=str(config_path),
                config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
                target=target, draft=draft, source_pin=source_pin)
    spec['spec_sha256'] = digest(spec)
    return validate_spec(spec)


def check_inputs(spec):
    validate_spec(spec)
    if hashlib.sha256(Path(spec['config_path']).read_bytes()).hexdigest() != spec['config_sha256']:
        raise ValueError('baseline config changed')
    check_tree(spec['stock_engine'], spec['stock_tree_sha'])


def build_bundle(spec, directory):
    check_inputs(spec)
    directory = Path(directory).absolute()
    if directory.is_relative_to(Path(spec['stock_engine'])):
        raise ValueError('candidate output must be outside the stock engine')
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copytree(spec['stock_engine'], directory / 'engine', symlinks=True,
                    ignore=shutil.ignore_patterns(*SKIP_DIRS, '*.pyc', '*.pyo'))
    check_tree(directory / 'engine', spec['stock_tree_sha'])
    for name, value in [('manifest.json', spec), ('build.json', dict(spec_sha256=spec['spec_sha256'],
            stock_tree_sha=spec['stock_tree_sha'], candidate_tree_sha=spec['stock_tree_sha'],
            kind='stock-copy; startup-option only; no source overlay'))]:
        with (directory / name).open('x') as destination:
            json.dump(value, destination, indent=2)
            destination.write('\n')


def load_bundle(directory):
    directory = Path(directory).absolute()
    spec = validate_spec(json.loads((directory / 'manifest.json').read_text()))
    check_inputs(spec)
    check_tree(directory / 'engine', spec['stock_tree_sha'])
    receipt = json.loads((directory / 'build.json').read_text())
    expected = dict(spec_sha256=spec['spec_sha256'], stock_tree_sha=spec['stock_tree_sha'],
                    candidate_tree_sha=spec['stock_tree_sha'],
                    kind='stock-copy; startup-option only; no source overlay')
    if receipt != expected:
        raise ValueError('candidate build receipt changed')
    return spec


def candidate_arm(directory, *, enabled=False):
    if type(enabled) is not bool:
        raise ValueError('candidate mode must be an explicit boolean')
    spec = load_bundle(directory)
    return dict(name='candidate', block=spec['value'] if enabled else spec['stock_default'],
                tree_sha=spec['stock_tree_sha'], engine=str(Path(directory).absolute() / 'engine'),
                env={}, candidate_id=spec['candidate_id'], spec_sha256=spec['spec_sha256'],
                option_enabled=enabled)


def launch_environment(environment, arm, spec, gpu_uuid, port):
    validate_spec(spec)
    clean = {key: value for key, value in environment.items()
             if not key.startswith('SPECPILOT_') or key == 'SPECPILOT_DATA'}
    clean.update(SP_KIND='stock', SP_ENGINE=arm['engine'], SP_TARGET=spec['target'], SP_DRAFT=spec['draft'],
                 CUDA_VISIBLE_DEVICES=gpu_uuid, PORT=str(port), NCCL_PORT=str(port + 1),
                 DRAFT_TOKENS=str(arm['block']), PYTHONDONTWRITEBYTECODE='1')
    return clean


def expected_arguments(spec, block):
    return dict(model_path=spec['target'], dtype='bfloat16', speculative_algorithm='DFLASH',
                speculative_draft_model_path=spec['draft'], speculative_num_draft_tokens=block,
                enable_fp32_lm_head=False, kv_cache_dtype='auto', mamba_ssm_dtype='float32',
                attention_backend='fa3', mem_fraction_static=.90, max_running_requests=4,
                cuda_graph_max_bs_decode=4, chunked_prefill_size=8192,
                disable_radix_cache=True, random_seed=0)


def check_identity(identity, spec, block):
    expected = expected_arguments(spec, block)
    if identity.get('tree_sha') != spec['stock_tree_sha'] or any(
            identity.get('server_args', {}).get(key) != value for key, value in expected.items()):
        raise ValueError('actual server identity does not match the frozen candidate launch')
