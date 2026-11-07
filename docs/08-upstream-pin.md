# 08 — 上游快照 pin（无 git 的 tarball 基线）

上游没有 `.git`，只有一份解包树 + 一个 tarball。本文件把"我们复现的到底是哪份代码"钉死，
并给出**可重算的规范化哈希**，让任何人（包括另一个 session）都能判断手里的树有没有被动过。

## 1. 两个原物

| 项 | 路径 | 大小 |
|---|---|---|
| 解包树 | `/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main` | 334 M，4166 文件（含 .pyc） |
| tarball | `/gpfs/users/jixinpeng/SpecDec/upstream/specpilot-main.tar.gz` | 10,397,250 B |

```
tarball sha256 : 25e68b1b5985a7eb73c2423e7eac0f564030b8ab32b577b88bf23dc3d0602dd4
```

## 2. 规范化树哈希（canonical tree hash）

**定义**：避开运行时产物（`__pycache__/`、`*.pyc`），对全部源文件按相对路径
`LC_ALL=C sort` 后逐行输出 `"<sha256>  <relpath>"`，再对这份清单取 sha256。

```
manifest      : assets/upstream/MANIFEST.sha256   （3097 行，已入库）
manifest sha  : 4bca3c10479c4f920903edc4dfbe12ddbf4085dfb053fb76d10546653f81563f
```

复算（任意机器）：

```bash
cd /gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main
find . -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -printf '%P\n' \
  | LC_ALL=C sort \
  | while read -r f; do printf '%s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"; done \
  | sha256sum
# 期望 4bca3c10479c4f920903edc4dfbe12ddbf4085dfb053fb76d10546653f81563f
```

## 3. 已核对的事实

- tarball 解包后，**排除 .pyc 的 3097 个源文件与树上逐字节一致** → 两者是同一快照。
- 树里多出的 1069 个文件**全部**是 `__pycache__/*.pyc`（`PYTHONPATH` 直接指向上游 `python/`，
  首次 import 时生成的），不构成版本差异。
- 上游 README 自述 commit `78c42af`（取自 tarball 元数据/README，不是 git 事实）。

## 4. 只读边界（重申，`AGENTS.md` 铁律之外的补充）

| 路径 | 权限 | 原因 |
|---|---|---|
| `python/` | **只读，禁止阅读** | stock 引擎树；读了就等于抄实现，失去"独立复现"的意义。允许 `PYTHONPATH` 引用、允许跑。 |
| `settings/*/files/` | **只读，禁止阅读** | final 覆盖层源码，同上。 |
| `settings/*/config.json` | 允许读，已固定到 `assets/upstream/configs/` | 只含参数与开关名，不含实现。 |
| `research/bench/`、`research/scripts/` | 允许读 | 评测协议与启动口径，属于"尺子"而非"算法"。 |
| `scripts/` | 允许读 | 构建/服务/评分脚本。 |
| `overlays/`、`assets/` | 允许读 | 覆盖配置与数据清单。 |

## 5. 变更规则

- 上游树**永远不改**。要在引擎上做机制，走 `patches/` + option（`AGENTS.md` 第 3 条），
  在 `harness/build_engine.py` 组装的派生树里生效，派生树带自己的 content hash。
- 若上游被重新下载/替换，本文件与 `MANIFEST.sha256` 必须同步更新，并在 git log 里说明原因。

## 6. 派生引擎树（P1 产出）

上游树永远只读；真正跑的是 `harness/build_engine.py` 组装出来的派生树，位置：

```
/gpfs/users/jixinpeng/specpilot_data/work/engines/<setting>-{stock,final}
```

当前 `h100_c1_qwen38-27b_dflash2`：

| kind | tree sha（canonical content hash） | 覆盖层 | block |
|---|---|---|---|
| stock | `e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff` | 0 | 8 |
| final | `d406ba8183917674fffc083c67117a9c5e7b01a51da3620f5419638a7854f90a` | 49 文件（`int-015-tlvcbn32`） | 32 |

重建：

```bash
python3 harness/build_engine.py h100_c1_qwen38-27b_dflash2 stock /path/out
python3 harness/build_engine.py h100_c1_qwen38-27b_dflash2 final /path/out
python3 gates/g6_engine_build.py     # 6/6，重建出来的 sha 必须与上表一致
```

hash 定义与上游 `scripts/build_engine.py` 相同（`sha256` of canonical
`{relpath: sha256(file)}`，排除 `__pycache__`/`.pyc`），所以两边的 `TREE_SHA`
可以直接对比。**注意**：树上只有文件；final 的 46 个 `SPECPILOT_*` 开关与 block size
由 `harness/sglang/serve.sh` 以环境变量注入，改开关不会改 tree sha —— 配对测量时
必须把注入的环境一起记进测量记录。

## P3 补充：final 臂的 46 个 `SPECPILOT_*` 从哪来

`p3_pair.sh` 不手抄这些变量。`harness/sglang/gen_final_env.py` 读
`assets/upstream/configs/<setting>/config.json` 的 `final.env` + `final.block_size`
生成 shell export 文件（默认 `$SPECPILOT_DATA/work/env/<setting>-final.env`，**不进 git**），
生成后立刻 `--check` 回比，不一致就硬失败。

理由：抄错一个变量名不会被任何东西报错，只会让 final 臂悄悄跑成 stock，然后
"复现失败"却查不出原因。config.json 是唯一真源，派生文件必须可重生成。

## P3 补充：只跑 turn 0

上游 `bench.py --first-turn-only` 的等价做法。mt-bench 是 20/20 多轮，第 2 轮起的输入
依赖本臂自己的输出 → 三臂输入不同 → 配对失效。turn 0 的 `input_ids` 在三臂间按构造
完全相同，`run_arm.py` 落 `input_sha256` 供 `gates/g8_pair_arms.py` 证明这一点。

## P3 补充：AR 臂与 stock 臂的 token 差异不是 bug

烟测 5 条里只有 1 条 AR 与 stock 逐 token 全同（其余在第 3/135/160/237 个 token 分歧）。
两个原因叠加，都是预期内的：

1. 采样路径不同（AR 每步 1 个 token；spec 是 draft + batched verify），H100 上
   BF16 GEMM 的 batch 形状不同 → logprob 有 ~1e-3 抖动 → 近似并列的 argmax 会翻转；
2. 512 万 token 以内没有"标准答案"可比对。

所以 **lossless 不等于 AR 与 stock 逐 token 相同**。论文的口径是"greedy，且每个 token
由 target 模型判定"（README: *the target model decides every token*），
上游的对照是 `noop` 实验"必须与 stock token-identical"——即 **同引擎、同采样路径下
改 proposal 侧** 才要求逐 token 相同。跨采样路径的 lossless 只能靠
**token forcing**（把 stock 的 token 序列喂回去，检查每一步 target 的 argmax 是否等于该 token）
来证明，这条在 P4 建。
