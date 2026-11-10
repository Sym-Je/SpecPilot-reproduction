"""Author final sampling compatibility and physically paired dev performance."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import signal
import statistics
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from controller.http_transport import Arm,HttpPairBench,sha_ids
from controller.scored_forcing import read_reference
from controller.scoring import NativeClient,server_arguments
from exp.candidate_smoke import CandidateServer
from exp.diagnosis import digest
from exp.p3_pair_run import Server,clean_environment,gpu_lock,interrupted,run_round,wait_for_idle
from harness.engine_research import save
from harness.sampling_protocol import SEEDS,TEMPERATURES,non_argmax_count,parameters,summarize,validate_measurement


class SamplingServer(CandidateServer):
    def launch_spec(self):
        return Server.launch_spec(self)


def identity(client,arm):
    declared=client.server_identity(arm['tree_sha'])
    actual=server_arguments(read_reference(declared['evidence'],client.raw_dir.parent)['response'])
    required=dict(speculative_algorithm='DFLASH',speculative_num_draft_tokens=arm['block'],dtype='bfloat16',
        model_path='/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B',
        speculative_draft_model_path='/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2',
        disable_radix_cache=True,random_seed=0)
    if any(actual.get(key)!=value for key,value in required.items()):
        raise ValueError('actual server launch differs from frozen author arm')
    return declared


def check_request(path):
    record=json.loads(Path(path).read_text())
    source=record['source_archive']
    if digest(source['path'])!=source['sha256'] or digest(record['config']['path'])!=record['config']['sha256']:
        raise ValueError('frozen input identity changed')
    with tarfile.open(source['path']) as archive:
        for name,checksum in source['files'].items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=checksum:
                raise ValueError('frozen source member differs')
    return record


def generate(client,item,temperature,seed,rid,*,logprobs=False):
    body=dict(input_ids=item['input_ids'],sampling_params=dict(parameters(temperature,seed),max_new_tokens=128),rid=rid)
    if logprobs:
        body.update(return_logprob=True,top_logprobs_num=5)
    previous=client.last_evidence
    try:
        response=client.post('/generate',body)
        return dict(ok=True,evidence=client.last_evidence,non_argmax=non_argmax_count(response))
    except Exception as error:
        return dict(ok=False,error=str(error),evidence=client.last_evidence if client.last_evidence!=previous else None)


def probe(record,directory,gpus,environment):
    selected=[next(item for item in record['requests'] if item['suite']==suite) for suite in ('gsm8k','humaneval','mt-bench')]
    samples=[]
    with ExitStack() as resources:
        clients=[]
        for index,arm in enumerate(record['arms']):
            root=directory/arm['name']
            root.mkdir()
            server=SamplingServer(arm,gpus[index],30600+index*10,root,environment)
            resources.callback(server.stop)
            server.start()
            clients.append((server,NativeClient(f'http://127.0.0.1:{server.port}',root/'raw',timeout=300),arm))
        identities=[]
        for server,client,arm in clients:
            server.wait_ready(1200)
            identities.append(identity(client,arm))
        save(directory/'identities.json',identities)
        for item in selected:
            for temperature in TEMPERATURES:
                for seed in SEEDS:
                    sample=dict(id=item['id'],temperature=temperature,seed=seed)
                    for _,client,arm in clients:
                        sample[arm['name']]=generate(client,item,temperature,seed,
                            f"probe-{item['id']}-t{temperature}-s{seed}")
                    samples.append(sample)
                    save(directory/'samples.json',samples)
                    print(json.dumps(dict(event='sampling-probe',id=item['id'],temperature=temperature,seed=seed,
                        stock_ok=sample['stock']['ok'],final_ok=sample['final']['ok'])),flush=True)
        extras=[]
        for temperature in (.7,1.):
            sample=dict(temperature=temperature,id=selected[0]['id'])
            for _,client,arm in clients:
                sample[arm['name']]=generate(client,selected[0],temperature,0,f'logprob-t{temperature}',logprobs=True)
            extras.append(sample)
        save(directory/'logprob-probes.json',extras)


class SamplingArm(Arm):
    def __init__(self,*args,temperature,arm_spec,**options):
        super().__init__(*args,**options)
        self.temperature=temperature
        self.generator=identity(NativeClient(self.url,self.raw_dir.parent/f'{self.name}-identity'),arm_spec)

    def step(self,input_ids,max_new,warmup=0,rid=None):
        match=re.search(r'@s([01])(?:$|\|)',rid or '')
        seed=int(match[1]) if match else 0
        self.sampling=parameters(self.temperature,seed)
        result=super().step(input_ids,max_new,warmup=warmup,rid=rid)
        return dict(result,sampling=dict(self.sampling),generator=self.generator)


def measure(record,directory,gpus,environment):
    requests=[dict(item,id=item['id']+f'@s{seed}',base_id=item['id'],seed=seed) for item in record['requests'] for seed in SEEDS]
    for number in (0,1):
        root=directory/f'round-{number+1:02d}'
        def factory(name,url,**options):
            options['raw_dir']=root/f'{name}-raw'
            options['trace_timing']=True
            return SamplingArm(name,url,temperature=record['temperature'],arm_spec=next(arm for arm in record['arms'] if arm['name']==name),**options)
        def bench(first,second):
            return HttpPairBench(first,second,synchronized_start=True,reverse_submission=bool(number))
        run_round(record['arms'],gpus,[30620,30630],number,requests,root,environment,2048,2,1200,
            server_factory=SamplingServer,arm_factory=factory,bench_factory=bench)
        wait_for_idle([0,1])


def run(request,directory):
    record=check_request(request)
    for name,checksum in record['source_archive']['files'].items():
        if digest(ROOT/name)!=checksum:
            raise ValueError('runtime source differs from archive')
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    signal.signal(signal.SIGTERM,interrupted)
    with ExitStack() as resources:
        gpus=wait_for_idle([0,1])
        for gpu in gpus:
            resources.enter_context(gpu_lock(gpu))
        save(directory/'manifest.json',dict(request_path=str(request),request_sha256=digest(request),gpus=gpus))
        if record['phase']=='probe':
            probe(record,directory,gpus,clean_environment())
        else:
            measure(record,directory,gpus,clean_environment())
        save(directory/'cleanup.json',wait_for_idle([0,1]))
    result=audit(directory)
    save(directory/'result.json',result)
    print(json.dumps(result),flush=True)


def audit(directory):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    if digest(manifest['request_path'])!=manifest['request_sha256']:
        raise ValueError('request changed')
    record=check_request(manifest['request_path'])
    if record['phase']=='probe':
        samples=json.loads((directory/'samples.json').read_text())
        conditions={}
        supported=[]
        for temperature in TEMPERATURES:
            arm_results={}
            for arm in ('stock','final'):
                rows=[row for row in samples if row['temperature']==temperature]
                outputs=defaultdict(dict)
                errors=[]
                for row in rows:
                    result=row[arm]
                    if not result['ok']:
                        errors.append(result['error'])
                        continue
                    packet=read_reference(result['evidence'],directory)
                    item=next(item for item in record['requests'] if item['id']==row['id'])
                    expected=dict(input_ids=item['input_ids'],sampling_params=dict(parameters(temperature,row['seed']),max_new_tokens=128),
                        rid=f"probe-{row['id']}-t{temperature}-s{row['seed']}")
                    if packet['request']!=expected or packet['http_status']!=200 or not packet['response'].get('output_ids'):
                        raise ValueError('sampling request/response drift')
                    outputs[row['id']][row['seed']]=packet['response']['output_ids']
                varied=sum(value.get(0)!=value.get(1) for value in outputs.values() if set(value)=={0,1})
                arm_results[arm]=dict(successes=sum(len(value) for value in outputs.values()),errors=errors,
                    seed_variant_prompts=varied,sampling_observed=not errors and len(rows)==6 and (temperature==0 or varied>0))
            conditions[str(temperature)]=arm_results
            if temperature>0 and all(value['sampling_observed'] for value in arm_results.values()):
                supported.append(str(temperature))
        return dict(protocol='author-final-sampling-probe-v1',conditions=conditions,supported_temperatures=supported,
            performance_measured=False,distributional_correctness_tested=False,ledger_eligible=False)
    pairs=[]
    for number in (1,2):
        root=directory/f'round-{number:02d}'
        rows=[json.loads(line) for line in (root/'pairs.jsonl').read_text().splitlines()]
        if json.loads((root/'complete.json').read_text())!=dict(round=number,pairs=40):
            raise ValueError('physical round incomplete')
        deployment=json.loads((root/'deployment.json').read_text())
        assigned=manifest['gpus'] if number==1 else list(reversed(manifest['gpus']))
        if [row['gpu']['uuid'] for row in deployment['assignments']]!=[gpu['uuid'] for gpu in assigned]:
            raise ValueError('physical GPU swap differs')
        for pair in rows:
            base,seed=pair['id'].rsplit('@s',1)
            item=next(item for item in record['requests'] if item['id']==base)
            for key,arm,gpu in zip(('a','b'),record['arms'],assigned):
                sample=pair[key]
                raw=read_reference(sample['raw_evidence'],directory)
                expected=dict(parameters(record['temperature'],int(seed)),max_new_tokens=2048)
                if (raw['request']['input_ids']!=item['input_ids'] or raw['request']['sampling_params']!=expected or
                        raw['response']['output_ids']!=sample['output_ids'] or sample['input_sha256']!=sha_ids(item['input_ids']) or
                        sample['gpu_uuid']!=gpu['uuid'] or sample['tree_sha']!=arm['tree_sha'] or
                        sample['tokens']!=len(sample['output_ids']) or sample['tokens']!=raw['response']['meta_info']['completion_tokens']):
                    raise ValueError('sampling measurement binding differs')
                validate_measurement(sample,raw,item['input_ids'],record['temperature'],int(seed))
                actual=server_arguments(read_reference(sample['generator']['evidence'],directory)['response'])
                if (sample['generator']['tree_sha']!=arm['tree_sha'] or actual.get('speculative_num_draft_tokens')!=arm['block'] or
                        actual.get('speculative_algorithm')!='DFLASH'):
                    raise ValueError('generator identity differs')
            pairs.append(pair)
    lengths={}
    for key,name in (('a','stock'),('b','final')):
        rows=[pair[key] for pair in pairs]
        lengths[name]=dict(tokens_mean=statistics.mean(row['tokens'] for row in rows),
            tokens_median=statistics.median(row['tokens'] for row in rows),
            latency_median_s=statistics.median(row['latency_s'] for row in rows),
            cap_count=sum(row['finish_reason']=='length' for row in rows),
            stop_count=sum(row['finish_reason']=='stop' for row in rows),
            zero_spec_verify_count=sum(not row['spec_verify_ct'] for row in rows),
            reported_tokens_per_counter_median=statistics.median(row['tau'] for row in rows if row['tau'] is not None)
                if any(row['tau'] is not None for row in rows) else None,
            counter_warning='final TLV counter not guaranteed comparable to stock acceptance length')
    per_round={str(number):summarize([dict(pair,round=1 if pair['round']==number else pair['round']) for pair in []],record['requests'])
        for number in ()}
    import math
    per_round={str(number):math.exp(statistics.mean(math.log(pair['b']['tokens_per_s']/pair['a']['tokens_per_s'])
        for pair in pairs if pair['round']==number)) for number in (1,2)}
    return dict(protocol='author-final-sampling-measure-v1',temperature=record['temperature'],
        length_and_counter_summary=lengths,per_round_geomean=per_round,**summarize(pairs,record['requests']))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('run','audit'))
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--request',type=Path)
    args=parser.parse_args()
    if args.command=='run':
        run(args.request,args.directory)
    else:
        print(json.dumps(audit(args.directory),sort_keys=True))


if __name__=='__main__':
    main()
