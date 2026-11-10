# 最小 Skills 接入与研究诊断

日期：2026-11-10。用户批准本阶段，仅离线使用既有 H100 stock 证据；不新增 GPU、
不恢复 ceiling 补采、不启动科学角色、不接管 Ascend。不读 sealed 或作者 final。
完整 ceiling 不再作为启动自主研究的硬前置，未知三因子继续保留 null。

## 先行验收与范围

以下是工具接入的工程判据，不新增或放宽 controller 的科学验收规则。
先记录命令再实现；输出落在被 Git 忽略的阶段目录。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_skill_diagnostics -v \
  > logs/skills-diagnostics-20261110-a01/unit-tests.txt 2>&1
$PY -B -m exp.skill_diagnostics --help
# manifest 由维护者冻结授权 stock trace/config 与工具逐文件 SHA，不能由角色自选宿主路径。
$PY -B -m exp.skill_diagnostics \
  --manifest logs/skills-diagnostics-20261110-a01/inputs.json \
  --tools logs/skills-diagnostics-20261110-a01/tools.json \
  --output logs/skills-diagnostics-20261110-a01/analysis-01
```

- 固定 BBuf/AI-Infra-Auto-Driven-SKILLS 的 commit 和最小依赖文件 SHA；不执行安装脚本，
  不加载全仓库提示、PR 知识库或优化答案。第三方源码仅留私有日志，不重新分发。
- 只接受显式冻结的本地 stock trace、模型 config 和证据文件；不接受 URL、shell 或额外参数。
  原始输入不改写，输出目录必须新建；输入或工具 SHA 变化必须拒绝。
- profiler 结果以独立读取的 kernel 个数、持续时间之和及时间区间并集交叉检查。
  累计 kernel 时间不等于墙钟时间；capture-only/eager/tree-probe 不冒充生产请求性能。
  上游 extraction 把 GPU memcpy/memset 包含在 kernel 表中；适配器另外保留其原始口径，
  只过滤明确的 `cat=kernel` 做同口径交叉核对。其 DFlash2 阶段标签未验证，不作为阶段分解。
- pipeline 未核对锚点和层边界时标记不适配，不猜测层标签。
- compute 模拟显式给定实际验证行数、KV 长度、BF16 和 TP/DP/EP；只称估计，
  不将 FLOPs 分摊、MFU、理论 floor 当成实测归因或吞吐提升。
- 测试包含篡改、非法形状、未知工具、缺失锚点与不可信归因的拒绝；保留失败回执。
- 本阶段工具是维护者离线入口，不宣称已验证研究角色的自主调用或新的强制隔离。
  未来只通过既有受限 broker 分发逐方向授权证据及能力，不向角色开放本阶段整个目录。

## 每一阶段的正确性闸门

规则唯一来源为 `docs/02-acceptance.md` 和现有 controller；本表是工作流说明，不改变规则。

| 阶段 | 自检 | 独立验收与去向 |
|---|---|---|
| Direction | option 默认 stock、机制契约、单元/数值检查 | 候选进入开发验收时由 controller 做 T1 token forcing；只有正确性与配对性能均合格才能保留为已验收候选 |
| Integration | 检查依赖、交互、组合默认值及整栈回归 | 每个拟保留的组合重新做 T1 和独立配对性能，不能继承单项的通过结论 |
| Kernel | 算子数值、边界形状、微基准、真实调用路径 | 每个拟保留的整栈变体重新做 T1 和系统级性能；微基准不代替端到端验收 |
| Phase 4 | 最终候选冻结 | controller 加载 sealed，按 T3 做换卡性能和常规/更长输出 forcing；不向研究回传内容调参 |

低成本筛选/调试可早于完整开发验收，但不能先称晋升。现有 dev 联合验收会先采集
待评分的真实输出，再独立 scoring；不是必须重排执行器，也不是只在最后检验正确性。
当前未执行新的候选 T1/T2/T3，不以工具测试替代上述科学验收。

## 后续 GPU 优先级

用户要求后续 GPU 任务使用 `higher-priority-job`。已核对当前 NorthJob 3.3.11：
`northjob create --help` 支持 `--k8s-priority`，本地 `K8sPriorityMaps` 将 **3** 映射到
`higher-priority-job`；不能把类名直接填入整数参数。提交前仍须查重、确认本阶段资源/
镜像、展示完整命令和总 GPU，成功后核对 code 200/UUID 与实际任务 priorityClassName。
不自动设置 no-reclaim；高优先级不是不会被抢占、故障或取消的保证。

## 进度

- [x] 已读交接、计划与验收来源；17 个旧 ceiling 任务均已终态。
- [x] b17 服务端复查为 Aborted；b16/b17 的 JobPreempted 证据保留。
- [x] 旧阶段保守费用 24942 GPU 秒（6.928333 小时），本阶段新增 GPU 为 0。
- [x] 最小工具源码/依赖审查与冻结，工程拒绝测试。
- [x] 既有 stock trace 离线分析及原始事件交叉核对。
- [x] 研究简报与主页/交接更新；归档和公开同步身份在私有 publication 回执单列。

私有证据：`logs/skills-diagnostics-20261110-a01/`。旧树通路的 argmax 分歧和未完成
两轮验收仍是未解决项，不把测量工具当候选交给研究角色，也不称自主发现或 lossless。

## 实际工具验证与限制

固定上游 commit 为 `5df356636bf9da3a1446653043942ff3487c1430`；
`harness/skill_tools.json` 固定 10 个最小源码/数据依赖的 SHA-256，另逐文件核对 Git blob。
上游树未发现明确 LICENSE 文件，本阶段不向本仓库复制分发其源码，只保存外部引用与 hash。
所有脚本在剥离凭据、禁 GPU 的子进程运行，固定入口不接受 live URL 或额外 shell 参数；
Python audit hook 拒绝网络/嵌套进程，但这不是防恶意代码的内核沙箱，不能开放给不可信角色。

| 能力 | 本阶段验证 | 不能宣称 |
|---|---|---|
| Profiler | 既有 b07 stock 完整请求 trace 实际运行；89391 个 kernel 与原记录个数、累计耗时、并集和跨度一致 | 自动定位了全部源码或可靠拆分了 DFlash2 阶段 |
| Pipeline | 合成两层/两次 forward CPU fixture 成功；错误锚点数会拒绝 | 真实模型 64 层已准确标注；实际 trace 缺独立锚点，未运行层归因 |
| Compute | 实际模型 config，B1、8 个验证行、prefix118、BF16、TP/DP/EP1、全行 logits；四个投影/FFN 的 FLOPs 手算相等 | 完整运行成本、GPU 指令计数、实测 MFU 或论文 ceiling |

示例 trace：累计 kernel 工作 **2322.039395 ms**，GPU kernel 并集 **1966.638738 ms**，
首尾跨度 **2143.776001 ms**。三者不同，均不能直接当作正式请求延迟。
上游原始 extraction 为 91887 个 GPU 活动事件，比纯 kernel 多 2496 个 memcpy/memset；
旧 `analysis-01` 因此严格拒绝，保留失败记录；后续显式保留两种口径并交叉核对。
上游阶段输出约 98% 落在 `all`，不具备直接拆开 draft/verify 的能力。
工具给出的 fusion/overlap 建议只能作为待验证假设，不能写成测得的收益或瓶颈因果。

计算模拟给出 target-only 约 **404.782 GFLOPs/8-row forward**，仅是结构估算；
四个投影/FFN 公式检查不等于独立验证了全部 recurrent/attention 成本。
没有提供 measured-ms，因此 MFU 保持 null，不用累计 kernel 时间伪造一个利用率。

验收：18 项新增工程测试与 34 项既有 engine/paper-policy/forcing/dev-campaign 测试共
**52 项通过**，不是全仓库通过。系统 Python3.10 首次因现有代码依赖 tomllib 导入失败，
改用仓库既有 dev Python3.12 后通过，未修改无关依赖。合成 pipeline 首次 5 个锚点不整除
被拒绝；另建正确 4 锚点 fixture 后通过，没有放宽上游检查。两类旧失败全部保留。

## 给 Master 的研究简报

### 可使用的证据

1. 历史 b07 的 10 请求 graph-provenance 报告中，target graph 累计 kernel 工作约 **90.14%**，
   draft 约 **8.31%**、bookkeeping 约 **1.21%**、prefill 约 **0.35%**。
   这是复用旧审计报告的工作量分组，不是本阶段新做的全部审计，也不是互斥墙钟占比；
   本阶段只独立核对了一份原始请求 trace。不能据此宣称 VERIFY 之外的开销均可忽略。
2. 历史原缓存独立 FP32 参考重放覆盖 10 个独立请求、两轮共 5290 有效步；
   stock 条件接受量约 **4.8604**，N32 best-first 条件接受量区间 **[5.9312, 6.0301]**。
   这是参考分叉模型边界，不是速度 CI，不是已通过正确性验收的树候选。
3. 当前配置为 64 层：48 个 linear-attention 与 16 个 full-attention；请求 B1 不等于
   verify 只算一行。模拟使用实际 8 行，不能用接受长度代替实际计算行数。

### Master 可以据此提出的问题

- 大头的 target 路径是否存在重复计算、访存或低效 kernel，值得何种最小实验证伪？
- 增加接受量的方向，能否在计入草稿/验证/提交成本后获得真实净收益？
- draft 或调度的小开销方向是否投入更低、能与其他补丁互补，而不是重复优化同一项？

以上不是预分配的研究方向，更不是要求正结果。Master 自主选题/分预算，direction 自主
选择分析工具和实验并修复；Integration 研究组合，Kernel 处理有价值的底层热点。
controller 对单项、组合和 kernel 后的拟保留候选分别执行独立 dev 正确性/forcing 与
配对性能；最后冻结后才用 sealed。没有验收的树测量实现不作为可用候选或独立发现。

### 明确保留的未知项

- 最佳节点预算与正文/附录两种 ceiling 的确切计算口径；formal 三因子和 ceiling 为 null。
- 新树测量通路多题分支 argmax 分歧及未完成的两轮协议；不能由本阶段工具通过消除。
- 真实层锚点、全部 kernel 调用点和工具建议的因果解释；需要后续按方向验证。
- 研究角色实际自主调用这些 Skills、源码 overlay 能力、Integration/Kernel 的真实闭环
  仍未验证。下一阶段先提案，不用维护者的离线分析冒充这些成果。

## 复算与证据

成功运行目录为 `analysis-03/`、`analysis-04/`；二者的 kernel 统计、计算模拟、
上游/本地源码身份和未验证项需一致，输入原 SHA 不变。输出中的本地路径可不同。
`independent-checks.json` 记录与旧 trace 回执和四个 GEMM/FFN 公式的独立核对；
`historical-evidence-summary.json` 记录旧报告身份，`source-review.json` 记录上游 blob。
最终 manifest 与发布回执另建，不覆盖旧 ceiling 归档或 resource-state。
