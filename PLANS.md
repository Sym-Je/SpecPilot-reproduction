
## Ascend continuation — 2026-11-10 用户要求继续优化

- 用户明确要求持续优化；本地新执行器取消三方向总上限，仍保留逐方向资源分配和统一NPU锁。Claude累计200美元、GPT累计上限依用户最新授权提高到1000美元，Claude上限原样保留，Claude账本直接复用。
- 新DSH Master/Direction已启动，真实进程与阶段状态记录在部署目录；首方向选择graph/C32成本归因，尚无新的NPU测量或收益。
- 已修正profile工作负载能力：实际C1/C8/C32、短中长输入、有界worker-step窗口、串行离线导出和八rank/数据丢失检查。8项新CPU验收及5项原startup-guard检查通过，NPU能力尚待实测。
- 旧validation已经打开，继续研究不读取或使用其结果；另冻结40条未使用的原validation分区请求组，仍不开放给研究角色。
- 源码快照见`harness/ascend_dsh/continuation/`。此更新不修改H100轨道、正式controller/eval/ledger，也不声称论文复现或性能提升。

# 当前执行计划

## 当前优先：Master原生同等权限（2026-11-12）

- [x] 用户明确授权仅prompt约束两类禁区，原生Master继承主助手工具/平台权限，不继续专用research-only限制。
- [x] 保存controller/ledger/指定规则摘要；先行postcheck正反例通过，不扫描sealed或凭据。
- [x] 实际原生stock阅读、scratch写入、CPU/公开网络验收；首次308失败后自主修复取得200，保护文件事后比较无变化。
- [x] 469项指定联合回归通过，入口/进度同步与公开审查；发布身份以本阶段publication回执为准。
- [ ] 后续另布置自主方案评估，不把能力探针当研究成果，不自动启动GPU。

本次0GPU，旧链长轮已停止；原失败与恢复记录保留，旧阶段完整工程收尾尚未完成。原生入口不保证强制数据隔离。

## H100已收口：Master研究决策要求（CPU，2026-11-12）

- [x] 保留旧47份dirty，先写验收；本阶段0GPU/0真实模型，不恢复旧研究。
- [x] 接通真实来源与SHA绑定、条件收益、否定判断反例取证、失败分类和最小实验要求。
- [x] CPU合成入口案例拒绝错误配置外推，接受修订后的未知结论与受阻取证；接受/拒绝记录两次离线复核一致。
- [x] 指定回归、旧证据重放与公开副本复验；精确数量和GitHub发布身份见阶段closeout/publication回执。
- [ ] 尚未真实Master复验，不宣称研究能力提升、GPU正确性、新收益或完整RSI；下一阶段另审研究与资源。

方案与边界见`docs/experiments/master-review-20261112.md`，不改controller、不向角色注入作者final答案。

## H100已收口：Master开放研究权限（2026-11-12）

新16GPU小时/12小时/4卡及既有镜像/调度已确认，唯一目录`logs/master-open-20261112-a01/`。
- [x] 保留47份旧dirty；先行边界、扩展源码option和入口154项检查通过。
- [x] 真实Master主动读源码/公开检索/BBuf/自写CPU分析，比较四维并选择d1链长、d2小M GEMM。
- [x] Direction自主实现并完成真实尝试；4任务6511GPU秒，所有任务终止，无活动GPU。
- [x] 完整日志交付缺口修复后同逻辑Master独立复核并stop，未新增GPU或改写原停止结论。
- [ ] 科学目标未达：链16兼容性未知、GEMM未见可靠收益，未触发controller dev正确性/性能；尚无Integration组合或Kernel候选，不开放sealed。
- [x] 433项指定回归及配置依赖后的公开副本复验、两次一致原生审计；归档与GitHub发布身份见closeout/publication回执，不重启旧任务、不结转余额。

## H100最新接续：真实树适配（2026-11-12）

- [x] Master评估最小真实范围，Direction自主实现双叶、CPU自检、真实失败修复与差分诊断。
- [x] 4任务全部终止、累计8100 GPU秒；原进程中断后保留原始结果，Master零工具管理评议defer。
- [ ] 正确性目标未完成：已执行版本10/10输出不一致；最新独立conv窗口修复仅CPU通过，尚未提交GPU。
- [ ] 下一阶段另批资源后先复核修复身份并运行既定最小诊断；通过后才由Master考虑独立controller。

唯一资源账本`logs/tree-adapter-20261112-a01/resource-state.json`不重置；本阶段不再提交新任务。
详见`docs/experiments/tree-adapter-20261112.md`；未进入sealed/晋升/真实RSI，不把旧待办当授权。

H100/Codex与Ascend/DSH是独立轨道。下面先保留Ascend既有计划，H100结果与下一步见后半；本次H100会话不接管Ascend进程、计费或validation。

日期：2026-11-09。入口为[HANDOFF](HANDOFF.md)，长期规则为[AGENTS](AGENTS.md)。

当前用户已授权本地8卡Ascend、DSH＋Claude 5.5与200美元API上限；预算保护触发后接续`gpt-6.1-sol`，GPT独立上限500美元，不用`gpt-5.5`；MRV2可不用。旧H100/NorthJob提案仍不自动执行。

1. 冻结dev60/validation40及9组baseline协议。已完成；validation不参与研究。
2. 完成预算/恢复/真实MCP边界验收。已完成；22项定向测试及真实工具探针通过。合并后303项回归有12失败/29错误，涉及旧H100路径及Landlock环境不满足，详见阶段记录。
3. MRV1同步调度、固定DSpark K7的9组dev baseline/192次正式请求已完成并独立审计通过；异步C32失败、瞬态监控断线及重试保留。
4. 三方向研究已停止，无可靠候选：D1启动失败；D2的16384/C1无稳定收益、12288启动失败；D3的graph profile失败、eager C1采集完成。启动/清理/格式/上游中断的修复及51项本地检查保留，不算科学收益。
5. 本轮最多3方向的执行器限制已到达，Claude预算未耗尽；GPT条件监督正常退出，无付费GPT请求。费用账本保持原200/500美元独立上限，不因正常收尾释放或重置历史预占。
6. 无候选冻结后独立终测已完成，仅基线：40条validation形成9组/142请求，0错误；AIPerf原始记录重算一致。不得把这些验证结果反馈给研究模型继续优化本轮，不能报告优化加速或精度无损。
7. 服务保留，健康检查200。既有eager trace的离线导出与质量审计已结束：6/8个rank得到timeline/算子表，rank1/4失败，562个原文件SHA不变，但有数据缺失警告，不能宣称完整瓶颈归因。源码身份/原生DSH/可信回执私有归档，公开只同步非敏感摘要。
8. 性能优化目标尚未达成；本轮封存后续应先补齐完整profile与可信源码option能力，不能仅靠三次方向额度就把未覆盖任务写成完成，也不能用已打开的验证集做调参反馈。

阶段文档：[Ascend执行与验收](docs/experiments/ascend-ctrip-dsh-20261109.md)。
串行筛选及终测不替代受保护controller的配对晋升；历史teacher参考不是已核实正确答案。

2026-11-10 接续更新：用户已授权持续优化和多路并行。原三方向阶段已封存；当前取消总方向数限制，三组完整八卡基线 profile 已获得，正在检验共享专家多流重叠。新增两路受限 DSH 分析，由科学 Master 分配互补主题；既有卡上实验保持单队列、完整恢复后再推进。并行分析先交付来源、成本下界、候选 option/补丁与验收计划，主研究复核后安排实测。保留累计 Claude/GPT 200/500 美元上限、开发集固定及新 holdout 封存，不把理论提案写成提速。实际进度见 HANDOFF 的 Ascend continuation 与部署目录状态。

---

# H100独立轨道：计划与已收口记录

## 最新专项：作者final的temperature>0验证（已收口）

- [x] 冻结stock/final、20公开dev请求、正温度top_k=-1/top_p=1及独立预算。
- [x] 6项CPU验收；唯一双H100兼容性任务code200/UUID/启动/终态分别确认。
- [x] 确认stock能随机采样；final首次0.7请求在作者greedy-only树路径报错退出。
- [x] 两次独立audit及配置/树SHA/原始请求/预算/清理复核；330 GPU秒，两卡释放。
- [x] 因兼容性未通过停止正式测速；无加速比/CI、无sealed或晋升，更新主页与交接。

详见[专项结果](docs/experiments/final-sampling-20261110.md)。1.0未在存活final上独立执行；
不修改作者方案以绕过限制，不结转余额，不改变下面其他主线的接续点。

日期：2026-11-09。新 session 先读 [HANDOFF](HANDOFF.md)，长期规则见 [AGENTS](AGENTS.md)。
以下保留H100主线；历史证据留在阶段文档，不继承其中已失效的“下一步”和资源授权。

## 核心目标

先用 Codex 复现自主研究过程：

**Master 分方向/预算 → direction 自主设计、执行、迭代 → controller 独立验收 → Master 决策。**

架构复现与数字复现分开。作者 final 的已有收益不是自主发现；dev 不是 sealed；
论文 sealed 参照仍为 2.13× [2.07, 2.19]，当前未独立复现该结论。
DSH 后置，不以更换框架作为当前研究的前提。

## 已执行：Direction自主最小选树候选

授权4 GPU小时/4小时/并发2卡，镜像/调度沿用；本轮新增GPU0，未准备待提交任务，不结转余额。
方案`docs/experiments/direction-candidate-20261111.md`；证据`logs/direction-candidate-20261111-a01/`及`a02/`。

- [x] 保存47份旧dirty，先行判据、受限候选入口和独立预算登记。
- [x] Master派发tree16-selection，Direction自主读stock/先写自检/实现/执行/修复。
- [x] 2700项CPU合成检查、6类分叉错误检测与两次独立重放；失败和逻辑续接完整保留。
- [x] 原生报告实际交付Master后stop，不提交无适配器的GPU性能任务。
- [x] 243项指定回归及公开副本复验、双次一致异常工程审计、14个子进程退出复核。
- [ ] 科学上未完成真实stock树适配、controller dev正确性或配对收益，不是完整Phase1/RSI。

工程异常收口独立标注，不冒充正常pipeline；下一阶段先另审真实分支执行与提交/回滚方案，仍由研究角色自主研究。

## 当前研究：接受量上界与匹配路径证据

用户批准验证，并要求给Master理论最大接受长度，支持自主研究draft tree/verify length。
方案`docs/experiments/acceptance-headroom-20261111.md`，目录`logs/acceptance-headroom-20261111-a01/`。
新1H100/累计1GPU小时/最长2小时及旧镜像/调度已确认；先复核已有证据，不为耗额度重复提交。

- [x] 保存47份原dirty身份；数学边界、冻结审计、graph映射及匹配请求测试先行，321项指定回归通过。
- [x] 三份旧stock证据用各自冻结源码audit通过；有限格20次重放、graph运行形状与同题2048cap计时匹配。
- [x] 新摘要核对8个capture/4123节点/10个profile；2865081个kernel中2725272个有记录ID映射，非关键路径覆盖率。
- [x] 新受限Master完成：1角色/3原生回合/19动作/9CPU额度/1自写CPU分析，树选择explore，其余三维diagnose后stop。
- [x] 三份冻结producer独立复算及graph摘要相同，2实际进程exit0，0新增GPU；原321项回归与原生审计通过。
- [x] 最终321项公开副本复验、双次原生审计和历史证据重算通过；源码/自身上下文归档、公开审查与发布准备完成，身份见publication回执。
- [ ] 科学上仍缺真实树完整成本，不能宣布最优N或实际收益；不把本阶段工程收口当树性能验证完成。

Master提出先确认最小可运行D/N/分支语义，再测完整step和实际进度；线性block16不冒充N16树成本。
本阶段复用已有证据，未准备或提交GPU任务；剩余额度不自动结转下一阶段。

## 当前研究：已有stock热点调用归因

用户批准按已有trace/stock源码自主核对热点GEMM路径、形状、dtype与暴露时间，GPU新授权0。
方案`docs/experiments/kernel-attribution-20261111.md`，目录`logs/kernel-attribution-20261111-a01/`。

- [x] 保存47份既有dirty身份；先行红测与只读ID关联、graph误归因/隐私/分页/权限/额度检查通过。
- [x] 接通`--attribute-kernels`与独立trace观察重放；研究版303项，最终版304项指定CPU联合回归通过。
- [x] 新受限Master自主BBuf/形状/源码/ID取证后stop；1角色/4回合/20动作/13CPU额度，无Direction或自写脚本。
- [x] 两次独立审计一致，2进程exit0、0新增GPU；三类GEMM与两条单次形状线索核对，不冒充完整模块归因。
- [x] 最终304项公开副本复验与双次独立重放通过；上下文/源码归档、主页/交接和公开审查完成，发布身份见publication回执。
- [ ] 科学目标仍缺graph节点映射与暴露时间，不能排序真实收益；不得将本阶段工程收口当优化完成。

下一步仅提案同工作量普通计时/profile与capture→replay映射，GPU预算另批，不自动补采或实现logits融合。

## 当前研究：Master端到端收益优先级

用户批准先评估可实现的端到端净收益再选方向，不直接实现上轮logits融合。
方案`docs/experiments/master-e2e-priority-20261111.md`，目录`logs/master-e2e-priority-20261111-a01/`。
只使用已有授权stock/配置/计时及公开知识；GPU0，不改裁判/规则/账本，不读final/sealed。

- [x] 249项先行回归通过；白名单两模型配置/启动参数/10条普通stock计时与profile分组，七份运行源码SHA冻结，TTY6160运行。
- [x] Master实际计算4机会的条件成本/收益边界并stop；工具help遗漏修复后，用剩余额度做一次有来源的逻辑接续复核，自主调用BBuf。
- [x] 合计4回合/37动作/15CPU额度/1脚本/1BBuf/0GPU，联合audit04/05一致；265项指定CPU回归通过。
- [x] 265项公开副本复验、213文件双次SHA归档、主页/交接和发布准备完成；提交/远端身份见publication回执。
- [ ] 科学目标未完成：仍未排出可信优化赢家，需同工作量归因/暴露时间。本轮已停止，下一阶段另审，不自动补采。

## 当前研究：知识增强的Master自主CPU实验

用户批准实际调研/机会比较/Direction自主实验/反馈决策，不再只验收联网或堆编排。
计划`docs/experiments/master-knowledge-20261111.md`，目录`logs/master-knowledge-20261111-a01/`。
复用已有受限入口和动态Campaign；不新增GPU，不读final/sealed，不改裁判/规则/账本。

- [x] 244项先行回归通过，冻结六份运行源码和30分钟/16回合/240动作/32CPU/2方向上限；前台TTY40175运行。
- [x] Master实际读3份公开资料并比较3机会；Direction自写两项CPU检查，额度拒绝后由Master自主continue追加，2次exit0。
- [x] Master按结果stop，2次独立原生审计一致，244项指定CPU回归通过；2角色/7回合/40动作/18CPU额度/0GPU。
- [x] 244项公开副本复验、187文件双次全SHA封存、主页/交接及发布准备完成；同步身份见publication回执，GPU收益仍未知。

## 当前排查：Master外部知识访问

用户批准排查现有公开检索/阅读的network_unavailable，先定位再最小修复；不新增GPU或代做研究。
计划`docs/experiments/public-knowledge-access-20261111.md`，目录`logs/public-knowledge-access-20261111-a01/`。

- [x] 分层确认DNS/代理收到200；根因是正文EOF后对关闭socket设置timeout，errno9被包装成网络不可用。
- [x] 先红后绿回归和一行EOF修复，不放宽公网/TLS/域名/路径限制；243项指定CPU回归通过。
- [x] 真实MasterAccess和新受限Master探针均完成搜索/两次读取；2条结果/1923与21812字节正文，原生审计两次一致。
- [x] 243项公开副本复验、61文件双次SHA封存、主页/交接和发布准备完成；提交/远端身份见publication回执，不冒充自主研究。

## 当前主线：Master动态研究决策（CPU）

用户批准：机会比较→最小取证→Direction自主CPU研究→Master按反馈修订/继续/改派/停止。
计划见`docs/experiments/master-decisions-20261111.md`，独立目录`logs/master-decisions-20261111-a01/`。
不新增GPU，不读作者final/sealed，不改controller/规则/账本，不接管其他专项。

- [x] 先写状态机/预算/反馈来源/隔离/回放的验收，冻结既有dirty身份；159项指定CPU回归通过。
- [x] 接通可复用动态决策状态机与受限CPU角色入口，不替Master预选研究方向；旧GPU流水线未切换。
- [x] 真实Master比较机会、接收历史负反馈后派发Direction并按其源码反馈stop；脚本额度拒绝，实际CPU脚本执行0次。
- [x] 242项指定CPU检查、两次一致独立审计；额度提示/近名反馈绑定修复只经工程测试，不冒充原生覆盖。
- [x] 136文件双次全SHA封存、主页/交接和242项公开副本复验；公开发布准备完成，提交/远端身份另见publication回执。

2角色/4原生回合/18获准动作，0新增GPU；实际没有revise/continue或新方向重派，相关分支仅fixture覆盖。
下一步先审核修复后真实廉价实验与GPU动态入口的接续，不由维护者代做缩块，不结转旧GPU预算。

## 已执行主线：Master自主源码提案与先行收益评估

用户批准执行，并新确认8 H100 GPU小时/12小时/并发2卡及既有镜像/WeaverDev/qiji/挂载/priority。
方案：[Master源码提案阶段](docs/experiments/master-proposal-20261111.md)，独立目录
`logs/master-proposal-20261111-a01/`；旧余额不结转，不接管并行长上下文或Ascend。

- [x] 冻结52个既有dirty文件身份，登记新预算与先行验收。
- [x] 明确四项必查：验证长度、送验token选择、kernel、端到端；每个源码提案须先评估净收益和新增成本。
- [x] 受控公开知识、接受量/成本证据、源码引用与提案来源验收；91项先行及371项最终指定联合回归通过。
- [x] 新Master自主获取证据、四维评估、源码级诊断提案；Direction自主实现/5924例CPU自检/真实双卡反馈，Master复盘并stop。
- [x] 独立重算与三任务终态核对，3445 GPU秒、峰值2卡、0活动GPU；10个进程退出事后复核，不提供Phase4打开许可。
- [x] 3555个证据文件双次SHA封存、371项最终及公开副本回归、公开审查完成；提交/推送身份另记publication回执。

接续Master自主重读源码，提出accept/bonus首次不匹配位置向量归约诊断，净收益保持unknown；
Direction自行实现/检查，两轮fresh及换卡、5请求/10pair/256cap测得0.995636×
[0.993251,0.998027]，不支持收益，自主停止。Integration无共享候选而停止；Kernel自主补采
stock profile并调用BBuf后因真实路径/形状仍未知停止；Master最终stop，不做独立dev gate或sealed。
首Master因来源字段错误停止后的逻辑接续明确归因维护者协议澄清，保留旧计数与原生回执。
收尾因跨父进程registry拼接导致main exit1，原失败保留；修复未来分父registry，
本次逐项事后核对原始birth/exit和实际进程消失，不冒充controller Phase4预打开许可。
目前证明源码提案/自主实验/反馈链路，不证明高效方案、真实组合/kernel优化、lossless或RSI完成。

## 最新最小离线诊断：长上下文收益收窄

- [x] 复用既有100pair/200份HTTP，SHA/轮次/换卡/直方图/冻结树身份核对，两次复算与篡改拒绝通过。
- [x] 核对TLV外层计数口径；final推进量中位数original→64K为12.950→12.588，未见整体崩塌。
- [x] 明确prefill与decode Attention仍无法分时；离线诊断完成，不宣称根因已证实。
- [ ] 若用户要求精确归因，另批小额资源后只补原始/64K固定题分时/trace，不扫N、不改final。

报告[最小离线诊断](docs/experiments/prefix-diagnosis-20261111.md)；新增GPU任务0，不结转旧额度。

## 最新独立专项：公开原题加干扰前缀（已收口）

- [x] 新8 H100 GPU小时／12小时／2卡和镜像/调度参数重新确认，不结转其他阶段余额。
- [x] 原题不变的50请求冻结、39项CPU检查、旧协议重算与4参考代码隔离控制通过。
- [x] 唯一任务code200/UUID与Job优先级核对，前台TTY40558；不重复提交。
- [x] 两轮fresh/换卡100pair，5条件TPS比2.179/2.028/1.945/1.462/1.164×；200输出/241695 token forcing通过。
- [x] 两次audit/工程复核/CPU质量评估一致；质量代理存在数学格式盲点，不宣称语义非劣。
- [x] 唯一任务Completed/exit0，7084 GPU秒、本阶段0活动GPU；39项指定CPU及公开副本通过。
- [x] 原始证据892文件双次SHA归档、公开发布准备；最终提交/推送身份以独立publication回执为准。

目录`logs/prefix-context-20261111-a01/`，方案[干扰前缀实验](docs/experiments/prefix-context-20261111.md)。
与Master自主研究隔离，不让研究角色参考作者final，不读取sealed或写晋升。

## 最新专项：冻结作者final的长上下文检查（已收口）

- [x] 用户批准新预算8 H100 GPU小时／12小时／2卡，已确认镜像和调度参数全部沿用。
- [x] 先行协议、32项指定CPU验收、3篇公开小说/15条精确长度输入及源码冻结。
- [x] 唯一任务code200/UUID与Running分别核对，Job优先级higher-priority-job；不重复提交。
- [x] 两轮fresh stock/final与换卡：2K/8K/32K/64K依次2.147×/1.818×/1.534×/1.319×；128K stock输入上限拒绝，不给加速比。
- [x] 48输出/94092 token forcing、4档×2轮正确性检查通过；两次audit及两次独立工程复核一致。
- [x] 唯一任务Completed/exit0，3708 GPU秒、0活动GPU；32项指定CPU回归复跑通过。
- [x] 原始证据305文件双次SHA归档，公开发布准备；提交/推送的最终身份以独立publication回执确认。

阶段目录`logs/long-context-20261111-a01/`，前台TTY94560已退出；
方案见[长上下文专项](docs/experiments/long-context-20261111.md)。
不扫N、不拆机制、不profile、不读旧私有题或sealed，不将本次诊断算作RSI或晋升。

## 已收口：按需stock profile与自主诊断

新授权8 H100 GPU小时／12小时／并发2卡；已确认镜像、WeaverDev/qiji、挂载、toleration
全部沿用，priority3。阶段目录`logs/stock-profile-autonomy-20261111-a01/`；不结转旧余额。
方案与先行验收见[本阶段](docs/experiments/stock-profile-autonomy-20261111.md)。

- [x] 固定公开workload/preset、collector、profile-only BBuf与研究请求反馈入口；147项指定CPU回归通过。
- [x] 单卡真实工程预检：首次失败33秒后修复；第二次Completed/exit0，613秒，真实trace/host独立CPU重算与BBuf通过，不改科学阈值。
- [x] Master自主分3方向；d1和Kernel分别自主申请profile并调用BBuf；d2/d3自写源码、自检及双卡诊断，均无可信收益。
- [x] Integration无共享候选而停止；Kernel观测后不猜测实现；Master最终stop，6科学角色/15原生回合/5次BBuf调用。
- [x] 五项工程缺口与格式重试谱系补验；250项指定CPU联合回归和排除旧dirty的公开源码副本通过，两次独立审计一致。
- [x] 六任务全部终态，7266 GPU秒/2.01833小时、峰值2卡；12个角色/辅助进程退出，无活动GPU，旧私有验证未读。
- [x] 6714个host可见产物两次全SHA复核；公开源码按白名单提交，GitHub同步身份以本阶段独立publication回执为准。
- [ ] 科学目标仍缺：合格候选独立dev、真实组合/kernel优化、正常final T3和多轮RSI。本轮工具链通过不改变这些未完成项。

下一步仅提案：补足热点kernel与真实调用路径/形状的可靠关联，再交Master自主选择研究。
不预设VERIFY优化，不补猜测ceiling，不复活旧角色，也不自动结转本轮余额。

## 已收口：BBuf角色接入、controller复核与真实全流程

用户已批准三个部分整体执行，并新确认32 H100 GPU小时／24小时／最多并发4卡，
镜像/WeaverDev/qiji/挂载沿用，priority=`higher-priority-job`。另授权必要controller/eval
维护者侧实现，不放宽规则；研究角色仍禁止读取sealed或修改裁判。
计划与验收见[本阶段](docs/experiments/skills-rsi-20261110.md)，唯一预算
`logs/skills-rsi-20261110-b01/resource-state.json`；旧余额不结转。

- [x] 先行计划、新预算、镜像与维护者权限确认；67项既有相关检查通过。
- [x] 工具broker与多角色执行器初版；controller故障/绑定/噪声复核和sealed协议fixture通过。
- [x] 真实source预检：第五次Completed/exit0，两轮fresh和换卡、10pair/20臂输出一致；
  五次终态共3196 GPU秒，原失败保留，不扩大文件权限，不再重复预检。
- [x] Master自主调用BBuf并分配3方向；3次真实源码诊断均无可信收益，6原生角色已停止。
- [ ] Integration无输入、Kernel证据不足，尚未完成真实科学组合/优化；分页修复后Master完整读证据仍stop。
- [x] 科学谱系与prefix审计通过；control03提交前10任务全终态，累计21170 GPU秒。
- [x] control02缺故障覆盖而拒绝后分离固定公开探针与私有forcing；同seed重跑，不放宽规则，旧证据保持。
- [x] control03 Completed/exit0：真实健康/故障回归及私有2048/4096上限forcing通过，故障尾部8272 token；stock/stock性能预期拒绝。
- [x] job内独立重算/2231文件封存、host公共SHA及终态复核；11任务35608 GPU秒，无活动GPU；公开源码副本316项指定测试通过。
- [ ] 科学候选独立dev、真实组合/kernel优化、正常final T3及多轮RSI未完成：本轮无合格候选，不用负对照冒充。
- [x] 预算/终态/独立审计、9326个host可见产物双次SHA归档及公开审查、主页交接完成；提交同步身份以publication回执为准。
- [ ] 下一主线先提案按需stock profile/真实形状能力，不自动新开GPU、不沿用旧余额，也不重开本轮私有题调参。

## 已收口历史：最小 Skills 离线接入与研究简报

用户批准：只使用已有授权 stock 证据，不新增 GPU、不继续 ceiling 补采、不启动科学角色；
完整 ceiling 不再作为研究硬前置。记录与验收：
[最小Skills阶段](docs/experiments/skills-diagnostics-20261110.md)。

- [x] 核对旧17任务全部终态；b16/b17被抢占，总计24942 GPU秒，本阶段0新增GPU。
- [x] 先写工程验收和逐阶段T0/T1/配对性能/T3边界，不改controller或科学规则。
- [x] 固定上游10文件SHA，真实stock profiler和计算估算通过；真实层归因留空。
- [x] 89391 kernel原始统计与旧记录核对、4项投影手算及52项定向CPU测试通过。
- [x] 研究简报及主页/交接更新，原始证据私有归档，公开发布身份以publication回执为准。

下一阶段先审核：Master据简报自主分方向→direction自主实验/修复→Integration→Kernel→
controller独立验收；不预设优化VERIFY，不以外部Skill复用冒充独立发现。
每个拟保留单项、组合、kernel变体均须dev正确性/token forcing与配对性能，最终冻结才用sealed。
后续GPU使用`--k8s-priority 3`（`higher-priority-job`），不保证免抢占；新预算/镜像另行确认。

## 已收口历史：Phase 0 ceiling证据采集

用户已批准执行，并重新确认16 H100 GPU小时、最长12小时、最多并发2卡；
沿用已确认镜像digest、WeaverDev/qiji、toleration及只读模型PVC。旧预算不结转，不接管Ascend。
详细口径及先行验收见[Phase 0计划](docs/experiments/ceiling-20261110.md)。

- [x] 阅读原PDF §3.1/§3.2/附录B，明确正文与附录的ceiling定义差异。
- [x] 有限lattice观测/重放、默认关闭与故障注入CPU验收：9项新测试及303既有回归通过。
- [x] 冻结10公开dev题/stock/实际源码及新预算，code200/UUID确认；prepare提前提交缺陷见阶段记录，已修复但原记录保留。
- [x] 两轮换卡on/off回归40pair/80臂行输出一致，20份完整请求profile覆盖通过。
- [x] 两次独立CPU审计及覆盖复核一致，80个故障副本拒绝；N32条件接受量+23.19%，不是速度收益。
- [x] 核对两任务终态，6908 GPU秒/1.918889小时，峰值2卡，331项定向CPU检查通过。
- [x] 5875文件归档两次全SHA通过，主页/交接更新；公开同步身份以独立publication回执为准。

此阶段不优化、不启动Integration/Kernel、不开sealed或写晋升；
没有最佳运行时预算或全kernel类floor时，完整ceiling必须保持未知。
本次诊断采集已结束，**完整Phase 0仍未完成**：三因子为null；缺kernel→工作量映射、
无干扰逐步时间与节点预算成本。下阶段先补这些依据，不把90.17% VERIFY工作比当优化收益。

## 暂停历史：源码 option 自主研究

最新接续：用户要求按完整多角色主线重新设计下一阶段，先提案再执行，暂不新增GPU提交。
9个预检任务均已终止，累计1996 GPU秒；尚无本阶段科学角色、源码研究或完整server配对结果。
最新ldconfig/自身子进程信号修复待复验。新提案须包含多个direction、Integration及Kernel，不能将源码入口本身当最终架构。

用户已批准执行并确认新上限：16 H100 GPU小时、12小时、最多并发2卡，沿用已验证镜像/WeaverDev/qiji及只读模型挂载。
本阶段独立计费，不结转旧64小时余额；不接管Ascend。验收先行见[源码研究计划](docs/experiments/source-autonomy-20261110.md)。

- [x] 核对交接、干净起点585b4d9、新资源授权和当前NorthJob CLI参数。
- [ ] 源码冻结、默认关闭=stock、CPU回执绑定和真实内核边界测试。
- [ ] 完整server可信GPU预检；小型GPU运算与UID保护已通过，不等于完整预检完成。
- [ ] Master自主选方向，direction自主实现/实验/修复，原始反馈闭环。
- [ ] 有候选才交原controller独立dev验收；允许无收益结案。
- [ ] 预算/终态/证据审计、主页与交接、公开审查和Git同步。

## 已收口历史：真实stock引擎自主探索

用户已批准：累计64 H100 GPU小时、最长24小时、最多并发8卡；失败与冷启动计入。
沿用已确认镜像digest、WeaverDev、qiji及只读模型PVC；不继承旧阶段尝试额度。
验收与范围见[本阶段记录](docs/experiments/engine-autonomy-20261109.md)。

- [x] 核对交接与干净起点8bd6029，记录本次授权；旧阶段证据不覆盖。
- [x] 真实引擎broker、冻结身份与持久预算CPU验收：303既有回归+10新测试通过。
- [x] Master自主选方向，direction自行设计、请求、分析与迭代；6次诊断后主动停止，Master也已stop。
- [x] 12与10交原controller独立dev gate，均通过且输出一致，无晋升；12为1.085260×，10为1.063766×。
- [x] 两次全谱系独立审计一致：14原生回合/30工具动作/5CPU/6GPU诊断，另2独立gate；8任务/6角色均终止。
- [x] 321CPU测试、两次独立审计、6类篡改拒绝、任务/角色终态与25836文件归档通过。
- [x] 主页/交接更新与公开审查通过；最终Git同步身份以publication目录的单列回执为准，不改旧归档。

先开放已验证startup option，不直接执行任意源码overlay；诊断不冒充正式验收或算法发现。
本阶段保守22730 GPU秒（6.314小时），峰值2卡，原上限64小时/24小时/8卡未超；不继续提交。
最终机器状态`logs/engine-autonomy-closeout-20261109-d01/stage-result.json`明确无sealed、账本、晋升或完整RSI。
下一阶段先提案受限源码option通路获批，不能把现有参数调优当新算法发现，也不自动结转余额。

## 已收口历史：direction自主修复与完整微实验

用户已批准完整探索窗口及沿用镜像/WeaverDev/qiji/只读模型挂载。
记录见[第三阶段](docs/experiments/gpu-autonomy-stage3-20261109.md)。

- [x] 新阶段1H100 GPU小时、最多同时1卡、最多3次900秒研究任务；CPU/动作额度单列，由Master分配。
- [x] 25项定向/303项全量CPU回归通过；旧阶段SHA和来源审计通过，冻结本次实际执行源。
- [x] Master自主继续原方向，分配24动作/4CPU运行/2GPU尝试；direction已开始自行修改筛选。
- [x] direction自行修复筛选，18个CPU回归例通过，复现旧错并绑定当前科学代码SHA。
- [x] 真实GPU实验及独立进程研究筛选通过，原协议延迟数据完成；Master主动stop，不追加运行。
- [x] 两次来源审计一致、CPU独立重放两次、原始延迟重算及6类工程篡改拒绝通过；容器和角色均终止。
- [x] 完整归档与公开内容审查通过；最终Git同步身份单列回执。

入口`logs/gpu-autonomy-run-20261109-c01/`，准备/可信提交入口`logs/gpu-autonomy-stage3-prep-20261109-c01/`。
不代写科学代码，不放宽原判据；阶段内通过request_budget交Master自动重分配，无需逐次找用户审批。
GPU前要求自身CPU成功回执与实验/筛选脚本SHA匹配；原阶段错误保留，不算新发现。
本次实际未触发预算重分配。累计4研究回合/8动作/1CPU/1GPU尝试/10usage事件，非精确API或token计费数。
任务job-4fdd307bbdb9-20261109202445，code200、Completed/exit0，保守43GPU秒/容器26秒；两原生角色关闭。
第三阶段微实验目标达成，不等于完整Phase1/真实模型RSI。无候选、controller验收或晋升；原容差、长度和计时脚本不变。
机器状态`logs/gpu-autonomy-stage3-closeout-20261109-c01/stage-result.json`分开上述字段；后续由Master评估真实stock路径映射，先提案获批。

## 已收口历史：依赖复验与原方向自主接续

用户已批准，资源参数已确认；记录见[GPU自治第二阶段](docs/experiments/gpu-autonomy-stage2-20261109.md)。

- [x] 确认1H100 GPU小时总上限，1次600秒依赖预检、最多2次1200秒研究；不继承旧余额。
- [x] 新资源契约、只读模型挂载及新阶段来源记录通过19项定向/297项全量CPU回归。
- [x] 真实GPU依赖预检通过，独立核对原始输出和8类权限探针。
- [x] Master自主决定接续，direction请求两次真实GPU研究；可信预加载后自行诊断其筛选头维度错误。
- [x] 独立审计、重复重放一致、5类协议篡改拒绝及资源终态核对通过。
- [x] 最终38定向/299回归通过，更新主页/交接；公开同步身份另记回执。
- [ ] 首次有效数值筛选/延迟数据；当前目标未达到，不把筛选错误当假设证伪。

本阶段已停止并收口：预检job-2ea20f106d5c-20261109191521成功，研究job-d8bd211a0273-20261109192612与
job-258e42aa7878-20261109193328均exit1。先是FA3延迟加载的子进程探测被拒，可信固定依赖预加载修复后，
由direction自行定位其GQA参考未按查询头展开；尚未修正或复验，无延迟数据、候选或晋升。
累计15研究回合/8动作/0研究CPU/2研究GPU尝试，另1次预检；保守134GPU秒、容器67秒，3600秒上限内。
8个角色进程关闭、3任务容器均终止；停止因尝试上限和Master决策，不是GPU时间耗尽，不再提交。
机器状态`logs/gpu-autonomy-stage2-closeout-20261109-b01/stage-result.json`区分工程推进与科学目标未达。
下一阶段先提案获批：由direction自行修复筛选并CPU自检，再由Master决定是否申请新GPU预算；不由主助手代写研究。

## 已收口历史：最小权限与首轮真实GPU实验自治

状态：**有限GPU执行/失败反馈链路已验证；有效科学实验未完成**。两次GPU尝试及16研究回合已用完，Master已停止，不再提交任务。
记录：[阶段与失败证据](docs/experiments/gpu-autonomy-20261109.md)。用户已确认原镜像digest和WeaverDev项目。

- [x] 写验收与预算，复用受限Codex入口，不单建上下文框架。
- [x] Master自主选方向并分配预算，direction自行编写实验与筛选脚本，完成CPU语法检查。
- [x] 保留旧步数上限故障；修复计数及复核写死stop问题，恢复时扣除已用动作，旧结论不覆盖。
- [x] 30项定向及291项全量CPU回归通过；无GPU证据时严格自治验收拒绝。
- [x] Master自主追加原阶段剩余3动作；direction读回脚本和核对stock接口后额度耗尽，Master再次停止。
- [x] 将主助手自设动作上限由24校准为28，GPU/16研究回合等资源上限不变，不新增不必要审批。
- [x] Master自主接续，真实1H100两次提交；GPU权限探针/原代码与输出绑定通过，错误原样交回direction。
- [x] Master授权一次纯执行器缓存修复重试；两次科学脚本均在依赖导入时失败，未完成screening，Master最终停止。
- [ ] 有效GPU数值筛选/微实验数据，及真实SGLang整模型实验。
- [ ] 有候选时交controller独立验收；不以agent脚本筛选替代裁判。

当前累计16个模型研究回合、26个研究/执行动作、2次CPU运行、2次GPU尝试；后台API调用量不由这些回合数推断。
GPU总上限仍2H100 GPU小时、最多同时2卡；新执行单元为1H100/128Gi/26分钟硬期限，最多2次GPU尝试。
两任务容器均Failed/exit1/Job Aborted；按创建至终止保守计77 GPU秒（容器合计31秒），原2GPU小时内。
十个原生角色进程均已关闭，canary/输入未变；科学脚本及筛选判据始终原样复用，不改写为人工设计。

### 验收、阻塞与接续

- 可执行命令及证据目录见阶段记录；controller/eval/账本/记忆/stock不变。
- 两个真实GPU回执均通过独立原代码/输出/权限/预算审计；scientific_screens_passed=0，不能宣布科学实验或完整Phase 1完成。
- 缓存写权限已修；随后暴露的/usr/local/cuda只读缺项也已做最小修复，32定向/293全CPU回归通过，**该最新修复未GPU复验**。
- 下一阶段先提方案获批，复验运行库依赖后由Master/direction自主继续原实验；不新增方向、强求正结果或恢复旧补采。
- 公开同步只发布通用实现、脱敏状态和证据索引；不发布方向脚本、原始模型/实验输出或私有上下文。
- 收尾复验：32定向/293回归、两GPU回执独立审计、重复审计一致、两次科学脚本SHA一致、10角色关闭及保护目录零改动通过。
  机器状态`logs/gpu-autonomy-closeout-20261109-a01/stage-result.json`分开记录链路通过与科学实验未完成。

## 已完成：权限验收收口与公开同步

状态：本地代码/证据及公开发布检查通过，用户确认的组织origin已核对；最终同步身份以本阶段回执为准。
详细结果见 [阶段记录](docs/experiments/codex-boundary-20261109.md)。

- [x] 核对交接、已有执行源和真实非敏感权限探针，不重跑已完成研究。
- [x] 17 项权限定向测试通过；真实探针两次独立审计均与原结果字节一致。
- [x] 明确适用范围：新受限入口通过有限 canary 验收；不扩展到旧 spawn 接口。
- [x] 对齐 AGENTS 分工，建立本计划及下一阶段提案。
- [x] 278 项完整 CPU 回归通过；审计与执行身份复核通过。
- [x] 更新主页/交接，明确本次0GPU、下一阶段未授权。
- [x] 用户确认公开及组织转移，发布审查、278项CPU回归和旧证据复核通过；原私有授权阻塞解除。

收尾：按[公开同步记录](docs/experiments/public-sync-20261109.md)审查全部待发布提交，更新授权并推送既有origin。
最终版本身份及同步结果记入 `logs/public-sync-20261109-git-sync.json`；原阻塞回执保留，不改写历史证据。
不更改仓库可见性，不把公开授权解释为GPU授权。

### 范围、验收与停止

- GPU 预算 **0**；本次仅重放既有真实探针，不新增模型研究轮。
- 验收命令见阶段记录：定向/全量 CPU 回归、两次独立审计、冻结源码 SHA、保护目录零改动、文档检查和远端提交核对。
- 不改 controller/eval/账本/记忆/作者实现；不读 sealed 或凭据，不恢复人工接受历史补采。
- 若证据不匹配、内核拒绝失效或回归失败，则保留原失败、先定位，未通过项不得打勾。
- 证据目录：`logs/codex-mainline-closeout-20261109-a01/`；真实探针：`logs/codex-boundary-live-20261109-a02/`。

## 历史提案：最小真实 GPU 自主实验（本阶段已获批准并执行）

详细流程/资源/停止条件见 [下一阶段提案](docs/experiments/codex-gpu-autonomy-proposal-20261109.md)。
本节仅保留已执行阶段的原提案，不是当前待批准任务；当前下一步见本文件“验收、阻塞与接续”。

1. 接好受限研究角色 → 可信资源入口 → GPU 执行/持久反馈链；先 CPU fixture 验收拒绝、预算和不重复提交。
2. Master 根据授权 stock 证据自行选 **1 个方向**；direction 决定实验、代码及是否需要 GPU。
3. 重新核对镜像、项目/队列/PVC 与总预算后才提交；不继承旧补采授权。
4. direction 读取真实退出码和证据，自行继续、修复或停止；Master 复核并结案。
5. 有候选才交独立 controller；无候选可正常结束，绝不把诊断数据直接当晋升结果。

原资源提案（本阶段已授权，停止后不延用）：总上限 **2 H100 GPU 小时**，最多同时 2×H100 80GB；
最多 2 个有独立身份的任务尝试，失败和冷启动计入总预算；具体内存/PVC/镜像提交前核对。
两个尝试不是两份预算。若预算不足以形成完整反馈，停止并报告，不自动追加。

### 后续主线

先解决实际依赖导入并获得有效科学数据，再按证据推进后续主线；失败反馈链路不等于真实模型RSI完成。
**没有批准不接入/启动下一阶段 GPU 实验**。
不预定接受长度预测、VERIFY 优化或作者 final 机制，不提前建 sealed，不要求发现正收益。

Ascend 监听接续：八卡两步 metadata/manifest 诊断已完成并恢复。前缀复用 CPU 上界审计完成，下一步由 Master 解决全部缓存状态恢复支持，再决定是否申请配置实测；上界不能冒充命中率或提速。49 项定向 CPU 检查通过，本地监听日志不等同自动聊天推送。GPT 保守预占与实际网关变化分列，500 美元上限不变。

Ascend 当前终态：累计 GPT 保守预占保护已触发，外部科学角色停止在未完成的 D5；没有新卡上缓存实验或收益。保留轨迹、服务与本地监听，不自动增加费用上限。

Ascend 最新接续：用户已明确将GPT累计上限调高到1000美元，保留此前全部预占和费用，旧拒绝归档；同一D5方向恢复，51项定向检查通过。以当前私有状态判断活跃与否。

Ascend 监听阶段：D5 APC 和 D6 TP4/DP2/EP8 预检均 needs_evidence、零卡上实验，不能误报优化失败或成功。Master7 接续选择必要证据，源搜索流不完整导致的单次故障已按回执恢复；全部费用/工具额度/轨迹保留。继续按实际私有状态监督，尚无新吞吐结论。

Ascend 当前能力准备：Master7 请求完整 APC 遥测。第一阶段初始化 adapter 经独立受限 DSH 审查仅准入 capture-only，66项定向CPU检查通过，可信 caching-OFF/零生成的8卡采集正在进行。等待实际终态与基线恢复；之后仍须补齐请求遥测和 OFF/ON 对照，不将结构metadata当完整能力或性能优化。

Ascend 当前：初始化结构采集8/8、每卡6组通过，但首次stock基线恢复OOM，已清理本次所属失败进程。用户要求维持串行等待；恢复脚本仍排队，不中断另一任务。当前不启动研究API，不声称服务健康。69项CPU检查通过；恢复后才向Master分享partial OFF事实，再决定补齐完整遥测/输出对照。

Ascend 最新：同配置第一次恢复重试成功（32/32图、8 worker、health200、无插桩），Master7接续已测partial OFF缓存组事实。原捕获任务仍保留初次恢复失败状态，post-finalize recovery单列；不得误写为无故障。enabled推理仍需单独准入，74项CPU检查含未接入比较器原型，不等同模型精度/性能结果。
