import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from controller.http_transport import sha_ids
from controller.sealed_protocol import CAPS, PHASES, PROTOCOL, freeze_candidate, open_phase4, validate_phase4
from harness import test_p5_scored_forcing as scored_tests


class SealedProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.research = self.base / 'research'
        self.research.mkdir()
        self.artifact = self.research / 'candidate.py'
        self.artifact.write_text('OPTION = False\n')
        self.root = self.base / 'controller'
        self.arms = [dict(name=name, tree_sha=checksum * 64, block=block, env={})
                     for name, checksum, block in (('stock', 'a', 8), ('candidate', 'b', 12))]
        self.gpus = [dict(index=index, uuid=f'gpu-{index}', name='H100') for index in (0, 1)]
        self.freeze_args = dict(artifacts={'candidate': self.artifact}, arms=self.arms,
            launch_protocol=dict(model_path='/fixture', dtype='bfloat16', enable_fp32_lm_head=False),
            gpus=self.gpus, seen_input_hashes=[sha_ids([7, 8])], research_roots=[self.research])
        self.freeze = freeze_candidate(self.root, **self.freeze_args)
        self.requests = [dict(id='unseen', suite='fixture-suite', turn=0,
                              input_ids=[2, 3], input_sha256=sha_ids([2, 3]))]
        self.request_file = self.base / 'requests.json'
        self.request_file.write_text(json.dumps(self.requests))
        self.request_file.chmod(0o600)
        self.counter = 0

    def save(self, value):
        self.counter += 1
        path = self.root / f'evidence-{self.counter}.json'
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def open(self):
        self.opened = open_phase4(self.freeze, self.request_file)
        self.state = json.loads(Path(self.opened['path']).read_text())

    def sample(self, assignment, number, cap, start, latency, identity_start):
        request = self.requests[0]
        output = [4] * self.lengths.get(cap, cap)
        finish_reason = 'length' if len(output) == cap else 'stop'
        args = dict(self.freeze_args['launch_protocol'], speculative_algorithm='DFLASH',
                    speculative_num_draft_tokens=assignment['arm']['block'])
        generator = dict(tree_sha=assignment['arm']['tree_sha'], server_args=args,
            evidence=self.save(dict(http_status=200, response={'server_args': args}, started_unix=identity_start)))
        raw = self.save(dict(http_status=200,
            request=dict(input_ids=request['input_ids'],
                         sampling_params=dict(temperature=0.0, top_k=1, max_new_tokens=cap)),
            response=dict(output_ids=output, meta_info=dict(completion_tokens=len(output),
                                                          finish_reason={'type': finish_reason}))))
        duration_ns = round(latency * 1e9)
        return dict(id=request['id'], suite=request['suite'], turn=0, round=number,
            arm=assignment['arm']['name'], tree_sha=assignment['arm']['tree_sha'], block=assignment['arm']['block'],
            gpu_uuid=assignment['gpu']['uuid'], input_sha256=request['input_sha256'],
            output_ids=output, output_sha256=sha_ids(output), completion_tokens=len(output),
            max_new_tokens=cap, latency_s=latency, tokens_per_s=len(output) / latency,
            finish_reason=finish_reason, raw_evidence=raw, generator=generator,
            client_timing=dict(step_start_ns=1, http_open_start_ns=2,
                body_complete_ns=duration_ns, step_end_ns=duration_ns + 1,
                started_unix=start, finished_unix=start + latency,
                url=f'http://127.0.0.1:{assignment["port"]}/generate'))

    def fixture(self, speedup=1.2, null_ratio=1.0, fault=False, lengths=None):
        self.lengths = lengths or {}
        self.open()
        self.records = {}
        serial = 0
        for cap in CAPS:
            for phase in PHASES:
                rounds = []
                arms = self.arms if phase == 'candidate' else [
                    dict(self.arms[0], name='stock-a'), dict(self.arms[0], name='stock-b')]
                for number in (1, 2):
                    serial += 1
                    start = self.state['opened_unix'] + serial * 100
                    gpus = self.gpus if number == 1 else list(reversed(self.gpus))
                    assignments = [dict(arm=arm, gpu=gpu, port=32000 + index,
                        process=dict(host_boot_id='fixture-boot', pid=serial * 10 + index + 1,
                                     start_ticks=serial * 100 + index + 1))
                        for index, (arm, gpu) in enumerate(zip(arms, gpus))]
                    warm = []
                    for offset, warm_phase in enumerate(('short', 'full')):
                        warm.append(dict(phase=warm_phase, **{key: self.sample(assignment, number,
                            32 if warm_phase == 'short' else cap, start + 2 + offset * 2, 1, start + .5)
                            for key, assignment in zip(('a', 'b'), assignments)}))
                    ratio = speedup if phase == 'candidate' else null_ratio
                    pair = dict(id=self.requests[0]['id'], **{key: self.sample(assignment, number, cap,
                        start + 10, 2 if key == 'a' else 2 / ratio, start + .5)
                        for key, assignment in zip(('a', 'b'), assignments)})
                    telemetry = [dict(time_unix=start + offset,
                        gpus=[dict(gpu, clocks_sm_mhz=1000, clocks_mem_mhz=1000,
                                   temperature_c=40, power_w=100) for gpu in self.gpus],
                        arms={entry['arm']['name']: entry['process'] for entry in assignments})
                        for offset in (10, 11)]
                    rounds.append(dict(protocol=PROTOCOL, cap=cap, round=number,
                        complete=dict(pairs=1, exit_code=0), started_unix=start, ready_unix=start + 1,
                        warmup_complete_unix=start + 8, finished_unix=start + 20,
                        assignments=assignments, warmup=warm, pairs=[pair], telemetry=telemetry))
                self.records[cap, phase] = rounds
        helper = scored_tests.ScoredForcingTests()
        helper.root = self.root
        helper.counter = 10000
        self.forcing = []
        scoring_start = start + 30
        for cap in CAPS:
            for number in (1, 2):
                entry = dict(cap=cap, round=number)
                pair = self.records[cap, 'candidate'][number - 1]['pairs'][0]
                for role, key in (('stock', 'a'), ('candidate', 'b'), ('ar', None)):
                    length = len(pair['a']['output_ids'])
                    output = [4] * length if key else [4, 4, 6] + [4] * (length - 3)
                    mismatches = {2: (6, .1)} if key else {}
                    if fault and role == 'candidate' and cap == 4096:
                        mismatches.update({index: (6, 2) for index in range(2048, length)})
                    path = helper.trace(output, mismatches=mismatches,
                        role='ar' if key is None else 'stock', request_id='unseen')
                    trace = json.loads(path.read_text())
                    for identity in ('scorer', 'generator'):
                        trace[identity]['server_args']['model_path'] = '/fixture'
                        raw = json.loads(Path(trace[identity]['evidence']['path']).read_text())
                        raw['response']['server_args']['model_path'] = '/fixture'
                        trace[identity]['evidence'] = self.save(raw)
                    if key:
                        trace['generator'] = pair[key]['generator']
                        trace['generation_segments'] = [pair[key]['raw_evidence']]
                    raw = json.loads(Path(trace['raw_evidence']['path']).read_text())
                    raw['started_unix'] = scoring_start
                    trace['raw_evidence'] = self.save(raw)
                    entry[role] = [self.save(trace)]
                self.forcing.append(entry)
        return self.publish()

    def publish(self):
        sessions = []
        for cap in CAPS:
            for phase in PHASES:
                source = self.save(dict(protocol=PROTOCOL, cap=cap, phase=phase,
                    rounds=[self.save(record) for record in self.records[cap, phase]]))
                sessions.append(dict(cap=cap, phase=phase, source=source))
        self.packet = dict(protocol=PROTOCOL, phase4_sha256=self.opened['sha256'],
                           sessions=sessions, forcing=self.forcing)
        return self.save(self.packet)

    def test_freeze_and_private_open_are_exclusive_and_anchored(self):
        self.open()
        self.assertEqual(os.stat(self.root).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.freeze['path']).st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): open_phase4(self.freeze, self.request_file)
        changed = dict(self.freeze, sha256='0' * 64)
        with self.assertRaises(ValueError): open_phase4(changed, self.request_file)

    def test_dev_renaming_empty_duplicate_and_bad_hash_requests_are_rejected(self):
        variants = [[], [dict(self.requests[0], id='dev-renamed', input_ids=[7, 8], input_sha256=sha_ids([7, 8]))],
            self.requests * 2, [dict(self.requests[0], input_sha256='0' * 64)],
            [dict(self.requests[0], input_ids=[])],
            self.requests + [dict(self.requests[0], id='different-id')]]
        for requests in variants:
            with self.subTest(requests=requests):
                self.request_file.write_text(json.dumps(requests))
                with self.assertRaises(ValueError): open_phase4(self.freeze, self.request_file)

    def test_permissions_research_overlap_symlink_and_artifact_drift_are_rejected(self):
        self.request_file.chmod(0o644)
        with self.assertRaises(ValueError): open_phase4(self.freeze, self.request_file)
        self.request_file.chmod(0o600)
        research_input = self.research / 'requests.json'
        research_input.write_bytes(self.request_file.read_bytes())
        research_input.chmod(0o600)
        self.research.chmod(0o700)
        with self.assertRaises(ValueError): open_phase4(self.freeze, research_input)
        link = self.base / 'link.json'
        link.symlink_to(self.request_file)
        with self.assertRaises(ValueError): open_phase4(self.freeze, link)
        self.artifact.write_text('OPTION = True\n')
        with self.assertRaises(ValueError): open_phase4(self.freeze, self.request_file)

    def test_complete_fixture_recomputes_correctness_but_never_authorizes_t3(self):
        evidence = self.fixture()
        result = validate_phase4(self.opened, evidence)
        self.assertTrue(result['protocol_evidence_passed'])
        self.assertEqual([entry['cap'] for entry in result['caps']], [2048, 4096])
        self.assertTrue(all(entry['correctness']['correctness_passed'] for entry in result['caps']))
        self.assertEqual(result['caps'][0]['correctness']['rounds'][0]['delta'], .125)
        for flag in ('t3_passed', 'promoted', 'ledger_eligible'):
            self.assertFalse(result[flag])
        self.assertTrue(result['missing_runtime'])

    def test_real_event_rule_rejects_post2048_fault_despite_uploaded_passed_flags(self):
        evidence = self.fixture(fault=True)
        self.packet.update(passed=True, correctness_passed=True, t3_passed=True)
        result = validate_phase4(self.opened, self.save(self.packet))
        self.assertFalse(result['protocol_evidence_passed'])
        self.assertTrue(result['caps'][1]['correctness']['rounds'][0]['event_flagged'])
        self.assertFalse(result['caps'][1]['correctness']['correctness_passed'])

    def test_natural_eos_is_allowed_without_truncating_the_scored_output(self):
        evidence = self.fixture(lengths={2048: 96, 4096: 2064})
        result = validate_phase4(self.opened, evidence)
        self.assertTrue(result['protocol_evidence_passed'])
        self.assertEqual(result['caps'][1]['correctness']['rounds'][0]['n'], 2064)

    def test_insufficient_gain_and_high_measured_noise_do_not_pass(self):
        self.fixture(speedup=1.005)
        result = validate_phase4(self.opened, self.publish())
        self.assertFalse(result['protocol_evidence_passed'])
        for cap in CAPS:
            for record in self.records[cap, 'candidate']:
                row = record['pairs'][0]['b']
                row['latency_s'] = 2 / 1.2
                row['tokens_per_s'] = cap / row['latency_s']
                timing = row['client_timing']
                timing.update(finished_unix=timing['started_unix'] + row['latency_s'],
                    body_complete_ns=round(row['latency_s'] * 1e9),
                    step_end_ns=round(row['latency_s'] * 1e9) + 1)
            for phase in ('null-pre', 'null-post'):
                for record in self.records[cap, phase]:
                    row = record['pairs'][0]['b']
                    row['latency_s'] = 2 / 1.15
                    row['tokens_per_s'] = cap / row['latency_s']
                    timing = row['client_timing']
                    timing.update(finished_unix=timing['started_unix'] + row['latency_s'],
                        body_complete_ns=round(row['latency_s'] * 1e9),
                        step_end_ns=round(row['latency_s'] * 1e9) + 1)
        result = validate_phase4(self.opened, self.publish())
        self.assertFalse(result['protocol_evidence_passed'])
        self.assertAlmostEqual(result['caps'][0]['noise_calibration']['noise'], .15)

    def test_missing_cap_round_forcing_and_dev_protocol_are_rejected(self):
        self.fixture()
        for change in ('cap', 'round', 'forcing', 'dev', 'anchor'):
            packet = copy.deepcopy(self.packet)
            if change == 'cap': packet['sessions'] = packet['sessions'][:3]
            if change == 'forcing': packet['forcing'].pop()
            if change == 'dev': packet['protocol'] = 'dev-joint-v1'
            if change == 'anchor': packet['phase4_sha256'] = '0' * 64
            if change == 'round':
                session = dict(protocol=PROTOCOL, cap=2048, phase='null-pre',
                               rounds=[self.save(self.records[2048, 'null-pre'][0])])
                packet['sessions'][0]['source'] = self.save(session)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_phase4(self.opened, self.save(packet))

    def test_missing_swap_reused_one_arm_serial_warmup_and_telemetry_are_rejected(self):
        self.fixture()
        original = copy.deepcopy(self.records)
        for change in ('swap', 'one-arm-reuse', 'serial', 'warmup', 'telemetry', 'gpu', 'failed'):
            self.records = copy.deepcopy(original)
            first, second = self.records[2048, 'candidate']
            if change == 'swap':
                for index, key in enumerate(('a', 'b')):
                    gpu = first['assignments'][index]['gpu']
                    second['assignments'][index]['gpu'] = gpu
                    for row in second['warmup'] + second['pairs']:
                        row[key]['gpu_uuid'] = gpu['uuid']
            if change == 'one-arm-reuse': second['assignments'][0]['process'] = first['assignments'][0]['process']
            if change == 'serial':
                timing = second['pairs'][0]['b']['client_timing']
                timing['started_unix'] += 3
                timing['finished_unix'] += 3
            if change == 'warmup': second['warmup'].pop()
            if change == 'telemetry': second['telemetry'].pop()
            if change == 'gpu': second['assignments'][0]['gpu']['uuid'] = 'unmatched-gpu'
            if change == 'failed': second['complete']['exit_code'] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_phase4(self.opened, self.publish())

    def test_well_formed_replacement_trace_cannot_replace_the_timed_output(self):
        self.fixture()
        helper = scored_tests.ScoredForcingTests()
        helper.root, helper.counter = self.root, 20000
        replacement = helper.trace([5] * 2048, request_id='unseen')
        self.forcing[0]['candidate'] = [dict(path=str(replacement),
            sha256=hashlib.sha256(replacement.read_bytes()).hexdigest())]
        with self.assertRaisesRegex(ValueError, 'exact original timed generation'):
            validate_phase4(self.opened, self.publish())

    def test_overlap_preopening_measurement_and_early_scoring_are_rejected(self):
        self.fixture()
        original = copy.deepcopy(self.records)
        first, second = self.records[2048, 'null-pre']
        first['finished_unix'] = second['started_unix'] + 1
        with self.assertRaisesRegex(ValueError, 'out of order'):
            validate_phase4(self.opened, self.publish())
        self.records = copy.deepcopy(original)
        self.state['opened_unix'] += 2000
        state_ref = self.save(self.state)
        self.opened = state_ref
        with self.assertRaisesRegex(ValueError, 'predate'):
            validate_phase4(self.opened, self.publish())
        self.state['opened_unix'] -= 2000
        self.opened = self.save(self.state)
        source = self.forcing[0]['stock'][0]
        trace = json.loads(Path(source['path']).read_text())
        raw = json.loads(Path(trace['raw_evidence']['path']).read_text())
        raw['started_unix'] = self.state['opened_unix']
        trace['raw_evidence'] = self.save(raw)
        self.forcing[0]['stock'] = [self.save(trace)]
        with self.assertRaisesRegex(ValueError, 'overlapped performance'):
            validate_phase4(self.opened, self.publish())

    def test_output_substitution_raw_hash_and_score_truncation_are_rejected(self):
        self.fixture()
        original = copy.deepcopy(self.forcing)
        for change in ('output', 'raw', 'scores', 'head', 'prompt'):
            self.forcing = copy.deepcopy(original)
            source = self.forcing[0]['candidate'][0]
            trace = json.loads(Path(source['path']).read_text())
            if change == 'output': trace['output_ids'][0] = 99
            if change == 'raw': trace['raw_evidence']['sha256'] = '0' * 64
            if change == 'scores': trace['scores'].pop()
            if change == 'head': trace['scorer']['server_args']['enable_fp32_lm_head'] = False
            if change == 'prompt': trace['prompt_ids'][0] = 99
            self.forcing[0]['candidate'] = [self.save(trace)]
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_phase4(self.opened, self.publish())

    def test_frozen_input_source_and_candidate_changes_invalidate_evidence(self):
        evidence = self.fixture()
        self.request_file.write_text('[]')
        with self.assertRaises(ValueError): validate_phase4(self.opened, evidence)
        self.request_file.write_text(json.dumps(self.requests))
        self.artifact.write_text('changed\n')
        with self.assertRaises(ValueError): validate_phase4(self.opened, evidence)


if __name__ == '__main__':
    unittest.main()
