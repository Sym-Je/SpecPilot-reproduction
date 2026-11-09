# 首轮真实agent探索：证据到候选提案

日期：2026-11-09（北京时间，机器日志保留UTC）。基准`6561e40122958b5f0e49b06c85cfea907faf26e7`。
状态：用户批准执行，先冻结T0接口验收；不预设VERIFY、不实施候选、不提交GPU或晋升。

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
