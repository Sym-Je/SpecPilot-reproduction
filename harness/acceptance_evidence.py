"""SHA-bound native counter summaries and conditional, non-promotional scenarios.

Only the stock-profile-capture-v1 DFLASH fixed-block schema is supported. Callers
authorize each manifest and input SHA plus the canonical stock tree/server args;
this module does not discover files, authorize evidence, or run a controller.
"""

import base64
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):
    if (not isinstance(value, str) or len(value) != 64 or
            any(character not in '0123456789abcdef' for character in value)):
        raise ValueError('expected a lowercase SHA256')
    return value


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('invalid integer: ' + name)
    return value


def _number(value, name, allow_zero=False):
    if (type(value) not in (int, float) or not math.isfinite(value) or
            value < 0 or (value == 0 and not allow_zero)):
        raise ValueError('invalid finite number: ' + name)
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _decode(content):
    result = json.loads(content, object_pairs_hook=_object)
    _encoded(result)
    return result


def _read(reference):
    path = Path(reference['path']).resolve()
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != _sha(reference['sha256']):
        raise ValueError('SHA256 mismatch: ' + str(path))
    return _decode(content), dict(path=str(path), sha256=reference['sha256'])


def _native(manifest, root, reference, endpoint):
    path = Path(reference['path']).resolve()
    if path.parent != root / 'native' or path.suffix != '.json':
        raise ValueError('native evidence must remain inside this manifest/native directory')
    if manifest['files'].get('native/' + path.name) != reference['sha256']:
        raise ValueError('native SHA disagrees with manifest file index')
    packet, source = _read(reference)
    if type(packet['http_status']) is not int or packet['http_status'] != 200:
        raise ValueError('native request was not successful')
    if urlsplit(packet['url']).path != endpoint:
        raise ValueError('wrong native endpoint; warmup/control is not generation')
    raw_keys = {'response_bytes_base64', 'response_bytes_sha256'}
    if raw_keys.intersection(packet):
        if not raw_keys.issubset(packet):
            raise ValueError('incomplete raw response binding')
        raw = base64.b64decode(packet['response_bytes_base64'], validate=True)
        if hashlib.sha256(raw).hexdigest() != _sha(packet['response_bytes_sha256']):
            raise ValueError('raw response SHA mismatch')
        if _encoded(_decode(raw)) != _encoded(packet['response']):
            raise ValueError('raw response disagrees with parsed response')
    return packet, source


def _counters(metadata, output_ids, block):
    names = ('completion_tokens', 'spec_verify_ct', 'spec_accepted_drafts',
             'spec_num_correct_drafts', 'spec_proposed_drafts', 'spec_num_proposed_drafts')
    counts = {name: _integer(metadata[name], name) for name in names}
    emitted, steps, accepted, correct, proposed, proposed_alias = (counts[name] for name in names)
    if emitted == 0 or steps == 0 or proposed == 0:
        raise ValueError('no positive emitted/verification workload; ratios unavailable')
    histogram = metadata['spec_accept_histogram']
    if not isinstance(histogram, list) or len(histogram) != block:
        raise ValueError('histogram does not match the stock block')
    for count in histogram:
        _integer(count, 'histogram bin')
    if (sum(histogram) != steps or
            sum(index * count for index, count in enumerate(histogram)) != accepted or
            accepted != correct or proposed != proposed_alias or proposed != (block - 1) * steps or
            _encoded(histogram) != _encoded(metadata['spec_correct_drafts_histogram'])):
        raise ValueError('inconsistent native counts, histogram or aliases')
    if not isinstance(output_ids, list) or len(output_ids) != emitted:
        raise ValueError('output_ids disagree with completion_tokens')
    for token in output_ids:
        _integer(token, 'output token ID')
    rate = _number(metadata['spec_accept_rate'], 'spec_accept_rate', allow_zero=True)
    length = _number(metadata['spec_accept_length'], 'spec_accept_length')
    if (not math.isclose(rate, accepted / proposed, rel_tol=1e-10, abs_tol=1e-10) or
            not math.isclose(length, emitted / steps, rel_tol=1e-10, abs_tol=1e-10)):
        raise ValueError('native derived field disagrees with counters')
    tail = accepted + steps - emitted
    if not 0 <= tail < block:
        raise ValueError('counts outside supported conditional single-tail stock convention')
    if _integer(metadata['num_retractions'], 'num_retractions') != 0:
        raise ValueError('retracted workload is unsupported')
    finish = metadata['finish_reason']
    if not isinstance(finish, dict) or finish.get('type') not in ('stop', 'length'):
        raise ValueError('missing or unsupported finish reason')
    matched = finish.get('matched')
    if isinstance(matched, bool):
        raise ValueError('invalid matched stop token')
    last_matches = None
    if type(matched) is int:
        _integer(matched, 'matched stop token')
        last_matches = output_ids[-1] == matched
    return dict(reported_accepted_draft_tokens=accepted, verify_steps=steps,
        proposed_draft_tokens=proposed, emitted_tokens=emitted,
        accepted_draft_histogram=list(histogram),
        mean_accepted_drafts_per_verify=accepted / steps,
        nominal_tokens_per_verify=(accepted + steps) / steps,
        emitted_tokens_per_verify=emitted / steps, native_spec_accept_length=length,
        conditional_uncommitted_tokens=tail, committed_accepted_draft_tokens=None,
        first_token_contribution=None, finish_reason=dict(finish),
        matched_stop_id_is_last_output=last_matches)


def summarize_native(references, *, canonical_stock):
    """Summarize explicitly authorized, SHA-pinned public stock captures.

    references: iterable of {path: manifest path, sha256: manifest SHA,
                             input_sha256: expected compact-JSON input_ids SHA}.
    canonical_stock: {tree_sha: authorized tree SHA, server_args: exact authorized
                      manifest identity.server_args mapping}.

    Reject missing/invalid counters, duplicates, unbound files, changed inputs,
    options, non-DFLASH, retractions, or mixed configuration/sampling/presets.
    Histogram bins count reported verify steps accepting that many drafts, not
    committed tokens. No per-step ordering or committed draft/bonus split exists
    in these responses. An exception is preferable to substituting zero.
    """
    rows, sources, seen = [], [], set()
    configuration = None
    try:
        _sha(canonical_stock['tree_sha'])
        expected_args = canonical_stock['server_args']
        block = _integer(expected_args['speculative_num_draft_tokens'], 'stock block', 2)
        if expected_args['speculative_algorithm'] != 'DFLASH':
            raise ValueError('only fixed-block canonical DFLASH counters are supported')
        for reference in references:
            manifest, manifest_source = _read(reference)
            root = Path(manifest_source['path']).parent
            if manifest_source['path'] in seen:
                raise ValueError('duplicate capture')
            seen.add(manifest_source['path'])
            arm, identity = manifest['arm'], manifest['identity']
            if (manifest['schema'] != 'stock-profile-capture-v1' or arm['name'] != 'stock' or
                    arm['option_enabled'] is not False or arm['env'] != {} or
                    _integer(arm['block'], 'arm block', 2) != block or
                    arm['tree_sha'] != canonical_stock['tree_sha'] or
                    identity['tree_sha'] != canonical_stock['tree_sha'] or
                    _encoded(identity['server_args']) != _encoded(expected_args) or
                    manifest['preset']['mode'] != 'canonical-stock-graph'):
                raise ValueError('capture is not the explicitly authorized canonical stock')
            server, server_source = _native(manifest, root, identity['evidence'], '/get_server_info')
            for key, value in expected_args.items():
                if _encoded(server['response'][key]) != _encoded(value):
                    raise ValueError('actual server configuration disagrees with stock identity')
            generation, generation_source = _native(manifest, root, manifest['generation'], '/generate')
            generation_key = ('generation', generation_source['sha256'])
            if generation_key in seen:
                raise ValueError('same native response cannot be counted twice')
            seen.add(generation_key)
            body = generation['request']
            ids = body['input_ids']
            if not isinstance(ids, list) or not ids:
                raise ValueError('missing flat input token IDs')
            for token in ids:
                _integer(token, 'input token ID')
            input_sha = hashlib.sha256(_encoded(ids)).hexdigest()
            request = manifest['request']
            if (input_sha != _sha(reference['input_sha256']) or
                    input_sha != _sha(request['input_sha256']) or
                    _encoded(ids) != _encoded(request['input_ids'])):
                raise ValueError('input SHA or token IDs disagree')
            sampling = body['sampling_params']
            maximum = _integer(sampling['max_new_tokens'], 'max_new_tokens', 1)
            if maximum != _integer(manifest['preset']['max_new_tokens'], 'preset max_new_tokens', 1):
                raise ValueError('generation workload does not match preset (possibly warmup)')
            _number(sampling['temperature'], 'temperature', allow_zero=True)
            if type(sampling['top_k']) is not int or sampling['top_k'] not in (-1, 1):
                raise ValueError('unsupported top_k; expected canonical -1 or 1')
            if type(sampling['ignore_eos']) is not bool:
                raise ValueError('ignore_eos must be boolean')
            signature = _encoded([server['response'], manifest['preset'], sampling])
            if configuration is not None and signature != configuration:
                raise ValueError('mixed server configuration, preset or sampling workload')
            configuration = signature
            metadata = generation['response']['meta_info']
            if _integer(metadata['prompt_tokens'], 'prompt_tokens', 1) != len(ids):
                raise ValueError('prompt workload count disagrees with input IDs')
            row = _counters(metadata, generation['response']['output_ids'], block)
            if row['emitted_tokens'] > maximum:
                raise ValueError('emitted count exceeds generation workload limit')
            row.update(request_id=request['id'], input_sha256=input_sha,
                       source=generation_source)
            rows.append(row)
            sources.extend([manifest_source, server_source, generation_source])
        if not rows:
            raise ValueError('no authorized native captures')
    except (OSError, KeyError, TypeError, OverflowError) as error:
        raise ValueError('unavailable or malformed native evidence: ' + str(error)) from error
    totals = {key: sum(row[key] for row in rows) for key in (
        'reported_accepted_draft_tokens', 'verify_steps', 'emitted_tokens', 'proposed_draft_tokens')}
    totals.update(request_count=len(rows),
        accepted_draft_histogram=[sum(row['accepted_draft_histogram'][index] for row in rows)
                                  for index in range(block)],
        mean_accepted_drafts_per_verify=totals['reported_accepted_draft_tokens'] / totals['verify_steps'],
        emitted_tokens_per_verify=totals['emitted_tokens'] / totals['verify_steps'],
        request_mean_accepted_drafts_per_verify=sum(row['mean_accepted_drafts_per_verify']
                                                   for row in rows) / len(rows),
        committed_accepted_draft_tokens=None)
    return dict(schema='acceptance-evidence-v1', requests=rows, aggregate=totals,
        canonical_stock=json.loads(_encoded(canonical_stock)), sources=sources,
        units=dict(reported_accepted_draft_tokens='reported draft tokens (not proven committed)',
                   verify_steps='reported target verification steps', emitted_tokens='output token IDs',
                   mean_accepted_drafts_per_verify='reported draft tokens / verify step',
                   nominal_tokens_per_verify='drafts + assumed one bonus token / verify step',
                   emitted_tokens_per_verify='output tokens / verify step',
                   accepted_draft_histogram='verify step counts indexed by accepted draft count'),
        weighting='pooled counts / pooled verify steps; request_mean is equal-weight per capture',
        definitions=dict(native_spec_accept_length='checked against completion_tokens/spec_verify_ct; '
                         'an emitted-progress field, not committed accepted draft length',
                         conditional_uncommitted_tokens='accepted_drafts + verify_steps - output_tokens; '
                         'only a residual under one bonus/step and single clipped tail assumptions'),
        unknowns=['Committed accepted draft tokens and bonus split are unavailable without a token lattice.',
                  'First token/prefill contribution and uncommitted tail-step identities are unavailable.',
                  'EOS identity/counting is not established by matched stop ID alone; emitted IDs include '
                  'any returned stop token, histogram may include uncommitted terminal proposals.',
                  'Histograms have no step order; full-request counters do not count a bounded profile window.',
                  'Unprofiled step wall costs, overlap and end-to-end benefit are unavailable.'],
        scope='Authorized full-request native counters only; not an ideal oracle, formal ceiling, '
              'losslessness test, paired performance result or kernel critical-path estimate.')


def estimate_conditional(*, tau_ratio, step_cost_ratio=None, extra_step_cost_ratio=None, assumptions):
    """Model decode throughput as tau_ratio / (step_cost_ratio + extra cost).

    All ratios are candidate/baseline; both costs use baseline seconds/verify as
    their denominator. tau must use the same committed-progress convention in
    both arms. Explicit extra=0 asserts no extra cost (or all included already).
    Missing cost stays unknown. No end-to-end or critical-path inference occurs.
    """
    _number(tau_ratio, 'tau_ratio')
    if (not isinstance(assumptions, (list, tuple)) or not assumptions or
            any(not isinstance(item, str) or not item.strip() for item in assumptions)):
        raise ValueError('explicit nonempty assumptions are required')
    unknowns = []
    for name, value in (('step_cost_ratio', step_cost_ratio),
                        ('extra_step_cost_ratio', extra_step_cost_ratio)):
        if value is None:
            unknowns.append(name + ' is unknown; no net decode benefit can be estimated')
        else:
            _number(value, name, allow_zero=name == 'extra_step_cost_ratio')
    speedup = None
    if not unknowns:
        total_cost = step_cost_ratio + extra_step_cost_ratio
        _number(total_cost, 'total step cost')
        speedup = tau_ratio / total_cost
        _number(speedup, 'conditional decode speedup')
    return dict(tau_ratio=tau_ratio, step_cost_ratio=step_cost_ratio,
        extra_step_cost_ratio=extra_step_cost_ratio, conditional_decode_speedup=speedup,
        end_to_end_speedup=None, unknowns=unknowns,
        units='dimensionless ratios; extra cost normalized to baseline seconds/verify',
        assumptions=list(assumptions) + [
            'Same emitted workload, valid committed-progress tau definition and steady decode regime.',
            'Extra step cost is additive, normalized to baseline, and not double-counted.',
            'No fixed prefill, scheduling, overlap or tail changes are modeled.'],
        scope='Conditional scenario, including finite replay if supplied; not an ideal oracle, '
              'formal ceiling, measured benefit or kernel-work critical-path inference.')
