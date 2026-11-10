"""Independent CPU acceptance registered before implementation:

python -B -m unittest harness.test_phase4_readiness_independent -v
Log: logs/skills-rsi-20261110-b01/controller-tests/readiness-independent-first.log
Use non-sensitive synthetic native packets and real controller forcing/calibration.
Reject public/private substitution, regenerated timed outputs, missing calibration
and absent stock/AR divergence. Never read real private data or execute GPU/model.
"""

import copy
import json
import unittest
from unittest.mock import patch

from controller import scored_forcing, sealed_protocol
from controller.http_transport import sha_ids
from exp import phase4_run
from harness import test_p5_scored_forcing as scoring_fixtures
from harness import test_sealed_protocol as protocol_fixtures


class IndependentReadinessIsolationTests(unittest.TestCase):
    def setUp(self):
        self.helper = protocol_fixtures.SealedProtocolTests()
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.helper.fixture(lengths={2048: 8, 4096: 9})
        self.root = self.helper.root
        self.frozen = scored_forcing.read_reference(self.helper.freeze, self.root)
        self.completed = max(record['finished_unix'] for rounds in self.helper.records.values() for record in rounds)
        self.scoring = scoring_fixtures.ScoredForcingTests()
        self.scoring.root = self.root
        self.scoring.counter = 50000

    def trace(self, output, *, request_id='unseen', prompt=None, role='ar', mismatches=None):
        path = self.scoring.trace(output, request_id=request_id, prompt=prompt, role=role, mismatches=mismatches)
        trace = json.loads(path.read_text())
        for key in ('generator', 'scorer'):
            trace[key]['server_args']['model_path'] = '/fixture'
            evidence = scored_forcing.read_reference(trace[key]['evidence'], self.root)
            evidence['response']['server_args']['model_path'] = '/fixture'
            trace[key]['evidence'] = self.helper.save(evidence)
        raw = scored_forcing.read_reference(trace['raw_evidence'], self.root)
        raw['started_unix'] = self.completed + 1
        trace['raw_evidence'] = self.helper.save(raw)
        return self.helper.save(trace)

    def force(self, entry=None):
        entry = self.helper.forcing[0] if entry is None else entry
        pairs = self.helper.records[entry['cap'], 'candidate'][entry['round'] - 1]['pairs']
        return sealed_protocol._forcing(entry, root=self.root, frozen=self.frozen,
            requests=self.helper.requests, pairs=pairs, completed_unix=self.completed)

    def test_real_private_short_outputs_calibrate_without_any_public_readiness_value(self):
        verdict = self.force()
        self.assertTrue(verdict['correctness_passed'])
        self.assertEqual(verdict['delta'], .125)
        self.assertEqual(scored_forcing.load_score_trace(self.helper.forcing[0]['stock'][0]['path'],
                         evidence_root=self.root)['output_tokens'], 8)

    def test_public_request_cannot_replace_private_ar_even_with_valid_native_packets(self):
        entry = copy.deepcopy(self.helper.forcing[0])
        entry['ar'] = [self.trace([4, 4, 6] + [4] * 5, request_id='public-readiness', prompt=[2, 12])]
        with self.assertRaisesRegex(ValueError, 'scorer/prompt|requests must match'):
            self.force(entry)

    def test_private_id_cannot_hide_public_prompt_in_ar_calibration(self):
        entry = copy.deepcopy(self.helper.forcing[0])
        entry['ar'] = [self.trace([4, 4, 6] + [4] * 5, prompt=[2, 12])]
        with self.assertRaisesRegex(ValueError, 'scorer/prompt|prompts'):
            self.force(entry)

    def test_public_stock_or_candidate_cannot_replace_original_timed_trace(self):
        public = self.trace([4] * 8, request_id='public-readiness', prompt=[2, 12], role='stock')
        for role in ('stock', 'candidate'):
            entry = copy.deepcopy(self.helper.forcing[0])
            entry[role] = [public]
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'exact original timed generation'):
                self.force(entry)

    def test_same_tokens_regenerated_are_not_the_original_timed_output(self):
        replacement = self.trace([4] * 8, role='stock', mismatches={2: (6, .1)})
        for role in ('stock', 'candidate'):
            entry = copy.deepcopy(self.helper.forcing[0])
            entry[role] = [replacement]
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'exact original timed generation'):
                self.force(entry)

    def test_missing_private_stock_or_ar_does_not_inherit_public_ready_bool(self):
        for role in ('stock', 'ar'):
            entry = copy.deepcopy(self.helper.forcing[0])
            entry.update(scientific_ready=True, delta=1234, calibration={'passed': True})
            entry[role] = []
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'complete scored cohort'):
                self.force(entry)

    def test_no_private_first_divergence_rejected_despite_public_readiness_success(self):
        entry = copy.deepcopy(self.helper.forcing[0])
        entry.update(scientific_ready=True, delta=8.0, calibration={'passed': True})
        entry['ar'] = [self.trace([4] * 8)]
        with self.assertRaisesRegex(ValueError, 'delta is not calibrated'):
            self.force(entry)

    def test_public_delta_cannot_raise_private_error_tolerance(self):
        public_stock = self.trace([4] * 8, role='stock', request_id='public-readiness', prompt=[2, 12], mismatches={2: (6, 8)})
        public_ar = self.trace([4, 4, 6] + [4] * 5, request_id='public-readiness', prompt=[2, 12])
        public_delta = scored_forcing.calibrate_delta([public_stock['path']], [public_ar['path']], evidence_root=self.root)
        self.assertEqual(public_delta['delta'], 8)
        entry = copy.deepcopy(self.helper.forcing[0])
        entry.update(delta=public_delta['delta'], calibration=public_delta, scientific_ready=True)
        verdict = self.force(entry)
        self.assertEqual(verdict['delta'], .125)

    def test_readiness_reference_cannot_point_to_private_request_cohort(self):
        public = [dict(id='public-fixed', suite='fixture-suite', input_ids=[11, 12], input_sha256=sha_ids([11, 12]))]
        reference = self.helper.save(dict(requests=self.helper.requests))
        source = self.helper.save(dict(phase4_sha256=self.helper.opened['sha256'],
            readiness_protocol=phase4_run.READINESS_PROTOCOL, reference=reference))
        with patch.object(phase4_run, 'load_readiness_requests', return_value=public), \
                patch.object(phase4_run, 'checked_head', side_effect=AssertionError('private readiness must reject before head')):
            with self.assertRaisesRegex(ValueError, 'fixed public dev cohort'):
                phase4_run.validate_science(source, root=self.root, frozen=self.frozen,
                    phase4_sha256=self.helper.opened['sha256'], not_before=self.completed)

    def test_readiness_rejects_protocol_or_opening_relabel_before_scoring(self):
        public = [dict(id='public-fixed', suite='fixture-suite', input_ids=[11, 12], input_sha256=sha_ids([11, 12]))]
        reference = self.helper.save(dict(requests=public))
        for change in (dict(readiness_protocol='private-readiness'), dict(phase4_sha256='0' * 64)):
            value = dict(phase4_sha256=self.helper.opened['sha256'], readiness_protocol=phase4_run.READINESS_PROTOCOL,
                         reference=reference)
            value.update(change)
            source = self.helper.save(value)
            with self.subTest(change=change), patch.object(phase4_run, 'load_readiness_requests', return_value=public), \
                    patch.object(phase4_run, 'checked_head', side_effect=AssertionError('relabelled readiness must reject')):
                with self.assertRaises(ValueError):
                    phase4_run.validate_science(source, root=self.root, frozen=self.frozen,
                        phase4_sha256=self.helper.opened['sha256'], not_before=self.completed)


if __name__ == '__main__':
    unittest.main()
