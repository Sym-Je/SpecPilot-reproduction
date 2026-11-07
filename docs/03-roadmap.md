# 03 — 复现路线与前置门槛

## 1. 主线与取舍

论文全量：13 轮、164 小时、530 GPU-小时、486 次代码变更、54 次晋升。全量复现不现实。

**锁定一条主线作为验收对象：**

> 单请求 × Qwen3.8-27B × DFlash2 × H100，三轮，184 -> 416 tok/s（2.13x over stock）

选它的理由：唯一一条能把 §3 每个机制都走一遍的路径——
tau 因子（树）、kernel 因子（W12）、改 ceiling 假设（TLV）。

其余部署（DSpark / PRO 6000 / Muse-Glimmer / 批处理）作为**记忆迁移验证**，不重新发现。
这正是 §5.3 的用意：验证记忆，而非重跑搜索。

## 2. 前置门槛（按风险降序）

### 2.1 权重与 drafter 可得性 — 最高风险

需要：Qwen3.8-27B、Muse-Glimmer-30B、Gemma-4-12B、Qwen3.5-4B、DFlash2、DSpark 的
checkpoint。这是首要卡点。

**若拿不到，正确的做法是换同期同规模模型，并在 `docs/` 明确记录"复现的是架构而非数字"，
验收标准相应改写。** 不要在未声明的情况下用替代模型跑出数字再与论文比较。

### 2.2 stock 调优基线

见 `02-acceptance.md` §3。必须一次性锁定。

### 2.3 噪声地板 < 0.1%

需要双卡配对 + 互换。本机 2xH100 满足，这是硬性前提，不能降级为单卡串行。

### 2.4 W12 的真正难点是 kernel

格式本身（16-binade 窗口 + escape list）几天可写对。难点在：

- `~105 指令/阶段`、5 级 SMEM ring
- wgmma RS 操作数（A 从寄存器来）
- fixed-order split reduce（保证确定性）

先做格式只得到内存收益（权重 -14~-22%、KV pool 1.5~2.5x），得不到 1.17–1.47x 的 GEMM 加速。

### 2.5 ceiling 不是上界

见 `00-architecture.md` §4 末。不要对齐数字，要对齐"因子排序是否正确"。

### 2.6 规模

单 agent 基线必须复现（1.34x vs 2.13x）。它比主线便宜得多，建议并行做——
没有这个对照，"成本模型有用"只是断言。论文数值是参照，不要求新实验精确相等。

## 3. 阶段计划

### 阶段 0：环境与自检（无优化）

- 起 SGLang 冻结版本（论文用 v0.5.20，token-identical 构建）
- 单请求 AR / stock 跑通，拿到 AR 基线 tok/s
- 实现 exact replay（录 lattice + target 输出，离线重跑选树与验证）
- 实现 profiler 聚合（按 kernel 类）
- 按`02-acceptance.md` §5–6保留校准证据与正确性/执行自检。

退出判据：同尺度stock null证据完整，噪声估计口径由维护者固定并进入后续晋升阈值；
真实正确性及执行完整性自检通过。不要求任意GPU达到固定0.2%噪声或CI宽度。
2026-11-08来源对齐见[对齐记录](experiments/p5-acceptance-alignment-20261108.md)；
当前controller未切换，旧诊断布尔不改写。

### 阶段 1：成本模型（无优化）

- byte/FLOP floor 表（60% dense 峰值、90% 带宽）
- 三因子计算，输入为 replay + profile
- 在 stock 上跑一次，输出三个因子

验证方式：与论文起点对照（tau 1.83 / overhead 1.01 / kernel 1.39，2.57x ceiling）。
数量级相符即可，不要求逐位相同。

### 阶段 2：控制器与评测器

- 配对计时、互换 GPU、噪声标定
- token forcing（teacher-forced scorer + 两规则 + delta 标定）
- sealed request 管理与账本

**这一阶段结束时必须有可用的人类界面**：能对任意两个 ref 跑一次判定并得到 promote/reject。

### 阶段 3：第一轮搜索

- master 按 Phase 0 因子开方向
- 目标：树（tau 因子）
- 预期达到论文第 1 轮的性质：184 -> ~270 tok/s

### 阶段 4：第二、三轮

- 第 2 轮做 W12（kernel/字节因子）
- 第 3 轮：若两因子饱和，改 ceiling 假设（TLV）
- **这里是对整个架构的真正检验**：能否自己意识到"该改目标函数的假设"

### 阶段 5：记忆与迁移

- 蒸馏条目，验证条目连同其依赖作用于stock后准确还原源系统代码。
- 迁移到 DSpark 或 PRO 6000（若硬件可用）

## 4. 每个阶段的验收

| 阶段 | 验收命令形态 | 通过条件 |
|---|---|---|
| 0 | `controller/calibrate --stock-vs-stock` | 校准证据完整、估计口径预登记；全宽与偏移单独报告，不设0.2%论文硬门槛 |
| 0 | `controller/selftest --inject-fault` | 假阳被拒、假阴被放行 |
| 1 | `costmodel/factors --ref stock` | 三因子与论文起点数量级相符 |
| 2 | `controller/measure --a stock --b <ref>` | 返回 gain + ci95 + verdict |
| 3-4 | `controller/sealed --ref <ref>` | sealed 通过且 token forcing 通过 |
| 5 | `memory/verify --entry <id> --onto stock` | 条目及其依赖字节级复现源系统代码 |

## 5. 需要你先决定的事

1. **模型可得性**：能否拿到 Qwen3.8-27B 与 DFlash2？拿不到则需确认"架构复现"降级方案。
2. **SGLang 版本**：v0.5.20 是否可获取？若要污染主线，需决定改到什么程度。
3. **GPU 预算**：全量 530 GPU-小时；主线三轮估计在其 1/3 左右。是否按主线走。
