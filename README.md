# SpecPilot 复现工程

复现 *SpecPilot: Autonomous Algorithm Discovery and Systems Optimization for Speculative
Decoding*（arXiv:2611.02501v1）的**自主优化闭环**，并独立验证性能；架构复现与数字复现分开报告。论文原件见
`docs/` 中的引用；PDF 不在仓库内。

## 当前进度（2026-11-07）

### 已完成
- mock 规模的闭环与验收骨架跑通。
- AR / stock / final 三臂真实 server 烟测完成，有原始记录。
- 双卡配对编排已实现，CPU/HTTP 测试 15/15 通过；真实配对测量尚未完成。
- GitHub 私有远端已创建并配置为 `origin`。

### 正在做
- 第 2 步：准备双卡测量工具的远程验收，调查合适镜像与 NorthJob 入口；**image 尚未确认，零次提交**。

### 接下来
1. 跑 AR vs stock：20 条请求、2048 token 上限、两轮换卡，校准基线。
2. 跑 AR vs final，再直接配对 stock vs final，验证作者方案收益。
3. 对齐正式统计协议，补齐真实正确性与噪声验收。
4. 前置验收通过后，推进真实自主优化闭环及 controller 管理的 sealed 验证。

**尚未独立复现论文数字。** 每个大步骤结束后更新本节，验收并创建阶段提交、推送到 GitHub；详细交接见 [HANDOFF.md](HANDOFF.md)。

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
