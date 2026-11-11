"""Source provenance and prospective-cost checks, not scientific promotion."""

import ast
import hashlib
import json
import math
from pathlib import Path
import re


AXES = frozenset(('verification_budget', 'verification_selection', 'kernel', 'end_to_end'))


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 8000:
        raise ValueError('bounded nonempty explanation required')
    return value


def texts(values, *, nonempty=True):
    if not isinstance(values, list) or len(values) > 16 or (nonempty and not values):
        raise ValueError('bounded explanation list required')
    for value in values:
        text(value)


def receipt(directory, identity):
    if not isinstance(identity, str) or not re.fullmatch(r'tools-[0-9]{2,}/action-[0-9]{3,}', identity):
        raise ValueError('own-role tool receipt identity required')
    base = Path(directory).resolve()
    path = base / identity
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise ValueError('cross-role receipt is forbidden')
    try:
        request = json.loads((path / 'request.json').read_text())
        returned = json.loads((path / 'response.json').read_text())
        answer = json.loads(returned['contentItems'][0]['text'])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError('tool receipt is missing or malformed') from error
    if returned.get('success') is not True or answer.get('status') not in ('completed', 'unavailable'):
        raise ValueError('successful source/evidence receipt required')
    return request['arguments']['action'], answer


def interval(value):
    if (not isinstance(value, list) or len(value) != 2 or
            any(type(number) not in (int, float) or not math.isfinite(number) or number <= 0 for number in value) or
            value[0] > value[1]):
        raise ValueError('finite positive ordered ratio interval required')
    return value


def validate_benefit(value, directory):
    fields = {'model', 'baseline_calls', 'acceptance_ratio', 'step_cost_ratio', 'net_speedup',
              'saved_work', 'added_cost', 'assumptions', 'unknowns', 'next_action'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('prospective net-benefit estimate and added cost are required')
    text(value['saved_work'])
    text(value['added_cost'])
    texts(value['assumptions'])
    texts(value['unknowns'])
    if value['next_action'] not in ('implement', 'diagnose', 'stop'):
        raise ValueError('explicit implementation/diagnosis/stop decision required')
    calls = value['baseline_calls']
    if not isinstance(calls, list) or not 1 <= len(calls) <= 8:
        raise ValueError('baseline tool evidence is required')
    factual = False
    scenarios = []
    for identity in calls:
        action, answer = receipt(directory, identity)
        if action.get('kind') not in ('get_baseline_stats', 'run_skill', 'read_file', 'estimate_scenario'):
            raise ValueError('baseline reference is not an observation or cost-evidence tool')
        if action.get('kind') == 'read_file' and action.get('path') != 'inputs/evidence.json':
            raise ValueError('scratch hypotheses cannot substitute baseline measurement')
        if value['model'] != 'unquantified' and answer.get('status') != 'completed':
            raise ValueError('unavailable evidence cannot support a quantified implementation')
        if action.get('kind') == 'estimate_scenario':
            from harness.acceptance_evidence import estimate_conditional
            expected = estimate_conditional(**{key:item for key,item in action.items() if key != 'kind'})
            if answer.get('scenario') != expected:
                raise ValueError('conditional estimate differs from its executed calculation')
            if expected['conditional_decode_speedup'] is not None:
                scenarios.append(expected)
        else:
            factual = factual or answer.get('status') == 'completed'
    if value['model'] == 'unquantified':
        if (any(value[field] is not None for field in ('acceptance_ratio', 'step_cost_ratio', 'net_speedup')) or
                value['next_action'] == 'implement'):
            raise ValueError('unknown cost requires diagnosis/stop, not a manufactured net gain')
    elif value['model'] == 'acceptance_over_step_cost':
        acceptance = interval(value['acceptance_ratio'])
        cost = interval(value['step_cost_ratio'])
        net = interval(value['net_speedup'])
        expected = [acceptance[0] / cost[1], acceptance[1] / cost[0]]
        if any(not math.isclose(actual, reference, rel_tol=1e-6, abs_tol=1e-9)
               for actual, reference in zip(net, expected)):
            raise ValueError('net speedup must include the full step-cost ratio')
        if not factual:
            raise ValueError('quantified proposal needs actual baseline observations, not only assumed scenarios')
        for tau, full_cost in ((acceptance[0], cost[1]), (acceptance[1], cost[0])):
            if not any(math.isclose(item['tau_ratio'], tau, rel_tol=1e-6) and
                       math.isclose(item['step_cost_ratio'] + item['extra_step_cost_ratio'], full_cost, rel_tol=1e-6)
                       for item in scenarios):
                raise ValueError('both forecast endpoints require executed scenarios with explicit full and extra cost')
    else:
        raise ValueError('unsupported prospective cost model; not a formal ceiling')


def definitions(source):
    result = {}
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    def position(line, column):
        return offsets[line - 1] + len(lines[line - 1].encode()[:column].decode())
    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            name = prefix
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = '.'.join((*prefix, child.name))
                start = position(child.lineno, child.col_offset)
                end = position(child.end_lineno, child.end_col_offset)
                result[name] = dict(source=source[start:end], start=start, end=end)
                name = (*prefix, child.name)
            visit(child, name)
    visit(ast.parse(source), ())
    return result


def validate_change(change, directory, stock):
    fields = {'path', 'symbol', 'source_sha256', 'source_call', 'quote', 'mechanism'}
    if not isinstance(change, dict) or set(change) != fields:
        raise ValueError('exact source location and mechanism required')
    name = text(change['path'])
    if (not name.startswith(('python/sglang/srt/', 'python/sglang/kernels/')) or not name.endswith('.py') or
            any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('only authorized stock runtime source may ground a proposal')
    root = Path(stock).resolve()
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('existing nonsymlink stock source required')
    content = path.read_text()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    action, answer = receipt(directory, change['source_call'])
    quote = text(change['quote'])
    offset = action.get('offset', 0)
    if (action.get('kind') != 'read_stock' or action.get('path') != name or
            answer.get('status') != 'completed' or answer.get('sha256') != digest or
            change['source_sha256'] != digest or type(offset) is not int or offset < 0 or
            answer.get('content') != content[offset:offset + 12000] or quote not in answer.get('content', '')):
        raise ValueError('source proposal was not grounded in the Master actual source read')
    symbol = text(change['symbol'])
    available = definitions(content)
    selected = available.get(symbol)
    if selected is None and '.' not in symbol:
        candidates = [body for key, body in available.items() if key.split('.')[-1] == symbol]
        selected = candidates[0] if len(candidates) == 1 else None
    if selected is None or quote not in content[max(selected['start'], offset):min(selected['end'], offset + len(answer['content']))]:
        raise ValueError('cited quote is not in the proposed function/class')
    text(change['mechanism'])


def validate_proposals(value, directory, stock):
    if not isinstance(value, dict) or set(value) != {'directions'}:
        raise ValueError('directions object required')
    directions = value['directions']
    if not isinstance(directions, list) or not 1 <= len(directions) <= 3:
        raise ValueError('one to three substantive proposals required')
    names = set()
    for item in directions:
        if not isinstance(item, dict) or set(item) != {'id', 'brief', 'allocation', 'proposal'}:
            raise ValueError('a general direction is not an actionable source proposal')
        identity = item['id']
        if not isinstance(identity, str) or not re.fullmatch(r'd[a-z0-9]{1,20}', identity) or identity in names:
            raise ValueError('unique bounded direction ID required')
        names.add(identity)
        text(item['brief'])
        allocation = item['allocation']
        if (not isinstance(allocation, dict) or set(allocation) != {'actions', 'cpu_runs', 'gpu_attempts'} or
                any(type(allocation[key]) is not int or not 1 <= allocation[key] <= upper
                    for key, upper in (('actions', 160), ('cpu_runs', 32), ('gpu_attempts', 3)))):
            raise ValueError('proposal allocation exceeds the approved role envelope')
        proposal = item['proposal']
        if not isinstance(proposal, dict) or set(proposal) != {'changes', 'invariants', 'risks', 'benefit', 'validation', 'external_sources'}:
            raise ValueError('complete source proposal and prospective evaluation required')
        if not isinstance(proposal['changes'], list) or not 1 <= len(proposal['changes']) <= 8:
            raise ValueError('bounded source change list required')
        for change in proposal['changes']:
            validate_change(change, directory, stock)
        texts(proposal['invariants'])
        texts(proposal['risks'])
        validate_benefit(proposal['benefit'], directory)
        validation = proposal['validation']
        if not isinstance(validation, dict) or set(validation) != {'correctness', 'path_hit', 'performance', 'stop'}:
            raise ValueError('correctness/path/performance/stop validation plan required')
        for explanation in validation.values():
            text(explanation)
        external = proposal['external_sources']
        if not isinstance(external, list) or len(external) > 8:
            raise ValueError('bounded external knowledge provenance required')
        for entry in external:
            if not isinstance(entry, dict) or set(entry) != {'call', 'reuse'}:
                raise ValueError('external retrieval and reuse declaration required')
            action, answer = receipt(directory, entry['call'])
            if action.get('kind') not in ('search_public', 'read_public') or answer.get('status') != 'completed':
                raise ValueError('external knowledge must be actually retrieved by this Master')
            text(entry['reuse'])
    if sum(item['allocation']['actions'] for item in directions) > 400:
        raise ValueError('direction actions exhaust the shared stage reserve')
    return directions


def validate_axes(value, directory):
    if not isinstance(value, list) or len(value) != len(AXES):
        raise ValueError('all four user-requested research axes must be assessed')
    seen = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {'axis', 'findings', 'evidence_calls', 'unknowns', 'priority', 'benefit_assessment'}:
            raise ValueError('axis needs evidence, prospective benefit, uncertainty and priority')
        if entry['axis'] not in AXES or entry['axis'] in seen or entry['priority'] not in ('explore', 'diagnose', 'defer'):
            raise ValueError('unique recognized axis and explicit priority required')
        seen.add(entry['axis'])
        text(entry['findings'])
        text(entry['benefit_assessment'])
        texts(entry['unknowns'])
        if not isinstance(entry['evidence_calls'], list) or len(entry['evidence_calls']) > 12:
            raise ValueError('bounded evidence calls required')
        if not entry['evidence_calls'] and entry['priority'] == 'explore':
            raise ValueError('unobserved axis requires diagnosis or deferral')
        factual = False
        for identity in entry['evidence_calls']:
            action, answer = receipt(directory, identity)
            if action.get('kind') not in ('read_stock', 'list_stock', 'search_stock', 'get_baseline_stats',
                                           'run_skill', 'search_public', 'read_public', 'read_file', 'estimate_scenario'):
                raise ValueError('authored claims are not observational evidence for a research axis')
            if action.get('kind') == 'read_file' and action.get('path') != 'inputs/evidence.json':
                raise ValueError('scratch hypotheses cannot substitute axis observations')
            factual = factual or (answer.get('status') == 'completed' and action.get('kind') != 'estimate_scenario')
        if entry['priority'] == 'explore' and not factual:
            raise ValueError('exploration axis needs available factual evidence, not only hypotheses')
    return value


def validate_estimate_review(response, proposals, feedback):
    reviews = response.get('estimate_reviews')
    if not isinstance(reviews, list) or len(reviews) != len(proposals):
        raise ValueError('Master must revisit the prospective estimate for every direction')
    seen = set()
    for entry in reviews:
        if not isinstance(entry, dict) or set(entry) != {'id', 'observed_geomean', 'forecast_supported', 'revision'}:
            raise ValueError('observed statistic, forecast disposition and revision required')
        identity = entry['id']
        if identity not in proposals or identity in seen:
            raise ValueError('estimate review must cover unique actual proposal identities')
        seen.add(identity)
        measurements = [item for item in feedback if item.get('role_label') == 'direction-' + identity and
                        item.get('status') == 'completed' and 'geomean' in item]
        observed = entry['observed_geomean']
        supported = entry['forecast_supported']
        if not measurements:
            if observed is not None or supported is not None:
                raise ValueError('an unmeasured proposal cannot claim a confirmed forecast')
        else:
            expected = measurements[-1]['geomean']
            if (type(observed) not in (int, float) or not math.isfinite(observed) or observed <= 0 or
                    not math.isclose(observed, expected, rel_tol=1e-6, abs_tol=1e-9) or type(supported) is not bool):
                raise ValueError('forecast review differs from the actual controller diagnostic statistic')
            if supported:
                benefit = proposals[identity].get('proposal', {}).get('benefit', {})
                predicted = benefit.get('net_speedup')
                if not isinstance(predicted, list) or not predicted[0] <= observed <= predicted[1]:
                    raise ValueError('observed value cannot confirm an absent or incompatible forecast')
        text(entry['revision'])
    return reviews
