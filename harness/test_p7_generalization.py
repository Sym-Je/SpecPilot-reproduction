import tempfile
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch


class GeneralizationTests(unittest.TestCase):
    def test_deferred_quality_is_explicitly_pending_not_scientific_acceptance(self):
        from exp.generalization_run import finish
        with tempfile.TemporaryDirectory() as temporary:
            public=Path(temporary)
            with patch('exp.generalization_run.quality') as quality,patch('exp.generalization_run.analyze') as analyze:
                finish(public,{},[],public,defer_quality=True)
            quality.assert_not_called();analyze.assert_not_called()
            pending=json.loads((public/'gpu-complete.json').read_text())
            self.assertFalse(pending['scientific_acceptance_complete'])
            self.assertEqual(pending['quality_location'],'local-cpu-sandbox')
            self.assertFalse((public/'result.json').exists())

    def test_official_cmrc_schema_and_squad_schema(self):
        from exp.generalization_data import source_rows
        chinese=[dict(context_id='a',context_text='文章',qas=[dict(query_text='问题',query_id='b',answers=['答案'])])]
        item=source_rows('chinese-qa',chinese)[0]
        self.assertEqual(item['answers'],['答案'])
        self.assertIn('文章',item['prompt'])
        squad=dict(data=[dict(paragraphs=[dict(context='passage',qas=[dict(id='b',question='question',answers=[dict(text='answer')])])])])
        self.assertEqual(source_rows('json-extraction',squad)[0]['answers'],['answer'])

    def test_normalization_and_near_duplicate_exclude_old_questions(self):
        from exp.generalization_data import duplicate, normalize
        self.assertEqual(normalize('Ａ B\nC!'), 'abc')
        self.assertTrue(duplicate('What is the capital of France?', ['What is the capital of France?']))
        self.assertTrue(duplicate('a long question about ten consecutive numbered objects!',
                                  ['A long question about ten consecutive numbered objects.']))
        self.assertFalse(duplicate('Solve the new quadratic equation', ['Translate this Chinese paragraph']))

    def test_selection_is_deterministic_excludes_all_and_balances_input_lengths(self):
        from exp.generalization_data import select
        pool = [dict(source_id=str(index), prompt=f'Unique question number {index} '+chr(0x4000+index)*40,
                     input_ids=list(range(index + 1)), suite='sample') for index in range(80)]
        excluded = [pool[index]['prompt'] for index in range(30)]
        first, panel = select(pool, excluded, set(str(index) for index in range(30)), 20)
        second, other = select(list(reversed(pool)), excluded, set(str(index) for index in range(30)), 20)
        self.assertEqual(first, second)
        self.assertEqual(panel, other)
        self.assertEqual(len(first), 20)
        self.assertEqual(len(panel), 4)
        self.assertEqual(sum(row['input_band'] == 'short' for row in first), 10)
        self.assertFalse({row['source_id'] for row in first} & set(str(index) for index in range(30)))
        self.assertTrue(set(panel).issubset({row['source_id'] for row in first}))

    def test_answer_extraction_does_not_reward_unfinished_thinking(self):
        from exp.generalization_quality import final_text, grade
        self.assertEqual(final_text('<think>The answer is 42'), '')
        self.assertEqual(final_text('<think>wrong</think>42'), '42')
        self.assertEqual(grade(dict(metric='numeric', answer='42'), '<think>42')['score'], 0)
        self.assertEqual(grade(dict(metric='numeric', answer='42'), '<think>x</think>\\boxed{42}')['score'], 1)
        self.assertEqual(grade(dict(metric='numeric', answer='42'), '<think>x</think>\\boxed{42}<|im_end|>')['score'], 1)
        self.assertEqual(grade(dict(metric='numeric', answer='42', thinking_required=True), '42')['score'], 0)
        self.assertEqual(grade(dict(metric='json', answers=['Paris']), '{"answer":"Paris"}')['score'], 1)
        self.assertEqual(grade(dict(metric='json', answers=['Paris']), 'Paris')['score'], 0)
        self.assertIsNone(grade(dict(metric='ungraded'), 'hello')['score'])

    def test_quality_sandbox_allows_correct_and_rejects_wrong_code(self):
        from exp.generalization_quality import run_code
        self.assertEqual(run_code('def add(left, right): return left + right', 'assert add(2,3)==5')['status'], 'pass')
        self.assertEqual(run_code('def add(left, right): return 0', 'assert add(2,3)==5')['status'], 'fail')

    def test_quality_sandbox_denies_secret_network_and_subprocess_and_timeout(self):
        from exp.generalization_quality import run_code
        with tempfile.TemporaryDirectory() as temporary:
            secret = Path(temporary) / 'secret'
            secret.write_text('private')
            attacks = [f'open({str(secret)!r}).read()',
                       'import socket; socket.socket()',
                       'import subprocess; subprocess.run(["/bin/true"])',
                       'import os; os.fork()', 'import os; os._exit(0)']
            for attack in attacks:
                self.assertNotEqual(run_code(attack, '')['status'], 'pass')
        self.assertEqual(run_code('while True: pass', '', timeout=1)['status'], 'timeout')

    def test_round_cluster_requires_two_complete_assignments(self):
        from exp.generalization_audit import cluster_groups
        requests = [dict(id='one', suite='x'), dict(id='two', suite='y')]
        pairs = [dict(round=number, id=request['id'], suite=request['suite'],
                      a=dict(tokens_per_s=10, latency_s=2), b=dict(tokens_per_s=20, latency_s=1))
                 for number in (1, 2) for request in requests]
        groups = cluster_groups(pairs, requests)
        self.assertEqual(set(groups), {'x', 'y'})
        self.assertEqual(len(groups['x']), 1)
        with self.assertRaises(ValueError): cluster_groups(pairs[:-1], requests)
        with self.assertRaises(ValueError): cluster_groups(pairs + pairs[:1], requests)

    def test_real_http_evidence_validator_rejects_missing_warmup_swap_and_packets(self):
        from controller.http_transport import sha_ids
        from controller.paper_policy import measurement_protocol_id
        from exp import generalization_audit, generalization_run, p3_pair_run
        from exp.generalization_audit import validate_session
        from exp.dev_campaign import CapturedArm
        serial = []
        class Server:
            def __init__(self,arm,gpu,port,output_dir,environment):
                self.arm,self.gpu,self.port=arm,gpu,port
                self.number=len(serial)+1
                serial.append(self.number)
            def start(self):
                arm=self.arm
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args): pass
                    def send(self,value):
                        payload=json.dumps(value).encode()
                        self.send_response(200)
                        self.send_header('Content-Length',str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    def do_GET(self):
                        self.send(dict(model_path='/model',dtype='bfloat16',enable_fp32_lm_head=False,
                            speculative_algorithm='DFLASH',speculative_num_draft_tokens=arm['block']))
                    def do_POST(self):
                        json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        time.sleep(.015)
                        self.send(dict(output_ids=[9,10],meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1,finish_reason=dict(type='stop'))))
                self.http=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
                self.thread=threading.Thread(target=self.http.serve_forever)
                self.thread.start()
            def wait_ready(self,timeout): pass
            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
        class Telemetry:
            def __init__(self,servers,gpus,path,**options):
                self.servers,self.gpus,self.path=servers,gpus,path
                self.stop=threading.Event()
            def __enter__(self):
                def monitor():
                    with self.path.open('x') as output:
                        while not self.stop.is_set():
                            output.write(json.dumps(dict(time_unix=time.time(),
                                gpus=[dict(gpu,clocks_sm_mhz=1000,clocks_mem_mhz=1000,temperature_c=40,power_w=100) for gpu in self.gpus],
                                arms={server.arm['name']:[dict(pid=server.number,start_ticks=server.number,allowed_cpus='0-1')] for server in self.servers}))+'\n')
                            output.flush()
                            self.stop.wait(.005)
                self.thread=threading.Thread(target=monitor)
                self.thread.start()
                return self
            def __exit__(self,*args):
                self.stop.set()
                self.thread.join()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            ports=[]
            for port in range(35100,36000,10):
                try:
                    p3_pair_run.check_ports([port,port+4]); ports=[port,port+4]; break
                except OSError: continue
            self.assertTrue(ports)
            gpus=[dict(index=index,uuid=f'gpu-{index}',name='H100') for index in (0,1)]
            requests=[dict(id=f'{suite}-{index}',suite=suite,input_ids=[2,index],input_sha256=sha_ids([2,index]),input_band='short' if index==0 else 'long')
                      for suite in ('alpha','beta') for index in (0,1)]
            arms=[dict(name=name,block=block,tree_sha='a'*64,env={}) for name,block in (('stock',8),('final',32))]
            campaign=dict(directory=str(root),source_pin='b'*40,campaign_id='synthetic',source_sha256={},
                campaign_protocol_version=generalization_audit.PROTOCOL,requests=requests,suites=['alpha','beta'],
                max_new_tokens=32,per_suite=2,rounds=2,warmup=2,gpus=gpus,ports=ports,candidate_arms=arms,null_arms=arms,
                full_scale_warmup=True,synchronized_start=True,raw_capture=True,model_path='/model',declared_models={},
                sampling=dict(temperature=0.,top_k=1,enable_thinking=True),launch_protocol=dict(model_path='/model',dtype='bfloat16',enable_fp32_lm_head=False))
            campaign['protocol_id']=measurement_protocol_id(campaign)
            original=p3_pair_run.run_round
            def run_round(*args,**options):
                return original(*args,**options,server_factory=Server)
            with patch('exp.generalization_run.run_round',run_round),patch('exp.p3_pair_run.Telemetry',Telemetry),patch('exp.generalization_run.wait_for_idle',return_value=gpus):
                generalization_run.timing(root/'cap-32',campaign,{},root)
            session=root/'cap-32'/'candidate'
            checked,pairs=validate_session(session,campaign)
            self.assertEqual(len(pairs),8)
            self.assertTrue(checked['physical_gpu_swap'])
            warm=session/'round-01/warmup.jsonl'
            content=warm.read_text()
            warm.write_text('\n'.join(content.splitlines()[:-1])+'\n')
            with self.assertRaises(ValueError):validate_session(session,campaign)
            warm.write_text(content)
            path=session/'round-02/deployment.json'
            content=path.read_text();value=json.loads(content)
            value['assignments'][0]['gpu']=gpus[0]
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):validate_session(session,campaign)
            path.write_text(content)
            packet=Path(pairs[0]['a']['raw_evidence']['path'])
            packet.write_text('{}')
            with self.assertRaises(ValueError):validate_session(session,campaign)


if __name__ == '__main__':
    unittest.main()
