# SpecPilot 复现工程

复现 *SpecPilot: Autonomous Algorithm Discovery and Systems Optimization for Speculative
Decoding*（arXiv:2611.02501v1）的**自主优化闭环**，并独立验证性能；架构复现与数字复现分开报告。论文原件见
`docs/` 中的引用；PDF 不在仓库内。

GitHub：[china-qijizhifeng/SpecPilot-reproduction](https://github.com/china-qijizhifeng/SpecPilot-reproduction)（用户管理的公开组织仓库）。

## 当前进度（2026-11-09，UTC+08）

图例：✅ 已完成 · 🟡 初步完成 · 🔵 正在推进 · ⬜ 待完成。只有完成该阶段验收才标 ✅。

| 步骤 | 主线任务 | 状态 | 已有进展 / 待完成项 |
|---|---|---|---|
| 1 | 明确复现对象与实验协议 | 🟡 初步完成 | 已区分 dev / sealed 与诊断 / 正式统计，见[协议规划](docs/11-reproduction-plan.md) |
| 2 | 双卡配对测量自动化与远程验收 | ✅ 已完成 | a05 两轮真实换卡，10 pair / 20 臂行，exit=0，GPU 清理通过；26 项回归通过，见[验收记录](docs/experiments/p2-remote-smoke-20261107.md) |
| 3 | AR vs stock 基线测量 | ✅ 诊断通过 | stock/AR 3.8699×，95% CI [3.5571, 4.2242]；40 pair / 80 臂行、两轮换卡通过，见[验收记录](docs/experiments/p3-ar-stock-2048-20261107.md) |
| 4 | 验证作者 final 的收益 | ✅ 产物测量完成 | final/AR=8.7347× [8.0235,9.5599]；直接 final/stock=2.2219× [2.1381,2.2988]，见[验收记录](docs/experiments/p3-final-2048-20261107.md) |
| 5 | 真实正确性、噪声与晋升判据 | ✅ dev联合验收完成 | [验收记录](docs/experiments/dev-joint-20261108.md)：30请求、当前前后null、两轮换卡与实际测速输出forcing均通过；作者产物不写晋升账本 |
| 6 | 建立独立 sealed 验证 | ⬜ 未开始 | 前置验收通过后由 controller 管理，agent 不接触内容 |
| 7 | 真实 profiling 与成本模型 | 🟡 profiling/线性重放通过 | [stock诊断](docs/experiments/bottleneck-20261109.md)与[真实链重放](docs/experiments/step-replay-20261109.md)完成；完整最佳树/三因子仍缺 |
| 8 | agent 自主提案与实现 | 🟡 CPU与受限入口通过，GPU未接通 | CPU自治与独立Codex入口的非敏感权限探针已验收；旧spawn接口不继承该保证，尚无真实GPU自主实验 |
| 9 | 多轮真实优化闭环与记忆 | ⬜ 待真实验证 | [mock 闭环](docs/06-gates.md)已跑通，不代表真实引擎闭环完成 |
| 10 | 对照实验与最终报告 | ⬜ 未开始 | 分析各组件贡献，分别报告架构与数字复现证据 |

**已完成：**配对工具、基线与30题dev联合验收（2.2215×）、[200新题泛化审计](docs/experiments/generalization-20261108.md)，以及[160新题反例独立确认](docs/experiments/confirmation-20261108.md)。该确认阶段148回归、两次独立重放、5928文件SHA及GPU清理通过。

**当前结论：有泛化，但不是普适约2.2×。** 2048上限、自然EOS、两轮换卡，final/stock的95%CI如下；原100条作者dev已按预设规则排除。

| 新题分组 | 几何平均加速 | 95%CI |
|---|---:|---|
| 原5基准族100题 | **2.172×** | [2.130,2.216] |
| 新5领域100题 | **1.530×** | [1.487,1.574] |
| 全部200题 | **1.823×** | [1.792,1.855] |

**重要边界：**上轮中文20题速率仅0.513×；最新独立60题完整请求延迟比stock/final为**0.540× [0.504,0.577]**（三主要端点校正后区间），final约需**1.85倍时间，性能反例确认**。尚未隔离语言/短答等因果因素。

**质量结论：**新人工参考摘要ROUGE-L差-0.0027[-0.0108,0.0046]，代码通过率差+5个百分点[-5,+17.5]；均未确认下降，但**未证明非劣**。摘要来源不同，不能推翻旧Alpaca告警。forcing通过不等于全域提速/语义非劣，也不能排除所有reward hack。

**此前诊断：**[中文短答减速诊断](docs/experiments/diagnosis-20261108.md)已执行/重放/归档，167回归与6509文件SHA通过。正式计时未重跑；profile采集器修复后16探针全部成功，不改final/controller。

**诊断结论：不是只因输出短。** 匹配512输入、实际64输出时，中文final仅0.619×、英文1.490×；中文长答实际生成2048时仍约0.666×（触顶，不是完整任务收益）。单个预选probe里final中文/英文的VERIFY标签次数38/10，差异主要落在验证循环；不能直接等同于已审计的接受率或某开关故障。

**边界：**12个合成事实卡不是自然中文总体；强制1024组约72–75%token发生在EOS之后，不能以“强行拉长就快”证明固定成本是唯一原因。质量非劣仍未证明。

**诊断阶段状态：**该阶段两H100已释放；按容器时长折算约11.27GPU小时，原16预算内。初次profile失败保留，阶段报告/两次重放/SHA已归档。

**此前准备：**按用户批准回到真实自主优化主线，[stock基线、验收护栏与接口缺项核对](docs/experiments/rsi-readiness-20261109.md)完成：167回归、五阶段25319项SHA、裁判/dev各四次重放通过。原格式比较失败保留，仅末尾换行差异已核实；未启动GPU或修改裁判。

**最新完成：**[真实candidate接入与no-op烟测](docs/experiments/candidate-20261109.md)：184项回归、关闭/开启两模式各两轮换卡、20pair/40臂行输出一致；40条实际输出FP32评分及绑定检查通过。两次CPU重放与2970项SHA通过；任务Completed/exit0，两卡已释放，折算0.395GPU小时。不改controller，不宣称优化收益或lossless。

**此前stock诊断：**[真实瓶颈分析](docs/experiments/bottleneck-20261109.md)：原20pair计时保留，独立补采20/20窗口；202回归、两次CPU重放与393项SHA通过。窗口累计kernel工作约89.6%在VERIFY，不是整请求墙钟占比。当时36/40行满足旧代数约束，一题的“多1 token”已由下述逐步重放解释；可识别mm仅覆盖约0.51% kernel工作，完整三因子仍为未知。

**最新完成：**[stock逐步观测与真实线性重放](docs/experiments/step-replay-20261109.md)：3题on/off共12pair/24臂行与原stock输出一致；6份真实链、24个故障副本拒绝、两次CPU重放、210回归及5598项SHA通过。计数差1已解释：`输出=首token+正确草稿+已提交验证步−末尾裁切`；原异常题未裁切，两个正常对照各裁掉1。

**观测边界：**每份真实链均额外执行1个未提交overlap尾步，不能算进实际接受量；未逐条对齐旧profile标签。观测耗时不是无干扰步计时，线性重放不等于最佳树或完整成本模型。

**最新完成：**[首轮真实agent探索接入与证据分析](docs/experiments/exploration-20261109.md)：master自行选择接受历史预算、终止重叠关键路径两个方向；实际完成2项CPU实验。224回归、两次独立审计重放、5类篡改拒绝及118文件SHA通过；0个GPU提交，无候选实现或晋升。

**最新核查：**[独立记录可用性](docs/experiments/history-confirmation-20261109.md)：22份归档索引、35030个去重路径中，可识别的有序计数仍只有原3题；文件副本和两轮重复不是新样本。原master复核为`needs_independent_collection`，没有重算旧题冒充独立验证；不代表规则已失败，也不代表磁盘绝无其他未索引数据。

**已停止支线：**[接受历史补采](docs/experiments/history-collection-20261109.md)按用户要求停止人工推进。a01在短预热后因日志参数冲突失败，修复及235项CPU回归通过；a02仅准备、从未提交，已拦截旧提交脚本。保留代码/证据，无正式独立确认结果，不算自主探索完成，也不判断点子无效。

**最新完成：**[真实CPU实验自治回路](docs/experiments/agent-autonomy-plan-20261109.md)：master自主分配两个方向和预算，direction自行设计/编写脚本并执行4次（3成功、1失败后自行修复），再由master根据反馈停止两方向。249回归、两次独立审计、输入/代码绑定和5类篡改拒绝通过；0GPU、无优化发现或晋升。

**此前核查：**[GPU自治权限边界与离线预检](docs/experiments/autonomy-gpu-boundary-20261109.md)：旧spawn子agent通过直接shell读写了broker目录外的无敏感canary；这是应用层工具边界缺口，不是绕过宿主审批或实读sealed。12项新增测试、261项总CPU回归通过；离线请求检查始终返回blocked，无GPU提交或正式研究实验。

**最新完成：**[Codex权限边界与主线收口](docs/experiments/codex-boundary-20261109.md)：独立app-server加外层Landlock/seccomp，真实探针8次broker调用、1次CPU运行；授权读写/执行成功，越界读取、规则写入、GPU动作及原生patch越界被拒。17项定向/278项总CPU回归、两次独立审计与冻结源码身份复核通过。不是旧spawn入口安全证明，也不是GPU研究完成。

**发布状态：**用户确认本人主动将仓库设为public，并批准按公开标准同步，原“仅授权私有同步”的阻塞已解除。公开发布审查、范围与版本核对见[同步记录](docs/experiments/public-sync-20261109.md)；不上传原始证据、凭据或受限数据，不改变仓库可见性。

**正在做：**[首轮GPU自治接入](docs/experiments/gpu-autonomy-20261109.md)已获批，镜像/WeaverDev项目已确认；Master自行选方向，direction自行写脚本和CPU检查。累计10研究回合/24动作/2CPU运行，动作额度耗尽，Master已停止；**0GPU提交，GPU自治尚未验收**。已询问是否追加最多4动作，不擅自扩额。当前计划见 [PLANS.md](PLANS.md)。

**接下来：**审核[最小真实GPU自主实验方案](docs/experiments/codex-gpu-autonomy-proposal-20261109.md)，再接通受限角色到GPU执行/反馈链；Master选方向，direction自主设计与迭代。资源提案为最多2×H100、合计2GPU小时，尚未授权；镜像/提交参数需重新核对确认。不恢复旧补采，不预设VERIFY优化，不自动进入RSI或sealed。

**已有基础：**三臂真实 server、dev验收、外部数据审计与mock闭环完成；**尚未复现论文原sealed数字或真实RSI方法结论。**

每个大步骤结束后更新本看板、附上验收结果链接，创建阶段提交并推送到 GitHub；详细交接见 [HANDOFF.md](HANDOFF.md)。

## 这是什么

论文提出一个**逐部署自动发现投机解码优化**的 agentic 循环，并用它发现了四个
无损机制（W12 权重格式、混合目标 best-first 树、两级验证 TLV、批处理三件套）。

复现目标不是"重跑出 10.87×"，而是**重跑出这套循环**，使其在给定部署上自己找到
同等性质的机制。因此验收看的是循环的结构正确性（成本模型能否指出真瓶颈、评测器能否
判死自己），而不是单个加速比数字。

## 主线

单请求 × Qwen3.8-27B × DFlash2 × H100 × SGLang v0.5.20；后续统一通过 NorthJob 执行。
先校准与验证作者方案，再推进自主发现；2.13× [2.07, 2.19] 是论文 sealed 参照，不是当前实测结果。

选它的理由：唯一一条能同时覆盖 τ 因子（树）、kernel 因子（W12）、以及"改 ceiling 假设
本身"（TLV）三类的路径。其余部署作为**记忆迁移**验证，不重新发现。

## 文档

- `docs/00-architecture.md` — 论文骨架与五层系统架构
- `docs/01-message-protocol.md` — 四类结构化消息 schema
- `docs/02-acceptance.md` — 五级验收闸门与判据
- `docs/03-roadmap.md` — 前置门槛、路线与工作量估算
- `docs/04-paper-facts.md` — 论文关键数字速查（便于核对实现）

## 硬件前提

正式配对测量按现行协议申请 2×H100 80GB，并交换 GPU；不再等待本机 GPU 释放。
NorthJob 提交前必须确认 image，不能以单卡串行结果冒充正式配对测量。

## 工作约定

见 `AGENTS.md`。

## 接手：先读 HANDOFF.md

新 session / 新维护者从 [`HANDOFF.md`](HANDOFF.md) 开始。它记录当前卡点、环境事实、
已验证结论和下一步路线，取代任何口头交接。
