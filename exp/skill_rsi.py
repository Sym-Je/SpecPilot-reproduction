"""Trusted multi-role research coordinator; scientific choices remain model-owned."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import threading
import time

from exp import gpu_autonomy as roles
from exp.source_autonomy import COMMON as SOURCE_COMMON
from exp.source_resource import execute
from harness.engine_research import Budget, save
from harness.skill_broker import SkillAccess
from harness.source_candidate import cpu_receipt, file_sha, read_patch, validate_action


ROOT = Path(__file__).resolve().parents[1]
LIMITS = dict(gpu_seconds=115200, wall_seconds=86400, concurrent_gpus=4)
COMMON = SOURCE_COMMON.replace('16H100 GPU小时、墙钟12小时、并发2卡',
    '32H100 GPU小时、墙钟24小时、最多并发4卡').replace('只能修改已有srt Python文件',
    '只能修改已有srt或python/sglang/kernels/下的Python/Triton文件') + '''
本阶段包含Master、direction、integration、kernel，阶段均共享唯一总预算。
额外research工具：{"action":{"kind":"list_skills"}}；
{"action":{"kind":"run_skill","skill":"profiler|compute|pipeline|capacity|triage","evidence":"stock"}}。
这是固定版本BBuf能力的可信代理，不接受你的路径、URL、shell或额外参数；工具结果是外部先验，不算独立发现。
按需自主调用，不强迫所有工具都跑。层锚点/启动日志缺失会返回unavailable，不据此编造结论。
每次run_skill计一次CPU工具额度。集成只收到Master明确共享的补丁及摘要，不获得其他角色私人推理。
kernel可以改授权的既有Python/Triton路径，不预设必须找到收益；真实调用、数值和系统验收仍不可省。
资源/基础设施失败先给具体反馈，科学修复由你自己完成。最终JSON可用finish并提供candidate及patch/self_check路径。
'''


def freeze(directory):
    names = subprocess.check_output(['git', 'ls-files', 'agents', 'exp', 'harness', 'controller',
        'assets/upstream/dev', 'assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'],
        cwd=ROOT, text=True).splitlines()
    for prefix in ('exp', 'harness', 'controller'):
        names.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / prefix).glob('*.py'))
    names.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / 'exp').glob('source_*.sh'))
    names.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / 'harness').glob('source_*.c'))
    names = sorted(set(names))
    with tarfile.open(directory / 'source.tar', 'w') as bundle:
        for name in names:
            bundle.add(ROOT / name, arcname=name, recursive=False)
    save(directory / 'source-identity.json', dict(files={name: file_sha(ROOT / name) for name in names},
        archive_sha256=file_sha(directory / 'source.tar')))
    return directory / 'source.tar'


class ModelResponseError(ValueError):
    pass


def validate_plan(value):
    if not isinstance(value, dict) or set(value) != {'directions'}:
        raise ValueError('Master must return a directions list')
    directions = value['directions']
    if not isinstance(directions, list) or not 2 <= len(directions) <= 3:
        raise ValueError('two or three independently assigned directions required')
    names = set()
    for item in directions:
        if set(item) != {'id', 'brief', 'allocation'} or item['id'] in names:
            raise ValueError('direction identity/fields invalid')
        if not isinstance(item['id'], str) or not item['id'].isalnum() or len(item['id']) > 32:
            raise ValueError('bounded alphanumeric direction ID required')
        if not isinstance(item['brief'], str) or not item['brief'].strip():
            raise ValueError('falsifiable direction brief required')
        allocation = item['allocation']
        if set(allocation) != {'actions', 'cpu_runs', 'gpu_attempts'}:
            raise ValueError('complete role allocation required')
        for key, upper in (('actions', 160), ('cpu_runs', 32), ('gpu_attempts', 3)):
            if type(allocation[key]) is not int or not 1 <= allocation[key] <= upper:
                raise ValueError('role allocation outside stage allowance')
        names.add(item['id'])
    if sum(item['allocation']['actions'] for item in directions) > 400:
        raise ValueError('combined directions would consume the integration/kernel reserve')
    return directions


class Campaign:
    def __init__(self, root, inputs, tools):
        self.root = Path(root).resolve()
        self.inputs, self.tools = Path(inputs).resolve(), Path(tools).resolve()
        self.budget = Budget(self.root / 'resource-state.json', limits=LIMITS)
        self.pin = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        self.counters = dict(actions=0, cpu_runs=0, gpu_attempts=0, controller_jobs=0, model_turns=0, usage_updates=0)
        self.opened = []
        self.feedback = []
        self.completed = []
        self.lock = threading.RLock()

    def packet(self):
        report = json.loads((ROOT / 'logs/skills-diagnostics-20261110-a01/historical-evidence-summary.json').read_text())
        return dict(scope='authorized stock source research; no author final/sealed/private cross-role context',
            stock=dict(block=8, dtype='bfloat16', target='Qwen3.8-27B', draft='DFlash2', engine='SGLang v0.5.20'),
            diagnosis=dict(source='previous independently reviewed stock evidence; reused, not a new discovery',
                kernel_work_fraction=report['kernel_work_fraction'], not_wall_clock_share=True,
                conditional_stock_tau=4.860407323199587,
                conditional_N32_tau=[5.931151582431141, 6.030082190236792],
                note='reference-fork model bounds, not speedup CI or an accepted tree implementation',
                formal_ceiling=None),
            skills=dict(evidence_ids=['stock'], action='list_skills then run_skill as needed'),
            fixed_runtime=dict(numa_bind_v2=False, trusted_atomic_triton_cache=True,
                scope='common deployment preparation, not an agent optimization'),
            resource_limits=LIMITS, source_pin=self.pin)

    def open_role(self, label, kind, packet, actions=120, runs=24):
        role = roles.session(self.root / label, kind, packet, actions, runs)
        startup = ROOT / 'logs/ceiling-complete-run-20261110-b01/sp-ceiling-complete-20261110-b07/remote/stock/stock.launcher.log'
        role['broker_factory'] = SkillAccess(kind, {'stock': self.inputs}, self.tools,
            self.root / 'skill-cache', extensions=self.root / 'extensions',
            startup_log=dict(path=str(startup), sha256=file_sha(startup))).factory()
        self.opened.append(role)
        role['counters'] = dict(actions=0, cpu_runs=0, gpu_attempts=0, model_turns=0, usage_updates=0)
        return role

    def ask(self, role, prompt):
        if time.time() >= self.budget.read()['started'] + self.budget.read()['wall_seconds']:
            raise RuntimeError('stage wall budget exhausted')
        before = dict(role['counters'])
        try:
            try:
                return roles.turn(role, prompt, role['counters'])
            except ValueError as error:
                cursor = error.__traceback__
                while cursor is not None:
                    if cursor.tb_frame.f_code is getattr(roles.response_object, '__code__', None):
                        raise ModelResponseError(str(error)) from error
                    cursor = cursor.tb_next
                raise
        finally:
            with self.lock:
                for name in self.counters:
                    self.counters[name] += role['counters'].get(name, 0) - before.get(name, 0)
                if self.counters['actions'] > 900 or self.counters['model_turns'] > 96:
                    raise RuntimeError('stage action/model allocation exhausted')
                save(self.root / 'counters.json', self.counters)

    def model_response(self, role, prompt, *, action_required=False):
        for attempt in range(3):
            try:
                response = self.ask(role, prompt)
                if not isinstance(response, dict) or (action_required and not isinstance(response.get('action'), dict)):
                    raise ModelResponseError('one JSON object with a structured action is required')
                return response
            except ModelResponseError as error:
                if attempt == 2:
                    raise
                prompt = '模型JSON/协议格式未通过：' + str(error) + '。仅修复格式，保留自己的科学判断，重交完整JSON对象。'

    def reserved_jobs(self, mode, role=None):
        selected = []
        thread = role['thread']['thread']['id'] if role is not None else None
        for reservation in self.budget.read()['jobs']:
            request = json.loads((self.root / reservation['name'] / 'request.json').read_text())
            if request['mode'] == mode and (thread is None or request.get('role_thread') == thread):
                selected.append(reservation['name'])
        return selected

    def experiment(self, role, action, stage):
        validate_action(action)
        work = Path(role['manifest']['work'])
        receipt = cpu_receipt(work, role['directory'], action)
        patch = read_patch(work / action['patch'])
        with self.lock:
            if self.counters['gpu_attempts'] >= 16 or role['actions'] < 1:
                raise ValueError('GPU request/action allowance exhausted')
            self.counters['gpu_attempts'] += 1
            self.counters['actions'] += 1
            role['actions'] -= 1
            directory = self.root / f'sp-skillrsi-20261110-b01-{stage}-{self.counters["gpu_attempts"]:02d}'
            directory.mkdir(mode=0o700)
        shutil.copyfile(work / action['patch'], directory / 'patch.json')
        shutil.copyfile(work / action['self_check'], directory / 'self-check.py')
        save(directory / 'cpu-receipt.json', receipt)
        request = dict(mode='source-research', source_pin=self.pin, action=action,
            patch_sha256=file_sha(directory / 'patch.json'), option_id=patch['option_id'],
            cpu_receipt_sha256=file_sha(directory / 'cpu-receipt.json'),
            self_check_sha256=file_sha(directory / 'self-check.py'),
            role_thread=role['thread']['thread']['id'], role_turn=role['number'],
            role_response_sha256=file_sha(role['directory'] / f'turn-{role["number"]:02d}-response.json'))
        comparison = role.get('comparison_base')
        if comparison is not None:
            if comparison not in self.completed:
                raise ValueError('comparison stack is not an actual measured current-stage candidate')
            shutil.copyfile(comparison / 'patch.json', directory / 'comparison-base.json')
            request.update(comparison_base_sha256=file_sha(directory / 'comparison-base.json'),
                comparison_source=str(comparison))
        save(directory / 'request.json', request)
        value = execute(directory, freeze(directory), self.budget)
        value.update(request_directory=str(directory), scientific_stage=stage, role_label=stage,
            owner=role['manifest']['role'])
        with self.lock:
            self.feedback.append(value)
            if value['status'] == 'completed':
                self.completed.append(directory)
            save(self.root / 'feedback.json', self.feedback)
        return value

    def explore(self, label, kind, packet, allocation, prompt, comparison_base=None):
        role = self.open_role(label, kind, packet, allocation['actions'], allocation['cpu_runs'])
        role['comparison_base'] = comparison_base
        for step in range(1, 13):
            response = self.model_response(role, prompt, action_required=True)
            action = response.get('action', {})
            if action.get('kind') in ('finish', 'request_budget'):
                save(role['directory'] / 'research-result.json', response)
                return dict(label=label, role=kind, response=response,
                    measurements=[value for value in self.feedback if value.get('request_directory', '').split('/')[-1].startswith('sp-skillrsi')
                        and value.get('owner') == kind and value.get('role_label') == label])
            try:
                if len(self.reserved_jobs('source-research', role)) >= allocation['gpu_attempts']:
                    raise ValueError('role GPU allocation exhausted; finish or request_budget')
                value = self.experiment(role, action, label)
            except (ValueError, SyntaxError, FileNotFoundError) as error:
                value = dict(status='rejected', reason=str(error), controller_accepted=False)
            prompt = json.dumps(value, ensure_ascii=False) + '\n这是你的实际反馈。自己复核/修复，继续请求run_source，或finish；不得把诊断当正确性验收。'
        return dict(label=label, role=kind, response=dict(action=dict(kind='finish'),
            conclusion='bounded model-turn allocation exhausted'), measurements=[])

    def gate(self, directory):
        directory = Path(directory)
        if directory not in self.completed or directory.parent != self.root:
            raise ValueError('only an actually completed current-stage candidate can be independently reviewed')
        request = json.loads((directory / 'request.json').read_text())
        if request['patch_sha256'] != file_sha(directory / 'patch.json'):
            raise ValueError('candidate changed after measurement')
        gate = self.root / (directory.name + '-gate')
        gate.mkdir(mode=0o700)
        names = ['patch.json', 'cpu-receipt.json', 'self-check.py']
        if request.get('comparison_base_sha256'):
            names.append('comparison-base.json')
        for name in names:
            shutil.copyfile(directory / name, gate / name)
        request.update(mode='source-controller', diagnostic_request=str(directory),
            diagnostic_feedback_sha256=file_sha(directory / 'feedback.json'),
            action=dict(request['action'], per_suite=6, max_new_tokens=2048))
        save(gate / 'request.json', request)
        try:
            result = execute(gate, freeze(gate), self.budget)
        finally:
            with self.lock:
                self.counters['controller_jobs'] = len(self.reserved_jobs('source-controller'))
                save(self.root / 'counters.json', self.counters)
        result.update(request_directory=str(gate), diagnostic_request=str(directory))
        self.feedback.append(result)
        save(self.root / 'feedback.json', self.feedback)
        return result

    def shared(self, directories):
        shared = []
        for directory in directories:
            directory = Path(directory)
            if directory not in self.completed:
                raise ValueError('Master cannot share an unmeasured candidate')
            shared.append(dict(id=directory.name, patch=json.loads((directory / 'patch.json').read_text()),
                patch_sha256=file_sha(directory / 'patch.json'), diagnostic_source=str(directory),
                diagnostic_feedback_sha256=file_sha(directory / 'feedback.json'),
                measurement=json.loads((directory / 'feedback.json').read_text()),
                provenance='Master explicitly shared candidate and measurement; reused, not independently discovered'))
        return shared

    def select_reviews(self, master, stage, stage_result, candidates):
        prompt = json.dumps(dict(stage=stage, stage_result=stage_result,
            completed_candidates=[str(path) for path in candidates]), ensure_ascii=False)
        prompt += '\n自主选择值得独立dev验收的本阶段已测候选。输出{"review":["目录",...],"reason":"依据"}；允许空列表，不把实验失败当优化收益。'
        decision = self.model_response(master, prompt)
        selected = [Path(name) for name in decision.get('review', [])]
        if len(selected) != len(set(selected)) or any(path not in candidates for path in selected):
            raise ValueError('Master review refers to duplicated or unmeasured stage candidates')
        save(self.root / (stage + '-master-review.json'), decision)
        return selected

    def select_baseline(self, master, stage, candidates, fallback=None):
        if not candidates:
            return fallback
        response = self.model_response(master, json.dumps(dict(stage=stage,
            independently_accepted=[str(path) for path in candidates]), ensure_ascii=False) +
            '\n选择下一阶段的当前栈，只能选上述独立验收通过的候选。输出{"baseline":"目录","reason":"依据"}。性能将直接与该栈配对，正确性仍参考canonical stock。')
        selected = Path(response.get('baseline', ''))
        if selected not in candidates:
            raise ValueError('Master baseline must be independently accepted')
        save(self.root / (stage + '-baseline.json'), response)
        return selected

    def run(self):
        if (self.root / 'pipeline-result.json').exists():
            raise ValueError('campaign already started; explicit checkpoint recovery required')
        proof = self.root / 'preflight-result.json'
        if (not proof.is_file() or json.loads(proof.read_text()).get('status') != 'completed'
                or json.loads(proof.read_text()).get('preflight') is not True):
            raise ValueError('actual source boundary/engine preflight must pass before research')
        roles.COMMON = COMMON
        roles.ACTION_LIMIT = 900
        roles.RUN_LIMITS = dict(model_turns=96, cpu_runs=192, gpu_attempts=16, usage_updates=3072)
        result = dict(status='running', stages={}, sealed_completed=False, promoted=False,
            real_engine_rsi_completed=False, formal_ceiling=None)
        save(self.root / 'pipeline-result.json', result)
        try:
            packet = self.packet()
            master = self.open_role('master', 'Master', packet, 120, 20)
            prompt = '先读自身证据并查看工具能力，按需用BBuf工具。自主分配2至3个互补源码方向，不代做实现。'
            prompt += '只输出{"directions":[{"id":"d1","brief":"假设/证据/范围/停止条件","allocation":{"actions":120,"cpu_runs":24,"gpu_attempts":2}},...]}。'
            for attempt in range(3):
                plan = self.model_response(master, prompt)
                try:
                    directions = validate_plan(plan)
                    break
                except ValueError as error:
                    if attempt == 2:
                        raise
                    prompt = '你的计划未通过结构化协议：' + str(error) + '。保留自己的科学判断，自己修复输出格式后重交完整directions对象。'
            save(self.root / 'master-plan.json', plan)
            with ThreadPoolExecutor(max_workers=2) as executor:
                pending = {}
                for item in directions:
                    label = 'direction-' + item['id']
                    pending[label] = executor.submit(self.explore, label, 'direction',
                        dict(packet, assignment=item), item['allocation'],
                        '自主读取证据和源码，按需用BBuf工具，先写验收脚本，再实现option，执行自检并请求run_source；自己迭代或诚实停止。')
                for label, future in pending.items():
                    result['stages'][label] = future.result()
                    save(self.root / 'pipeline-result.json', result)
            review = self.model_response(master, json.dumps(dict(direction_results=result['stages'],
                completed_candidates=[str(path) for path in self.completed]), ensure_ascii=False) +
                '\n选择值得独立dev验收并考虑整合的已测候选。输出{"review":["候选目录绝对路径",...],"reason":"依据"}；允许空列表但说明限制。')
            candidates = [Path(name) for name in review.get('review', [])]
            if len(candidates) != len(set(candidates)) or any(path not in self.completed for path in candidates):
                raise ValueError('Master review must select unique actually measured candidates')
            gates = [self.gate(path) for path in candidates]
            result['direction_gates'] = gates
            safe = [Path(item['diagnostic_request']) for item in gates
                if item.get('controller_verdict', {}).get('correctness', {}).get('correctness_passed')]
            current_stack = self.select_baseline(master, 'integration', [Path(item['diagnostic_request'])
                for item in gates if item.get('controller_accepted') is True])
            allocation = dict(actions=160, cpu_runs=32, gpu_attempts=2)
            integration_packet = dict(packet, shared_candidates=self.shared(safe),
                comparison_stack=str(current_stack) if current_stack else 'canonical-stock',
                scope_note='Only explicitly shared patches; no other direction private reasoning.')
            integrated = self.explore('integration', 'integration', integration_packet, allocation,
                '研究共享补丁的兼容/互补/冲突，按需用BBuf。可组合单项弱收益但正确性通过的补丁；自己实现/自检/run_source并迭代。'
                '没有可整合补丁时给出有依据的finish，不能假造组合或收益。', comparison_base=current_stack)
            result['stages']['integration'] = integrated
            integrated_paths = [path for path in self.completed if '-integration-' in path.name]
            integrated_reviews = self.select_reviews(master, 'integration', integrated, integrated_paths)
            integration_gates = [self.gate(path) for path in integrated_reviews]
            result['integration_gates'] = integration_gates
            current_stack = self.select_baseline(master, 'kernel', [Path(item['diagnostic_request'])
                for item in integration_gates if item.get('controller_accepted') is True], fallback=current_stack)
            kernel_inputs = [Path(item['diagnostic_request']) for item in integration_gates
                if item.get('controller_verdict', {}).get('correctness', {}).get('correctness_passed')] or safe
            selected_stack = None
            if current_stack is not None:
                kernel_inputs = list(dict.fromkeys([current_stack, *kernel_inputs]))
                sources = [item for item in gates + integration_gates
                    if item.get('controller_accepted') is True and Path(item['diagnostic_request']) == current_stack]
                if len(sources) != 1:
                    raise ValueError('selected current stack lacks a unique accepted gate provenance')
                selected_stack = dict(diagnostic_source=str(current_stack),
                    patch_sha256=file_sha(current_stack / 'patch.json'),
                    controller_gate=sources[0],
                    provenance='Master-selected independently accepted stack; explicitly shared reuse, not a new discovery')
            kernel_packet = dict(packet, shared_candidates=self.shared(kernel_inputs),
                comparison_stack=str(current_stack) if current_stack else 'canonical-stock',
                selected_stack=selected_stack,
                scope_note='Master shared current correct stack(s); kernel agent chooses an evidence-backed hotspot.')
            kernel = self.explore('kernel', 'kernel', kernel_packet, allocation,
                '自主诊断当前正确栈的kernel热点，按需用BBuf。只在有证据时实现可开关机制并自检/run_source，确认数值与真实路径；'
                '没有可信热点或能力不足可finish，不能把微基准当端到端收益。', comparison_base=current_stack)
            result['stages']['kernel'] = kernel
            kernel_paths = [path for path in self.completed if '-kernel-' in path.name]
            kernel_reviews = self.select_reviews(master, 'kernel', kernel, kernel_paths)
            kernel_gates = [self.gate(path) for path in kernel_reviews]
            result['kernel_gates'] = kernel_gates
            final = self.model_response(master, json.dumps(dict(direction_gates=gates, integration_gates=integration_gates,
                kernel_gates=kernel_gates), ensure_ascii=False) +
                '\n根据独立验收选择最终候选或停止。输出{"decision":"final|stop","request_directory":"通过验收条目的diagnostic_request原候选目录或空串","reason":"证据和限制"}。不要选gate目录；不宣称sealed已过或晋升。')
            reviewed = gates + integration_gates + kernel_gates
            eligible = [item for item in reviewed if item.get('controller_accepted') is True
                and final.get('request_directory') == item.get('diagnostic_request')]
            if final.get('decision') not in ('final', 'stop') or (final.get('decision') == 'final' and len(eligible) != 1):
                raise ValueError('final must refer to one independently accepted candidate, or stop')
            result.update(status='research_complete', master_final=final,
                all_research_roles_executed=True, controller_accepted=final['decision'] == 'final' and bool(eligible),
                phase4_status='requires_frozen_candidate_and_controller_owned_execution',
                next_round_checkpoint=dict(source_pin=self.pin, final_decision=final, feedback_sha256=file_sha(self.root / 'feedback.json') if self.feedback else None))
        except Exception as error:
            result.update(status='needs_attention', error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            for role in self.opened:
                role['client'].close()
            result.update(counters=self.counters, resource_state=self.budget.read(),
                role_processes={role['directory'].name: dict(pid=role['client'].process.pid,
                    exit_code=role['client'].process.returncode) for role in self.opened},
                role_processes_closed=all(role['client'].process.poll() is not None for role in self.opened))
            save(self.root / 'pipeline-result.json', result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    arguments = parser.parse_args()
    result = Campaign(arguments.root, arguments.inputs, arguments.tools).run()
    print(json.dumps(dict(status=result['status'], sealed_completed=result['sealed_completed'],
        controller_accepted=result.get('controller_accepted', False))))


if __name__ == '__main__':
    main()
