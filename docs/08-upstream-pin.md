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
