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

## G2 断流续跑 — 进行中

本地 mock server 方案，不依赖外网。

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
