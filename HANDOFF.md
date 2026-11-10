# HANDOFF — 交接给新 session

本文件是唯一入口。仓库并行记录H100/Codex与Ascend/DSH；先按本次用户授权选择轨道，权限、预算、数据和待办不互通。
H100任务直接看下文“H100接续点”，不要接管Ascend进程；Ascend部分保留远端会话既有记录，本次H100会话未重跑或复核其科学实验。

## Ascend轨道接续点：本地开发集 baseline → DSH＋Claude 5.5 自主研究

用户已授权：选定100条本地agent数据（dev60/validation40），先baseline，再DSH＋Claude 5.5运行SpecPilot；Claude总额上限200美元，预算保护触发后用`gpt-6.1-sol`接续，GPT独立上限500美元。不得使用`gpt-5.5`；MRV2不是要求。
唯一阶段记录：[Ascend执行计划与验收](docs/experiments/ascend-ctrip-dsh-20261109.md)。当前源码归档在`harness/ascend_dsh/`，真实运行目录在部署工作区`profiling/specpilot-ctrip-dsh-20261109/`。

- 本地8卡910B2C，V4 Flash W8A8，MRV1、图模式、固定DSpark K7。异步调度的C32失败已保留；改同步调度建立新baseline，不能把这个修复记成优化收益。
- 9组dev AIPerf baseline/192次正式请求已完成并独立审计通过；C32短/中/长输入输出吞吐约288/210/185 tok/s，中/长档各1次输出到上限。瞬态metrics连接失败及恢复证据保留。
- DSH预算/会话恢复及真实MCP受限工具探针已通过；22项本地定向测试通过。CPU隔离使用chroot/降权/seccomp，本容器Landlock不可用。
- 真实DSH科学Master已完成三方向并stop；状态`research_finished`、campaign/终测均complete。无可靠候选或新收益；原生会话/MCP/逐调用费用均落盘。三方向上限为执行器阶段限制，停止不是API预算耗尽，GPT未付费启用。
- Master选方向，Direction自主读源码/写CPU分析/提交配置或profile实验；每个方向最多3个NPU实验，两模型阶段合计最多3个方向。各阶段共享各自200/500美元保守预占上限，不重置先前费用或角色分配。源代码patch仅提交独立审查，不自动部署。
- GPT接续代码为`gpt_handoff.py`，实际状态看`handoff/state.json`；独立账本`billing-gpt/`只在交接时创建。原生DSH pi-ai Responses、xhigh、store=false、直连网关；禁止5.5路由。36项定向检查通过，离线3次请求=3次预算准入，真实MCP调用/加密reasoning重放/跨进程恢复通过。尚未做GPT付费接口验证，不把离线fixture写成真实GPT科学运行。
- 首方向16384 prefill预算候选启动失败，无候选吞吐，基线恢复成功。Claude方向报告先输出截断，再返回含一个多余根括号的完整答案；`resume_claude.py`从原会话恢复，后者仅删除一个括号并保存原始回执SHA，无科学数值改写或重复NPU实验。Master继续判断；完整失败/恢复轨迹保留。
- 2026-11-10：D2的16384/C1已完成，每档2请求，短/中/长吞吐53.38→54.92、55.49→58.59、51.24→47.78 tok/s，TTFT改善均不足2%；自然EOS输出长度有差异，无稳定收益。12288/C1在aclnnCumsum图捕获时报错，按已核对PID取消可信runner以执行其自身清理，基线已恢复且/health=200。第二方向报告no_gain，但其部分因果解释未独立证实。
- 发现调度竞态：runner先写failed，再恢复基线，旧broker提前返回，方向报告提交时cleanup检查使研究停止。`experiment_lifecycle.py`将此阶段呈现为restoring_baseline，调度器等待实际收尾，保留已完成报告；42项检查通过。恢复复用D2完整回执，不重复方向API或实验，工具动作21、实验2次原样保留。失败的实际启动日志和人工取消依据通过受限证据交Master，避免只看到泛化的cancellation。
- Master接续后另遇NorthGate上游60秒停止发送（原生turn/end code=SERVER），未完成第三方向决策；这不是预算耗尽。`resume_claude.py --resume-upstream`从原会话继续，后续仅对这一已确认错误最多额外重试两次；新请求逐次预占，不重复大段上下文或重置账本。45项检查通过，历史失败回执保留。实时角色/进程以state和supervisor为准。
- 恢复后的Master提出stop/no_gain，答复末尾JSON代码块前有说明文字，已补充终端代码块解析，原答复不改。该提议未被当作任务完成：两方向只覆盖prefill预算，本轮尚未执行用户要求的profile。按原任务要求发起一次明确记录的覆盖复核，剩余一方向仍由Master自主选择诊断，允许无收益结论；不得强迫正结果或声称这一督导修正是模型独立发现。复核依据/原提议SHA保存在`research/master-stop-coverage-review.json`，validation保持未打开。
- D3首个profile（名字含c32-baseline）在8192配置的NPUGraph capture中发生aclnnCumsum/worker-init失败，trace数量0；研究进程仍在等runner恢复基线。新增`startup_guard.py watch`仅在命中两类致命标记且runner argv/PID出生时间/候选归属均核对后SIGTERM该runner，由原finally恢复；不重置设备或影响别的任务。此次实际runner在guard启用前已自行失败，未发送信号，后续故障才由guard自动处理；这一区别在注释回执里明确。
- 关键口径纠正：冻结`profile_request`只采一条中长度请求、C1、max_tokens=128，忽略screen_concurrency，不能声称C32或长输入trace。已通过本次失败的受限证据向存活Direction披露；新broker明确能力并拒绝profile/C32提交（已加载的旧MCP进程不假称热更新）。51项本地检查通过，新增guard/范围检查不是已经获得性能提升。
- `research/supervisor.json`与`handoff/supervisor.json`区分研究进程和条件切换进程。仅持久化Claude预算不足事件可触发GPT；普通错误需要处理后重新挂起监督，Master正常停止或validation冻结后不启用GPT。不要重复启动已有进程。
- 全机flock串行协调独立量化任务，不抢占它们。服务在实验后恢复。不能重复启动已有监督进程。
- 2026-11-10 02:10前后：无候选冻结后独立终测已完成，仅baseline臂，40条validation形成9组/142次正式请求，0错误；原AIPerf记录重算全部一致。validation已打开，不再把结果回传给研究角色或恢复本轮调参；服务保留且健康检查200。
- D3第二次eager/C1/mid/128采样完成，原始562文件约955 MB。未自动导出是torch-npu禁止daemon内解析；主助手随后离线复制导出，得到部分timeline/CSV，但发现TLV数据缺失警告和部分rank解析失败。离线收尾为partial_export，6/8个rank成功导出、rank1/4失败；见`offline-profile-analysis/state.json`，562个原文件SHA复核未变；导出在`/data/northinfer-profile-artifacts/ctrip-d3-eager-20261110`，避免写满工作盘。不能用部分事件推算完整通信占比、关键路径或理论收益。
- 本轮模型报告用均值/中位数重建的prefill/decode占比、约94%排队和overlap解释均未获trace独立验证，不能作为实测phase分解。研究收尾不代表用户的优化/profile目标已达成；后续应先补齐可信profile与真实源码option能力，保留本轮验证隔离。研究/预算切换/启动监测/离线导出监督进程均已退出，仅服务保留；不能对用户声称仍在后台优化。
- 合并最新H100提交后，仓库303项回归在此容器未全过：12失败/29错误，涉及缺失旧H100固定路径和Landlock不可用。不要将新22项定向通过写成仓库全绿；未修改旧controller/eval/ledger/memory。
- 上述串行实验不写论文配对晋升账本，不承诺正确率/无损。公开提交不含数据内容、原生研究轨迹、权重、密钥或计费原始日志。


## Ascend continuation — 2026-11-10 用户要求继续优化

当前真实运行目录：`/data/northinfer-specpilot-cont-20261110`。三份 graph 基线采集（long/C32 prefill、long/C32 decode、long/C1 decode）均完成八 rank 导出，无导出丢数据告警。C32 decode 触发时实际仅 7 请求仍活跃、25 已完成，不能称稳定 batch32。D1 因 provider refusal 缺少模型最终报告，保留原轨迹，由督导仅按回执收口，未重复 NPU 实验。D2 共享专家多流重叠候选已完成八 rank 导出，正在恢复基线；尚无无 profiler 的吞吐收益。压缩 timeline 均有 SHA 回读验证，原始采集与 kernel CSV 保留。

- 用户新增授权多路并行。`parallel_research.py` 启动科学 Master 分配两路互不重复的源码/trace/CPU 分析，与原单路 NPU 研究并行；状态见 `research/parallel/state.json`。分析角色经 broker 禁止 launch/wait NPU，只能读授权源码和 SHA 固定的既有 dev CSV、运行隔离 CPU 分析和提交待审补丁。两路产出由后续主研究角色复核并串行实测；提案不是测量收益。
- 并行两角色现已实际启动并各执行了 broker 源码/证据读取：长 prefill 的 sparse attention/indexer 数据流，以及本地 HcPre/HcPost 中间张量开销。规划结果仅因 topic 名称 42 字符超出入口 40 字符限制被拒，放宽至仍满足 broker 80 字符角色上限的 60 字符后，原模型 JSON 原样验收复用，未重复付费规划。Claude 预算拒绝已触发，主研究和两路分析现共用获授权的 GPT 阶段，未改动原账本上限。

- 两路继续共用原 Claude 200 美元保守预占账本；只有持久化 Claude 预算拒绝出现后，可信调度器才能启动共享 GPT 500 美元阶段；不改写主研究状态或中断其在途实验。不重置额度，不提前切换模型，不开放旧/新 validation。原生 DSH、MCP 和逐调用轨迹继续保留。
- 已纠正 D2 Master 的归因：HcPre/HcPost 是本地 hyper-connection 运算，不能算 HCCL；不同算子族 union 相加不是关键路径占比。重叠优化不要求 AllReduce 次数下降，需实际重叠和无 profiler 计时。督导来源与纠正单独存档，通过新 broker 的证据回执向主研究角色共享；不声称旧 MCP 进程热加载。
- 并行入口的 8 项新验收覆盖 NPU 禁止、共享 CSV SHA/路径限制、角色互不读取报告、两方向分配、截断续接和预算交接边界；连同既有相关验收共 21 项通过。源码快照不含原始数据、轨迹、计费或凭据。

- 用户明确要求持续优化；本地新执行器取消三方向总上限，仍保留逐方向资源分配和统一NPU锁。Claude累计200美元、GPT独立500美元上限原样保留，Claude账本直接复用。
- 新DSH Master/Direction已启动，真实进程与阶段状态记录在部署目录；首方向选择graph/C32成本归因，尚无新的NPU测量或收益。
- 已修正profile工作负载能力：实际C1/C8/C32、短中长输入、有界worker-step窗口、串行离线导出和八rank/数据丢失检查。8项新CPU验收及5项原startup-guard检查通过，NPU能力尚待实测。
- 旧validation已经打开，继续研究不读取或使用其结果；另冻结40条未使用的原validation分区请求组，仍不开放给研究角色。
- 源码快照见`harness/ascend_dsh/continuation/`。此更新不修改H100轨道、正式controller/eval/ledger，也不声称论文复现或性能提升。

- 后续回执：两路分析报告均已完成。A1 的原回答是引导句紧接完整 JSON，解析失败已按原始 native receipt 离线恢复，科学字段未改、未重复 API/NPU；`parallel_research.py` 增加有界终端 JSON 解析。A1 指出 Hadamard 缩放→动态量化的约 256 MiB/观测大调用中间读写是待核实融合点；尚无可部署 patch 或实测收益。A2 对 clone/缓冲复用保持 needs_evidence，CPU参考仅说明别名风险。
- 共享专家多流重叠的八 rank 诊断 span 约 27.278 秒，原 profile 约 24.929 秒；不视为无 profiler 吞吐对照或因果退化定论。随后的 shared-expert DP 配置在图捕获/GroupedMatmulWeightNz 阶段失败，guard 触发原 runner 清理，恢复状态以 state 的 completed_epoch/baseline_restored 为准。
- 主助手发现已安装 AscendC C++/头文件实际存在，旧 Python-only broker 导致研究角色无法阅读。新增只读 `ascendc` source tree 和受限源码后缀，保持隔离/无 NPU 执行；已启动 `parallel-b1-hc-kernel-contracts` 延续 A2 核查，要求先证明源码与 910B/npu_hc_pre_v2 的对应关系，不把 arch35 路径直接套用。角色预算 24 工具动作，共用既有 GPT 账本；旧会话不声称热加载新能力。24 项相关定向检查通过。

- 之后主研究因 native 会话累计内容超过 512 KiB 请求准入上限退出；原样重试不能修复该错误。它的 needs_attention 状态又使并行已准入请求的 settle 检查失败。两类原始错误和轨迹已保存，并非设备故障或 GPT 预算耗尽。
- 已修复：`gpt_context.py` 在明确 input-byte-limit 错误后创建有来源/SHA 的有界检查点和新 native session，保留原 broker role、动作计数、scratch、实验归属与累计费用；最多两次运行中 rollover，不扩大字节上限。主调度恢复未完成 direction 时复用已批准的 Master 分配，不重选/重跑。settle 可在主研究暂停后完成已准入请求记账，reserve 仍执行原阶段/预算/validation 门禁。
- 已恢复原 D2 主研究与 `parallel-b1-hc-kernel-contracts`，实际新工具记录已出现；此次恢复未提交 NPU 实验。27 项定向检查通过，原生实跑仍需继续监测；完整 native 日志与新的 session-routing/checkpoint 私有保存。最新 supervisor 身份与研究状态以部署目录为准。

- D2 与 AscendC follow-up 已正常提交完整报告。D2 撤回此前 2.2 秒/5–9% headroom 推测，确认部分共享专家重叠但未证明增量收益；shared-DP 图捕获失败原因未确定，未跑 AIPerf 候选。AscendC 报告发现条件性的 FP32 workspace staging，但 v2 binding/已加载二进制/910B tiling 对应仍缺，未提出可部署 patch。
- Master 3 选定 indexer scale→quantization 暴露成本核查，因 Master 不能读取既有 profile 而请求能力。已增加只读、SHA 固定的已完成 profile CSV 授权，Master 不获得 NPU/CPU 执行能力；direction 保留原限制。`profile_dependency_export.py` 对已完成基线的八卡 CSV/压缩 timeline 做离线导出，涵盖形状匹配的量化/相邻算子、全部 flow/event/phase markers；不会凭时间相邻推断内存依赖或完整关键路径。
- 首卡 672 个匹配调用的 scale/quant 服务时间分别约 0.101617/0.256264 秒，合计约占该 24.929 秒诊断 span 的 1.44%；不是可实现收益、全模型收益上限或 phase 分解。其余卡及相关事件正在导出。首轮因单个派生 CSV 超过 60 MiB 中止，原文件保留；修复为分片并逐卡 checkpoint，未重跑 NPU。31 项定向检查通过。
- 离线进程状态见 `research/profile-dependency-export/state.json`，完成八卡导出后自动恢复仍处于同一 needs_harness_capability/round3 的主研究；若状态发生变化则拒绝自动恢复。不要把此时的离线分析说成 NPU 压测仍在进行。所有新产物/轨迹/计费仍留私有部署目录。

- 八卡离线导出全部完成，每卡 672 对匹配调用；scale/quant union 约 0.349826–0.369435 秒，相对约 24.929 秒诊断 span 为 1.40–1.48%。每卡扫描约 303 万 timeline 事件，flow/event 原始记录可读；没有 phase marker，不据此构造完整关键路径。Master 已完成更深入 sparse-attention 源码报告，但返回 direction 型报告造成主调度拒绝，原报告与失败完整保留。
- 找到续接缺陷：旧检查点覆盖当前角色请求，格式重试又只保留泛化提示，丢失 Master 输出 schema。已保留长请求头尾、把当前角色/输出要求追加到 checkpoint 之后，并让格式重试保留原任务；Master schema 在 invoke 内校验。33 项定向检查通过，已恢复原 Master 3；不重复 NPU 实验或重置计费。
- `collect_binding_evidence.py` 已通过实际安装扩展读取 HC pre/post、sparse-attention、dynamic-quant 四项注册/schema，并被动检查服务 worker 的库映射/inode/SHA。检查前后 torch.npu 均未初始化，未执行模型/算子或重启服务。独立 PR 验证 build 的两个扩展 SHA 与当前服务不同，不混用其性能/源码身份。新增 `binding_reference` 只读 stock csrc 源码树，明确它是参考而非已加载二进制的来源证明。新证据位于私有 `research/operator-binding-evidence.json`，不提交原始回执。

## 以下为H100独立轨道，不混用Ascend资源授权


> 本文件是**唯一的入口**。新 session 读这里，不要试图读旧对话。
> 最后更新：2026-11-10 北京时间（真实stock参数探索与两份dev联合验收通过，Master主动停止；完整RSI未完成）。

## H100当前接续点：Phase 0诊断采集收口，完整ceiling仍缺

- [Phase 0诊断](docs/experiments/ceiling-20261110.md)采集与复核已收口；完整Phase 0尚未完成，三因子仍为null。
- 新资源授权16 H100 GPU小时/12小时/最多并发2卡，沿用已确认镜像/WeaverDev/qiji/只读模型PVC，旧余额不结转。
- 原PDF已读：正文§3.1用best-first最佳预算及60%/90% floor；附录B历史数值用oracle/full-peak，不能混用。
- 准备有限top16 lattice条件重放、独立无profiler计时及完整请求kernel profile；缺失最佳运行时预算、
  完整byte/FLOP工作量或匹配无干扰步时间时，三因子/ceiling仍为null，不用普通profile冒充。
- 唯一预算为`logs/ceiling-run-20261110-a01/resource-state.json`，两个任务均已终态。
  首任务`job-b1bf6f83e255-20261110102708`身份适配错误/exit1，1114 GPU秒；
  第二任务`job-ca3363cd2236-20261110104035`Completed/exit0，5794 GPU秒；总1.918889 GPU小时、峰值2卡，无余额结转。
  40pair/80臂行全部输出一致；20份完整profile的5308提交步/5328 VERIFY标注覆盖20/20通过。
  20份真实lattice重放、80故障拒绝、两次独立CPU审计与覆盖复核一致，331项定向CPU检查通过。
  block8/top16格内stock tau=4.860407，N32=5.987720、N128=6.426686；只是条件接受量，不是速度收益或全局tau_best。
  下一阶段先补kernel工作量映射/无干扰逐步时间/预算成本，不预设VERIFY优化，不启动科学角色或sealed。
  5875文件/693033124字节两次全SHA通过，清单SHA为`78aba017df807f0d94af73f86333febc380234e2bef186e3ec922dd068f5e394`。
  Git同步回执单列`logs/ceiling-publication-20261110-a01/`，原始证据不入公开Git。
  prepare缺return导致首轮提前提交的缺陷及修复已披露并留证。旧源码通路修改保留，9次旧预检已终止，不恢复为待办。

## 历史接续：用户要求按完整多角色主线重新规划

- 本次最新请求是重新设计下一阶段，不是批准新增Integration/Kernel/sealed实验；先给方案审核，暂不新增提交。
- 9次可信基础设施预检均已终止，无活动GPU预留；保守累计1996 GPU秒。尚未启动本阶段科学Master/direction，尚无源码优化或完整server配对结果。
- 已验证受限真实H100矩阵乘、独立UID、父进程环境不可读；完整server先后暴露固定工具/系统数据依赖。
  第9次已加载真实权重，因ldconfig执行受限失败，旧信号限制阻碍自身子进程清理；已定向清理该任务，未影响其他任务。
- 当前工作树中的ldconfig/numactl及自身子进程信号修复尚未复验；不能把早先15项测试或GPU探针算成这些最新修复已通过。
- 新主线提案应覆盖Master→至少两个独立direction→Integration组合→Kernel研究→原controller独立dev验收；先完成必要源码执行验收，不把该前置通路当最终架构。
  sealed/晋升/可信记忆/真实多轮RSI仍未完成，不自动创建；执行新版阶段前确认范围和资源，不结转旧余额。

### 本次源码通路的既有授权与准备（尚未达成科学目标）

- 用户已批准本阶段实现与执行，另行确认16 H100 GPU小时、12小时、最多并发2卡；沿用镜像digest/WeaverDev/qiji与只读模型挂载，不继承旧余额。
- 新计划与先行验收见`docs/experiments/source-autonomy-20261110.md`。入口`exp/source_autonomy.py`，唯一新预算状态`logs/source-autonomy-run-20261110-a01/resource-state.json`。
- 当前仅完成部分可信引擎边界预检，尚未启动Master/direction源码研究。已经确认实际GPU矩阵乘及独立UID/父进程环境保护，完整server/换卡预检仍待完成。
- 原始失败、各次冻结源码、提交/启动/终态和预算均独立保留；恢复前核对`preflight-plan.json`、提交UUID与资源状态，不重复create已有任务。
- 仅保护必要红线，不改controller/判据/sealed，不读作者final；允许SGLang必要子进程/JIT/网络IPC，不声称网络隔离或硬件逐臂隔离。设备授权限Pod已分配两卡，CUDA_VISIBLE_DEVICES逐臂选择；不同UID保护可信父进程和另一臂文件。
- 本会话不接管Ascend/DSH进程、计费或validation；后续科学决策仍由Master/direction自主完成，不由主助手代写优化。

## 已收口历史：真实stock参数探索

- 用户批准累计64 H100 GPU小时、最长24小时、最多并发8卡；失败和冷启动计入，上限非使用目标。
- 沿用已确认镜像digest、WeaverDev、qiji、toleration及只读模型挂载。范围/先行验收见
  `docs/experiments/engine-autonomy-20261109.md`，执行进度见PLANS。
- 已接通受限startup option真实server研究，12通过原controller dev联合验收：1.085260 [1.062888,1.109728]，
  输出与stock一致；noise=0.00289225。无sealed、晋升、源码/算法新发现或完整Phase1/RSI。
- 当前主循环`logs/engine-autonomy-run-20261109-d03/`已exit0，Master与direction均主动stop，不再恢复研究或提交GPU。
  16/10诊断后，Master请求10独立gate（job-1c73aef8db5d-20261110001129），1.063766 [1.046362,1.082538]，
  noise=0.0007445165，输出一致且联合验收通过；没有证明10优于12或任何配置最优。
  预算唯一状态仍在d01/resource-state.json，8任务均Completed/exit0，保守22730GPU秒，峰值2卡；6研究角色均exit0。
- d01曾因吞吐比/耗时比语义缺项暂停；direction自行纠正。d02末controller通过后，适配器tuple/list比较误报，
  仅JSON规范化重放修复，未改数字/判据，也未重交该GPU任务。全部旧回包/错误保留。
- 当前代码另有多次恢复计数修复与独立审计，旧运行中的主循环并未热加载它们；实际host入口源以各run首请求归档为准。
  最终独立审计区分旧producer的resume范围完成数与全谱系真实诊断数，不能把gate或重复请求当新样本。
- 两次全谱系独立审计一致，14原生回合/30工具动作/5CPU运行/6GPU诊断，另2独立gate；44usage事件非精确API/token计费。
  630计时pair只覆盖30个独立公开dev题，不能把重复运行算新题；5份CPU代码/输出与原生工具流绑定通过。
- 起点8bd6029；收尾机器状态见`logs/engine-autonomy-closeout-20261109-d01/stage-result.json`。
  321CPU测试、两次独立重放及6类篡改拒绝通过；新归档25836文件/523390549字节，SHA为
  9fd4dbc77a1a5e97fb831c25a7f852458171437ba0c498ebfe911363e84ee85f，两次全SHA通过。公开审查通过，最终同步身份以publication目录单列回执为准。
  当时的源码通路接续提案已在新阶段获批，见上方；不读sealed/作者final，不自动integration/kernel/DSH或结转旧GPU余额。
- 首条通路仅startup option，非任意源码优化；不读作者final/sealed，不改controller或判据。

## 已收口历史：第三阶段有效微实验

- 用户批准阶段目标及1H100 GPU小时/最多同时1卡/最多3次900秒任务，并明确沿用原镜像、WeaverDev、qiji和只读模型PVC。
- 25定向/303总CPU回归、旧314文件清单SHA及上一阶段来源审计通过，实际角色源已冻结。
- Master自主继续原方向并分24动作/4CPU/2GPU尝试；direction自行修复GQA筛选、写CPU fixture，18例通过并复现旧问题。
  独立重放CPU fixture两次字节一致；实验脚本、原容差/长度/测量判据未变，主助手未代写科学代码。
- 唯一任务job-4fdd307bbdb9-20261109202445，code200+UUID核对通过，Completed/exit0；保守43GPU秒/容器26秒。
  真实H100上实验内筛选、另一个独立进程研究筛选及8类边界拒绝均通过；产出3种KV长度、11轮算子微实验耗时。
  单GPU内交替query宽度的微实验，不是正式双卡配对/CI/模型加速、lossless或controller验收；无候选晋升。
- 实际4回合/8动作/1CPU/1GPU尝试/10usage事件，2原生角色关闭、输入/canary未变，唯一容器终止；Master自主stop，未用完预算也不追加。
  两次独立来源审计一致、原始11轮数据重算及6类工程篡改拒绝通过；异常轮次保留，范围不是CI。
  内部阶段上限64动作/8CPU/24回合/3GPU尝试；可request_budget由Master阶段内重分配，不增加用户总预算。
- 本次执行目录`logs/gpu-autonomy-run-20261109-c01/`，准备及可信入口`logs/gpu-autonomy-stage3-prep-20261109-c01/`。
  每个GPU请求须绑定当前实验/筛选SHA的CPU成功回执；主助手不修改科学脚本或放宽原判据。
- 机器状态`logs/gpu-autonomy-stage3-closeout-20261109-c01/stage-result.json`：stage_goal_met与scientific_microexperiment_completed为true，
  controller_accepted/candidate_promoted/full_phase1_completed/real_engine_rsi_completed均false；不能将本次记成新算法发现。
- 新归档`logs/gpu-autonomy-stage3-evidence-20261109-c01.sha256`共126文件/4835333字节，两次全SHA通过；
  SHA=e52b13d9550139145010e90dee311f4608a99c4bb8633c63bbf8307dcdd8f321。Git同步回执`logs/gpu-autonomy-stage3-git-sync-20261109-c01.json`单列，不覆盖旧归档。
- 目标/验收见`docs/experiments/gpu-autonomy-stage3-20261109.md`、PLANS；完整归档/公开内容审查通过，最终Git同步身份以单列回执为准，不再启动研究或GPU。
  下一阶段由Master评估如何映射到真实stock部署路径，再设计验证/option候选；先报方案获批，不强制VERIFY/作者final，不自动进integration/kernel/sealed。
  旧阶段已结束，不恢复其GPU上限或把复用算新发现。下节全部为历史。

## 已收口历史：由direction修复自身筛选

- 用户批准本阶段并确认1H100 GPU小时总预算，最多同时1卡；1次600秒依赖预检，最多2次1200秒研究。
  镜像digest、WeaverDev、qiji、原只读模型PVC已确认；不继承旧阶段余额。
- 最终38定向/299全量CPU回归通过；新阶段来源、资源契约、恢复计数和8类边界拒绝均验收。
- 预检code200、UUID=`job-2ea20f106d5c-20261109191521`，Completed/exit0；保守59GPU秒。
- Master自主接续，direction两次请求GPU：job-d8bd211a0273-20261109192612、job-258e42aa7878-20261109193328，
  均code200且独立确认UUID，最终Aborted/exit1；保守41秒、34秒。总134GPU秒/容器67秒，3容器均终止。
- 首次研究在FA3延迟加载触发FlashInfer的ptxas版本探测时被禁子进程边界拒绝。
  主助手仅修复固定依赖可信预加载，Master自行批准最后一次研究尝试；GPU证明已越过加载故障且8类探针仍全通过。
  随后direction自行诊断其GQA参考头维度错误，筛选未通过、未进入延迟测量，不是原假设被证伪。
- 科学脚本/筛选SHA保持上一阶段原样，主助手未代改研究。累计15回合/8动作/0研究CPU/2研究GPU尝试/19usage事件；
  8个新角色进程均关闭，输入/canary未变。两次研究尝试已用完，Master停止，不新增任务；不是GPU时间预算耗尽。
- b01旧失败上下文未附新预检、b02方向动作耗尽/扩额措辞歧义均保留；修复反馈分发及阶段内重分配说明后由Master重决策。
  实际执行前均冻结源tar；没有追溯改写旧阶段或假称研究成功。
- 两真实GPU回执独立审计、最终重复一致、5类协议篡改拒绝通过；工程验收不等于controller正确性/性能验收。
  机器状态`logs/gpu-autonomy-stage2-closeout-20261109-b01/stage-result.json`明确original_goal_met=false、
  scientific_experiment_completed=false、controller_accepted=false，可信预加载GPU复验则为true。
- 新阶段先提案获批：由direction自主修复筛选、先做CPU维度fixture，再由Master决定新GPU请求；不代写GQA修复。
  证据prep-b01至b04、run-b01至b04、preflight-b01及closeout-b01；新清单`logs/gpu-autonomy-stage2-evidence-20261109-b01.sha256`。
  新清单314文件/12185277字节，两次全SHA通过；SHA=1767ae60ca82564559175754911fa09a922354bbef573238b2666308bd2e7e82。
  Git同步回执`logs/gpu-autonomy-stage2-git-sync-20261109-b01.json`单列，旧363文件清单复核通过，不覆盖。
- 当前阶段记录`docs/experiments/gpu-autonomy-stage2-20261109.md`，进度见PLANS；下节为旧阶段，不恢复旧上限或旧待办。

## 已收口历史：CUDA运行库白名单修复待GPU复验

- 本阶段用户批准后，Master自主选方向/预算、direction自主写实验/筛选，真实GPU代码与原生回包绑定通过。
  仅有限GPU脚本执行/失败反馈闭环通过，**有效科学实验、真实27B生成、完整Phase 1/RSI均未完成**。
- 2次create均code200/dataNone，按精确任务名解析native name并经Kubernetes确认UUID：
  `job-097d59232135-20261109181434`、`job-71e60201ac44-20261109183113`，node233，均1H100/128Gi。
  两者Job Aborted/Pod Failed/容器exit1；每任务观察到1个Pod UID/restart0，不宣称服务端零重试。
- 首次GPU/8类权限探针通过后，实验在SGLang依赖导入时因.cache不可写失败；原错误交direction，Master自主授权纯缓存修复重试。
  实验/筛选脚本SHA完全未变。第二次同样探针通过，随后因/usr/local/cuda/.../libcudart.so.12只读权限缺项失败。
  两次stdout为空、screening未执行，无延迟/数值结果，假设未检验，不是证伪。
- 最终16研究回合/26动作/2CPU运行/2GPU尝试/36 usage-update事件。主助手自设24动作曾不必要地索要追加审批，
  已显式校准为28，未改用户GPU预算、16研究回合或controller判据；旧24动作记录/失败不覆盖。
  Master最后stop，十个原生角色进程关闭，输入/canary未变。按创建至结束保守77GPU秒（容器31秒），原2GPU小时内。
- 最新代码只补/usr/local/cuda标准运行库READ，不给整个/usr/local或用户目录权限；32定向/293总CPU回归通过，
  最后这项库白名单修复**未GPU复验**。不因代码已改就自动新增第3个GPU任务。
- 准备/旧失败：`logs/gpu-autonomy-prep-20261109-a01/`、run-a01/a02/a03；真实GPU及完整冻结源：run-a04/a05。
  审计/资源/最终发布：`logs/gpu-autonomy-publish-20261109-a01/`；唯一阶段记录`docs/experiments/gpu-autonomy-20261109.md`。
  两GPU源码tar均实际执行前冻结；早期CPU driver逐版本冻结缺项仍保留，不回写历史。
- 下一阶段先说明方案获批：GPU验证最小运行库依赖，再由同逻辑Master/direction自主继续原实验。
  不由主助手设计新研究、不改controller、不建sealed、不启动integration/kernel或DSH；无候选/晋升/论文新数字。
- 收尾复验32定向/293回归通过，两个GPU独立审计及a05重复一致，10角色关闭/保护路径零diff通过。
  机器状态`logs/gpu-autonomy-closeout-20261109-a01/stage-result.json`；新最终清单
  `logs/gpu-autonomy-final-evidence-20261109-a01.sha256`，不覆盖195文件旧checkpoint。
  新清单363文件/7949293字节、两次全SHA通过，SHA=eb02fade93db43364f45386f6721cfd67ac73c3368857a37d4e3fe249c888211。
  Git最终同步身份单列`logs/gpu-autonomy-git-sync-20261109-a01.json`，不混进证据清单造成自引用。

## 以下均为本阶段早期checkpoint与历史记录，不恢复旧阻塞或旧待办

## 历史checkpoint：GPU研究动作额度曾耗尽

- 用户批准必要权限后推进Master/direction真实GPU自治阶段，再次确认原镜像digest及WeaverDev项目。
  记录`docs/experiments/gpu-autonomy-20261109.md`；新实现为通用GPU脚本执行/反馈，不预设科学实验。
- GPU尚未提交、没有UUID；远程边界、真实GPU研究反馈均未验收，不能宣布本阶段或真实Phase 1完成。
- 本机30定向/291全量CPU回归通过；独立CPU协议审计通过，但gpu_autonomy_passed=false。全量最终回归见准备日志。
  role输入/canary未变，六原生进程均exit0关闭；controller/作者实现/eval/账本/记忆/stock无Git变更。
- a01触发旧权限探针12步上限；原结果的动作计数在异常中未刷新，实际13动作/1CPU运行已在后续恢复时补扣。
  a02由direction自行写实验/筛选/语法脚本，分配额度8用尽，GPU请求被拒。旧复核入口曾写死stop，已修复并保留失败。
  a03恢复逻辑角色（新原生thread，非同一thread/新发现）；Master自主将原阶段剩余3动作分给原方向。
  direction读回两个脚本并核对stock接口后再次耗尽，Master停止。没有主助手代写科学脚本或自行扩额。
- 累计10模型研究回合/24动作/2CPU运行/0GPU尝试；30个usage-update事件不是精确后台API次数或token账单。
  2GPU小时总上限不变。已询问是否追加最多4动作，未答复前不能重启研究或提交GPU。
- 证据`logs/gpu-autonomy-{prep,run}-20261109-a01/`、`logs/gpu-autonomy-run-20261109-a02/`、a03目录。
  CPU协议审计用`--allow-no-gpu`，严格模式必须拒绝。原始角色回包、代码、工具回执均留logs不入公开Git。
  checkpoint归档195文件/2985858字节全SHA通过，清单`logs/gpu-autonomy-evidence-20261109-a01.sha256`，
  SHA=`cdd83282ad0d847566ad6c5c036aa04458acac85df171286b18825d6766f3c81`。
  旧CPU driver逐版本源码冻结有缺项，已在阶段记录披露；当前源码包不能冒充旧执行版本。
- 新GPU执行器未在GPU上验证。若恢复，先查重/展示命令/核对code200+UUID，GPU内探针通过才执行原脚本。
  不因目前代码已写就恢复旧取消任务，不放宽controller、不预先建sealed或进入integration/kernel。

## 以下为此前已完成阶段与历史接续（不恢复旧待办）

## 已完成：权限收口与公开组织仓库同步

- **公开授权已明确：**用户说明是本人主动改为public，并批准审查本次待发布内容、更新授权记录及推送。
  旧“只可推私有仓库”的阻塞解除，不改回私有，不自动改变任何可见性。阶段记录`docs/experiments/public-sync-20261109.md`。
  审查覆盖远端main之后的待发布提交历史及暂存树，不发布凭据、sealed、受限数据或原始运行产物；不是全仓库历史安全审计。
  本地权限阶段提交`60a601b`；最终远端身份以`logs/public-sync-20261109-git-sync.json`为准。
  原先阻塞回执和588文件清单不改写，以新记录追加后续处理；公开授权不扩大GPU/实验权限。
- 用户确认已转入组织，当前origin为`https://github.com/china-qijizhifeng/SpecPilot-reproduction.git`。
  GitHub旧地址重定向及组织地址均对应repository ID `1449067162`，同步前main相同；未改仓库可见性。

- 用户已批准“权限验收收口、AGENTS/PLANS、主页/交接与下一阶段提案”；本阶段只CPU复验和文档收口，
  不新启模型研究轮/GPU，不恢复接受历史补采。唯一记录：`docs/experiments/codex-boundary-20261109.md`。
- 先读本节，再读 `PLANS.md`。长期规则见 `AGENTS.md`；Master自主定方向/预算，direction自主设计、
  编写、执行与迭代，主助手不代做研究，controller独立裁判。Codex当前主线，DSH迁移后置。
- 本次接续前已有未提交受限入口实现及真实探针，均保留并复验，未改已执行源码。
  独立app-server + Landlock/seccomp入口只开放授权工作区与必要运行库，broker保留stock阅读/scratch读写/隔离CPU。
  真实live-a02：8次动作/1次CPU运行，3个必要能力成功，5次拒绝（其中2次格式错误，3次红线动作）；
  原生apply_patch越界另被内核拒绝。非敏感canary/只读输入/配置未变，进程exit0。
- 17项定向/278项总CPU回归通过；真实探针两次独立审计均与原结果字节一致；冻结四份执行源及两个二进制SHA一致。
  既有失败native-a01–a05、live-a01和红测全部保留。实际进程入口仅经本次有限canary验收，
  不扩大为旧spawn接口安全、GPU工作进程隔离、完整网络隔离或论文复现完成。
- 真实探针：`logs/codex-boundary-live-20261109-a02/`；本次复验：`logs/codex-mainline-closeout-20261109-a01/`。
  精确证据清单、源码包和同步回执见阶段记录。原始产物不入Git，不读sealed/凭据，不改controller/eval/账本/记忆。
  本次归档588文件/8268976字节，两次全SHA验证通过；清单`logs/codex-mainline-evidence-20261109-a01.sha256`，
  SHA=`3e39974a215094800cece82e54c35f2a1b209636f60bd2c2b2b0858e2ac7711a`。
- 下一阶段提案：`docs/experiments/codex-gpu-autonomy-proposal-20261109.md`，**尚未授权执行**。
  需先接通受限角色任务/真实反馈与可信GPU入口，经CPU fixture验收后，再由Master选一个方向。
  提案总2GPU小时、最多同时2H100；新预算/具体镜像/项目等提交参数必须核对确认，不沿用旧补采授权。
  当前GPU离线预检仍恒blocked，权限探针不是GPU driver；没有新任务UUID、真实GPU自治或候选晋升。
- 公开同步收尾后再审核下一阶段；不擅自接入GPU、搜索、建sealed或实现指定优化。

## 以下均为历史记录（不恢复其中旧“当前/下一步”）

## 历史：先解决模型工具边界，不能把离线预检当GPU自治完成

- 用户批准完成GPU自治接入阶段；唯一记录`docs/experiments/autonomy-gpu-boundary-20261109.md`。
  先实测权限，不能证明时fail closed。不继承旧补采预算/镜像授权，不恢复已取消a02。
- 当前spawn_agent接口无工具白名单/独立沙箱参数。fresh权限探针Laplace
  `01a1beda-4937-7933-abe1-293eefde61f4`通过require_escalated直接shell读写了broker允许目录外的无敏感canary。
  父端验证SHA和实际marker，两次验证一致；探针已关闭。没有访问真实sealed/凭据/controller或作者final。
  这是应用层broker边界未强制实施，不说明绕过宿主审批，也不证明未提权时能读sealed。
- 新`harness/gpu_preflight.py`及`exp/gpu_preflight.py`仅离线检查direction请求的字段/路径/文件SHA/资源需求。
  无执行、无northjob create、无授权开关；始终submission_allowed=false/exit75。
  镜像proposal不等于确认，接口请求上限不等于预算，source_pin检查不是执行源冻结。
  没有接入实际GPU执行器或GPU反馈，不可声称真实GPU自治/优化发现/晋升完成。
- 12项定向/261项总CPU回归通过；两次CLI结果字节一致，SHA=
  2868d9d535b1cd3ca6c95725a0c9b99a0b2d8440dfabf86da71e8e57e9e9f3a6。
  旧CPU审计第二次用--out与原result逐字节一致，独立输入完整性检查亦通过。
  第一次stdout紧凑JSON与原缩进JSON的cmp失败保留，解析结果相同；另保留新增测试helper的None哨兵错误及修复。
- 准备/证据：`logs/autonomy-gpu-prep-20261109-a01/`。真实角色只有权限探针，不是新master/direction研究轮；
  研究方向/题目未由主助手安排。GPU提交0、进程未启动、GPU测试未运行、无UUID。
- 新38文件/3084148字节全SHA通过；清单`logs/autonomy-gpu-evidence-20261109-a01.sha256`，
  SHA=5eb42d48234a77d79e12c9176517de469f6669918d560cdb30967b7bebc0ec28；前阶段109项亦复验。
  source overlay tar SHA=c0bbc892c887424cadc8ea9859a21be9059c3c2a310a7fbc9be23d246a33875d，
  基准0cc44ac+新增三Python文件，不冒充GPU冻结。stage-result明确blocked/stage_completed=false。
- 必须先获得可强制工具白名单的运行入口或无直接工具的纯文本模型接口，完成真实拒绝探针，
  再按新预算/镜像授权接GPU执行及反馈。已向用户询问接口/配置位置，不索要明文密钥。
  若仍只提供同一spawn工具接口，不能以额外提示词或用户豁免冒充强制隔离。
  以下全部是历史，不恢复其中的旧下一步。

## 当前接续点：真实CPU实验自治首阶段通过，不接管科学实验

- 用户已批准“下一轮目标和流程”并说“开始”；只建设/验收CPU实验自治，不授权GPU、旧补采或完整RSI。
  唯一记录`docs/experiments/agent-autonomy-plan-20261109.md`。controller/ledger/memory/作者资源不变。
- 新通用write/read/list_stock/read_stock/run_python，Landlock+seccomp真实限制脚本：
  只读工作区/运行库，禁宿主越界读写/网络/子进程/设备，6s墙钟/3sCPU/768MiB/每流64KiB。
  脚本写入经broker，原样来自direction响应；不是主助手写科学实验。模型后端本身仅提示约束，不宣称物理隔离。
- 11原定向+3独立完整性/249总回归通过，执行pin=ff96c81535d035d06409b38e80fb099530e70a37，tar SHA=
  9f9e2d06426f6ca9fb21301b87718a3bd180e9636fab65dfed50ff7a540ae09b。
  `logs/autonomy-prep-20261109-a01/driver.js`为通用transport，运行cell1004已结束，不另开重复运行。
- fresh master已自主选boundary-accounting-invariants、prefix-distribution-ordering，各10actions/3runs，
  留4actions/2runs；direction自行编写并请求执行，主助手只做非重叠验收/归档工作。
  实际12模型回包、8计费actions/4 CPU runs（3成功、1失败），另2次finish不计研究动作。
  T004为direction本地模块导入失败，T005由它自行修复，T006成功，主助手未代改实验。
  状态/请求/回执/原代码/真实输出在`logs/autonomy-{prep,run,public}-20261109-a01/`。
- 原master R012根据反馈停止两方向、追加0预算。计数代数相容并非执行正确性，筛选后suite直方图统一排序被反例否定；
  都只限已有/合成CPU证据，不是优化发现/模型新测量。真实运行没有追加预算，追加能力只在fixture测试过。
- 两独立CLI审计与原结果字节一致，SHA=dcd8cf7cfdad9ca2e4d1c3d88ee68f57518aa527512a0c405aa0b2af2ef8a18f；
  5类篡改拒绝。后置独立只读integrity验证2工作区输入、3最终脚本、4内核bootstrap，另3测试通过，未修改已执行源码。
  三模型角色已关闭，无活动CPU会话/本阶段GPU任务；controller/作者资源/ledger/memory不变。
  新109文件/3200858字节全SHA通过，清单`logs/autonomy-evidence-20261109-a01.sha256`，
  SHA=53c82d863f8354945969d9fe42d5311963fb83b03bd36c89e981547f91f5ffa5；后置校验器代码SHA单列integrity-source.sha256。
- 后端仍为Codex工具，精确模型ID/token用量不可得，客户端回执非后端签名；模型后端工具仅提示约束，
  不宣称模型物理隔离。真正被Landlock/seccomp限制的是实验CPU子进程；没有独立LLM服务或GPU工具接通声明。
- 下一大步骤先报通用GPU执行/资源审批及候选到controller交接方案获批；不由主助手接管已停止的研究，
  不恢复四题GPU提交、不优化指定VERIFY、不自动进RSI/sealed。以下全部是历史。

## 当前唯一接续点：停止补采，先审核实验自治方案

- 用户明确：不要再由主助手推进接受历史预测支线，不提交已准备的GPU任务；保留代码和证据，
  不算自主探索完成，不是判定点子无效。下一主线是direction自主设计/执行/迭代，master真正统筹。
  方案`docs/experiments/agent-autonomy-plan-20261109.md`仅草案，尚无实施或新GPU授权。
- 补采历史`docs/experiments/history-collection-20261109.md`：a01已create一次，code200，UUID=
  job-a0d49c75347b-20261109123806，node233，Failed/exit1。server/1H100预检成功，1次短预热后，
  事件函数phase参数重名TypeError退出；无正式四题链。容器176秒；保守创建至结束199秒计预算。
- a01 pin6d0676b；修复a02 pin=e243e2fce3ebeb2b0c4bc83129cb4342784cf88f，235项CPU回归通过。
  真实两轮/18调用的外层CPU fixture先红后绿；只改日志字段及剩余预算/失败AbortJob策略，未改预测/观测/裁判。
  a02的tar/manifest/四题复核/命令均已准备，但用户停止时未create，没有UUID，不自动再提交。
  `logs/history-collection-prep-20261109-a02/CANCELLED.json`与submit.sh前置拒绝已验收（exit75）。
- 精确查名确认a01终态Failed、a02不存在，本次无活动任务；两个前台监控已结束。
  停止归档65文件/5194094字节全SHA通过，清单`logs/history-collection-stopped-20261109.sha256`，
  SHA=07035ac740420bad9dd217e08d2e8ccfcd9dc3c2e5f535170aed71f34e980c83。
  a01一个Pod UID/容器restart0，Job retryCount最终1，不宣称集群零重试；未观察第二Pod或容器启动。
- 现有真实direction只能选少数CPU算术工具，还不能自行写/执行实验；不得把主助手代采集叫实验自治。
  新方案需接通direction行动→真实执行→证据/退出码反馈→direction继续/停止，master分配预算和决策。
  先审核再改实现，controller只读/sealed不可访问/option默认stock/性能双卡配对等边界不变。
  下文均为历史，不恢复任何旧“下一步”；尤其不继续4题补采，也不强行优化VERIFY。

## 当前接续点：独立确认缺数据，先批准最小采集

- 用户批准本阶段核查已有独立计数并CPU确认；无合格记录时只报告采集方案，不提交GPU。
  唯一记录`docs/experiments/history-confirmation-20261109.md`，基准2ff1c49；本阶段运行源码未改。
- 受控程序只读22份归档SHA索引元数据及已有匿名计数，35030去重路径；3份计数副本SHA一致，
  仍是原3个诊断请求。两observer流是原活动两轮；可识别格式中没有新增候选流。
  首次RUN元数据误拒与普通权限漏读1索引均保留，修正范围/受控读索引后补齐，不读私有内容。
  只覆盖已归档索引及stock-step/count-order格式，不声称全盘绝无数据，也未复验35030个原始产物。
- 清点SHA=969ae8c079400274501da0c152e61f69f32f238fa72a7dec53cb84f59f231ef4，两独立CLI重放字节一致。
  复用原a02 master真实resume/send/completion/close；未换agent，原始输入/响应/回执在
  `logs/history-confirmation-20261109-a01/`，结论needs_independent_collection。
  independent_confirmation_run=false、confirmation_mae=null、end_to_end_gain=null、implementation_ready=false。
  缺数据不是规则证伪，不重算3旧题冒充独立确认；原角色已关闭，模型精确ID/用量仍不可得。
- 14定向/224总CPU回归、清点与响应审计重放及3类工程篡改拒绝通过；0GPU、无候选实现/晋升。
  新32文件/121237逻辑字节全SHA通过，清单`logs/history-confirmation-20261109-a01.sha256`，
  SHA=407ee5796497a3d3d66fb850ce31ee23d205def388467cb85eccfef9d9107443。
  观测time_ns只有发出时间，不能推算入队、可靠终止信息时刻或关键路径，不另开终止方向采集。
- 下一阶段待批准：GSM8K/HumanEval各2新dev，broker排除旧3题与重复/别名后固定哈希选择，
  stock/block8/greedy/2048cap/自然EOS，两次fresh采集/线性重放，只向模型导出匿名计数。
  agent建议一轮不符合现有history_screen两轮契约，broker已标出并建议保留两轮，不放宽验收。
  拟1H100/最多30GPU分钟仅计数诊断，不是单卡A/B，不报告性能；未来性能仍需双卡配对换卡。
  仅4新题固定T001留一/训练专属均值中位数/同suite基线，不混旧3题、不调参，最多初步筛选。
  当前采集入口固定旧3题，需下一阶段批准后做外围runner/导出适配与执行冻结，不改controller/eval。
  不自动提交NorthJob/实现优化/晋升/RSI/sealed；以下全部是历史，不再执行旧“下一步”。

## 最新接续点：真实agent探索已接通，尚无可实施候选

- 用户批准的本阶段已完成工程接入与首轮分析，唯一记录`docs/experiments/exploration-20261109.md`。
  不预设VERIFY，不提供作者final实现/机制列表/旧对话；不实现候选、不提交GPU、不改controller或晋升。
- 新`agents/exploration*.py`、`exp/exploration.py`管理中立证据、角色提示、实际回执与受控CPU实验。
  真实子agent均fresh context、继承默认模型，仅处理inline JSON；精确模型ID/用量不可得，保持null。
  记录的是可见调用，不是后端签名或文件系统物理隔离；旧mock/registry未冒充本轮真实推理。
- a01 pin8195964/tar df438f2b...：3角色/6响应、0实验，agent指出接口不足，原始回答保留。
  原独立重放03/04与冻结源码隔离重放05/06均通过；不能用变化后的源码绕过hash。
- 按agent需求受控补E005匿名接受数量/事件顺序，3独立诊断请求×2物理重复；无原题/输出/token ID。
  a02 pin=`b0b89d0b876e77ce26d5c75a61dbf2ef5e418201`，tar SHA=e031783e...；两次额外导出字节一致。
  fresh master自行选history-conditioned-draft-budget、terminal-overlap-critical-path，实际执行T001/T002。
- T001等请求MAE：历史1步2.211373、训练均值2.420281、训练中位数2.457883。
  只支持继续核验预测信号，不是预算收益/加速比/泛化证明；重复轮次不算独立请求。
  T002每份记录1个未提交worker输出早于finish，但缺入队时间/无扰动关键路径，不能推算延迟节省。
- 两direction均needs_measurement/proposal=null；master-final=needs_more_evidence。
  工程验收通过不代表候选发现成功、方向已淘汰或真实RSI完成；不为得出提案换agent/改规则。
  每题MAE均改善与3%目标是探索筛选设想，不是新论文硬门槛或controller判据。
- 14定向/224总CPU测试、a02两次独立重放与5类篡改拒绝通过；a02结果SHA=
  `75f79c7fd62cfcbfad827238d48df4847637cfe39f87e8a5e5daf1f2e3c57915`。
  新118文件/2438743逻辑字节全SHA通过，清单`logs/exploration-evidence-20261109-a01.sha256`，
  SHA=`887ccc599fa87433465e75c21326689befba40d141b5dcd03a269862f2d927e0`；前阶段5598项亦复验。
  两attempt共6个模型角色均关闭，本阶段0GPU任务；controller/原stock/ledger/memory等保护目录不变。
- 下一大步骤先报最小独立证据确认方案获批：优先核查已有授权的未参与诊断dev计数记录，
  冻结预测及训练专属基线；已有终止产物仅核因果时间关联。没有合格记录则等待或申请最小采集。
  不自动实现/采集GPU/晋升/RSI/sealed，不再由主助手指定VERIFY优化；下面均是历史记录，不是待执行动作。

## 最新接续点：真实逐步观测与线性重放完成，未进入优化

- 唯一记录`docs/experiments/step-replay-20261109.md`。用户本阶段明确批准独立stock诊断副本的必要源码阅读/
  默认关闭只读钩子；不扩展为final阅读、controller修改或自主优化授权。
- 执行pin=`e65925c337ab06b7327feab5d627576f418e9c8c`，source.tar SHA=01cf21f1...，
  observer tree=cb27466a...、runtime SHA=fc825e59...，原stock=e5472c4f...未变。
  源码只在副本的worker/scheduler加观测点及独立runtime，重复构建/逐文件差异检查通过。
- 唯一GPU UUID=`job-7021a7f03f72-20261109101400`，原镜像/WeaverDev/实际proj-31/node244。
  02:14:23–02:30:14 UTC（15分51秒），Completed/Pod Succeeded/容器与脚本exit0。
  33快照单Pod UID/restart0，Job retryCount未设置；总0.528333GPU小时，2预算内，未重复提交。
- 旧10题受控选3题（异常+同suite正常+首跨suite正常），2048cap/自然EOS。
  stock vs副本关闭/开启各两轮fresh物理换卡，12pair/24臂行输出全相同，也全部匹配旧stock输出hash。
  仅开启模式6份真实链重放；24个accepted/bonus/缺步/错输出故障副本全拒，不是论文event-rule实验。
- 差1已真实解释：输出=首token1+正确草稿+提交验证步−EOS尾裁切。
  异常1+1312+413−0=1726；正常1+344+81−1=425、1+604+155−1=759，两轮一致。
  原36/40及costmodel旧条件判据不改，不追写旧证据，不把差1当尚未解释的生成错误。
- worker82/414/156步，提交81/413/155，每份有1个未提交overlap尾步；实际接受量不含尾步。
  支持旧标签偏移解释，但本次未开profiler，不冒充同次旧trace逐条对齐；相应flag仍false。
- 210CPU回归、两次独立CPU重放与远程result字节一致，SHA=
  `6446c21f635ece6c45685e819202b22d04c95fcbe66805f1452e5ee87b4dc406`。
  新5598项/92137799逻辑字节全SHA通过，清单`logs/step-replay-evidence-20261109-a01.sha256`，
  SHA=`d501afd8a1d0418ac81b0db36e6e57133c8d004f24dad2ef8e7f690a42fc2e3a`；前阶段393项亦全过。
- 私有run/bundle/重复构建不手工读题或输出；只看对应public聚合。两卡0MiB/0%，端口释放，全部会话结束。
  没有controller/原stock/旧成本模型/ledger/memory改动，无sealed或RSI、性能/lossless/晋升声明。
- 线性stock链已可重放，但最佳树tau_best、全部kernel-class floor及无干扰步计时仍缺。
  下一大步骤先报VERIFY实际工作量/byte与匹配步计时方案获批；不扩大题集或自动搜索。

## 本阶段准备与运行历史（已完成，不再作为下一步）

- 用户已批准阶段内自主执行，并明确允许独立stock诊断副本的必要源码阅读及默认关闭只读钩子。
  唯一记录`docs/experiments/step-replay-20261109.md`；仍不读取final实现，不改controller或sealed。
- 已先红后绿新增runtime/线性重放/副本构建器及exp入口；8定向/210总CPU回归通过。
  stock canonical=e5472c4f...未变；重复构建observer canonical=cb27466a...一致，
  只改worker与scheduler两文件的观测插入，另加独立runtime文件。开关默认不存在，不触碰tensor/日志。
- 冻结协议：沿用旧10题，受控选唯一重复异常+同suite正常+首跨suite正常共3题。
  stock vs observer关闭/开启各两轮fresh物理换卡，2048cap/自然EOS，12pair/24臂行；
  只验输出/真实逐步链重放，不报性能收益。prefill首token假设待真实数据确认，不翻绿旧计数。
- 下一内部动作冻结源码tar→当前CLI查重/完整命令2GPU展示→create一次、核对code200+UUID。
  沿用确认镜像digest/WeaverDev/qiji/原toleration，2H100/256Gi、最长1小时/2GPU小时。
  结束后两次CPU重放、真实故障注入、SHA/清理、主页交接阶段提交推送；不自动进入优化/RSI。
- 已create一次code200/dataNone，精确UUID=`job-7021a7f03f72-20261109101400`，执行pin=e65925c，
  source.tar SHA=01cf21f1...，WeaverDev/实际proj-31；前台监控prep/lifecycle.*。
  不再create、不改执行源码或commit；只看公开聚合，不手工读逐题输出。

## 最新接续点：stock瓶颈诊断完成，完整成本模型未完成

- 唯一记录`docs/experiments/bottleneck-20261109.md`。原5suite各2题共10独立公开dev/2048cap/自然EOS；
  原20pair/40臂行fresh换卡计时保留，独立profile补采20/20窗口，202项CPU回归及两次重放通过。
- 计时pin=a102b64c0173aa9b72e126778005a137bad174fc，tar SHA=6c6d11a5...；
  profile-only pin=5ed0302e123ae51af3c669ffc6bf1350a64672e4，tar SHA=17afdc16...。
  两者完整SHA与命令、模型config/stock canonical hash和任务身份见阶段文档及prep。
- 原a01 UUID=`job-fa7aeb0532ed-20261109083627`，18分18秒，计时通过/profile仅4/20；
  a02 UUID=`job-46790c2ece9b-20261109090434`，14分3秒，仅补profile，不重跑计时。
  stop在自动结束后返回500；以该次新原生日志切片偏移/长度/SHA证明“未在采集”，不翻绿HTTP。
  原失败/16条隔离保留；补采12次500仍计为错误，全部有原生状态证明。
- 20窗口按请求等权累计kernel工作：VERIFY89.5782%、DRAFT8.2852%、EXTEND0.9770%、未知1.1596%。
  这不是整请求墙钟占比。12窗口只含127个VERIFY标签；另8窗口标签数比原生verify_ct多1，不能混称步数。
- 接受计数36/40行满足全部约束；另外4行是同一HumanEval题两卡两轮，实际1726比1312+413多1。
  原生直方图/别名可对齐，bonus/末尾裁切条件未解释，不改判据或宣称引擎错误。
- BF16 mm形状可识别4216项，但仅覆盖累计kernel工作0.5111%；名义冷I/O情景不是实测DRAM。
  真实lattice/replay API、全kernel-class工作量及匹配无干扰step时间未提供；三因子/ceiling均null。
- 私有`logs/bottleneck-run-20261109-a01/`与a02不手工读题/答案；只看对应public聚合。
  a01两CPU重放SHA=81b347f7...，a02两重放SHA=0300ac0b...，均与各自远程result逐字节一致。
  新393文件/181717264逻辑字节SHA全过，清单`logs/bottleneck-evidence-20261109-a01.sha256`，
  SHA=`05cafb7ebff1a06eb44664321a282cb59a43f0dfc9046c2da0b1d4eb98b719c3`；前阶段2970项亦复验通过。
- 两任务均node244/Completed/Pod Succeeded/容器与脚本exit0；38/29监控快照各单Pod/restart0，
  Job retryCount未设置。总1.078333GPU小时/2预算，两卡0MiB/利用率0–1%，端口释放，全部会话结束。
- 不改controller/作者实现/旧floors，不碰sealed/ledger/memory，不实施优化或真实RSI。
  下一大步骤先报最小逐步计数/lattice及无profiler步计时接口方案，获用户/维护者授权后再做。
  不自动扩大样本、重跑final、填三因子或开始搜索；这是诊断能力完成，不是完整论文成本模型完成。

## 本阶段准备与补采历史（已完成，不再作为下一步）

- 用户已批准本阶段内自主执行，唯一记录`docs/experiments/bottleneck-20261109.md`。
  原5suite前2题共10公开dev/2048cap/自然EOS；先stock/stock两轮fresh换卡，20pair/40臂行，
  再两卡各fresh stock采10题，共20探针。每server有短预热与完整10题同尺度预热。
- 新观察层只做计数代数一致性、明确标签/correlation阶段归因与可识别BF16 mm子集名义情景，
  不拿直方图冒充lattice replay，不将128个公开profiling步预称128次VERIFY。
  完整三因子/ceiling缺证据均为null；不改旧floor或controller，不读sealed/作者实现/私有逐题输出。
- 新16项/全200项CPU回归通过，准备日志`logs/bottleneck-prep-20261109-a01/`。
  下一内部动作冻结源码tar→当前CLI查重/展示完整2GPU命令→create一次核对code200及精确UUID。
  沿用原确认digest、WeaverDev/qiji/toleration，1节点×2H100/256Gi，最长1小时/2GPU小时。
- 远程结束后两次CPU受控重放、SHA归档、资源清理、README/交接/阶段提交推送后停止。
  真实candidate前阶段已完成，不重跑；不自动优化、晋升、RSI或sealed。
- 已提交一次：pin=a102b64，source.tar SHA=6c6d11a5...，code200/dataNone后精确查名UUID=
  `job-fa7aeb0532ed-20261109083627`，node244/实际proj-31，已见双H100版本预检通过。
  a01已Completed/exit0（00:36:55–00:55:13 UTC），原计时20pair及两CPU重放通过，profile仅4/20。
  两次stop返回500，原生server报告“Profiling is not in progress”；其余16探针被安全隔离。
- 已先红后绿修复该次新日志切片绑定，只以精确原生异常证明未在采集，不把500改200。
  准备a02 profile-only补采同20探针，不重跑/覆盖计时，35分钟加a01仍在总2GPU小时预算。
  a02独立pin/tar/UUID/日志待登记；只看公开聚合，不读私有逐题输出，结束重放归档后停止。
- a02已提交一次code200/精确UUID=`job-46790c2ece9b-20261109090434`，pin5ed0302，
  source.tar SHA=17afdc16...，202回归通过，前台监控`logs/bottleneck-prep-20261109-a02/lifecycle.*`。
  不再create、不改执行源码或commit，结束后受控重放两次/归档/收尾；计时仍归a01源码。

## 最新接续点：真实candidate启动option接入完成，不自动开始自主搜索

- 唯一记录`docs/experiments/candidate-20261109.md`。184项CPU回归通过，controller及作者资源未改。
  首版只支持`draft_tokens`启动option；默认8、本次开启值也8，no-op，不支持任意源码patch，不算新发现。
- 执行pin=`d526f763b3c003f84e8a0e91a8adf5a5db8e87ba`；源码tar SHA=
  `94e1a6cc8d5ea734ab57021c0d09d00752e57a88670689427c022fe6362c9915`，准备目录
  `logs/candidate-prep-20261109-a01/`；bundle=`logs/candidate-bundle-20261109-a01/`，spec SHA=
  `4b55bd2d3d232d25ee7107f74e902bc7c9ab0359a1eec044b1586a50925f8037`。
- 唯一GPU任务UUID=`job-4fcf9416b13f-20261109072806`，create code200/dataNone后精确查名解析，未重复提交。
  node233，2026-11-08 23:28:33–23:40:24 UTC（本地11-09 07:28:33–07:40:24），11分51秒。
  Job Completed/Pod Succeeded/容器和脚本exit0；2H100/256Gi/原digest/WeaverDev/实际proj-31核对通过。
  23监控快照单Pod UID/容器restart0；Job retryCount未设置，不扩称全任务无重试。
- 关闭/开启各两轮fresh/物理换卡，5独立公开dev请求/64cap，20pair/40臂行全部输出相同；
  8测量server另起1 stock FP32 scorer，40条实际输出/2560token及head preflight/证据绑定全过。
  四个candidate runtime均实际解析到bundle内sglang，不只是改标签；stock-copy canonical hash=e5472c4f...。
  全40臂行length触顶，不是完整任务质量验证，也不是一般候选的rate/event门禁。
- 私有原始运行`logs/candidate-run-20261109-a01/`及`.log/.exit-status`，只看受控聚合，不手工看逐题输出。
  首次CPU重放01仅因sudo PATH无git失败保留；02/03显式传原PATH及进程safe.directory成功，
  与远程result逐字节一致，SHA=`eccc657de223a957ee59a7847705844008df077b8fd7fdcdd14d29f1fe619ebf`。
- 新2970项/38058598逻辑字节全SHA通过，清单`logs/candidate-evidence-20261109-a01.sha256`，
  SHA=`9249c02f1a26a4856d01d412a3c7b635a28bf29b32684856873679613126ed4e`；前阶段37项亦复验通过。
  两卡0MiB/利用率0–1%，端口释放，全部监控/CPU会话结束；折算0.395GPU小时，2预算内。
- `correctness_passed=null/performance_passed=null/promoted=false/ledger_eligible=false`，仅接口smoke。
  未sealed/真实RSI/写ledger或memory；不能把184测试/同token/评分通过说成lossless或性能晋升。
- 下一大步骤先报代表性stock profiling/replay和实测成本模型方案获批；不再重跑本smoke。
  真实proposer/正式晋升状态机仍缺，controller/eval变更需维护者明确授权，不自动执行下一阶段。

## 本阶段准备/运行历史（已完成，不再执行）

- 唯一记录`docs/experiments/candidate-20261109.md`，准备目录`logs/candidate-prep-20261109-a01/`。
  本阶段用户已批准阶段内自主，包括短双卡烟测；不改controller/eval/ledger/memory，不自主搜索。
- 新`harness/candidate.py`只支持启动参数`draft_tokens`，默认8；本次开启值也8，刻意no-op。
  构建为stock同源复制，canonical SHA固定e5472c4f...；候选runtime receipt核验实际sglang解析到快照内。
  第一版不支持任意作者覆盖层或源码patch，不把接线当发现。
- 新`exp/candidate_smoke.py`/`candidate_serve.sh`/`candidate_remote.sh`，既有三臂入口不变。
  17项新CPU/真实HTTP测试及167项旧回归通过；红测试/首次实际stock链接拒绝保留。
  stock有1个合法内部相对`.clang-format`文件链接，复制保留并计入hash，外链/断链/目录链仍拒绝。
- 下一内部动作：冻结源码提交与tar、prepare新的candidate bundle、核对当前help/任务名查重，
  展示完整命令/2GPU，create一次且核对code200+精确UUID。仍使用已确认镜像digest、WeaverDev/qiji/原toleration。
  1节点×2H100/256Gi，bash/nproc1，禁RDMA/hostNetwork；最长1小时，即2GPU小时，不追性能数字。
- 关闭/开启各2轮fresh并物理换卡，每suite1条共5公开dev/64cap自然EOS，20pair/40臂行；
  之后单独stock FP32 scorer评分40条实际输出并用controller检查原始生成绑定。
  无当前noise/δ晋升结论，无lossless声明。结束后两次CPU重放、SHA/清理/首页与交接提交推送。
- 已冻结并提交：pin=`d526f763b3c003f84e8a0e91a8adf5a5db8e87ba`，source.tar SHA=
  `94e1a6cc8d5ea734ab57021c0d09d00752e57a88670689427c022fe6362c9915`；
  bundle `logs/candidate-bundle-20261109-a01/`，spec SHA=4b55bd2d3d232d25ee7107f74e902bc7c9ab0359a1eec044b1586a50925f8037。
- create一次code200/dataNone，精确查名取得UUID=`job-4fcf9416b13f-20261109072806`，
  23:28:33 UTC容器在node233启动；2H100/原digest/256Gi/实际proj-31与GPU版本预检通过。
  运行`logs/candidate-run-20261109-a01/`，生命周期在准备目录；正在前台监控，不改源码/commit或再create。

## 上一阶段：真实RSI准入核对完成，不自动运行搜索

- 用户批准结束final泛化/接受长度追因，复用已有验收，只补准备缺项；本阶段唯一记录
  `docs/experiments/rsi-readiness-20261109.md`，基准pin=`c05d17d46446c31f3044943a7423c444583207a6`。
- 独立目录`logs/rsi-readiness-20261109-a01/`，先写`acceptance.sh`后CPU验收；
  不提交GPU，不调用`exp/run_e2e.sh`/mock loop，不修改controller/引擎/patches/eval，不碰sealed/ledger/memory。
- 已核对：真实正确性裁判和30题dev联动不是缺项，不重复作者基线；搜索从stock/block8起步，
  final仅作作者参考。既有noise和δ只属于原活动，新候选必须同活动重标定并验实际测速输出。
- 真正缺口：CLI和dev活动固定ar/stock/final；没有通用真实candidate构建/option/T0适配；
  costmodel仍kernel=1，代表性stock lattice/replay未接；proposer仍固定registry；
  paper_policy明确只读pre-promotion verdict，正式真实候选状态机/账本集成需维护者交付。
- 中文60题反例保留，作为后续开发/回归范围的依据；不手工读/搬私有题，不把见过结果的集再叫独立确认，
  不擅加“所有领域必须都提速”论文门槛。作者产物验证、数字复现和真实自主发现仍分开。
- 验收完成：11定向/167总回归、五阶段25319清单项SHA通过；裁判/dev各四独立进程重放一致。
  初次`acceptance.sh`在dev原汇总字节比较处exit1保留，原文件仅比CLI多一个末尾换行；
  新`acceptance-final.sh`验证dev与历史两CLI字节一致、原汇总严格仅多单个换行/JSON对象相同，exit0。
- 活动22:52:53–22:56:43 UTC（本地2026-11-09 06:52:53–06:56:43）；
  dev重放SHA=`840502614d4bbd84c743ea377838e22e457a64cbaa6e283e2e53bc728fed172f`，
  裁判重放SHA=`ad1238a1fbc7ccf67ea7b176ed8a3f2fffe1079535e0c5f9a76b4f03e41d9d3c`。
- 新37文件/2380283字节全SHA通过，清单`logs/rsi-readiness-evidence-20261109-a01.sha256`，
  SHA=`f3d90b8237a340274b77c889ef1a3e7e84de6c1427f569a20c5f66178ecea23f`。
  无GPU/晋升/真实RSI，无运行会话。下一大步骤先报candidate接入/T0方案获批，不自动改controller或开新GPU。

## 上一阶段：匹配因素诊断全部完成，不自动新阶段

- 唯一记录`docs/experiments/diagnosis-20261108.md`，已全部执行/重放/归档。不要重复提交、重抽样或改final追绿。
- 固定stock/final/controller，12合成事实卡，中英文×512/1536精确输入×短/长指令96自然请求；
  短指令48变体分别实际固定64/256/1024。每条件前null→candidate→后null，各两轮fresh/物理换卡。
  语言/长度/物理轮次在事实卡内聚合，独立单位是12，不是96/240。
- 三主要对比Bonferroni区间：固定64下S中文/S英文=0.408755[0.394764,0.424361]；
  S1024/S64=1.794214[1.650111,1.961477]；S输入1536/S512=1.024434[0.942193,1.105345]。
  S=stock请求耗时/final请求耗时，别把收益系数之比误读为两语言原始速度比。
- **不能只用短输出解释减速。** 固定512输入/实际64输出，中文S0.619186、英文1.490048；
  1536输入0.566826/1.409761。长答自然EOS允许但两臂实际均2048触顶，中文0.665814/0.656750，
  英文2.185057/2.318001。触顶不是完成任务的实用收益，无新语义非劣/lossless结论。
- 强制1024有大量EOS后延续：stock71.5820%/final75.0122%token，不能把收益提高只归于固定开销。
  64组无EOS，跨预算各臂前64token96/96相同，但不是stock/final互相lossless证明。
- 阶段probe只取预先固定1张合成卡/512输入/两物理轮。64token时final中文/英文
  VERIFY标签38/10，累计VERIFY kernel均值774.647/204.341ms，EXTEND71.698/71.849ms；
  差异主要落在验证循环而不是本probe输入扩展。未核验接受率/树/TLV因果，不判某开关坏了。
  12数值变体/1模板不能推广到所有中文；profile累计kernel时间不是端到端墙钟占比。
- 原保守scope白名单未识别动态`step[DRAFT/VERIFY/EXTEND ...]`，未归因100%的报告保留；
  新CPU `diagnosis_trace.py`按明确标签、同线程launch及correlation归因，未知/歧义保留，
  16trace未归因仅1.083–1.201%。没有从kernel名字猜阶段，没有读作者实现。
- 原正式GPU UUID=`job-89c6c8cd6c11-20261108200750`，node244，12:08:18–17:34:34 UTC，exit0；
  初次profile16个JSONDecodeError保留，原HTTP字节未保存的局限如实记录，不翻绿。
- profile-only补采UUID=`job-72e589efab39-20261109014404`，node244，17:44:24–17:56:10 UTC，exit0；
  32次HTTP200确认为无Content-Type纯文本响应；独立ProfileClient修复，16/16 trace成功。
  两任务均Completed/Pod Succeeded，监控648/18快照各单Pod/restart0，Job retryCount均未设置。
  不重叠/最多同时2GPU，按容器时长11.267778GPU小时，原16预算内；两卡0MiB/0–1%，端口释放。
- 正式pin629eb4268dcf49bed41e1266f0f159426dc7444a，source.tar SHA=
  `2411dcc0208573d3ab8af7203948374ebc5816884093bb580cafa9f199401a67`；
  补采pin74afcee9077baa7da7c60113673e8b7d34fa1e83，profile-source.tar SHA=
  `095da269bae0ba8d647ed6c2d21d01914e43118e305f20ae0325482cd53955bf`；
  CPUmapper pin d7a5fd2c0558c2d939546807d7451575bae12ff4，trace-source.tar SHA=
  `b3b19e600797960b2fe79b916aba088438749c0d0a4eb6bb78b664bd6c85bacb`。
- dataset SHA=`0d92ecbdd62cc57473fd97f692183013314f4d271ead9fa30e739fea8eab4b30`，私有data/run/profile-run在
  `logs/diagnosis-data-20261108-a01/`、`logs/diagnosis-run-20261108-a01/`、`logs/diagnosis-profile-run-20261108-a01/`。
  **agent只看公开`logs/diagnosis-public-20261108-a01/`和`logs/diagnosis-profile-public-20261108-a01/`**。
- 正式result/replay01/02字节一致SHA=f998dcadd38d07647256898d6719184f21d351bd3957847e48dd63de8183af4b；
  补采result/replay01/02一致SHA=0a11c217cfe8736d41aa1c22a54d8c8996481bd896b68cd97f0f39e5536eb87a；
  EOS审计重放一致SHA=1cd84c1d187f89d87fc765001054b0560aa7beddf81f33b6d02680630edbc66c；
  CPU阶段归因重放一致SHA=e6e6a99ee81f18aee0644259b6d12bc4c241fdab07397f5803e97c57b5066e64。
- 167项最终回归/shell/diff通过；1440正式pair/2880臂行，1440全尺度预热/48短预热pair；
  6509文件/507041718字节全SHA通过，清单`logs/diagnosis-evidence-20261108-a01.sha256`，SHA=
  `3e970173a509dfe501f70db89f8ea4b77265da52cd24b9b18ae7444624812aee`。
  前一阶段5928文件也复验全过。controller/patches/作者config/dev未改；无sealed/RSI/ledger/memory/晋升。
- 所有监控/CPU进程结束。下一大步骤先报方案获用户允许；可继续查验证循环，也可回论文工作负载主线。
  不以这次诊断额外设论文硬门槛，不自动重复GPU，不读取私有逐题输出/已有sealed/作者实现。

## 本阶段准备与补采历史（已完成，不再作为下一步）

- 唯一记录`docs/experiments/diagnosis-20261108.md`；新增`exp/diagnosis.py`/`exp/diagnosis_remote.sh`。
  不改final/stock/46开关/controller，不碰sealed/RSI/ledger。不是新的质量或lossless验收阶段。
- 12合成事实卡×中英文×精确512/1536输入×短/长指令=96自然请求（2048cap）；
  短指令48条分别ignore_eos固定64/256/1024实际token。干预组不冒充自然任务收益。
  每条件前null→candidate→后null各两轮fresh/物理换卡；全部以事实卡聚类，不把因素重复当新样本。
- 主要对比语言/输出长度/输入长度三项，提前冻结Bonferroni区间；计时后单独profile/1token代理，
  1token含初次解码及HTTP，不叫纯prefill；不明scope/不等价TLV计数不推断接受率或阶段占比。
- 数据私有`logs/diagnosis-data-20261108-a01/`，仅看公开`logs/diagnosis-public-20261108-a01/`；
  SHA=`0d92ecbdd62cc57473fd97f692183013314f4d271ead9fa30e739fea8eab4b30`。
  精确token与独立进程分词通过，160项CPU回归通过；准备日志`logs/diagnosis-prep-20261108-a01/`。
- 接下来冻结源码/tar、当前help查重、展示完整2GPU命令、create一次并核对code200+UUID。
  沿用已确认digest/WeaverDev/qiji/原toleration，1节点×2H100/256Gi，最多8小时；不因结果重抽样。
  profile公开API不可用或scope不全则明确局限，不改引擎“补证”。两次重放/SHA/README/阶段推送后停止。
- 上述提交已完成：code200且精确UUID=`job-89c6c8cd6c11-20261108200750`，node244，
  12:08:18 UTC启动，2H100/256Gi/原digest与挂载已核对；实际queue=proj-31。
  pin=`629eb4268dcf49bed41e1266f0f159426dc7444a`，源tar SHA=
  `2411dcc0208573d3ab8af7203948374ebc5816884093bb580cafa9f199401a67`。
  私有运行`logs/diagnosis-run-20261108-a01/`，仅监控公开a01与准备目录lifecycle；
  不再次create、不改代码，运行中仅文档更新。结束后CUDA不可见执行`diagnosis.py audit --out <新路径>`两次核验。
- 原GPU任务已Completed/Pod Succeeded/exit0，12:08:18–17:34:34 UTC；正式四条件全验收。
  profile16探针均JSONDecodeError（JSON-only客户端不能处理响应），初次trace不能宣称已采到。
  初次CPU `diagnosis.py audit`已成功，公开a01/result.json；尚未完成阶段，不重跑任何正式测量。
- 独立新增`diagnosis_profile.py`/`diagnosis_profile_remote.sh`修复纯文本响应捕获，163回归通过；
  原main诊断/计时源码及controller保持不变，新任务仅两轮fresh/换卡补采profile，最长1小时，
  加原5h26m16s仍在原8小时/16GPU小时内；同一时刻最多2GPU，正式数据始终绑定629eb42。
  新公开`logs/diagnosis-profile-public-20261108-a01/`；新私有运行拟`logs/diagnosis-profile-run-20261108-a01/`。
  新任务单独source pin/命令/UUID待登记，查重→展示→create一次，不复用旧任务名。
- 补采已提交且开始成功trace：code200，UUID=`job-72e589efab39-20261109014404`，node244，
  17:44:24 UTC启动；2H100/原镜像/WeaverDev/proj-31核对通过。
  source pin=`74afcee9077baa7da7c60113673e8b7d34fa1e83`，profile-source.tar SHA=
  `095da269bae0ba8d647ed6c2d21d01914e43118e305f20ae0325482cd53955bf`。
  只监控新公开`logs/diagnosis-profile-public-20261108-a01/`，私有profile-run-a01不手工看逐题结果。
  原正式result/replay01/replay02字节一致，SHA=f998dcadd38d07647256898d6719184f21d351bd3957847e48dd63de8183af4b。
  新补采结束后`diagnosis_profile.py audit --private <profile-run> --out <新公开JSON>`，显式CUDA不可见，
  两次重放/原始字节与traceSHA/总证据校验后再收尾。不重复create，不动运行代码，只能更新文档。

## 最新接续点：反例独立确认已完成，不自动进入下一阶段

- 唯一记录`docs/experiments/confirmation-20261108.md`。用户批准的阶段已全部完成，不再提交GPU/重抽题/改final。
- 160新题排除作者全部100dev与上轮200题：中文60、人工参考摘要60（2048cap）、代码40（4096cap）；
  两条件各前null→candidate→后null、各两轮fresh/物理换卡。独立题cluster，不把两卡当新样本。
- 三主要端点Bonferroni同时区间（每项98.333333%）：中文请求stock/final延迟比0.539657
  [0.504294,0.577406]，**final约需1.853倍时间，性能反例确认**。
  摘要ROUGE-L差-0.002707[-0.010846,0.004635]、代码通过率差+0.05[-0.05,0.175]均证据不足。
  不能以未显著证明质量非劣，也不能用新DialogSum结果推翻旧Alpaca告警。不是故意reward hack的证据。
- 中文每臂120轮次全自然EOS，实际平均输出76.267/77.533token。未因果隔离语言/短答/prefill/接受率，
  不说“中文本身造成”。摘要ROUGE-L均值0.259538/0.256830（非准确率）；代码平均通过率82.5%/87.5%。
- 两cap新noise0.6597425%/0.4177801%；全局/局部新δ0.25、rate/event均过，零大margin事件。
  800条完整FP32评分（640测速输出+160新AR），960正式pair/1920臂行。forcing不是数学lossless。
- GPU唯一UUID=`job-a99898c2f332-20261108164059`，node208，08:41:27–10:49:13 UTC（2h7m46s），
  Job Completed/Pod Succeeded/容器与脚本exit0，255快照单Pod UID/restart0，Job retryCount未设置。
  两H100均0MiB/利用率0–1%，端口释放；所有监控/CPU会话已结束。
- GPU源pin=`65364f55ae0d367438f11efaa1c06332c2ebc717`，source.tar SHA=
  `ac85e3ca050e50a614ceb4f840e7023dcebb1d7a0932bf1bec67d84de371328b`；
  CPU评测源pin=`bb5b8fbcdf1bc1da32ddb474b12af9d8c57702ff`，evaluator.tar SHA=
  `631d8a4c222c6e9bd20937e14819fdbd77c28956d7d4a29a61ac9e0f30ad9678`。
- 原CPU评分失败因中文180参考中1个有限float；原partial文件不覆盖。新CPU评测只标该题辅助质量缺测，
  60题速度/160题forcing全保留，主要摘要/代码不缺测。修复PATH仅进程有效，未改controller或阈值。
- 私有数据`logs/confirmation-data-20261108-a02/`，私有运行`logs/confirmation-run-20261108-a01/`，
  私有质量`logs/confirmation-evaluation-20261108-a01/`；**agent只看公开`logs/confirmation-public-20261108-a02/`**。
  dataset SHA=`03f72f87aa3422197de540838fc9a7ae2f1494415e97e9a4ed5e13ce4f786e2e`。
- 11:10:49 UTC统一验收完成；result/replay-01/replay-02字节一致，SHA=
  `b07cf371ca03c20bc66b844fe7048e9f12a9e28a045af46b6d2f772bc6657c77`。
  148回归/shell/diff通过，旧泛化10312文件SHA复验全过；本阶段5928文件/272733966字节校验全过。
  清单`logs/confirmation-evidence-20261108-a01.sha256`，SHA=
  `29bfb790646ab81cfcab9035071d904a96cfa82fb66ada6be9238f4923bfebbf`。
- controller/patches/作者config/dev相对36166c7无变化；没有sealed/RSI/ledger/memory写入或晋升。
  不再次运行finalize；复核仅冻结CPU源`confirmation.py audit --quality-root <上述私有质量目录> --out <新路径>`，
  显式CUDA不可见，只看聚合，不手工读私有样本。完整命令见唯一记录。
- 下一步建议：先给用户中文短答减速的因果诊断方案，再获准执行；也可由用户选择正式sealed顺序。
  质量告警仍需可靠语义复核，不擅加论文硬门槛、不自动新阶段，不用本确认集改final再自验。

## 本阶段准备与运行历史（已完成，不再作为下一步）

- 唯一记录`docs/experiments/confirmation-20261108.md`。固定final/stock/controller，不碰sealed/RSI/ledger。
- 中文60＋DialogSum人工参考摘要60（2048cap），HumanEval40（4096cap）；排除作者100dev与上轮200题。
  摘要不同来源，不以新源无下降推翻旧Alpaca告警。三主要端点、Bonferroni同时区间提前声明。
- 新入口`exp/confirmation.py`和`exp/confirmation_remote.sh`；复用既有controller，不改裁判。
  `generalization_audit`只新增可选domains/caps，原默认不变；146回归通过。
- 私有数据`logs/confirmation-data-20261108-a02/`，公开状态`logs/confirmation-public-20261108-a02/`；
  agent不要看题目/答案/逐题输出。SHA=`03f72f87aa3422197de540838fc9a7ae2f1494415e97e9a4ed5e13ce4f786e2e`。
  准备/失败日志`logs/confirmation-prep-20261108-a01/`；a01源schema失败止于抽样前，保留不覆盖。
- 独立retokenize、全部源SHA、40参考代码隔离测试通过。输入104–1006token，不宣称长上下文。
- 下一内部动作：冻结源码/查重/展示完整2GPU命令，再create一次，核对code200与精确UUID。
  沿用确认镜像digest、WeaverDev/qiji、1节点×2H100/256Gi；最多8小时，不因结果扩样追绿。
  成功后本机隔离质量/两独立重放/证据SHA/进度提交推送，完成后再询问下一大阶段。
- 上述提交已完成：code200，精确UUID=`job-a99898c2f332-20261108164059`，node208，
  08:41:27 UTC启动，实际queue=proj-31，2H100/256Gi/原digest已核对。
  source pin=`65364f55ae0d367438f11efaa1c06332c2ebc717`，源tar SHA=
  `ac85e3ca050e50a614ceb4f840e7023dcebb1d7a0932bf1bec67d84de371328b`。
  私有运行`logs/confirmation-run-20261108-a01/`，只监控公开a02与准备目录lifecycle。
  不重复create、不改运行代码；运行中只允许更新文档。GPU结束后才本机finalize/audit。
- 最新GPU已Completed/Pod Succeeded/exit0，08:41:27–10:49:13UTC，255快照单Pod/restart0；
  两卡0MiB/0–1%，两条件新δ0.25/forcing通过。原本机finalize失败：中文180参考中1个有限float。
  新评测器将该题的辅助质量标缺测，60题速度/160题forcing不删；主要摘要/代码不允许缺测。
  原partial quality/本机失败log保留，不再次运行旧完成器或新GPU。
- CPU修复148回归通过，下一步独立冻结CPU源码/归档，在新目录
  `logs/confirmation-evaluation-20261108-a01/`完成质量。GPU源始终65364f5不变。
  `confirmation.py finalize/audit`现在必须传`--quality-root <该目录>`；finalize另需
  `CONFIRMATION_EVALUATOR_EXPECTED_COMMIT`、`CONFIRMATION_EVALUATOR_TAR`、`CONFIRMATION_EVALUATOR_SHA256`。
  CPU显式CUDA不可见；只看公开a02汇总，不手工读私有样本。成功后两次重放与SHA归档。

## 最新接续点：泛化审计完成，不能宣称普适2.2倍

- 本阶段唯一记录`docs/experiments/generalization-20261108.md`已包含完整结果、失败、规则和复核命令。
  **任务已完成，不再提交GPU、不重抽样、不改final追绿、不自动sealed/RSI。**
- 200条新题（排除已知作者全部100条dev）、2048cap：全部1.823022× [1.792292,1.854873]；
  原5基准族新100题2.171842× [2.129914,2.216151]，新5领域100题1.530226× [1.487339,1.574006]。
  不只是原30题有效，但公开题不能保证作者绝对未见，也不能把这些结果当原sealed数字。
- **中文阅读QA减速：0.513279× [0.464119,0.573095]**，整请求约需1.94倍时间，
  输出长度stock/final72.65/72.30，自然EOS，不能只用总体均值掩盖。
  同4中文面板题256/2048/4096约0.4263/0.4274/0.4282，上限加长未消除减速；尚未做因果profile。
- 摘要ROUGE-L0.322758→0.302970，差-0.0197875，未校正95%CI[-0.0420161,-0.0027901]；
  合成参考/代理/多重比较限制，不断言语义已退化。4096 HumanEval3/4→2/4，n=4证据不足。
  MT/普通指令未作可靠语义评测；不能宣称全任务质量非劣或排除所有reward hack。
- 同40题长度面板256/2048/4096分别1.753500/1.790064/1.799322×，不是拿全200题与40题直接比cap。
  两臂4096各8/80轮次输出触顶，保留自然EOS，未把不同cap/两卡重复当新独立样本。
- 新noise分别0.3498892%/0.3413052%/0.7115808%，全部前后null计入；不要求CI覆盖1或全宽0.2%。
  三cap全局δ0.25、rate/event通过、全局零大margin事件；局部HumanEval4096更小δ下有1事件/轮，
  stock也有1，未触发门禁。中文4题在256/4096局部δ无法标定，明确证据不足，不套旧值。
  **joint_acceptance=true只表示总体性能＋forcing，不表示全域提速/语义非劣/数学lossless。**
- GPU UUID=`job-6b21065b7a0e-20261108104221`，node244，02:42:54–07:04:34 UTC，
  4h21m40s，Job Completed/Pod Succeeded/容器与脚本exit0；522快照只见单Pod UID/容器restart0，
  Job retryCount未设置。两卡清理0MiB/0%，端口释放。a01 Failed/retryCount2无真实测量，原证据保留。
- source pin=`c39c7af0b244e2669bb307ec5684c4165f16d6f6`，固定镜像/WeaverDev/qiji/实际proj-31，
  原2 H100/256Gi；运行期间仅文档commit6f2fb9b，代码/config始终未变。
  `source-a02.tar` SHA=`c19da8e1726c92cccea411bc0a708eb8e0c2024e427d30069a84e03752c67a5b`。
- 私有输入`logs/generalization-data-20261108-a04/`，私有输出`logs/generalization-run-20261108-a02/`；
  **agent不要读题目/答案/逐题输出**，只看`logs/generalization-public-20261108-a05/`聚合报告。
  受控sudo/controller读取root私有证据；代码题仅本机Landlock/seccomp隔离执行，未无沙箱降级。
  dataset SHA=`7c179e5d0f84fb87b0ebcdb78a70248f15c01e51d9668ee1b72da5cdcb514486`。
- 远程1400条完整FP32评分，本机任务质量与证据统一验收07:18:27 UTC完成；40参考代码通过，137回归通过，
  两独立进程重放与result.json逐字节一致，三份SHA均为
  `df269e986755c02b3d94810e76d75315c8572cbb6a28e4acc1b264c7600aa3a3`。
  不要重跑`generalization_local.py`覆盖现有质量产物；只用冻结`generalization_audit.py --out <新路径>`复核。
- 成功/失败/源码/原始证据共10312文件、598919466字节，清单
  `logs/generalization-evidence-20261108-a01.sha256`，SHA=
  `2fc0112af7d18e7fa368fa15aa88138e0afaceef4b1cfa9b0b82dd23c2757675`，全量核验通过；
  旧dev1223文件SHA复验全过。controller/patches/作者config/dev相对e12537c无变化。
- promoted=false/ledger_eligible=false；未读既有sealed、未RSI、未写ledger/memory。
  下一大步骤先提出中文短回答性能与摘要/长代码质量告警的独立确认方案，再由用户选择与正式sealed的顺序；
  这些是本次发现的研究问题，不是擅加论文硬门槛。若以后改final，此集转dev，必须换新确认集。

## 本阶段准备/执行历史（已完成，不再作为下一步）

- 新唯一阶段记录`docs/experiments/generalization-20261108.md`。用户已批准实际运行，阶段内自主；
  不修改final/stock/46开关/controller，不读取现有sealed，不写ledger/memory，不RSI。
- 200条新题：原5领域各20（ID100）＋中文QA/科学QA/摘要/JSON抽取/普通指令各20（OOD100）。
  排除作者全部100条dev与内部近重复，独立retokenize/源SHA及40代码参考解验收通过；
  固定40题长度面板额外256/4096cap，2048复用主集同题；自然EOS，不把跨cap/卡轮重复当新样本。
- 私有数据`logs/generalization-data-20261108-a04/`，dataset SHA256=
  `7c179e5d0f84fb87b0ebcdb78a70248f15c01e51d9668ee1b72da5cdcb514486`。
  **agent不得读取新题目/答案/逐题结果**；仅查看`logs/generalization-public-20261108-a04/`聚合状态/报告。
  同UID约定隔离不冒充第三方物理盲评。输入59–636 token，不宣称长上下文泛化；摘要参考为合成数据，
  对话无可靠语义裁判。若结果后改final，此集转dev，必须换确认集。
- 运行入口`exp/generalization_remote.sh <新私有输出> <dataset.json> <公开状态目录>`，
  复用既有controller计时/统计/forcing，exp仅新协议编排和代理质量；三cap各前null→候选→后null、各两轮fresh/物理换卡。
  全部测速结束后新AR/完整自身prefix FP32评分/任务质量；不套旧δ或旧noise。
- 新旧136项CPU测试通过；源冻结提交/最终NorthJob命令/UUID待登记。沿用用户已确认digest镜像、
  WeaverDev/qiji/实际proj-31/原toleration、单节点2 H100/256Gi，最长8小时（16GPU小时）。
  查重→展示完整命令/资源→create一次→code200+精确UUID，含糊先查不重提。
- 已提交一次：source pin=`c085f8bc069228c9dd156aac578f9d99ae6427f4`，
  UUID=`job-611d30b86458-20261108103155`，code200且精确名唯一；初始Pending。
  私有输出`logs/generalization-run-20261108-a01/`不要读取；只监控公开a04状态目录。
  不再次create，执行/科学验收仍待结果；生命周期落准备目录，最终更新以阶段记录为准。
- 准备失败a01/a02为数据源路径/下载，a03为CMRC schema；均无GPU提交/性能结果，原证据保留。
  目前尚未产生新泛化数字；30题dev通过记录见下，不借其替代新数据验收。
- 最新：GPU a01已Failed（node204，retryCount2，原日志和监控权限失败保留），未进入真实runner，
  **无性能测量、无模型server**。远程沙箱正例自检不通过，具体worker stderr当时未保留；
  不断言未经证实的内核根因。公开root日志0600也已诊断，只恢复公开文件可读，私有目录不开放。
- 修正执行位置：新a02远程只配对+FP32 forcing，代码题/质量固定移到本机已验证CPU隔离器，
  root本机9项隔离/编排合成测试通过、新旧137回归通过。新`--defer-quality`只记录质量待完成，不能当科学通过。
  a02公开状态`logs/generalization-public-20261108-a05/`，仍复用a04同一dataset SHA；不重抽样或改final/controller。
  远程完成后用`exp/generalization_local.py`（CUDA_VISIBLE_DEVICES=''，受控sudo读取root私有输出）
  完成质量和独立重放，只读公开汇总；新任务查重/源码pin/UUID见实验记录后续登记。
- a02已code200+精确UUID=`job-6b21065b7a0e-20261108104221`，node244，02:42:54 UTC容器启动，
  pin=`c39c7af0b244e2669bb307ec5684c4165f16d6f6`，公开events进入2048cap/null-pre/round1。
  **不要再次提交或修改运行代码**；前台monitor session13645，文件`logs/generalization-prep-20261108-a01/lifecycle-a02.*`。
  新纯合成探针确认为Landlock后ctypes库查找误走gcc/tempfile，非内核不支持；本机质量路径已验收。
  GPU脚本exit0且gpu-complete存在后，才运行本机质量、两次独立重放/证据SHA，再报告泛化结论。
  运行中只允许文档进度提交，不变更controller/exp/harness/assets；运行身份始终使用上述pin与source-a02.tar。

## 历史接续点：30请求正式dev联合验收通过

- 新入口`docs/experiments/dev-joint-20261108.md`；本阶段controller协议适配/证据联动获用户授权，
  默认legacy不变，不放宽判据。128项回归、旧P5重放/1347历史SHA与本活动独立重放通过。
- UUID=`job-e71c6069ec59-20261108081913`，node135，08:19:29–09:10:36 +08:00，51分7秒；
  Job=Completed/Pod=Succeeded、容器与脚本exit0。观测单Pod UID/Created1/Started1、容器restart0，
  Job retryCount字段未设置。原镜像/WeaverDev/qiji/实际queue=proj-31，2 H100/256Gi。
  source pin=`721b72c013aa6323837de30cba740c6eb55bf796`，运行中源码未变。
- 输出`logs/dev-joint-20261108-a01/`，准备/提交/生命周期`logs/dev-joint-prep-20261108-a01/`。
  固定每suite6条共30请求、2048cap自然EOS；null-pre → candidate → null-post，各两轮fresh/物理换卡，
  2条短预热＋全30条全尺度预热，实际原生生成证据计时后落盘；测得120条输出＋新AR30完整评分。
- final/stock=2.2214815927×，suite分层request-cluster95%CI [2.1585000041,2.2827307674]；
  两轮分别2.219895/2.223069。null-pre=1.00051887 [0.999775944,1.001327351]，
  null-post=1.00026564 [0.999435387,1.001086805]，两会话全部纳入noise=0.00132735095。
  current_campaign_usable=true，输出不同故收益门槛3%，95%收益下界115.85%，性能通过。
- 两轮独立δ=0.25；各轮stock198/25307=0.782392%、final187/24811=0.753698%，零大margin事件，
  rate/event均未触发，正确性均通过。新AR只标定δ，没有重测AR性能。
- joint_acceptance_passed=true，但promoted=false/ledger_eligible=false：作者产物不是自主发现。
  两次独立进程重放JSON字节相同，源码tar/独立retokenize请求/原始HTTP/评分/时序绑定均通过。
  测速后与评分后/最终两卡均0MiB/0%，端口释放；不能把Job Completed单独当科学通过。
- 本活动1223文件清单`logs/dev-joint-evidence-20261108-a01.sha256`，SHA256=
  `0ced7f2f3b760971ba9428ffb344e7da1a1bb974debfa715cd2320ce57c1d4f1`。
- 下一步先向用户报第6步sealed隔离/正式验证的目标与流程，获准后由controller/维护者落实。
  本阶段未读sealed、未做RSI、未写ledger/memory；不自动追加100请求或重复作者基线追数字。

## 已完成：第5步真实裁判回归（上一子阶段）

- 唯一新实验入口`docs/experiments/p5-real-controller-20261108.md`。用户授权本阶段controller改动，
  显式paper-aligned策略、真实FP32 scorer、δ与rate/event规则、runner/证据重放已交付；旧默认不变。
- 成功任务`job-93e052b78439-20261108074348`，node135，07:44:08–07:51:40 +08:00，
  Job=Completed/Pod=Succeeded，容器与脚本exit0；观测单Pod UID、Created/Started各1、容器restart0，
  Job retryCount字段未设置。2 H100/原镜像/WeaverDev/qiji/实际queue=proj-31，两卡清理0MiB/0%。
- 执行pin=`bfb5d6c39fc5cf435557f886e5eda99f7d4b3bdb`；输出`logs/p5-real-forcing-20261108-a02/`，
  源快照/提交/生命周期/独立重放脚本和结果在`logs/p5-real-controller-prep-20261108-a01/`。
  最终controller身份补强pin=`58f37d16f7f432ae1f2e50b34f8ec4dbdda63852`，两次离线重放JSON字节相同。
- 原20请求dev：14对首分歧标定δ=0.25；stock178/20250=0.879012%。健康stock、AR、分段续写、
  等价head均通过；故障475/18512、298大margin事件、rate/event双拒绝；作者final145/19295通过。
  故障实际post2048共8272 token；前200事件prefill审计解释0，另98未审计且按预定规则保留未解释。
- 等价控制5suite×64=320 token，真实checkpoint/FP32逆序8块；logit差最大7.629e-6，选择差异0。
  121项P2/P3/P5 unittest及shell/diff检查通过。全文件discover误导入旧8B独立GPU脚本因无torch失败，
  原失败保留，未修改或擅自运行该旧脚本。无完整Fig4任务精度区间、sealed或数学lossless结论。
- a01完整生成75条后，在head有限值整矩阵临时分配处OOM，原校准/输出不改；CPU分块验证修复后，
  a02按冻结249文件SHA清单复用全部真实生成并用fresh scorer全部重评分，明确不是单会话/性能配对。
  a01最终Failed/retryCount2和两次接口探针失败均保留，不把最终Pod restart0当全任务无重试。
- 新结果judge_ready=true，promoted=false/ledger_eligible=false；历史null重放noise=0.0022681713，
  current_campaign_usable=false，不能充当前正式校准。不自动进入sealed/RSI/写ledger。
- 1347文件证据清单`logs/p5-real-controller-evidence-20261108-a01.sha256`，SHA256=
  `050794539a3104f4fce85a56ba88704513a31438bf301e680847cd77df61c815`，包括所有失败和成功执行及源码快照。
- 下一步先向用户报正式dev扩围/当前null与候选联动的目标和主要流程，批准后再执行；
  不重跑已经完成的作者性能基线，不再为0.2%或覆盖1额外工程自检追绿。阶段验收后按授权推送私有origin。

### 以下为本阶段早期及上一阶段历史记录

- 最新用户已明确批准本阶段修改controller（仅校准与正确性验收），阶段内自主执行，不进入sealed/RSI/正式晋升。新入口记录`docs/experiments/p5-real-controller-20261108.md`。先红后绿的新旧105项CPU测试通过：显式paper-aligned-v1校准/候选readiness判定及native teacher-forced评分传输，legacy默认不变。准备短NorthJob接口探针，真实scorer/δ/注入/等价控制尚未验收；勿将接口测试当真实正确性通过。
- 本次记录：`docs/experiments/p5-acceptance-alignment-20261108.md`，依据用户PDF的§3.2/3.3/3.4/5.1；文档规则`paper-aligned-v1`见`docs/02-acceptance.md`。用户明确要求“对齐验收规则”，本次仅文档修订，不修改controller/运行代码，不提交GPU、不读sealed、不写ledger。
- 论文要求收益95%下界超过`1% + 2×实测stock-null噪声`，输出有分歧时约3%；H100 noise<0.1%是论文观测值。论文没有规定null CI全宽<0.2%或两独立会话均覆盖1，也没有规定CPU独占。上述额外自检降为诊断，不再以此阻塞研究主线或继续追绿；校准有效性、真实正确性及晋升下界仍必须验收。
- 历史precision/centered/stable字段、失败JSON和gate exit=1保持原值；本次不宣称旧实验新通过。controller尚未切换，不能由harness另设裁判绕过。正式noise估计量、跨会话选择、CI尾概率与候选同尺度协议需维护者先确认并接入；真实FP32-head scorer、stock mismatch/δ、故障注入/归约对照仍未完成。
- 下一步应先报真实裁判交付流程再获准执行；不重跑A1/A2/A3，不把CPU资源配置当唯一前置，不自动sealed/RSI。旧“先把CI压到0.2%/先等独占CPU”的接续计划已由本段替代。架构与论文数字复现仍分开报告。

## 第5步历史实验与权限记录（以下非当前执行计划）

- 最新完成CPU亲和性受控复验：`docs/experiments/p5-cpu-bound-null-20261107.md`，执行pin=`794219b`。UUID=`job-788af093f15c-20261108003647`，node131，16:37:05–17:22:20 UTC，Job=Completed/Pod=Succeeded，容器/脚本exit0、restart0，两会话两卡清理0 MiB/0%。会话1=1.0002672639、CI[0.9998000780,1.0007914498]、全宽0.0991372%，stable=true；会话2=0.9990706080、CI[0.9977318287,1.0003567337]、全宽0.2624905%，stable=false。均覆盖1且CPU绑定验收通过，但整体稳定性门禁exit1；不挑首会话、不合并平均、不再同配置追绿。
- CPU修正默认关闭，只在stable-null配合`--pin-cpus`；GPU固定scheduler主核2/50、各自8后台核，全部线程监控通过；不改controller/统计/门槛/引擎/时钟，不等于独占CPU。98项回归、独立复算两次JSON一致、历史校验通过。161文件清单`logs/p5-cpu-bound-null-evidence-20261107-a01.sha256`，SHA=`3b76e931a655ea915d97a1fae2e13766c8d1d87e46514a12a155573ac1f23a8d`。
- 此前资源诊断分支：真实Pod为Burstable、无CPU request/limit；当前NorthJob CLI无CPU预留/独占参数。第二会话约80.57%分层方差来自HumanEval，服务端也有延迟差；不能断言CPU是根因。一次预登记CPU修正已执行完，曾建议确认可用CPU隔离资源再做诊断；2026-11-08已取消其通用前置地位。不得擅自修改集群、升级CLI或手写Volcano提交，不盲重提。
- GitHub原credential helper指向已清理的`/tmp/handoff-gh/.../gh`；本轮push只在该进程使用`logs/p5-github-credential-helper.py`读取本人现有gh配置，未改全局配置、未把凭据写入Git/对话。后续push应注意此环境限制，不打印token。
- 稳定化a01已完成：`job-8f1d3b6bafa2-20261107233518`，node131，15:35:54–16:23:17 UTC，Job=Completed/Pod=Succeeded、容器/脚本exit0、无重启，两卡清理0 MiB/0%。会话1比值1.0020415084、CI[1.0011419394,1.0029587541]、全宽0.1816815%；会话2比值1.0018638161、CI[1.0010030732,1.0027354135]、全宽0.1732340%。两次precision=true但centered/stable=false；不平均掩盖，不盲重跑。141文件清单SHA=`7b99fcff66511193a200153c301600ae387a730766717d29db1335287477f1bb`。详见稳定化报告结果段；91项回归及独立复算通过。CPU迁移/亲和性是待受控验证假设，尚无因果结论；若继续本授权需先登记实质修正，不改controller或门槛。
- 最新用户已批准噪声稳定化大流程，明确流程内自主实现/调试/复验，无需中途请示；上一轮“只读、再复验需批准”是历史限制。高风险/额外权限仍须审批，不放宽门槛、不读取sealed、不设置共享GPU时钟。
- 正在冻结新协议代码：`docs/experiments/p5-stable-null-20261107.md`；固定完整20条/2048cap预热一遍，正式同20条，每会话预先4轮fresh双server/GPU×端口独立交叉，启动/提交顺序平衡并有线程屏障、HTTP实际时序、每2秒GPU/CPU监控。两独立会话均须全宽<0.2%；另加CI覆盖1的工程自检防窄但偏移，不冒充论文新增判据。20请求仍20独立cluster，不把4轮当80独立请求。
- 新旧91项测试通过、历史统计复算不变；入口 `exp/p5_remote_stable.sh <新目录> <A1目录>`，显式 --stable-null 启用，默认旧协议不变。a01于2026-11-07 23:35:18 +08:00唯一一次create code200，精确名查重解析UUID=`job-8f1d3b6bafa2-20261107233518`；原镜像/WeaverDev/qiji/实际proj-31/2 H100不变。现已结束，切勿重复create；真实forcing/注入不在本次噪声稳定化范围。
- 以下只读诊断是此前完成记录，本轮执行状态以最新协议记录为准。

- 最近用户只批准分析已有日志，本轮未提交GPU、未启停server、未改controller/exp/harness/gates或测量协议。下一次GPU复验须先报主要流程并获准，不能把此次“允许”当提交授权。
- 只读诊断 `docs/experiments/p5-noise-diagnosis-20261107.md`：8个server启动参数仅端口不同，输出/verify工作量一致且确实物理换卡。客户端残差通常约2ms，第二会话server时段仍有0.3273%偏差（客户端0.3333%），首会话server影子CI全宽仍约0.2635%，所以不能只换计时字段解决。
- 首条425-token/81-verify请求的双臂均时跨轮1.995–2.739s、跨度37.3%；其余19条的双臂均时跨度<1%。源代码预热是前两请求各最多32新token，结束后约0.5–0.8ms立即测速。支持优先检查启动稳态，但固定请求顺序混淆了样本与位置，不能断言预热是根因。
- 第一会话GPU1在36/40对更快，第二会话29/40，角色/端口/先发顺序/时间仍混杂。Pod没有显式CPU request/limit、numa_node=None；没有GPU频率/温度/功耗、实际CPU亲和性/运行负载、两臂发送时间等时序，不能甩锅“某张卡差”或认定CPU争用。第一会话gsm8k贡献约69.51%的分层bootstrap方差；前两请求的全局离散70.22%不等于贡献70%的CI方差（实际分层贡献34.61%）。
- 4个离线脚本在a02重放JSON一致，79测试、所有历史清单及运行实现未变验证均通过。最终26文件清单 `logs/p5-noise-diagnosis-evidence-20261107-a02.sha256`，清单SHA=0f42977b996332bfd6b86b5887bf7a58884b94c91f08b12275bbbe55b1e71512。脚本/输出在同名前缀a01/a02目录，完整SHA见报告，不覆盖旧测量。最终影子CI严格沿用原suite顺序/seed，客户端区间先逐字段复现，再换server时段；不要把初步排序suite的supplement端点当最终影子结果。
- 建议待批准后固定一次全尺度未计时预热并补状态/发起时序记录，再有限复验两会话；不删首请求，不把多个会话平均成通过，不改原20请求/2048cap/自然EOS/物理换卡/<0.2%要求。本轮止于日志诊断，真实FP32 scorer/注入/sealed/RSI均未推进。

- 用户在审计之后明确授权“允许修改”：范围为本阶段 controller 正确性/统计修复，不放宽判据，不读取 sealed，不进入 RSI。后续普通 agent 仍须遵守 controller 维护者边界，不能推定永久授权。
- 修复记录 `docs/experiments/p5-controller-repair-20261107.md`。空/长度/统计溢出/rate rule/输出分歧性能门槛已修；stock stock 显式展开 stock-a/stock-b，底层仍启动 stock。原 9 个合成反例全过，新旧 79 项测试通过，仍没有真实 lossless/晋升结论。
- 真实 null 已结束：`job-3c6565eedef3-20261107210140`，测量源 pin=dbebc6b88e97b893d7a0afd2a326a8ed37fd1bbc，2026-11-07 21:01:40 +08:00 code=200 后按精确名解析唯一 UUID。原镜像/WeaverDev/qiji/原 toleration、2 H100，node233；21:02:04启动、21:18:55结束，Job=Completed/Pod=Succeeded，容器/脚本exit=0、restart=0；两会话各两卡清理0 MiB/0%。输出 `logs/p5-stock-null-2048-20261107-a01/`，总80 pair/160臂行，但仅原20个不同请求。
- Session 1：比值0.9999525264、分层双侧95% CI [0.9986248088,1.0012594020]，全宽0.2634593%，noise=0.1375191%，precision_passed=false。Session 2：1.0033328725、CI [1.0026846326,1.0039834119]，全宽0.1298779%，noise=0.3983412%，precision_passed=true。整体精度门禁exit=1；两实例/卡位/会话输出一致不等于lossless。不能挑第二会话或跨会话平均掩盖失败，不重提追绿，不进入sealed/RSI。
- 下一步应先定位预热/稳态与角色时序偏差，登记稳定性协议；真实FP32-head scorer/stock mismatch/delta/注入及归约对照尚未完成。黑盒help已确认有 --enable-fp32-lm-head，但开关存在不是验收通过。权限阻塞已解除，当前是实测精度门禁未过。
- 78文件清单 `logs/p5-controller-repair-evidence-20261107.sha256`，清单SHA=170479f90a00a324865fe3430f9ab066906e19b213d52cdbef997fc9790f0c4d；完整源码快照在repair-a01/final-source.tar。95组SciPy核验、最后79测试、历史统计复算/清单均过。测量结束后仅澄清null reader CI字段标签，原始数据与判断未变，复验结果见independent-null-reaudit.json。详细报告记录具体路径与SHA。
- 以下审计条目是修复前历史，当前状态以本段与修复记录为准。

- 用户已批准开始第 5 步，但没有授权修改 `controller/`。先做只读 CPU 审计，无 NorthJob create、无 GPU 进程、无 sealed/作者实现访问、无 ledger 写入。
- 新入口 `exp/p5_readiness_audit.py --out <新JSON路径>`，只用合成 token / 内存 fixture 调用已有接口；exit=1 是未就绪证据，不是可放宽的正式门禁。
- 9 项检查全部未过：空请求/空 token 误报 lossless；少尾/多尾/整条缺失仍误过；4096 相同 token 自比 OverflowError；1000/1000 分歧 rate_flagged=False（event 此例仍拒绝）；合成输出不同的 2.5% 增益被 HTTP compare 标 promoted；stock stock 非执行计划被现有 CLI 拒绝。不是 9 个独立根因，也不是 27B 真实注入。
- scorer/margin/delta/实测 stock mismatch、真实注入及独立双 server null 尚无证据，不能绕过 controller 在 harness 另立正式裁判。审计工具 7 项测试、既有 P2/P3 50 项回归通过；不表示第 5 步通过。
- 记录与维护者交付清单：`docs/experiments/p5-readiness-20261107.md`；原始 `logs/p5-readiness-20261107-a01/`，复验另用 a02，不覆盖旧证据。继续需用户明确授权限定 controller 改动或维护者交付；不自动进入 sealed / RSI。
- a02 复验 9 项观察相同、exit=1；最终 57/57 测试通过，P2 a05/A1/A2/A3 历史证据和 controller 未改验证通过。新 12 文件清单 `logs/p5-readiness-evidence-20261107.sha256`，清单 SHA=5dc42cbdc0ba68dba02ccc2c3abfdce6955ea293c6b58a1d0a9af091ab1c3480；含完整审计代码/测试快照。阶段仍 blocked，不把“工具测试通过”写成“真实裁判通过”。

## 前一阶段：第 4 步作者 final 验证（不是 sealed Phase 4）

- 当前第 4 步已完成：A2 final/AR=8.7347197445× [8.0234899904,9.5599189918]；A3 **直接 final/stock=2.2218558884× [2.1380887617,2.2987528227]**，不是两次 AR 对照相除。两项实验均 20 原请求/2048 cap/自然 EOS、两轮 fresh server/物理换卡，各 40 pair/80 臂行、Job=Completed/Pod=Succeeded、容器/脚本 exit=0、GPU 清理 0 MiB/0%、50/50 回归及独立统计复算通过。源 pin=4d67c2f4acfa1b68df24ef3de5a8cf53819e1962，模型/镜像/调度参数未换。
- A3 唯一 UUID `job-4508734deeb3-20261107190750`，19:07:50 +08:00 code=200，19:08:14 启动、19:16:09 结束，node204，无重启；A2 已结束后才提交，最大同时占 2 GPU。输出 logs/p3-stock-final-2048-20261107-a01，38 文件清单 logs/p3-stock-final-evidence-20261107-a01.sha256，清单 SHA=bd5088cdd15862f2959cf7e327af7a4f8b04fdc76d12c051fbcf37bc6026bff6。A2 的 37 文件清单与 A1 历史清单均再次复核完整。
- 解释边界：AR/stock/final 平均实际长度为 999.0/1012.5/965.075 token；当前是作者产物 dev 子集验证，不是完整 dev（6 条/suite）/sealed、lossless 或自主发现。W12/tree/GDN 日志表明相关路径运行；缺字面 TLV 日志不等于未启用，但语义/计数仍需审计。长输出收益提高支持固定开销解释，不是同样本短/长输出严格因果证明。下一主线第 5 步真实正确性与噪声/晋升；先报计划获准，controller 仍仅维护者，不自动 sealed/RSI。

### 第 4 步准备与 A2 历史（以上述完成状态为准）
- A2 已完成：`job-674358f4a1a0-20261107183406`，final/AR=8.7347197445×，95% CI [8.0234899904,9.5599189918]；40 pair/80 臂行、请求绑定/树/46 开关/物理换卡/统计复算通过，Job=Completed、Pod=Succeeded、exit=0，两卡清理 0 MiB/0%。源 pin=4d67c2f4acfa1b68df24ef3de5a8cf53819e1962；输出 logs/p3-ar-final-2048-20261107-a01，37 文件清单 logs/p3-ar-final-evidence-20261107-a01.sha256，清单 SHA=cabf4e5079946bec3ce9e7f18e709c0a930428b63f069b332b919033061cf417。运行日志有 W12/tree/GDN 路径证据，未检出 TLV 字面日志，不宣称已审计 TLV 语义/lossless；其后 A3 已按计划完成，不重复任何 create。
- 当前完成：用户授权本阶段自主拆分、调试、测试及正常范围内重跑，小步骤不再等待回复；高风险及 skill 的查重/镜像/不明确提交保护仍有效。a04 首轮完成后因端口 TIME_WAIT 误报失败，已保留全部证据；只在探测 socket 增加 SO_REUSEADDR，真实 TCP 回归先红后绿，真实监听仍拒绝。最终 CPU 回归 26/26（17 编排 + 9 挂载/验收）通过；controller、sealed、账本、模型和镜像未改。
- a05 完成：2026-11-07 16:42:26 +08:00 code=200，唯一 UUID `job-ad27e2790ef7-20261107164226`；16:42:45 启动、16:47:09 结束，Job=Completed / Pod=Succeeded / container exit=0 / script exit=0，无容器重启。源 pin=`0bb2965474bc7b2872d59bc6f311c94ebf6b22b1`；原 5 请求/64 cap/两轮物理换卡全部通过，10 pair/20 臂行、请求哈希一致，两张 GPU 清理后均 0 MiB/0%。结果 `logs/p2-remote-smoke-20261107-a05`；33 个证据文件清单 `logs/p2-evidence-a05-20261107.sha256`，清单 SHA=231d9d7fcc24a526750d925eb2ad5a5321b4893f909789d09aa875fa0ad74e03。统计复算与持久 summary 完全相同，但这是短输出诊断，不是论文/正式性能或 lossless 结论。
- 当前主线已完成：AR/stock 20 请求、2048 cap、两轮 fresh server/GPU 互换，40 pair/80 臂行完整。stock/AR 几何平均 **3.8698909614×，95% CI [3.5570626359,4.2241726177]**，既有点估计判据 [3.555,4.345] 通过；两轮 3.8768596249× / 3.8629348241×，不能把差值当噪声地板。自然 EOS 保留，每臂 40 行中 30 stop/10 length，AR 平均 999.0、stock 1012.5 token，不能说每条生成满 2048。
- a01 唯一 UUID `job-3214d33ae356-20261107173128`；2026-11-07 17:31:28 +08:00 code=200，17:31:51 启动、17:50:33 结束，Job=Completed / Pod=Succeeded，容器/脚本 exit=0、restart_count=0。源 pin=`79fe81a61ffc38cc6a1352cbf0f25fe6668c280a`；原镜像、WeaverDev、namespace=qiji、请求 queue=qiji/实际 proj-31、toleration 均未换。输出 logs/p3-ar-stock-2048-20261107-a01，独立校验/统计复算一致、GPU 清理为两卡 0 MiB/0%，39/39 回归通过；38 文件清单 logs/p3-baseline-evidence-20261107-a01.sha256，清单 SHA=69f88e265d58e89ef86bc90878db3f61808bab2143fe578c2ac41f1be217c7b5。详细报告 docs/experiments/p3-ar-stock-2048-20261107.md。
- 当前第 4 步已获用户批准：先 A2 AR/final、再 A3 直接 stock/final，独立两次任务、各 2 H100，不并发占 4 卡；同 A1 原 20 请求/模型/采样、2048 cap、warmup=2、两轮 fresh server/物理换卡。新入口 exp/p3_remote_final.sh <ar|stock> <out> <A1 reference>，final 身份、A1 请求绑定及统计完整性由 harness/final_validation.py 校验；共享逻辑泛化后 A1 旧验收输出完全相同，新旧 50/50 回归通过。原镜像/WeaverDev/qiji/原 toleration 保持，不套用 A1 3.95 或 sealed 2.13 门槛；低收益也保留数据并排查，不进入 RSI/sealed。记录 docs/experiments/p3-final-2048-20261107.md；准备冻结源 pin 并先提交 specpilot-p3-ar-final-20261107-a01，后提交 specpilot-p3-stock-final-20261107-a01。

### 以下为准备及失败历史（当前状态以上述完成记录为准）
- 当前在原十步主线的第 2 步“配对测量远程验收”；镜像、CLI 和挂载是内部准备，不重新拆成研究大步骤。大步骤先报目标、流程与自检并等用户允许，内部小步骤自主安排。
- 用户已批准开始第 2 步，并明确同意使用下面固定 digest 的 oss-sglang 镜像。首次提交于 2026-11-07 06:46:44 UTC 被 HTTP 403 / code 40301 拒绝：账号 jixinpeng 不属于 default 项目。提交后按原名查询 total=0；无 code=200、无 job_uuid，未启动远程测量。需确认可用 `--project` 并获准重提，不要直接再次 create。运行记录见 `docs/experiments/p2-remote-smoke-20261107.md`。
- 用户随后明确指定 `--project infra-dev-weaver --k8s-namespace qiji --k8s-queue qiji --k8s-toleration key=task-type,operator=Equal,value=infra-dev-weaver,effect=NoSchedule` 并授权重提一次。已核对 CLI help、凭据格式与查重；新尝试名 `specpilot-p2-smoke-20261107-a02`，代码 pin 与镜像不变。2026-11-07 15:23:13 +08:00 返回 HTTP 400 / code 40005：项目 infra-dev-weaver 不存在；无 UUID，提交后 total=0。模板确认四项参数正确、无新增 nodeSelector；项目、namespace/queue、toleration 不能混同，toleration 不保证只调度该池。暂停，核实后端项目身份并取得新授权后才能再次提交。
- 用户要求只读排查后，已交叉核对 CLI/API 与两条本人 Kubernetes 任务：当前账号 jixinpeng、CLI 3.3.11、后端 10.1.2.7:31000 均无身份/环境覆盖异常。旧 infra-dev-weaver 任务在服务端为 project_exists=false / user_in_project=false；本人 WeaverDev 任务为 true / true，且现场注解、namespace/queue 与 API 一致。建议下一次仅改 `--project WeaverDev`，保留 qiji namespace/queue 和 infra-dev-weaver toleration，待用户授权再提交。只读诊断证据 `logs/p2-project-diagnosis-20261107.json`；不能据此称 GPU 配额、调度或镜像兼容通过，也不知道旧任务的创建路径或项目历史变更。本轮没有 create/update/delete。
- 用户随后批准修正项目重提。a03 名 `specpilot-p2-smoke-20261107-a03`，2026-11-07 15:54:59 +08:00 收到 code=200/data=None；精确查重唯一匹配 UUID `job-65f7d61d3d7f-20261107155459`，确认提交成功。进程 15:55:52 +08:00 已启动；持久日志显示 git dubious ownership，脚本 exit=128；最终 Job/Pod Failed（容器 exit=1）。未创建 runner 输出目录、未到 GPU 预检，无配对数据。请求 namespace/queue 为 qiji，服务端有效 queue 为 proj-31，不能隐瞒这一差别。未再次 create。下一次建议仅在任务命令的进程环境中设置 `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/gpfs/users/jixinpeng/SpecDec/SpecPilot`，不改全局配置、不信任通配路径；本机模拟 Git 归属不匹配验证 128→0，尚需新授权才能重提。记录见 docs/experiments/p2-remote-smoke-20261107.md。
- 可用 CLI 已找到：`/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/northjob`（3.3.11，参数与 skill 匹配，get 查询成功）；不再用缺 Kubernetes 依赖的 `/gpfs/envs/miniconda3/bin/northjob`，未升级 CLI。计划名 `specpilot-p2-smoke-20261107` 的查询 total=0；真正提交前重新查重。
- 已从本人现有任务核对镜像候选：`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。仅证明在集群已有运行实例，不证明适配本实验；拟优先复用共享 `sp-sglang1520` 环境，不切换为镜像内未知引擎。
- 挂载已补最小适配：`exp/p2_northjob.py create ...` 在本进程调用原 CLI，仅在其生成的模板上追加 `share-readonly` / `models` 子路径到 `/gpfs/models` 的只读挂载；主挂载用 `jixinpeng-pvc` → 用户目录。不改已安装 CLI、不复制权重；真实模板离线验收通过。`RUN/` 已忽略，提交回执与日志保留在 `logs/`。
- 原编排测试 15/15，新增真实端口回归后 17/17；挂载与验收测试 9/9。stock/final 的 5 请求、64 cap、两轮烟测已在 a05 完成（10 pair / 20 臂行）。入口 `exp/p2_remote_smoke.sh`，1 节点 × 2 H100，256Gi，禁 RDMA 和 hostNetwork；只验收生命周期与落盘，不设论文收益门槛。代码 pin 比对 exp/harness/controller，允许后续只更新文档。
- 私有远端：`https://github.com/Sym-Je/SpecPilot-reproduction.git`（origin）。用户已授权每个大步骤结束后更新 README 进度、交接与相关代码，验收后阶段提交并推送；不上传大产物、凭据或 sealed 数据。
- 重新对齐论文/公开项目后的详细方案见 `docs/11-reproduction-plan.md`（草案，未授权修改 controller 或已有判据）。其中区分每 suite 4 条诊断、上游默认 6 条 dev 表格和后续 sealed；正式 CI 与真实 forcing 尚有维护者待办。
- `exp/p3_pair_run.py` 已实现 fresh 双 server、controller 逐请求配对、两轮物理 GPU UUID 互换、每轮一对 JSONL 和几何平均 CI；controller 未改。
- 验收：`PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s harness -p test_p3_pair_run.py` → 15/15；shell 语法和 `git diff --check` 通过。
- AR/stock 的 20 请求、2048 token、两轮执行已尝试，但在起 server 前被忙卡保护拒绝：GPU0/1 分别有 PID 59780/59781（各约 518 MiB，当前命名空间查不到进程名）。未杀进程，无实测数字。
- 用户已将后续执行统一到 NorthJob；不再等待本机两卡释放，也不继续扩建本机调度。按 northjob-submit skill 查重名并展示完整命令与资源，核对 code==200 且有 job_uuid；镜像已由用户确认，不得静默换镜像或重提不明确的提交。
- 远程按既有配对协议复用编排：先 AR/stock（20 请求、2048 token、两轮物理换卡，诊断区间 [3.555, 4.345]），通过后 AR/final，再直接 stock/final。相同 H100 不自动取消配对规则；远程环境与 GPU 生命周期尚未验证。
- Git 管理全流程的计划、任务、证据索引和决策，见 `docs/12-experiment-management.md`；每次实验使用 `docs/experiments/TEMPLATE.md` 建记录。原始产物外存并校验，不改 controller、不手写正式账本、不提前 RSI 或 sealed。
- 本机执行日志：`logs/p3-local-ar-stock-20261107.log`；因预检失败尚未创建对应运行目录。

## 一句话现状

RSI 的**制度层**在 mock 规模跑通（G2–G5）；**执行层**已打通到"三臂各起一次真 server、
跑同一请求集、落可审计 JSONL"（P0–P3，G6/G7/G8 全绿）。
**NorthJob 共尝试提交五次：前两次被拒，a03/a04 执行失败，a05 完整远程双卡烟测通过。** 论文正式数字一个都还没独立测出；本机烟测 stock/AR 3.74×
只作历史诊断，不代表正式配对尺子已经校准。

上述五次为 P2 历史；此后 A1 单独提交一次并完成，真实 20 请求配对诊断 stock/AR=3.8699× [3.5571,4.2242]，不能与论文完整 dev/sealed 协议混称。

## 接手前必做（5 分钟）

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
git log --oneline -5 && git status --short
cat AGENTS.md              # 铁律，不可协商
cat docs/06-gates.md       # 已通过的闸门与实际数字
cat docs/07-experiment.md  # 短期实验记录 + 5 个踩过的坑（必读）
ls harness/sglang/         # 启停脚本，环境约定全在 env.sh
cat docs/09-p3-harness-validation.md   # 三臂烟测实测数字与"为什么不能引用"
```

## 1. 任务边界

复现 *SpecPilot*（arXiv 2611.02501）的 **RSI 闭环**，引擎用 SGLang v0.5.20，硬件 H100 + Qwen3.8-27B + DFlash2。

**永远区分两件事**：
- **架构复现** = 闭环/测量/判据/账本/记忆是否正确
- **数字复现** = 能否独立测出 config 的 2.13× [2.07, 2.19]（sealed final vs stock）

在拿到实测前，任何"复现了论文"的说法都是错的。

## 2. 铁律（摘自 AGENTS.md）

1. 数字生产权归 `controller/`。agent 自报的加速比只是假设。
2. `eval/sealed/` 只由 controller 在 Phase 4 加载，agent 进程不得读。
3. 一切变更走 option，默认值必须复现 stock 行为。
4. 先写验收命令，再写实现。
5. 禁止：单卡串行 A/B 冒充配对测量；把"任务精度没掉"当 lossless 证据。
6. lossless 判据 = **token 级检查**（每个提交 token 都是 target 在该位置的自身选择），
   不是比文本。上游明说任何投机解码器（含 stock）输出都不与 AR 逐位相同。

## 3. 上游：只读边界

`/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main`（329 M，tarball 解压，**无 .git**，commit 78c42af）

**禁止读**：`python/`（剪枝 SGLang 实现）、`settings/*/files/`（final 机制实现）
**允许用**：`settings/*/config.json`、`research/bench/splits/`、`scripts/`、`research/dflash_lab/README.md`

上游**给了**：stock 引擎树、6 个 setting 的 final 覆盖层 + 46 个 `SPECPILOT_*` 开关、
bench/compare/score 脚本、dev split manifest（seed 20260928，5 数据集 × 20 条）。
上游**没给**（已全树关键词扫描确认，别再重新调研）：agent 主循环、cost model、ledger、
memory、candidate/campaign 管理、sealed 集、`ar` CLI。

## 4. 环境事实

| 项 | 值 |
|---|---|
| GPU | 2× H100 80GB HBM3，驱动 **535.154.05**（CUDA **12.2**） |
| 目标模型 | `/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B`（52 G）✅ |
| drafter | `/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2`（3.6 G）✅ |
| sglang 依赖环境 | `envs/sp-sglang1520`（sglang 0.5.20 / torch 2.13.0+cu130 / py3.12） |
| 引擎树 | 上游 `python/`，通过 `PYTHONPATH` 覆盖，**不 pip 安装** |
| 数据/缓存 | `/gpfs/users/jixinpeng/specpilot_data`（370 M） |
| 代理 | `http://10.51.6.1:6890`（外网必设） |
| git | 已修好：`~/.local/bin/git` → `envs/gitcli`（2.56.0）。备份 `git.bak-20261107` |
| NorthJob | `/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/northjob`（3.3.11；不用旧的 /gpfs/envs 版本） |
| 备选环境 | `envs/alice-sglang`（torch 2.9.1+cu128）—— 535 驱动上唯一原生可用的 torch，但**不含 sglang 0.5.20 依赖** |

**三个坑**（`harness/sglang/env.sh` 已针对它们写好）
1. torch 2.13+cu130 需 R580；535 要靠 NVIDIA **cuda-compat-13-0** 的 `libcuda.so.1`。
2. 全系统无 C 编译器。Triton JIT 会崩 `Failed to find C compiler`。
   解法：conda-forge `gcc_linux-64=13` 或 `nvidia-cuda-nvcc==13.0.*`。
3. 容器内 supervisord(PID 1) 会 reap 后台进程（exit 255）。长任务**前台跑**或走 NorthJob。
   `/tmp` 会被清空。

## 5. 卡点已解除：stock server 在真实权重上跑通（2026-11-07）

`logs/serve2.log`（stock 臂，block 8）：
```
Load weight end. elapsed=72.92s, type=Qwen3_5ForConditionalGeneration
Load weight end. elapsed=4.90s,  type=DFlash2DraftModel
Initialized DFLASH draft runner. attention_backend=fa3, block_size=8
KV Cache allocated: #tokens 108029
scheduler_e2e=219.34s  cuda_graph={prefill=39.73, target_verify=1.45, draft_decode=8.68}
The server is fired up and ready to roll!
```

此前崩在 `memory_pool.py:2114 _init_kv_copy_and_warmup` → triton JIT → 缺 C 编译器，
已由 `harness/sglang/env.sh` 的三件修补解决（conda gcc 14.4.0 / cuda-compat libcuda / CUDA_HOME）。

**第一条真实 greedy 请求已跑通**（`harness/sglang/probe_greedy.py`）：

```
[gsm8k-1182] 425 tok 2.70s 157.6 tok/s verify=81 tau=5.25
[gsm8k-211 ] 309 tok 1.54s 201.1 tok/s verify=46 tau=6.72
[gsm8k-877 ] 505 tok 2.50s 202.0 tok/s verify=79 tau=6.39
deterministic 3/3          → ACCEPT
```

- greedy 两次 output_ids 的 sha256 完全相同 → 逐 token 判据可以接到真引擎。
- τ 均值 6.12（论文 stock 4.65，不同请求集，不可直接比）。
- **这是烟测，不是测量**：单臂、无预热标定、无配对、无 GPU 互换。
  详见 `docs/07-experiment.md` 第二部分。

## 6. 起 server / 打请求

```bash
# 前台起（长任务必须前台，supervisord 会 reap 后台进程）
bash harness/sglang/serve.sh 2>&1 | tee logs/serve.log

# 另一终端：greedy 探针，自带确定性验收
source harness/sglang/env.sh
$SP_PY harness/sglang/probe_greedy.py --n 3 --repeats 2 --max-new-tokens 2048
```

`serve.sh` 已对齐上游 `research/scripts/launch.sh`：`--random-seed 0`、`--served-model-name`。

## 7. 之后的路线

- **P0（已完成）**：`docs/08-upstream-pin.md` — tarball sha256 `25e68b1b…602dd4`，
  规范化清单 `assets/upstream/MANIFEST.sha256`（3097 文件）sha256 `4bca3c10…81563f`；
  已核对 tarball 解包树与现有树逐字节一致（差异仅 .pyc）。
- **P1（已完成）**：`harness/build_engine.py` + `gates/g6_engine_build.py`（6/6）。
  stock `e5472c4f…652e3ff` / final `d406ba81…54f90a`，产物在
  `specpilot_data/work/engines/<setting>-{stock,final}`。`env.sh` 已改为优先用派生树，
  缓存按 `TREE_SHA[:16]` 分桶。验收：派生 stock 与上游树逐 token 一致（3/3）。
  坑：换 PYTHONPATH 会让 JIT 缓存失效，首次启动 `draft_decode` 图采集 8.7 s → 222.8 s。
- **P2（已完成）**：`controller/http_transport.py` + `gates/g7_http_transport.py`（5/5）。
  真实引擎的 options 是启动参数，所以配对变成"两个 server 各占一卡"；
  `HttpPairBench` 复用 `controller.stats`，统计不改。单卡顺序路径
  `SequentialPairBench` 直接 raise，**不许**冒充配对。验收含同 arm 确定性、
  噪声地板、`1%+2*noise` 下界判据注入测试。
- **P3（20 请求/2048-cap 的 A1/A2/A3 诊断已完成；下一步真实正确性与噪声/判据）**：链路提交 `ed8b571`，编排修复 `0bb2965`，A1 源 pin=79fe81a、A2/A3=4d67c2f；不是论文完整 dev/sealed 验收。
  `exp/p3_pair.sh <arm> <gpu> <port> <out.jsonl>` = 单臂执行单元（起 server → run_arm → 停）；
  `harness/sglang/gen_final_env.py` 从 config.json 派生 final 的 46 个 `SPECPILOT_*`（不手抄）；
  `gates/g8_pair_arms.py` = 配对前置条件 8 项，其中 **E2 要求三臂 `input_sha256` 逐条相同**。
  本机烟测（1 条/suite、256 tok、单卡顺序）：AR 43.6 / stock 162.9 / final 245.7 tok/s，
  stock/AR **3.74×**（论文 3.95×），τ 5.02→11.13（论文 4.65→13.08）。
  `final/stock` 只有 1.51×；**256-token 短序列摊不开固定开销**是待验证解释，不能排除覆盖层或配置生效问题。
  已经 NorthJob 双卡、每臂 fresh server，`P3_PER_SUITE=4 P3_MAX_NEW=2048`、两轮物理换卡，完成 AR/stock、AR/final 和直接 stock/final；实际结果见顶部与实验记录。
  后续正式 dev 扩围需先登记协议；P4/sealed 仍需 controller 真实判据与正确性/噪声就绪。原 image 与 WeaverDev 已验证，20 请求诊断完成，不得据此宣布正式 dev/sealed 完成。
  详见 `docs/09-p3-harness-validation.md`、`docs/11-reproduction-plan.md` 和 `docs/12-experiment-management.md`；`docs/10-p3-local-pairs.md` 保留执行单元说明，不再要求先跑本机。
- **P4（2 天，可与 P3 并行设计）**：建 `eval/sealed`（controller 侧抽样，agent 不可见）；
  `patches/` 先放 `noop`（必须 token-identical 到 stock）+ `block_8_16`。
  **必须新增门禁**：τ 计数口径一致性 —— final τ=13.08 是 *per exact-weight pass*
  （TLV 下可超 16 token draft block），stock τ=4.65 是 per verify step，**两个 τ 不同源**。
  用 τ 做奖励会把"换计数口径"当成"机制有效"。`run_arm.py` 已落 `tau_source` 字段
  （`per_verify_step` / `ar_no_verify`），final 的 TLV 口径仍是待办的第三个值。
  **lossless 判据**：paper 的 lossless 指"greedy 且每个 token 由 target 判定"，**不是**
  AR 与 stock 逐 token 相同（烟测仅 1/5 相同，第 3 个 token 就分叉，原因是采样路径不同 →
  BF16 GEMM 形状不同 → argmax 在近似并列处翻转）。跨路径的 lossless 只能靠
  **token forcing**（把 stock 的 token 序列喂回去，逐位检查 target argmax）来证明。
- **P5（长期）**：真 RSI。**不要追 W12**（69 KB CUDA kernel，短期做不到）。
  从简单机制族起：block size、tree shape、accept 阈值、attention backend、mem-fraction。

## 8. 仓库现状

`git log`: … e87db70 → 5a46dca → 3d14168(P0) → 76b642d(P1) → 39edfcb(P2) → ed8b571(P3)
（以 `git log --oneline` 为准）

**新门禁**：G6 引擎树可重现 6/6 · G7 传输层 5/5 · G8 配对前置 8/8
**派生树**：stock `e5472c4f…652e3ff` / final `d406ba81…54f90a`
**final env**：`/gpfs/users/jixinpeng/specpilot_data/work/env/h100_c1_qwen38-27b_dflash2-final.env`
（派生，勿手改；`gen_final_env.py --check` 可验）

**已通过验收（mock/TinyLM 规模）**
- `controller/measure.py` 双卡配对 + 互换 GPU + bootstrap CI
- `controller/ledger.py` append-only 哈希链（`ledger/rsi.jsonl` 8 条，chain OK）
- `controller/landlock.py` G3 9/9；`controller/token_force.py` G4 5/5
- `orchestrator/loop.py` G5 6/6；G2 故障续跑 6/6
- 噪声标定 3.11%，晋升阈值 = 1% + 2×噪声 = 7.21%

**已通过验收（真实 27B + DFlash2，本机 2×H100）**
- P0 stock server 跑通；P1 派生树 stock 与上游树逐 token 一致
- P3 三臂各起一次真 server 并跑完同一请求集（`docs/09`）

**空壳 / 未做**
- `eval/sealed` 空（`eval/dev` 已由 `assets/upstream/dev` 供给，5 suite × 20 条）；
  `memory/entries/rsi.json` 是 mock 结果
- `exp/run_e2e.sh` 用 TinyLM，不是真引擎
- **NorthJob 的 20 请求/2048-cap A1/A2/A3 已完成；论文完整 dev/sealed、真实 forcing/噪声/晋升仍未完成**
- `harness/make_traces.py`：自蒸馏语料生成，**WIP，不在主路径上**（DFlash2 已是训练好的 drafter，
  不需要自蒸馏）。保留但不要依赖。
- `harness/qwen_backend.py` / `qwen_spec.py`：自写前向，与 HF 数值一致（max diff 0.0），
  修好了 `is_causal` 在 `S>T` 时左上对齐的坑。**但不作为主引擎**（AR 35 tok/s，launch-bound
  会污染成本结构：让"加大 block"被高估、"省字节"显示零收益）。

## 9. 论文关键数字（用于对齐，不是结论）

`h100_c1_qwen38-27b_dflash2`：stock/AR 3.95×，final/AR 8.86×，
final/stock **2.13× `[2.07, 2.19]`**，τ 4.65 → 13.08。

> 基准取值只看 `assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json` 的 `paper` 段
> （`sealed_final_vs_stock = 2.13x [2.07, 2.19]`）。上游 README 的 2.24× 来自 dev 表格的
> 8.86/3.95，与 sealed 的 2.13× 是不同请求协议，不应简单称为配置冲突。
> **sealed 目标以 config 为准**，dev/AR 对照单独报告，不在口径之间漂移。

成本拆解：ceiling 2.57× = τ 1.83 × overhead 1.01 × kernel 1.39。
单请求 27B：读权重占 23.61 ms 步时的 80%；GEMM 1 行 17.88 ms vs 64 行 18.58 ms（行数几乎免费）。

## 10. 工作方式

- 中文回答，直接不铺垫，单条回复别太长。
- 大输出落盘，`tail`/`grep`/限定行数回读。
- 跨轮状态外置到文件（`ledger/` 测量、`docs/` 决策、`AGENTS.md` 约定）。
- 所有 `exec_command` 需 `sandbox_permissions: require_escalated`。
- 每完成一步就跑一次验收命令。

## 11. NorthJob 提交规矩

提交前必须：① `northjob get --keyword <name>` 查重名；② 显示最终命令 + 资源摘要；
③ **image 显式确认**（`--k8s-images`）；④ 核对 `code == 200` 且 `data.job_uuid` 存在。
总 GPU > 32 且含推断项要二次确认。
