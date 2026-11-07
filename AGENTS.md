# AGENTS.md — 本仓库的工作约定

本仓库用于复现 *SpecPilot: Autonomous Algorithm Discovery and Systems Optimization for
Speculative Decoding*。任何 agent（人或模型）在此工作都必须遵守以下约定。

## 铁律

1. **数字的生产权归 `controller/`。** agent 自报的加速比只是假设；进 `ledger/` 的必须是
   controller 在配对运行（双卡同请求、互换 GPU）后测出的区间。agent 不得修改 controller。
2. **`eval/sealed/` 只由 controller 在 Phase 4 加载。** agent 进程不得读取其路径，也不得
   用其内容做任何决策。
3. **一切变更走 option。** `patches/` 中每个机制必须由一个开关控制，默认值必须复现 stock
   行为。否则并行方向无法在同一条基线上比较。
4. **先写验收命令，再写实现。** 没有可执行的判据就不许开始改代码；判据由 controller 侧
   提供，实现者不能自己放宽。

## 目录职责

| 目录 | 谁写 | 内容 |
|---|---|---|
| `harness/` | 任何人 | server 启动、请求生成、交错跑、profiler、exact replay |
| `costmodel/` | cost model 角色 | byte/FLOP floor 表、三因子计算、方向 brief 生成 |
| `controller/` | **仅维护者** | 配对计时、晋升判定、token forcing、sealed 管理、账本写入 |
| `agents/` | 任何人 | master / direction / integration / kernel 的 prompt 与工具封装 |
| `patches/` | direction / kernel | 每个机制一个 option，default = stock |
| `memory/entries/` | controller（sealed 之后） | 结构化记忆条目 |
| `eval/` | 仅维护者 | dev / sealed 请求集，物理隔离 |
| `ledger/` | controller | 追加式测量记录，**只增不改** |

## 上下文纪律

长任务最容易死在上下文，而不是死在 token 上限：

- 大输出一律落盘，再用 `tail` / `grep` / 限定行数回读。不要 `cat` 整个 profile。
- 跨轮状态外置到文件：`ledger/` 记测量、`docs/` 记决策、本文件记约定。对话记忆不可靠。
- Git 必须追踪实验计划、版本身份、NorthJob 任务索引、验收与决策；执行规范和记录模板见 `docs/12-experiment-management.md`。原始产物持久存档并记录校验值，不以 Git 替代 controller 账本，不提交 sealed 或凭据。
- 每完成一步就跑一次验收命令，不要攒到最后。
- 每个大步骤执行前，先说明目标、主要流程与简要自检，得到用户允许后执行；阶段内小步骤自主安排，不另立主线。
- 用户已授权每完成一个大步骤后更新 README 的“已完成 / 正在做 / 接下来”和交接，验收后创建阶段提交并推送私有 GitHub origin；不自动创建分支、公开仓库或上传受限数据。

## 禁止

- 用单卡串行 A/B 冒充配对测量。
- 把"任务精度没掉"当作 lossless 的证据（见 `docs/02-acceptance.md` 的故障注入回归）。
- 把复用记忆条目算作新发现。
