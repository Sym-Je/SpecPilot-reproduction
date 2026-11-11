# Master动态研究决策：CPU接通与历史失败反馈验证

## 授权与目标

用户批准：先补Master的自主研究决策循环，比较机会、选择最便宜的取证、分配Direction，
收到反馈后可修订、继续原方向、改派或停止。此阶段只用已授权stock、公开证据与隔离CPU，
不新增GPU、不结转旧GPU预算、不读取作者final或sealed、不改controller/规则/账本。

复用现有受限Codex入口、MasterAccess与独立native回执。新增CPU入口与可复用决策状态机，
不声称旧GPU固定流水线已经完成动态切换，不以新框架或完整ceiling为前置。
维护者实现通用调度和证据分发，不替Master选择研究方向或替Direction编写科学分析。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_decisions -v
$PY -B -m exp.master_decisions --stage logs/master-decisions-20261111-a01
$PY -B -m harness.master_decisions_audit --root logs/master-decisions-20261111-a01
```

先红后绿：未知动作/GPU动作拒绝；四维与机会比较；真实反馈只能由可信层分发；
修订/继续须绑定已有反馈；新方向不复用他人私有上下文；同方向继续不重置预算；
阶段动作/CPU/模型回合/墙钟上限；闭环停止可重放，来源或事件被改动时审计拒绝。
验收允许有依据停止，不要求开新方向或取得正收益。

## 执行与证据

独立目录`logs/master-decisions-20261111-a01/`。固定原有dirty身份，公开提交不混入旧ceiling或其他专项。
维护者整理已有四维事实与未知项；Master自行比较具体机会。历史失败来自已封存的公开stock
源码诊断，只分发机制摘要/测量反馈，不分发其他方向私有推理、作者final或独立专项结果。
第一次比较后由可信层揭示该历史反馈，明确这是回顾性决策验证，不是新测量或独立发现。
随后Master自主取证、修订、派发隔离CPU研究、继续或停止。Direction自己写脚本并解释结果。

工程执行上限：最多16个原生研究回合、240次工具动作、32次CPU额度、墙钟30分钟；
最多2个Direction，Master最多96动作/16CPU，单次方向分配最多64动作/8CPU。
这些是本次CPU入口的保护上限，不是新增GPU或无限API授权；不为用完额度强迫研究。
每次模型/工具/决策及实际CPU输出均落盘；维持同一可信父进程的birth/wait/关闭证明。

## 完成标准

1. 真实Master给出机会比较及未知项，不仅模板测试通过。
2. 真实历史失败反馈送达；记录之后如何修订优先级、补证、继续、改派或停止及其依据。
3. 对实际派发的Direction，核对自身源码阅读/脚本作者身份/CPU执行和返回反馈；允许没有值得派发的任务。
4. 独立重放预算、原生来源、状态变化和进程退出；不把字段完整自动判为科学判断合理。
5. 更新README/PLANS/HANDOFF，持久化证据与SHA，公开审查后提交推送。

不承诺优化收益；GPU快筛、真实GPU动态研究、Integration/Kernel实质优化、T3/sealed和多轮RSI仍待后续授权。

## 实际结果与边界

本次CPU决策链已正常结束，2个原生角色、4个原生回合、18个获准工具动作、1次CPU额度计费，
新增GPU提交为0。约289秒完成，两个角色与辅助进程共4个进程均有同父进程birth/wait/关闭证明。
额度计费不是脚本执行次数：本次实际`run_python`成功执行为0，不能写成CPU科学实验已通过。

1. Master独立比较缩短验证块与first-mismatch归约两个机会，覆盖四项研究维度，保留未知收益。
2. 首次比较后，可信层才交付历史实测0.995636× [0.993251,0.998027]。Master据此暂缓旧kernel机制，
   转派缩块的最便宜源码/CPU诊断。这是历史负反馈回顾，不是新的性能测量或独立发现。
3. Direction自行读取stock，写出`scratch/block_model.py`，识别非因果draft注意力和跨步上下文依赖。
   因此前缀不变假设没有保证，不能把旧接受量直方图截断当成真实缩块后的反事实收益。
4. Direction分配12个动作、2次CPU额度；源码阅读/脚本写入已用完12个动作，第13次运行请求被拒。
   Direction明确报告脚本未执行；Master也识别了这一点，认为补算术不能解决因果及真实成本缺证据，停止。
   不能因工具拒绝判定缩块无效；本轮没有优化候选、晋升、lossless或端到端收益结论。

本次原生实跑覆盖compare→历史反馈→dispatch→Direction反馈→stop；没有实际revise/continue，
也没有再次开新方向。修订/续派和累计额度等分支只由工程测试覆盖，不宣称所有动态分支均实跑。
Master未调用BBuf或公开检索，不能把可用工具写成本轮实际使用；旧GPU固定流水线仍未切换。

## 工程问题与验收

- 首次原生审计因工具动作耗尽时broker在落私有记录之前拒绝，导致wire比私有动作多1次而失败。
  保留`audit-01.stderr`。审计新增可选的可信逐轮额度，只接受确切耗尽点、原生wire中的失败拒绝；
  不计为获准动作/CPU执行，成功执行或提前拒绝不能借此隐藏。旧入口默认严格行为不变。
- 原始Direction简报没有显示Master的动作/CPU分配。结束后修复为显式显示本次新增和当前剩余额度，
  提醒自行为运行预留动作；不替研究角色决定实验，也不为了制造成功重开本轮研究。
- 发现续派反馈的前缀匹配可能误认近名方向，先复现失败测试，再改为绑定该方向确切已返回反馈。
  此修复没有在本次原生进程中运行，只有工程测试覆盖。
- 三份运行源码在修改前逐一核对launch SHA并封存`runtime-source/`，原manifest不改。
  独立审计分别报告启动版本和结束后修复版本，不假称存活进程热加载；角色inputs/自身scratch及
  config/canary按原SHA持久化到`role-context/`，不复制auth或整个home。原生路径引用仍保留，
  若临时目录被清理，需要按归档显式恢复，不能静默改写原始回执。
- 242项指定CPU回归通过，非仓库全量；两个不存在的测试模块名导致过一次命令错误，修正选择后重跑。
  `audit-05.json`和`audit-06.json`独立运行且完全一致；历史数值、实际反馈送达Master的下一原生prompt、
  journal重放、累计预算、脚本未执行和进程关闭均核对通过。审计不自动认证研究判断正确。

复验命令（不会重开研究）：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_decisions harness.test_skill_rsi_audit \
  harness.test_profile_autonomy_audit harness.test_master_autonomy_audit \
  harness.test_master_proposal harness.test_master_autonomy harness.test_research_paging \
  harness.test_research_knowledge harness.test_engine_research harness.test_research_shutdown \
  harness.test_skill_rsi_continue harness.test_master_recovery harness.test_skill_rsi_pipeline
$PY -B -m harness.master_decisions_audit --root logs/master-decisions-20261111-a01
```

## 接续建议（非自动授权）

下一步应让Master按真实缺口自主申请可负担的观测/微实验，而不是由维护者接手缩块研究，
也不应再仅靠“停得合理”证明研究能力。先用修复后的额度简报验证实际廉价实验/反馈，再将动态
决策接入已有GPU快筛和独立dev入口。新增GPU需重新确认资源，不恢复旧任务或结转余额。
真实Integration/Kernel、正常final T3/sealed与多轮RSI仍未完成；架构证据不等于论文数字复现。

## 封存与发布

242项指定CPU回归在工作区和排除旧dirty的公开index源码副本均通过；追加的Direction简报白名单审计
与前两次结果一致。已核对44份非本阶段旧dirty文件SHA不变，controller/eval/ledger/memory无改动。
只发布10份本阶段代码/摘要文件，不发布原始角色轨迹、配置、scratch或鉴权文件；未复制外部Skill实现。
阶段中Master误把compare决策作为工具动作提交过一次，被拒后按JSON决策返回；这消耗了1次CPU额度，
但没有执行科学脚本。原失败工具回执保留，不把它算成正确性或性能验证。

私有归档136文件、1887644字节，双次全SHA通过；索引`logs/master-decisions-20261111-a01.sha256`，
SHA-256为`7d9f7c9bb2c6d02158696238cffc5ba3ffcda2b0b6ec172a7257481e7944905c`。
封存目录不再写入，后续发布审查及提交/远端身份记录在独立的
`logs/master-decisions-20261111-a01-publication.json`，以该回执为同步完成依据，不改写原运行manifest。
