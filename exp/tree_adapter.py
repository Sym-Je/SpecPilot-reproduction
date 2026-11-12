"""Direction-owned stock adapter research through the existing trusted source executor."""

import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import time

from exp import autonomy, gpu_autonomy as roles, source_autonomy
from exp.engine_resource import execute as engine_execute
from exp.gpu_autonomy import ROOT
from exp.phase4_run import reference
from exp.skill_rsi_continue import recorded_processes
from exp.source_resource import command as source_command, feedback as source_feedback
from harness.decision_evidence import prepare as prepare_evidence, verify as verify_evidence
from harness.decision_review import verify as verify_review
from harness.engine_research import Budget, save
from harness.headroom_evidence import freeze_inputs
from harness.master_research import MasterAccess
from harness.source_candidate import file_sha
from harness.source_replay import own_replay
from harness.research_protocol import CPU_ACTIONS


LIMITS=dict(gpu_seconds=28800,wall_seconds=28800,concurrent_gpus=2)
DEADLINES={'source-preflight':1200,'source-research':1800,'source-controller':7200}


def execution_plan(directory,source,resource_state):
    directory=Path(directory).resolve();source=Path(source).resolve()
    record=json.loads((directory/'request.json').read_text())
    deadline=DEADLINES[record['mode']]
    command=source_command(directory/'request.json',source,directory/'remote',directory.name,deadline)
    return dict(name=directory.name,mode=record['mode'],command=command,shell_command=shlex.join(command),
        source_sha256=file_sha(source),request_sha256=file_sha(directory/'request.json'),
        resource_state=str(Path(resource_state).resolve()),limits=LIMITS,deadline_seconds=deadline,
        nodes=1,total_gpus=2,gpu_type='H100',priority_class='higher-priority-job')


def validate_admission(plan,receipt):
    if not isinstance(receipt,dict) or set(receipt)!={'approved','plan'} or receipt['approved'] is not True or receipt['plan']!=plan:
        raise ValueError('trusted admission must bind the exact displayed execution plan')
    return plan


def submit_gate(directory,source,budget):
    record=json.loads((directory/'request.json').read_text())
    if record['mode']!='source-controller':raise ValueError('full gate adapter is controller-only')
    plan=execution_plan(directory,source,budget.path)
    save(directory/'admission-plan.json',plan)
    save(directory/'controller-execution-contract.json',dict(deadline_seconds=7200,
        science_protocol_unchanged=True,adapter=reference(__file__)))
    print(json.dumps(dict(event='AWAIT_TRUSTED_ADMISSION',plan=plan),ensure_ascii=False),flush=True)
    path=directory/'trusted-admission.json'
    while not path.exists():
        state=budget.read()
        if time.time()+30>=state['started']+state['wall_seconds']:
            raise RuntimeError('stage wall expired before controller admission')
        time.sleep(1)
    validate_admission(plan,json.loads(path.read_text()))
    if execution_plan(directory,source,budget.path)!=plan:raise ValueError('controller execution identity changed')
    return engine_execute(directory,source,budget,command_factory=source_command,
        feedback_loader=source_feedback,deadline=7200)


def interrupted_usage(root,depth=0):
    if depth>4:raise ValueError('bounded continuation ancestry exceeded')
    root=Path(root).resolve();metadata=root/'continuation.json'
    actual=dict(actions=0,cpu_runs=0,gpu_attempts=0,model_turns=0,usage_updates=0);roles_used={}
    budget_path=root/'resource-state.json'
    if metadata.exists():
        previous=json.loads(metadata.read_text()).get('prior_root')
        if previous is not None:
            actual,roles_used,budget_path=interrupted_usage(previous,depth+1)
    actual=dict(actual);roles_used={key:dict(value) for key,value in roles_used.items()}
    for directory in [root/'master',*sorted(root.glob('direction-*'))]:
        if not directory.is_dir():continue
        usage=dict(actions=0,cpu_runs=0)
        for path in sorted(directory.glob('tools-*/action-*/request.json')):
            action=json.loads(path.read_text())['arguments']['action']
            answer=json.loads(json.loads((path.parent/'response.json').read_text())['contentItems'][0]['text'])
            usage['actions']+=1
            usage['cpu_runs']+=action.get('kind') in CPU_ACTIONS and answer.get('reason')!='CPU run budget exhausted'
        wire=[json.loads(line)['message'] for line in (directory/'wire.jsonl').read_text().splitlines()]
        actual['model_turns']+=sum(row.get('method')=='turn/start' for row in wire)
        actual['usage_updates']+=sum(row.get('method')=='thread/tokenUsage/updated' for row in wire)
        cumulative=roles_used.setdefault(directory.name,dict(actions=0,cpu_runs=0))
        for key in usage:actual[key]+=usage[key];cumulative[key]+=usage[key]
    requests=sum(json.loads(path.read_text()).get('mode')=='source-research' for path in root.glob('*/request.json'))
    actual['gpu_attempts']+=requests;actual['actions']+=requests
    if actual!=json.loads((root/'result.json').read_text())['counters']:
        raise ValueError('continued counters differ from actual native evidence')
    return actual,roles_used,Path(budget_path)


class Context:
    job_prefix='sp-treeadapter-20261112-a01'

    def __init__(self,root,prior=None):
        self.root=Path(root).resolve()
        self.prior=None if prior is None else Path(prior).resolve()
        self.prior_counters={};self.prior_decision=None;self.prior_usage={}
        self.coverage_review=False
        budget_path=self.root/'resource-state.json'
        if self.prior is not None:
            stopped=json.loads((self.prior/'result.json').read_text())
            if (stopped.get('status')!='infrastructure_blocked' or stopped.get('error') not in
                    ('ValueError: one complete JSON response required','ValueError: Master must choose explore/controller/stop') or
                    not all(stopped['immutable_role_inputs']) or any(stopped['closed_role_processes'])):
                raise ValueError('only preserved protocol failures can be continued')
            self.prior_counters,self.prior_usage,budget_path=interrupted_usage(self.prior)
            self.coverage_review=stopped['error']=='ValueError: Master must choose explore/controller/stop'
            if not self.coverage_review:self.prior_decision=json.loads((self.prior/'master-decision-01.json').read_text())
        self.job_prefix='sp-'+self.root.name.replace('tree-adapter','treeadapter',1)
        self.budget=Budget(budget_path,limits=LIMITS)
        if any(not row.get('terminated') for row in self.budget.read()['jobs']):
            raise ValueError('reconcile active or uncertain jobs before continuing')
        if self.coverage_review:
            proof=json.loads((self.prior/'preflight-result.json').read_text())
            if proof.get('status')!='completed' or proof.get('preflight') is not True:
                raise ValueError('same-stage preflight reuse needs a passing actual receipt')
            matching=[row for row in self.budget.read()['jobs'] if row.get('uuid')==proof.get('uuid')]
            if len(matching)!=1 or matching[0].get('create_calls')!=1:
                raise ValueError('passing preflight has no unique actual resource reservation')
            original=self.prior/matching[0]['name']
            replay=source_feedback(original/'remote',json.loads((original/'request.json').read_text()))
            if any(proof.get(key)!=value for key,value in replay.items()):
                raise ValueError('same-stage preflight differs from independent replay')
            save(self.root/'preflight-result.json',proof)
            save(self.root/'preflight-reuse.json',dict(source=reference(self.prior/'preflight-result.json'),
                actual_job_uuid=proof['uuid'],same_stage=True,new_gpu_execution=False))
        previous=ROOT/'logs/direction-candidate-20261111-a02'
        review=verify_review(previous)
        prior=previous/'direction-tree16-selection/turn-01-response.json'
        proof=ROOT/'logs/acceptance-headroom-20261111-a01'
        for name in ('lattice-frozen-audit.json','mapping-frozen-audit.json','timing-frozen-audit.json','graph-context-full.json'):
            shutil.copy2(proof/name,self.root/name)
        freeze_inputs(self.root,ROOT)
        evidence=prepare_evidence(self.root,ROOT,prioritize_e2e=True,acceptance_headroom=True)
        verify_evidence(self.root)
        save(self.root/'authorized-evidence.json',evidence)
        self.packet=dict(scope='new real-stock adapter research; historical evidence explicitly reused, no final/sealed',
            evidence=evidence['initial'],previous_direction_report=dict(source=reference(prior),value=json.loads(prior.read_text())),
            previous_master_stop=review['master_decision'],resource_limits=LIMITS,
            capabilities=dict(source_option=True,new_files=False,max_source_edits=8,option_default=False,
                gpu_submission_allowed=False,preflight_required_before_source_execution=True),
            infrastructure_preflight=dict(status='not_yet_run',not_a_passing_receipt=True))
        self.rules=source_autonomy.COMMON.replace('GPU总上限16H100 GPU小时、墙钟12小时、并发2卡',
            'GPU总上限8H100 GPU小时、墙钟8小时、并发2卡')
        self.rules+='''\n本阶段目标是真实stock适配，不再以合成token或玩具状态契约代替实际引擎实现。
可自主search_stock、search_public/read_public和run_skill获取必要知识，先help核对字段，搜索也消耗CPU额度。
source-option-v1仍限8个既有Python源码edit，不扩大任意执行权限；需要超出范围时明确报告，不暗中绕过。
必须先写验收脚本，再写option.json，再成功run_python，最后输出run_source请求。
CPU只支持标准库；write_file才能写scratch，不能在CPU脚本中创建代码文件；本地模块导入不保证可用。
真实候选须有实际分支、真实词表ID、正确父状态与提交/回滚；输出路径命中证据的位置和可反驳条件。
只有真实已完成诊断才可交独立controller；正确性不过不解释性能，不读sealed，不称晋升。
'''
        self.master_brief='''\n本轮已获用户批准推进真实stock适配。你是Master，先评估最小范围、实现成本、潜在端到端收益、风险和停止条件。
上轮合成候选及报告是明确复用的历史信息，不是本轮产物；不必再做2700例玩具研究。
先核对是否存在可利用的真实父状态/树verify路径，再向Direction派发可实现、可证伪的最小适配任务。
由Direction自主决定代码和实验，不由维护者提供研究答案。不要仅因缺树适配器就原样重复上轮停止理由；
本轮就是评估和实现这个缺口，但若具体审查后改动范围/风险超出能力或收益不足，可以有依据停止或换方向。
unknown收益保持unknown，N16旧条件比不是新线上接受量，不拿线性block16当N16树。
为Direction留足读源码、写验收/实现、运行、失败修复额度。真实GPU请求经可信准入，预检按需触发，不事先浪费GPU。
独立dev gate由Master输出decision=controller和本阶段实际request_directory请求；不得延迟正确性到sealed。
'''
        if self.coverage_review:
            prior_role=self.prior/'direction-01'
            responses=sorted(prior_role.glob('turn-*-response.json'))
            last=json.loads(responses[-1].read_text())
            latest=sorted(self.prior.glob('sp-treeadapter-*-??/patch.json'))[-1]
            self.packet.update(current_failed_candidate=dict(source=reference(latest),patch=json.loads(latest.read_text()),
                direction_report=last,reuse_not_independent_discovery=True),
                coverage_review=dict(reason='User-approved implementation/correctness goal remains unfinished; stopping the faulty candidate is not a proof that no bounded repair or diagnostic exists.',
                    unmodified_gpu_rerun_forbidden=True,original_stop_preserved=True,same_authorized_stage=True))
            self.master_brief+='''\n这是一次明确标注的阶段目标覆盖复核，不是让你强行产生正收益。此前stop针对已失败补丁，目标尚未完成；剩余额度仍在同一8GPU小时阶段内，未重置。
先自主利用完整日志、原始paired输出、当前option与stock源码，评估有无低成本定位/差分或最小修复；不要只根据反馈尾部缺少某条日志就推断完整日志没有。
禁止直接重跑未修改的坏版本。若确有不可克服的范围/数值/工具障碍，给具体证据后可以stop，不要求用尽预算。
若延续原逻辑Direction，请在explore决定里加reuse_source="previous-direction-01"，其自身代码与反馈可原样恢复，必须注明复用；新分配是额外额度。
inputs/prior-runtime-feedback.json及其workspace_path提供该候选完整运行证据，不含其他方向私有推理。先做廉价诊断，再决定GPU，不预设维护者的修复答案。'''

    def session(self,directory,kind,packet,actions,runs):
        if kind=='Master':actions,runs=120,16
        previous=None
        reuse=kind=='Master' or not self.coverage_review or packet.get('assignment',{}).get('reuse_source')=='previous-direction-01'
        if self.prior is not None and reuse and (self.prior/directory.name/'manifest.json').exists():
            previous=self.prior/directory.name
            usage=self.prior_usage[directory.name]
            if kind=='Master' or not self.coverage_review:
                actions=max(0,actions-usage['actions']);runs=max(0,runs-usage['cpu_runs'])
            packet=dict(packet,logical_recovery=dict(provenance='same logical role own work, not a new discovery',
                own_previous_texts=[json.loads(path.read_text())['texts'] for path in sorted(previous.glob('turn-*-native.json'))],
                prior_counters=self.prior_counters,
                instruction=('本阶段坏补丁已停止；这是一次目标覆盖复核。旧运行是真实GPU证据，不能无修改重跑；先自主廉价定位，再决定继续或有依据停止。' if self.coverage_review else
                    '原生请求已完成但JSON根括号缺失，未提交GPU。自己的scratch由可信层从自身原生写回执恢复；先运行当前check.py，再重交完整JSON，不重复全部调研。')))
        role=roles.session(directory,kind,packet,actions,runs)
        if previous is not None:
            role['manifest']['own_replay']=own_replay(previous,Path(role['manifest']['work']))
            save(directory/'manifest.json',role['manifest'])
        if self.coverage_review:
            old_manifest=json.loads((self.prior/'direction-01/manifest.json').read_text())
            old_work=Path(old_manifest['work']);work=Path(role['manifest']['work'])
            shutil.copytree(old_work/'inputs/runtime-logs',work/'inputs/runtime-logs',dirs_exist_ok=True)
            shutil.copy2(old_work/'inputs/source-feedback-02.json',work/'inputs/prior-runtime-feedback.json')
        role['turn_timeout_seconds']=900
        role['broker_factory']=MasterAccess(kind,{'stock':self.root/'inputs/stock-profile.json'},
            self.root/'inputs/tools.json',self.root/'skill-cache',stock=autonomy.STOCK,
            baseline_loader=lambda:json.loads((self.root/'inputs/baseline.json').read_text())).factory()
        return role

    def freeze(self,directory):
        names=subprocess.check_output(['git','ls-files','agents','exp','harness','controller',
            'assets/upstream/dev','assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json'],cwd=ROOT,text=True).splitlines()
        names=sorted(set(names+['exp/tree_adapter.py','harness/source_replay.py']))
        previous=json.loads((self.root/'preexisting-dirty.json').read_text())['files']
        identity={};archive=directory/'source.tar'
        with tarfile.open(archive,'w') as destination:
            for name in names:
                if name in previous:
                    content=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
                else:content=(ROOT/name).read_bytes()
                import io
                import hashlib
                info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o644
                destination.addfile(info,io.BytesIO(content))
                identity[name]=hashlib.sha256(content).hexdigest()
        save(directory/'source-identity.json',dict(files=identity,archive_sha256=file_sha(archive),preexisting_dirty_excluded=True))
        return archive

    def submit(self,directory,source):
        plan=execution_plan(directory,source,self.budget.path)
        save(directory/'admission-plan.json',plan)
        print(json.dumps(dict(event='AWAIT_TRUSTED_ADMISSION',plan=plan),ensure_ascii=False),flush=True)
        path=directory/'trusted-admission.json'
        while not path.exists():
            state=self.budget.read()
            if time.time()+30>=state['started']+state['wall_seconds']:
                raise RuntimeError('stage wall expired while awaiting trusted admission; no submission')
            time.sleep(1)
        validate_admission(plan,json.loads(path.read_text()))
        if execution_plan(directory,source,self.budget.path)!=plan:
            raise ValueError('displayed source/request changed before submission')
        return engine_execute(directory,source,self.budget,command_factory=source_command,
            feedback_loader=source_feedback,deadline=plan['deadline_seconds'])

    def execute(self,directory,source,budget):
        if budget is not self.budget:raise ValueError('only this stage new resource budget is authorized')
        path=self.root/'preflight-result.json'
        if not path.exists() or json.loads(path.read_text()).get('preflight') is not True:
            number=len(list(self.root.glob(self.job_prefix+'-preflight*')))+1
            if number>2:raise ValueError('bounded preflight attempts exhausted')
            preflight=self.root/f'{self.job_prefix}-preflight{number:02d}';preflight.mkdir(mode=0o700)
            save(preflight/'request.json',dict(mode='source-preflight',source_pin=subprocess.check_output(
                ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),action=dict(per_suite=1,max_new_tokens=256)))
            proof=self.submit(preflight,self.freeze(preflight));save(path,proof)
            if proof.get('status')!='completed' or proof.get('preflight') is not True:
                return dict(status='failed',reason='actual source boundary preflight failed',preflight=proof,controller_accepted=False)
        return self.submit(directory,source)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--continue-from',type=Path)
    args=parser.parse_args();root=args.stage.resolve()
    if (root/'result.json').exists() or (root/'master').exists():
        raise ValueError('never overwrite or silently restart a research stage')
    context=Context(root,args.continue_from)
    sources=('exp/tree_adapter.py','exp/source_autonomy.py','exp/source_dev_gate.py','exp/gpu_autonomy.py','harness/source_replay.py')
    for name in sources:
        target=root/'runtime-source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    save(root/'manifest.json',dict(schema='real-tree-adapter-research-v1',limits=LIMITS,
        source_pin=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        launch_sources={name:reference(root/'runtime-source'/name) for name in sources},
        prior_private_context_shared=False,require_trusted_admission=True))
    save(root/'continuation.json',dict(prior_root=None if context.prior is None else str(context.prior),
        prior_counters=context.prior_counters,resource_state_path=str(context.budget.path),
        own_replay_only=True,budget_reset=False,prior_failure_preserved=True))
    closure={}
    try:
        with recorded_processes(root/'processes',closure):source_autonomy.run(root,context=context)
    finally:
        save(root/'process-closure.json',closure)


if __name__=='__main__':main()
