"""Auditable native SGLang teacher-forcing transport with strict token alignment."""

import hashlib
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.request

from controller.http_transport import sha_ids


def checked_tokens(values):
    if not isinstance(values, list) or not values or any(type(token) is not int or token < 0 for token in values):
        raise ValueError('a nonempty list of nonnegative token IDs is required')


def prefix_hashes(prompt, output):
    checked_tokens(prompt)
    checked_tokens(output)
    digest = hashlib.sha256(b'[' + ','.join(map(str, prompt)).encode())
    results = []
    for token in output:
        current = digest.copy()
        current.update(b']')
        results.append(current.hexdigest())
        digest.update(b',' + str(token).encode())
    return results


def decode_scores(response, prompt, output):
    hashes = prefix_hashes(prompt, output)
    metadata = response.get('meta_info', {})
    actual = metadata.get('input_token_logprobs', [])
    tops = metadata.get('input_top_logprobs', [])
    tokens = prompt + output
    if len(actual) != len(tokens) or len(tops) != len(tokens):
        raise ValueError('native input logprob coverage does not match the complete forced sequence')
    if any(not isinstance(entry, (list, tuple)) or len(entry) < 2 or entry[1] != token
           for entry, token in zip(actual, tokens)):
        raise ValueError('native input token identities are shifted or incomplete')
    results = []
    for index, token in enumerate(output):
        position = len(prompt) + index
        if not isinstance(tops[position], list) or not tops[position] or len(tops[position][0]) < 2:
            raise ValueError('missing scorer argmax evidence')
        logprob = actual[position][0]
        best_logprob, best_token = tops[position][0][:2]
        if (type(best_token) is not int or best_token < 0 or
                any(type(value) not in (int, float) or not math.isfinite(value) or value > 1e-5
                    for value in (logprob, best_logprob))):
            raise ValueError('invalid or nonfinite scorer probability')
        margin = best_logprob - logprob
        if margin < -1e-5 or (best_token == token and abs(margin) > 1e-5):
            raise ValueError('argmax and forced-token probabilities are inconsistent')
        results.append(dict(index=index, token=token, argmax=best_token,
                            token_logprob=logprob, argmax_logprob=best_logprob,
                            margin=max(0, margin), prefix_sha256=hashes[index],
                            context_tokens=position))
    return results


def server_arguments(info):
    nested = info.get('server_args')
    if nested is not None:
        if not isinstance(nested, dict) or any(info[key] != nested[key] for key in set(info) & set(nested)):
            raise ValueError('conflicting or invalid server-info parameter schemas')
        return nested
    if isinstance(info.get('model_path'), str):
        return info
    raise ValueError('server-info response has no recognized parameter schema')


class NativeClient:
    def __init__(self, url, raw_dir, timeout=1800):
        self.url, self.raw_dir, self.timeout = url.rstrip('/'), Path(raw_dir), timeout
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.sequence = 0
        self.last_evidence = None
        self.identity = None

    def request(self, path, body=None):
        self.sequence += 1
        request = urllib.request.Request(self.url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload, status = response.read(), response.status
        except urllib.error.HTTPError as error:
            payload, status = error.read(), error.code
        decoded = json.loads(payload) if status == 200 else payload.decode(errors='replace')
        record = dict(url=self.url + path, request=body, response=decoded,
                      http_status=status, started_unix=started, finished_unix=time.time())
        destination = self.raw_dir / f'{self.sequence:06d}.json'
        with destination.open('x') as output:
            json.dump(record, output, allow_nan=False)
        self.last_evidence = dict(path=str(destination), sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
        if status != 200:
            raise RuntimeError(f'native HTTP {status}; raw evidence: {destination}')
        return decoded

    def post(self, path, body):
        return self.request(path, body)

    def get(self, path):
        return self.request(path)

    def server_identity(self, tree_sha):
        info = self.get('/get_server_info')
        arguments = server_arguments(info)
        return dict(tree_sha=tree_sha, server_args={key: arguments.get(key) for key in
            ('model_path', 'dtype', 'enable_fp32_lm_head', 'enable_return_hidden_states',
             'return_hidden_states_mode', 'chunked_prefill_size', 'speculative_algorithm', 'speculative_num_draft_tokens')},
             evidence=self.last_evidence)

    def scorer_identity(self, tree_sha):
        identity = self.server_identity(tree_sha)
        if identity['server_args']['enable_fp32_lm_head'] is not True:
            raise ValueError('server does not advertise enabled FP32 LM head')
        self.identity = identity
        return self.identity

    def score(self, prompt, output):
        checked_tokens(prompt)
        checked_tokens(output)
        if self.identity is None:
            raise ValueError('scorer identity must be checked before collecting forcing evidence')
        response = self.post('/generate', dict(input_ids=prompt + output,
            sampling_params={'temperature': 0, 'top_k': 1, 'max_new_tokens': 1},
            return_logprob=True, logprob_start_len=0, top_logprobs_num=1, return_text_in_logprobs=False))
        return dict(prompt_sha256=sha_ids(prompt), output_sha256=sha_ids(output),
                    prompt_tokens=len(prompt), output_tokens=len(output),
                    prompt_ids=prompt, output_ids=output, scores=decode_scores(response, prompt, output),
                    scorer=self.identity, raw_evidence=self.last_evidence,
                    scope='stock-engine FP32-head native teacher-forced scores; not a correctness verdict')
