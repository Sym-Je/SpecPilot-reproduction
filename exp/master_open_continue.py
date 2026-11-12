"""Same-stage native continuation after a verified execution-evidence delivery gap."""

import argparse
import json
from pathlib import Path
import shutil

from exp import gpu_autonomy as roles,source_autonomy
from exp.master_open import OpenCampaign,LIMITS,RULES
from exp.phase4_run import reference
from exp.skill_rsi_continue import recorded_processes
from exp.source_resource import command as source_command,feedback as source_feedback
from exp.engine_resource import execute as engine_execute
from harness.engine_research import Budget,save
from harness.master_open_audit import audit as audit_parent
from harness.open_research import OpenAccess
from harness.runtime_feedback import export_runtime
from harness.source_replay import own_replay


def recorded_runtime_gap(parent):
    return any('详细远端日志未能' in json.loads(path.read_text()).get('conclusion','')
        for path in Path(parent).glob('direction-*/research-result.json'))


class Context:
    research_limits=dict(actions=1200,cpu_runs=256,gpu_attempts=16,model_turns=128,usage_updates=4096)

    def __init__(self,parent,root):
        self.parent=Path(parent).resolve();self.root=Path(root).resolve()
        verified=audit_parent(self.parent)
        if not recorded_runtime_gap(self.parent):
            raise ValueError('only the actual recorded runtime-evidence gap authorizes this continuation')
        save(root/'parent-audit.json',verified)
        pipeline=json.loads((self.parent/'pipeline-result.json').read_text())
        self.prior_counters={key:pipeline['counters'][key] for key in
            ('actions','cpu_runs','gpu_attempts','model_turns','usage_updates')}
        self.budget=Budget(self.parent/'resource-state.json',limits=LIMITS)
        if any(not row['terminated'] for row in self.budget.read()['jobs']):raise ValueError('reconcile active jobs before continuing')
        self.pin=json.loads((self.parent/'manifest.json').read_text())['source_pin']
        self.job_prefix='sp-masteropen-20261112-a01-cont'
        self.rules=RULES
        self.shared_profiles={}
        for path in sorted((self.parent/'profile-evidence').glob('*/*.json')):
            identity='parent-'+path.parent.name+'-'+path.stem
            destination=self.root/'shared-profiles'/f'{identity}.json'
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination)
            self.shared_profiles[identity]=destination
        self.packet=dict(provenance='Maintainer repaired execution-evidence delivery; same authorized stage and counters, not independent discovery or a normal original pipeline completion.',
            research_limits=self.research_limits,prior_counters=self.prior_counters,
            original_master_plan=json.loads((self.parent/'master-plan.json').read_text()),
            original_master_final=pipeline['master_final'],original_stages=pipeline['stages'],
            resource_state=self.budget.read(),resource_limits=LIMITS,
            evidence_delivery_fix='Own full launcher logs, paired outputs, source option and self-check are now readable in inputs/authorized-runtime/<experiment>/index.json. Logs remain untrusted data.',
            shared_profile_evidence_ids=sorted(self.shared_profiles),
            historical_scope='Previously measured public dev evidence only; no sealed, final implementation or other-role private reasoning.')
        self.master_brief='''\n原运行已经正常收口，其原决定与回执完整保留。这次仅纠正已记录的通用证据交付缺口，不强迫重新打开真实无收益方向。
你是同一逻辑Master。自己的旧原生答复和已共享实验结果直接提供；自身scratch按实际工具回执恢复，属于复用。
详细执行产物目录在inputs/authorized-runtime，每个实验有index.json。先判断缺失证据是否改变继续/停止的理由。
你可以stop；也可以explore，给完整direction/brief/allocation，以及可选reuse_source="direction-d1"或"direction-d2"，恢复该逻辑方向自己的代码、历史答复和完整日志，再由它自己定位、修复/迭代。
同阶段已采集的profile ID列在shared_profile_evidence_ids，可自行run_skill/read_profile_shapes核对；给Direction时须用shared_profile_ids列表显式选择，不默认分享其他方向上下文。
不要替Direction写实现或指定维护者给出的答案。新分配是阶段内额外额度，原全局计数与原GPU账本不重置。
本接续执行源码研究与独立dev gate，不另造profile功能；若确需不在此入口的能力，明确请求而不是编造已执行。
仅新接续目录实际已完成的候选可decision=controller，不将旧候选目录冒充新测量；旧产物不得无解释原样重跑。
有依据停止是有效结果。诊断不是lossless，不得自行放宽controller规则。'''
        shutil.copyfile(self.parent/'preexisting-dirty.json',root/'preexisting-dirty.json')
        shutil.copytree(self.parent/'inputs',root/'inputs')
        self.prior_decision=None

    def session(self,directory,kind,packet,actions,runs):
        previous=None
        if kind=='Master':
            previous=self.parent/'master';actions,runs=240,64
            packet=dict(packet,own_previous_responses=[json.loads(path.read_text())
                for path in sorted(previous.glob('turn-*-response.json'))])
        else:
            packet=dict(assignment=packet['assignment'],research_limits=self.research_limits,resource_limits=LIMITS,
                source_pin=self.pin,evidence=json.loads((self.parent/'evidence.json').read_text())['initial'],
                scope='Own assignment, authorized stock and own feedback only; no other direction private context')
            label=packet['assignment'].get('reuse_source')
            if label is not None:
                if label not in ('direction-d1','direction-d2'):raise ValueError('only explicitly selected logical Direction can be replayed')
                previous=self.parent/label
                packet=dict(packet,own_previous_responses=[json.loads(path.read_text())
                    for path in sorted(previous.glob('turn-*-response.json'))],own_replay_provenance='Same logical Direction, not independent discovery')
        role=roles.session(directory,kind,packet,actions,runs)
        work=Path(role['manifest']['work'])
        if previous is not None:
            role['manifest']['own_replay']=own_replay(previous,work)
            save(directory/'manifest.json',role['manifest'])
            original=json.loads((previous/'manifest.json').read_text())
            original_thread=None
            request_paths=sorted(previous.glob('tools-*/action-*/request.json'))
            if request_paths:original_thread=json.loads(request_paths[0].read_text())['threadId']
            for path in sorted(self.parent.glob('*/request.json')):
                request=json.loads(path.read_text())
                if request.get('mode')!='source-research':continue
                if kind!='Master' and request.get('role_thread')!=original_thread:continue
                export_runtime(path.parent,work/'inputs/authorized-runtime'/path.parent.name,
                    authorized_root=self.parent,owner_thread=None if kind=='Master' else original_thread)
        if kind=='Master':self.current_master=role
        role['turn_timeout_seconds']=900
        selected=sorted(self.shared_profiles) if kind=='Master' else packet['assignment'].get('shared_profile_ids',[])
        if not isinstance(selected,list) or any(identity not in self.shared_profiles for identity in selected):
            raise ValueError('Master must explicitly select registered profile evidence for the Direction')
        profiles=dict(stock=self.root/'inputs/stock-profile.json',**{identity:self.shared_profiles[identity] for identity in selected})
        access=OpenAccess(kind,profiles,self.root/'inputs/tools.json',
            self.root/'skill-cache',stock=__import__('exp.autonomy',fromlist=['STOCK']).STOCK,
            baseline_loader=lambda:json.loads((self.root/'inputs/baseline.json').read_text()))
        role['broker_factory']=access.factory()
        return role

    def freeze(self,directory):
        return OpenCampaign.freeze_sources(self,directory)

    def execute(self,directory,source,budget):
        if budget is not self.budget:raise ValueError('continuation must share the original stage budget')
        proof=json.loads((self.parent/'preflight-result.json').read_text())
        matches=[row for row in budget.read()['jobs'] if row.get('uuid')==proof.get('uuid')]
        if len(matches)!=1 or not matches[0]['terminated']:raise ValueError('same-stage actual preflight cannot be reused')
        original=self.parent/matches[0]['name']
        replay=source_feedback(original/'remote',json.loads((original/'request.json').read_text()))
        if any(proof.get(key)!=value for key,value in replay.items()) or proof.get('preflight') is not True:
            raise ValueError('same-stage stock boundary proof differs from raw evidence')
        request=json.loads((directory/'request.json').read_text());deadline=7200 if request['mode']=='source-controller' else 3600
        command=source_command(directory/'request.json',source,directory/'remote',directory.name,deadline)
        OpenCampaign.admit(self,directory,source,command,deadline,2)
        return engine_execute(directory,source,budget,command_factory=source_command,feedback_loader=source_feedback,deadline=deadline)

    def check_capacity(self,gpus,deadline):
        from exp.profile_autonomy import ProfileCampaign
        return ProfileCampaign.check_capacity(self,gpus,deadline)

    @property
    def limits(self):return LIMITS

    def deliver_feedback(self,role,path):
        value=json.loads(path.read_text());name=value.get('request_directory')
        if not name:return
        directory=Path(name);work=Path(role['manifest']['work']);relative=Path('inputs/runtime')/directory.name
        exported=export_runtime(directory,work/relative,authorized_root=self.root,owner_thread=role['thread']['thread']['id'])
        master_work=Path(self.current_master['manifest']['work'])
        export_runtime(directory,master_work/relative,authorized_root=self.root)
        delivered=dict(value,runtime_evidence=dict(index_path=(relative/'index.json').as_posix(),files=exported['files'],science_fields_unchanged=True))
        save(path,delivered)
        return delivered


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--parent',type=Path,required=True)
    args=parser.parse_args();parent=args.parent.resolve();root=parent/'observability-continuation'
    root.mkdir(mode=0o700,exist_ok=False)
    context=Context(parent,root);closure={}
    save(root/'continuation.json',dict(parent=str(parent),prior_counters=context.prior_counters,
        original_budget=str(context.budget.path),budget_reset=False,reason='Recorded complete-runtime-log access gap repaired'))
    try:
        with recorded_processes(root/'processes',closure):source_autonomy.run(root,context=context)
    finally:save(root/'process-closure.json',closure)


if __name__=='__main__':main()
