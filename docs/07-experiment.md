# 短期实验：整条 RSI 链路的端到端验证

> **声明**：本文验证的是**架构链路是否闭合**，不是论文数字的复现。
> 本机无 Qwen3.8-27B / DFlash2 权重，target 与 draft 都是 `harness/engine.py` 里
> 构造的 TinyLM（4 层 target / 1–3 层 draft，vocab 4096）。tok/s 的绝对值没有
> 任何跨系统可比性；有意义的是**相对收益、判定流程、账本完整性**。

## 1. 环境

| 项 | 值 |
|---|---|
| GPU | 2 × H100 80GB（`cuda:0` / `cuda:1`，worker 各自 `CUDA_VISIBLE_DEVICES` 隔离） |
| Python | `/gpfs/users/jixinpeng/miniconda3/envs/alice-sglang/bin/python`（torch 2.9.1+cu128） |
| 模型 | 代码内构造，`build_weights(Options(), seed=1)` 固定权重 |
| 请求 | 单请求，prompt = `1..32`，`max_new=256` |
| 命令 | `bash exp/run_e2e.sh` |

## 2. 结果

### 2.1 G4 —— token forcing 自检：5/5

```
[PASS] E1 确定性: 46 tokens，两次一致=True
[PASS] E2 假阴性: rate=0.0000 flagged=False
[PASS] E3 假阳性: 分歧 5/46 tokens，event_p=1.14e-33
[PASS] E4 精度不可判: 长度不变=True 全合法=True 分歧=5 → 结构上看不出损坏
[PASS] E5 长度型故障: 长度 46→45，event_p=6.08e-16
```

E4 是这套设计的关键：注入「拒绝位预测偏移」后，输出**长度不变、token 全合法、
语言上仍然通顺**，任何基于输出结构或任务精度的检查都看不出来；只有逐 token
比对能发现。这直接复现了论文 Fig 2c「四个精度区间全含 0」的结论。

### 2.2 噪声标定：3.11%

```
gate noise-calibration: noise=3.11%  mean=122.5 tok/s  n=12
protocol: stock-vs-stock paired, swap GPU, ratio dispersion
```

阈值 = 1% + 2×噪声 = **7.21%**。

### 2.3 三轮闭环

| 轮 | 机制 | 因子 | 基线中位 | 候选中位 | 95% LB | 判定 |
|---|---|---|---|---|---|---|
| 0 | `batch-verify` (block_verify F→T) | overhead | 128.0 | 144.2 | **1.1018** | **晋升** |
| 1 | `deeper-draft` (draft_layers 1→3) | tau | 143.0 | 80.9 | 0.5579 | 拒绝 |
| 2 | `longer-chain` (tree_depth 4→8) | tau | 143.6 | 100.6 | 0.7003 | 拒绝 |

- `batch-verify`：+12.7%（中位）、下界 +10.2%，三因子归因 = **overhead**
  （验证前向次数从 O(depth) 降到 O(1)）。
- `deeper-draft`：−41%。TinyLM 的 hidden 只有 256，前三层 draft 的算力开销
  远大于 τ 的提升（τ 从 ~0.08 的基线没有明显改善），方向被正确否决。
- `longer-chain`：−27%。depth 8 时接受率衰减 + 每步验证成本翻倍，净亏。

三轮都通过 forcing 无损检查（575 token 全等）——这说明 forcing 只否决、
不背书：`deeper-draft` 输出是对的，但它慢，照样被拒。

### 2.4 账本

```
records=8 kinds={'gate': 1, 'summary': 1, 'memory': 3, 'measurement': 3}
hash chain: OK
```

## 3. 过程中踩到并修掉的坑（都要记住）

1. **噪声地板不能用各次均值的标准差。** 最初这样算得到 14–15%，阈值 25%，
   任何 <30% 的机制都无法晋升。改成**配对比值的离散度**后降到 1–3%。
2. **测量窗口太短会把时钟爬坡算成噪声。** `max_new=128` 时噪声 7.4%、
   `max_new=256` 时 1.3%；预热从 16 token 改成跑满一整次同样关键。
3. **E4 原来的断言写错了。** 早期用「accepted 减 1」注入故障会改变输出长度，
   于是 `len(tb_bad) == len(ta)` 恒假。正确做法是保长度注入（改预测位），
   断言改成「长度一致 + token 全合法 + 有分歧」。
4. **draft_layers 变化需要独立权重。** worker 原先只缓存一份默认层数的权重，
   `draft_layers=3` 时 `load_state_dict` 直接报 key 缺失。现在按层数缓存，
   且深层由 stock 层循环复制（第 i 层 = 第 i%L 层），保证是同一个模型语义。
5. **记忆必须真的影响提案。** 第二次运行 `run()` 时 `promoted=[]`，
   因为三个机制都已在记忆里，proposer 无新提案 —— 这是正确行为，不是 bug。

## 4. 与论文的差距（明确不在本轮范围）

| 论文 | 本仓库 | 影响 |
|---|---|---|
| Qwen3.8-27B + DFlash2 | TinyLM 4 层 | tok/s 绝对值无意义 |
| 2.13× 加速 | 1.13×（单机制） | 规模效应完全没体现 |
| 13 轮 / 530 GPU-h | 3 轮 / ~4 分钟 | 只验证链路 |
| LLM proposer（direction/kernel agent） | 确定性 Proposer | 接口已对齐，替换即可 |
| 184 → 416 tok/s | 128 → 144 tok/s | 不构成复现声明 |

下一步若要逼近论文，必须先解决权重问题（本机无 checkpoint，NorthGate 不可达）。

---

# 第二部分：真实引擎烟测（2026-11-07，stock SGLang v0.5.20）

> **声明**：这是**烟测（smoke test）**，不是测量。3 条请求、无预热标定、无配对、
> 无 GPU 互换、单臂。它的唯一目的是证明"真实 27B + DFlash2 这条路能跑通，
> 且 greedy 输出确定"。**任何加速比结论都还不能从这里得出。**

## 1. 环境（真实）

| 项 | 值 |
|---|---|
| GPU | 1 × H100 80GB HBM3，驱动 535.154.05（CUDA 12.2），forward-compat 到 13.0 |
| 引擎 | SGLang v0.5.20，`PYTHONPATH` 指向上游 `python/`（不 pip 安装） |
| target | `/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B`（BF16） |
| drafter | `/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2` |
| Python | `/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520`（torch 2.13.0+cu130，py3.12.16） |
| 启动 | `bash harness/sglang/serve.sh`，`--speculative-num-draft-tokens 8`（= stock block 8） |
| 请求 | 单请求，`temperature 0`、`top_k 1`、`max_new_tokens 2048`，chat template（thinking 开） |

启动耗时（`logs/serve2.log`）：权重 72.9 s，KV 0.95 s，scheduler e2e 219.3 s，
CUDA graph prefill 39.7 s / target_verify 1.45 s / draft_decode 8.68 s。
KV 池 108,029 tokens（K/V 各 3.30 GB）。

## 2. 结果

```
[gsm8k-1182] 425 tok  2.70s  157.6 tok/s  verify=81  tau=5.25  sha 2f310702dffd
[gsm8k-211 ] 309 tok  1.54s  201.1 tok/s  verify=46  tau=6.72  sha 569b0f5f1158
[gsm8k-877 ] 505 tok  2.50s  202.0 tok/s  verify=79  tau=6.39  sha 7a5bd8b0cd50
deterministic 3/3
```

| 指标 | 观测 | 论文 stock | 说明 |
|---|---|---|---|
| 确定性 | 每条的两次 output_ids sha256 相同 | — | greedy 路径可信，可做逐 token 判据 |
| τ (accept_len) | 5.25 / 6.72 / 6.39，均值 **6.12** | 4.65 | 不同请求集，不可直接比；同量级 |
| decode 速率 | 157–205 tok/s | — | 非配对测量，单臂、无预热标定 |

## 3. 回归：旧验收仍然通过（同日，real server 占卡时）

```
node: bash exp/run_e2e.sh (KEEP=1)
G4 5/5  ·  RSI 3 轮  ·  ledger records=10 hash chain: OK
[calib] noise=7.77% mean=123.9 tok/s
```

**噪声从 3.11% 涨到 7.77%**，原因明确：本次标定时 stock server 正占着 GPU（`gpu_util` 竞争），
不是代码回归。这条记录的价值在于给后面的 P3 立规矩 —— **配对测量必须在独占卡上做，
标定噪声时也一样**；否则阈值会被噪声撑大，机制全被拒。

## 4. 结论与已知偏差

- ✅ **解除硬卡点**：`_init_kv_copy_and_warmup` → triton JIT → 缺 C 编译器的问题已解决
  （conda-forge gcc 14.4.0 + cuda-compat libcuda），stock server 首次在真实权重上起飞。
- ✅ greedy 确定性成立 → `controller/token_force.py` 的逐 token 判据可以接到真引擎上。
- ⚠️ **本次运行的 server 未传 `--random-seed 0`**（`server_args.random_seed = 774826012`）。
  greedy 下无影响，但已把 `--random-seed 0` 与 `--served-model-name` 补进 `serve.sh`，
  下次启动即为上游口径（`research/scripts/launch.sh`）。
- ⚠️ `spec_verify_ct` 的口径是 **per verify step**（stock），与 final 的
  *per exact-weight pass* 不同源 —— 见 HANDOFF §七 P4 的 G6 门禁要求。
- ⚠️ 3 条样本、无 AR 臂 → **不能**推出 stock/AR ≈ 3.95×。

## 5. 下一步（P1）

`harness/build_engine.py`：按 `settings/*/config.json` 组装 stock/final 两棵派生树，
打印 content hash（sha256 of canonical `{relpath: file sha256}`），两次构建必须同 hash。
