# 00 — 论文骨架与系统架构

> 依据：*SpecPilot*（arXiv:2611.02501v1），正文 §1–§8 + 附录 A–F，共 23 页。

## 1. 这篇论文的结构特征

它不是"提出一个算法"，而是**提出一个发现算法的循环，再用循环发现的算法证明循环有效**。

方法层（§3）与产物层（§4）互相支撑，缺一则论证崩塌：

- 只有 §3（循环）而无 §4（机制），是架构论文，没有证据说明它能产出真东西。
- 只有 §4（机制）而无 §3，是四个互不相关的系统优化，无法解释为什么它们恰好都对准了瓶颈。

复现时必须同时复现两层。只实现 W12 + 树 + TLV 而用人工方式决定做哪个，等于删掉了论文
的主语。

### 章节职能

| 部分 | 职能 | 论证作用 |
|---|---|---|
| §1 + Fig 2 | 三个瓶颈：单请求权重流主导、批处理验证开销翻倍、优化依赖部署 | 建立"必须逐部署优化"的必要性 |
| §2 | 投机解码、DFlash2/DSpark 格、GDN 混合目标 | 定义 lossless 的严格含义，为"为什么难验收"铺垫 |
| §3 | 成本模型、五阶段循环、token forcing、结构化记忆 | 方法层 |
| §4 | W12、混合目标 best-first 树、TLV、批处理三件套 | 产物层：每个都对准 §3.1 量出的某个 gap |
| §5 | 4 目标 × 3 drafter × 2 GPU × 5 benchmark | 广度 |
| §6 | 三轮瓶颈迁移、故障注入、W12 外溢、replay、regime 依赖 | 机制解释；也是"这不是调参"的证据 |
| 附录 A–F | 逐档增益、15 次晋升链、成本表、W12 细节、被关闭方向 | 可审计性 |

### 复现时最该先读的两页

- **§6.1 单 agent 对照**：1.34× vs 2.13×。没有这个对照，"成本模型有用"只是断言。
- **附录 F 被关闭方向表**：告诉搜索空间里哪些洞是死的，能省掉大量无效探索。

## 2. 五层架构

```
L4  Structured Memory   140 entries: code delta + requires + registry + evidence card
        ^ 蒸馏（sealed final 之后）      | 播种（新一轮 / 新部署）
L3  Agents              master(规划) / direction x N / integration / kernel，一方向一卡
        ^ 只读数字                      | 只能提交 patch（默认复现 stock）
L2  Controller          配对计时、晋升规则、token forcing、sealed final、账本（agent 不可改）
        ^                               |
L1  Cost Model          S(N)=tau(N)/c(N); ceiling = tau_best/tau * Tprof/Tfloor * Tstep/Tprof
L0  Harness             SGLang 冻结构建、请求生成、交错跑、profiler、exact replay
```

## 3. 一轮的时序（对应论文 Fig 3 的 0–4）

1. **Phase 0 成本模型**：只用已有 replay 记录和 profile 算三个因子，报出最大因子。
   返回的是"哪里漏速"，不是"该做什么"。
2. **Phase 1 探索**：master 按最大因子开出若干方向，一方向一卡。子 agent 先用最便宜的
   证据（replay / microbench / 单卡计时）验证 headroom，净收益 >= 3% 才动手。
3. **Phase 2 集成**：单独不够格但合起来够格的 patch 叠成一个栈，整栈接受同一条晋升规则。
4. **Phase 3 kernel 调优**：对离 byte floor 最远的 kernel 下手。
5. **Phase 4 sealed final**：在**未见过的请求**上对 stock 计时 + 对最长 4096 token 的输出
   重跑 token forcing。任一不过则整轮作废。

第 k 轮起点是第 k-1 轮的 final；新部署起点是 stock + 记忆条目。这个递归是跨部署泛化的
**全部**机制，没有别的。

## 4. 关键设计一：ceiling 分解

```
S(N) = tau(N) / c(N),     c(N) = Tstep(N) / T_AR

ceiling = (tau_best / tau) * (T_prof / T_floor) * (T_step / T_prof)
              ^ tau 因子        ^ kernel 因子        ^ overhead 因子
```

`T_floor` = max(FLOP 时间 @ 60% 峰值 dense 吞吐, 字节时间 @ 90% 峰值带宽)。

这是全文的核心抽象：**它把"优化"变成了"排序"**。

论文实测的因子迁移（§6.1）：

| 轮次 | 主导因子 | 采取的动作 | 结果 |
|---|---|---|---|
| 起点 | tau=1.83, overhead=1.01, kernel=1.39 | 做树 | 184 → 270 tok/s |
| 第 2 轮 | tau=1.34, step-cost=1.45 | 做 W12（字节） | → 约 350 |
| 第 3 轮 | 两者饱和 | 改 ceiling 的**假设**（一次 pass 一份 draft → TLV） | → 416 |

第三轮那一步是架构上最漂亮的：剩下的增益不在被优化的对象里，而在目标函数的假设里。
复现时如果任何一轮出现"两个因子都接近 1"，正确反应是**质疑 ceiling 的假设**，而不是
继续调 kernel。

### ceiling 不是上界

RTX PRO 6000 上实测 2.44× 超过其 2.12× 的 ceiling，论文自认原因是 ceiling 假设"一次
pass 一份 draft"。所以：

- **不要**把 ceiling 当硬指标去对齐。
- **要**用它当排序工具：只要它给出的最大因子方向与实测 profile 的迁移一致，成本模型就
  基本正确。
- 反过来，若 ceiling 反复指向一个做了却不涨的方向，那是**成本模型错了**，不是 agent 错了。

## 5. 关键设计二：晋升规则是统计门

- 基准：95% 置信下界 > 1% + 2 x (stock vs stock 噪声)；单请求 H100 上噪声 < 0.1%
- 若输出与当前最优有分歧，门槛抬到 ~3%
- 测量：双卡同请求配对、互换 GPU、两轮

这条规则的实质是：**把"是否采纳"从 agent 的判断里拿走**。它同时防住了两类错误——
把噪声当增益（假阳），以及把真实但微小的增益丢掉（因为门槛有明确的统计含义）。

## 6. 关键设计三：token forcing

它检验的是"对 stock 的统计同一性"，不是"正确性"。

流程：
1. teacher-forced scorer：把被测系统输出喂回 **stock 引擎 + FP32 LM head**，取 argmax
2. mismatch = 与被测 token 不同；margin = 到 argmax 的 logprob 差
3. delta = stock 首次偏离 AR 时的最大 margin，向上取整到 1/8 的倍数
4. 两条规则：
   - **rate rule**：mismatch 率超 stock 0.5pt（95% CI）即拒
   - **event rule**：margin > 2*delta 的事件在二项检验下显著多于 stock 即拒

参考值：stock 自身 mismatch 0.72%（27B）/ 0.53%（4B），几乎全是 kernel 舍入的 near-tie。

### 为什么必须这样

§2.1 说明 lossless 只保证到"浮点归约顺序"层面，stock 自己就偏离 AR（首次分歧 logprob
差 <= 0.232 nats）。因此：

- "输出与 stock 逐字相同" → 误杀合法系统
- "任务精度不掉" → 放过故障系统（Fig 2c：四个区间全部包含 0）

Fig 2c 是全篇最强的动机图，也是复现时最容易做错的一环：若你的评测器只测任务精度，
它**不可能**发现故障。

## 7. 关键设计四：记忆的不变式

条目只有一条硬性约束：

> 把它的 code delta 连同 requires 应用到 stock，必须**字节级复现**出源系统的代码。

- 复用条目要重新调优、重新计时，且**不算新发现**
- 规模：140 条，最多 12 个前置依赖，15 条 sm120 专属

这条不变式是"记忆"与"缓存"的分界线：它保证条目是可移植的**机制**，而不是某个系统的
快照。

## 8. 四个机制与它们对准的 gap

| 机制 | 对准的因子 | 一句话原理 | 为什么无损 |
|---|---|---|---|
| W12（§4.1） | kernel / 字节 | 每权重 12 bit：符号 + 3 位高尾数 + 4 位 binade 偏移 + 4 位低尾数；越窗者进 escape list；GEMM 在寄存器里解码 | 逐位等于 checkpoint，加载时校验 |
| best-first 树（§4.2） | tau | 按 parent-conditioned logprob 选 N 节点；混合目标沿根路径重算 GDN 状态（WY kernel） | 只改归约顺序，精确 pass 仍是精确权重 |
| TLV（§4.3） | 改 ceiling 假设 | 先用 W12 内嵌 8-bit 视图做 Q pass 出链 C，再从 C 尾续 draft，一次精确 pass 验 32 节点 | 只有精确 pass 接受 token |
| 批处理三件套（§4.4） | 批处理 step cost | 共享节点预算、按请求调 drafter block、prompt admission | 只挑选要 draft/verify 的行 |

注意 W12 的加速**主要来自 kernel 而非格式**：stream-K、5 级 SMEM ring、wgmma RS 操作数、
fixed-order split reduce。只实现格式只有内存收益（权重 -14~-22%），不会有 1.17–1.47× 的
GEMM 加速。这是复现时最容易被低估的一点。
