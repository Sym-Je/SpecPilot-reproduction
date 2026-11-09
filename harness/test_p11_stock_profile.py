import unittest
import base64
import hashlib


class StockProfileTests(unittest.TestCase):
    def test_500_requires_fresh_bound_native_inactive_log_not_status_relabel(self):
        from pathlib import Path
        import tempfile
        from exp.stock_profile import control_status,profile_state
        payload=b'Internal Server Error'
        packet=dict(http_status=500,response_bytes_base64=base64.b64encode(payload).decode(),
                    response_bytes_sha256=hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            log=root/'stock.server.log'
            native=b'RuntimeError: Profiling is not in progress. Call /start_profile first.\n'
            log.write_bytes(native+b'new call\n'+native)
            offset=len(native)+len(b'new call\n')
            proof=dict(path=str(log),offset=offset,length=len(native),sha256=hashlib.sha256(native).hexdigest())
            state=profile_state(packet,proof,root)
            self.assertFalse(state['http_success'])
            self.assertFalse(control_status(packet)['explicitly_not_running'])
            self.assertTrue(state['native_inactive_log_verified'])
            self.assertFalse(profile_state(packet,None,root)['native_inactive_log_verified'])
            other=b'RuntimeError: out of memory\n'
            log.write_bytes(other)
            unrelated=dict(path=str(log),offset=0,length=len(other),sha256=hashlib.sha256(other).hexdigest())
            self.assertFalse(profile_state(packet,unrelated,root)['native_inactive_log_verified'])
            log.write_bytes(b'x'*log.stat().st_size)
            with self.assertRaises(ValueError):
                profile_state(packet,proof,root)

    def test_profile_only_repair_binds_original_and_never_retimes(self):
        from contextlib import nullcontext
        import json
        import os
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from exp.stock_profile import repair_profiles,digest
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            original=root/'original'
            original.mkdir()
            manifest=dict(source_pin='original-pin',arms=[dict(engine='/stock')],ports=[1,2],profile_port=3)
            (original/'manifest.json').write_text(json.dumps(manifest))
            (original/'result.json').write_text('{}')
            before=digest(original/'manifest.json')
            archive=root/'source.tar'
            archive.write_bytes(b'fixture')
            public=root/'public'
            public.mkdir()
            output=root/'repair'
            with patch.dict(os.environ,dict(BOTTLENECK_SOURCE_TAR=str(archive),BOTTLENECK_SOURCE_SHA256=digest(archive))), \
                    patch('exp.stock_profile.clean_environment',return_value={}), \
                    patch('exp.stock_profile.signal.signal'),patch('exp.stock_profile.sources',return_value={}), \
                    patch('exp.stock_profile.check_tree'),patch('exp.stock_profile.check_ports'), \
                    patch('exp.stock_profile.wait_for_idle',return_value=[dict(uuid='gpu')]), \
                    patch('exp.stock_profile.gpu_lock',return_value=nullcontext()), \
                    patch('exp.stock_profile.run_timings',side_effect=AssertionError('must not retime')), \
                    patch('exp.stock_profile.run_profiles') as profiles, \
                    patch('exp.stock_profile.audit',return_value=dict(profile_requests_usable=20)):
                repair_profiles(output,public,original,'repair-pin')
            self.assertEqual(profiles.call_count,1)
            repaired=json.loads((output/'manifest.json').read_text())
            self.assertEqual(repaired['source_pin'],'repair-pin')
            self.assertEqual(repaired['timing_origin']['source_pin'],'original-pin')
            self.assertEqual(repaired['timing_origin']['manifest_sha256'],before)
            self.assertEqual(digest(original/'manifest.json'),before)
            self.assertFalse((output/'timing').exists())

    def test_profile_window_is_not_a_shorter_generation_budget(self):
        from exp.stock_profile import profile_request,sampling
        schema=dict(components=dict(schemas=dict(ProfileReq=dict(properties={
            key:{} for key in ('output_dir','num_steps','record_shapes','with_stack','detailed_annotations')}))))
        body=profile_request(schema,'/traces')
        self.assertEqual(body['num_steps'],128)
        self.assertNotIn('start_step',body)
        self.assertEqual(sampling(),dict(temperature=0.0,top_k=1,max_new_tokens=2048))
        self.assertNotIn('ignore_eos',sampling())

    def test_missing_bounded_profile_api_is_explicitly_unavailable(self):
        from exp.stock_profile import profile_request
        with self.assertRaises(ValueError):
            profile_request({},'/traces')

    def test_profiled_time_cannot_be_inserted_into_timing_coverage(self):
        from exp.stock_profile import validate_order
        validate_order([dict(start=1,end=2),dict(start=3,end=4)],profile_start=5)
        with self.assertRaises(ValueError):
            validate_order([dict(start=1,end=3),dict(start=2,end=4)],profile_start=5)
        with self.assertRaises(ValueError):
            validate_order([dict(start=1,end=2),dict(start=3,end=4)],profile_start=3.5)

    def test_pure_text_control_and_automatic_stop_remain_distinct(self):
        from exp.stock_profile import control_status
        payload=b'Profiler is not running.'
        packet=dict(http_status=400,response_bytes_base64=base64.b64encode(payload).decode(),
                    response_bytes_sha256=hashlib.sha256(payload).hexdigest())
        result=control_status(packet)
        self.assertFalse(result['http_success'])
        self.assertTrue(result['explicitly_not_running'])
        packet['http_status']=500
        self.assertFalse(control_status(packet)['explicitly_not_running'])
        packet['response_bytes_sha256']='0'*64
        with self.assertRaises(ValueError):
            control_status(packet)

    def test_in_progress_trace_export_is_waited_but_invalid_time_is_not_hidden(self):
        import json
        from pathlib import Path
        import tempfile
        import threading
        import time
        from exp.stock_profile import ready_traces
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            path=root/'trace.json'
            path.write_text('{')
            def finish():
                time.sleep(.1)
                path.write_text(json.dumps(dict(traceEvents=[dict(ph='X',cat='kernel',name='any',ts=0,dur=10,args=dict(device=0))])))
            writer=threading.Thread(target=finish)
            writer.start()
            result=ready_traces(root,timeout=2)
            writer.join()
            self.assertEqual(result[0]['observation']['kernel_sum_us'],10)
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(result[0]['sha256'],checksum)
            from unittest.mock import patch
            calls=[]
            def changing_digest(path):
                calls.append(1)
                return '0'*64 if len(calls)==1 else checksum
            with patch('exp.stock_profile.digest',side_effect=changing_digest):
                stable=ready_traces(root,timeout=2)
            self.assertEqual(stable[0]['sha256'],checksum)
            path.write_text(json.dumps(dict(traceEvents=[dict(ph='X',cat='kernel',name='any',ts=0,dur=-1,args=dict(device=0))])))
            with self.assertRaises(ValueError):
                ready_traces(root,timeout=2)

    def test_real_http_stock_rounds_have_full_warmup_and_physical_swaps(self):
        import json
        from pathlib import Path
        import tempfile
        import threading
        from contextlib import nullcontext
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from unittest.mock import patch
        from controller.http_transport import sha_ids
        from exp.stock_profile import run_timings,validate_timing_round
        from exp.p3_pair_run import check_ports,write_json
        from harness.candidate import expected_arguments
        spec=dict(target='/model',draft='/draft',stock_tree_sha='a'*64)
        serial=[]
        class FakeServer:
            def __init__(self,arm,gpu,port,output_dir,environment):
                self.arm,self.port,self.root=arm,port,output_dir
                self.number=len(serial)+1
                serial.append(self.number)
            def start(self):
                arguments=expected_arguments(spec,8)
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):
                        pass
                    def send(self,value):
                        payload=json.dumps(value).encode()
                        self.send_response(200)
                        self.send_header('Content-Length',str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    def do_GET(self):
                        self.send(arguments)
                    def do_POST(self):
                        json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        self.send(dict(output_ids=[9,10],meta_info=dict(completion_tokens=2,
                            spec_verify_ct=1,finish_reason=dict(type='stop'))))
                self.http=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
                self.thread=threading.Thread(target=self.http.serve_forever)
                self.thread.start()
                write_json(self.root/f'{self.arm["name"]}.process.json',dict(pid=self.number,start_ticks=self.number))
            def wait_ready(self,timeout):
                pass
            def stop(self):
                self.http.shutdown()
                self.thread.join()
                self.http.server_close()
                write_json(self.root/f'{self.arm["name"]}.stopped.json',dict(stopped=True))
        for port in range(37000,38000,10):
            try:
                check_ports([port,port+4])
                break
            except OSError:
                continue
        suites=('gsm8k','math500','humaneval','mbpp','mt-bench')
        requests=[dict(id=f'{suite}-{index}',suite=suite,input_ids=[index+2],input_sha256=sha_ids([index+2]))
                  for index in (0,1) for suite in suites]
        manifest=dict(requests=requests,gpus=[dict(index=index,uuid=f'gpu-{index}') for index in (0,1)],
            arms=[dict(name=name,launch_arm='stock',engine='/engine',tree_sha='a'*64,block=8,env={})
                  for name in ('stock-a','stock-b')],ports=[port,port+4],stock_spec=spec,
            launch_protocol=expected_arguments(spec,8))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch('exp.p3_pair_run.Telemetry',return_value=nullcontext()):
                run_timings(root,manifest,{},server_factory=FakeServer)
            for number in (0,1):
                pairs,processes=validate_timing_round(root,manifest,number)
                self.assertEqual(len(pairs),10)
                self.assertEqual(len(processes),2)
            warm=root/'timing/round-01/warmup.jsonl'
            content=warm.read_bytes()
            warm.write_text('\n'.join(warm.read_text().splitlines()[:-1])+'\n')
            with self.assertRaises(ValueError):
                validate_timing_round(root,manifest,0)
            warm.write_bytes(content)
            deployment=root/'timing/round-02/deployment.json'
            value=json.loads(deployment.read_text())
            value['assignments'][0]['gpu']['uuid']='wrong'
            deployment.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                validate_timing_round(root,manifest,1)

    def test_profile_http_preserves_plain_text_and_automatic_stop_errors(self):
        import json
        from pathlib import Path
        import tempfile
        import threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from unittest.mock import patch
        from controller.http_transport import sha_ids
        from exp.stock_profile import run_profiles
        from exp.p3_pair_run import check_ports,write_json
        from harness.candidate import expected_arguments
        for port in range(38000,39000,10):
            try:
                check_ports([port])
                break
            except OSError:
                continue
        schema=dict(components=dict(schemas=dict(ProfileReq=dict(properties={key:{} for key in
            ('output_dir','num_steps','record_shapes','with_stack','detailed_annotations')}))))
        spec=dict(target='/model',draft='/draft',stock_tree_sha='a'*64)
        stops=[]
        class FakeServer:
            def __init__(self,arm,gpu,actual_port,output_dir,environment):
                self.arm,self.root,self.port=arm,output_dir,actual_port
            def start(self):
                if self.port!=port:
                    raise ValueError('profile did not use the explicitly bound endpoint')
                server_log=self.root/'stock.server.log'
                server_log.write_bytes(b'')
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):
                        pass
                    def send(self,value,status=200):
                        payload=value if isinstance(value,bytes) else json.dumps(value).encode()
                        self.send_response(status)
                        self.send_header('Content-Length',str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    def do_GET(self):
                        self.send(schema if self.path=='/openapi.json' else expected_arguments(spec,8))
                    def do_POST(self):
                        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        if self.path=='/start_profile':
                            self.server.profile_directory=Path(body['output_dir'])
                            self.send(b'Start profiling.\n')
                        elif self.path=='/stop_profile':
                            events=[dict(ph='X',cat='user_annotation',name='step[VERIFY bs=1]',ts=0,dur=30,pid=1,tid=2),
                                dict(ph='X',cat='cuda_runtime',name='launch',ts=2,dur=1,pid=1,tid=2,args=dict(correlation=7)),
                                dict(ph='X',cat='kernel',name='arbitrary',ts=4,dur=10,args=dict(correlation=7,device=0))]
                            write_json(self.server.profile_directory/'trace.json',dict(traceEvents=events))
                            stops.append(len(stops)+1)
                            if len(stops)%2:
                                with server_log.open('ab') as output:
                                    output.write(b'RuntimeError: Profiling is not in progress. Call /start_profile first.\n')
                            self.send(b'Internal Server Error' if len(stops)%2 else b'Stop profiling.\n',500 if len(stops)%2 else 200)
                        else:
                            self.send(dict(output_ids=[9,10],meta_info=dict(completion_tokens=2,spec_verify_ct=1,finish_reason=dict(type='stop'))))
                self.http=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
                self.thread=threading.Thread(target=self.http.serve_forever)
                self.thread.start()
            def wait_ready(self,timeout):
                pass
            def stop(self):
                if hasattr(self,'http'):
                    self.http.shutdown()
                    self.thread.join()
                    self.http.server_close()
        requests=[dict(id=f'case-{index}',suite='gsm8k',input_ids=[index+2],input_sha256=sha_ids([index+2])) for index in range(10)]
        manifest=dict(arms=[dict(name='stock-a',engine='/engine',tree_sha='a'*64,block=8,env={})],
            gpus=[dict(index=index,uuid=f'gpu-{index}') for index in (0,1)],requests=requests,
            stock_spec=spec,profile_port=port)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            public=root/'public'
            public.mkdir()
            with patch('exp.stock_profile.StockServer',FakeServer),patch('exp.stock_profile.wait_for_idle',return_value=[]):
                run_profiles(root,manifest,{},public)
            records=json.loads((root/'profiles/records.json').read_text())
            self.assertEqual(len(records),20)
            self.assertEqual(sum(row['status']=='captured_with_control_error' for row in records),10)
            self.assertEqual(sum(row['status']=='captured' for row in records),10)
            self.assertEqual(len(stops),20)
            self.assertEqual(sum('stop_state_log' in row for row in records),10)
            self.assertTrue(all(row['traces'][0]['observation']['stages']['kernel_us']['VERIFY']==10 for row in records))


if __name__=='__main__':
    unittest.main()
