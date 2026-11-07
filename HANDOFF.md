# HANDOFF — 交接给新 session

> 本文件是**唯一的入口**。新 session 读这里，不要试图读旧对话。
> 最后更新：2026-11-07。维护者：上一轮 session。

## 一句话现状

RSI 的**制度层**已经在 mock 规模跑通并有验收证据（G2–G5）；**执行层**卡在最后一步环境修补：
SGLang server 能加载 52 G 的 Qwen3.8-27B + DFlash2 draft，但在 KV 内存池预热时因缺 C 编译器崩溃。
**一次 NorthJob 都没提交过。** 论文数字一个都还没独立测出。

## 接手前必做（5 分钟）

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
git log --oneline -5 && git status --short
cat AGENTS.md              # 铁律，不可协商
cat docs/06-gates.md       # 已通过的闸门与实际数字
cat docs/07-experiment.md  # 短期实验记录 + 5 个踩过的坑（必读）
ls harness/sglang/         # 启停脚本，环境约定全在 env.sh
```

## 1. 任务边界

复现 *SpecPilot*（arXiv 2611.02501）的 **RSI 闭环**，引擎用 SGLang v0.5.20，硬件 H100 + Qwen3.8-27B + DFlash2。

**永远区分两件事**：
- **架构复现** = 闭环/测量/判据/账本/记忆是否正确
- **数字复现** = 能否独立测出 2.24×（final vs stock）

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
| NorthJob | `/gpfs/envs/miniconda3/bin/northjob`（不在 PATH） |
| 备选环境 | `envs/alice-sglang`（torch 2.9.1+cu128）—— 535 驱动上唯一原生可用的 torch，但**不含 sglang 0.5.20 依赖** |

**三个坑**（`harness/sglang/env.sh` 已针对它们写好）
1. torch 2.13+cu130 需 R580；535 要靠 NVIDIA **cuda-compat-13-0** 的 `libcuda.so.1`。
2. 全系统无 C 编译器。Triton JIT 会崩 `Failed to find C compiler`。
   解法：conda-forge `gcc_linux-64=13` 或 `nvidia-cuda-nvcc==13.0.*`。
3. 容器内 supervisord(PID 1) 会 reap 后台进程（exit 255）。长任务**前台跑**或走 NorthJob。
   `/tmp` 会被清空。

## 5. 卡点：一个几乎成功但没起来的 server

`logs/stock-serve.log`：**模型全部加载成功**
```
Load weight end. elapsed=69.74s, type=Qwen3_5ForConditionalGeneration, avail mem=26.87GB
Load weight end. elapsed=5.13s,  type=DFlash2DraftModel, avail mem=23.10GB
Initialized DFLASH draft runner. attention_backend=fa3, block_size=8
```
→ **DFlash 在 0.5.20 上可用，stock 的 block_size=8 口径成立**（这是重要结论）。

崩溃点：`memory_pool.py:2114 _init_kv_copy_and_warmup` → triton JIT → 缺 C 编译器。

## 6. 立刻做（按顺序）

1. 验证 `harness/sglang/env.sh` 里的三件修补是否真的生效：
   ```bash
   source harness/sglang/env.sh
   $CC --version                    # 应有 gcc 13.x
   $SP_PY -c "import torch;print(torch.cuda.is_available())"   # 应为 True
   ```
   任一不满足就修它，**不要再换环境、不要 pip 升级**。
2. 前台起 server：`bash harness/sglang/serve.sh 2>&1 | tee logs/serve2.log`
   验收：`curl -s localhost:30000/health_generate` 返回 200。
3. 打一次 `/generate`（greedy，block 8），确认能出 token、记录 output ids。

## 7. 之后的路线

- **P0（30 min）**：把上游来源 pin 进 `docs/08-upstream-pin.md`（无 .git，要记 tarball 哈希）；
  决定 `harness/make_traces.py` 提交或丢弃；`scratch/`（399 M，含 sglang 0.5.20 wheel 与解包树）归档。
- **P1（1 天）**：`harness/build_engine.py` —— 按 `settings/*/config.json` 组装 stock/final 两棵树，
  打印 content hash（sha256 of canonical {relpath: file sha256}），两次构建 hash 必须相同。
- **P2（1–2 天）**：`controller/measure.py` 的 worker 从 JSONL stdio 换成本地 HTTP
  （`POST /generate`，body `{input_ids, sampling_params, stream}`），**只换传输不改统计**。
  验收：同请求两次 output ids 的 sha256 相同。
- **P3（2 天，NorthJob）**：三臂配对 AR / stock / final，每臂 fresh server，双卡互换。
  目标 stock/AR ≈ 3.95×，final/stock ≈ 2.24×（上游 CI `[2.18, 2.32]`）。
  **这一步检验的是尺子，不是算法。**
- **P4（2 天，可与 P3 并行设计）**：建 `eval/sealed`（controller 侧抽样，agent 不可见）；
  `patches/` 先放 `noop`（必须 token-identical 到 stock）+ `block_8_16`。
  **必须新增 G6 门禁**：τ 计数口径一致性 —— final τ=13.08 是 *per exact-weight pass*
  （TLV 下可超 16 token draft block），stock τ=4.65 是 per verify step，**两个 τ 不同源**。
  用 τ 做奖励会把"换计数口径"当成"机制有效"。
- **P5（长期）**：真 RSI。**不要追 W12**（69 KB CUDA kernel，短期做不到）。
  从简单机制族起：block size、tree shape、accept 阈值、attention backend、mem-fraction。

## 8. 仓库现状

`git log`: fd64fe9 → a251ee5 → 87256e8 → cd0ac1d → d497a7f

**已通过验收（mock/TinyLM 规模）**
- `controller/measure.py` 双卡配对 + 互换 GPU + bootstrap CI
- `controller/ledger.py` append-only 哈希链（`ledger/rsi.jsonl` 8 条，chain OK）
- `controller/landlock.py` G3 9/9；`controller/token_force.py` G4 5/5
- `orchestrator/loop.py` G5 6/6；G2 故障续跑 6/6
- 噪声标定 3.11%，晋升阈值 = 1% + 2×噪声 = 7.21%

**空壳 / 未做**
- `eval/dev`、`eval/sealed` 都空；`memory/entries/rsi.json` 是 mock 结果
- `exp/run_e2e.sh` 用 TinyLM，不是真引擎
- **零次 NorthJob**
- `harness/qwen_backend.py` / `qwen_spec.py`：自写前向，与 HF 数值一致（max diff 0.0），
  修好了 `is_causal` 在 `S>T` 时左上对齐的坑。**但不作为主引擎**（AR 35 tok/s，launch-bound
  会污染成本结构：让"加大 block"被高估、"省字节"显示零收益）。

## 9. 论文关键数字（用于对齐，不是结论）

`h100_c1_qwen38-27b_dflash2`：stock/AR 3.95×，final/AR 8.86×，final/stock 2.24×
（独立复现 2.25× `[2.18, 2.32]`），τ 4.65 → 13.08。
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
