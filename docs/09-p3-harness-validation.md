# P3 —— 尺子校准（harness 验证），不是算法结论

**状态：链路已通，数字不可引用。**

## 做了什么

`exp/p3_pair.sh` 是**单卡单臂**执行单元：起 server → 等就绪 → 跑固定请求集 → 落 JSONL → 停 server。
配对逻辑不在这个脚本里（27B 一臂占 78/80 GB，两臂必然两张卡），在 `controller/http_transport.py`。

三臂定义与上游 `scripts/serve.sh` 一致：

| 臂 | 引擎树 | block | 额外参数 |
|---|---|---|---|
| `ar` | stock (`e5472c4f…`) | 0 | 无 spec 参数 |
| `stock` | stock (`e5472c4f…`) | 8 | `--speculative-algorithm DFLASH` |
| `final` | final (`d406ba81…`) | 32 | DFLASH + 46 个 `SPECPILOT_*` |

## 本机烟测（1 条/suite，`max_new_tokens=256`）

| id | AR tok/s | stock | final | stock/AR | final/AR | final/stock | τ stock | τ final |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gsm8k-1182 | 40.3 | 162.9 | 258.5 | 4.04× | 6.41× | 1.59× | 5.12 | 12.19 |
| math500-25 | 42.3 | 178.4 | 312.9 | 4.21× | 7.39× | 1.75× | 5.57 | 15.06 |
| humaneval-117 | 43.6 | 133.9 | 242.6 | 3.07× | 5.57× | 1.81× | 4.20 | 11.13 |
| mbpp-31 | 45.2 | 140.6 | 236.0 | 3.11× | 5.22× | 1.68× | 4.27 | 10.67 |
| mt-bench-61 | 47.1 | 166.5 | 245.7 | 3.54× | 5.22× | 1.48× | 5.02 | 10.67 |
| **median** | **43.6** | **162.9** | **245.7** | **3.74×** | **5.64×** | **1.51×** | **5.02** | **11.13** |

`gates/g8_pair_arms.py` → PASS 8/8（含"三臂 `input_sha256` 逐条相同"）。

## 为什么这些数不能当复现结论

1. **`max_new_tokens=256` 而非论文的 2048**，5 条而非 20 条/suite，全部以 `length` 结束。
   final 每步验证 32 个节点，固定开销（verify kernel launch、树构建、GEMM 形状切换）
   在短序列上摊不开 → final/stock 被系统性低估。τ 的比值（11.13/5.02 = 2.22×）
   反而高于吞吐比值（1.51×），正说明 **per-step 开销变大了**，与上述解释一致。
2. **单卡顺序**：AR → stock → final 是三次独立启动，没有 GPU 互换，没有配对 CI。
   卡温/主频漂移全部计入。
3. 上游口径是 **dev split 首轮、2048 new tokens、per-request speedup 的几何平均**。
   本表用 median 吞吐，口径不同，只能看量级。

## 有意义的部分

- AR 43.6 tok/s 与"27B 单请求权重读取下界 23.61 ms/步 ≈ 42 tok/s"吻合 → AR 臂没跑偏。
- stock/AR 3.74× vs 论文 3.95×（差 5%），τ 5.02 vs 4.65（差 8%）→ **尺子是对的**。
- final 树 + 46 个 `SPECPILOT_*` 真能起、真能加速，且引擎树 hash 与 P1 组装结果一致。

## 下一步（P3 正式测量）

需要 NorthJob：三臂 × 两张卡，每臂 fresh server，`--max-new-tokens 2048`，
`P3_PER_SUITE=20`，跑 ≥2 轮取 paired CI。判据来自 `controller/stats.py`，
**不是**本文件里的手算比值。
