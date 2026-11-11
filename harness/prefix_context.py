"""Frozen public-task identities for the irrelevant-prefix control experiment."""

import hashlib
from controller.http_transport import sha_ids

PROTOCOL = 'author-dev-prefix-context-v1'
CONDITIONS = ('original', '2048', '8192', '32768', '65536')
SUITES = ('gsm8k', 'math500', 'humaneval', 'mbpp', 'mt-bench')


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def validate(record):
    bases = record['base_requests']
    requests = record['requests']
    if len(bases) != 10 or len({item['id'] for item in bases}) != 10:
        raise ValueError('ten unique public base tasks required')
    if any(sum(item['suite'] == suite for item in bases) != 2 for suite in SUITES):
        raise ValueError('two public tasks per suite required')
    if len(requests) != 50 or len({item['id'] for item in requests}) != 50:
        raise ValueError('fifty unique condition requests required')
    for base in bases:
        if (text_sha(base['question']) != base['question_sha256'] or
                sha_ids(base['input_ids']) != base['input_sha256']):
            raise ValueError('base public question identity differs')
        selected = [item for item in requests if item['base_id'] == base['id']]
        if len(selected) != 5 or {item['condition'] for item in selected} != set(CONDITIONS):
            raise ValueError('base task missing a condition')
        for item in selected:
            if (item['suite'] != base['suite'] or item['input_sha256'] != sha_ids(item['input_ids']) or
                    item['context_tokens'] != len(item['input_ids']) or
                    item['question_sha256'] != base['question_sha256']):
                raise ValueError('condition input, suite or question identity differs')
            if item['condition'] == 'original':
                if item['input_ids'] != base['input_ids']:
                    raise ValueError('unmodified control differs from author template')
            else:
                suffix = base['question_suffix_ids']
                prefix = base['chat_prefix_ids']
                if (item['context_tokens'] != int(item['condition']) or not suffix or
                        item['input_ids'][-len(suffix):] != suffix or item['input_ids'][:len(prefix)] != prefix):
                    raise ValueError('padded context changed question suffix or exact input length')
                used = item['input_ids'][len(prefix):-len(suffix)]
                if not used or used != base['document_prefix_ids'][:len(used)]:
                    raise ValueError('padding is not the frozen continuous public-document prefix')
    return True
