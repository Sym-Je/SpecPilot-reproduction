# BBuf 角色工具、controller 复核与真实闭环

用户批准三部分整体执行，并确认新资源上限：32 H100 GPU小时、24小时、最多并发4卡；
失败/排队/冷启动保守计入，不结转旧余额。沿用已验证 image digest、WeaverDev、qiji、
既有 toleration/只读模型挂载，显式 `--k8s-priority 3`。每次提交仍查重、展示命令、
只 create 一次并核对 code200/UUID/实际 priorityClassName。

用户另行授权主助手作为维护者补齐必要 controller/eval 接口，不放宽科学规则。
研究角色仍不得读 sealed、改裁判/规则/账本或直接提交 GPU。Ascend 轨道完全独立。

## 执行次序与先行验收

1. 必要执行通路：复验旧 source 边界/冻结/default-off/CPU回执绑定测试；新唯一预算下最多
   先做一次真实 stock 预检，有基础设施错误才有证据地修复，不持续代做科学研究。
2. BBuf 工具：固定外部版本与文件SHA，研究只获得角色对应工具卡与自身授权证据。
   profiler/pipeline/compute/capacity/triage 按需调用；PR知识/作者优化不默认开放。
   不为“每阶段都用”而强迫重复分析，无可用证据必须明确拒绝或返回未知。
3. Controller：先跑已有 forcing/paper-policy/dev-campaign 回归，再补健康/错误注入、实际
   输出绑定、缺失轮次/换卡/哈希拒绝；科学阈值沿用 `docs/02-acceptance.md`。
4. 真实阶段：Master 自主至少分两方向；direction 自己设计/实现/实验/修复；Integration
   研究组合；Kernel 根据实际热点选择实现或有依据停止。拟保留的每个单项/组合/kernel
   变体分别交独立dev正确性与配对性能，不能继承上一阶段通过或强行产生正结果。
5. Phase4：候选冻结后仅controller管理/加载未参与研究的请求，常规及4096上限forcing、
   两轮fresh server和换卡；验收后才可能写可信记忆/账本。无合格候选不得伪造晋升。
6. 收尾：重算、故障拒绝、任务/角色终态、预算/归档、主页/交接、公开审查与正常同步。

工程与科学验收分开。先登记的工程命令：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_source_candidate harness.test_source_boundary \
  harness.test_source_research harness.test_skill_diagnostics -v
$PY -B -m unittest harness.test_p5_paper_policy harness.test_p5_scored_forcing \
  harness.test_p6_dev_campaign harness.test_engine_research -v
# 新增工具broker/流程/验证侧测试随实现登记为独立test_skill_rsi模块。
$PY -B -m unittest harness.test_skill_rsi -v
```

所有大输出留在 `logs/skills-rsi-20261110-b01/`；唯一预算为该目录的 resource-state.json。
现有未提交 ceiling/source 来源先冻结，不静默混成自己的独立发现；本阶段复用旧通路
须明确标注并在正式发布前复验。主助手仅维护通用机制，不写科学优化补丁。

## 完成定义

- 工具接入：实际角色经可信broker自主调用，原生动作/工具版本/输入输出SHA可审计；
  不能以提示词列表或维护者代跑冒充完成。
- 裁判复核：健康fixture能通过、已知错误被拒、证据替换/缺轮等失效；fixture不冒充真实GPU检验。
- 全流程：分别报告每个实际执行阶段、跳过原因、真实GPU/独立验收/sealed结果与下一轮
  接续能力。未运行的阶段不能写已完成；无收益允许，但不等于全部方法结论得到验证。

## 研究启动时检查点（历史）

五次source预检全部终态，共3196 GPU秒。第五次Completed/exit0，真实stock两轮fresh
与换卡、5题/10pair/20臂输出一致；比值0.9998275 [0.9989243,1.0007659]仅为预检诊断。
修复ldconfig helper、固定两臂关闭自动NUMA、同目录Triton缓存及Ninja自建进程组，
属于通用设施，不算科学优化。最新105项联合回归及14项并行工具/计数检查通过。

Master已通过受限原生入口自主调用BBuf并分配三个互补方向；最多两方向同时研究，
各自经可信broker申请两卡任务，唯一预算限制总并发4卡。科学候选、独立dev及sealed
尚待实际执行；pipeline层锚点仍缺，返回unavailable，不能把外部估算当实测阶段归因。

## 原生研究结果与当前控制验证

Master自行分配三个方向，各方向独立读取stock、编写CPU验收与option、请求真实GPU诊断，
未由维护者代写科学补丁。每次诊断为5个公开dev请求、256上限、两轮fresh server与换卡。

| 方向 | 机制 | candidate/stock tok/s | 95%请求cluster区间 |
|---|---|---:|---|
| d1 | BF16输出头M8补零到M16 | 0.999116 | [0.996860, 1.001485] |
| d2 | gated norm省去未使用统计量存储 | 1.003641 | [0.999300, 1.008194] |
| d3 | draft argmax直接写输出缓冲 | 0.994493 | [0.991033, 0.997896] |

三者均未获可信收益；小样本短输出诊断不能说明全部形状/长输出下无效，也不等于正确性验收。
Master选择stop且未请求dev gate；Integration无合格共享补丁，Kernel认为形状/阶段归因证据不足，
均诚实停止。实际原生角色已执行不等于真实补丁整合或kernel优化已经完成。

科学轮独立谱系重算：6角色、13回合、53工具动作、4Python执行与4次BBuf调用、3GPU诊断、
30pair。Master与Kernel实际消费诊断工具；Integration无输入不强制空跑工具。
capacity另在原生工程探针实跑，triage按故障需要提供；pipeline仍缺经核对的层锚点。
这些能力和外部先验不替代controller，不当作新的自主优化发现。

首次额外coverage审核遇到12k输入截断与不明确工具schema，原始失败保留。
补齐通用help与分页后，一次显式repair从真实工具回执核全68044字符/6页，
Master自主仍stop；累计15回合/69动作/10CPU工具收费（含2个被拒CPU请求），不重置预算。

为了验证裁判执行而非硬凑科研成果，维护者单独运行canonical stock/stock负对照：
5类未用于研究的新请求各1条，2048/4096两cap，各含null-pre/candidate/null-post、两轮换卡。
此规模只检验协议与拒绝路径，不是论文100题sealed数字复现；控制模式永不授予T3/晋升。
原100dev、既有200题/160题/合成请求及本阶段请求按冻结引用排除，正文只由controller root加载。

control01在READY握手前失败144 GPU秒；umask077令非敏感bootstrap/探针不可读，
修复仅显式设置只读代码/探针权限，controller私有目录/文件仍0700/0600。
同时修正选题排序不依赖job目录；生成前设施失败不构成按性能换题。
严格prefix审计保留原科学8任务与controller扩展，控制任务不能写成研究成功。
control02已终态Aborted/exit1，11792 GPU秒；12轮物理计时已执行，FP32 head预检已通过，
但5条私有请求的AR输出均在2048之前自然结束，故障回归缺少注入覆盖而被拒。
这不是正确性通过，也不能通过重抽私有题或忽略EOS掩盖。累计10任务21170 GPU秒，均终态。

### 控制验证修复计划（同一授权阶段）

先把裁判自身的健康/等价归约/2048之后故障回归放到预登记的固定公开dev探针上；
私有计时输出仍逐轮做匹配stock/AR校准及自身上下文token forcing，不用dev校准替代。
故障必须被event rule拒绝、长尾覆盖不少于1024 token，既有科学阈值不改。
不恢复科学角色，不把维护者修复算独立发现。

先行验收：新增CPU fixture覆盖私有请求全部早停仍需完成独立故障回归、探针来源绑定、
拒绝替换/缺失证据，并运行原phase4/controller联合回归。命令：

```bash
/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python -B -m unittest \
  harness.test_phase4_run harness.test_phase4_resource harness.test_sealed_protocol \
  harness.test_controller_reference harness.test_controller_capabilities -v
```

旧执行源码已锁入旧freeze；为避免把新评分代码混入旧执行身份，不改旧freeze或覆盖旧产物，
新任务全量重跑同一预登记seed/pool的stock负对照。旧失败及有效计时证据保持原样。
仍使用唯一32 GPU小时预算，提交前重做停机证明、查重和完整资源核对。

修复后306项指定模块联合回归通过，含28项公开/私有隔离与摘要拒绝定向检查。
control03查重后只提交一次，code200，UUID `job-b8b4bbffbc29-20261111035140`，
2H100、14400秒deadline；source archive SHA为
`197bd0f0880479ced6e605b0074fb8add6eefa6bd768f1369a95429fe5393928`。
已提交不等于进程启动、GPU验收或forcing通过；当前以前台monitor及公共结果为准。

先前公开检查点的20个指定模块297项CPU联合回归通过；选择性暂存树导出到独立/tmp后亦297项通过，
不包含未提交ceiling扩展。首次导出只有旧测试写死本机祖先目录导致失败，
测试改为实际ROOT及parent，不改权限策略；原失败及修复后回执均保留。
此结果不宣称全仓库或其他机器全绿。该历史检查点发布时control02仍运行；最新终态与control03见上文。
normal post-terminal T3 finalizer仍为未验收原型，本轮不调用，不写ledger或memory。

## 本轮最终结果（2026-11-10 UTC）

control03已Completed/exit0、零重启，GPU任务实际运行19:52:00–21:51:59 UTC。
健康stock、AR、分段健康与等价FP32归约回归通过；故障被event rule拒绝，
2048之后实际故障尾部累计8272 token，达到原≥1024覆盖条件。
私有实际计时输出在2048/4096两个上限、各两轮换卡下独立校准/forcing通过。
上限不代表实际输出都达到2048/4096，EOS行为没有改变。

| 检查 | 结果 | 解释 |
|---|---|---|
| 裁判健康/故障回归 | 通过 | 固定公开探针，不用私有题挑选故障样本 |
| 私有计时输出正确性 | 通过 | 逐cap/轮次匹配canonical stock、AR与自身输出上下文 |
| stock/stock性能门 | 拒绝，符合预期 | 没有真实优化，不能因波动晋升 |
| 独立重算 | job内独立controller进程完成 | 原包重算一致，2231文件封存；host核公共SHA及终态 |
| 正常候选T3/账本/记忆 | 未执行 | 控制模式始终不授予晋升 |

stock/stock输出速率比：2048上限为1.004738，噪声0.003814，对应提升阈值1.7628%；
4096上限为0.991757，噪声0.002214，阈值1.4428%。均未过性能门。
**每suite只有1条请求，分层request-cluster bootstrap在本样本退化为点值；
不得把该区间当成有统计功效的置信区间，或用作论文数字复现。**
本次仅验证小规模执行/正确性/拒绝链路，不证明正式样本规模或最终收益。

source archive为上文`197bd0…`，私有证据seal SHA为
`969df1db95a21fa568b8f36595ae61d7f56cd3008687d3f0dfe35e138a48c4f6`，
私有独立replay SHA为`4ad0021f4f4d4049658a6ea5900d7e467064186a9985afe10c88e93bcb11e651`。
主助手未读取私有正文/日志；host不宣称自己遍历了root私有封存文件。

本轮11个GPU任务全部终态，累计35608 GPU秒，即9.891111 H100 GPU小时，
峰值预留4卡，未超过32 GPU小时／24小时／4卡授权。control03单任务14438 GPU秒，
失败与冷启动均计入；没有活动GPU任务，不自动结转余额或重复提交。

公开导出先发现两个CPU fixture依赖真实`.git`，仅mock测试pin、未改生产身份规则；
独立`/tmp`公开源码副本最终316项指定回归全部通过。未声明全仓库或其他平台全绿。

### 对三个目标的如实验收

1. **BBuf：角色工具接入已验证，但非所有能力适配完成。** 原科学轮真实调用4次，
   分布为Master 2、direction 1、Kernel 1；capacity另有原生工程探针。
   Integration没有合格输入，不强制空跑；pipeline缺可信层锚点，仍不可用于真实层归因。
2. **Controller：健康、故障、真实私有输出及stock负对照拒绝链路已验证。**
   这不等于正常候选的post-terminal T3授权/晋升路径已经跑通。
3. **研究流程：完成一轮真实多角色探索和有依据停止，没有找到合格final。**
   Integration/Kernel角色运行过，但真实多补丁组合、kernel优化、正常final T3、
   可信记忆和多轮RSI仍未完成，不能写成整篇论文闭环或2.13×数字已复现。

下次大步骤应另行提案：优先补可信的按需stock profile/实际形状证据，使Master和Kernel
能自主判断下一轮；不由维护者代写优化，不重开本轮私有题给研究角色调参。

收尾审计：原科学prefix及三个controller扩展独立重算一致；前两次失败保持原样。
9326个host可见产物完成两次全SHA回读一致，root私有目录不遍历、仅引用job内seal；
发布/收尾元数据与凭据路径显式排除。原始产物留在GPFS，不进公开Git。
44个旧ceiling文件仍与接手时SHA一致；三份共享进度文档仅发布本阶段hunks。
公开副本的6个本阶段Python文件与316项通过时逐SHA一致，文档后续收口不伪造新的测试。
最终提交及GitHub同步身份以私有`publication`回执为准。
