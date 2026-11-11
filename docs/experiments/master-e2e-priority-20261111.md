# Master端到端收益优先级评估

## 授权与目标

用户批准：先定位真实开销，评估候选的端到端潜在净收益，再决定最值得研究的方向。
纠正上一轮优先选择容易CPU验证的机制而未证明收益空间的问题；logits融合只作备选，不直接实现。
研究由Master自主完成，必要时派Direction做收益诊断；维护者只提供通用工具和忠实的授权stock元数据。
不新增GPU、不改引擎/裁判/规则/账本、不读作者final/sealed、不建立正式记忆，不接管Ascend。

## 先行流程与验收

1. 冻结旧dirty；把已有stock的target/draft配置、启动参数及10条普通请求计时按白名单提供给Master。
   原始来源SHA可复核，不开放prompt/token IDs、其他角色私有推理、candidate实现或作者final。
   配置不是运行路径认证；256cap普通计时与另一份profile请求分组，禁止混用分母。
2. 复用已有Campaign，新增端到端优先级任务模式。Master自主读源码、profile/BBuf、公开知识，
   分析关键路径暴露耗时，而非把累计kernel work当整请求占比；不以完整ceiling为前置。
3. 比较至少3个机会、覆盖四维。每项给出来源、可减少的工作、理想上限/现实范围/新增成本、
   不确定性、最小取证成本及优先级。证据不足时给条件区间/盈亏阈值和补采清单，不编造实测f或收益。
4. 允许Master自己做隔离CPU估算，或派Direction做收益诊断；没有收益依据不推进实现。
   若关键数据只能GPU取得，返回最小元数据/分时请求，不提交任务，不重复穷举归约语义凑成果。
5. 原生来源/科学引用/脚本与输出/反馈/预算/退出独立审计；明确是否真正排出了可信优先级，
   不把格式完整或条件模型当已测提速。定向与公开副本复验、SHA归档、主页/交接和审查后同步。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_e2e_context harness.test_master_decisions harness.test_research_knowledge
$PY -B -m exp.master_decisions --prioritize-e2e --stage logs/master-e2e-priority-20261111-a01
$PY -B -m harness.master_decisions_audit --root logs/master-e2e-priority-20261111-a01
```

CPU保护上限沿用30分钟/16原生回合/240动作/32CPU额度/最多2方向；Master96动作/16CPU，
单次方向分配最多64动作/8CPU，续派不清零。实际GPU授权0，不自动结转旧余额。

## 结果：完成收益诊断，尚未找到可信优化赢家

原Master在约313秒后stop：1次真实CPU收益模型、4个机会（覆盖四维），没有派Direction或实现。
随后发现通用工具help未列出list_skills/run_skill/read_profile_shapes，导致Master猜错接口；这是
维护者工具说明缺口，不作为方案无效的证据。补充help准确schema与授权evidence ID，保留原能力边界。
同时修正提示里不存在的独立runtime-metadata路径：已分享数据实际在自身inputs/evidence.json中。

原停止和原生轨迹不改。维护者安排**原Master逻辑接续的一次接口澄清复核**，新原生会话只重放自身
旧答复/CPU结果和已授权stock证据，不冒充模型自主续轮或新独立发现。仅使用原Master剩余64动作/2CPU，
不重置预算。复核自主调用一次BBuf profiler并维持stop；没有强迫正结果或由维护者代做归因。

两会话合计4原生回合、37动作、15CPU额度、23次usage更新；原Master96动作/16CPU上限未突破。
从原研究起点到复核结束约1189.6秒，仍在30分钟保护上限；1次CPU脚本执行、1次BBuf、0GPU、0Direction。
4个初始化/角色进程分父registry记录并均exit0；不是拼接为controller Phase4预打开许可。

## Master给出的量化边界

| 机会 | 已核对的计算与局限 | 决策 |
|---|---|---|
| 验证长度 | 草稿上限7→6（总块宽8→7），在候选前缀不变/每步bonus假设下，完整step成本须下降超过7.2941%才改善长解码段；前缀不变未证明 | diagnose，不能据旧直方图直接选择新宽度 |
| 更好送验选择 | 单请求425/81推进量下，固定step成本/忽略prefill及尾部的理想进度比为648/425=1.524706；不是现实预测或正式ceiling | diagnose，需真实进度与新增完整成本 |
| LM-head物化 | 假设未分片BF16 dense head，H=5120、V=248320，权重2542796800字节；8行示例logits3973120字节，一次写+读7946240字节；8行不是已认证实际形状 | diagnose，不能把省logits说成省权重或投影FLOP，端到端f未知 |
| accept前缀归约 | 仅复用旧0.995636× [0.993251,0.998027]诊断，不支持原候选正收益 | defer，不外推到其他机制 |

CPU还计算了显式假设的Amdahl情景，未将假设f写成实测占比。所有现实端到端收益范围仍unknown。
同工作量正常耗时的prefill/step拆分、实际路径/消费者、重叠及暴露份额不足，前三项**无法按可信净收益
排出先后**。Master把“信息获取优先级”与“优化优先级”分开，没有因CPU容易验证而推进logits融合。

## BBuf复核改变了什么

复核读取原stock trace，90047个kernel，累计work2324231.204us、busy union1968115.977us、
span2170693.737us。最大累计work的GEMM为nvjet_sm90_tst_384x8_64x4_4x1_v_bz_TNT，约700161.864us。
这些数字从授权原trace独立重算一致，**都不是整请求可消除的关键路径时间**。

Master据此把下一步取证重点收敛到：先确认高累计work GEMM对应的真实模块/dtype/消费者/graph形状，
再关联同工作量的逐步推进量、prefill、完整step和阶段时间。工具报告的FP8/shared-expert等标签没有
独立路径认证，不予照搬；all/extend标签也不当DFlash draft/verify分解。没有形成优化赢家或新的收益上限。

## 工程验收与证据边界

- 265项指定CPU回归通过，非仓库全量。配置/普通计时导出校验完整启动参数（包括被脱敏的模型路径），
  再白名单输出；不同模型身份不能因路径脱敏而被混算。正常stock行与profile不共用分母。
- 原研究七份源码在启动前SHA封存；帮助说明/路径提示、审计工具锁布局和模型身份校验在停止后修复。
  原进程没有热加载；澄清复核另封存七份实际源码版本，保留两个版本和修复来源。
- CPU入口新增规范的root/tools.json审计副本；本次工具锁/缓存按逐文件SHA复制给既有独立审计器，
  原运行缓存和原生回执不改。复制不是重新运行BBuf，也不算新增测量。
- combined-audit04/05两次独立重放一致，核对原生来源、只复用自己上下文、37/15/4累计预算、截止时间、
  两套进程退出、真实工具结果、CPU算术和原trace统计。不能从审计通过自动认证研究判断正确。
- 首次schema来源引用错误由原Master自行重交，拒绝/重交均保留；接口失败不伪装为实际技能调用成功。
- 11份角色自身inputs/scratch/config/canary持久化，不复制auth/整个home。原生绝对路径保持，若/tmp清理
  需按归档显式恢复。TTY6160及94541均已退出，不重启旧角色或复核脚本。

## 下一步与未完成项

本轮完成了条件收益/成本核算和取证重点收敛，**未完成“确认当前最值得优化方向”的科学目标**。
不应直接实现logits融合，也不应把高累计work GEMM宣布为低效或最高收益方向。
下一步应由Master/Direction明确最小同工作量路径归因与暴露时间诊断请求，优先复用已有trace可关联
的信息，确需GPU补采时再确认预算/镜像/统一broker准入。配置、prompt/token IDs和sealed边界保持。
不新增GPU、不继承旧额度、不改controller/规则/账本，不将条件模型写入可信memory或论文数字复现。

## 封存与发布

265项指定CPU回归在工作区及排除旧dirty的公开源码副本均通过；44份其他旧dirty保持原SHA。
本阶段只发布11份源码/测试/摘要，不发布原始trace、角色轨迹、配置、普通请求原始响应或鉴权。
213文件/31296120字节双次全SHA封存；索引`logs/master-e2e-priority-20261111-a01.sha256`，
SHA-256为`dce059b6310136ac506320728ce3516029c2ea2e608e64d09189e137bfb3f685`。
封存目录不再写入；最后提交/远端身份记录在独立的`logs/master-e2e-priority-20261111-a01-publication.json`。
以发布回执确认同步，不将工程收尾或Git提交写成科学目标已达成。
