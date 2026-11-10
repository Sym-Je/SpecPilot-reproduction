"""MCP broker for SpecPilot roles; all model-visible actions are capability gated."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from prepare_baseline import ROOT, OUT, write, sha
from experiment_lifecycle import wait_final, failure_diagnostics

REPO = ROOT / 'vendor/SpecPilot-reproduction'
sys.path.insert(0, str(REPO))
from harness.experiment_executor import local_path
from cpu_sandbox import execute_python

SOURCE_ROOTS = {
    'vllm': ROOT / 'vendor/vllm-0.30.0/vllm',
    'vllm_ascend': ROOT / '.venv/lib/python3.12/site-packages/vllm_ascend',
    'ascendc': ROOT / '.venv/lib/python3.12/site-packages/vllm_ascend/_cann_ops_custom/vendors/custom_transformer/op_impl/ai_core/tbe/custom_transformer_impl/ascendc',
    'binding_reference': ROOT / 'ascend-v99k/experiments/e4_hc_pre_a0/stock-source/vllm-ascend-c09d3e20b9c45c80b34ae3781440d90904a44023/csrc',
}
SOURCE_SUFFIXES = {'.py', '.cpp', '.h', '.hpp'}


def source_files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in SOURCE_SUFFIXES and not p.is_symlink())
SCHEMAS = {
    'read_evidence': {'name': {'type': 'string', 'enum': ['baseline', 'hardware', 'model', 'deployment', 'budget', 'prior_research', 'cache_initialization']}},
    'list_source': {'tree': {'type': 'string', 'enum': list(SOURCE_ROOTS)}, 'prefix': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}},
    'read_source': {'tree': {'type': 'string', 'enum': list(SOURCE_ROOTS)}, 'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}},
    'write_scratch': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
    'run_cpu': {'path': {'type': 'string'}},
    'launch_experiment': {'id': {'type': 'string'}, 'config': {'type': 'object'}, 'mode': {'type': 'string', 'enum': ['benchmark', 'profile', 'cache_init']}},
    'wait_experiment': {'id': {'type': 'string'}, 'seconds': {'type': 'integer', 'minimum': 0, 'maximum': 1200}},
    'read_profile': {'id': {'type': 'string'}, 'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}},
    'search_source': {'tree': {'type': 'string', 'enum': list(SOURCE_ROOTS)}, 'query': {'type': 'string'}, 'prefix': {'type': 'string'}},
    'submit_patch': {'path': {'type': 'string'}, 'rationale': {'type': 'string'}},
}
DESCRIPTIONS = {
    'read_evidence': 'Read frozen development-only baseline, hardware, model, launch configuration, or remaining API budget.',
    'list_source': 'List authorized installed stock engine Python/C++/header files, including the AscendC tree; no controller, dataset or credentials access.',
    'read_source': 'Read at most 12000 characters of one authorized stock Python/C++/header source file at a byte-independent character offset.',
    'write_scratch': 'Write a bounded .py/.json/.patch file in your own scratch directory. This does not modify the deployment.',
    'run_cpu': 'Execute your scratch Python analysis inside a chroot, dropped UID and seccomp CPU sandbox: no network, devices, subprocess, host reads or writes; 3 CPU seconds. Standard-library analysis modules only.',
    'launch_experiment': 'Serial 8-NPU configuration benchmark or bounded diagnostic CPU+NPU profile; restores baseline. Config: max_num_batched_tokens, max_num_seqs, gpu_memory_utilization, enable_prefix_caching, enforce_eager, num_speculative_tokens, additional_config. screen_concurrency=1/8/32. Profile additionally accepts profile_stratum=short/mid/long, profile_phase=prefill/decode, profile_steps=1..32 (default 8). Profile launches the stated concurrent dev requests, caps output at 128, and records actual activity. Decode collection requires all requests to reach first token; if no window exists it fails explicitly. Offline export checks eight ranks and loss warnings. Profile timing is diagnostic, never a benchmark gain. No model, precision, topology, sampling or split changes.',
    'wait_experiment': 'Wait for trusted experiment progress/result without launching or duplicating work. Up to 1200 seconds; no model billing while waiting. Measurements are serial screening, not formal paired promotion.',
    'read_profile': 'Read at most 12000 characters from an owned completed experiment CSV under traces. Use profile_summary.csv_files for paths. No request or model output files are exposed.',
    'search_source': 'Literal search in authorized engine Python/C++/headers, at most 30 matching lines and 12000 characters. Use a path prefix to narrow the search.',
    'submit_patch': 'Submit a scratch patch for independent admission review. Records a proposal; does not execute or auto-approve code.',
}


def normalize_source_prefix(tree, prefix):
    if tree not in SOURCE_ROOTS or not isinstance(prefix, str):
        raise ValueError('Invalid source prefix')
    if prefix.startswith('/') or '..' in prefix.split('/'):
        raise ValueError('Invalid prefix')
    if prefix == tree or prefix == '.':
        return ''
    if prefix.startswith(tree + '/'):
        return prefix[len(tree) + 1:]
    return prefix


class Broker:
    def __init__(self, role, mode):
        if not re.fullmatch(r'[a-z0-9-]{1,80}', role): raise ValueError('Invalid role')
        if mode not in ('master', 'direction', 'probe'): raise ValueError('Invalid mode')
        self.role, self.mode = role, mode
        self.directory = OUT / 'research' / 'roles' / role
        self.work = self.directory / 'scratch'
        self.work.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.log = self.directory / 'broker.jsonl'
        self.statefile = self.directory / 'broker-state.json'
        allocation = self.directory / 'allocation.json'
        self.allocation = json.loads(allocation.read_text()) if allocation.exists() else {'max_experiments': 3, 'max_actions': 160}
        shared_access = OUT / 'research/profile-export-access.json'
        if shared_access.exists() and not self.allocation.get('analysis_only'):
            self.allocation['shared_profile_csvs'] = json.loads(shared_access.read_text())['shared_profile_csvs']
        self.state = json.loads(self.statefile.read_text()) if self.statefile.exists() else {'actions': 0, 'experiments': []}

    def names(self):
        if self.allocation.get('analysis_only'):
            return [n for n in SCHEMAS if n not in ('launch_experiment', 'wait_experiment')]
        if self.mode == 'direction': return list(SCHEMAS)
        if self.mode == 'probe': return ['read_evidence', 'list_source', 'read_source', 'write_scratch', 'run_cpu']
        return ['read_evidence', 'list_source', 'read_source', 'search_source'] + (['read_profile'] if self.allocation.get('shared_profile_csvs') else [])

    def source(self, tree, name):
        if tree not in SOURCE_ROOTS: raise ValueError('Unknown source tree')
        root = SOURCE_ROOTS[tree].resolve()
        p = local_path(root, name)
        if p.suffix not in SOURCE_SUFFIXES or not p.is_file(): raise ValueError('Only stock Python/C++/header source files are readable')
        return p

    def evidence(self, name):
        if name == 'baseline':
            state = json.loads((OUT / 'baseline-state.json').read_text())
            return {'status': state['status'], 'rows': state['rows'], 'split': 'dev',
                    'protocol': json.loads((OUT / 'plan.json').read_text()),
                    'limitations': 'Serial absolute measurements; C1 has 4 samples per input bucket. No candidate promotion or accuracy certificate.'}
        if name == 'hardware':
            return {'NPU': '8x Ascend 910B2C', 'HBM_per_NPU_GiB': 64, 'cube_cores': 24, 'vector_cores': 48,
                    'CPU': json.loads((ROOT / 'profiling/serial-experiments/exp241-v4flash-bench/host-hardware-snapshot.json').read_text()),
                    'peak_HBM_GB_s': None, 'peak_FLOP_s': None,
                    'constraint': 'Do not invent peak bandwidth/FLOPS. Distinguish serialized device time, overlap, wall time, and measured attainable limits. Use source tensor shapes/bytes and profile evidence before claiming theoretical headroom.'}
        if name == 'model':
            return json.loads((ROOT / 'models/DeepSeek-V4-Flash-0731-w8a8/config.json').read_text())
        if name == 'deployment':
            return {'launch_script': (OUT / 'launch-mrv1.sh').read_text(),
                    'configuration_only_capabilities': True,
                    'profile_workload': {'concurrency_options': [1, 8, 32], 'strata': ['short', 'mid', 'long'],
                                         'output_cap': 128, 'multi_request_profile_supported': True,
                                         'bounded_worker_steps': [1, 32], 'requires_eight_rank_quality_check': True},
                    'patches': 'Source/kernel patches can be submitted for independent review; not auto-executed by the broker.'}
        if name == 'prior_research':
            return json.loads((OUT / 'prior-dev-research.json').read_text())
        if name == 'cache_initialization':
            receipt=OUT/'research/cache-init-observations.json'
            facts=OUT/'research/cache-init-group-facts.json'
            if not receipt.is_file() or not facts.is_file():return {'status':'not_collected','full_prefix_capability_ready':False}
            observed=json.loads(receipt.read_text())
            if observed.get('baseline_restored') is not True:
                return {'status':'restoration_pending','full_prefix_capability_ready':False}
            if (receipt.is_symlink() or facts.is_symlink() or facts.stat().st_size>16384):
                raise ValueError('Invalid bounded metadata artifact')
            if (self.allocation.get('analysis_only') and self.allocation.get('shared_cache_init_facts_sha256')!=sha(facts)):
                raise ValueError('Initialization facts are outside this independent role frozen brief')
            return {'status':'observed_caching_off_initialization_only','full_prefix_capability_ready':False,
                    'experiment_status':observed.get('status'),
                    'initial_restoration_failed':observed.get('initial_restoration_failed',False),
                    'source_sha256':sha(facts),'facts':json.loads(facts.read_text())}
        if name == 'budget':
            ledger = 'billing-gpt' if os.environ.get('SP_BUDGET_PHASE') == 'gpt' else 'billing'
            x = json.loads((OUT / ledger / 'state.json').read_text())
            return {k: x[k] for k in ('limit_micro_usd', 'conservative_reserved_micro_usd', 'observed_gateway_delta_micro_usd', 'stopped')}
        raise ValueError('Evidence name not authorized')

    def act(self, name, args):
        if name not in self.names() or set(args) != set(SCHEMAS[name]):
            raise ValueError('Unknown or malformed capability')
        if self.state['actions'] >= self.allocation['max_actions']: raise RuntimeError('Role action budget exhausted')
        self.state['actions'] += 1; write(self.statefile, self.state)
        action_id = f"{self.role}-T{self.state['actions']:04d}"
        if name == 'read_evidence':
            result = self.evidence(args['name'])
            from parallel_evidence import shared_updates
            updates = shared_updates(OUT, analysis_only=self.allocation.get('analysis_only', False))
            if updates:
                result = dict(result, shared_research_updates=updates)
        elif name == 'list_source':
            root = SOURCE_ROOTS[args['tree']].resolve()
            prefix = normalize_source_prefix(args['tree'], args['prefix'])
            names = sorted(str(p.relative_to(root)) for p in source_files(root)
                           if not p.is_symlink() and str(p.relative_to(root)).startswith(prefix))
            offset = args['offset']; assert type(offset) is int and offset >= 0
            result = {'total': len(names), 'offset': offset, 'files': names[offset:offset + 80],
                      'requested_prefix': args['prefix'], 'resolved_prefix': prefix}
        elif name == 'read_source':
            p = self.source(args['tree'], args['path'])
            offset = args['offset']; assert type(offset) is int and offset >= 0
            content = p.read_text(); result = {'path': args['path'], 'sha256': sha(p), 'offset': offset,
                                             'total_chars': len(content), 'content': content[offset:offset + 12000]}
        elif name == 'search_source':
            tree, prefix, query = args['tree'], args['prefix'], args['query']
            if tree not in SOURCE_ROOTS or not isinstance(query, str) or not 2 <= len(query) <= 128: raise ValueError('Invalid search')
            prefix = normalize_source_prefix(tree, prefix)
            root = SOURCE_ROOTS[tree].resolve(); matches = []
            searched_files = 0
            for path in source_files(root):
                relative = str(path.relative_to(root))
                if not relative.startswith(prefix) or path.is_symlink(): continue
                path = self.source(tree, relative)
                searched_files += 1
                for line_number, line in enumerate(path.read_text().splitlines(), 1):
                    if query in line:
                        matches.append({'path': relative, 'line': line_number, 'text': line[:300]})
                        if len(matches) >= 30: break
                if len(matches) >= 30: break
            result = {'matches': matches, 'limit': 30, 'truncated_at_limit': len(matches) == 30,
                      'requested_prefix': args['prefix'], 'resolved_prefix': prefix,
                      'searched_files': searched_files}
            if not matches:
                result['search_guidance'] = ('No files matched this prefix; list_source can locate directories.'
                    if searched_files == 0 else 'No literal match. A multi-word query is one exact phrase; search one symbol at a time.')
        elif name == 'write_scratch':
            p = local_path(self.work, args['path'])
            if p.suffix not in ('.py', '.json', '.patch') or len(args['content'].encode()) > 65536:
                raise ValueError('Invalid scratch file')
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(args['content'])
            result = {'path': args['path'], 'sha256': sha(p)}
        elif name == 'run_cpu':
            result = execute_python(self.work, args['path'], self.directory / 'cpu' / action_id)
        elif name == 'launch_experiment':
            from experiment_runner import validate_config
            if args['config'].get('enable_prefix_caching') is True:
                admission=OUT/'research/prefix-inference-admission.json'
                if (not admission.is_file() or admission.is_symlink()
                        or self.allocation.get('prefix_inference_admission_sha256')!=sha(admission)):
                    raise ValueError('Separate enabled-prefix inference admission required; initialization metadata is insufficient')
            if args['mode']=='cache_init':
                admission=OUT/'research/cache-init-admission.json'
                if (not admission.exists() or self.allocation.get('cache_init_admission_sha256')!=sha(admission)):
                    raise ValueError('Explicit independent initialization-capture admission required')
                record=json.loads(admission.read_text())
                review=OUT/'research/parallel/roles/review-prefix-cache-init-metadata/result.json'
                if (record.get('adapter_sha256')!=sha(OUT/'cache_metadata_diag.py')
                        or record.get('review_sha256')!=sha(review)
                        or json.loads(review.read_text())['report']['decision']!='admit_initialization_capture_only'
                        or args['config']!={'cache_init_metadata':True}):
                    raise ValueError('Initialization admission source or scope mismatch')
            elif args['config'].get('cache_init_metadata'):
                raise ValueError('Initialization metadata cannot run a generation mode')
            experiment_id = args['id']
            if not re.fullmatch(r'[a-z0-9-]{1,60}', experiment_id): raise ValueError('Invalid experiment ID')
            validate_config(args['config'])
            if args['mode'] not in ('benchmark', 'profile','cache_init'): raise ValueError('Unknown experiment mode')
            experiment_id = self.role + '-' + experiment_id
            folder = OUT / 'experiments' / experiment_id
            if folder.exists():
                original = json.loads((folder / 'request.json').read_text())
                assert original['config'] == args['config'] and original['mode'] == args['mode'], 'ID conflicts with another request'
                assert original['role'] == self.role
                if not (folder / 'submission.json').exists(): raise RuntimeError('Submission outcome uncertain; do not resubmit')
                if experiment_id not in self.state['experiments']:
                    self.state['experiments'].append(experiment_id); write(self.statefile, self.state)
                result = {'id': experiment_id, 'already_submitted': True}
            else:
                if len(self.state['experiments']) >= self.allocation['max_experiments']: raise RuntimeError('Direction experiment allocation exhausted; Master may allocate the next direction')
                for prior_id in self.state['experiments']:
                    from experiment_lifecycle import cleanup_pending
                    prior_state = json.loads((OUT / 'experiments' / prior_id / 'state.json').read_text())
                    if (prior_state['status'] not in ('complete', 'failed') or cleanup_pending(prior_state)
                            or (prior_state.get('lock_acquired_epoch') and prior_state.get('baseline_restored') is not True)):
                        raise RuntimeError('Prior experiment must finish restoration before another submission')
                folder.mkdir(mode=0o700, parents=True)
                request = {'id': experiment_id, 'role': self.role, 'config': args['config'], 'mode': args['mode'],
                           'split': 'dev', 'created_epoch': time.time(), 'source_sha256': sha(OUT / 'experiment_runner.py'),
                           'execution_pins': {name: sha(OUT / name) for name in ('experiment_runner.py', 'profile_workload.py', 'activity_watchdog.py', 'run_baseline.py', 'audit_baseline.py', 'prepare_baseline.py', 'launch-mrv1.sh', 'plan.json', 'baseline-input-manifest.json')},
                           'installed_engine_manifest_sha256': sha(OUT / 'installed-engine-source-manifest.json')}
                if args['config'].get('cpu_work_metadata'):
                    request['execution_pins'].update({name:sha(OUT/name) for name in
                        ('sparse_work_diag.py','sparse_work_export.py','runtime/sitecustomize.py','runtime/network_guard.py')})
                if args['mode']=='cache_init':
                    request['execution_pins'].update({name:sha(OUT/name) for name in
                        ('cache_metadata_diag.py','cache_init_export.py','runtime/sitecustomize.py','runtime/network_guard.py','research/cache-init-admission.json')})
                write(folder / 'request.json', request)
                with (folder / 'supervisor.log').open('xb') as log:
                    p = subprocess.Popen([str(ROOT / '.venv/bin/python'), str(OUT / 'experiment_runner.py'),
                                          '--id', experiment_id], cwd=ROOT, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                         env={k: v for k, v in os.environ.items() if not any(s in k.lower() for s in ('key', 'token', 'secret', 'proxy'))})
                write(folder / 'submission.json', {'pid': p.pid, 'created_epoch': time.time()})
                self.state['experiments'].append(experiment_id); write(self.statefile, self.state)
                result = {'id': experiment_id, 'submitted': True, 'pid': p.pid, 'status': 'queued'}
        elif name == 'wait_experiment':
            if args['id'] not in self.state['experiments']: raise ValueError('Experiment not owned by this direction')
            if type(args['seconds']) is not int or not 0 <= args['seconds'] <= 1200: raise ValueError('Invalid wait')
            folder = OUT / 'experiments' / args['id']
            result = wait_final(folder / 'state.json', args['seconds'])
            if result['status'] == 'failed': result.update(failure_diagnostics(folder, result))
        elif name == 'read_profile':
            access=OUT/'research/profile-export-access.json'
            if access.exists() and not self.allocation.get('analysis_only'):
                self.allocation['shared_profile_csvs']=json.loads(access.read_text())['shared_profile_csvs']
            shared = self.allocation.get('shared_profile_csvs', {}).get(args['id'], {})
            owned = args['id'] in self.state['experiments']
            if not owned and args['path'] not in shared:
                raise ValueError('Experiment not owned or explicitly shared')
            folder = OUT / 'experiments' / args['id']
            state = json.loads((folder / 'state.json').read_text())
            if state['status'] not in ('complete', 'failed'): raise ValueError('Profile is not yet finalized')
            path = local_path(folder / 'traces', args['path'])
            if path.suffix != '.csv' or not path.is_file() or path.stat().st_size > 64 * 1024**2: raise ValueError('Only bounded trace CSVs')
            if not owned and sha(path) != shared[args['path']]:
                raise ValueError('Shared profile changed after evidence freeze')
            offset = args['offset']
            if type(offset) is not int or offset < 0: raise ValueError('Invalid offset')
            content = path.read_text(errors='replace')
            result = {'path': args['path'], 'sha256': sha(path), 'total_chars': len(content), 'offset': offset, 'content': content[offset:offset + 12000]}
        elif name == 'submit_patch':
            p = local_path(self.work, args['path'])
            if p.suffix != '.patch' or not p.is_file(): raise ValueError('Existing scratch patch required')
            result = {'status': 'candidate_pending_independent_admission', 'patch_sha256': sha(p),
                      'rationale': args['rationale'], 'executed': False}
            write(self.directory / (action_id + '-patch-proposal.json'), result | {'path': str(p)})
        else:
            raise AssertionError(name)
        record = {'id': action_id, 'epoch': time.time(), 'tool': name, 'arguments': args, 'result': result}
        with self.log.open('a') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
        return {'action_id': action_id, 'result': result}


def reply(request, result=None, error=None):
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], **({'error': error} if error else {'result': result})}, ensure_ascii=False), flush=True)


def serve(role, mode):
    for k in list(os.environ):
        if any(s in k.lower() for s in ('api_key', 'claude_key', 'northgate_key', 'deepseek_key')):
            del os.environ[k]
    broker = Broker(role, mode)
    for line in sys.stdin:
        request = json.loads(line)
        if 'id' not in request: continue
        method = request.get('method')
        if method == 'initialize':
            reply(request, {'protocolVersion': request.get('params', {}).get('protocolVersion', '2024-11-05'),
                            'capabilities': {'tools': {}}, 'serverInfo': {'name': 'specpilot-ascend', 'version': '1'}})
        elif method == 'ping': reply(request, {})
        elif method == 'tools/list':
            reply(request, {'tools': [{'name': n, 'description': DESCRIPTIONS[n], 'inputSchema': {
                'type': 'object', 'properties': SCHEMAS[n], 'required': list(SCHEMAS[n]), 'additionalProperties': False}}
                for n in broker.names()]})
        elif method == 'tools/call':
            try:
                params = request['params']; result = broker.act(params['name'], params.get('arguments', {}))
                reply(request, {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'isError': False})
            except Exception as exc:
                with broker.log.open('a') as f:
                    f.write(json.dumps({'epoch': time.time(), 'status': 'denied_or_failed',
                        'tool': request.get('params', {}).get('name'),
                        'arguments': request.get('params', {}).get('arguments'),
                        'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False) + '\n')
                reply(request, {'content': [{'type': 'text', 'text': f'{type(exc).__name__}: {exc}'}], 'isError': True})
        else: reply(request, error={'code': -32601, 'message': 'Unsupported broker method'})


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', required=True)
    parser.add_argument('--mode', choices=('master', 'direction', 'probe'), required=True)
    args = parser.parse_args()
    serve(args.role, args.mode)
