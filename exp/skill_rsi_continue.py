"""Explicit native Master coverage review, not a pipeline restart or GPU broker.

Engineering acceptance: python -B -m unittest harness.test_skill_rsi_continue -v.
Old evidence remains immutable. A new ephemeral thread replays only its logical
Master's own decisions, own skill feedback and already-shared measurements.
"""

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from controller.phase4_final import close_registry, record_birth, record_exit, trusted_metadata, validate_shutdown
from exp import codex_boundary
from exp import gpu_autonomy as roles
from exp.skill_rsi import LIMITS, ModelResponseError
from harness.engine_research import Budget, save
from harness.skill_rsi_audit import audit, audit_role, load, require, safe_path, sha
from harness import research_boundary


COMMON = '''你是SpecPilot受限Master的显式coverage-review续接，不是新一轮direction研究。
只用research工具读取自身inputs/evidence.json及授权stock；可用read_file/read_stock/list_stock/write_file/run_python。
先调用research {"action":{"kind":"help"}}查看精确字段。
然后research {"action":{"kind":"read_file","path":"inputs/evidence.json","offset":0}}；
按返回next_offset继续同一路径，直到next_offset=null，核对total_chars与同一sha256，不把首段当全文。
read_file不支持limit字段。只有run_python {"kind":"run_python","path":"scratch/check.py"}，不接受code/source。
若需CPU摘要，先write_file {"kind":"write_file","path":"scratch/check.py","content":"Python源码"}，再run_python。
list_stock精确格式为{"kind":"list_stock","prefix":"python/sglang/","offset":0}；不要省略字段。
已取得的信息可以自行写CPU摘要，无需重复所有工具。未读全须明确限制，不能冒称完整coverage裁决。
只允许scratch写入和既有隔离CPU工具，不读作者final/sealed/其他角色私人推理，不探测宿主路径，不提交GPU。
输入重放你自己的旧决策、自己的工具反馈和之前共享的诊断。全部标注复用，不算新发现；这是新ephemeral线程，不是假称原生线程恢复。
原stop有效，原轮没有真实整合/kernel优化/controller验收。你自主判断是否值得补正确性覆盖；允许继续stop。
三个direction没有可信收益，不等于已证明不正确，也不等于弱收益机制没有互补性。
可选择把正确性未知的已测单项交独立dev，不仅按单项赢家筛选；没有价值或证据/预算不足则stop。
此入口不执行dev、组合或kernel；只有独立正确性证据出现后才可另行交Integration自主研究，Kernel可请求能力或停止。
最终只输出{"decision":"stop|review","review":["输入中的候选id"],"reason":"证据、取舍及覆盖限制"}。
不输出路径或shell，不放宽科学阈值，不宣称lossless、RSI、sealed、晋升或正结果。
'''


def validate_decision(value, candidates):
    if not isinstance(value, dict) or set(value) != {'decision', 'review', 'reason'}:
        raise ModelResponseError('coverage decision requires decision/review/reason')
    review = value['review']
    if (value['decision'] not in ('stop', 'review') or not isinstance(review, list) or
            any(not isinstance(item, str) for item in review) or len(review) != len(set(review)) or
            any(item not in candidates for item in review) or
            (value['decision'] == 'stop' and review) or (value['decision'] == 'review' and not review) or
            not isinstance(value['reason'], str) or not 1 <= len(value['reason']) <= 4000):
        raise ModelResponseError('coverage decision is outside the measured candidate set')
    return value


@contextmanager
def recorded_processes(directory, result, *, prior_members=()):
    directory.mkdir(mode=0o700)
    processes = []
    originals = [(module, module.subprocess) for module in (codex_boundary, research_boundary)]

    class RecordedModule:
        def __init__(self, original, label):
            self.original, self.label = original, label

        def __getattr__(self, name):
            return getattr(self.original, name)

        def Popen(self, *arguments, **keywords):
            process = self.original.Popen(*arguments, **keywords)
            try:
                birth = record_birth(process, self.label, directory)
            except BaseException:
                process.kill()
                process.wait()
                raise
            processes.append((process, birth, keywords.get('start_new_session', False)))
            return process

    try:
        for module, original in originals:
            module.subprocess = RecordedModule(original, 'coverage-Master-' + module.__name__.split('.')[-1])
        yield
    finally:
        for module, original in originals:
            module.subprocess = original
        members, errors = [], []
        for process, birth, new_session in processes:
            try:
                if process.poll() is None:
                    if process.stdin is not None and not process.stdin.closed:
                        process.stdin.close()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        if new_session:
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                ended = record_exit(process, birth, directory, timeout=8)
                members.append(dict(birth=birth, exit=ended))
            except Exception as error:
                errors.append(type(error).__name__ + ': ' + str(error))
        result['process_members'] = list(prior_members) + members
        result['role_processes_closed'] = bool(processes) and len(members) == len(processes)
        if members and not errors:
            result['shutdown_registry'] = close_registry(directory, members)
        if errors:
            raise RuntimeError('coverage process closure unconfirmed: ' + '; '.join(errors))


def prepare(parent, output):
    parent, output = Path(parent).resolve(), Path(output).resolve()
    if output.exists() or output.parent != parent or not output.name.startswith('coverage-review-'):
        raise ValueError('explicit new coverage-review directory under the parent is required; never replay an existing review')
    verified = audit(parent)
    previous = load(parent / 'pipeline-result.json')
    if previous['status'] != 'research_complete':
        raise ValueError('coverage review requires a closed parent; recovery is a different explicit operation')
    candidates = {}
    for reservation in previous['resource_state']['jobs']:
        directory = parent / reservation['name']
        request, feedback = load(directory / 'request.json'), load(directory / 'feedback.json')
        if request['mode'] == 'source-research' and feedback['status'] == 'completed':
            candidates[directory.name] = dict(id=directory.name, diagnostic_request=str(directory),
                patch_sha256=sha(directory / 'patch.json'), self_check_sha256=sha(directory / 'self-check.py'),
                feedback_sha256=sha(directory / 'feedback.json'), diagnostic=feedback,
                correctness='unknown unless independently gated; diagnostic completion is not correctness',
                provenance='previous independently replayed diagnostic; shared reuse, not a new discovery')
    decisions = [dict(turn=path.name, value=load(path), sha256=sha(path),
        provenance='same logical Master own prior decision; context replay, not native-thread resume')
        for path in sorted((parent / 'master').glob('turn-*-response.json'))]
    own_tools = []
    for path in sorted((parent / 'master').glob('tools-*/action-*/request.json')):
        if load(path)['arguments']['action']['kind'] == 'run_skill':
            response = path.parent / 'response.json'
            own_tools.append(dict(value=load(response), sha256=sha(response), provenance='own prior Master skill feedback'))
    output.mkdir(mode=0o700)
    packet = dict(scope='coverage review only; no repeated direction GPU or automatic scientific stages',
        parent_audit=verified, parent_pipeline_sha256=sha(parent / 'pipeline-result.json'),
        parent_feedback_sha256=sha(parent / 'feedback.json'),
        previous_master_decisions=decisions, own_previous_skill_feedback=own_tools,
        measured_candidates=list(candidates.values()), authorized_resource_limits=LIMITS,
        shared_budget_path=str(parent / 'resource-state.json'),
        provenance='explicit follow-up to a valid no-gain stop; not retroactive completion of missing stages')
    save(output / 'coverage-input.json', packet)
    save(output / 'parent-resource-snapshot.json', previous['resource_state'])
    identity = dict(continuation_source_sha256=sha(Path(__file__)),
        parent_pipeline_sha256=packet['parent_pipeline_sha256'], parent_feedback_sha256=packet['parent_feedback_sha256'],
        parent_host_source_sha256=sha(parent / 'host-start-skill-rsi.py') if (parent / 'host-start-skill-rsi.py').exists() else None,
        current_runner_sha256=sha(Path(__file__).with_name('skill_rsi.py')),
        old_host_hot_reloaded=False, native_context_mode='new thread with own-context provenance replay')
    save(output / 'source-identity.json', identity)
    return packet, candidates, previous['counters']


def native_counters(parent, directory, result):
    role, responses, _ = audit_role(parent, directory / 'master')
    require(role['kind'] == 'Master' and role['thread'] == result['role_thread'], 'prior native Master identity differs')
    response = responses.get((result['role_thread'], result['role_turn']))
    require(response is not None and response['sha256'] == result['native_response_sha256'] and
            response['value'] == result['decision'], 'prior native decision/SHA differs')
    before, after = result['counters_before'], result['counters_after']
    require(set(before) == set(after) and all(type(value) is int and value >= 0 for value in (*before.values(), *after.values())),
            'invalid cumulative coverage counters')
    for key in before:
        delta = role['counts'][key] if key in ('actions', 'cpu_runs', 'model_turns', 'usage_updates') else 0
        require(after[key] == before[key] + delta, 'prior native counter differs: ' + key)
    return role


def repair_context(parent, prior):
    original = Path(prior).absolute()
    prior = safe_path(original, parent)
    require(original == prior and prior.parent == parent and prior.name.startswith('coverage-review-'),
            'repair must name the original direct-child coverage review')
    claim = load(parent / 'coverage-review-claim.json')
    result, identity, packet = [load(prior / name) for name in
                               ('coverage-result.json', 'source-identity.json', 'coverage-input.json')]
    require(claim['output'] == str(prior) and 'repair_context' not in packet and
            result['status'] in ('stopped', 'controller_review_requested'), 'only the original claimed review may be repaired once')
    require(result.get('role_processes_closed') is True and result.get('role_exit_code') == 0,
            'prior native role has not exited cleanly')
    registry_ref = result['shutdown_registry']
    safe_path(registry_ref['path'], prior / 'processes')
    registry = trusted_metadata(registry_ref, os.geteuid())
    require(registry['members'] == result['process_members'], 'prior shutdown inventory differs')
    for member in registry['members']:
        for key in ('birth', 'exit'):
            safe_path(member[key]['path'], prior / 'processes')
        ended = trusted_metadata(member['exit'], os.geteuid())
        require(ended['returncode'] == 0, 'prior native process exit was not successful')
    validate_shutdown(registry, broker_uid=os.geteuid(), opened_unix=time.time())
    pipeline_sha, feedback_sha = sha(parent / 'pipeline-result.json'), sha(parent / 'feedback.json')
    require(claim['parent_pipeline_sha256'] == identity['parent_pipeline_sha256'] == packet['parent_pipeline_sha256'] == pipeline_sha and
            identity['parent_feedback_sha256'] == packet['parent_feedback_sha256'] == feedback_sha,
            'original parent evidence SHA differs')
    previous = load(parent / 'pipeline-result.json')
    require(result['counters_before'] == previous['counters'] and
            load(prior / 'parent-resource-snapshot.json') == previous['resource_state'], 'prior parent snapshot/counters differ')
    require(all(result.get(key) is False for key in ('controller_accepted', 'integration_executed', 'kernel_executed',
            'sealed_used', 'promoted')) and result.get('gpu_jobs_submitted') == 0, 'prior coverage claimed scientific execution')
    native_counters(parent, prior, result)
    state = result['resource_state']
    require(state == previous['resource_state'], 'prior coverage changed the shared GPU budget')
    manifest = load(prior / 'master/manifest.json')
    work = safe_path(manifest['work'])
    evidence = safe_path(work / 'inputs/evidence.json', work)
    prior_input = load(evidence)
    require(all(prior_input.get(key) == value for key, value in packet.items()), 'prior coverage input differs from preparation')
    receipts = []
    for request_path in sorted((prior / 'master').glob('tools-*/action-*/request.json')):
        response_path = request_path.parent / 'response.json'
        receipts.append(dict(request=dict(path=str(request_path), sha256=sha(request_path)),
            response=dict(path=str(response_path), sha256=sha(response_path)),
            action=load(request_path)['arguments']['action'], returned=load(response_path)))
    root = Path(__file__).resolve().parents[1]
    context = dict(prior_directory=str(prior), prior_result=dict(path=str(prior / 'coverage-result.json'), sha256=sha(prior / 'coverage-result.json')),
        original_claim=dict(path=str(parent / 'coverage-review-claim.json'), sha256=sha(parent / 'coverage-review-claim.json')),
        prior_input_sha256=sha(evidence), prior_decision=result['decision'], prior_tool_receipts=receipts,
        engineering_fix_sources={name:sha(root / name) for name in ('agents/autonomy.py', 'harness/research_tools.py', 'exp/skill_rsi_continue.py')},
        provenance='explicit one-time correction of truncated context and tool schema; not a new discovery or native-thread resume',
        prior_coverage_conclusion='incomplete context; preserved decision is not a complete scientific coverage stop')
    return context, dict(result['counters_after']), packet


def input_reading(directory):
    manifest = load(directory / 'manifest.json')
    work = safe_path(manifest['work'])
    evidence = safe_path(work / 'inputs/evidence.json', work)
    content, digest = evidence.read_text(), sha(evidence)
    pages, intervals, helped = [], [], False
    for path in sorted(directory.glob('tools-*/action-*/request.json')):
        action = load(path)['arguments']['action']
        response = load(path.parent / 'response.json')
        if not response['success']:
            continue
        answer = json.loads(response['contentItems'][0]['text'])
        if action == {'kind': 'help'}:
            helped = answer.get('status') == 'completed'
        if action.get('kind') != 'read_file' or action.get('path') != 'inputs/evidence.json':
            continue
        offset = action.get('offset', 0)
        end = min(len(content), offset + 12000) if type(offset) is int else -1
        valid = (type(offset) is int and 0 <= offset <= len(content) and
                 set(action) <= {'kind', 'path', 'offset'} and answer.get('status') == 'completed' and
                 answer.get('sha256') == digest and answer.get('offset') == offset and
                 answer.get('total_chars') == len(content) and answer.get('content') == content[offset:end] and
                 'next_offset' in answer and answer['next_offset'] == (end if end < len(content) else None))
        pages.append(dict(offset=offset, next_offset=answer.get('next_offset'), total_chars=answer.get('total_chars'),
            sha256=answer.get('sha256'), verified=valid, help_preceded=helped,
            request_sha256=sha(path), response_sha256=sha(path.parent / 'response.json')))
        if valid and helped:
            intervals.append((offset, end))
    covered = 0
    for start, end in sorted(intervals):
        if start > covered:
            break
        covered = max(covered, end)
    return dict(complete=bool(pages) and covered == len(content) and any(page['help_preceded'] for page in pages),
                total_chars=len(content), covered_chars=covered, sha256=digest, pages=pages,
                scope='recomputed native-bound tool receipts; not a model assertion')


def review(parent, output, *, repair_from=None):
    parent, output = Path(parent).resolve(), Path(output).resolve()
    claim = parent / ('coverage-review-repair-claim.json' if repair_from is not None else 'coverage-review-claim.json')
    if claim.exists():
        raise ValueError('coverage review already claimed; no implicit restart or resubmission')
    repair = repair_context(parent, repair_from) if repair_from is not None else None
    packet, candidates, previous_counters = prepare(parent, output)
    if repair is not None:
        context, previous_counters, prior_packet = repair
        require(all(packet[key] == prior_packet[key] for key in ('measured_candidates', 'previous_master_decisions',
                'own_previous_skill_feedback', 'shared_budget_path')), 'parent shared context changed before repair')
        packet['repair_context'] = context
        save(output / 'repair-provenance.json', context)
        save(output / 'coverage-input.json', packet)
    budget = Budget(parent / 'resource-state.json', limits=LIMITS)
    counters = dict(previous_counters)
    actions, runs = min(32, 900 - counters['actions']), min(4, 192 - counters['cpu_runs'])
    turns = min(3, 96 - counters['model_turns'])
    if actions <= 0 or runs < 0 or turns <= 0 or counters['usage_updates'] >= 3072:
        raise ValueError('no remaining parent action/CPU allowance')
    packet['review_allocation'] = dict(actions=actions, cpu_runs=runs, model_turns=turns)
    with claim.open('x') as destination:
        os.chmod(claim, 0o600)
        json.dump(dict(output=str(output), parent_pipeline_sha256=packet['parent_pipeline_sha256'],
                       repair_from=str(Path(repair_from).resolve()) if repair_from is not None else None,
                       claimed_unix=time.time(), scope='one explicit native Master review; never auto-restart'), destination)
    original = roles.COMMON, roles.ACTION_LIMIT, roles.RUN_LIMITS
    role = None
    result = dict(status='needs_attention', controller_accepted=False, integration_executed=False,
                  kernel_executed=False, sealed_used=False, promoted=False, gpu_jobs_submitted=0)
    process_context = ExitStack()
    try:
        roles.COMMON = COMMON
        roles.ACTION_LIMIT = 900
        roles.RUN_LIMITS = dict(model_turns=96, cpu_runs=192, gpu_attempts=16, usage_updates=3072)
        state = budget.read()
        if time.time() >= state['started'] + state['wall_seconds']:
            raise ValueError('parent wall budget exhausted')
        packet['resource_snapshot'] = state
        process_context.enter_context(recorded_processes(output / 'processes', result))
        role = roles.session(output / 'master', 'Master', packet, actions, runs)
        prompt = '先research {"action":{"kind":"help"}}，再read_file inputs/evidence.json offset=0，按next_offset读到null。重放自己的旧决策与已共享反馈。自主决定保持stop或补充未知正确性单项的dev覆盖，不按单项赢家机械筛选，不强迫正结果。只输出规定的coverage decision JSON。'
        for attempt in range(packet['review_allocation']['model_turns']):
            if time.time() >= budget.read()['started'] + budget.read()['wall_seconds']:
                raise RuntimeError('parent wall budget exhausted during coverage review')
            try:
                value = roles.turn(role, prompt, counters)
                decision = validate_decision(value, candidates)
                break
            except ValueError as error:
                cursor = error.__traceback__
                model_format = isinstance(error, ModelResponseError)
                while cursor is not None:
                    model_format = model_format or cursor.tb_frame.f_code is getattr(roles.response_object, '__code__', None)
                    cursor = cursor.tb_next
                if not model_format or attempt + 1 == packet['review_allocation']['model_turns']:
                    raise
                prompt = '仅修复模型JSON/协议格式并保持自主科学判断：' + str(error)
        else:
            raise ValueError('no remaining native model turns')
        response = role['directory'] / f'turn-{role["number"]:02d}-response.json'
        reading = None
        if repair is not None:
            binding = dict(role_thread=role['thread']['thread']['id'], role_turn=role['number'],
                native_response_sha256=sha(response), decision=decision, counters_before=previous_counters, counters_after=counters)
            native_counters(parent, output, binding)
            reading = input_reading(role['directory'])
        result.update(status='stopped' if decision['decision'] == 'stop' else 'controller_review_requested',
            decision=decision, role_thread=role['thread']['thread']['id'], role_turn=role['number'],
            native_response_sha256=sha(response),
            controller_handoff=[dict(candidates[name], coverage_response_sha256=sha(response)) for name in decision['review']],
            next_step='No automatic execution. Independently gate selected units before Integration; Kernel may request capability or stop.')
        if reading is not None:
            result.update(input_reading=reading, repair_from=context['prior_result'], coverage_complete=reading['complete'])
            if not reading['complete']:
                result.update(status='incomplete_context', controller_handoff=[],
                    next_step='Context still incomplete: decision is not a scientific coverage ruling. No automatic repair/restart.')
    except BaseException as error:
        result.update(status='needs_attention', error=type(error).__name__ + ': ' + str(error)[:2000])
        raise
    finally:
        try:
            try:
                if role is not None:
                    role['client'].close()
                    result['role_exit_code'] = role['client'].process.returncode
            finally:
                process_context.close()
            if role is not None and (result['role_exit_code'] != 0 or not result.get('role_processes_closed')):
                raise RuntimeError('coverage native role did not close cleanly')
        except BaseException as error:
            result.update(status='needs_attention', error=type(error).__name__ + ': ' + str(error)[:2000])
            raise
        finally:
            roles.COMMON, roles.ACTION_LIMIT, roles.RUN_LIMITS = original
            result.update(counters_before=previous_counters, counters_after=counters, resource_state=budget.read(),
                          parent_pipeline_unchanged=sha(parent / 'pipeline-result.json') == packet['parent_pipeline_sha256'],
                          parent_feedback_unchanged=sha(parent / 'feedback.json') == packet['parent_feedback_sha256'])
            save(output / 'coverage-result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repair-from', type=Path)
    arguments = parser.parse_args()
    result = review(arguments.parent, arguments.out, repair_from=arguments.repair_from)
    print(json.dumps(dict(status=result['status'], reviewed_candidates=len(result['controller_handoff']),
        coverage_complete=result.get('coverage_complete'),
        gpu_jobs_submitted=0, controller_accepted=False, sealed_used=False)))


if __name__ == '__main__':
    main()
