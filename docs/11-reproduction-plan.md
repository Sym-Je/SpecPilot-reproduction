# SpecPilot 复现方案：论文、公开项目与本地交接的重新对齐

日期：2026-11-07。状态：方案草案；不修改已有验收，不授权 NorthJob 或 controller 变更。
本轮只读分析并保存文档，没有启动 server、测量、RSI 或 sealed 流程。

执行方式更新：用户已要求后续统一通过 NorthJob，不再等待本机 GPU；具体任务提交仍需确认 image、完整命令与资源。Git 全流程管理规则和实验索引见 `docs/12-experiment-management.md`。下述原有统计及正确性边界不因换执行平台而放宽。

## 1. 依据与可信边界

- 用户附件 SpecPilot.pdf，共 23 页；重点为 §3.1–3.4、§5.1、§6.1–6.2、附录 A–F。
- 对应公开项目：StargazerX0/SpecPilot；公开 README 将论文 dev 表格与 sealed 结果分开说明。
- 本地上游：/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main，无 .git；78c42af 是项目自述，不能替代 tarball 与 canonical manifest 的固定哈希。
- 初次分析基准为本地 HEAD=8817621；后续编排及文档版本以 Git 历史为准。私有远端现已配置，用户授权大步骤验收后提交并推送。
- 遵守 HANDOFF.md 的上游实现阅读禁令；只核对配置、评测和启动协议，不读 python/ 或 settings/*/files/，不读 sealed。
- 公开项目的 main 只作元信息和协议对照，不自动升级本地冻结快照。
- 旧路线图中的 controller/calibrate 等“命令形态”不是已存在 CLI，不直接拿来运行。

## 2. 三种不同交付物

1. 作者产物复现：用冻结的 stock/final 黑盒引擎，独立测量速度与正确性。证明发布产物可复现，不证明我们重新发现了机制。
2. 真实 RSI 复现：从 stock 出发，真实 profile/replay 驱动方向，由实际 agent 实现 option，经 controller 判定，完整跑过晋升、sealed 与记忆。
3. 独立机制实现：不读作者实现，自行实现并验证树、W12、TLV。难度与预算单独核定，不能把加载作者覆盖层算成独立实现。

近期并行的是逻辑上的两条工作线，而不是同时占用 GPU：先用作者产物校准尺子，再在独立 stock 分支验证真实 RSI。
最终作者 final 不作为独立搜索的起点；公开机制复现属于 open-book reproduction，不冒充盲发现或新颖算法。

## 3. 重新校正的口径

### 3.1 2.24 与 2.13 不应简单称为冲突

- dev 表格：stock/AR=3.95，final/AR=8.86，两者相除约 2.24。
- sealed：config.paper.sealed_final_vs_stock=2.13x [2.07, 2.19]。
- 两者使用不同请求协议；作者说明 dev 与 sealed 有偏差。不能把 dev 的 2.24 当作 sealed 目标，也不能要求 dev 恰好等于 2.13。
- 汇总 tok/s 的比值不一定等于 per-request 几何平均；184→416 也不能直接写成 2.13。

### 3.2 请求规模分三层

允许访问的上游 scripts/bench.sh:4–7、19：单请求表格默认前 6 条/suite，共 30 请求；ITEMS=20 才是全量 100 条 dev。
当前每 suite 4 条、共 20 请求，是用户明确指定的尺度诊断，不是论文表格的严格同请求规模复现。
顺序为 20 条诊断 → 30 条论文 dev 口径 → 按风险选择 100 条稳健性检查；sealed 是之后由 controller 独立构造的 unseen 请求。

### 3.3 当前 CI 只能按其真实方法命名

上游 scripts/compare.py:24–58：先跨 fresh runs 对每请求速率作几何平均，再按 suite×concurrency cell 等权汇总；在 cell 内重采样请求，2000 次，2.5%/97.5% 分位点。
当前 p3_pair_run.py 使用 controller.stats.bootstrap_ci 对每请求的两轮 log-ratio 作 pooled request-cluster bootstrap，10000 次；不是 suite-stratified。
每 suite 等量时点估计一致，但区间构造不同。保留当前 CI 做诊断；严格论文口径与 controller 正式统计入口由维护者确认，不把现有 median CI 改名充数。

### 3.4 真实方法层未完成

- orchestrator/loop.py:56 的 Proposer 是固定 registry 的确定性策略，未接真实 LLM；run() 仍用 mock PairBench 与固定 prompt。
- costmodel/floors.py:62 的分解把 kernel 固定为 1，缺真实 T_prof、分 kernel floor 与 lattice-derived tau_best，不能视为论文完整三因子。
- controller/token_force.py:54 仍比较 token 列表，没有 FP32 scorer、逐位置 margin、delta 标定与大 margin 事件解释。现有 G4 不能证明真模型 lossless。
- controller/http_transport.py 的输出分歧门槛及正式聚合仍有待维护者确认项；这些不阻止低风险诊断，但阻止正式晋升/论文级结论。

## 4. 当前事实

- G2–G5 是 mock/TinyLM 范围；G6–G8 与真实三臂 smoke 的历史证据保留，不扩大其结论。
- 本机编排 CPU/HTTP 验收 15/15，真实 20 个 dev 输入及 final 46 个开关已检查。
- 新编排的真实 GPU 生命周期尚未走通：运行前发现 GPU0/1 存在 PID 59780/59781，各约 518 MiB；本轮只读复查仍有约 68%/69% 利用率。
- 未启动新的测量 server；没有独立配对速度数字，NorthJob 零次提交。

## 5. 阶段 A：NorthJob 20 请求尺度诊断

### A0 冻结与空闲检查

固定模型路径/revision 声明、树 hash、配置、greedy、thinking、turn 0、BF16、2048 new tokens、预热、端口、GPU UUID、请求 manifest 和脚本 hash。
确认真实 GPU 型号/驱动/功耗状态；只在两卡空闲且无其他计算进程时运行。确认归属和释放由用户/管理员处理，不杀未知进程。
执行节点改为 NorthJob 分配的两张 H100；本机旧进程不再是实验前置阻塞。先验收远程挂载、依赖、存储和编排生命周期；不假定本机路径或已生成环境能在镜像中直接复用。
每轮两根 fresh server；控制器逐请求配对；停止并释放后实际交换 GPU UUID；不以 logical swap 或两个独立单臂 JSONL 冒充。

### A1 AR vs stock

P3_PER_SUITE=4，P3_MAX_NEW=2048，2 轮。20 个不同请求、40 个完整 pair、80 条臂记录。
用户既定验收：stock/AR 几何平均在 [3.555, 4.345]。点估计是否达标和 CI 分开报告。
失败先停，不自动继续 AR/final，不因结果不好临时换请求或放宽阈值；4 与 6 条子集的差异也作为诊断因素，而非自动判引擎有错。

### A2 AR vs final

只有 A1 达标后才运行；同一请求、长度、预热和两轮 GPU 互换。
报告 final/AR 的直接配对结果；与 A1 的 stock/AR 相除只能叫间接 final/stock 诊断，不给它包装成同会话直接配对 CI。

### A3 直接验证 final/stock 与长度解释

进入 P4 前需要直接 stock/final 配对证据；若 A2 暴露问题则优先做此项，而不是基于间接比值下结论。
使用同一 20 请求及物理换卡协议，在需要判断长度因果时对照 256/2048 caps；原 smoke 只有 5 请求且协议不同，不作严格因果对照。
同时报告真实 completion_tokens、stop/length、prefill 与 decode 成本、verify/exact-pass 计数、target/draft/glue 时间。
自然 EOS 早停的请求不能因 cap=2048 就称为长序列；不通过 ignore_eos 或删短样本凑速度。

若升至约 2.0–2.2，支持固定开销解释，但仍需路径/计数证据；若仍约 1.5，则先检查配置/加载身份、实际机制激活、lazy JIT、功耗/频率与跨卡差异，再决定是否继续。
TREE_SHA 和 46 开关存在证明产物/配置身份，不单独证明每个机制在运行路径上生效。只用运行时日志、module 路径、计数、profile 及维护者审计，不读禁止的实现源码。

## 6. 阶段 B：严格 dev 对照与稳健性

A 阶段通过后，冻结实验计划，按上游每 suite 6 条、2048 tokens 跑 30 请求同口径 dev 比较；需要稳定估计和故障排查时再用 20 条/suite 的 100 请求。
不把扩大样本作为“追数字直到碰巧吻合”的过程；请求集合、轮数、停止规则与可接受偏差先登记。
跨 suite 等权，跨轮同请求聚合；两轮不作为两份独立请求。报告所有 suite 和全部轮次，既报点估计又报区间与卡位分层。
用允许访问的上游 compare.py 对相同原始记录作影子对照；其交集丢项行为必须由外层完整 manifest 检查拦住。
正式 CI 口径由维护者/controller 确认；当前 pooled CI 仍按原名保留作诊断。

## 7. 阶段 C：真实 controller 与 correctness 前置

在任何正式候选晋升或 sealed 数字结论之前完成，由维护者提供 controller 侧实现/验收：

1. 两个独立 stock server、两卡互换的 null calibration；噪声来自真实同尺度会话，不复用 mock 3.11% 或单 URL 自比值。
2. 明确噪声定义、95% 下界与双侧 CI、输出分歧约 3% 门槛的精确组合。遵守已有要求，不擅自放宽 docs/02 的区间全宽 <0.2%。
3. 实现 stock-engine teacher-forced scorer，FP32 LM head，沿候选自身输出上下文评分，保留 argmax 与 margin；重新测本机 stock mismatch，而非硬抄论文 0.72%。
4. 依据 stock 首次偏离 AR 的 margin 标定 delta；rate rule 和 large-margin event rule 分开，并支持 stock 复现及 prefill 长度敏感性解释。
5. 真模型故障注入：2048 tokens 之后，每第 7 个 vocab id 加 logit bias=2；在最长 4096 输出的 controller 测试中须被拒。仅改归约次序的近并列差异不能被当作明显造假。
6. 长度不一致、缺 token、空样本、非有限速率、identity 变化、半对、请求缺项必须拒绝；G8 PASS 不能替代完整 run 验收。

agent 不改 controller，不给 controller 伪造 promoted；诊断阶段不调用现有 compare() 来作真实晋升，不写 ledger。

## 8. 阶段 D：P4 sealed

按用户顺序，在远程尺度确认及 controller 真实判据就绪后，再由 controller/维护者建立 unseen 请求集。
先定抽样策略、去重、suite 配额、随机种子和访问权限，再冻结；不根据 P3 哪些题跑得快来挑 sealed。
方差可以指导预先规定的样本量，不能破坏样本独立性或使 agent 看到请求内容。
Phase 4 才加载：stock/final 双卡同请求换卡计时，输出及更长至 4096 tokens 的 token forcing；任一不通过则拒绝整轮。
2.13x [2.07, 2.19] 是论文 sealed 参照，不是要求我们的 CI 逐端点相同；本地等效性容差和统计功效须在揭盲前由维护者/用户明确。
agent 只接收允许公开的汇总证据，不接触 sealed 内容。

## 9. 阶段 E：真实成本模型和 replay

在 stock 与各 promoted candidate 上固定代表性 dev 请求采集 lattice、target 输出、阶段计时和 kernel-class profile。
profile 不计入正式测速；warm path 与首次编译分开。

三因子按论文定义：

- tau_best/tau：同一 lattice 上 exact replay 的最佳树/实际接受量。
- T_prof/T_floor：实际 profile kernel 类时间与各类 byte/FLOP floor 之和。
- T_step/T_prof：profile 外调度、CPU glue 与其他开销。
- 每类 floor=max(FLOPs/(0.60×dense peak), bytes/(0.90×bandwidth))，明确读写字节与计时单位。

不能只用模型参数量硬凑 1.83×1.01×1.39；实际要验最大的 gap 能否预测下一轮可测的瓶颈迁移。
计数区分 verify step、Q pass、exact pass；final τ 未核对前不作奖励。
ceiling 是带假设的排序工具，不是不可突破的物理上界。若数个因子接近 1，审查“一次 draft/一次 exact pass”等假设，而不是无限调 kernel。

## 10. 阶段 F：从 stock 开始的真实 RSI

固定 agent 模型/工具/提示词版本，接真实 proposer 与 candidate 状态机；接口输出含机制、option、默认值、profile/replay 依据、净 headroom、验收命令、成本预算与失败条件。
先做低风险、可归因的 block/tree-budget、调度或消除重复工作的机制；参数调优、系统优化和算法机制分开记账。不能用放松最终 target 验证换速度。
每候选默认关闭并复现 stock；先 T0、dev forcing 与廉价 headroom 证据，再占两卡正式测量；没有净收益证据不堆复杂实现。

每轮流程：真实 profile/replay → 因子排序 → 方向提出/实现 → T0/forcing → 配对 CI → controller 晋升或拒绝 → 集成/剖析 → controller sealed final → 合格记忆 → 下一轮重算成本。
候选对 current-best 的增量与 final 对原 stock 的增益分开；不能直接连乘不同协议下的中间点估计来替代 final 实测。
先以 2–3 轮和可解释的接受/拒绝轨迹验证闭环；若没有有效晋升，只能报告真实闭环已运行、尚无收益，不能伪造成功发现。
W12/TLV 独立实现作为后续高成本里程碑，按格式契约、microbenchmark、集成计时分拆，不承诺一小时完成。

仅两卡时：探索最多一方向一卡；正式配对独占两卡，暂停其他 GPU 工作；先关闭持有显存的探索任务再测量。多 agent 不等于有更多 GPU。
CPU replay、文档和代码检查可与不冲突工作并行，正式计时不混入 profiler/编译/其他 GPU 负载。

## 11. 对照和记忆

最小复现实验对照为 cost-guided multi-agent 与无 cost-model single-agent，固定同一先验、候选权限、轮数和总 GPU/token 预算；这检验组合方法，不单独归因 cost model。
若要隔离贡献，补 single/multi × cost-model on/off 的 2×2；预算不足只报告案例，不宣称已证明各组件的独立因果效应。
论文 1.34 与 2.13 是参照，不是要求挑随机种子命中。多次独立 campaign 才能讨论稳定优势。

只有 controller sealed final 合格后才写 promoted memory：code delta、requires、options、契约、汇总证据、适用范围与未验证 regime。
依赖闭包应用到 stock 后须字节级复现来源代码；复用机制不计新发现。
失败方向和进程/环境故障写运行日志/决策文档，不冒充合格迁移记忆。

## 12. 资源、时间与停止规则

A1/A2 每对大致按 R×(双 server 启动时间 + 请求数×较慢臂单请求时间 + 预热/清理) 估计；NorthJob 排队和镜像准备另计。
若仅采用用户给的 AR≈47秒估计，20请求×2轮的请求段约31分钟，另加启动/清理；可规划每对约45–90分钟，但在真实长度/启动数据出来前不承诺。
30 请求或100 请求按实际耗时重新预算；正确性 scorer、真实 RSI 和 W12 不能套用这一小时估计。
论文全量是13轮、530 GPU小时量级，不把小规模复现承诺成全量覆盖。

硬停止：忙卡、错 manifest、缺项、未物理换卡、server 失败、身份漂移、forcing 拒绝、噪声不达标、sealed 泄漏或 option 默认不复现 stock。
不自动降级串行、不把失败轮静默续接、不临时改样本/目标、不绕过 controller、不在 image 和任务命令未经确认时提交。
NorthJob 为后续执行入口：按 skill 查重名、展示完整命令与资源、显式确认 image、提交后验证 code==200 和 job_uuid。任务、失败和产物索引均按全流程管理规范记录；用户已授权大步骤验收后更新首页、提交并推送到私有 GitHub origin。

## 13. 下一次实际执行

1. 建立实验记录，确认远程 image、代码快照、挂载和资源，按 skill 准备 NorthJob；不再等待本机两卡释放。
2. 在确认的远程环境重跑已有 CPU 验收、配置和空闲检查，不增加新的研究方向。
3. 经 NorthJob 运行 A1，报告全部 suite、两轮和总体数字；达标才运行 A2。
4. 根据 A2 做必要的直接 stock/final 与长度诊断；随后确认 B/C 的正式口径和维护者工作。
5. 每阶段单独报验收与证据并更新 Git 中的记录；不提前 RSI 或 sealed，不把作业提交成功当作实验成功。
