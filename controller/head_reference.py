"""Independent checkpoint FP32 head and equivalent reordered-reduction control."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.http_transport import sha_ids
from controller.scoring import NativeClient


def reduce_head(weight, hidden, chunks=1, reverse=False):
    if (weight.ndim != 2 or hidden.ndim != 1 or weight.shape[1] != len(hidden) or
            type(chunks) is not int or not 1 <= chunks <= len(hidden)):
        raise ValueError('invalid FP32 head reduction dimensions or chunks')
    boundaries = [(index * len(hidden) // chunks, (index + 1) * len(hidden) // chunks) for index in range(chunks)]
    if reverse:
        boundaries.reverse()
    result = None
    for start, stop in boundaries:
        partial = weight[:, start:stop] @ hidden[start:stop]
        result = partial if result is None else result + partial
    return result


class FP32Head:
    def __init__(self, target, device):
        import torch
        from safetensors import safe_open

        torch.backends.cuda.matmul.allow_tf32 = False
        torch.set_float32_matmul_precision('highest')
        self.torch, self.device = torch, device
        target = Path(target)
        index_path = target / 'model.safetensors.index.json'
        index = json.loads(index_path.read_text())['weight_map']
        shard = target / index['lm_head.weight']
        with safe_open(shard, framework='pt', device='cpu') as source:
            tensor = source.get_tensor('lm_head.weight')
        if tuple(tensor.shape) != (248320, 5120) or tensor.dtype != torch.bfloat16:
            raise ValueError('unexpected target LM head shape or checkpoint dtype')
        tensor_sha = hashlib.sha256(memoryview(tensor.contiguous().view(torch.uint8).numpy())).hexdigest()
        self.weight = tensor.to(device=device, dtype=torch.float32)
        if not bool(torch.isfinite(self.weight).all()):
            raise ValueError('nonfinite checkpoint LM head')
        self.identity = dict(checkpoint=str(target), tensor_sha256=tensor_sha,
            index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
            config_sha256=hashlib.sha256((target / 'config.json').read_bytes()).hexdigest(),
            shape=list(tensor.shape), checkpoint_dtype=str(tensor.dtype), compute_dtype='torch.float32',
            tf32=False, chunks=8, reversed_accumulation=True, device=str(device),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def evaluate(self, response):
        values = response.get('hidden_states', response.get('meta_info', {}).get('hidden_states'))
        while isinstance(values, list) and len(values) == 1 and isinstance(values[0], list):
            values = values[0]
        if not isinstance(values, list) or len(values) != 5120 or any(isinstance(value, list) for value in values):
            raise ValueError('last hidden state is not one target hidden vector')
        torch = self.torch
        hidden = torch.tensor(values, dtype=torch.float32, device=self.device)
        with torch.inference_mode():
            direct = reduce_head(self.weight, hidden)
            reverse = reduce_head(self.weight, hidden, chunks=8, reverse=True)
            token = int(response['output_ids'][0])
            output_probability = response['meta_info']['output_token_logprobs'][0]
            if output_probability[1] != token:
                raise ValueError('native output probability is shifted')
            direct_lp, reverse_lp = torch.log_softmax(direct, dim=0), torch.log_softmax(reverse, dim=0)
            canonical_token, reverse_token = int(direct.argmax()), int(reverse.argmax())
            result = dict(native_token=token, canonical_token=canonical_token, reverse_token=reverse_token,
                native_logprob=output_probability[0], canonical_native_logprob=float(direct_lp[token]),
                reverse_native_logprob=float(reverse_lp[token]),
                max_logit_difference=float((direct - reverse).abs().max()),
                native_choice_margin=float(direct.max() - direct[token]),
                native_logprob_error=abs(float(direct_lp[token]) - output_probability[0]))
        if (result['native_logprob_error'] > .001 or result['native_choice_margin'] > .001 or
                result['max_logit_difference'] > .001):
            raise ValueError(f'independent FP32 head disagrees beyond the frozen 1e-3 tolerance: {result}')
        return result


def write_json(path, value):
    with Path(path).open('x') as output:
        json.dump(value, output, allow_nan=False)


def run(mode, directory, reference, url, tree_sha, device):
    directory.mkdir(parents=True, exist_ok=False)
    client = NativeClient(url, directory / 'raw')
    identity = client.scorer_identity(tree_sha)
    head = FP32Head(identity['server_args']['model_path'], device)
    write_json(directory / 'head-identity.json', head.identity)
    manifest = json.loads(reference.read_text())
    requests = manifest['requests']
    if mode == 'preflight':
        requests = requests[:1]
    else:
        seen = set()
        selected = []
        for request in requests:
            if request['suite'] not in seen:
                seen.add(request['suite'])
                selected.append(request)
        requests = selected
    paths, checks = [], []
    for request in requests:
        prompt, generated, segments, steps = request['input_ids'], [], [], []
        for index in range(1 if mode == 'preflight' else 64):
            response = client.post('/generate', dict(input_ids=prompt + generated,
                sampling_params={'temperature': 0, 'top_k': 1, 'max_new_tokens': 1, 'ignore_eos': False},
                return_hidden_states='last', return_logprob=True, logprob_start_len=-1,
                top_logprobs_num=1, return_text_in_logprobs=False))
            segment = client.last_evidence
            check = head.evaluate(response)
            if check['reverse_token'] != check['native_token']:
                raise ValueError('equivalent reduction changed selection; native generation proof needs a separate extension')
            generated.append(check['reverse_token'])
            segments.append(segment)
            steps.append(dict(check, index=index, prefix_sha256=sha_ids(prompt + generated[:-1]), raw_evidence=segment))
            if response['meta_info'].get('finish_reason', {}).get('type') == 'stop':
                break
        checks.extend(steps)
        if mode == 'control':
            trace = client.score(prompt, generated)
            trace.update(request_id=request['id'], generator=identity, generation_segments=segments,
                         head_reduction_control=dict(head_identity=head.identity, steps=steps))
            path = directory / f'{request["id"]}.json'
            write_json(path, trace)
            paths.append(str(path))
    write_json(directory / 'result.json', dict(mode=mode, head_identity=head.identity,
        requests=len(requests), tokens=len(checks), traces=paths, checks=checks,
        canonical_reverse_token_differences=sum(row['canonical_token'] != row['reverse_token'] for row in checks),
        native_reverse_token_differences=sum(row['native_token'] != row['reverse_token'] for row in checks),
        scope='actual checkpoint FP32 reduction control; same target hidden states; no throughput or promotion claim'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('preflight', 'control'), required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--tree-sha', required=True)
    parser.add_argument('--device', default='cuda:1')
    args = parser.parse_args()
    run(args.mode, args.out_dir, args.reference, args.url, args.tree_sha, args.device)


if __name__ == '__main__':
    main()
