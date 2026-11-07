# HANDOFF — 交接给新 session

> 本文件是**唯一的入口**。新 session 读这里，不要试图读旧对话。
> 最后更新：2026-11-07（私有 GitHub origin 已配置；执行主线为 NorthJob，image 未确认、零次提交；版本状态以 git log/status 为准）。

## 当前接续点：NorthJob 准备与 Git 全流程追踪

- 当前在原十步主线的第 2 步“配对测量远程验收”；镜像、CLI 和挂载是内部准备，不重新拆成研究大步骤。大步骤先报目标、流程与自检并等用户允许，内部小步骤自主安排。
- 私有远端：`https://github.com/Sym-Je/SpecPilot-reproduction.git`（origin）。用户已授权每个大步骤结束后更新 README 进度、交接与相关代码，验收后阶段提交并推送；不上传大产物、凭据或 sealed 数据。
- 重新对齐论文/公开项目后的详细方案见 `docs/11-reproduction-plan.md`（草案，未授权修改 controller 或已有判据）。其中区分每 suite 4 条诊断、上游默认 6 条 dev 表格和后续 sealed；正式 CI 与真实 forcing 尚有维护者待办。
- `exp/p3_pair_run.py` 已实现 fresh 双 server、controller 逐请求配对、两轮物理 GPU UUID 互换、每轮一对 JSONL 和几何平均 CI；controller 未改。
- 验收：`PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s harness -p test_p3_pair_run.py` → 15/15；shell 语法和 `git diff --check` 通过。
- AR/stock 的 20 请求、2048 token、两轮执行已尝试，但在起 server 前被忙卡保护拒绝：GPU0/1 分别有 PID 59780/59781（各约 518 MiB，当前命名空间查不到进程名）。未杀进程，无实测数字。
- 用户已将后续执行统一到 NorthJob；不再等待本机两卡释放，也不继续扩建本机调度。先按 northjob-submit skill 准备任务，向用户确认 k8s image，查重名并展示完整命令与资源；获准提交后核对 code==200 且有 job_uuid。当前 image 未指定，不能猜测或直接提交。
- 远程按既有配对协议复用编排：先 AR/stock（20 请求、2048 token、两轮物理换卡，诊断区间 [3.555, 4.345]），通过后 AR/final，再直接 stock/final。相同 H100 不自动取消配对规则；远程环境与 GPU 生命周期尚未验证。
- Git 管理全流程的计划、任务、证据索引和决策，见 `docs/12-experiment-management.md`；每次实验使用 `docs/experiments/TEMPLATE.md` 建记录。原始产物外存并校验，不改 controller、不手写正式账本、不提前 RSI 或 sealed。
- 本机执行日志：`logs/p3-local-ar-stock-20261107.log`；因预检失败尚未创建对应运行目录。

## 一句话现状

RSI 的**制度层**在 mock 规模跑通（G2–G5）；**执行层**已打通到"三臂各起一次真 server、
跑同一请求集、落可审计 JSONL"（P0–P3，G6/G7/G8 全绿）。
**一次 NorthJob 都没提交过。** 论文数字一个都还没独立测出；本机烟测 stock/AR 3.74×
只作历史诊断，不代表正式配对尺子已经校准。

## 接手前必做（5 分钟）

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
git log --oneline -5 && git status --short
cat AGENTS.md              # 铁律，不可协商
cat docs/06-gates.md       # 已通过的闸门与实际数字
cat docs/07-experiment.md  # 短期实验记录 + 5 个踩过的坑（必读）
ls harness/sglang/         # 启停脚本，环境约定全在 env.sh
cat docs/09-p3-harness-validation.md   # 三臂烟测实测数字与"为什么不能引用"
```

## 1. 任务边界

复现 *SpecPilot*（arXiv 2611.02501）的 **RSI 闭环**，引擎用 SGLang v0.5.20，硬件 H100 + Qwen3.8-27B + DFlash2。

**永远区分两件事**：
- **架构复现** = 闭环/测量/判据/账本/记忆是否正确
- **数字复现** = 能否独立测出 config 的 2.13× [2.07, 2.19]（sealed final vs stock）

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

## 5. 卡点已解除：stock server 在真实权重上跑通（2026-11-07）

`logs/serve2.log`（stock 臂，block 8）：
```
Load weight end. elapsed=72.92s, type=Qwen3_5ForConditionalGeneration
Load weight end. elapsed=4.90s,  type=DFlash2DraftModel
Initialized DFLASH draft runner. attention_backend=fa3, block_size=8
KV Cache allocated: #tokens 108029
scheduler_e2e=219.34s  cuda_graph={prefill=39.73, target_verify=1.45, draft_decode=8.68}
The server is fired up and ready to roll!
```

此前崩在 `memory_pool.py:2114 _init_kv_copy_and_warmup` → triton JIT → 缺 C 编译器，
已由 `harness/sglang/env.sh` 的三件修补解决（conda gcc 14.4.0 / cuda-compat libcuda / CUDA_HOME）。

**第一条真实 greedy 请求已跑通**（`harness/sglang/probe_greedy.py`）：

```
[gsm8k-1182] 425 tok 2.70s 157.6 tok/s verify=81 tau=5.25
[gsm8k-211 ] 309 tok 1.54s 201.1 tok/s verify=46 tau=6.72
[gsm8k-877 ] 505 tok 2.50s 202.0 tok/s verify=79 tau=6.39
deterministic 3/3          → ACCEPT
```

- greedy 两次 output_ids 的 sha256 完全相同 → 逐 token 判据可以接到真引擎。
- τ 均值 6.12（论文 stock 4.65，不同请求集，不可直接比）。
- **这是烟测，不是测量**：单臂、无预热标定、无配对、无 GPU 互换。
  详见 `docs/07-experiment.md` 第二部分。

## 6. 起 server / 打请求

```bash
# 前台起（长任务必须前台，supervisord 会 reap 后台进程）
bash harness/sglang/serve.sh 2>&1 | tee logs/serve.log

# 另一终端：greedy 探针，自带确定性验收
source harness/sglang/env.sh
$SP_PY harness/sglang/probe_greedy.py --n 3 --repeats 2 --max-new-tokens 2048
```

`serve.sh` 已对齐上游 `research/scripts/launch.sh`：`--random-seed 0`、`--served-model-name`。

## 7. 之后的路线

- **P0（已完成）**：`docs/08-upstream-pin.md` — tarball sha256 `25e68b1b…602dd4`，
  规范化清单 `assets/upstream/MANIFEST.sha256`（3097 文件）sha256 `4bca3c10…81563f`；
  已核对 tarball 解包树与现有树逐字节一致（差异仅 .pyc）。
- **P1（已完成）**：`harness/build_engine.py` + `gates/g6_engine_build.py`（6/6）。
  stock `e5472c4f…652e3ff` / final `d406ba81…54f90a`，产物在
  `specpilot_data/work/engines/<setting>-{stock,final}`。`env.sh` 已改为优先用派生树，
  缓存按 `TREE_SHA[:16]` 分桶。验收：派生 stock 与上游树逐 token 一致（3/3）。
  坑：换 PYTHONPATH 会让 JIT 缓存失效，首次启动 `draft_decode` 图采集 8.7 s → 222.8 s。
- **P2（已完成）**：`controller/http_transport.py` + `gates/g7_http_transport.py`（5/5）。
  真实引擎的 options 是启动参数，所以配对变成"两个 server 各占一卡"；
  `HttpPairBench` 复用 `controller.stats`，统计不改。单卡顺序路径
  `SequentialPairBench` 直接 raise，**不许**冒充配对。验收含同 arm 确定性、
  噪声地板、`1%+2*noise` 下界判据注入测试。
- **P3（链路已完成，编排 CPU 验收通过；下一步 NorthJob 环境确认与远程测量）**：链路提交 `ed8b571`，编排版本以当前 Git 历史为准。
  `exp/p3_pair.sh <arm> <gpu> <port> <out.jsonl>` = 单臂执行单元（起 server → run_arm → 停）；
  `harness/sglang/gen_final_env.py` 从 config.json 派生 final 的 46 个 `SPECPILOT_*`（不手抄）；
  `gates/g8_pair_arms.py` = 配对前置条件 8 项，其中 **E2 要求三臂 `input_sha256` 逐条相同**。
  本机烟测（1 条/suite、256 tok、单卡顺序）：AR 43.6 / stock 162.9 / final 245.7 tok/s，
  stock/AR **3.74×**（论文 3.95×），τ 5.02→11.13（论文 4.65→13.08）。
  `final/stock` 只有 1.51×；**256-token 短序列摊不开固定开销**是待验证解释，不能排除覆盖层或配置生效问题。
  下一步经 NorthJob 申请双卡、每臂 fresh server，`P3_PER_SUITE=4 P3_MAX_NEW=2048`、两轮物理换卡，依次测 AR/stock、AR/final 和直接 stock/final。
  通过后按正式 dev 协议扩大范围；P4 还需 controller 真实判据就绪。image 未确认前不提交。
  详见 `docs/09-p3-harness-validation.md`、`docs/11-reproduction-plan.md` 和 `docs/12-experiment-management.md`；`docs/10-p3-local-pairs.md` 保留执行单元说明，不再要求先跑本机。
- **P4（2 天，可与 P3 并行设计）**：建 `eval/sealed`（controller 侧抽样，agent 不可见）；
  `patches/` 先放 `noop`（必须 token-identical 到 stock）+ `block_8_16`。
  **必须新增门禁**：τ 计数口径一致性 —— final τ=13.08 是 *per exact-weight pass*
  （TLV 下可超 16 token draft block），stock τ=4.65 是 per verify step，**两个 τ 不同源**。
  用 τ 做奖励会把"换计数口径"当成"机制有效"。`run_arm.py` 已落 `tau_source` 字段
  （`per_verify_step` / `ar_no_verify`），final 的 TLV 口径仍是待办的第三个值。
  **lossless 判据**：paper 的 lossless 指"greedy 且每个 token 由 target 判定"，**不是**
  AR 与 stock 逐 token 相同（烟测仅 1/5 相同，第 3 个 token 就分叉，原因是采样路径不同 →
  BF16 GEMM 形状不同 → argmax 在近似并列处翻转）。跨路径的 lossless 只能靠
  **token forcing**（把 stock 的 token 序列喂回去，逐位检查 target argmax）来证明。
- **P5（长期）**：真 RSI。**不要追 W12**（69 KB CUDA kernel，短期做不到）。
  从简单机制族起：block size、tree shape、accept 阈值、attention backend、mem-fraction。

## 8. 仓库现状

`git log`: … e87db70 → 5a46dca → 3d14168(P0) → 76b642d(P1) → 39edfcb(P2) → ed8b571(P3)
（以 `git log --oneline` 为准）

**新门禁**：G6 引擎树可重现 6/6 · G7 传输层 5/5 · G8 配对前置 8/8
**派生树**：stock `e5472c4f…652e3ff` / final `d406ba81…54f90a`
**final env**：`/gpfs/users/jixinpeng/specpilot_data/work/env/h100_c1_qwen38-27b_dflash2-final.env`
（派生，勿手改；`gen_final_env.py --check` 可验）

**已通过验收（mock/TinyLM 规模）**
- `controller/measure.py` 双卡配对 + 互换 GPU + bootstrap CI
- `controller/ledger.py` append-only 哈希链（`ledger/rsi.jsonl` 8 条，chain OK）
- `controller/landlock.py` G3 9/9；`controller/token_force.py` G4 5/5
- `orchestrator/loop.py` G5 6/6；G2 故障续跑 6/6
- 噪声标定 3.11%，晋升阈值 = 1% + 2×噪声 = 7.21%

**已通过验收（真实 27B + DFlash2，本机 2×H100）**
- P0 stock server 跑通；P1 派生树 stock 与上游树逐 token 一致
- P3 三臂各起一次真 server 并跑完同一请求集（`docs/09`）

**空壳 / 未做**
- `eval/sealed` 空（`eval/dev` 已由 `assets/upstream/dev` 供给，5 suite × 20 条）；
  `memory/entries/rsi.json` 是 mock 结果
- `exp/run_e2e.sh` 用 TinyLM，不是真引擎
- **零次 NorthJob**
- `harness/make_traces.py`：自蒸馏语料生成，**WIP，不在主路径上**（DFlash2 已是训练好的 drafter，
  不需要自蒸馏）。保留但不要依赖。
- `harness/qwen_backend.py` / `qwen_spec.py`：自写前向，与 HF 数值一致（max diff 0.0），
  修好了 `is_causal` 在 `S>T` 时左上对齐的坑。**但不作为主引擎**（AR 35 tok/s，launch-bound
  会污染成本结构：让"加大 block"被高估、"省字节"显示零收益）。

## 9. 论文关键数字（用于对齐，不是结论）

`h100_c1_qwen38-27b_dflash2`：stock/AR 3.95×，final/AR 8.86×，
final/stock **2.13× `[2.07, 2.19]`**，τ 4.65 → 13.08。

> 基准取值只看 `assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json` 的 `paper` 段
> （`sealed_final_vs_stock = 2.13x [2.07, 2.19]`）。上游 README 的 2.24× 来自 dev 表格的
> 8.86/3.95，与 sealed 的 2.13× 是不同请求协议，不应简单称为配置冲突。
> **sealed 目标以 config 为准**，dev/AR 对照单独报告，不在口径之间漂移。

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
