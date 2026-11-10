"""Controller-private Phase4 evidence contract, not a runtime or final verdict."""

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time

from controller.dev_campaign import check_scored_measurements, combine_correctness, validate_packet
from controller.http_transport import sha_ids
from controller.paper_policy import POLICY, calibration_from_intervals, candidate_verdict, valid_digest
from controller.scored_forcing import calibrate_delta, calibrate_stock, digest_record, judge_scored_forcing, load_score_trace, read_reference
from controller.scoring import checked_tokens
from controller.stats import stratified_geomean_ci


PROTOCOL = 'controller-phase4-v1'
CAPS = (2048, 4096)
PHASES = ('null-pre', 'candidate', 'null-post')
MISSING_RUNTIME = (
    'trusted Phase4 GPU execution and controller/research UID/private-evidence boundary',
    'independent FP32 head preflight, healthy/fault/reduction runtime regressions',
    'independent T0/dev prerequisite verification and final controller authorization',
    'trusted hardware/process/source provenance, job terminal state and archival',
)


def _private(path, *, directory=False):
    path = Path(path).absolute()
    if path != path.resolve():
        raise ValueError('private paths must not contain symlinks')
    info = path.stat()
    if (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077 or
            (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))):
        raise ValueError('controller-owned owner-only private storage required')
    return path


def _separate(path, research_roots):
    for root in research_roots:
        root = Path(root).resolve()
        if path.is_relative_to(root) or root.is_relative_to(path):
            raise ValueError('controller storage overlaps a research-visible root')


def _save(path, value):
    content = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    return dict(path=str(path), sha256=hashlib.sha256(content).hexdigest())


def _frozen(reference):
    path = _private(reference['path'])
    root = _private(path.parent, directory=True)
    frozen = read_reference(reference, root)
    if frozen.get('protocol') != PROTOCOL or path.name != 'freeze.json':
        raise ValueError('not an anchored Phase4 candidate freeze')
    _separate(root, frozen['research_roots'])
    for artifact in frozen['artifacts'].values():
        if hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest() != artifact['sha256']:
            raise ValueError('frozen source or deployment artifact drifted')
    return root, frozen


def freeze_candidate(private_root, *, artifacts, arms, launch_protocol, gpus,
                     seen_input_hashes, research_roots, purpose='scientific-candidate'):
    """Freeze before loading unseen requests; caller retains the returned SHA anchor."""
    if (purpose not in ('scientific-candidate', 'controller-negative-control') or
            not artifacts or len(arms) != 2 or [arm.get('name') for arm in arms] != ['stock', 'candidate'] or
            any(not valid_digest(arm.get('tree_sha')) or type(arm.get('block')) is not int or
                arm['block'] < 1 or not isinstance(arm.get('env'), dict) for arm in arms) or
            arms[0]['block'] != 8 or arms[0]['env'] or
            not launch_protocol.get('model_path') or len(gpus) != 2 or
            len({gpu['uuid'] for gpu in gpus}) != 2 or
            len({gpu['index'] for gpu in gpus}) != 2 or not research_roots or
            any(not valid_digest(value) for value in seen_input_hashes)):
        raise ValueError('complete frozen stock/candidate deployment and research scope required')
    if purpose == 'controller-negative-control' and (arms[1].get('option_enabled') is not False or
            any(arms[0].get(key) != arms[1].get(key) for key in ('tree_sha', 'block', 'env', 'engine'))):
        raise ValueError('negative control requires canonical stock on both arms with option disabled')
    root = Path(private_root).absolute()
    research_roots = [str(Path(path).resolve()) for path in research_roots]
    _separate(root.resolve(), research_roots)
    inventory = {}
    for name, path in artifacts.items():
        path = Path(path).resolve(strict=True)
        inventory[name] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    root.mkdir(mode=0o700)
    _private(root, directory=True)
    return _save(root / 'freeze.json', dict(protocol=PROTOCOL, purpose=purpose, frozen_unix=time.time(),
        artifacts=inventory, arms=arms, launch_protocol=launch_protocol, gpus=gpus,
        seen_input_hashes=sorted(set(seen_input_hashes)), research_roots=research_roots))


def open_phase4(freeze, request_path):
    """Load a private request file once, after freeze; never call from a research UID."""
    root, frozen = _frozen(freeze)
    source = _private(request_path)
    _private(source.parent, directory=True)
    _separate(source, frozen['research_roots'])
    content = source.read_bytes()
    requests = json.loads(content)
    if not isinstance(requests, list) or not requests:
        raise ValueError('nonempty unseen cohort required')
    identifiers, hashes = set(), set()
    for request in requests:
        checked_tokens(request['input_ids'])
        checksum = sha_ids(request['input_ids'])
        if (not isinstance(request.get('id'), str) or not request['id'] or
                not isinstance(request.get('suite'), str) or not request['suite'] or
                request.get('turn') != 0 or request.get('input_sha256') != checksum or
                request['id'] in identifiers or checksum in hashes or checksum in frozen['seen_input_hashes']):
            raise ValueError('duplicate, seen or incorrectly hashed unseen request')
        identifiers.add(request['id'])
        hashes.add(checksum)
    return _save(root / 'phase4.json', dict(protocol=PROTOCOL, freeze=freeze,
        opened_unix=time.time(), requests=requests,
        request_source=dict(path=str(source), sha256=hashlib.sha256(content).hexdigest()),
        caps=list(CAPS), phases=list(PHASES), rounds=2))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _ordered(phases):
    previous = -math.inf
    for phase in phases:
        start, finish = phase.get('started_unix'), phase.get('completed_unix')
        if not _number(start) or not _number(finish) or not previous <= start < finish:
            raise ValueError('physical rounds or campaign phases overlap or are out of order')
        previous = finish


def _process(assignment):
    process = assignment['process']
    if (not isinstance(process.get('host_boot_id'), str) or not process['host_boot_id'] or
            any(type(process.get(key)) is not int or process[key] <= 0 for key in ('pid', 'start_ticks'))):
        raise ValueError('complete server process identity required')
    return tuple(process[key] for key in ('host_boot_id', 'pid', 'start_ticks'))


def _sample(sample, request, assignment, cap, root, frozen, round_number, lower, upper):
    if (sample.get('id') != request['id'] or sample.get('suite') != request['suite'] or
            sample.get('round') != round_number or sample.get('turn') != 0):
        raise ValueError('timed sample identity drifted')
    checked_tokens(sample['output_ids'])
    if any(not _number(sample.get(key)) or sample[key] <= 0 for key in ('latency_s', 'tokens_per_s')):
        raise ValueError('positive finite actual timing required')
    validate_packet(sample, request, assignment, cap, root, frozen['launch_protocol'])
    timing = sample['client_timing']
    start, finish = timing.get('started_unix'), timing.get('finished_unix')
    if (not _number(start) or not _number(finish) or not lower <= start < finish <= upper or
            abs(finish - start - sample['latency_s']) > .005):
        raise ValueError('sample escaped its physical execution interval')
    identity = read_reference(sample['generator']['evidence'], root)
    if not lower <= identity.get('started_unix', -math.inf) <= start:
        raise ValueError('generator identity is not from this fresh server session')
    return start, finish


def _round(record, *, cap, phase, number, root, frozen, requests, used_processes):
    if record.get('protocol') != PROTOCOL or record.get('cap') != cap or record.get('round') != number:
        raise ValueError('not a native Phase4 physical round')
    if record.get('complete') != dict(pairs=len(requests), exit_code=0):
        raise ValueError('incomplete or failed physical round')
    times = [record.get(key) for key in ('started_unix', 'ready_unix', 'warmup_complete_unix', 'finished_unix')]
    if any(not _number(value) for value in times) or not times[0] < times[1] < times[2] < times[3]:
        raise ValueError('invalid fresh server lifecycle')
    assignments = record['assignments']
    arms = frozen['arms'] if phase == 'candidate' else [
        dict(frozen['arms'][0], name='stock-a'), dict(frozen['arms'][0], name='stock-b')]
    if (len(assignments) != 2 or [assignment['arm'] for assignment in assignments] != arms or
            sorted((assignment['gpu'] for assignment in assignments), key=lambda gpu: gpu['uuid']) !=
            sorted(frozen['gpus'], key=lambda gpu: gpu['uuid']) or
            len({assignment['gpu']['uuid'] for assignment in assignments}) != 2 or
            len({assignment['port'] for assignment in assignments}) != 2):
        raise ValueError('two distinct physical GPUs/endpoints and frozen arms required')
    for assignment in assignments:
        process = _process(assignment)
        if process in used_processes:
            raise ValueError('server process reused in another arm, round or phase')
        used_processes.add(process)
    warm_requests = requests[:2] + requests
    expected = ['short'] * len(requests[:2]) + ['full'] * len(requests)
    warmup = record['warmup']
    if len(warmup) != len(expected) or [row.get('phase') for row in warmup] != expected:
        raise ValueError('complete predeclared short/full warmup required')
    for row, request, warm_phase in zip(warmup, warm_requests, expected):
        for key, assignment in zip(('a', 'b'), assignments):
            start, finish = _sample(row[key], request, assignment, 32 if warm_phase == 'short' else cap,
                                   root, frozen, number, times[0], times[2])
            if start < times[1]:
                raise ValueError('warmup began before fresh server readiness')
    pairs = record['pairs']
    if [pair.get('id') for pair in pairs] != [request['id'] for request in requests]:
        raise ValueError('missing, duplicate or reordered paired request')
    previous = times[2]
    for pair, request in zip(pairs, requests):
        intervals = [_sample(pair[key], request, assignment, cap, root, frozen, number, times[0], times[3])
                     for key, assignment in zip(('a', 'b'), assignments)]
        if min(finish for start, finish in intervals) <= max(start for start, finish in intervals):
            raise ValueError('single-card serial execution is not a physical pair')
        if min(start for start, finish in intervals) < previous:
            raise ValueError('measurements overlap warmup or previous request')
        previous = max(finish for start, finish in intervals)
    during = [snapshot for snapshot in record['telemetry']
              if times[2] <= snapshot['time_unix'] <= previous]
    if len(during) < 2 or any('error' in snapshot for snapshot in record['telemetry']):
        raise ValueError('complete measurement telemetry required')
    for snapshot in during:
        if {gpu['uuid'] for gpu in snapshot['gpus']} != {entry['gpu']['uuid'] for entry in assignments}:
            raise ValueError('telemetry physical GPUs differ')
        for gpu in snapshot['gpus']:
            if any(not _number(gpu.get(key)) or gpu[key] <= 0 for key in
                   ('clocks_sm_mhz', 'clocks_mem_mhz', 'temperature_c', 'power_w')):
                raise ValueError('invalid measured GPU state')
        if any(snapshot['arms'].get(entry['arm']['name']) != entry['process'] for entry in assignments):
            raise ValueError('live process identity differs from deployment')
    return assignments, pairs


def _session(reference, *, root, frozen, requests, cap, phase, used_processes):
    session = read_reference(reference, root)
    if (session.get('protocol') != PROTOCOL or session.get('cap') != cap or
            session.get('phase') != phase or len(session.get('rounds', [])) != 2):
        raise ValueError('both declared Phase4 physical rounds required')
    records, pairs_by_round, mappings = [], [], []
    for number, source in enumerate(session['rounds'], 1):
        record = read_reference(source, root)
        assignments, pairs = _round(record, cap=cap, phase=phase, number=number,
            root=root, frozen=frozen, requests=requests, used_processes=used_processes)
        records.append(record)
        pairs_by_round.append(pairs)
        mappings.append([assignment['gpu'] for assignment in assignments])
    if mappings[0] != list(reversed(mappings[1])):
        raise ValueError('physical GPUs were not exchanged')
    _ordered([dict(started_unix=record['started_unix'], completed_unix=record['finished_unix'])
              for record in records])
    groups = {}
    for index, request in enumerate(requests):
        values = [math.log(pairs[index]['b']['tokens_per_s'] / pairs[index]['a']['tokens_per_s'])
                  for pairs in pairs_by_round]
        groups.setdefault(request['suite'], []).append(sum(values) / 2)
        if phase != 'candidate':
            outputs = [pair[index][key]['output_sha256'] for pair in pairs_by_round for key in ('a', 'b')]
            if len(set(outputs)) != 1:
                raise ValueError('stock null outputs differ across arms or physical rounds')
    return dict(groups=groups, pairs=pairs_by_round, started_unix=records[0]['started_unix'],
                completed_unix=records[-1]['finished_unix'], source=reference)


def _forcing(entry, *, root, frozen, requests, pairs, completed_unix):
    paths = {}
    for role, key in (('stock', 'a'), ('candidate', 'b'), ('ar', None)):
        sources = entry[role]
        if len(sources) != len(requests):
            raise ValueError('complete scored cohort required')
        for source in sources:
            read_reference(source, root)
        paths[role] = [source['path'] for source in sources]
        if key is not None:
            check_scored_measurements(paths[role], [pair[key] for pair in pairs], requests, evidence_root=root)
        for path, request in zip(paths[role], requests):
            trace = load_score_trace(path, evidence_root=root)
            scorer = trace['scorer']
            raw = read_reference(trace['raw_evidence'], root)
            if (trace['request_id'] != request['id'] or trace['prompt_ids'] != request['input_ids'] or
                    scorer['tree_sha'] != frozen['arms'][0]['tree_sha'] or
                    scorer['server_args'].get('speculative_algorithm') is not None or
                    not _number(raw.get('started_unix')) or raw['started_unix'] < completed_unix):
                raise ValueError('wrong stock scorer/prompt or scoring overlapped performance')
            if role == 'ar' and (trace['generator']['tree_sha'] != frozen['arms'][0]['tree_sha'] or
                                trace['generator']['server_args'].get('speculative_algorithm') is not None):
                raise ValueError('AR calibration must use the frozen stock tree')
    delta = calibrate_delta(paths['stock'], paths['ar'], evidence_root=root)
    baseline = calibrate_stock(paths['stock'], delta, evidence_root=root)
    audits = entry.get('prefill_audits', [])
    for source in audits:
        read_reference(source, root)
    return judge_scored_forcing(baseline, paths['candidate'], evidence_root=root,
                                prefill_audits=[source['path'] for source in audits])


def validate_phase4(opened, evidence):
    """Recompute private evidence; never returns a real T3 or promotion authorization."""
    path = _private(opened['path'])
    root = _private(path.parent, directory=True)
    state = read_reference(opened, root)
    freeze_root, frozen = _frozen(state['freeze'])
    if root != freeze_root or state.get('protocol') != PROTOCOL:
        raise ValueError('Phase4 state is not bound to its freeze')
    source = _private(state['request_source']['path'])
    _private(source.parent, directory=True)
    _separate(source, frozen['research_roots'])
    if (hashlib.sha256(source.read_bytes()).hexdigest() != state['request_source']['sha256'] or
            json.loads(source.read_bytes()) != state['requests'] or
            not frozen['frozen_unix'] <= state['opened_unix']):
        raise ValueError('unseen cohort or freeze chronology drifted')
    packet = read_reference(evidence, root)
    expected = [(cap, phase) for cap in CAPS for phase in PHASES]
    if (packet.get('protocol') != PROTOCOL or packet.get('phase4_sha256') != opened['sha256'] or
            [(entry.get('cap'), entry.get('phase')) for entry in packet.get('sessions', [])] != expected or
            [(entry.get('cap'), entry.get('round')) for entry in packet.get('forcing', [])] !=
            [(cap, number) for cap in CAPS for number in (1, 2)]):
        raise ValueError('complete native Phase4 schedule and forcing required; dev is not sealed')
    sessions, used_processes = {}, set()
    for entry in packet['sessions']:
        sessions[entry['cap'], entry['phase']] = _session(entry['source'], root=root, frozen=frozen,
            requests=state['requests'], cap=entry['cap'], phase=entry['phase'], used_processes=used_processes)
    _ordered([sessions[key] for key in expected])
    if sessions[expected[0]]['started_unix'] < state['opened_unix']:
        raise ValueError('measurements predate candidate freeze and request opening')
    completed = sessions[expected[-1]]['completed_unix']
    results = []
    for cap in CAPS:
        protocol_id = digest_record(dict(phase4=opened['sha256'], cap=cap))
        campaign_id = opened['sha256']
        nulls = [sessions[cap, phase] for phase in ('null-pre', 'null-post')]
        calibration = calibration_from_intervals([
            dict(session_id=phase, protocol_id=protocol_id, source_sha256=session['source']['sha256'],
                 interval=stratified_geomean_ci(session['groups']))
            for phase, session in zip(('null-pre', 'null-post'), nulls)],
            declared_sessions=['null-pre', 'null-post'], protocol_id=protocol_id,
            campaign_id=campaign_id, policy=POLICY)
        candidate = sessions[cap, 'candidate']
        correct = combine_correctness([_forcing(entry, root=root, frozen=frozen, requests=state['requests'],
            pairs=candidate['pairs'][entry['round'] - 1], completed_unix=completed)
            for entry in packet['forcing'] if entry['cap'] == cap])
        identical = all(pair['a']['output_ids'] == pair['b']['output_ids']
                        for pairs in candidate['pairs'] for pair in pairs)
        performance = candidate_verdict(groups=candidate['groups'], calibration=calibration,
            correctness=correct, protocol_id=protocol_id, campaign_id=campaign_id, output_identical=identical)
        results.append(dict(cap=cap, correctness=correct, noise_calibration=calibration, performance=performance))
    result = dict(protocol=PROTOCOL, phase4_sha256=opened['sha256'], evidence=evidence, caps=results,
        protocol_evidence_passed=all(result['performance']['eligible_for_promotion'] for result in results),
        t3_passed=False, promoted=False, ledger_eligible=False, missing_runtime=list(MISSING_RUNTIME),
        scope='untrusted-runtime evidence contract only; synthetic fixtures and dev are not true T3')
    return dict(result, evidence_sha256=digest_record(result))
