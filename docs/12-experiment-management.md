# Git 全流程实验管理

日期：2026-11-07。用户要求：仓库不仅管代码，也要管理从计划到结论的整个实验流程。
本文件建立记录规范与当前索引；不代表 NorthJob 自动归档已实现，也不授权提交任务或修改 controller。用户后续已授权大步骤验收后提交 Git 并推送私有远端。

## 1. 单一入口和职责

- `HANDOFF.md`：当前状态、阻塞、下一步；新 session 从这里进入。
- `docs/11-reproduction-plan.md`：研究阶段、协议和停止规则。
- 本文件：流程管理规则、阶段索引。
- `docs/experiments/<experiment-id>.md`：每次实验的版本、任务、证据和决策；从 `TEMPLATE.md` 复制。
- `exp/`、`harness/`：执行单元；`controller/`：维护者负责的计时、正式判定和账本。
- 原始日志、JSONL、profile、源快照：持久存储，不强行加入 Git；记录精确位置、大小和 SHA-256。

Git 里的记录是实验索引，不是 agent 自己生产的正式统计结果或晋升账本。
私有 GitHub origin：`https://github.com/Sym-Je/SpecPilot-reproduction.git`。每个大步骤结束更新首页与交接，验收后阶段提交并推送；只有确认远端提交身份一致才算同步完成。不自动建分支或改变仓库可见性。

## 2. 每次实验的生命周期

1. **计划**：分配唯一 experiment-id，写目标、对照、请求协议、可执行验收命令、预先规定的判据和预算。
2. **冻结**：绑定执行代码、引擎树、配置、请求 manifest、模型身份和环境；不能只写一个 HEAD 来代表带未提交修改的代码。
3. **提交前确认**：按 northjob-submit skill 查重，展示完整命令与资源，确认具体 image；敏感值另行安全注入，不入 Git。
4. **提交**：追加 attempt-id、UTC 时间、返回码和 job_uuid。只有 code==200 且有 job_uuid 才记为 submitted，不记为实验通过。
5. **运行**：记录 started/failed/blocked 等状态、退出码和失败证据；返回不明确时先查任务，不盲目重提。
6. **测量归档**：核对请求和轮次完整、物理换卡、环境身份；保存原始数据、计算命令和统计输出的校验清单。
7. **验收与决策**：引用实际验收输出，区分诊断与正式结果、作者产物与独立发现；缺项或失败如实记录。
8. **交接**：更新阶段索引和 HANDOFF，标明下一步；经用户授权提交后才算进入 Git 历史，未提交时明确提示。

重跑保留 experiment-id 并新增 attempt-id；协议或实现改变则新建 experiment-id，链接旧实验。失败尝试不删、不覆盖成功记录，不静默续跑半轮。

## 3. 代码与产物可追溯要求

- 优先用确定的代码 commit 执行；未经授权不为冻结而自动 commit。
- 若使用未提交代码，必须打包实际执行源快照，包含跟踪文件修改和新增执行文件；记录基准 commit、变更清单、快照位置与 SHA-256。只有 diff 而漏掉新增文件不够。
- 验证远程实际加载的代码、引擎树和配置与冻结身份一致；本地 HEAD 不等于远程执行身份。
- image 记录用户确认的名称及可取得的不可变 digest；digest 不可取得时写明限制，不能伪称环境完全冻结。
- 记录目标/草稿模型 revision 或可用身份、数据 manifest hash、实际 GPU UUID/型号、软件版本与关键参数。
- 每个 attempt 独立输出目录，至少索引提交回执、环境 manifest、server 日志、逐请求原始记录、验收和统计输出。
- 任务退出前确认产物已写入持久存储。只在容器临时目录或 `/tmp` 的数据不算完成归档；后续使用前复核校验值。
- Git 中只记录脱敏摘要和证据引用，不提交密钥、sealed 内容或可泄露 sealed 请求的信息。sealed 结果仅引用 controller 允许公开的摘要/记录标识，不为归档读取受限产物。

## 4. 当前阶段索引

| 阶段 | 状态 | 已有证据 / 下一步 |
|---|---|---|
| mock 闭环与真实三臂 smoke | 历史阶段已验收，非论文数字复现 | `docs/06-gates.md`、`docs/09-p3-harness-validation.md` |
| 配对编排 | 完成；17/17 CPU/HTTP 回归，含真实 TIME_WAIT/live-listener 测试 | `exp/p3_pair_run.py`、`harness/test_p3_pair_run.py`；a05 远程生命周期通过 |
| 本机 AR/stock 尝试 | 历史 blocked；未启动测量 server | `logs/p3-local-ar-stock-20261107.log`；不是远程执行前置条件 |
| NorthJob 远程工具验收 | completed；a05 两轮换卡、10 pair/20 臂行、exit=0 | [最终验收及失败历史](experiments/p2-remote-smoke-20261107.md)；26 项回归、统计复算、33 文件校验与 GPU 清理通过，非论文数字 |
| A1：AR/stock | completed；点估计诊断通过，源 pin=79fe81a | [基线记录](experiments/p3-ar-stock-2048-20261107.md)；3.8699× [3.5571,4.2242]，40 pair/80 臂行、两轮换卡、39 回归及 38 文件校验通过 |
| A2/A3：AR/final、stock/final | completed；源 pin=4d67c2f，同 A1 请求身份 | [本阶段记录](experiments/p3-final-2048-20261107.md)；8.7347× [8.0235,9.5599] / 直接 2.2219× [2.1381,2.2988]；各 40 pair/80 行、50 回归及证据复核通过，非 sealed/lossless |
| B/C：正式 dev、真实正确性与裁判 | 待诊断及维护者工作 | 正式统计、噪声和 forcing 不以 mock 通过代替 |
| P4、真实 RSI 与最终对照 | 未开始 | 前置条件满足后按计划推进，agent 不接触 sealed |

上表引用的历史产物尚未在本次变更中补齐校验清单；不能称为已完成全量归档。

## 5. 管理机制的验收

文档验收命令（本次变更前已列出）：

```bash
git diff --check
git diff --exit-code -- controller
test -s docs/12-experiment-management.md && test -s docs/experiments/TEMPLATE.md
rg -n 'NorthJob|12-experiment-management' HANDOFF.md docs/11-reproduction-plan.md
```

后续每个实验单独提供执行验收。只有能沿“实验记录 → 实际代码快照 → job_uuid → 原始证据及校验值 → 验收输出 → 决策”完整追溯，才算该实验的记录闭环完成。
