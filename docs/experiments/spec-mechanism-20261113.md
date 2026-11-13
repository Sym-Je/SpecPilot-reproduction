# 投机机制与验证预算真实研究

## 用户目标与授权

本阶段研究如何联合草稿范围D、验证节点预算N和候选组织/选择，让实际提交进度覆盖新增成本。
用户批准Master自主设计、Direction自主实现/实验/修复；主助手维护通用执行和证据，不代写科学patch，不预定best-first、增大长度或正收益。
新资源上限8 H100 GPU小时/8小时/并发2卡，失败/排队/冷启动计入，不结转旧额度；镜像digest、WeaverDev、qiji、既有只读模型PVC/toleration和priority3均已确认。
具体授权与原始回执位于`logs/spec-mechanism-20261113-a01/authorization.json`；此文不授权sealed或改变controller规则。

## 执行设计

1. 维护者先固定ACCEPTANCE.md，保存旧工作/保护文件，核对CLI/凭据结构/执行器与角色边界。
2. 原生Master按需读授权stock、已有接受量/replay及公开资料，比较至少两个机制并给明确首版/对照/停止条件；历史结果与公开先验标记复用。
3. Direction只收到自足简报和授权stock/证据，用既有受限入口自主写验收、source-option-v2和CPU自检，绑定当前文件SHA后申请真实运行。
4. 可信broker执行同请求双卡、两轮fresh换卡；参数/路径生效、位置/mask/Conv-GDN-KV状态、提交进度和完整成本均需证据。
5. 实际反馈交回同一原生Master决定继续/修复/独立dev/停止，不由主助手决定科学参数；有候选才用既有source-controller验收，不碰sealed。
6. 结束核对任务/角色/进程终态、实际预算、原始产物及版本，公开只同步阶段摘要，不提交原始stock/trace/凭据。

初始原生Master只交机制检查点，不代表整个研究完成。现有启动宽度接口4/8/12/16是工具范围，不是模型上限；需要额外能力应明确证据/最小适配，不能直接宣告算法无效。
研究诊断不是正式晋升；CPU/replay通过不证明真实执行、lossless或提速。工程失败、工具限制、实现错误和科学反证分别记录。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native harness.test_source_candidate harness.test_role_turn
$PY -B -m unittest harness.test_source_research harness.test_open_research harness.test_engine_research
$PY -B logs/spec-mechanism-20261113-a01/test_campaign.py
```

阶段驱动`logs/spec-mechanism-20261113-a01/campaign.py`仅编排既有受限Direction/预算/测量；原生Master通过management请求/响应参与决策，不退回旧受限Master。
运行前核对campaign-started不存在；长任务TTY前台，不用后台shell；来源以实际运行源快照/每任务source-identity为准，不拿HEAD代替dirty执行代码。

## 已执行与自主分工

原62份dirty保留，397份同研究谱系材料复制并绑定来源；最终17项入口、39项执行器、9项阶段协议回归通过，共65项指定检查，不代表全仓全绿。
首轮维护者验收误列不存在的test_runtime_feedback，失败回执保留；已改为现有engine_research回归，不改变科研或裁判判据。
Master已交付spine-fork12-v1：固定原D7/draft8主链，在target物理容量12中加入至多4个侧链节点，按当前草稿概率代理选择分叉；不是简单改成长链或预定全局best-first。
5290个历史有效步的条件进度从4.860407到5.352015（约1.101145倍），逐步回放独立重放一致、19来源SHA通过；这是条件筛选，不是在线收益、lossless或全局上限。
维护者初次独立副本漏复制checks.md，失败保留；复制完整科研副本后复验通过，原研究文件未改。
维护者两次启动参数错误（角色大小写/超时超界）均零科学回合/零GPU，修复后保留原目录和退出记录。
真正Direction已自主写11-edit补丁/自检/源码缓存，首次CPU反例见证错误自行修复；累计128动作/5CPU后触及32模型步数入口上限，尚未请求GPU。
Master复核实际代码/CPU与中断，决定继续；own_replay核验恢复三个自身原生写入文件，不共享其他方向，不算新独立发现。
接续窗口为新增96动作/12CPU/3GPU并替代旧未用额度，累计224动作/17CPU/3GPU；后Master另批32动作/4CPU/0新GPU，最终实际255动作/18CPU/3候选GPU。原8小时/8GPU小时/2卡起点、权限和单轮限制不改。
原生Master恢复同一线程管理；Direction始终由受限入口自主写科学补丁、自检、实验请求和修复。主助手只处理通用编排、提交准入、证据复核与发布，没有接管科学实现。

## 真实任务与资源

| 任务 | UUID | 终态与实际结果 | 保守GPU秒 |
|---|---|---|---:|
| stock/stock预检 | job-064c97d9fe14-20261113114502 | Completed，双卡两轮预检通过，不是候选收益 | 2172 |
| 候选01 | job-1d66ad00e75c-20261113120857 | Aborted，prefill graph CUDA OOM，无完整pair | 972 |
| 候选02 | job-6052f986caaa-20261113133922 | Aborted，真实侧链已执行，输出额度耗尽的在途轮次断言 | 1334 |
| 候选03 | job-e6560c9571e0-20261113135448 | Completed/exit0，两轮fresh换卡、5请求、10pair、cap256 | 2388 |

四次各查重、展示完整命令、只create一次，分别核对code200/UUID、启动和终态；合计**6866 GPU秒，约1.907 GPU小时，0活动GPU**。失败/冷启动/排队保守计入，原上限未提高，剩额不自动结转。
镜像、两H100和只读模型挂载已核对；CLI请求WeaverDev/qiji，实际namespace为qiji、queue为proj-31。实际job级priorityClassName为higher-priority-job，task模板和pod字段为null；不宣称优先级保证免抢占。
Master明确改用分阶段实际结算，取消同时保留未来controller最坏额度的硬要求；这不是扩大预算或保证能进行正式验收。

## 实现失败与修复

1. 候选01将target状态分配扩到12，但Mamba容量估算仍按draft8，出现显存压力与图捕获OOM。Direction自主修正三个估算分支、补自检；不声称这一不一致是唯一原因。
2. 修复过程中新增自检出现IndentationError，Direction改为核对完整冻结源码并自行修复，当前SHA绑定CPU回执通过；原失败保留，不删除断言或改验收。
3. 候选02成功启动并自然执行侧链，但overlap在输出额度耗尽后仍有在途轮次，触发cap断言。Direction增加前置门控，让此类轮次走canonical stock处理，正额度仍走树。
4. 候选03完成后，Direction后处理打印超65536字节导致exit120；这是审计脚本错误，不是候选GPU任务失败。Master与维护者限量读取原记录复核，保留原失败。

最终patch SHA：`598a4c0024d61564eff3735211d5ac97cf99851d9e09d5fc79f0bbc6e3694b8f`；self-check SHA：`a2a41e93376971af4a35e18220fb4fe9bb2f5cd855f0bbbc4aaeb1c7cd3a761d`。
每任务source-identity/source.tar冻结了实际运行的维护者代码（包括原有dirty），不能用基准HEAD39017ae冒充全部执行源码身份。原始补丁/stock/trace仅私有归档，不随本次摘要公开。

## 诊断结果与解释边界

候选03为**256-token公开dev研究诊断，不是正式2048或controller晋升**。每suite1条，共5个独立请求，每请求两轮fresh换卡；10pair不是10个独立样本。
输入SHA逐pair一致；按请求聚合换卡log吞吐比，再几何平均。95%CI使用既有controller.stats的10000次请求簇bootstrap，seed0、非suite分层；物理轮次留在同一请求簇。
维护者从两份原始JSONL复算全部中心值/区间/各suite结果逐值一致，并核对物理GPU互换。

| suite | candidate/stock吞吐比 | 输出比较 |
|---|---:|---|
| gsm8k | 0.403530 | 两轮首分歧索引3 |
| math500 | 0.396307 | 两轮首分歧索引160 |
| humaneval | 0.446843 | 两轮首分歧索引109 |
| mbpp | 0.386693 | 两轮256 token完全相同 |
| mt-bench | 0.368959 | 两轮256 token完全相同 |
| 整体 | **0.399651 [0.379664, 0.425345]** | 不作lossless或晋升结论 |

实际D7/draft8/K16/target容量12、eager、父槽、terminal和KV压紧均有执行见证，正式请求也有自然侧链接受；只证明该路径执行，不认证Conv/GDN/KV数值状态正确。
候选日志的committed255是decode部分，HTTP256另含prefill seed，不能误判丢token；排除warm/full-warm后才计正式请求。
三个请求6个pair输出分歧，尚无相同前缀forcing/target margin/数值状态差分，不能区分near-tie与状态、mask或提交错误。SHA不同不直接等于正式lossless失败，两个短输出相同也不能认证全路径。
不同轨迹中的verify减少/侧链接受不能解释为因果收益。相同输出的mbpp报告verify60→57而仍慢，mt-bench51→51亦慢，支持停止**当前实现**。
普通HTTP包含实际执行/通信/调度/prefill成本，冷启动另计资源；尚无足够因果对照把回退归因于eager、Python/D2H、状态处理或日志中的某一项。不把条件回放约10%进度空间当在线加速，不外推cap2048。

## Master决定与未完成项

Master复核Direction的finish及两轮原始证据，**自主stop当前eager实现，不追加实验、不请求controller**。不是预算耗尽，不是所有单叉机制无效，也不是完整RSI完成。
科学结论见私有目录`native-master/research/management-scientific-conclusion-02.md/json`，管理响应逐字转交并保留来源。
本轮已完成机制设计→自主实现/失败修复→真实配对诊断→Master复核停止；**优化目标未达**。lossless、2048完整成本、晋升、integration/kernel和sealed均未完成。
以后若重新立项，最小缺口为首分歧同前缀target margin及serial/root-only/branch状态差分，再决定是否值得性能投入；此建议不自动授权任何GPU或下一主线。

## 工程收尾与公开范围

研究驱动正常exit0、Direction进程关闭、原生Master关闭、四任务均终态。保护文件及原62份工作、23份Master冻结检查点核对未变；事后摘要不能证明从未读取禁区。
stage_audit.py --final与diagnostic_review.py保存工程/统计复核，原始失败、预算、命令、代码身份和生命周期保留在同一目录。
持久私有归档位置及SHA见archive-receipt.json；公开只同步README/HANDOFF/PLANS本轮新增块和此摘要，不混入旧改动、原始运行产物、sealed或凭据。阶段提交/远端身份以publication.json为准。
