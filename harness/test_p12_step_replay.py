import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class StepReplayTests(unittest.TestCase):
    def fixture(self):
        from controller.http_transport import sha_ids
        common=dict(schema='stock-step-v1',pid=42,rid='fixture',input_sha256=sha_ids([1,2]))
        initial=dict(common,sequence=0,kind='commit',phase='prefill',output_ids=[10],finished_len=None,
            finish_reason=None,verify_ct=0,correct_drafts=0,histogram=[],max_new_tokens=5,
            temperature=0.0,top_k=1,ignore_eos=False,eos_ids=[99],stop_ids=[],stop_strings=False)
        verify=dict(common,sequence=1,kind='verify',candidates=[10,20,30,40,50,60,70,80],
            target_pred=[20,30,99,41,51,61,71,81],accepted=2,bonus=99,commit_len=3,
            committed_ids=[20,30,99])
        final=dict(initial,sequence=2,phase='decode',output_ids=[10,20,30,99],finished_len=4,
            finish_reason=dict(type='stop',matched=99),verify_ct=1,correct_drafts=2,
            histogram=[0,0,1])
        return [initial,verify,final]

    def test_seed_and_greedy_chain_reconstruct_exact_output(self):
        from harness.step_replay import replay_request
        report=replay_request(self.fixture(),expected_output=[10,20,30,99])
        self.assertEqual(report['seed_tokens'],1)
        self.assertEqual(report['committed_verify_steps'],1)
        self.assertEqual(report['correct_drafts'],2)
        self.assertEqual(report['tail_clip_tokens'],0)
        self.assertEqual(report['output_tokens'],4)
        self.assertFalse(report['tau_best_available'])

    def test_wrong_accept_bonus_missing_step_and_output_are_rejected(self):
        from harness.step_replay import replay_request
        for field,value in [('accepted',3),('bonus',98),('commit_len',4),('committed_ids',[20,31,99])]:
            events=copy.deepcopy(self.fixture())
            events[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                replay_request(events,expected_output=[10,20,30,99])
        with self.assertRaises(ValueError):
            replay_request(self.fixture()[::2],expected_output=[10,20,30,99])
        with self.assertRaises(ValueError):
            replay_request(self.fixture(),expected_output=[10,20,31,99])

    def test_zero_full_accept_and_length_clip(self):
        from harness.step_replay import replay_request
        for accepted in (0,7):
            events=self.fixture()
            predictions=[21,31,41,51,61,71,81,91]
            predictions[:accepted]=events[1]['candidates'][1:accepted+1]
            committed=events[1]['candidates'][1:accepted+1]+[predictions[accepted]]
            events[1].update(target_pred=predictions,accepted=accepted,bonus=predictions[accepted],
                             commit_len=accepted+1,committed_ids=committed)
            full=[10]+committed
            cap=min(3,len(full))
            histogram=[0]*8
            histogram[accepted]=1
            events[2].update(output_ids=full,finished_len=cap,finish_reason=dict(type='length',length=cap),
                             max_new_tokens=cap,correct_drafts=accepted,histogram=histogram)
            events[0]['max_new_tokens']=cap
            report=replay_request(events,expected_output=full[:cap])
            self.assertEqual(report['tail_clip_tokens'],len(full)-cap)

    def test_uncommitted_overlap_tail_is_separate_and_checked(self):
        from harness.step_replay import replay_request
        events=self.fixture()
        tail=dict(events[1],sequence=3,candidates=[99,20,30,40,50,60,70,80])
        events.append(tail)
        report=replay_request(events,expected_output=[10,20,30,99])
        self.assertEqual(report['observed_verify_steps'],2)
        self.assertEqual(report['uncommitted_verify_steps'],1)
        events[-1]['accepted']=7
        with self.assertRaises(ValueError):
            replay_request(events,expected_output=[10,20,30,99])

    def test_defaults_do_not_touch_tensors_or_create_logs(self):
        from harness.stock_step_runtime import observe_verify,observe_commit
        class Untouchable:
            def __getattr__(self,name):
                raise AssertionError('disabled observer touched runtime')
        with patch.dict(os.environ,{},clear=True):
            observe_verify(Untouchable(),None,None,None,None,None,None)
            observe_commit(Untouchable(),'prefill')

    def test_bound_stream_rejects_hash_drift_and_sequences(self):
        from harness.step_replay import read_stream
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            path=root/'events.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in self.fixture()))
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(len(read_stream(dict(path=str(path),sha256=checksum),root)),3)
            path.write_text(path.read_text()+'\n')
            with self.assertRaises(ValueError):
                read_stream(dict(path=str(path),sha256=checksum),root)

    def test_runtime_serialization_and_native_generation_binding(self):
        from harness.stock_step_runtime import observe_verify,observe_commit
        from harness.step_replay import read_stream,replay_bound
        class Tensor:
            def __init__(self,value):
                self.value=value
            def detach(self):
                return self
            def cpu(self):
                return self
            def tolist(self):
                return copy.deepcopy(self.value)
        initial,worker,final=self.fixture()
        parameters=SimpleNamespace(max_new_tokens=2048,temperature=1.0,top_k=1,ignore_eos=False,
            stop_token_ids=set(),stop_strs=[],stop_regex_strs=[])
        request=SimpleNamespace(rid='fixture',origin_input_ids=[1,2],grammar=None,sampling_params=parameters,
            output_ids=[10],finished_len=None,finished_reason=None,spec_verify_ct=0,
            spec_num_correct_drafts=0,spec_correct_drafts_histogram=[],eos_token_ids={99})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch.dict(os.environ,dict(SPECPILOT_STEP_TRACE_DIR=str(root))):
                observe_commit(request,'prefill')
                arrays=[Tensor([worker[key]]) for key in
                        ('candidates','target_pred','accepted','commit_len','bonus','committed_ids')]
                observe_verify(SimpleNamespace(reqs=[request]),*arrays)
                request.output_ids=final['output_ids']
                request.finished_len=4
                request.finished_reason=SimpleNamespace(to_json=lambda:dict(type='stop',matched=99))
                request.spec_verify_ct=1
                request.spec_num_correct_drafts=2
                request.spec_correct_drafts_histogram=[0,0,1]
                observe_commit(request,'decode')
            path=next(root.glob('*.jsonl'))
            events=read_stream(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()),root)
            packet=dict(http_status=200,request=dict(rid='fixture',input_ids=[1,2],
                sampling_params=dict(temperature=0.0,top_k=1,max_new_tokens=2048)),
                response=dict(output_ids=final['output_ids'],meta_info=dict(completion_tokens=4,spec_verify_ct=1,
                    spec_num_correct_drafts=2,finish_reason=dict(type='stop',matched=99),spec_correct_drafts_histogram=[0,0,1])))
            raw=root/'generation.json'
            raw.write_text(json.dumps(packet))
            reference=dict(path=str(raw),sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
            self.assertTrue(replay_bound(events,reference,root=root)['replay_passed'])
            events[0]['rid']='unrelated'
            with self.assertRaises(ValueError):
                replay_bound(events,reference,root=root)

    def test_missing_finish_counter_drift_and_non_greedy_are_rejected(self):
        from harness.step_replay import replay_request
        mutations=[lambda rows:rows.pop(),lambda rows:rows[2].update(correct_drafts=3),
            lambda rows:rows[2].update(histogram=[0,1,0]),lambda rows:rows[2].update(sequence=1),
            lambda rows:rows[2].update(pid=99),lambda rows:rows[0].update(top_k=2),
            lambda rows:rows[1].update(candidates=[True]*8)]
        for mutate in mutations:
            events=self.fixture()
            mutate(events)
            with self.assertRaises(ValueError):
                replay_request(events,expected_output=[10,20,30,99])


if __name__=='__main__':
    unittest.main()
