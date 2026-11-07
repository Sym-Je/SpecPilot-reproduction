# P3 本机双卡编排

## 范围

执行方式已调整：后续经 NorthJob 跑 AR/stock、AR/final，再直接 stock/final；不再等待本机 GPU。本文件保留编排与运行参数说明，下面的本机命令不是 NorthJob 提交命令；远程挂载、环境和启动方式须单独验收。此阶段不建 sealed、不做 RSI 晋升。
真实测量前必须保证两卡空闲；已有计算进程时硬失败，不杀进程，不在忙卡上强行测量。

`exp/p3_pair_run.py` 复用 `controller/http_transport.py` 的 Arm/HttpPairBench，不改 controller。
它通过 `exp/p3_pair.sh` 的 opt-in `P3_SERVER_ONLY=1` 起两根 server，统一预热后逐请求配对；每轮结束停两根 server，等待 GPU 释放后交换物理 GPU，再 fresh 启动。
启动时传 GPU UUID，避免 CUDA ordinal 与物理卡序号不一致；controller 的逻辑 swap 关闭。
原来的单臂脚本默认仍起 server、独立请求、落 JSONL、停 server。

## 先验收，再实测

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s harness -p test_p3_pair_run.py
bash -n exp/p3_pair.sh
git diff --check
git diff --exit-code -- controller
```

CPU 测试使用合成 server/结果，包含真实本地 HTTP 与未改动的 HttpPairBench 传输联调，不产生真实性能数字。
覆盖物理换卡、fresh 启动、失败清理、完整配对持久化、身份隔离、覆盖完整性、几何平均、忙卡保护和默认不执行。

## 第二步：AR vs stock

不加 `--execute` 只打印计划，不创建输出目录、不起 server、不占 GPU。
实际运行必须前台、TTY；所有输出落盘，不用 nohup 或脱离父进程的后台任务。

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
P3_PER_SUITE=4 P3_MAX_NEW=2048 \
  /gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python -B \
  exp/p3_pair_run.py ar stock --gpus 0 1 --ports 30100 30110 \
  --rounds 2 --out-dir logs/p3-local-ar-stock-20261107 --execute \
  > logs/p3-local-ar-stock-20261107.log 2>&1
```

共五 suite × 4 请求 = 20 个不同请求；两轮 = 40 个完整配对、80 条臂记录。
两轮分别为 AR→GPU0/stock→GPU1 与 AR→GPU1/stock→GPU0，每轮两根 fresh server。
每轮先做两次不计时预热；正式请求调用 run_pair(warmup=0, swap=False)。

用户指定的本阶段判据：stock/AR 的几何平均在 3.95× ±10%，即 [3.555, 4.345]。
判据作用于点估计，不偷换为整个 CI 必须落入该范围。未达标时返回非零并保留结果，不自动进入 AR/final。
这不是论文 sealed 结果验收，也不是 RSI 晋升判据。

## 第三步：AR vs final

在 AR/stock 完成且点估计达标后，保持请求、长度、两轮换卡协议不变：

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
P3_PER_SUITE=4 P3_MAX_NEW=2048 \
  /gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520/bin/python -B \
  exp/p3_pair_run.py ar final --gpus 0 1 --ports 30100 30110 \
  --rounds 2 --out-dir logs/p3-local-ar-final-20261107 --execute \
  > logs/p3-local-ar-final-20261107.log 2>&1
```

final 树必须存在且 TREE_SHA 有效；46 个开关仍由既有 gen_final_env.py 派生并检查。
父进程不继承 SPECPILOT 机制开关到 stock/AR 子进程，避免 final 污染基线。

AR/final 给出 final/AR 的直接配对结果。与上一会话的 stock/AR 相除可作 final/stock 的间接对照，但不是同会话直接 final/stock 配对，不能把其 CI 当作直接配对 CI。
约 2.0–2.2× 支持“短序列固定开销”的解释，并非单凭吞吐证明所有覆盖机制都已生效；若仍约 1.5×，先查加载身份、配置和机制生效证据，不进入 RSI。
不得为此直接阅读交接禁止访问的上游实现；需要检查的实现证据由维护者提供或由运行时审计产物支持。

## 产物和统计

输出目录必须全新，拒绝覆盖或跨会话静默续跑。

- `manifest.json`：请求 input_ids/hash、固定参数、树 hash、GPU UUID、源文件 hash 和基线 HEAD。
- `round-01/`、`round-02/`：各自一对 `<arm>.jsonl`、canonical `pairs.jsonl`、部署身份、事件、server/launcher 日志。
- `complete.json`：对应轮次成功且 server 已完成清理；失败轮无此标记。
- `summary.json`：几何平均、双侧 95% CI、各 suite 几何平均、每请求 log-ratio 和 AR/stock 点估计验收。
- `failed.json`：异常或中断说明；此前完整配对逐条 fsync，半对不入 canonical 数据。

每请求先对两轮的速率比作几何平均，再每 suite 作几何平均，最后 suite 等权几何平均。
五 suite 的样本数必须相等且覆盖完整，不支持不等样本数。
CI 复用未改动的 `controller.stats.bootstrap_ci`，在每请求 log-ratio 上以 alpha=0.025 计算上下界，固定 seed=0、默认 10000 次。
同一请求两轮保留为一个 cluster，不把 40 个重复请求当作 40 个独立样本；重采样是 pooled request-cluster bootstrap，不是 suite-stratified bootstrap，明确写进 summary。

这些是 dev 诊断产物，不写 ledger，不使用 compare()/promoted，不宣称 sealed 数字复现或 lossless。
final 的 tau_source 标为尚未核准的 TLV 计数，不把它与论文 per-exact-pass 的 τ 直接比较。

## 后续

远程尺度数字、机制身份及 controller 真实判据确认后，才由 controller/维护者推进 P4。
后续执行统一通过 northjob-submit skill；提交前必须显式确认 image，不能猜。全流程记录见 `docs/12-experiment-management.md`。
