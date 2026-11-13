# 投机解码研究知识包

这是供Master按需检索的**外部研究先验**，不是本机已验收的structured memory。
全部机制卡标记`local_validation=not_validated`；来源、适用条件、收益依据、新增成本、正确性风险和最小验证分别记录。
资料可以指导研究，但不证明本地正确性、实测提速、论文数字或独立发现，也不授权GPU。
公开索引只含外部来源；涉及本地stock/历史诊断的判断，还须核对任务简报中授权的原始证据，不能只凭公开卡片确认本机实现。

## 使用方式

1. 根据当前瓶颈在[cards.json](cards.json)检索`category`、`tags`、`id`，不必一次读取全部资料。
2. 按`source_ids`查[sources.json](sources.json)，读取具体固定版本及定位；仓库首页不等于实现已读。
3. 与授权stock代码、实际接受量和未profile成本核对，注明不适配之处、条件假设和未知项。
4. 比较备选机制，给出条件净收益及最便宜的证伪实验；由Direction自主实施、独立controller验收。
5. 引用/移植/复用如实标记。只有按既有规则验收后，才可能产生本项目可信记忆；不得直接写入`memory/entries/`。

```bash
rg -n 'lookahead|parallel-draft|confidence' docs/knowledge/speculative-decoding/cards.json
rg -n 'prefix-closed|parent-conditioned|conv-window|bonus' docs/knowledge/speculative-decoding/cards.json
rg -n 'graph|cost-frontier|critical-path' docs/knowledge/speculative-decoding/cards.json
```

## 四个维度

| category | 研究问题 |
|---|---|
| length_budget | 固定/动态验证长度，串行与并行draft的成本差异 |
| candidate_tree | 候选路径评分、预算树形、祖先闭合及接受路径 |
| recurrent_state | SSM、因果卷积、KV和bonus的完整状态语义 |
| kernel_e2e | CUDA Graph、byte/FLOP估计、临界路径与完整请求成本 |

对随机采样、不同模型/精度、批处理或不同硬件的适用性不能从单请求greedy直接推广。
有限lattice不是全局接受上限，FLOPs不是延迟，异轨迹接受量不能当因果收益。
来源许可不明时不移植实现；卡片是机制摘要，不随包转载原始论文或整套代码。

Master已在[本阶段研究](../../experiments/knowledge-master-20261113.md)实际检索使用这些知识。
公开文件只含机制摘要与来源元数据；原始下载、授权stock/诊断和工具回执私有归档。
不包含sealed、凭据或本轮禁止参考的作者final实现；知识包接入不构成强制权限隔离。
