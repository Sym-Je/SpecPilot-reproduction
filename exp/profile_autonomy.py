"""New bounded research round with model-owned requests for stock observations."""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from exp import gpu_autonomy as roles, skill_rsi
from exp.profile_resource import LIMITS, archive, execute, feedback, prepare
from exp.phase4_run import reference
from exp.skill_rsi import Campaign
from harness.engine_research import save
from harness.skill_broker import SkillAccess
from harness.skill_diagnostics import checked_file, checked_manifest, write_json


PROFILE_RULES = '''
本轮新增按需stock观测能力：最终JSON action可为
{"kind":"request_stock_profile","workload_id":"目录中的ID","preset":"目录中的preset","reason":"你要检验的假设与所需证据"}。
GPU请求只由可信broker执行，不在research动态工具里同步跑，不可提交路径/提示/命令/flags。
拿到evidence ID后，可research {"action":{"kind":"run_skill","skill":"profiler","evidence":"ID"}}。
形状摘要截断时，可research {"action":{"kind":"read_profile_shapes","evidence":"ID","offset":0}}，
按next_offset继续分页；它只返回原trace的维度事实，每页计一次CPU额度，不认证VERIFY/kernel关联。
不知道形状时只提供profile-only；compute/pipeline unavailable不是零成本，不得填猜测形状。
graph trace的kernel工作、shape事件和源码归因要区分；profile耗时不能当正常吞吐或收益。
同一角色重复申请同workload/preset会明确复用原观测；这不是新的独立实验。
本轮新预算8 GPU小时/12小时/并发2卡，单卡profile硬限45分钟，source研究是双卡单元。
研究GPU按方向串行调度，不为并发抢额度；独立dev需额外双卡预算，预算不足应停止或请求Master重分配。
不读取旧私有验证、本轮没有sealed授权。先查看自己的证据和精确工具help，自己设计实验和迭代。
'''


def profile_action(action):
    from exp.profile_capture import validate_action
    if not isinstance(action, dict) or set(action) != {'kind', 'workload_id', 'preset', 'reason'}:
        raise ValueError('profile requests accept only a fixed workload, preset and reason')
    if action['kind'] != 'request_stock_profile':
        raise ValueError('not a stock-profile action')
    return validate_action({key: value for key, value in action.items() if key != 'kind'})


class ProfileCampaign(Campaign):
    def __init__(self, root, inputs, tools, capture_template, preflight, *, executor=execute,
                 job_prefix='sp-stockprof-20261111-a01'):
        super().__init__(root, inputs, tools, limits=LIMITS, job_prefix=job_prefix, max_workers=1)
        self.capture_template, self.preflight = capture_template, Path(preflight).absolute()
        self.profile_executor = executor
        self.profile_requests = []
        self.profile_evidence = {}
        self.profile_cache = {}
        self.profile_allocations = {}

    def explore(self, label, kind, packet, allocation, prompt, comparison_base=None):
        self.profile_allocations[label] = allocation['gpu_attempts']
        return super().explore(label, kind, packet, allocation, prompt, comparison_base=comparison_base)

    def reserved_jobs(self, mode, role=None):
        selected = super().reserved_jobs(mode, role)
        if mode == 'source-research' and role is not None:
            label = role['directory'].name
            names = {job['name'] for job in self.budget.read()['jobs']}
            selected += [Path(item['directory']).name for item in self.profile_requests
                         if item['role_binding']['role'] == label and Path(item['directory']).name in names]
        return selected

    def packet(self):
        from exp.profile_capture import PRESETS, WORKLOADS
        packet = super().packet()
        catalog = {}
        sources = {}
        for identity, selection in WORKLOADS.items():
            suite = selection['suite']
            if suite not in sources:
                path = checked_file(self.capture_template['dev_sources'][suite])
                sources[suite] = [json.loads(line) for line in path.read_text().splitlines() if line]
            request = sources[suite][selection['index']]
            catalog[identity] = dict(selection, public_id=request['id'], prompt_characters=len(request['turns'][0]))
        packet.update(stock_profile=dict(workloads=catalog, presets=PRESETS,
            request_action='request_stock_profile', maximum_current_stage_requests=4,
            prompt_characters_are_not_token_or_kv_lengths=True,
            unknown_shapes_remain_unknown=True),
            prior_validation_visible=False,
            stage_scope='new public-dev research; previous private validation is not reused or disclosed')
        return packet

    def check_capacity(self, gpus, deadline):
        state = self.budget.read()
        seconds = deadline + 1200
        charged = sum(job.get('charged_gpu_seconds', job['gpus'] * job['seconds']) for job in state['jobs'])
        active = sum(job['gpus'] for job in state['jobs'] if not job['terminated'])
        if (charged + gpus * seconds > state['gpu_seconds'] or active + gpus > state['concurrent_gpus'] or
                time.time() + seconds > state['started'] + state['wall_seconds']):
            raise ValueError('remaining stage budget cannot reserve this bounded job; no task submitted')

    def experiment(self, role, action, stage):
        self.check_capacity(2, 3600)
        return super().experiment(role, action, stage)

    def gate(self, directory):
        try:
            self.check_capacity(2, 7200)
        except ValueError as error:
            return dict(status='rejected-before-submission', controller_accepted=False,
                diagnostic_request=str(directory), reason=str(error), correctness_not_evaluated=True)
        return super().gate(directory)

    def attach_skills(self, role):
        label = role['directory'].name
        evidence = self.profile_evidence.setdefault(label, {'stock': self.inputs})
        role['broker_factory'] = SkillAccess(role['manifest']['role'], evidence, self.tools,
            self.root / 'skill-cache', extensions=self.root / 'extensions').factory()

    def open_role(self, label, kind, packet, actions=120, runs=24):
        role = roles.session(self.root / label, kind, packet, actions, runs)
        role['counters'] = dict(actions=0, cpu_runs=0, gpu_attempts=0, model_turns=0, usage_updates=0)
        self.opened.append(role)
        self.attach_skills(role)
        return role

    def validate_preflight(self):
        if self.preflight.parent != self.root:
            raise ValueError('profile readiness must come from this new stage, not an old campaign')
        request = json.loads((self.preflight / 'request.json').read_text())
        if request['budget_path'] != str(self.budget.path.absolute()):
            raise ValueError('profile readiness belongs to a different budget')
        jobs = [job for job in self.budget.read()['jobs'] if job['name'] == self.preflight.name]
        if (len(jobs) != 1 or not jobs[0]['terminated'] or jobs[0]['terminal'] != 'Completed' or
                jobs[0]['submission_code'] != 200 or request['role_binding'] is not None):
            raise ValueError('current-stage completed trusted stock-profile readiness is required')
        result = feedback(self.preflight / 'remote', request)
        if not result['capture_completed'] or result['option_enabled'] is not False:
            raise ValueError('stock profile readiness is incomplete')
        initial = json.loads(self.inputs.read_text())
        if checked_manifest(initial)[2] is not None:
            raise ValueError('initial observation must not invent a verified workload shape')
        manifests = result.get('profile_inputs')
        if not isinstance(manifests, list) or initial not in manifests:
            raise ValueError('initial stock evidence differs from the selected current-stage preflight')

    def freeze_sources(self, directory):
        source = archive(directory)
        identity = json.loads((directory / 'source-identity.json').read_text())
        identity['archive_sha256'] = identity['archive']['sha256']
        save(directory / 'source-identity.json', identity)
        return source

    def collect_profile(self, role, action):
        action = profile_action(action)
        label = role['directory'].name
        key = (label, action['workload_id'], action['preset'])
        if key in self.profile_cache:
            return dict(self.profile_cache[key], cached=True,
                        provenance='same-role stock observation reused; no new GPU execution or discovery')
        if len(self.profile_requests) >= 4:
            raise ValueError('current-stage profile request allocation exhausted; continue analysis or finish')
        if len(self.reserved_jobs('source-research', role)) >= self.profile_allocations.get(label, 2):
            raise ValueError('Master-assigned role GPU attempt allocation exhausted')
        if role['actions'] < 1:
            raise ValueError('profile request requires remaining role action allocation')
        self.check_capacity(1, 2700)
        number = len(self.profile_requests) + 1
        directory = self.root / f'{self.job_prefix}-profile-{number:02d}'
        binding = dict(role=label, thread=role['thread']['thread']['id'], turn=role['number'],
            response=reference(role['directory'] / f'turn-{role["number"]:02d}-response.json'))
        request = dict(self.capture_template, action=action)
        self.prepare_profile(directory, request, binding)
        self.counters['actions'] += 1
        role['actions'] -= 1
        entry = dict(directory=str(directory), role_binding=binding, action=action)
        self.profile_requests.append(entry)
        save(self.root / 'profile-requests.json', self.profile_requests)
        save(self.root / 'counters.json', self.counters)
        result = self.profile_executor(directory, self.budget)
        if result.get('status') != 'completed':
            return dict(status='failed', request_directory=str(directory),
                error=result.get('error'), log_tail=result.get('log_tail'), controller_accepted=False)
        evidence = self.profile_evidence[label]
        identifiers = []
        registered = self.root / 'profile-evidence' / label
        registered.mkdir(parents=True, exist_ok=True)
        for index, manifest in enumerate(result['profile_inputs']):
            checked_manifest(manifest)
            identity = f'profile-{number:02d}-{index:02d}'
            path = registered / f'{identity}.json'
            if path.exists():
                raise ValueError('profile evidence IDs are immutable')
            write_json(path, manifest)
            evidence[identity] = path
            identifiers.append(identity)
        self.attach_skills(role)
        answer = dict(status='completed', evidence_ids=identifiers, cached=False,
            workload_id=action['workload_id'], preset=action['preset'], shape_status=result['shape_status'],
            stage_attribution_validated=False, controller_accepted=False,
            provenance='new trusted canonical-stock observation, not a candidate or acceptance')
        self.profile_cache[key] = answer
        entry['result'] = answer
        save(self.root / 'profile-requests.json', self.profile_requests)
        return answer

    def prepare_profile(self, directory, request, binding):
        return prepare(directory, request, self.budget, role_binding=binding)

    def model_response(self, role, prompt, *, action_required=False):
        original = prompt
        for step in range(6):
            response = super().model_response(role, prompt, action_required=action_required)
            action = response.get('action')
            if not isinstance(action, dict) or action.get('kind') != 'request_stock_profile':
                return response
            try:
                result = self.collect_profile(role, response['action'])
            except (ValueError, KeyError, TypeError) as error:
                result = dict(status='rejected', reason=str(error), controller_accepted=False)
            prompt = original + '\n你的实际profile反馈：' + json.dumps(result, ensure_ascii=False)
            prompt += '\n自行分析/修复/迭代；可按需run_skill或申请另一观测，最终仍遵循本阶段原输出schema。'
        raise ValueError('profile-only response loop exhausted without a research decision')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--capture-template', type=Path, required=True)
    parser.add_argument('--preflight', type=Path, required=True)
    args = parser.parse_args()
    from exp.skill_rsi_continue import recorded_processes
    skill_rsi.COMMON += PROFILE_RULES
    campaign = ProfileCampaign(args.stage, args.inputs, args.tools,
        json.loads(args.capture_template.read_text()), args.preflight)
    closure = {}
    try:
        with recorded_processes(campaign.root / 'processes', closure):
            result = campaign.run()
    finally:
        save(campaign.root / 'process-closure.json', closure)
    save(campaign.root / 'profile-campaign-result.json', dict(result,
        profile_requests=campaign.profile_requests, prior_sealed_reused=False,
        preflight_directory=str(campaign.preflight), initial_evidence=reference(campaign.inputs),
        role_processes_closed=closure.get('role_processes_closed') is True,
        scope='public profile-enabled research; no normal final T3 or multiround RSI claim'))


if __name__ == '__main__':
    main()
