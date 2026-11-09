# 真实 stock 引擎自主探索（2026-11-09）

## 批准范围与目标

用户批准本阶段自主执行：最多并发8张H100、累计64 GPU小时（230400 GPU秒）、最长24小时。
失败、冷启动及未能确认终态的任务均占用预算；上限不是必须消耗的目标。
沿用已确认镜像digest `6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`、
WeaverDev、qiji namespace/请求queue、既有toleration及只读模型PVC。

本阶段将上一阶段合成注意力微实验推进到真实27B stock部署研究。
Master选方向与预算，direction自主设计实验、分析和修复；主助手只维护可信通用工具及审计。
允许无候选、负结果和主动停止，不以用完预算或找到正收益作为验收条件。

## 先写验收，再实现

1. `python -B -m unittest harness.test_engine_research`：请求拒绝、默认stock、身份绑定、预算预留与不确定任务不退款。
2. `python -B -m unittest discover -s harness -p 'test_p*.py'`：沿用已有CPU回归范围；新测试另列。
3. `python -B exp/engine_autonomy.py --help`、`python -B exp/engine_research.py --help`：新入口可执行。
4. 真实角色原生回包→结构化请求→冻结代码/请求→唯一NorthJob任务→原始配对输出→direction反馈→Master决策可追溯。
5. 每次提交均查重、展示完整命令/总GPU、只create一次、核对code200及UUID；提交、启动、实验完成分开。
6. 若执行真实诊断，须同请求、fresh server、两轮换卡、默认关闭option=stock；只报告开发诊断，不能宣称lossless/晋升。
7. 有候选才调用不改动的controller独立dev验收；没有完整证据就保留未验收状态。
8. 收尾核对任务/角色终态、实际/保守GPU用量、保护目录零改动；新证据SHA清单，公开审查后更新主页并提交推送。

## 能力边界

第一条真实研究通路仅开放已有startup-candidate-v1的draft_tokens整数option（1..64，关闭=8）。
不执行agent任意shell或源码overlay；agent自己的分析代码仅在已有隔离CPU入口运行。
这不是预定研究结论：Master可以选择不用该能力、要求补工具或停止；不能把参数调优称为新算法发现。
只提供授权stock证据与公开dev题，不读作者final或sealed，不改controller、eval、账本、可信记忆或stock原树。
旧微实验仅为带来源的共享证据，不算本阶段新发现。

## 开始时的checkpoint（历史）

- 已核对HEAD `8bd6029`，旧阶段不重跑；本阶段未提交GPU、无新UUID。
- 最小真实引擎研究动作、冻结身份、持久资源预留及独立dev gate适配器已实现；303既有CPU回归+10新测试通过。
- 新测试包括真实本地HTTP两轮配对及6类篡改拒绝；默认option关闭=stock沿用既有candidate验收。
- 曾用过宽`test_*.py` discovery触发已有手工GPU脚本的torch导入错误；未启动GPU、未改旧脚本，
  改回上一阶段既定CPU范围`test_p*.py`后303通过，新10项另跑，不隐瞒该范围差异。
- 研究即将启动；有实际候选才由Master申请固定30题/2048/null前后/FP32-head独立dev gate。
- 完整Phase1、integration/kernel、sealed、多轮RSI及论文数字均未完成。

## 运行中checkpoint：指标语义修复

- Master自主选择draft_tokens权衡，分配32动作/4CPU/4GPU尝试；direction自行决定先测4，再测2，均15题/2048/两轮fresh换卡。
- 首任务`job-5470e6c4c91b-20261109213605`，code200、Completed/exit0，30pair；吞吐比candidate/stock为
  0.705274 [0.668057,0.744147]。这是吞吐下降，不能按耗时比反向解释为提升；尚无正确性/晋升结论。
- direction旧第二回包把该比值称作延迟比。可信反馈缺少明确metric definition，属于工具契约缺口；
  未接受该结论，也未进入controller。暂停主循环后两角色exit0、输入/canary未变，旧回包原样保留。
- 第二任务`job-314848e56ac2-20261109215036`暂停前已确认提交并运行；仅恢复监控，不create重提，允许其完整产出原协议数据。
- 新反馈显式声明candidate tok/s / stock tok/s、越大越好、不是延迟比；不改原数字、协议或判据。
  12项新CPU测试通过，包括指标方向与恢复不得重复create；后续由direction自行重新解释自身旧结果。
- 原64GPU小时/24小时/8卡上限及起算点不重置，旧失误不冒充新发现；主助手不替direction决定下一个科学设置。

## 恢复后的自主研究

- `logs/engine-autonomy-run-20261109-d02/`恢复逻辑角色（新原生thread，不是新发现）；继续使用d01的同一资源状态及原起算点。
- Master自行撤回旧收益解释，direction阅读stock源码、写分析及预设停止条件，自行选择12，不由主助手指定。
- 15题真实诊断：1.096513 [1.058947,1.138512]；随后direction固定12扩至30题：
  1.080950 [1.056399,1.106541]，均为candidate/stock吞吐比，两个诊断样本重叠，不当独立验证。
- direction自行编写并运行CPU分析，新增15题为1.07085，其中12题点估计改善；新增mt-bench仅1.00495，
  明确不能宣称普遍获益。它主动停止调参，将12作为待验收候选，未用完分配尝试。
- Master自主请求固定dev gate，任务`job-2366dc731891-20261109224327`已核对code200/UUID并启动。
  controller、验收规则和数据不变；`final`仅是既有schema的候选槽位，此处装agent的stock启动option，不读作者final实现。
- GPU代码每请求冻结；主循环实际执行源以d01首请求、d02首请求的归档为准。
  后续恢复保护/独立审计的本机加固不追溯声称已在运行中的主循环加载；原始计时runner与请求判据未变。

## 12候选dev联合验收与后续自主选择

- 原controller结果：1.085260 [1.062888,1.109728]（suite-stratified request-cluster bootstrap）；
  前后null噪声0.00289225，输出与stock一致，joint_acceptance_passed=true，promoted/ledger_eligible=false。
- 收尾适配器直接比较Python tuple与JSON list曾误报不一致。补JSON规范化后独立重放原判据通过，
  数字变化仍被测试拒绝；不修改controller，不重交GPU。旧失败result/日志原样保留。
- d03在同预算下恢复逻辑角色。Master自主决定继续，direction用标准库CPU复核旧配置及范围后选择16，
  30题诊断1.074331 [1.043098,1.108494]；随后选择10以补查8与12之间的权衡，没有宣称12显著优于16。
- 各run实际host入口版本以其首请求归档为准；后续多次恢复计数加固仅影响未来加载的入口。
  旧producer记录的是恢复窗口内所有完成回包（含gate），最终独立审计另从全谱系原始证据计算诊断数；
  新代码已按全谱系且排除gate修复，测试覆盖预算不重置及历史反馈不丢失。

## 最终结果（2026-11-10北京时间）

direction主动停止扫参、不使用剩余尝试；Master选择10的收益/退化权衡做独立验收，随后也主动stop。
主助手只修通用指标契约、JSON表示与恢复计数，不代写研究代码、不替角色选10/12/16或修正其研究结论。

| 用途 | option | 题数 | 吞吐比 / 95% CI | NorthJob UUID |
|---|---:|---:|---|---|
| dev诊断 | 4 | 15 | 0.705274 [0.668057,0.744147] | job-5470e6c4c91b-20261109213605 |
| dev诊断 | 2 | 15 | 0.412751 [0.381947,0.445764] | job-314848e56ac2-20261109215036 |
| dev诊断 | 12 | 15 | 1.096513 [1.058947,1.138512] | job-6055d2818e12-20261109221414 |
| dev扩展 | 12 | 30 | 1.080950 [1.056399,1.106541] | job-cdbd42b44760-20261109222812 |
| 独立dev gate | 12 | 30 | 1.085260 [1.062888,1.109728] | job-2366dc731891-20261109224327 |
| dev诊断 | 16 | 30 | 1.074331 [1.043098,1.108494] | job-a70a805eb03e-20261109234109 |
| dev诊断 | 10 | 30 | 1.065215 [1.046724,1.083983] | job-c21d9c4974ae-20261109235701 |
| 独立dev gate | 10 | 30 | 1.063766 [1.046362,1.082538] | job-1c73aef8db5d-20261110001129 |

全部比较默认8，同请求、2048上限、自然EOS、两轮fresh换卡；所有任务均code200、实际启动、Completed/exit0，三种状态分别存证。
诊断CI为pooled request-cluster bootstrap；两个gate用原controller的suite-stratified request-cluster bootstrap，不能混为同一判据。
两个gate均前后null、真实测速输出forcing及正确性契约通过，测速输出与stock一致；噪声分别0.00289225与0.0007445165。
结果只属dev，不能证明数学losslessness、最优长度、配置间显著优劣或对新数据泛化。

### 验收、资源和来源

- 303既有CPU回归+18新增测试通过；两次全谱系独立审计一致，6类工程证据篡改均拒绝，原始文件未修改。
- 实际14原生回合/30工具动作/5隔离CPU运行/6GPU诊断，另2独立gate；5份CPU脚本及输出均绑定原生工具流。
  44usage事件不是精确后台API或token账单。
- 630计时pair只覆盖30个独立公开dev请求；跨配置、物理轮次及已有15题重用均不当新样本。
- 8任务在集群独立复核均Completed、容器exit0；6研究角色exit0，输入/canary未变。
  观察到每任务1个Pod、restart0，不据此声称集群绝不会重试；实际queue记录为proj-31，namespace仍qiji。
- 保守22730 GPU秒（6.313889 GPU小时），峰值2卡；原64 GPU小时/24小时/8卡上限未超，无未知任务或自动追加预算。
- 机器结果：`logs/engine-autonomy-closeout-20261109-d01/stage-result.json`；
  独立审计`independent-audit-{1,2}.json`，资源复核`cluster-recheck.json`，工程故障注入`tamper-checks.json`。
- d01/d02旧失败result不覆盖；最终结果以完整证据重放为准。旧producer的恢复窗口计数与新全谱系计数明确分开，
  controller的原判据和原数字不变。实际host入口版本以各run首请求归档为准，不把后续源文件当作运行中已热加载。

**本阶段达成：真实stock参数探索及独立dev裁判通路。**
这不是算法/源码新发现，没有sealed、账本、晋升、可信记忆或完整Phase1/多轮RSI，论文sealed的2.13×也未独立复现。
下一阶段先提案受限源码option执行通路获批；本阶段预算停止，不自动结转，不自动进入integration/kernel、sealed或DSH。

### 归档与公开同步

新归档清单`logs/engine-autonomy-evidence-20261109-d01.sha256`：25836文件、523390549字节，
清单SHA256=`9fd4dbc77a1a5e97fb831c25a7f852458171437ba0c498ebfe911363e84ee85f`。
原始产物、角色上下文与生成脚本仅保留忽略的logs，不入公开Git；旧第三阶段126文件归档复核通过。
最终代码快照、来源身份及两次独立重放均在closeout；发布审查/二次全SHA与Git同步回执单列
`logs/engine-autonomy-publication-20261109-d01/`，不改已归档文件或制造自引用清单。
公开只同步通用实现、测试、脱敏状态和证据索引；不是全仓库历史或许可证安全保证。
