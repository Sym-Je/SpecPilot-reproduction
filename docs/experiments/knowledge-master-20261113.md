# 研究知识包与Master自主方案

## 目标与范围

用户批准先补研究先验，使Master能自主比较投机机制、交付正确性与完整成本路径明确的首版。不是继续当前已停止的单叉eager实现，不预定新树/长度/kernel或正收益。
本阶段0GPU/NPU、0NorthJob/模型server、不派Direction、不改引擎/controller/规则/账本、不读sealed/凭据/作者final实现。
基准e83754e；唯一原始证据目录`logs/knowledge-master-20261113-a01/`。保留62份旧工作，原始论文/源码/trace不随摘要公开。

## 工作流程

1. 核对附带SpecPilot论文与可获取公开材料中memory、初始化和轮次的陈述，分别标注原文事实、缺失证据和推测，不把140条累计memory当成初始化答案库。
2. 建立四维可检索机制卡：长度/动态预算、候选选择/树、混合递归状态正确性、kernel/端到端成本。记录来源、版本/定位、条件、收益依据、新增成本、风险、最小验证。
3. 原生Master实际读资料、授权stock和历史dev反馈，自主补证据、比较至少两个候选，再确定可交Direction的首版。
4. 方案明确算法/伪代码、参数/调用点、default-stock option、状态不变量、条件端到端收益/unknown、正确性/性能协议、最小证伪及停止条件；不把核心设计交给用户逐项引导。
5. 维护者独立复核来源与CPU重放，不代写科学答案；有缺口退回同一Master修订，不以字段齐全或CPU通过当GPU结果。
6. 角色退出、保护文件和旧工作保留验收，私有归档，公开脱敏知识与进度，精确提交推送；任何后续实现/GPU阶段另行规划授权。

## 知识与证据纪律

外部论文和实现是未在本机验收的先验，不写`memory/entries/`，不冒充可重建的已验证机制。历史stock和上一轮自研候选明确标记共享复用，不包装为新发现。
本阶段不是有/无知识的随机对照，不能从一次方案得出“知识注入已因果提升Master能力”；也不能断言论文第一轮从零独立发明或主要依靠预置答案。
原生Master使用默认继承模型、不继承旧对话；平台审批不变，禁区仅prompt约束，文件SHA检查不证明从未读取。

## 先行验收

`ACCEPTANCE.md`先于研究实现固定。入口命令：
```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native
$PY -B -m harness.master_native check --directory logs/knowledge-master-20261113-a01
$PY -B logs/knowledge-master-20261113-a01/audit.py
```
来源/结构检查不替代科学判断；Master自行先写CPU判据再实现分析，维护者用独立副本重放。

## 交付与知识接入

原生Master Volta以新线程、继承模型/父工具执行；没有旧对话，历史材料明确共享复用。最终交付论文审计、9张机制卡/40项来源、实际查询/源码读取回执、4方向比较、首版设计、自审与CPU证据。主助手只维护工具与独立复核，未代写科学方案。
公开知识入口：[投机解码研究知识包](../knowledge/speculative-decoding/README.md)。公开22项外部来源和9张脱敏卡，保留来源revision/SHA/定位；本地stock/诊断身份及原始下载/完整日志私有归档，不是40篇论文。
`agents/master_native.md`已增加按需查询索引的约定，不把全部资料一次塞入上下文，不以索引代替读对应源码，更不将外部卡写入可信memory。

| 维度 | 卡数 | 主题 |
|---|---:|---|
| length_budget | 3 | 固定长链、置信停止、接受反馈预算 |
| candidate_tree | 2 | EAGLE-2上下文树、Sequoia硬件/成本选形 |
| recurrent_state | 2 | SSM/conv/KV完整状态、GatedDelta分块/路径顺序 |
| kernel_e2e | 2 | 固定形状CUDA Graph、完整成本/临界路径 |

Master实际执行四类卡片查询，并读取固定版本实现和授权stock；卡片的条件、风险和成本进入方案比较，不是结尾仅声称“用了资料”。具体查询、读取文件、行定位、SHA和HTTP/CPU退出码在knowledge-use/read-evidence/receipts中。

## 论文事实核对

附带23页PDF SHA为`b495e50a886acaa7ead1ef29712a76dc2e5213b3999a3d0d5987c063ca06677f`，与公开arXiv 2611.02501v1交叉核对；作者项目只读固定README和无源码的版本元数据，不读取final实现。

- §3.4（PDF第7页）明确：sealed final后将晋升机制整理为包含依赖代码delta、变体、正确性契约、option、证据/限制的条目；跨deployment复用要重调/重测，不算新发现。
- 140是论文报告时的累计条目数，不是首次运行预置140个答案的证据。在所读PDF/公开正文/作者README中未找到初始逐条清单和全部调用级轨迹；不据此断言材料不存在。
- Table A4（第21页）H100单请求首轮包含**26次变更、4次晋升、11.7小时、28.3 GPU小时**，所以“一轮”不是一次模型回答或一次实验。
- Appendix D（第22页）报告13轮、486次变更、54次晋升、164小时、530 GPU小时。没有知识有/无对照，不能把作者成功或本轮方案归因到预置memory。

## Master自主比较与选定首版

| 候选 | 当前判断 |
|---|---|
| 固定长链12，随后有条件16 | 现有override/setter提供最小取证入口，减少新树状态耦合；选择有界诊断，不保证收益 |
| 并行draft8后的置信前缀预算4/6/8 | 需本地校准、verify长度成本和shape处理；不能照搬串行assistant节省draft计算的论证 |
| 前缀闭合、parent-conditioned的16节点树 | 旧深度7条件接受量有空间，但完整状态/graph/调度成本未证；不复活旧eager实现，也不否定所有树 |
| recurrent/chunk或kernel融合 | 缺完整临界路径暴露，不能把kernel work合计当可省墙钟，暂后置 |

选择首版`D1-chain12-bounded-diagnostic`，核心参数/算法已确定，但**不支持直接实施整引擎**：

1. 未来option `lookahead_study=off|chain12|chain16`，默认off不改变传入stock参数；当前基线B=8，B含anchor，第一探针12，16仅条件扩展，未实现runtime wrapper。
2. 每个fresh server生命周期固定一个B，不逐步切换，不改变精度、接受规则或额外引入树。stock worker解析B并调用模型setter，传播到所有非空conv；CPU stub验证不等于真实图/池/checkpoint可运行。
3. 接受j个draft后，发出j个draft加target bonus；状态提交到输入索引j，即anchor加j个已处理draft之后。新bonus尚未作为target输入处理，下轮才作anchor。所有SSM/conv/KV/hidden必须保持同一前缀，不泄漏拒绝尾部。
4. 未解决shape/状态错误就停止诊断；不能在可能已污染状态的step中隐式切B继续。未来恢复须新进程off-stock，默认off不得增加hook/分配/同步。
5. 下一阶段取证顺序是默认8身份→固定12配置/池/图→同前缀完整状态/拒绝边界→独立token forcing→未profile的2048配对成本；只有12可解释才考虑16。任何GPU/实现需另行规划授权。

排序依据是**取证成本和可解释性，不是已测收益排名**。尚未知checkpoint长块proposal质量、U12/C12、真实状态/图支持、2048收益；不能靠补资料承诺优化成功。

## 条件收益与CPU证据

同轨迹稳态假设下，净吞吐比为`R=(U_B/U_8)/(C_B/C_8)`；完整C包括draft/head/verify/accept/状态与KV整理/host/graph，完整请求还含prefill/tail。3%仅作研究情景，不改controller阈值。
旧匹配cohort深度7的16节点条件进度比约1.164613；若假设希望3%净收益，允许完整step成本比须小于约1.130692。这是成本边界，不是树实测加速，也不能推到深度11/15。
BBuf实际CPU工具初次默认TP/EP=8且无context，不适配当前单卡；Master保留原结果，用独立v2显式TP=DP=EP=1、context2048、全行logits重算。8/12/16行约410.853/616.289/821.732 GFLOPs，**没有测得延迟/MFU，不能按比例推出墙钟**。
完整SSM快照的条件容量算术为144MiB/位置/请求（48层×48 value heads×128×128×4字节）；从8到12额外576MiB，不含其他buffer。真实layout/liveness仍须核对，不用这项算术证明无空间。
CPU实际覆盖setter的8/12/16传播、37个accept位置的有理数状态oracle、flatten-sibling和SSM-only rollback故障注入、bonus延迟、成本反例及知识查询；均不证明真实模型正确。
维护者从独立目录重放frontier、修正BBuf和tie反例三脚本，stdout逐字节相同；并独立复算条件边界、抽查论文原文/stock调用点。角色自己的副本重放与维护者复核分开记录。

## 来源审查与失败

来源抽查发现T1最初将“平分时浅层优先”与实现保证混写。Master自主确认EAGLE-2论文明确该策略，但所读固定版本cnets使用topk后排序/searchsorted，未见显式depth tie guard；PyTorch文档也不保证tie索引稳定。已修订卡片，区分论文、代码、本地建议和unknown，并保留旧版。
抽象反例只表明合法tie选择可能缺parent、searchsorted不是membership证明；本机未执行Torch topk或复现真实EAGLE bug，不能扩张结论。
匿名API限流403、博客TLS、猜错路径/annotated-tag导致404、Sequoia LICENSE路径404均保留。采用合法匿名git ref/固定SHA raw替代；许可未知不移植源码，不把工具故障当算法反证。
一次维护者只读检查审批服务超时未执行，按工具提示重试一次成功；不放宽平台权限。初次BBuf配置错误虽exit0仍不作为本地适用证据。

## 验收、收尾与未完成项

4项Master入口及12项来源审计正反例通过，共16项指定回归，不代表全仓全绿。最终阶段审计通过：62份旧工作/授权输入/PDF身份和controller/ledger/指定规则未变；原生Master已关闭。
本阶段0GPU/NPU/NorthJob/server，不派Direction，不写引擎实现或可信memory。文件快照不能证明从未读取禁区；知识包完成不证明模型能力的因果提升。
未完成：真实长块proposal与完整状态/forcing、U12/C12、2048双卡性能、可晋升优化、完整RSI/论文数字。下一阶段仅建议另审Direction最小真实取证，不自动执行或结转旧资源。
原始产物私有持久归档，位置/SHA/文件清单见archive-receipt/evidence-manifest；公开8文件仅知识摘要、来源元数据、Master索引和进度，不含原始stock/论文全文/trace/sealed/凭据。提交及GitHub身份以publication.json为准。
