# SpecPilot 复现工程

复现 *SpecPilot: Autonomous Algorithm Discovery and Systems Optimization for Speculative
Decoding*（arXiv:2611.02501v1）的**架构与方法**，而非逐数字对齐。论文原件见
`docs/` 中的引用；PDF 不在仓库内。

## 这是什么

论文提出一个**逐部署自动发现投机解码优化**的 agentic 循环，并用它发现了四个
无损机制（W12 权重格式、混合目标 best-first 树、两级验证 TLV、批处理三件套）。

复现目标不是"重跑出 10.87×"，而是**重跑出这套循环**，使其在给定部署上自己找到
同等性质的机制。因此验收看的是循环的结构正确性（成本模型能否指出真瓶颈、评测器能否
判死自己），而不是单个加速比数字。

## 主线

单请求 × Qwen3.8-27B × DFlash2 × H100，三轮，目标 184 → 416 tok/s（2.13× over stock）。

选它的理由：唯一一条能同时覆盖 τ 因子（树）、kernel 因子（W12）、以及"改 ceiling 假设
本身"（TLV）三类的路径。其余部署作为**记忆迁移**验证，不重新发现。

## 文档

- `docs/00-architecture.md` — 论文骨架与五层系统架构
- `docs/01-message-protocol.md` — 四类结构化消息 schema
- `docs/02-acceptance.md` — 五级验收闸门与判据
- `docs/03-roadmap.md` — 前置门槛、路线与工作量估算
- `docs/04-paper-facts.md` — 论文关键数字速查（便于核对实现）

## 硬件前提

2×H100 80GB（本机已具备）。双卡是**硬性前提**：晋升判定依赖配对运行 + 互换 GPU，
单卡串行无法把噪声压到 0.1% 以下。

## 工作约定

见 `AGENTS.md`。
