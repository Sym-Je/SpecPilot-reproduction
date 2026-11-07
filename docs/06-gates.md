# 06 — 闸门实测记录

本文件只记录**跑过的**闸门结果与踩到的坑。未跑过的闸门不写在这里。

## G0 环境隔离 — 通过

- Node 24.22.2 装在 `~/.local/node24`，现有 v22.11.0 未受影响
- `dsh` 0.2.2-rc.1 装在 `~/.local/dsh`
- **坑**：`npm dist-tags` 里 `latest = 0.0.1-rc.1` 是旧列车，`next = 0.2.2-rc.1` 才匹配 CLI。
  不加版本号安装会拉错列车，运行时炸在 `ERR_MODULE_NOT_FOUND: @deepseek-ai/dsh-type-meta`。
  所有 `@deepseek-ai/*` 插件必须显式写 `@0.2.2-rc.1`。

## G1 goal 自驱多轮 — 待验证（阻塞）

依赖 NorthGate 网关。**2026-11-06 实测该域名从本机不可达**：

| 检查 | 结果 |
|---|---|
| DNS | 正常 `180.184.171.202` |
| 直连 443 | 超时（出网需代理） |
| 代理 `CONNECT` | `200 Connection established` |
| 隧道内 TLS | `UNEXPECTED_EOF_WHILE_READING`，对端立即关闭 |
| 同代理访问 npmmirror / baidu | 正常 |
| 同 IP 换 SNI 为 baidu | 握手成功 |
| 重试 4 次 + 观察 60s | 全失败 |

结论：非本地配置问题，是网关侧按 SNI 拒绝（或服务未起）。G1 在网关恢复前无法推进。

## G2 断流续跑 — 通过（6/6，本地 mock）

`python3 gates/g2_resilience.py`，mock server 在本地 8899，零外网零 GPU。

| 判据 | 结果 |
|---|---|
| D1 注入 500 后确实重试 | 共 4 次请求，第 0 次为 500 |
| D2 SSE 缺 `[DONE]` 被判定截断 | 客户端抛 Truncated，未当成功 |
| D3 重试后拿到完整输出 | `Hello from mock` |
| D4 副作用只执行一次 | idempotency key 出现 1 次 |
| D5 重试有上限 | 4 次封顶 |
| D6 指数退避 | 0.2 → 0.4s，总耗时 0.91s |

### 实现要点

1. **截断在 HTTP 层表现为两种异常**：`http.client.IncompleteRead`（chunked 编码未收尾）
   和自定义的「流结束但未见 `[DONE]`」。两者都必须归为可重试，否则半截响应当成功。
2. **重试必须配 idempotency key**。没有 key 就无法判断副作用是否已经发生过；
   SpecPilot 里对应的就是「一次测量只该记一条账」。
3. **超出范围的**：这验证的是「客户端 + 协议层」的续跑能力，不是 dsh 自身的续跑能力。
   dsh 在断流下是否自动 retry、checkpoint 是否落盘，仍需 G1 打通后在真实会话里观察。

## G3 controller 权限边界 — 通过（9/9）

`python3 gates/g3_isolation.py`：

| 判据 | 结果 |
|---|---|
| C1 agent 写 `ledger/`（direction / auditor） | EACCES |
| C2 agent 读 `eval/sealed/`（direction / auditor） | EACCES |
| C3 agent 写 `controller/` | EACCES |
| C4 direction 写 `scratch/` | 成功 |
| C5 controller 写账本 + 校验 | 通过 |
| C6 外部回改账本一条 | `verify()` 检出 hash 不符 |

### 实现要点（踩过的坑）

1. **bwrap 不可用**：内核禁非特权 user namespace，`bwrap` 直接报错。改用 **Landlock**（内核 5.15，ABI v1）。
2. **ABI 裁剪**：ABI v1 不认识 `MAKE_SYM`(1<<12)、`REFER`(1<<13)、`TRUNCATE`(1<<14)。
   `landlock_create_ruleset` 收到这些位直接返回 `EINVAL` —— 不是权限问题，是参数不合法。
3. **白名单语义**：给 `ROOT` 授权等于把 `eval/sealed` 也授了，**无法在子树上收回**。
   正确做法是逐项展开：子树内无 deny → 整目录授权；含 deny → 该目录只授 `READ_DIR`，
   再递归每个子项。`controller/landlock.py:grant_tree()` 就是这个逻辑。
4. **`prctl(PR_SET_NO_NEW_PRIVS)`** 必须在 `landlock_restrict_self` 之前调用。
5. **账本文件模式**：`0o444` 会让 controller 自己也写不进去（root 除外）。
   用 `0o644` + Landlock 做访问控制，而不是靠文件权限位。

### 已获得的保证

- agent 进程即使拿到 `python3 -c "open('ledger/x','a')"` 也物理写不进账本
- sealed 请求集对 agent 不可读 —— 不是约定，是内核拒绝
- 账本任何一条被回改，`verify()` 都能定位到 seq

## G6 派生引擎树可重现 — 通过（6/6）

`python3 gates/g6_engine_build.py`（纯 CPU，不碰 GPU）：

| 判据 | 结果 |
|---|---|
| E1 同输入两次构建 → 同一 tree hash | `e5472c4fbb6e6bf5` == 同一值 |
| E2 `kind=stock` 的 `python/` 与上游逐文件相同 | identical（0 差异） |
| E3 `kind=final` 与 stock 不同 | 49 个文件变了 |
| E4 改动全部来自 `settings/<setting>/files/` | clean（无夹带） |
| E5 树内无 `.pyc` / `__pycache__` | 0 |
| E6 dflash2 setting 不套 dspark overlay | 符合 |

### 为什么需要这道门

- **E1 是缓存的前提**：`serve.sh` 按 `TREE_SHA` 前缀分桶放 JIT / torch_extensions 缓存。
  hash 不稳定 → 每次启动都冷编译，一次 220 s 起步，配对测量直接废掉。
- **E2 是"默认=stock"的机器证据**：AGENTS.md 铁律 3 要求每个机制默认关闭且复现 stock。
  靠人读代码保证不了；靠"stock 树 == 上游树"这个等式才保得住。
- **E4 是防夹带的**：final 树只能由 `files/` 覆盖层产生差异。如果 final 树里出现
  `files/` 里没有的改动，说明组装逻辑自己改了什么 —— 那部分就没被 option 控制。
- **E5 是坑**：上游 `python/` 被 `PYTHONPATH` 直接 import 过，树里有 1069 个 `.pyc`。
  不排除它们，哈希会随"谁 import 过"变化，E1 假失败。

### 一个实现细节

覆盖层 `settings/<setting>/files/` 的路径是 `python/sglang/...` 同构的，
所以 G6 比对时必须把树内路径也统一成带 `python/` 前缀的形式；直接比
`root/python/` 下的相对路径会让 E4 全部误报"夹带"。
