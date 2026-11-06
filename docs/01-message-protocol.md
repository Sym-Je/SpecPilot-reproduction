# 01 — 角色能力边界与消息协议

## 1. 角色能力边界

| 角色 | 必须会 | 明确不给 | 论文出处 |
|---|---|---|---|
| Cost Model | replay 选树、按 kernel 类聚 profile、byte/FLOP 算术 | 不能改测量口径 | §3.1 |
| Master | 按因子排序开方向、估 headroom、判断何时该改 ceiling 假设 | 不碰代码 | §3.2 Ph.1 |
| Direction sub | 写 SGLang patch、CUDA/Triton kernel、跑 microbench/replay | **不能自证收益**、不能读 sealed | 净 headroom >= 3% 才动手 |
| Integration | 解 patch 冲突、叠栈、判断叠加后是否仍 lossless | 不能跳过 token forcing | §3.2 Ph.2 |
| Kernel sub | stream-K / wgmma / mma.sync、看 byte floor 差距 | 不能改算法语义 | §3.2 Ph.3 |
| Controller | 配对计时、噪声标定、两规则判定、sealed 管理、账本 | **agent 无写权限** | §3.3 |

真正的稀缺能力不是"会写 kernel"，而是**会造一个能判死自己的评测器**。

推论：L0 + L2 必须先于任何优化存在，包括一个"假系统"测试集——
- 注入 logit bias 的实现**必须**被 token forcing 抓住
- 只改浮点归约的合法实现**必须**被放行

这道自检不过，后面所有数字都不可信。

## 2. 四类消息

全部走结构化文件 + 单一 CLI。不用自由文本传数——自由文本是 reward hacking 的温床。

### 2.1 Direction brief（master → sub）

```jsonc
{
  "dir_id": "r2-w12",
  "factor": "Tprof/Tfloor",              // 来自 Phase 0，必须是三者之一
  "hypothesis": "12-bit 定长记录 + 寄存器解码",
  "headroom_est": 0.25,
  "cheapest_evidence": ["byte_arith", "microbench"],
  "budget_gpu_min": 600,
  "kill_if": "decode 慢于 BF16 的 1.5x",
  "accept_if": "paired LB > 1%"
}
```

### 2.2 Patch proposal（sub → controller）

**其中所有数字一律视为未验证。**

```jsonc
{
  "ref": "git:abc123",
  "options": { "w12": true },
  "requires": ["w12_layout"],
  "claims": ["decode_bitexact_vs_ckpt", "chain_matches_stock"],
  "self_reported_gain": 1.076
}
```

### 2.3 Measurement request（sub → controller）

```jsonc
// 请求
{ "a": "stock", "b": "git:abc123", "requests": "dev/gsm8k",
  "batch": 1, "reps": 2, "swap_gpu": true }
// 响应
{ "gain": 1.076, "ci95": [1.041, 1.112], "noise_ref": 0.0008, "verdict": "promote" }
```

### 2.4 Memory entry（sealed final 之后，仅 controller 写）

```jsonc
{
  "id": "two_level_verify",
  "requires": ["w12", "tree_bestfirst"],
  "delta": "<code delta path>",
  "registry": { "variants": ["nested8", "int6", "int6_int8"], "options": { "tlv": true } },
  "contract": "only exact pass accepts tokens",
  "evidence": "ledger/2026-11-06-r3-sealed.json",
  "limits": "batching 下不适用（Q pass 占 0.80-0.88 步时）"
}
```

## 3. 铁律

> **agent 之间可以吵，但只有 controller 输出的区间能改系统状态。**

论文原话是 controller 为"agents call but cannot modify"的脚本。工程上落成：
controller 拥有写账本与改 master 分支的**唯一**权限。

## 4. 上下文纪律（工程补充，非论文内容）

长 agent 任务死于上下文，而非死于 token 上限：

- 大输出落盘，用 `tail` / `grep` / 限定行数回读；不要 `cat` 整个 profile
- 跨轮状态外置到文件（`ledger/` 记测量、`docs/` 记决策）；对话记忆不可靠
- 每步跑验收，不攒到最后
