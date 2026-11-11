# Master自主源码提案与先行收益评估

## 授权与目标

用户批准执行：Master自主读stock源码、调研公开知识、获取profile/接受量与成本证据，
提出可落地的源码修改方案，再由Direction独立实现和实验、Master依据反馈修订或停止。
新增要求：每个方案执行前先评估潜在净性能收益，不能仅列热点或把kernel工作占比当墙钟占比。
工具调用成功、模板填满或无收益停止，不能自动记为源码提案科学目标达成。

新资源已确认：8 H100 GPU小时/12小时/最多并发2卡，失败、排队和冷启动计入；旧余额不结转。
镜像沿用已验证digest、WeaverDev/qiji、既有toleration/只读模型PVC和higher-priority-job。
已有长上下文专项由另一会话负责；本阶段不读其final产物、不修改其代码/预算或干预任务，
仅在其释放GPU后提交自己的任务。Ascend轨道独立，不接管。

阶段目录：`logs/master-proposal-20261111-a01/`。起点`6f31e9f`；现有dirty先记录SHA，
本阶段发布不得混入旧ceiling或并行长上下文改动。所有研究角色仅经受限入口/broker运行。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_proposal harness.test_research_knowledge \
  harness.test_acceptance_evidence harness.test_master_autonomy harness.test_master_autonomy_audit -v
$PY -B -m harness.master_autonomy_audit --root logs/master-proposal-20261111-a01
```

先写合成故障fixture再实现。应覆盖：空泛提案/假源码引用/跨角色证据/旧估计冒充当前测量、
工作量不匹配/只算接受量不算新增成本、未受控URL/重定向/私网/凭据外传、预算越界及伪造来源拒绝。
既有profile/source权限与独立controller判据保持不变；追加现有250项指定CPU回归。

## 每个源码提案必须给出

1. 模块、函数、源码SHA/原文引用，及已观察调用与静态推断之间的区别。
2. 明确机制变化、适用条件、独立option和默认关闭行为；不要求Master代写Direction代码。
3. 证据支撑的问题、预期减少的工作、新增开销、数值/状态/别名/缓存等风险。
4. 先行收益评估：同协议基线、实际tau及定义、每步成本和证据来源；估计范围/情景与假设。
   可计算tau_gain/step_cost_ratio或有依据的Amdahl情景，但不能把有限replay称理想oracle，
   不能把GPU kernel work当请求关键路径，也不能把未知成本填0。实测、模型、条件假设分开标注。
5. 正确性、路径命中、性能验证及证伪/停止计划。估计不足时先提出最小取证动作，而不是编造正收益。
6. 资料URL/版本/来源及复用声明；引用外部优化不算本系统独立发现，禁止读取作者final或sealed。

提案结构和来源绑定通过只表示工程可执行/可审计，不由字段检查器宣布科学合理。
真正的目标证据还须有Direction真实实现/反馈和Master复核；不保证找到正收益，不放宽晋升规则。

## 执行顺序

1. 冻结起点与新预算，先补通用知识/接受量/源码调研工具及提案验收，不代做科学选题。
2. 新Master自主调研、分析及申请观测，提交含净收益评估的源码级提案；可补证或诚实停止。
3. Direction仅获得自身提案和Master明确共享的资料，自主实现、验收脚本、实验和修复。
4. 有候选按原规则交独立dev验收；Master根据实际结果复核预估、调整或停止。
5. 只读复核原生谱系、资料与源码SHA、预算和进程退出；归档、更新主页/交接并审查后推送。

本阶段不开放sealed、不绕过资源入口、不要求完整ceiling、不把主助手工程修复记为科学发现。

## 用户指定的四项必查研究维度

Master必须逐项评估并说明证据、潜在净收益、未知项和优先级；不是固定派四个角色或各跑一次GPU。

1. verification_budget：静态验证长度/节点预算怎样选择，是否需要按请求或运行状态动态选择；
   同时考虑接受量与草稿/target验证成本，不预设长度越长越好。
2. verification_selection：哪些候选token/分支值得送验、怎样排序或剪枝；保持采样/接受规则及状态正确性，
   不把任务精度或少验证token冒充lossless。
3. kernel：在实际调用和形状证据下，哪些算子有足够成本与可实现优化空间；热点不自动等于低效。
4. end_to_end：CPU调度、同步、数据搬运、缓存、草稿/target衔接与重叠等整体潜力；
   防止局部微基准改善被新增开销抵消。

stock的block8只是对照身份，不是禁止研究验证预算/选择策略的科学限制。
现有执行模板不支持的配置须明确请求能力，不能绕过broker自行改启动参数，也不能把工具限制判成想法无效。

## 一次协议澄清接续

首个Master因来源字段反复错误而自主停止；三次公共检索不可用，不能伪称调研成功。
允许一次明确标注的逻辑Master接续：外部来源没有实际使用时可为空；BBuf属于基线证据，
不是外部检索。重放自身原生答复和拒绝原因，不替换科学机制、不强迫继续或产生正结果。
原答复、停止、进程退出及预算快照保持可校验；新原生会话不冒充原线程恢复，
动作/CPU/GPU及墙钟均沿用原阶段累计值，原Master剩余动作和CPU额度不重置。

先行验收：
```bash
python -B -m unittest harness.test_master_recovery harness.test_master_autonomy \
  harness.test_master_proposal harness.test_profile_autonomy_audit harness.test_skill_rsi_continue -v
```
覆盖重复接续、非提案阶段恢复、原始快照篡改、预算/计数重置拒绝及旧新进程退出合并。
协议澄清不是Master自主发现，最终审计须同时复核两个会话；若再次自主停止则如实收口。

收尾补验：`python -B -m unittest harness.test_research_shutdown -v`。
旧新原生会话由不同可信父进程启动，不能拼成同一controller shutdown registry。
未来分父进程保存registry；本次已发生的registry构建失败不重跑科学研究，保存原失败，
仅由维护者事后逐项核对原始birth/exit、原生角色、预算时间和实际进程消失。
事后复核明确不是Phase4打开前的可信关闭许可，不据此打开sealed或宣称T3通过。

## 实际结果（2026-11-11，UTC+08）

- Master先读当前stock接受计数、BBuf和源码，四维逐项评估；预算/送验策略因证据不足defer，
  kernel与端到端先diagnose，没有凭空填写收益区间。三个公共检索回执均unavailable，不能称调研成功。
- 首Master来源字段失败并stop；一次明确的协议澄清接续只重放自身上下文，保留原36动作/14CPU/4回合，
  新原生会话不算新的独立发现。修正说明允许external_sources为空，不删除原失败或替模型改科学方案。
- 接续Master自主提出`_dflash_accept_bonus_contig_kernel`首错位置向量min归约诊断；Direction独立实现
  默认关闭option、自写CPU验收并通过5924例。CPU只是标准库语义模型，不认证Triton/GPU数值或性能。
- 真实诊断：每suite1题、5请求、两轮fresh与换卡、cap256，共10pair；candidate/stock几何均值
  **0.9956361157×，95% CI [0.9932511881,0.9980267699]**，五suite均低于1。
  独立复核10对输出ID相同、每臂2560 token；未做token forcing，不声称lossless或退化原因已确定。
- Direction据实际反馈自主stop；Master不选择dev gate。Integration无共享候选而停止；Kernel自主读取
  delta-rule源码、申请一次stock profile并调用BBuf，因形状/调用路径及墙钟成本仍未知停止，没有实现kernel候选。
- Master最终stop并复核原估计：原先unquantified，无数值预测可校准，实测不支持净收益。不会为了用完预算重跑。
- 三任务分别为预检`job-8cc12cccfd1f-20261111130505`（568 GPU秒）、Direction
  `job-71d432512769-20261111134004`（2256 GPU秒）、Kernel观测
  `job-25d13ec7a676-20261111140142`（621 GPU秒），均Completed/exit0；合计3445 GPU秒
  （0.956944 GPU小时），峰值2卡、0活动GPU，显式higher-priority-job。主进程收尾exit1与GPU任务exit0分别记录。
- 5原生科学会话（包含一次逻辑Master接续）、15回合、78动作（76工具/1源码/1profile）、24CPU额度、7次BBuf。
  初步独立audit已完整重算来源、配对统计、预算和反馈；退出使用明确标注的事后观察，不能用于sealed预打开。

**完成：**具体源码提案→Direction自主实验/修复→Master依据实际反馈决策的链路。
**未完成：**有净收益的方案、量化收益预测能力的实测校准、独立dev候选验收、真实补丁整合/kernel优化、
正常final T3、sealed晋升、多轮RSI及论文数字复现。原始证据只留私有logs，公开发布只含通用代码和摘要。

工程验收：91项先行检查、371项最终指定联合CPU回归通过；不是仓库全量、GPU正确性或科学晋升通过。
独立audit02/03字节一致；排除旧dirty和并行专项的待发布源码副本371项同样通过。
3555个host可见证据文件已双次SHA核对，角色自身28个非凭据输入/脚本/元数据文件另持久保存；
清单`logs/master-proposal-evidence-20261111-a01.sha256`，SHA256为
`dd5ec7c6d69d57c7c3ed1fa7fac205a06576d806fed67bf629476fb29551ad11`。
公开源码按白名单和共享文档分段暂存；不带旧ceiling、并行前缀专项、原始日志、模型、sealed或凭据。
Git提交/推送最终身份由独立publication回执记录，不把main收尾exit1改写成正常exit0。
本轮不再提交任务。后续仅提案补足实际路径/形状和无profiler墙钟成本，再由Master自主选择；
需要用户批准新阶段及资源，不结转本阶段剩余额度，也不将本次停止解释成四类优化均无潜力。
