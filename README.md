# SpecPilot 复现工程

复现 *SpecPilot: Autonomous Algorithm Discovery and Systems Optimization for Speculative
Decoding*（arXiv:2611.02501v1）的**自主优化闭环**，并独立验证性能；架构复现与数字复现分开报告。论文原件见
`docs/` 中的引用；PDF 不在仓库内。

## 当前进度（2026-11-07）

图例：✅ 已完成 · 🟡 初步完成 · 🔵 正在推进 · ⬜ 待完成。只有完成该阶段验收才标 ✅。

| 步骤 | 主线任务 | 状态 | 已有进展 / 待完成项 |
|---|---|---|---|
| 1 | 明确复现对象与实验协议 | 🟡 初步完成 | 已区分 dev / sealed 与诊断 / 正式统计，见[协议规划](docs/11-reproduction-plan.md) |
| 2 | 双卡配对测量自动化与远程验收 | ✅ 已完成 | a05 两轮真实换卡，10 pair / 20 臂行，exit=0，GPU 清理通过；26 项回归通过，见[验收记录](docs/experiments/p2-remote-smoke-20261107.md) |
| 3 | AR vs stock 基线测量 | ✅ 诊断通过 | stock/AR 3.8699×，95% CI [3.5571, 4.2242]；40 pair / 80 臂行、两轮换卡通过，见[验收记录](docs/experiments/p3-ar-stock-2048-20261107.md) |
| 4 | 验证作者 final 的收益 | ✅ 产物测量完成 | final/AR=8.7347× [8.0235,9.5599]；直接 final/stock=2.2219× [2.1381,2.2988]，见[验收记录](docs/experiments/p3-final-2048-20261107.md) |
| 5 | 真实正确性、噪声与晋升判据 | 🔵 基础已修，真实噪声未过 | [修复/校准](docs/experiments/p5-controller-repair-20261107.md)：9反例/79测试通过；[只读噪声诊断](docs/experiments/p5-noise-diagnosis-20261107.md)完成，根因仍待受控验证；真实 forcing 未完成 |
| 6 | 建立独立 sealed 验证 | ⬜ 未开始 | 前置验收通过后由 controller 管理，agent 不接触内容 |
| 7 | 真实 profiling 与成本模型 | ⬜ 待补齐 | 简化骨架已有，真实耗时分析与成本模型待接入 |
| 8 | agent 自主提案与实现 | ⬜ 待真实自主搜索 | 需独立提出优化并实现为可开关 option，默认保持 stock |
| 9 | 多轮真实优化闭环与记忆 | ⬜ 待真实验证 | [mock 闭环](docs/06-gates.md)已跑通，不代表真实引擎闭环完成 |
| 10 | 对照实验与最终报告 | ⬜ 未开始 | 分析各组件贡献，分别报告架构与数字复现证据 |

**已完成：**配对工具、AR/stock 基线及作者 final 的 dev 子集测量。直接 final/stock=2.2219×，95% CI [2.1381,2.2988]；两项 final 实验各 40 pair/80 臂行、两轮换卡、exit=0、GPU 清理通过，50 项回归及证据复核通过。

**当前边界：**20 请求、2048 上限、自然 EOS 的 dev 子集；平均输出 AR 999.0、stock 1012.5、final 965.075 token。是作者产物验证，不是论文完整 dev/sealed、lossless 或自主发现结论；不能拿本结果宣称 sealed 2.13× 已复现。

**正在做：**第 5 步[稳定化复验](docs/experiments/p5-stable-null-20261107.md)已获批准：固定全尺度预热、每会话4轮GPU×端口交叉、平衡发起顺序并记录CPU/GPU状态。新旧91测试通过，正冻结代码准备两会话实测；旧失败证据保留。

**接下来：**自主执行已批准的稳定化大流程，核对两会话精度与偏移，不删样本/挑会话、不放宽<0.2%要求。真实 FP32-head scorer、delta 与故障注入仍待补齐，不进入 sealed 或 RSI。

**已有基础：**三臂真实 server 烟测与 mock 闭环完成，GitHub 私有远端已配置；**尚未独立复现论文数字。**

每个大步骤结束后更新本看板、附上验收结果链接，创建阶段提交并推送到 GitHub；详细交接见 [HANDOFF.md](HANDOFF.md)。

## 这是什么

论文提出一个**逐部署自动发现投机解码优化**的 agentic 循环，并用它发现了四个
无损机制（W12 权重格式、混合目标 best-first 树、两级验证 TLV、批处理三件套）。

复现目标不是"重跑出 10.87×"，而是**重跑出这套循环**，使其在给定部署上自己找到
同等性质的机制。因此验收看的是循环的结构正确性（成本模型能否指出真瓶颈、评测器能否
判死自己），而不是单个加速比数字。

## 主线

单请求 × Qwen3.8-27B × DFlash2 × H100 × SGLang v0.5.20；后续统一通过 NorthJob 执行。
先校准与验证作者方案，再推进自主发现；2.13× [2.07, 2.19] 是论文 sealed 参照，不是当前实测结果。

选它的理由：唯一一条能同时覆盖 τ 因子（树）、kernel 因子（W12）、以及"改 ceiling 假设
本身"（TLV）三类的路径。其余部署作为**记忆迁移**验证，不重新发现。

## 文档

- `docs/00-architecture.md` — 论文骨架与五层系统架构
- `docs/01-message-protocol.md` — 四类结构化消息 schema
- `docs/02-acceptance.md` — 五级验收闸门与判据
- `docs/03-roadmap.md` — 前置门槛、路线与工作量估算
- `docs/04-paper-facts.md` — 论文关键数字速查（便于核对实现）

## 硬件前提

正式配对测量按现行协议申请 2×H100 80GB，并交换 GPU；不再等待本机 GPU 释放。
NorthJob 提交前必须确认 image，不能以单卡串行结果冒充正式配对测量。

## 工作约定

见 `AGENTS.md`。

## 接手：先读 HANDOFF.md

新 session / 新维护者从 [`HANDOFF.md`](HANDOFF.md) 开始。它记录当前卡点、环境事实、
已验证结论和下一步路线，取代任何口头交接。
