"""Offline native DSH/Responses integration test. Dummy credential, loopback only.

Exercises the real adapter, real restricted MCP broker and budget hook source
against deterministic SSE replies. No inference request reaches a paid gateway.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import threading
import time

from dsh_call import plain
from gpt_call import patch_for
from gpt_budget import HERE, MODEL


def run():
    from deepseek_harness import DeepSeekHarness
    os.umask(0o077)
    for k in list(os.environ):
        if k.lower().endswith('_proxy') or any(s in k.lower() for s in ('api_key', 'claude_key', 'northgate_key', 'deepseek_key')):
            del os.environ[k]
    os.environ['NO_PROXY'] = '*'; os.environ['no_proxy'] = '*'
    directory = HERE / ('gpt-offline-probe-' + str(time.time_ns()))
    directory.mkdir(mode=0o700)
    wire, failures = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                wire.append(body)
                assert self.path == '/v1/responses', self.path
                assert self.headers['Authorization'] == 'Bearer fixture-not-a-real-key'
                assert body['model'] == MODEL and body['store'] is False
                assert body['reasoning']['effort'] == 'xhigh'
                assert 0 < body['max_output_tokens'] <= 4096
                assert body['stream'] is True
                tools = body['tools']; assert tools and all(t['type'] == 'function' for t in tools)
                assert all(t['name'].endswith(('read_evidence', 'list_source', 'read_source', 'search_source')) for t in tools)
                if len(wire) == 1:
                    tool = next(t['name'] for t in tools if t['name'].endswith('read_evidence'))
                    item = {'type': 'function_call', 'id': 'fc_fixture', 'call_id': 'call_fixture',
                            'name': tool, 'arguments': '{"name":"budget"}', 'status': 'completed'}
                    events = [
                        ('response.output_item.added', {'output_index': 0, 'item': dict(item, arguments='', status='in_progress')}),
                        ('response.function_call_arguments.delta', {'output_index': 0, 'item_id': item['id'], 'delta': item['arguments']}),
                        ('response.function_call_arguments.done', {'output_index': 0, 'item_id': item['id'], 'arguments': item['arguments']}),
                        ('response.output_item.done', {'output_index': 0, 'item': item})]
                else:
                    assert any(x.get('type') == 'function_call_output' and x['call_id'] == 'call_fixture' for x in body['input'])
                    assert any(x.get('type') == 'reasoning' and x.get('encrypted_content') == 'fixture-encrypted-reasoning' for x in body['input'])
                    content = {'type': 'output_text', 'text': '{"passed":true}', 'annotations': []}
                    item = {'type': 'message', 'id': 'msg_fixture_' + str(len(wire)),
                            'role': 'assistant', 'status': 'completed', 'content': [content]}
                    events = [
                        ('response.output_item.added', {'output_index': 0, 'item': dict(item, content=[], status='in_progress')}),
                        ('response.content_part.added', {'output_index': 0, 'content_index': 0, 'part': dict(content, text='')}),
                        ('response.output_text.delta', {'output_index': 0, 'content_index': 0, 'item_id': item['id'], 'delta': content['text']}),
                        ('response.output_text.done', {'output_index': 0, 'content_index': 0, 'item_id': item['id'], 'text': content['text']}),
                        ('response.output_item.done', {'output_index': 0, 'item': item})]
                output = [item]
                if len(wire) == 1:
                    reason = {'type': 'reasoning', 'id': 'rs_fixture', 'summary': [],
                              'encrypted_content': 'fixture-encrypted-reasoning'}
                    for _, value in events:
                        if 'output_index' in value: value['output_index'] = 1
                    events = [('response.output_item.added', {'output_index': 0, 'item': reason}),
                              ('response.output_item.done', {'output_index': 0, 'item': reason})] + events
                    output.insert(0, reason)
                response = {'id': 'resp_fixture_' + str(len(wire)), 'object': 'response',
                            'created_at': int(time.time()), 'model': MODEL, 'status': 'completed',
                            'output': output, 'usage': {'input_tokens': 100, 'output_tokens': 10,
                                'total_tokens': 110, 'input_tokens_details': {'cached_tokens': 0},
                                'output_tokens_details': {'reasoning_tokens': 2}}}
                events = [('response.created', {'response': dict(response, output=[], status='in_progress')})] + events
                events.append(('response.completed', {'response': response}))
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                for seq, (kind, payload) in enumerate(events):
                    payload = {'type': kind, 'sequence_number': seq, **payload}
                    self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps(payload) + '\n\n').encode()); self.wfile.flush()
            except BaseException as exc:
                failures.append(f'{type(exc).__name__}: {exc}')
                self.send_error(500, 'fixture assertion failed')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Use the actual hook code with only the budget command replaced by a local
    # fixture ledger. This cannot authorize the production GPT phase.
    fake_budget = directory / 'fixture_budget.py'
    fake_budget.write_text('import sys,json\nfrom pathlib import Path\n'
        + 'sys.path.insert(0, ' + repr(str(HERE)) + ')\nfrom gpt_budget import Budget\n'
        + 'print(json.dumps(Budget(Path(__file__).parent / "billing").transact(sys.argv[1], json.load(sys.stdin), '
        + '{"total_used_quota":0,"epoch":0,"rates":{}})))\n')
    hook = directory / 'hook.mjs'
    hook.write_text((HERE / 'gpt-budget-hook.mjs').read_text().replace("join(here, 'gpt_budget.py')", json.dumps(str(fake_budget))))
    role = 'gpt-offline-wire-' + str(time.time_ns())
    patch = patch_for(role, 'master', directory / 'patch.yml', endpoint=f'http://127.0.0.1:{server.server_port}/v1', hook=hook)
    home = directory / 'home'; work = directory / 'workspace'; work.mkdir()
    kwargs = dict(dsh_home=str(home), cwd=str(work), profile='sdk-minimal', provider='dreamwalk',
                  model=MODEL, reasoning_effort='xhigh', max_tokens=4096, patches=(str(patch),),
                  env={'SP_DREAMWALK_API_KEY': 'fixture-not-a-real-key', 'SP_ROLE_ID': role,
                       'DSH_SYSTEM_PROMPT': 'Offline transport fixture. Use the provided tools.'},
                  initialize_timeout_seconds=120)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Offline fixture deadline')))
    signal.alarm(180)
    try:
        with DeepSeekHarness(**kwargs) as harness:
            result = harness.start_session(role).run('Read the budget using the provided tool, then report JSON.')
            (directory / 'first-result.json').write_text(json.dumps(plain(result), default=plain))
            assert result.finish_reason == 'completed' and json.loads(result.final_response) == {'passed': True}, result.finish_reason
        with DeepSeekHarness(**kwargs) as harness:
            result = harness.resume_session(role).run('Confirm the previous fixture result.')
            assert result.finish_reason == 'completed' and json.loads(result.final_response) == {'passed': True}
        assert not failures, failures
        assert len(wire) == 3, len(wire)
        billing = json.loads((directory / 'billing/state.json').read_text())
        assert len(billing['reservations']) == len(wire)
        assert all(x['status'] == 'settled_without_refund' for x in billing['reservations'].values())
        logs = list(home.rglob('session.v4.jsonl')); assert len(logs) == 1
        records = [json.loads(l) for l in logs[0].read_text().splitlines()]
        # Headers are per user turn; each LLM step is separately budgeted.
        assert sum(x['type'] == 'request/header' for x in records) == 2
        assert sum(x['type'] == 'step/start' for x in records) == 3
        assert sum(x['type'] == 'tool/result' for x in records) == 1
        (directory / 'wire.json').write_text(json.dumps(wire, indent=2))
        report = {'passed': True, 'model': MODEL, 'wire_api': 'responses', 'reasoning_effort': 'xhigh',
                  'store': False, 'paid_inference_requests': 0, 'offline_requests': len(wire),
                  'budget_admissions': len(billing['reservations']), 'native_mcp_tool_loop': True,
                  'fresh_process_resume': True, 'encrypted_reasoning_replay': True,
                  'native_trajectory_sha256': hashlib.sha256(logs[0].read_bytes()).hexdigest(),
                  'directory': str(directory), 'epoch': time.time()}
        (HERE / 'gpt-offline-preflight.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    finally:
        signal.alarm(0); server.shutdown()
        (directory / 'failures.json').write_text(json.dumps(failures))


if __name__ == '__main__': run()
