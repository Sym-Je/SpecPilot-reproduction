"""Margin-aware forcing with raw-score, own-prefix and generation provenance."""

import hashlib
import json
import math
from pathlib import Path

from controller.http_transport import sha_ids
from controller.paper_policy import valid_digest
from controller.scoring import checked_tokens, decode_scores, server_arguments
from controller.stats import binom_one_sided
from controller.token_force import _wilson_low


def digest_record(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_bound(path, evidence_root, expected=None):
    path, root = Path(path).resolve(), Path(evidence_root).resolve()
    if not path.is_relative_to(root):
        raise ValueError('evidence path escapes the declared campaign root')
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    if expected is not None and checksum != expected:
        raise ValueError('raw evidence checksum mismatch')
    return json.loads(content), {'path': str(path), 'sha256': checksum}


def read_reference(reference, evidence_root):
    if not valid_digest(reference.get('sha256')):
        raise ValueError('raw evidence needs an immutable checksum')
    return read_bound(reference['path'], evidence_root, reference['sha256'])[0]


def checked_server(identity, evidence_root, fp32=False):
    if not valid_digest(identity.get('tree_sha')):
        raise ValueError('missing engine tree identity')
    original = read_reference(identity['evidence'], evidence_root)
    arguments = identity.get('server_args', {})
    actual = server_arguments(original.get('response', {}))
    if (original.get('http_status') != 200 or not arguments.get('model_path') or
            any(actual.get(key) != value for key, value in arguments.items())):
        raise ValueError('server configuration differs from raw identity evidence')
    if fp32 and arguments.get('enable_fp32_lm_head') is not True:
        raise ValueError('scorer is not an enabled FP32-head reference')
    return arguments


def load_score_trace(path, *, evidence_root, require_generation=True):
    trace, source = read_bound(path, evidence_root)
    prompt, output = trace.get('prompt_ids'), trace.get('output_ids')
    checked_tokens(prompt)
    checked_tokens(output)
    if (not isinstance(trace.get('request_id'), str) or not trace['request_id'] or
            trace.get('prompt_tokens') != len(prompt) or trace.get('output_tokens') != len(output) or
            trace.get('prompt_sha256') != sha_ids(prompt) or trace.get('output_sha256') != sha_ids(output)):
        raise ValueError('incomplete or incorrectly identified scored trace')
    arguments = checked_server(trace['scorer'], evidence_root, fp32=True)
    raw = read_reference(trace['raw_evidence'], evidence_root)
    body = raw.get('request', {})
    if (raw.get('http_status') != 200 or body.get('input_ids') != prompt + output or
            body.get('return_logprob') is not True or body.get('logprob_start_len') != 0 or
            body.get('top_logprobs_num', 0) < 1 or body.get('sampling_params', {}).get('max_new_tokens') != 1):
        raise ValueError('raw request was not complete native teacher forcing')
    if trace.get('scores') != decode_scores(raw['response'], prompt, output):
        raise ValueError('scores or explanations were altered after native inference')
    if require_generation:
        generator = checked_server(trace['generator'], evidence_root)
        if generator['model_path'] != arguments['model_path']:
            raise ValueError('generator and scorer target models differ')
        segments = trace.get('generation_segments', [])
        if not segments:
            raise ValueError('missing real generation provenance')
        generated = []
        for segment in segments:
            packet = read_reference(segment, evidence_root)
            response = packet.get('response', {})
            ids = response.get('output_ids')
            checked_tokens(ids)
            if (packet.get('http_status') != 200 or
                    packet.get('request', {}).get('input_ids') != prompt + generated or
                    response.get('meta_info', {}).get('completion_tokens') != len(ids)):
                raise ValueError('generation segments are incomplete or not own-prefix continuations')
            generated.extend(ids)
        if generated != output:
            raise ValueError('scored tokens differ from the actual generated tokens')
    return dict(trace, source=source,
                scorer_fingerprint=digest_record(dict(tree_sha=trace['scorer']['tree_sha'], server_args=arguments)))


def load_set(paths, evidence_root):
    if not paths:
        raise ValueError('nonempty scored request set required')
    result = {}
    for path in paths:
        trace = load_score_trace(path, evidence_root=evidence_root)
        if trace['request_id'] in result:
            raise ValueError('duplicate scored request')
        result[trace['request_id']] = trace
    if len({trace['scorer_fingerprint'] for trace in result.values()}) != 1:
        raise ValueError('scorer identity changed within the cohort')
    return result


def calibrate_delta(stock_paths, ar_paths, *, evidence_root):
    stock, autoregressive = load_set(stock_paths, evidence_root), load_set(ar_paths, evidence_root)
    if set(stock) != set(autoregressive):
        raise ValueError('AR and stock calibration requests must match exactly')
    differences = []
    for request_id, trace in stock.items():
        reference = autoregressive[request_id]
        if (trace['prompt_sha256'] != reference['prompt_sha256'] or
                trace['scorer_fingerprint'] != reference['scorer_fingerprint']):
            raise ValueError('AR/stock prompts or scorer identities differ')
        for index, (stock_token, ar_token) in enumerate(zip(trace['output_ids'], reference['output_ids'])):
            if stock_token != ar_token:
                stock_score, ar_score = trace['scores'][index], reference['scores'][index]
                if stock_score['prefix_sha256'] != ar_score['prefix_sha256']:
                    raise ValueError('first divergence does not have a common prefix')
                differences.append(dict(request_id=request_id, index=index,
                    prefix_sha256=stock_score['prefix_sha256'], stock_token=stock_token, ar_token=ar_token,
                    margin=abs(stock_score['token_logprob'] - ar_score['token_logprob'])))
                break
    if not differences:
        raise ValueError('no observed stock/AR first divergence; delta is not calibrated')
    result = dict(delta=math.ceil(max(row['margin'] for row in differences) * 8) / 8,
        first_divergences=differences, scorer_fingerprint=next(iter(stock.values()))['scorer_fingerprint'],
        stock_sources=[trace['source'] for trace in stock.values()],
        ar_sources=[trace['source'] for trace in autoregressive.values()],
        scope='measured stock/AR first-divergence calibration; not the paper delta copied')
    return dict(result, evidence_sha256=digest_record(result))


def score_counts(traces, delta):
    scores = [score for trace in traces.values() for score in trace['scores']]
    mismatches = [score for score in scores if score['token'] != score['argmax']]
    return dict(n=len(scores), mismatches=len(mismatches), rate=len(mismatches) / len(scores),
                large_margin_events=sum(score['margin'] > 2 * delta for score in mismatches))


def calibrate_stock(stock_paths, delta_calibration, *, evidence_root):
    for source in delta_calibration['stock_sources'] + delta_calibration['ar_sources']:
        read_reference(source, evidence_root)
    recalculated = calibrate_delta([source['path'] for source in delta_calibration['stock_sources']],
        [source['path'] for source in delta_calibration['ar_sources']], evidence_root=evidence_root)
    if recalculated != delta_calibration:
        raise ValueError('delta calibration differs from its raw evidence')
    traces = load_set(stock_paths, evidence_root)
    for trace in traces.values():
        arguments = trace['generator']['server_args']
        if (trace['scorer_fingerprint'] != delta_calibration['scorer_fingerprint'] or
                arguments.get('speculative_algorithm') != 'DFLASH' or
                arguments.get('speculative_num_draft_tokens') != 8):
            raise ValueError('baseline must be the declared stock DFlash2 configuration')
        for segment in trace['generation_segments']:
            body = read_reference(segment, evidence_root)['request']
            if body.get('sampling_params', {}).get('logit_bias'):
                raise ValueError('biased generation cannot calibrate stock')
    result = dict(delta=delta_calibration['delta'], delta_calibration=delta_calibration,
                  request_ids=list(traces), stock_sources=[trace['source'] for trace in traces.values()],
                  stock_counts=score_counts(traces, delta_calibration['delta']),
                  scorer_fingerprint=delta_calibration['scorer_fingerprint'])
    return dict(result, evidence_sha256=digest_record(result))


def binomial_upper(count, total, alpha=.025):
    if type(count) is not int or type(total) is not int or not 0 <= count <= total or total <= 0 or not 0 < alpha < 1:
        raise ValueError('invalid finite-stock event calibration')
    if count == total:
        return 1.0
    if count == 0:
        return -math.expm1(math.log(alpha) / total)
    lower, upper = count / total, 1.0
    for iteration in range(55):
        middle = (lower + upper) / 2
        if binom_one_sided(count + 1, total, middle) > 1 - alpha:
            upper = middle
        else:
            lower = middle
    return upper


def judge_scored_forcing(calibration, candidate_paths, *, evidence_root, prefill_audits=()):
    for source in calibration['stock_sources']:
        read_reference(source, evidence_root)
    recalculated = calibrate_stock([source['path'] for source in calibration['stock_sources']],
                                  calibration['delta_calibration'], evidence_root=evidence_root)
    if recalculated != calibration:
        raise ValueError('stock calibration was changed after measurement')
    traces = load_set(candidate_paths, evidence_root)
    if set(traces) != set(calibration['request_ids']):
        raise ValueError('candidate request coverage differs from the declared baseline cohort')
    if any(trace['scorer_fingerprint'] != calibration['scorer_fingerprint'] for trace in traces.values()):
        raise ValueError('candidate is not scored with the calibrated reference')
    audits = [load_score_trace(path, evidence_root=evidence_root, require_generation=False) for path in prefill_audits]
    counts = score_counts(traces, calibration['delta'])
    explained = []
    for request_id, trace in traces.items():
        for score in trace['scores']:
            if score['token'] == score['argmax'] or score['margin'] <= 2 * calibration['delta']:
                continue
            for audit in audits:
                if audit['scorer_fingerprint'] != trace['scorer_fingerprint'] or audit['request_id'] != request_id:
                    continue
                for alternate in audit['scores']:
                    if (alternate['prefix_sha256'] == score['prefix_sha256'] and
                            alternate['token'] == alternate['argmax'] == score['token'] and
                            audit['prompt_tokens'] + audit['output_tokens'] != trace['prompt_tokens'] + trace['output_tokens']):
                        explained.append(dict(request_id=request_id, index=score['index'],
                                              kind='prefill-length sensitivity', source=audit['source']))
                        break
                else:
                    continue
                break
    baseline = calibration['stock_counts']
    stock_rate_upper = 1 - _wilson_low(baseline['n'] - baseline['mismatches'], baseline['n'])
    candidate_rate_lower = _wilson_low(counts['mismatches'], counts['n'])
    rate_flagged = candidate_rate_lower - stock_rate_upper > .005
    stock_event_upper = binomial_upper(baseline['large_margin_events'], baseline['n'])
    unexplained = counts['large_margin_events'] - len(explained)
    event_p = binom_one_sided(unexplained, counts['n'], stock_event_upper)
    event_flagged = event_p < .025
    result = dict(n=counts['n'], mismatches=counts['mismatches'], rate=counts['rate'],
        delta=calibration['delta'], baseline=baseline, candidate_rate_lower=candidate_rate_lower,
        stock_rate_upper=stock_rate_upper, rate_excess_lower=candidate_rate_lower - stock_rate_upper,
        rate_flagged=rate_flagged, large_margin_events=counts['large_margin_events'],
        explained_events=explained, unexplained_events=unexplained, stock_event_upper=stock_event_upper,
        event_p=event_p, event_alpha=.025, event_flagged=event_flagged,
        correctness_passed=not rate_flagged and not event_flagged,
        calibration_sha256=calibration['evidence_sha256'],
        candidate_sources=[trace['source'] for trace in traces.values()], ledger_eligible=False,
        scope='bound real-score contract verdict; token-Bernoulli rate approximation; no promotion or mathematical losslessness proof')
    return dict(result, evidence_sha256=digest_record(result))


def validate_injected_generation(path, *, evidence_root, vocabulary_size=248320):
    trace = load_score_trace(path, evidence_root=evidence_root)
    segments = trace['generation_segments']
    if len(segments) != 2 or not 2048 < trace['output_tokens'] <= 4096:
        raise ValueError('fault must have a complete 2048-token prefix and a nonempty continuation')
    first, second = [read_reference(segment, evidence_root) for segment in segments]
    initial, tail = first['request']['sampling_params'], second['request']['sampling_params']
    bias = {str(token): 2 for token in range(0, vocabulary_size, 7)}
    if (len(first['response']['output_ids']) != 2048 or
            first['response']['meta_info'].get('finish_reason', {}).get('type') != 'length' or
            initial.get('max_new_tokens') != 2048 or tail.get('max_new_tokens') != 2048 or
            initial.get('logit_bias') or tail.get('logit_bias') != bias or
            initial.get('ignore_eos', False) or tail.get('ignore_eos', False)):
        raise ValueError('raw generation did not apply exactly the registered post-2048 logit bias')
    return dict(request_id=trace['request_id'], post2048_tokens=trace['output_tokens'] - 2048,
                bias=2, stride=7, vocabulary_size=vocabulary_size,
                generation_sources=segments, source=trace['source'])
