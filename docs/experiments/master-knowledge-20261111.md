# 知识增强的Master自主CPU研究

## 授权与目标

用户批准：Master自主阅读授权stock/当前基线/profile，检索公开知识，比较2–3个有依据的候选，
分配Direction自主设计/编写/运行/修复廉价实验，再按反馈迭代或停止。维护者不代做科学研究。
不新增GPU，不恢复旧角色或指定旧缩块方案，不读取作者final/sealed，不改controller/规则/账本。
外部参考、历史结果复用和独立发现分别标注；未验收不得写入可信memory。

## 先行验收与执行

复用已有动态Campaign、受限Codex入口、MasterAccess和原生审计，只增加一个任务模式，
不新建研究框架/知识库。既有stock证据和历史负反馈明确标注复用，非新的性能测量。
角色自主决定查询、源码范围、机制、实验和停止条件；不给预选优化答案。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_decisions harness.test_research_knowledge \
  harness.test_master_autonomy harness.test_master_autonomy_audit
$PY -B -m exp.master_decisions --knowledge-research --stage logs/master-knowledge-20261111-a01
$PY -B -m harness.master_decisions_audit --root logs/master-knowledge-20261111-a01
```

先验证新任务模式不改变默认历史验证模式、执行边界及累计预算，再运行真实角色。
沿用CPU保护上限：30分钟、16原生回合、240工具动作、32次CPU额度，最多2个Direction；
Master上限96动作/16CPU，Direction单次最多64动作/8CPU，续派不清零。
公开检索/技能等也占CPU额度，预算显式交付；失败/冷启动/重试都计入，不为完成指标空跑。
长进程TTY前台，输出落盘，保存同父birth/wait/关闭记录。

## 本阶段判据

1. Master实际获取有来源、非空的外部资料，并与stock/基线证据对应；有接口或一次调用不等于知识有效。
2. 自主比较2–3个机会，四维评估收益/新增成本/未知项，引用自身真实工具回执；未知不能编造数字。
3. Direction实际执行有解释力的CPU自检/模型/分析，并自行处理失败；若只能GPU检验，明确返回
   具体请求与缺口，不以无意义CPU算术冒充验证，也不把工具限制当方案无效。
4. Master实际收到实验结果后作决策。独立审计原生来源/脚本作者/输出/SHA/预算/角色隔离/退出。
5. 工程验收和科学结果分开：允许负结果，未完成实际实验则如实报告部分达成；CPU结果不是系统提速。
6. 定向及公开源码副本复验、证据SHA封存，更新README/PLANS/HANDOFF，公开审查后提交推送；
   保留旧ceiling/其他dirty，不上传角色轨迹、原始证据、凭据或受限数据。

## 真实执行结果

状态research_stopped，约600秒；2个原生角色、7回合、40工具动作、18次CPU额度、33次usage更新，
0GPU提交。Master/Direction实际进程exit0，4个角色/初始化进程有同父birth/wait/关闭记录。
历史stock统计仍是原单请求81次verify/425 emitted，不外推全体；没有新的性能测量。

### Master自主获取知识与比较

Master自主搜索2次、阅读4次（3成功/1域名未授权拒绝）：成功来源是DFlash公开项目README、
arXiv 2602.06036摘要和Triton fused-softmax教程。实际读取/源码引用的9处回执已逐项核对；
本轮没有调用BBuf，不能把按需可用写成实际使用。外部资料只作参考，不写可信memory。

Master提出三项诊断机会，潜在净收益都保留unknown，没有套用外部教程加速数字：

| 机会 | 假设与未知项 |
|---|---|
| greedy-logits-fusion | draft greedy的LM-head→argmax可能无需物化完整词表logits；需排除其他消费者，实际运行路径/形状和成本未知 |
| block-width-frontier | 宽度改变的工作量/接受量权衡；无逐步顺序与不同宽度成本，不能用旧直方图冒充反事实 |
| selector-path-cost | 部分greedy selector输出概率行可能没有消费者；需先确认实际selector分支及概率消费语义 |

首次答复引用了尚未登记为evidence ID的工具来源，状态机拒绝。模型自行修复并重写部分描述，
保留三个机会ID/研究维度；原始两份答复均保留，不声称只是字段替换或科学内容逐字不变。
历史first-mismatch的0.995636×负反馈随后交付，只用于旧机制，不外推为LM-head融合无效。

### Direction实际实验与自主续派

Master选择greedy-logits-fusion，分配24动作/4CPU。Direction自行读源码/写check.py；
4次获准搜索已耗尽CPU额度，另2次搜索和1次脚本运行被拒，因此第一份报告如实说明未执行。
Master收到反馈后自主continue，追加8动作/3CPU，没有维护者加额度或代做研究。
Direction在同一native thread执行两次，均exit0，并自行补充第一份检查缺少的base/added边界：

- check.py：16395次有限标量词表分块首最大检查，并构造padding、跨rank并列、采样及后处理反例。
- check_boundaries.py：468次有效词表布局、27次rank和7种token行分块检查，列出6个错误输出/简化变体反例。

独立审计绑定了脚本的同角色write_file SHA、实际隔离CPU执行、stdout/stderr SHA、预算累计和
两次反馈确实进入Master后续原生prompt。脚本不是维护者编写，也没有由维护者补跑。
但它们是自写标准库标量模型，没有调用项目实现、PyTorch或GPU；有些反例直接指定错误输出，
不是6个部署中的故障kernel或controller故障注入验收，不能夸大为真实lossless证明。

### 最终科学结论

源码诊断区分了已有token行分块与尚可能存在的块内词表logits物化。Master只保留**普通dense、
TP=1、无added vocab、非selector/非Domino的draft greedy head**作为待核对范围，不推广到target
verify或sampling：后者可能需要概率、penalty、grammar、logprob等完整logits消费者。

CPU反例说明padding/并列/跨rank/末块等语义不能随意改变；没有实现GPU融合、没有引擎option，
也没有认证当前部署属于上述范围。近并列、NaN/Inf、空shard、matmul舍入和图重放均未验证。
新增归约/寄存器/启动及GEMM效率变化未知，端到端净收益仍unknown，无候选晋升或可信记忆条目。
Master最终stop：继续CPU穷举不能解决决定性的GPU数值/成本问题，不为用完额度追加方向。

这证明了实际知识阅读→机会比较→自主实验→预算反馈→自主续派→结果决策链路，
不证明外部知识相对无知识对照的因果收益，不证明好优化已找到、GPU闭环或论文数字复现。

## 审计与接续

244项指定CPU回归通过，非仓库全量。audit01/02独立重放一致：1次机会比较、1次真实continue、
2次方向返回、2次Python执行、0次revise、0次BBuf；原生审计的denied_tool_attempts=0指未落私有
记录的动作额度拒绝，不包含已记录的3次CPU额度拒绝，后者在research-evidence-review-02中单列。
六份运行源码在启动前按SHA封存runtime-source，当前与启动版本一致；12份角色自身inputs/
scratch/config/canary持久化到role-context，不复制auth/整个home。原生绝对路径不改写，
临时目录清理后须显式按归档恢复。TTY40175已exit0，不重启旧角色。

下一步只提案：由Master/Direction进一步明确最小GPU配置/路径认证和全流程微基准请求，
先确认实际head/量化/LoRA/N/H/V/dtype/stride/graph桶及logits消费者。现有证据不足以给出可靠
显存/时长及预期加速数值；新增GPU须重新确认预算、镜像与统一broker准入，不自动提交或结转额度。
本阶段不推进Integration/Kernel/sealed，不将上述假设当独立发现或已经生效的优化。

## 封存与发布

244项指定CPU回归在工作区及排除旧dirty的公开index源码副本均通过，六份启动源码SHA一致。
44份非本阶段旧dirty保持原SHA，controller/eval/ledger/memory无改动；仅发布本阶段六份代码/摘要。
187文件/4216904字节双次全SHA封存，索引`logs/master-knowledge-20261111-a01.sha256`，
SHA-256为`7e621ce6dbde1d8dc56bbc6a53aaf0be12c5ee1550425246f6a65df665a3cc45`。
封存目录不再写入；最终提交/远端身份另存`logs/master-knowledge-20261111-a01-publication.json`，
以该回执确认同步，不改写原生回执或历史预算。
