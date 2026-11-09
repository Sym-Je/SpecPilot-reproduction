# Git 全流程实验管理

日期：2026-11-07。用户要求：仓库不仅管代码，也要管理从计划到结论的整个实验流程。
本文件建立记录规范与当前索引；不代表 NorthJob 自动归档已实现，也不授权提交任务或修改 controller。用户后续已授权大步骤验收后提交 Git 并推送私有远端。

## 1. 单一入口和职责

- `HANDOFF.md`：当前状态、阻塞、下一步；新 session 从这里进入。
- `docs/11-reproduction-plan.md`：研究阶段、协议和停止规则。
- 本文件：流程管理规则、阶段索引。
- `docs/experiments/<experiment-id>.md`：每次实验的版本、任务、证据和决策；从 `TEMPLATE.md` 复制。
- `exp/`、`harness/`：执行单元；`controller/`：维护者负责的计时、正式判定和账本。
- 原始日志、JSONL、profile、源快照：持久存储，不强行加入 Git；记录精确位置、大小和 SHA-256。

Git 里的记录是实验索引，不是 agent 自己生产的正式统计结果或晋升账本。
私有 GitHub origin：`https://github.com/Sym-Je/SpecPilot-reproduction.git`。每个大步骤结束更新首页与交接，验收后阶段提交并推送；只有确认远端提交身份一致才算同步完成。不自动建分支或改变仓库可见性。

## 2. 每次实验的生命周期

1. **计划**：分配唯一 experiment-id，写目标、对照、请求协议、可执行验收命令、预先规定的判据和预算。
2. **冻结**：绑定执行代码、引擎树、配置、请求 manifest、模型身份和环境；不能只写一个 HEAD 来代表带未提交修改的代码。
3. **提交前确认**：按 northjob-submit skill 查重，展示完整命令与资源，确认具体 image；敏感值另行安全注入，不入 Git。
4. **提交**：追加 attempt-id、UTC 时间、返回码和 job_uuid。只有 code==200 且有 job_uuid 才记为 submitted，不记为实验通过。
5. **运行**：记录 started/failed/blocked 等状态、退出码和失败证据；返回不明确时先查任务，不盲目重提。
6. **测量归档**：核对请求和轮次完整、物理换卡、环境身份；保存原始数据、计算命令和统计输出的校验清单。
7. **验收与决策**：引用实际验收输出，区分诊断与正式结果、作者产物与独立发现；缺项或失败如实记录。
8. **交接**：更新阶段索引和 HANDOFF，标明下一步；经用户授权提交后才算进入 Git 历史，未提交时明确提示。

重跑保留 experiment-id 并新增 attempt-id；协议或实现改变则新建 experiment-id，链接旧实验。失败尝试不删、不覆盖成功记录，不静默续跑半轮。

## 3. 代码与产物可追溯要求

- 优先用确定的代码 commit 执行；未经授权不为冻结而自动 commit。
- 若使用未提交代码，必须打包实际执行源快照，包含跟踪文件修改和新增执行文件；记录基准 commit、变更清单、快照位置与 SHA-256。只有 diff 而漏掉新增文件不够。
- 验证远程实际加载的代码、引擎树和配置与冻结身份一致；本地 HEAD 不等于远程执行身份。
- image 记录用户确认的名称及可取得的不可变 digest；digest 不可取得时写明限制，不能伪称环境完全冻结。
- 记录目标/草稿模型 revision 或可用身份、数据 manifest hash、实际 GPU UUID/型号、软件版本与关键参数。
- 每个 attempt 独立输出目录，至少索引提交回执、环境 manifest、server 日志、逐请求原始记录、验收和统计输出。
- 任务退出前确认产物已写入持久存储。只在容器临时目录或 `/tmp` 的数据不算完成归档；后续使用前复核校验值。
- Git 中只记录脱敏摘要和证据引用，不提交密钥、sealed 内容或可泄露 sealed 请求的信息。sealed 结果仅引用 controller 允许公开的摘要/记录标识，不为归档读取受限产物。

## 4. 当前阶段索引

最新核查：[接受历史方向独立记录可用性](experiments/history-confirmation-20261109.md)。
22份归档索引/35030去重路径中可识别计数仍只有旧3题，独立确认未运行，MAE/收益null。
原master真实复核needs_independent_collection并关闭；14定向/224回归、两独立清点重放及3类篡改拒绝通过。
32文件/121237字节归档全SHA通过，清单`logs/history-confirmation-20261109-a01.sha256`，SHA见阶段记录。
仅索引元数据与匿名计数，不是原始产物全量复验；不修改运行源码/保护目录，0GPU、无实现或晋升。
下一阶段待批4新dev/两次fresh计数采集，拟1H100/30GPU分钟；不是单卡A/B性能测量，不放宽T001契约。

最新完成：[首轮真实agent探索工程接入与证据分析](experiments/exploration-20261109.md)。
真实master自主选方向，direction实际完成2项CPU实验；科学结论needs_more_evidence，无可实施提案。
a01接口不足保留，按agent需求补证据后a02 fresh重试，不算两轮优化；两attempt共6角色已关闭。
执行pin8195964/b0b89d0，224回归/a02两次独立重放/5类篡改拒绝/118项SHA通过，0GPU。
预测MAE改善不是收益；终止顺序不是关键路径。未提供final答案，不改controller，不实现或晋升。
后端继承默认模型，精确模型ID/用量不可得；不冒充完整论文agent配置、物理隔离或真实多轮RSI。
下一阶段需先获批最小独立证据确认；没有合格记录则等待或另申请采集，不指定VERIFY优化。

最新完成：[stock逐步观测与线性链重放](experiments/step-replay-20261109.md)。
用户批准必要stock阅读/默认关闭钩子；3题on/off两轮换卡12pair/24臂行均匹配原stock，
6真实链/24故障副本拒绝/两次CPU重放/210回归/5598项SHA通过，原stock不变。
输出差1由首token与EOS尾裁切解释；每份有1个未提交overlap尾步，未冒充旧profile逐条对齐。
pin=e65925c/UUID job-7021a7f03f72-20261109101400已Completed/exit0，0.528333GPU小时/两卡释放。
无运行任务，不改controller，不读final，不作性能/lossless/晋升声明；完整成本模型仍缺。

最新完成：[stock真实瓶颈、计数审计与部分成本模型](experiments/bottleneck-20261109.md)。
202回归、原20pair计时、独立20/20窗口补采、两次CPU重放及393项SHA通过；未实施优化。
计时pin=a102b64/UUID job-fa7aeb0532ed-20261109083627，补采pin=5ed0302/UUID job-46790c2ece9b-20261109090434。
原profile4/20及500失败保留，补采以原生日志绑定确认未在采集，12次500仍记录错误。
窗口VERIFY工作约89.6%，计数一题差1、mm仅覆盖约0.51%，完整三因子保持null，不冒充完整成本模型。
两卡已释放，1.078333GPU小时/2预算；无运行任务，下一大步骤接口补齐先获批准。

最新完成：[真实candidate接入与no-op双卡烟测](experiments/candidate-20261109.md)。184回归、
关闭/开启各两轮换卡、20pair/40臂行输出一致与40条实际输出FP32评分/绑定通过；两次CPU重放字节一致，
2970项SHA通过。pin=d526f76，UUID=`job-4fcf9416b13f-20261109072806`已Completed/exit0，
node233两卡释放，折算0.395GPU小时。只做启动option接口验收，不改controller、不宣称收益/lossless或晋升。
准备/运行/bundle/清单均见阶段记录；无运行任务，下一大步骤待批准。

此前完成：[真实RSI准入准备](experiments/rsi-readiness-20261109.md)，用户批准结束final追因并回到主线。
仅CPU回归/历史证据重放/接口缺项核对，不提交GPU、不改controller或eval。stock为搜索起点，
final仅参考；历史noise/δ不得代替未来候选校准。candidate option/T0接入、完整成本模型、真实proposer
与正式晋升状态机仍缺，不能以现有mock入口冒充真实RSI。167回归、25319项SHA、裁判/dev各四次重放通过；
格式比较初次失败保留，修正参照历史CLI后通过。新37文件证据`logs/rsi-readiness-20261109-a01/`及
`logs/rsi-readiness-evidence-20261109-a01.sha256`已校验；无运行任务，下一大步骤待批准。

此前诊断：[中文短答减速诊断](experiments/diagnosis-20261108.md)执行/补采/归因/重放/归档完成；
12事实卡匹配输入/输出后仍有语言相关收益差；预选probe主要工作差异在VERIFY循环，非单纯短输出。
167回归、正式及profile独立重放、6509文件SHA通过，不改final/controller。
正式pin629eb42/UUID job-89c6c8cd6c11-20261108200750；补采pin74afcee/UUID job-72e589efab39-20261109014404；
CPUmapper pind7a5fd2。两任务已Completed/exit0，node244两卡释放，总约11.27GPU小时/16预算，无sealed/RSI/晋升。

新增活动：[final反例独立确认](experiments/confirmation-20261108.md)执行/重放/归档完成；
中文60/人工参考摘要60/代码40，排除全部dev与前审计；中文请求延迟比0.5397×的反例确认，
摘要/代码退化证据不足。148回归、两独立重放/5928文件SHA通过，不改final/controller。
GPU pin65364f5、CPU pinbb5b8fb，UUID job-a99898c2f332-20261108164059已Completed/exit0，
node208/2H100已释放。中文1题辅助质量格式缺测不删性能题；无新GPU或sealed/RSI/晋升。

| 阶段 | 状态 | 已有证据 / 下一步 |
|---|---|---|
| mock 闭环与真实三臂 smoke | 历史阶段已验收，非论文数字复现 | `docs/06-gates.md`、`docs/09-p3-harness-validation.md` |
| 配对编排 | 完成；17/17 CPU/HTTP 回归，含真实 TIME_WAIT/live-listener 测试 | `exp/p3_pair_run.py`、`harness/test_p3_pair_run.py`；a05 远程生命周期通过 |
| 本机 AR/stock 尝试 | 历史 blocked；未启动测量 server | `logs/p3-local-ar-stock-20261107.log`；不是远程执行前置条件 |
| NorthJob 远程工具验收 | completed；a05 两轮换卡、10 pair/20 臂行、exit=0 | [最终验收及失败历史](experiments/p2-remote-smoke-20261107.md)；26 项回归、统计复算、33 文件校验与 GPU 清理通过，非论文数字 |
| A1：AR/stock | completed；点估计诊断通过，源 pin=79fe81a | [基线记录](experiments/p3-ar-stock-2048-20261107.md)；3.8699× [3.5571,4.2242]，40 pair/80 臂行、两轮换卡、39 回归及 38 文件校验通过 |
| A2/A3：AR/final、stock/final | completed；源 pin=4d67c2f，同 A1 请求身份 | [本阶段记录](experiments/p3-final-2048-20261107.md)；8.7347× [8.0235,9.5599] / 直接 2.2219× [2.1381,2.2988]；各 40 pair/80 行、50 回归及证据复核通过，非 sealed/lossless |
| C：第5步真实正确性与裁判 | 真实回归及dev联动完成 | [真实回归](experiments/p5-real-controller-20261108.md)：健康/故障/归约通过；后续30请求current null/实际测速输出forcing已联动验收，作者产物不写晋升账本 |
| B：正式 dev 扩围 | 30请求联合验收通过 | [验收记录](experiments/dev-joint-20261108.md)，pin=721b72c，UUID=job-e71c6069ec59-20261108081913已完成；2.2215× [2.1585,2.2827]，noise0.1327%，两轮δ0.25/正确性通过；128回归、两次重放/1223文件校验通过 |
| P4、真实 RSI 与最终对照 | 未开始 | 前置条件满足后按计划推进，agent 不接触 sealed |
| 真实RSI准入准备 | 已完成，不代表真实搜索就绪 | [基线与缺项](experiments/rsi-readiness-20261109.md)；167回归/25319清单项/各四次重放通过，不改裁判，下一候选重新标定 |
| 真实candidate外围接入 | 首版验收完成，仅启动option | [no-op烟测结果](experiments/candidate-20261109.md)；184回归/20pair/40评分/两重放/2970项SHA通过，无正式晋升 |
| stock真实profiling/部分成本观察 | 诊断能力完成，完整成本模型未完成 | [瓶颈及缺项](experiments/bottleneck-20261109.md)；202回归/20pair/20窗口/两重放/393项SHA，窗口VERIFY约89.6%，三因子null |
| stock逐步钩子与真实线性重放 | 完成有限3题工程验收，非最佳树/完整成本模型 | [真实链与计数解释](experiments/step-replay-20261109.md)；210回归/12pair/6链/24故障拒绝/两重放/5598项SHA，已释放GPU |
| 真实agent探索接入与首轮分析 | 工程验收通过，科学结论待证据 | [真实探索记录](experiments/exploration-20261109.md)；自主选2方向/实际2项CPU实验/224回归/两独立重放/5类篡改拒绝/118项SHA；无可实施提案、0GPU、无晋升 |
| 接受历史方向独立记录核查 | 核查完成；独立确认缺数据未执行 | [可用性与最小采集建议](experiments/history-confirmation-20261109.md)；22索引/35030路径无新增可识别独立计数，原master复核待采集；224回归/0GPU/无实现 |
| 作者final外部数据泛化审计 | 执行/归档完成，部分泛化且有反例 | [完整结果](experiments/generalization-20261108.md)：200题1.8230×，原5类2.1718×/新5类1.5302×；中文0.5133×，摘要质量代理告警。a02 Completed/exit0，137回归/两次重放/10312文件校验通过；不改final/controller，不冒充论文sealed |

本次仅按已有清单复核真实裁判、dev、泛化、反例确认、诊断五阶段的25319项；
不将该范围扩大为所有早期smoke/P3产物的全量归档，也不为历史结果产生新晋升。

## 5. 管理机制的验收

文档验收命令（本次变更前已列出）：

```bash
git diff --check
git diff --exit-code -- controller
test -s docs/12-experiment-management.md && test -s docs/experiments/TEMPLATE.md
rg -n 'NorthJob|12-experiment-management' HANDOFF.md docs/11-reproduction-plan.md
```

后续每个实验单独提供执行验收。只有能沿“实验记录 → 实际代码快照 → job_uuid → 原始证据及校验值 → 验收输出 → 决策”完整追溯，才算该实验的记录闭环完成。
