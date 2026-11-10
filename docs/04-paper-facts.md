# 04 — 论文关键数字速查

用于核对实现，不用于对齐。所有数字来自正文与附录。

## 验收规则出处（2026-11-08核对）

- §3.2，第6页：晋升比较收益95%下界与`1% + 2×stock-vs-stock噪声`；输出分歧时约3%。
- 同段H100单请求噪声`<0.1%`是论文观测值，不是所有部署的硬验收阈值。
- 原文没有规定“null的95%CI全宽<0.2%”或“两独立会话CI均须覆盖1”；这是本地额外自检。
- §3.3，第6–7页：stock引擎FP32-head scorer、实测stock mismatch/δ、rate/event双规则；
  §5.1，第10页：sealed两次配对、每benchmark逐请求速率比几何平均，再等权聚合。
- 噪声精确估计量与bootstrap实现细节不能由上述观测值反推。正式口径见[验收规则](02-acceptance.md)，
  本次仅完成文档来源对齐，controller未切换；证据见[对齐记录](experiments/p5-acceptance-alignment-20261108.md)。

## 硬件

| 项 | 值 |
|---|---|
| H100 SXM5 峰值带宽 | 3.35 TB/s |
| RTX PRO 6000 Blackwell | sm 120，实测 1.51 TB/s，99 KB SMEM/block，无 wgmma |
| 引擎 | SGLang v0.5.20，token-identical 冻结构建 |
| Agent | Claude Opus 5.5 in Claude Code |

## 主结果（speedup over AR）

| 设定 | stock | SpecPilot |
|---|---|---|
| 单请求，H100，Qwen3.8-27B + DFlash2 | 3.95x | 8.86x |
| 单请求，H100，Qwen3.8-27B + DSpark | 3.74x | 9.41x |
| 单请求，PRO 6000，Qwen3.8-27B + DFlash2 | 4.46x | 10.87x |
| 单请求，PRO 6000，Muse-Glimmer-30B + DFlash2 | 4.69x | 10.63x |
| 批处理，H100，FP8 Qwen3.8-27B + DFlash2 | 2.02x | 3.90x |
| 批处理，H100，FP8 Qwen3.8-27B + DSpark | 1.94x | 3.93x |
| 批处理，H100，Qwen3.5-4B + DFlash2 | 1.51x | 3.77x |
| 批处理，H100，Gemma-4-12B + EAGLE-3 | 0.68x | 2.09x |

## Sealed gains over stock（Table 3）

| 目标 | Drafter | Gain | Tokens/step |
|---|---|---|---|
| Qwen3.8-27B, H100 | DFlash2 | 2.13x | 4.65 -> 13.08 |
| Qwen3.8-27B, H100 | DSpark | 2.38x | 4.42 -> 12.85 |
| Qwen3.8-27B, PRO 6000 | DFlash2 | 2.44x | 5.23 -> 12.80 |
| Muse-Glimmer-30B, PRO 6000 | DFlash2 | 2.21x | 5.16 -> 12.64 |
| Qwen3.8-27B FP8 (batch) | DFlash2 | 1.85x | 4.56 -> 5.39 |
| Qwen3.8-27B FP8 (batch) | DSpark | 1.94x | 4.37 -> 5.42 |
| Qwen3.5-4B (batch) | DFlash2 | 2.39x | 6.58 -> 6.97 |
| Gemma-4-12B (batch) | EAGLE-3 | 3.11x | 2.04 -> 2.54 |

绝对速率（单请求，tok/s）：H100 上 AR ~50，stock 184，SpecPilot 416。

## 成本模型参考值

起点 ceiling 2.57x = tau 1.83 x overhead 1.01 x kernel 1.39
第 2 轮前 ceiling 1.95x = tau 1.34 x step-cost 1.45

2026-11-10核对原PDF：上述历史数值在附录B（第20页）明确使用oracle的tau和full-peak floors；
正文§3.1式(4)（第5页）定义的却是best-first最佳预算与60% dense peak/90% bandwidth。
复现时分别标注，不将两者混成一套数值目标；本地证据缺项仍为未知，见
[Phase 0口径及采集](experiments/ceiling-20261110.md)。

单请求 27B：读权重占 23.61 ms 步时的 80%；即便峰值带宽也需 92% 的时间读全部字节。
GEMM 时间：1 行 17.88 ms，64 行 18.58 ms（行数几乎免费）。

## W12

| 项 | 值 |
|---|---|
| 编码 | 符号 1 + 高尾数 3 + binade 偏移 4 + 低尾数 4 = 12 bit |
| 窗口 | 每输出通道 16-binade |
| 逃逸率 | 7.3e-5（Qwen3.8-27B） |
| bits/weight | 12.013–12.020（8 个 dense 模型） |
| 27B 转换层 | 44.67 -> 33.58 GB |
| GEMM vs cuBLAS | 1.17–1.47x（1–32 行，H100） |
| AR 解码（SGLang） | 1.19–1.28x 单请求，1.13–1.20x @32 |
| KV pool 增长 | 2.03x（27B），2.54x（Muse） |
| PRO 6000 | mma.sync，13 个形状上 1.18–1.68x |
| 记录 | 12 KB / tile（128x64），前 2/3 为 8-bit 视图 |

## 树与 TLV

- stock 链 tau = 4.25（8 位置，exact replay）；oracle 上界 6.42@8 / 8.20@16
- best-first：5.38@32 节点（8 位置格）；5.85@32 / 6.25@63（16 位置格）
- 16 节点 best-first 约等于 EAGLE-2 风格 top-4（5.03 vs 5.02），优于 Sequoia（4.71）
- TLV 一轮周期约 30 ms：draft 1.05 x2，Q pass 11.5，exact pass 14.9，glue ~1.6
- TLV 收益：每精确 pass 6.16 -> 11.67 tokens
- Q pass 与 exact pass top-1 一致率：0.983（nested）、0.981（INT6）、0.984（INT6/INT8）

## 循环成本（附录 D）

| 项 | 值 |
|---|---|
| 单轮 | 7–20 小时，20–86 GPU-小时 |
| 13 轮合计 | 164 小时，530 GPU-小时 |
| 代码变更 | 486，晋升 54 |
| 记忆规模 | 140 条，最多 12 前置依赖，15 条 sm120 专属 |

## 批处理的 regime 依赖（§6.5）

| 机制 | 单请求 | 批处理 |
|---|---|---|
| 宽树 / W12 / TLV | 三部署均增益 | 24 节点树 -14.9%（FP8）；24 位置块 -9.9%、TLV -13%（BF16） |
| 共享节点预算 | — | 比等规模独立树多接 6–14% token |
| 按请求 drafter block | — | 1.040x |
| prompt admission | — | 仅放行被阻塞的 prompt 得 3.5%；放行所有短 prompt 亏损 |

## 被关闭的方向（附录 F）

| 方向 | 证据 | 结果 |
|---|---|---|
| 11-bit 权重 | microbench | decode 慢 3x |
| 跨 GEMM 持久化 W12 | microbench | 196 vs 172 us/layer |
| 单 kernel GDN 层 | microbench | 32.3 vs 17.3 us/layer |
| W12 上 48 节点树 | timed | -4.3% |
| 三级验证 | replay | -2 ~ -12% |
| 7-bit nested Q view | replay | -3.8% |
| 6-bit nested Q view | replay | -17.5% |

节点经济学：W12 系统上第 32 个节点以上每节点约 0.17 ms/步，收益约 0.063 ms。
nested Q view 每减 1/8 字节，top-1 一致率掉约 0.01（约为省下时间的 2 倍代价）。
