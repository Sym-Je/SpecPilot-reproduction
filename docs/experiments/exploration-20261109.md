# 首轮真实agent探索：证据到候选提案

日期：2026-11-09（北京时间，机器日志保留UTC）。基准`6561e40122958b5f0e49b06c85cfea907faf26e7`。
状态：工程接入与首轮证据分析已验收；科学结论`needs_more_evidence`，尚无可实施候选。
不预设VERIFY、不实施候选、不提交GPU或晋升；架构进展不等于论文数字或方法结论复现。

## 目标与边界

接入真实LLM master/direction决策，替代本轮对固定registry的依赖，但不改旧mock入口或controller。
本阶段终点为有来源/可执行下一验收的候选提案、有实验依据的方向关闭，或明确缺证据的待测结论。
第三种不是成功发现、也不是已淘汰；不能为完成阶段强编净收益≥3%。
不承诺本轮发现论文相同机制，不向agent提供作者final实现、已知机制列表、旧对话或固定答案。

使用当前会话的真实子agent工具后端，fresh context，继承用户默认模型，不擅改模型。
仓库管理证据包、提示、请求/响应、CPU工具、预算和审计；模型推理由外部工具后端执行，不伪称仓库内有独立LLM服务。
后端未暴露精确模型ID、用量或内部执行轨迹时，记录null与限制，不能冒充已冻结的论文agent配置。
只记录工具可见轨迹，不要求或记录模型隐藏思维链；响应回执是客户端证据，不是后端签名。
fresh prompt不继承本聊天历史。子agent仅处理提供的JSON，不调用文件/网络/终端或再分派；
这属于上下文/工具使用约束，不冒充Landlock文件系统物理隔离。原始题目、输出、sealed均不提供。

## 先写验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p13_exploration
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
git diff --exit-code 6561e40 -- controller orchestrator patches costmodel assets/upstream ledger memory
git diff --check
```

本地工程接口检查，不修改论文T1/T2：
- 证据白名单/源码hash/部署身份绑定；不读final段，不抄既有prompts的指定机制或registry。
- 没有模型响应即无提案；测试fixture不得标真实后端。模型回包必须绑定issued request hash和真实agent ID。
- master独立选择最多2个方向；direction请求最多2个白名单CPU实验。禁止任意shell/GPU/源码读取；未知工具显式拒绝。
- 数字分清kernel工作份额、局部反事实与端到端收益，缺因子保持null；不以89.6%直接推出加速空间。
- option默认值必须复现stock，提出方案不是实现完成；当前implementation_ready固定false。
- 每项事实引用E编号或实际CPU结果T编号；假设/成本未知必须明示，关闭方向需引用实际实验而非“数据缺失”。
- 记录真实prompt/raw response/transport回执/工具结果，独立重放审计两次；默认promoted=false、ledger_eligible=false。

## 执行流程

1. 从stock配置与已公开的profile/计数/线性重放聚合构造证据包，不读取私有逐题数据或作者实现。
2. fresh master选择方向；master推理同时本地完善审计/日志，不手工替其补结论。
3. fresh direction只接master选出的任务与相同证据；按其请求执行安全CPU算术，再交回同一agent继续判断。
4. master收齐结果，决定提案/关闭/待测。缺净headroom证据时不动手实现；GPU需求只列预算等待下一阶段批准。
5. 两次CPU审计、证据SHA、README/交接/阶段提交推送；不开始完整RSI或sealed。

## 预声明限制

成本因子仍不完整；只允许已有线性链/公开聚合支持的局部算术，不将其当tau_best或完整反事实生成。
模型可能有训练期先验，不能证明首次发现或排除所有已知解知识；只能追踪本次输入未提供作者答案。
单轮、少量方向不证明搜索方法优于基线，也不等同于论文多轮自主优化结果。

## a01：真实agent指出证据接口不足

- 源码pin=`8195964504809528ced509260268f1d3da82afe8`，tar SHA=
  `df438f2b3f7b5dff3f9c3f799bf539e0abfe0504e4f592b5dbd5224acbd4dda2`；9定向/219总回归通过。
- fresh master自行选择接受历史驱动块长、终止overlap关键路径两个方向；没有硬指定VERIFY。
  两个fresh direction均拒绝把现有3个CPU算术工具当相关实验，tests=[]、结论needs_measurement。
  没有净headroom、没有候选实现依据，不把“数据不足”说成方向已关闭。
- 两个agent自行请求的最便宜证据分别为：按独立请求分组的有序接受序列与整请求留出预测审计；
  终止判定/worker执行/提交的可关联顺序。先保存a01完整响应与审计，再补接口，不改写原回答。

## CPU接口补齐的预声明验收（若a01不能形成提案）

只由受控CPU程序读取上一阶段私有轨迹并以既有replay/原始SHA复验，不向agent开放文件读取。
新导出仅含匿名请求组、suite/角色、逐步接受数量和事件顺序，不含prompt/output/candidate/target token ID。
两轮物理重复同组，不能当6独立请求；先检查重复序列一致性，不能为了显著性切成很多独立样本。
接受预测筛选：预先固定整请求留一，历史1步预测下一步接受数；常数为仅训练请求拟合均值，
suite基线仅用训练请求同suite均值，无同suite训练样本则退回全训练均值。只报告MAE逐请求及等权均值，
同时报告仅训练请求中位数及同suite中位数常数，作为MAE的更强对照，避免只与均值弱基线比较。
不以3个请求构造普适置信区间/新晋升门槛。历史优势不等于块长收益，不支持3%端到端结论。
终止顺序筛选：仅报告已记录worker发出与最后scheduler finish提交的顺序，队列入队/原生关键路径仍未知。
任何观测时间受插桩影响，不能冒充无扰动计时。新增CPU工具必须先红后绿、另冻结a02源码和输入。
新的数据包仍不含作者答案，fresh master可重新选方向；a01保留为接口能力不足的尝试，不算一次优化迭代。

a01完整运行已得到needs_more_evidence（3个fresh角色、6个响应、0个CPU实验、0GPU）；
初次01/02是同一进程重复审计，不冒充独立重放。随后03/04为两个独立CPU进程且与原result字节一致，
SHA=`8cb7ac6d6ebc036297dd93fff0d73314384bf5c33296151f3c7325311e45d9c1`。
三个角色均关闭；不会在a02输入中提供a01已选方向或旧响应。

## a02：按agent需求补CPU证据接口，不指定优化答案

- 新E005仅由受控程序导出上一阶段的3匿名请求×两物理重复的接受数量与事件顺序，
  原始HTTP/step stream SHA及真实线性replay再次核验；两次额外导出逐字节一致，无token ID/生成文本。
- 新acceptance_history_audit及terminal_order_audit已先红后绿暴露给broker；14定向测试通过，
  全回归224项通过。均保持end_to_end_gain=null，不提供伪造CPU/队列关键路径时间。
- 数据接口扩展由a01真实agent需求触发；a02角色仍fresh context，不继承a01方向和结论。
  新工具/数据自然会影响可探索范围，不能把a02说成完全未受前次探索影响的独立研究确认。
- 不执行新GPU请求，不实现候选，不修改controller、原stock、成本模型或论文门槛。

- a02执行pin=`b0b89d0b876e77ce26d5c75a61dbf2ef5e418201`，源码tar SHA=
  `e031783e4f0ffc62e9418058d96c6d514216673bb035bf14d0fc7780e8b9d801`。
  fresh master自行选history-conditioned-draft-budget与terminal-overlap-critical-path；
  两个fresh direction各自行请求1个新增CPU工具，实际T001/T002已执行，并将原结果交回各自同一agent。
  原prompt/response/transport及CPU结果保存在对应`logs/exploration-{prep,run,public}-20261109-a02/`。

## 实际结果与解释

| 实验 | 实际观测 | 能说明什么 / 不能说明什么 |
|---|---|---|
| T001：接受历史预测 | 整请求留一，历史1步MAE=2.211373092926491；训练均值=2.420281466433951，中位数=2.4578825705039296 | 有继续检查的预测信号；不是加速比、净headroom或总体泛化证明 |
| T002：终止事件顺序 | 3请求×2物理重复，每份1个未提交worker输出早于finish | 只有插桩下的顺序；缺入队/可靠终止信息时刻、原生关键路径和可节省延迟证据 |

T001三个请求的历史MAE分别为2.200000、2.291262、2.142857，对应训练均值基线
2.568905、2.365654、2.326286。训练与测试按请求隔离，重复轮次合并，不能将6物理记录当6独立请求。
同suite基线仅用训练请求；唯一gsm8k请求没有同suite训练数据，显式回退，不能算同suite独立确认。
三个请求来自此前预选诊断，不代表完整dev分布。改变预算会改变生成/验证次数，旧固定链算术不能替代真实反事实。

两direction最终均为`needs_measurement`，`proposal=null`、`net_headroom_estimate=null`、
`implementation_ready=false`；master最终为`needs_more_evidence`。没有候选实现、方向淘汰、性能晋升或新发现声明。
agent优先请求独立计数记录上的确认及冻结预测到预算的映射；终止方向先核因果证据，不直接做取消优化。
“每题MAE都改善”和3%探索目标是agent的筛选设想，不是新增论文硬门槛，不修改controller判据。
不通过反复换agent/调整规则追出成功提案。

## 验收与证据归档

- 14项定向、224项全CPU回归通过；完整验收日志：
  `logs/exploration-prep-20261109-a02/acceptance-final.log`。测试中的stock/final速率是fixture，不是真实GPU测量。
- a02原结果与两个独立CLI重放逐字节一致，SHA=
  `75f79c7fd62cfcbfad827238d48df4847637cfe39f87e8a5e5daf1f2e3c57915`。
  a01变化前独立重放03/04通过，另以冻结tar隔离源码重放05/06通过，脚本
  `logs/exploration-prep-20261109-a01/replay-frozen.sh`，未绕过source hash。
- 编辑CPU结果、prompt、证据、模型身份、master决定五类篡改全部拒绝；记录
  `logs/exploration-public-20261109-a02/audit-faults.json`。这是工程完整性检查，不是论文token-forcing故障实验。
- 六个prep/public/run目录共118文件、2438743逻辑字节，全部SHA复核通过；清单
  `logs/exploration-evidence-20261109-a01.sha256`，清单SHA=
  `887ccc599fa87433465e75c21326689befba40d141b5dcd03a269862f2d927e0`。
  摘要及复核日志为同前缀`.summary.json`与`logs/exploration-evidence-verification-20261109-a01.log`。
  上阶段5598项亦复验，日志`logs/exploration-prep-20261109-a01/prior-evidence-verification.log`。
- a01/a02各3个fresh角色，均已关闭；a02实际2个CPU实验，本阶段0GPU提交。
  两attempt是接口重试，不是两轮优化；不改controller/orchestrator/patches/costmodel/作者资源/ledger/memory。
- 精确模型ID、token用量和后端内部轨迹不可得，不能声称论文agent配置完全冻结；
  客户端回执不是后端签名，提示限制不等于物理文件隔离。源码pin与tar绑定不替代这些限制。

## 下一阶段建议（未执行）

先报最小证据确认方案获批，再核查已有授权且未参与本次诊断的独立dev计数记录，冻结T001口径，
逐请求比较训练专属均值/中位数及可用同suite基线；重复轮次不是新样本，不事后调参。
没有合格记录则暂停或另报最小采集预算，不声称仓库其他位置绝无数据，不自动提交GPU。
终止方向仅先核已有产物能否关联因果时间；仅有事件顺序时继续待测，不能当成淘汰证据。
只有取得真实生成、开销与净headroom依据及外部验收判据后，才讨论默认关闭的option实现。
本阶段到此收口，不自行进入完整成本模型补测、候选实现、正式晋升、RSI或sealed。
