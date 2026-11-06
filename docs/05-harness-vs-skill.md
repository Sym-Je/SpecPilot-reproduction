# 05 — 编排层选型：Codex skill vs DeepSeek Harness vs 混合

> 状态：调研结论（未开始复现）。本文只回答"用什么东西把 RSI 循环跑起来"，
> 不涉及 SpecPilot 本身的架构（见 00）、验收（见 02）、排期（见 03）。

## 0. 结论先行

1. **这不是二选一。** dsh 的官方 bundle 里挂着 `dsh-subagent-codex`（通过 Codex
   app-server 协议，一次性子 agent）和 `dsh-subagent-claude-code`（通过 Agent SDK）。
   即：dsh 可以当宿主，把 Codex 当"编码工人"调进来。反过来 Codex 也能把 dsh 当 CLI 调。
2. **真正的选择不是"谁启动 agent"，而是"谁持有控制平面和审计账本"。**
   RSI 循环的命门是「数字生产权」「sealed 隔离」「跨轮存活」「全 trace」四件事，
   这四件都不是 prompt 能保证的，必须是进程边界 + 文件系统权限 + 事件日志。
3. **推荐：三平面拆分（方案 C）。**
   - 执行平面 → dsh（goal + round-driver + subagent）
   - 审计平面 → 独立 Python controller + dsh session JSONL/OTel（唯一裁判）
   - 策略平面 → SKILL.md（只写"怎么提案/过闸/写记忆"，不承担编排）
4. **skill 单独走不通**，但它必须存在——它是内容层，不是控制层。
5. 先过 G0–G5 六道闸门再谈复现；**G1 能证伪整个 dsh 路线，且零 token 零 GPU。**

## 1. 先厘清：我们在选什么

SpecPilot 的循环对基础设施提出的要求，可以直接从论文事实推出来：

| 论文事实 | 对基础设施的含义 |
|---|---|
| 486 变更 / 54 晋升 / 140 记忆条目 / 13 轮 | 需要可恢复的长程状态机，不是一次对话 |
| 164h wall / 530 GPU-h | 必须无人值守、可中断续跑、有预算闸 |
| 「controller 掌握所有测量，agent 只读数字」 | 需要 OS 级写权限隔离，不能靠约定 |
| sealed final 在轮末一次性使用 | sealed 目录必须对 agent 进程不可读 |
| 三轮瓶颈迁移靠 profile 归因 | 每条 proposal 必须能回溯到"哪次测量得出" |
| 附录 A3 的 15 次晋升链要能连乘核对 | 账本必须 append-only 且带证据指针 |
| 3 个 agent 并行、一方向一卡 | 需要程序化 fan-out，而非手点 |

把它压成 8 条判据：D1 权限边界、D2 trace、D3 无人值守、D4 并行编排、
D5 controller 集成、D6 成本/离线演练、D7 成熟度、D8 迁移成本。

## 2. 已核实的事实基础

```
@deepseek-ai/dsh  0.2.2-rc.1  MIT  90 个直接依赖  engines: node >=24.9.0
本机 node: v22.11.0 (/gpfs/users/jixinpeng/.local/node/bin/node)  → 不满足
```

存在**两条版本列车**（重要风险信号）：CLI/编排层发 0.2.2-rc.1，
而 base/插件层（dsh-base、dsh-goal、dsh-tool-subagent…）发 0.0.1-rc.1。
`dsh-experimental-*` 多为 alpha。含义：插件间接口仍在动，写 profile 要锁版本。

关键插件（逐个核实过存在与用途）：

| 插件 | 作用 | 对本项目 |
|---|---|---|
| `dsh-goal` | event-sourced 目标状态机 | 跨轮主状态 |
| `dsh-goal-round-driver` | idle + active goal → 自动排下一轮，带 reservation/revision fence | **命门** |
| `dsh-jobs-local` / `dsh-schedule` | 后台长任务注册表、定时 | northjob 轮询 |
| `dsh-tool-subagent` / `-control` | 前台/后台、one-shot/续接子 agent | 一方向一卡 |
| `dsh-experimental-agent-team-profile` | Lead + teammates，scoped 消息（alpha） | master/direction 角色 |
| `dsh-tool-workflow` + `dsh-workflow-ptc` | 用 JS 编排脚本程序化调度 | 批量评测扇出 |
| `dsh-tool-ralph` | fresh-agent 循环 | 可选：每轮新上下文防污染 |
| `dsh-session-persistence-jsonl` | 每条 session 事件落盘 | **trace 底座** |
| `dsh-session-projection` | 投影/重建会话视图 | 复盘、喂给 controller |
| `dsh-session-telemetry-otel` | session 记录 → OTel log pipeline（OTLP HTTP） | 导出到外部可观测性栈 |
| `dsh-experimental-inspector-profile` | 原始 session log 的可视化 | 人工排障 |
| `dsh-llm-replay` | 从 session JSONL 重建 chunk，短路 LLM | **零成本回归** |
| `dsh-llm-mock-server` | 可编程 OpenAI 兼容 HTTP/SSE 故障服务器 | 故障注入验收 |
| `dsh-skill` + `-filesystem` + `dsh-tool-skill` | dsh 自己有 skill 体系 | 可直接复用 SKILL.md 写法 |
| `dsh-mcp-client` | 接 MCP | 复用现有工具 |
| `dsh-subagent-codex` | 一次性 Codex 子 agent（app-server 协议） | **保留 Codex 编码力** |
| `dsh-subagent-claude-code` | 一次性 Claude Code 子 agent（Agent SDK） | 备选工人 |
| `dsh-fs-policy` / `dsh-permission` / `dsh-sandbox-policy` / `dsh-user-approval` | 权限与沙箱策略 | **D1 的落点** |

LLM seam 是 provider-neutral（`dsh-llm`），适配器有 `dsh-llm-deepseek`、
`dsh-llm-pi-ai`（设计验证孪生）、外加 replay/mock 两个离线实现。
接第三方 OpenAI 兼容端点需要自己写一个薄适配器，工作量约一天。

## 3. 判据 × 方案

### 3.1 方案 A：纯 Codex skill 编排

做法：写一个 `specpilot-rsi` skill，规定"每轮先 spawn 3 个 direction agent，
各自 worktree、各自 northjob 提交、回报后主 agent 汇总"，验收脚本当 skill 资源。

优点：
- **今天就能跑**，零基础设施。`spawn_agent` / `create_worktree` / NorthJob skill 都已在手。
- Codex 的编码与工具使用能力是最强的部分，直接复用。
- 单一信任域：用户已经在这里，配额和权限都清楚。

硬伤（逐条对判据）：
- **D1 弱**：sandbox 只有 workspace-write 这一档粗粒度。sealed 可以靠"放到 writable roots
  之外"做到不可读，但 **ledger 的写权限仍在 agent 手里**——"controller 是唯一写入者"
  只能靠 prompt 约定，而 RSI 循环里恰恰有 54 次晋升，任一次被 agent 顺手改了，
  整轮论证就废了。这是架构性缺陷，不是调参能补的。
- **D2 弱**：无 session 导出接口。trace 只能靠"我读 thread"或用户看 UI，
  无法程序化喂给 controller，也无法在 164h 后回溯"第 7 轮为什么放弃那条方向"。
  这正是用户说的"依赖封闭 codex"。
- **D3 弱**：每轮结束就交回用户。要么我连续跑（受单条消息时长与上下文限制），
  要么外层 shell 循环重启（丢上下文，且 compaction 不透明、可能悄悄丢掉账本要点）。
- **D4 中**：子 agent 有并发上限，且**无程序化编排脚本**——"4 目标 × 3 drafter ×
  2 GPU × 5 benchmark"这种笛卡尔扇出要靠对话逐条写，易漏易重。
- **D5 弱**：没有对外 RPC。controller 无法作为父进程驱动它、无法逐事件记账。
- **D6 弱**：每次验证都真烧 token，无 replay/mock。

### 3.2 方案 B：纯 dsh

做法：`dsh --profile headless` 起一个 goal，round-driver 自驱 13 轮，
worker 用 dsh 自己的模型，controller 作为外部进程。

优点：D2/D3/D4/D5/D6 全部为强。goal-round-driver 的 reservation + revision fence
正是"无人值守跨轮"需要的语义；JSONL 落盘 + OTel 正是"看得到整套 trace"。

硬伤：
- **D7 风险**：rc/alpha 遍地、两列版本、Node 24 硬门槛、社区小、文档密度低。
  出了诡异 bug 大概率要读它的 cordis 插件源码自己修。
- **D8 中高**：要学 cordis 的 profile patch 机制，把 NorthJob skill 改写成 dsh-skill
  形态，还要薄写一个模型适配器。到"能跑通 G2"约 1–2 天。
- 编码能力取决于挂哪个 worker 模型；如果为了它放弃 Codex，是净损失
  ——但这恰好**不必发生**（见方案 C）。

### 3.3 方案 C：三平面混合（推荐）

```
┌─ 策略平面 SKILL.md ──────────────────────────────┐
│  propose 怎么写 / 过哪道闸 / 记忆条目 schema    │  ← 纯文本，可版本化，人也读得懂
└──────────────────┬───────────────────────────────┘
                   │ 注入 system prompt（dsh-skill）
┌─ 执行平面 dsh headless ──────────────────────────┐
│  goal(13 轮) ← round-driver 自驱                 │
│  ├ direction×N  (dsh-tool-subagent / team)       │
│  ├ 编码落地    (dsh-subagent-codex, 保留 Codex)  │
│  └ northjob    (bash 工具 + northjob-submit)     │
│  session JSONL ──┬─→ controller（逐事件）        │
│                  └─→ OTel/OTLP（外部观测）        │
└──────────────────┬───────────────────────────────┘
                   │ JSON-RPC over stdio (--profile sdk)
┌─ 审计平面 Python controller ─────────────────────┐
│  唯一有权：配对计时 / 晋升判定 / token forcing   │
│            写 ledger / 读 sealed / 熔断          │
│  沙箱外的独立进程，agent 无法 import 也无法写    │
└──────────────────────────────────────────────────┘
```

为什么这么切：

- **controller 不属于任何 agent 框架。** 它是普通 Python 进程，两边方案都要它。
  把它抽出来，选型风险就被隔离在"可观测性"和"调度"上，损失可控。
- **skill 降级为策略手册。** 理由很硬：skill 是 prompt 包，不能强制边界
  （D1）、不能在 12h 无人值守中存活（D3）、不能保证 trace（D2）。
  它是"内容"，不是"控制"。但它必须存在——proposal 的写法、记忆条目 schema、
  闸门顺序这些是真正需要人反复打磨的资产，且 skill 形态可被 Codex 和 dsh 同时消费
  （dsh 自带 `dsh-skill` + `dsh-skill-filesystem`，格式兼容）。
- **执行平面留 Codex 接口。** 通过 `dsh-subagent-codex`，需要强编码时把 Codex 拉进来；
  不需要时纯 dsh 更快更省。这是可替换的，不是架构决策。
- **trace 落在 dsh 里而不是 Codex 里。** 用户的核心诉求是"不依赖封闭 codex 也能看到
  完整 trace"，方案 C 把 trace 的所有权移到了 JSONL + OTLP，Codex 只是被调用的工具，
  它内部黑箱不再影响可审计性。

### 3.4 对照表

| 判据 | A 纯 skill | B 纯 dsh | C 混合 |
|---|---|---|---|
| D1 数字生产权/sealed | ✗ 约定级 | ✓ 策略插件级 | ✓✓ controller 进程级 |
| D2 全 trace | ✗ 无导出 | ✓ JSONL+OTel | ✓✓ 同上 + controller 事件账本 |
| D3 无人值守跨轮 | ✗ 每轮停 | ✓ round-driver | ✓ round-driver |
| D4 并行扇出 | △ 对话式 | ✓ 工具+workflow 脚本 | ✓ 同上 |
| D5 controller 集成 | ✗ 无 RPC | ✓ JSON-RPC stdio | ✓✓ |
| D6 离线演练/故障注入 | ✗ | ✓ replay+mock | ✓✓ 正好承载 §2.2 验收 |
| D7 成熟度 | ✓ 生产 | ✗ rc/alpha | △ 风险被 controller 隔离 |
| D8 上手成本 | ✓ 零 | ✗ 1–2 天 | △ 先 A 后平滑迁移 |
| 编码能力 | ✓✓ 最强 | △ 看挂谁 | ✓✓ 可挂 Codex |

## 4. 分阶段路线：先 A 后 C，而不是一步到位

不必立刻押注 dsh。**A 是 C 的真子集**——skill 文本、验收脚本、controller、
sealed 目录布局在 A 阶段全部要写，且 100% 可迁移到 C。差别只在"谁驱动下一轮"。

- 阶段 α（1–2 天，纯 A）：写 skill + controller 骨架 + 闸门脚本，跑通**一轮**
  的 propose→implement→measure→judge，全在 dev 集，人工点"下一轮"。
  此阶段不碰 GPU 也行（用 `dsh-llm-replay` 的等价物：录好的 replay 文件）。
- 阶段 β（G0–G2）：起 dsh，把"人工点下一轮"换成 round-driver 自驱，
  先 replay 后真 provider。**trace 与自动续轮在这里被验证或证伪。**
- 阶段 γ（G3–G4）：controller 以 stdio 接管裁判权，接 NorthJob。
- 阶段 δ（G5+）：三轮真实循环，对照论文的瓶颈迁移。

这样即使 dsh 在 β 被证伪，α 的产出全部保留，退回 A 也能继续（只是人肉点下一轮）。

## 5. 六道闸门（"先不复现"阶段该做的事）

| 闸 | 验证什么 | 成本 | 失败意味着 |
|---|---|---|---|
| **G0** | 隔离装 Node 24，`dsh --help`，不动现有 v22 | 10 min | 环境不可行 → 放弃 B/C |
| **G1** | headless 下一个 goal **自动跨 3 轮**（`dsh-goal-round-driver` 真工作） | 0 token 0 GPU | **dsh 路线作废**，退回纯 A |
| **G2** | mock-server 注入 SSE 断流/500，看 retry+checkpoint+compaction 能否续上 | 极低 | 无人值守不可靠 |
| **G3** | controller 经 stdio 驱动；agent 试图写 ledger / 读 sealed **必须被拒** | 零 | 架构复现失去意义 |
| **G4** | dsh bash 工具内 `northjob` 提交 5 分钟 job 并回读日志 | 小 | 接不了真实 GPU |
| **G5** | 真 provider 三轮玩具循环：propose→patch→measure→judge，trace 可导出 | 中 | 回到 α |

G1 是关键：它用**零成本**回答"dsh 到底能不能自驱多轮"。round-driver 是 0.0.1-rc.3
的独立小包，语义是"idle + active goal → 排下一轮，带 reservation 与 revision fence"，
但**没有实测过**。这是整个选型里唯一无法从文档判断的东西。

## 6. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| dsh 版本列车分裂（0.2.2 编排 / 0.0.1 插件） | 升级即破 | 锁版本，profile 与 lockfile 一起进 git |
| `experimental-*` alpha 接口变动 | team profile 不可靠 | 只用 `dsh-tool-subagent` 稳定面 |
| Node 24 与现有 v22 冲突 | 影响其它项目 | 装到 `~/.local/node24`，只在 dsh 启动脚本里 PATH 前置 |
| round-driver 有 bug | B/C 不成立 | G1 先证；失败退回 A，损失为 0 |
| compaction 静默丢账本 | 判断漂移 | 账本外置到文件，每轮开头从文件重建而非从上下文 |
| dsh 的 LLM 适配器需自写 | 半天 | 优先 `dsh-llm-replay` 走完 G1–G2，真模型后置 |

## 7. 需要用户拍板

1. **接受 rc/alpha 风险吗？** 我的建议：接受。因为裁判权在独立 controller，
   dsh 挂了只损失"自动续轮 + 可观测性"，不损失正确性。
2. **Node 24 装哪？** 建议 `~/.local/node24`，不覆盖现有 v22。
3. **worker 用谁？** 建议默认 dsh 自驱，重编码任务经 `dsh-subagent-codex` 转 Codex。
4. **论文资产可得性**（Qwen3.8-27B / DFlash2 / SGLang v0.5.20）仍未确认，
   这决定 G5 之后是"架构复现"还是"含数字复现"。不阻塞 G0–G4。

## 8. 一句话

用 dsh 换掉的不是 Codex，是**"Codex 的对话界面当调度器"这件事**；
用 skill 保住的不是编排，是**"这个循环该怎么想、怎么判、怎么记"这件事**。
