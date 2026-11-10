"""Native DSH pi-ai Responses route for the authorized fallback phase."""
import json
import os
import re
import signal
import time

from dsh_call import plain
from gpt_budget import HERE, MODEL, GATEWAY, activated, credential
from prepare_baseline import ROOT


def patch_for(role, mode, destination, *, endpoint=GATEWAY + '/v1', hook=None):
    assert re.fullmatch(r'[a-z0-9-]{1,80}', role)
    assert mode in ('master', 'direction', 'probe')
    text = (HERE / 'research.patch.yml').read_text().split('- insert:')[0]
    # Sole callable route is explicitly enumerated, not a catalog alias.
    profile = {'apiKeyEnv': 'SP_DREAMWALK_API_KEY', 'api': 'openai-responses',
               'baseURL': endpoint, 'models': [{'id': MODEL, 'contextWindow': 131072,
                    'maxTokens': 8192, 'input': ['text'], 'reasoningEfforts': {'xhigh': 'xhigh'}}],
               'reasoning': 'xhigh', 'transport': 'sse', 'cacheRetention': 'none',
               'timeoutMs': 600000, 'streamIdleTimeoutMs': 300000,
               'retryPolicy': {'mode': 'normal', 'maxRetries': 0}}
    entries = [
        {'id': 'specpilot-gpt-pi-ai', 'name': '@deepseek-ai/dsh-llm-pi-ai',
         'config': {'providers': {'dreamwalk': profile}}},
        {'id': 'specpilot-gpt-budget', 'name': str(hook or HERE / 'gpt-budget-hook.mjs')},
        {'id': 'specpilot-broker', 'name': '@deepseek-ai/dsh-mcp-client', 'config': {
            'serverName': 'specpilot', 'transport': 'stdio', 'command': str(ROOT / '.venv/bin/python'),
            'args': [str(HERE / 'research_broker.py'), '--role', role, '--mode', mode],
            'toolCallTimeoutMs': 1250000, 'startupTimeoutMs': 30000, 'failOnStartupError': True,
            'reconnect': {'enabled': False}}}]
    for entry in entries:
        text += '\n- insert:\n    - ' + json.dumps(entry) + '\n'
    destination.write_text(text)
    return destination


def call(role, mode, prompt, system, max_tokens=8192, deadline_seconds=10800):
    from gpt_context import input_limit_failure, rotate_session, bounded_prompt
    from prepare_baseline import sha
    original_prompt = prompt
    directory = HERE / 'research-gpt'
    route_path = directory / 'session-routing' / (role + '.json')
    routing = json.loads(route_path.read_text()) if route_path.exists() else None
    session_id = routing['session_id'] if routing else role + '-gpt'
    prior = sorted((directory/'calls').glob(session_id+'-*.json'))
    if prior:
        record = json.loads(prior[-1].read_text())
        if record.get('session_id') == session_id and input_limit_failure(record['result']):
            routing = rotate_session(HERE, role, session_id, original_prompt, sha(prior[-1]))
            session_id = routing['session_id']
    started = time.monotonic()
    for attempt in range(3):
        if routing:
            prompt = ('Resume the same role from this attributed checkpoint; preserve the original task and experiment/budget state:\n'
                      + (HERE/routing['checkpoint_path']).read_text()
                      + '\nCurrent role and output contract take precedence over a stale checkpoint prompt:\n'
                      + bounded_prompt(original_prompt))
        remaining = max(1, int(deadline_seconds - (time.monotonic()-started)))
        answer, receipt = _native_call(role, mode, prompt, system, max_tokens, remaining, session_id)
        if receipt['result']['finish_reason'] == 'completed':
            return answer, receipt
        if not input_limit_failure(receipt['result']) or attempt == 2:
            raise RuntimeError('DSH GPT turn did not complete; preserved receipt: '+receipt['call_id'])
        path = directory/'calls'/(receipt['call_id']+'.json')
        routing = rotate_session(HERE, role, session_id, original_prompt, sha(path))
        session_id = routing['session_id']


def _native_call(role, mode, prompt, system, max_tokens, deadline_seconds, session_id):
    from deepseek_harness import DeepSeekHarness
    activated()
    assert re.fullmatch(r'[a-z0-9-]{1,80}', role)
    directory = HERE / 'research-gpt'
    home, work, results = directory / 'dsh-home', directory / 'workspace', directory / 'calls'
    for p in (home, work, results): p.mkdir(mode=0o700, parents=True, exist_ok=True)
    for key in list(os.environ):
        if key.lower().endswith('_proxy') or any(s in key.lower() for s in ('api_key', 'claude_key', 'northgate_key', 'deepseek_key')):
            del os.environ[key]
    os.environ['NO_PROXY'] = '*'; os.environ['no_proxy'] = '*'
    secret = credential()
    exists = any(p.parent.name == session_id for p in home.rglob('session.v4.jsonl'))
    patch = patch_for(role, mode, directory / (role + '.patch.yml'))
    call_id = f'{session_id}-{time.time_ns()}'
    started = time.time()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('DSH GPT activity deadline')))
    signal.alarm(deadline_seconds)
    try:
        with DeepSeekHarness(
            dsh_home=str(home), cwd=str(work), profile='sdk-minimal',
            provider='dreamwalk', model=MODEL, reasoning_effort='xhigh', max_tokens=max_tokens,
            env={'SP_DREAMWALK_API_KEY': secret, 'DSH_SYSTEM_PROMPT': system,
                 'DSH_CONTEXT_WINDOW': '131072', 'SP_ROLE_ID': role, 'SP_BUDGET_PHASE': 'gpt'},
            patches=(str(patch),), initialize_timeout_seconds=120,
        ) as harness:
            session = harness.resume_session(session_id) if exists else harness.start_session(session_id)
            result = session.run(prompt)
        record = {'call_id': call_id, 'session_id': session_id, 'broker_role': role, 'model': MODEL,
                  'started_epoch': started, 'completed_epoch': time.time(), 'resumed': exists,
                  'result': plain(result), 'sdk': '0.2.1rc2', 'api_route': 'direct Dreamwalk HTTPS Responses'}
        encoded = json.dumps(record, ensure_ascii=False, indent=2, default=plain)
        assert secret not in encoded
        (results / (call_id + '.json')).write_text(encoded + '\n')
        return result.final_response, record
    finally:
        signal.alarm(0)
