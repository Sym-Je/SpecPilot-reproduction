"""CPU tokenizer-only aggregate prefix ceilings on frozen dev replay cases.

No generation, cache configuration change, prompt/token-ID export, or model API
billing. Exact admission order, warmup payloads and residency are not simulated.
"""
import array
import ast
import collections
import fcntl
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from prepare_baseline import ROOT,OUT,sha,write


def reuse_ceiling(sequences,alignment):
    seen=set();full_seen=set();total=0;reused=0;repeat_reused=0;hist=collections.Counter()
    for tokens in sequences:
        total+=len(tokens);previous=b'';hashes=[]
        for offset in range(0,len(tokens)-alignment+1,alignment):
            block=array.array('I',tokens[offset:offset+alignment]).tobytes()
            previous=hashlib.sha256(previous+block).digest();hashes.append(previous)
        usable=0
        for index,digest in enumerate(hashes):
            if (index+1)*alignment>len(tokens)-1 or digest not in seen:break
            usable=(index+1)*alignment
        full=hashlib.sha256(array.array('I',tokens).tobytes()).digest()
        if full in full_seen:repeat_reused+=usable
        reused+=usable
        label='0' if usable==0 else '<4K' if usable<4096 else '4K-8K' if usable<8192 else '8K-16K' if usable<16384 else '16K-32K' if usable<32768 else '>=32K'
        hist[label]+=1;seen.update(hashes);full_seen.add(full)
    return {'total_input_tokens':total,'reusable_prefix_tokens_upper_bound':reused,
            'retained_suffix_tokens_lower_bound':total-reused,'exact_repeated_request_reuse_tokens':repeat_reused,
            'nonidentical_prompt_prefix_reuse_tokens':reused-repeat_reused,'reuse_length_histogram':dict(hist),
            'scope':'Capacity-unconstrained file-order scenario. Full earlier prefixes assumed published before subsequent lookup; not actual concurrent cache hits.'}


def backend_names(source):
    tree=ast.parse(source.read_text());result={}
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and node.name.startswith('AscendDSA'):
            for fn in node.body:
                if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) and fn.name=='get_name':
                    values=[x.value.value for x in ast.walk(fn) if isinstance(x,ast.Return) and isinstance(x.value,ast.Constant) and isinstance(x.value.value,str)]
                    if len(values)==1:result[node.name]=values[0]
    return result


def main():
    area=OUT/'research/prefix-reuse-audit';area.mkdir(exist_ok=True)
    state={'status':'waiting_for_readonly_slot','pid':__import__('os').getpid(),'started_epoch':time.time()};write(area/'state.json',state)
    with (ROOT/'evaluation/npu-workload.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8000/v1/models',timeout=10) as f:models=json.load(f)
        assert any(m['id']=='deepseek-v4-flash' for m in models['data']), 'Expected baseline tokenizer is not serving'
        layer=ROOT/'.venv/lib/python3.12/site-packages/vllm_ascend/models/layer/attention/layer.py'
        dsa=ROOT/'.venv/lib/python3.12/site-packages/vllm_ascend/attention/dsa_v1.py'
        names=backend_names(dsa)
        assert names and not any(v in ('TRITON_MLA','FLASHINFER') for v in names.values())
        manifest=json.loads((OUT/'baseline-input-manifest.json').read_text())
        token_cache={};cases=[]
        state.update(status='tokenizing_frozen_development_inputs',completed_cases=0);write(area/'state.json',state)
        for case in manifest['cases']:
            source=Path(case['input_path'])
            assert source.resolve().parent==(OUT/'baseline-inputs').resolve() and sha(source)==case['input_sha256']
            entries=json.loads(source.read_text())['data'];sequences=[]
            for entry in entries:
                payload=entry['payloads'][0]
                for message in payload['messages']:
                    content=message.get('content')
                    assert content is None or isinstance(content,str) or isinstance(content,list) and all(x.get('type')=='text' for x in content),'Only text inputs are authorized for this audit'
                request={k:payload[k] for k in ('messages','tools','chat_template_kwargs') if k in payload}
                request['model']='deepseek-v4-flash';request['add_generation_prompt']=True
                request.setdefault('chat_template_kwargs',{})['reasoning_effort']=payload.get('reasoning_effort','high')
                raw=json.dumps(request,ensure_ascii=False).encode();key=hashlib.sha256(raw).digest()
                if key not in token_cache:
                    query=urllib.request.Request('http://127.0.0.1:8000/tokenize',data=raw,headers={'Content-Type':'application/json'})
                    with opener.open(query,timeout=60) as f:response=json.load(f)
                    tokens=response['tokens'];assert len(tokens)==response['count'] and all(type(t) is int and t>=0 for t in tokens)
                    token_cache[key]=tokens
                tokens=token_cache[key];expected=case['requests'][entry['session_id']]['input_tokens']
                assert len(tokens)==expected,f'Token count calibration mismatch: expected {expected}, observed {len(tokens)}'
                sequences.append(tokens)
            cases.append({'case':case['name'],'stratum':case['stratum'],'concurrency':case['concurrency'],
                'requests':len(entries),'source_sha256':sha(source),'warmup_count_configured':case['warmups'],
                'alignment_scenarios':{str(a):reuse_ceiling(sequences,a) for a in (32,128,4096)},
                'schedule_and_residency_feasible_reuse':None,'warmup_assisted_reuse':None,
                'missing':'Exact warmup payload/admission schedule and prospective cache residency are not available. Alignment scenarios are not a resolved effective cache alignment.'})
            state['completed_cases']=len(cases);write(area/'state.json',state)
            print(json.dumps({'case':case['name'],'requests':len(entries),'token_counts_match_frozen_manifest':True}),flush=True)
        report={'status':'complete','scope':'CPU-only tokenizer and aggregate data-reuse audit, no generation/cache change/NPU launch',
            'unique_tokenized_payloads':len(token_cache),'input_manifest_sha256':sha(OUT/'baseline-input-manifest.json'),
            'tokenizer_source_sha256':sha(ROOT/'vendor/vllm-0.30.0/vllm/tokenizers/deepseek_v4.py'),
            'baseline_launch_sha256':sha(OUT/'launch-mrv1.sh'),'backend_names':names,
            'support_gate':{'identified_disable_guard_applies':False,'guard_source_sha256':sha(layer),
                'baseline_prefix_caching_enabled':False,'candidate_effective_enable_tested':False,
                'all_required_state_restoration_proven':False,'eligibility':'Unresolved: source guard does not match these backend names, but cache/state restoration still requires independent support review before a configuration experiment.'},
            'cases':cases,'limitations':['No raw prompts, token IDs, request IDs or per-prefix hashes are exported; token arrays/digests stay in process memory.',
                'Overlap ceilings do not establish actual cache hits, runtime support, capacity feasibility, elapsed-time savings or model correctness.',
                'No holdout or retired validation is read. Data order and source hashes are preserved.']}
        write(area/'summary.json',report);state.update(status='complete',completed_epoch=time.time());write(area/'state.json',state)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        p=OUT/'research/prefix-reuse-audit/state.json'
        state=json.loads(p.read_text()) if p.exists() else {}
        state.update(status='needs_attention',error=repr(error));write(p,state);raise
