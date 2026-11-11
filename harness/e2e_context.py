"""Faithful stock metadata export; no attribution, headroom or ranking is inferred."""

import json
from pathlib import Path

from exp.phase4_run import reference


MODEL_FIELDS=frozenset(('architectures','model_type','dtype','torch_dtype','hidden_size','intermediate_size',
    'num_hidden_layers','num_attention_heads','num_key_value_heads','head_dim','vocab_size','tie_word_embeddings',
    'layer_types','linear_num_key_heads','linear_num_value_heads','linear_key_head_dim','linear_value_head_dim'))
SERVER_FIELDS=frozenset(('dtype','speculative_algorithm','speculative_num_draft_tokens','enable_fp32_lm_head',
    'kv_cache_dtype','mamba_ssm_dtype','attention_backend','mem_fraction_static','max_running_requests',
    'cuda_graph_max_bs_decode','chunked_prefill_size','disable_radix_cache','random_seed'))
ROW_FIELDS=('round','prompt_tokens','completion_tokens','tokens','latency_s','tokens_per_s','spec_verify_ct',
    'tau','max_new_tokens')


def model_metadata(value):
    result={key:value[key] for key in sorted(MODEL_FIELDS) if key in value}
    if isinstance(value.get('text_config'),dict):
        result['text_config']=model_metadata(value['text_config'])
    return result


def server_metadata(value):
    return {key:value[key] for key in sorted(SERVER_FIELDS) if key in value}


def export_context(profile,timing,*,canonical_tree):
    profile,timing=Path(profile).resolve(),Path(timing).resolve()
    manifest_path=profile/'manifest.json'
    manifest=json.loads(manifest_path.read_text())
    if manifest['identity']['tree_sha']!=canonical_tree:
        raise ValueError('metadata is not from the authorized canonical stock')
    sources=[reference(manifest_path)];configs={}
    for arm in ('target','draft'):
        path=profile/f'inputs/{arm}/config.json'
        if path.is_symlink() or reference(path)['sha256']!=manifest['files'][str(path.relative_to(profile))]:
            raise ValueError('model configuration source SHA differs')
        configs[arm]=model_metadata(json.loads(path.read_text()))
        sources.append(reference(path))
    server=server_metadata(manifest['identity']['server_args'])
    rows=[]
    for ordinal in (1,2):
        directory=timing/f'round-{ordinal:02d}';path=directory/'stock.jsonl'
        sources.append(reference(path))
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if (row['arm']!='stock' or row['tree_sha']!=canonical_tree or row['round']!=ordinal or
                    row['generator']['server_args']!=manifest['identity']['server_args']):
                raise ValueError('timing row is not the matching canonical stock configuration')
            raw=Path(row['raw_evidence']['path'])
            if (raw.is_symlink() or raw.resolve().parent!=directory/'stock-raw' or
                    reference(raw)!=row['raw_evidence']):
                raise ValueError('normal stock raw source SHA/path differs')
            sources.append(reference(raw))
            rows.append({key:row[key] for key in ROW_FIELDS})
    if not rows:
        raise ValueError('normal stock timing is unavailable')
    return dict(schema='stock-e2e-context-v1',tree_sha=canonical_tree,server_args=server,model_configs=configs,
        normal_requests=rows,sources=sources,critical_path_fractions=None,normal_requests_are_profile_workload=False,
        limitations=['Configuration metadata does not certify the active LM-head, dtype, graph bucket or consumers.',
            'Normal cap256 stock timings are historical public dev observations, not this profile workload or new measurements.',
            'Request latency includes prefill and all exposed overhead; latency/verify is not pure decode step time.',
            'The separately supplied profile has perturbation; kernel work/union/shape facts are not end-to-end critical-path fractions.',
            'Only stock facts were exported; no prompts, token IDs, candidate implementation or other role reasoning.'])
