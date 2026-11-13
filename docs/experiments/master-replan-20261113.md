# Master重新评估与提案

## 目标与边界

用户批准基于知识包、真实基线和失败事实重新生成方案，不将旧chain12、树或kernel建议作为指定答案，再决定是否值得规划Direction。
唯一阶段目录`logs/master-replan-20261113-a01/`，基准9b65771，旧62份工作保留，先行验收在ACCEPTANCE.md。
本阶段0GPU/NPU/NorthJob/server，不派Direction、不改引擎/controller/规则/ledger、不读sealed/凭据/作者final，不接管Ascend、不继承旧预算。

## 执行流程

1. 保存旧工作/保护文件，冻结82份基线/知识/公开缓存/通用工具与40项来源入口；共享历史事实和外部先验，不提供旧Master完整设计或分析脚本作答案。
2. 新原生Master默认继承模型、fork_context=false，自主按需检索、读授权stock/原始证据、补公开资料，比较长度/候选选择/kernel/端到端四维。
3. 至少比较两个不同机制，说明来源、条件净收益、新增成本、unknown与关键判断反例，自主选择优先项；如果仍选旧方向，重新证明优先依据。
4. 给出具体算法/伪代码、参数/调用点、完整状态/索引/shape、default-stock option与fallback、正确性及成本验收、最小证伪/停止条件；0GPU不等于只能交方向名或manifest。
5. Master先写CPU判据再分析，实际读取/查询和运行绑定当前SHA/命令/退出码；父助手只独立核对，不提供或代写科学解法。
6. 来源/语义与独立CPU副本重放、旧工作/保护文件/角色关闭验收后，私有归档、公开脱敏摘要，按既有授权精确提交推送。

旧推荐在进度/知识材料中可见，因此不声称双盲、完全无先验暴露或知识注入的因果效果。外部知识不是本地validated memory，有限oracle不是全球上限，异轨迹tau不作因果，profile不替代未profile计时。
允许负结论或有界取证，但仍要求条件成立时的明确机制首版；不为完成任务编造接受量、运行时成本或正收益。只有独立controller能产生正式验收/晋升数字。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native
$PY -B -m harness.master_native check --directory logs/master-replan-20261113-a01
$PY -B logs/master-replan-20261113-a01/audit.py
```

另运行本阶段`test_audit.py`与`audit.py --final`；所有回执保留在私有阶段目录，不将schema通过替代科学语义复核。

## 已交付与独立复核

- 原生Master Kepler未继承旧对话、未覆盖模型，实际核对23个授权来源；比较联合投影、小M MLP、动态4/8预算、固定16长度、前缀闭合16节点树。排序是最小实验的信息价值，不是预期加速比排名。
- 首选`G-joint-projection`仅作有界取证：target C1 verify8，将QKVZ与BA权重按行拼接，一次现有BF16线性计算，继续使用stock支持真实行stride的拆分消费者。启动后/graph前准备，default=false，资格外保留stock；不改变接受、bonus和提交状态。
- 明确参数/输出布局、storage alias、内存生命周期、graph/stream及完整状态差分；适配stock已有拼接机制，不算独立发明。当前实际是否已经融合仍待E0，静态搜索未见直接调用不证明生产路径。
- Master主动检查原始trace：同名BA区间约99.95%与QKVZ重叠，反驳“将累计BA时长全部当可回收墙钟”的推论。维护者用独立Decimal端点扫描复算一致；此统计不是逐module配对、依赖DAG或因果暴露证明。
- 7项CPU检查、1944个合成接受/终结组合通过；维护者在新目录复制两份脚本与来源索引，用固定Python重放，stdout/stderr逐字节一致。54项交付文件身份、23实际来源身份、82冻结输入、旧62份工作和指定保护文件核对通过；4项入口与8项审计回归通过。
- 独立语义复核接受的是CPU设计交付，净收益仍unknown；不是controller正确性、lossless或性能晋升。Master已关闭，本阶段0GPU/NPU/NorthJob/server、未派Direction、未实施引擎。

## 知识使用与限制

实际读取已授权知识卡、Sequoia、HF预算/停止逻辑、CUDA Graph资料、BBuf计算分析Skill及stock/历史证据。均记录来源、SHA和用途；固定公开缓存是复用，不冒充本轮新HTTP取证。
BBuf本轮用于限定计算估计口径，没有运行模拟器，也没有Direction/Integration/Kernel执行，不声称各阶段全面使用BBuf或完成真实闭环。
CPU整数代数和状态toy不证明BF16舍入、真实GDN/conv、graph、全状态或forcing通过。历史profile与未profile计时不能拼成实测收益；有限lattice不是全球上限。
早期工具输出过大与CPU精度修正保留在原回执/工具说明中，不用最终成功掩盖过程问题。事后文件不变不能证明未读禁区，不声称双盲或知识注入因果提升。

## 下一阶段，仅为建议

1. 另行审批资源/可信执行入口，再交Direction自主取证；旧预算不结转，本阶段不自动提交。
2. E0确认实际stock路线、参数/shape/backend、是否已融合；机会已存在于运行路径或身份不符即停止。
3. E1对相同真实输入测完整stock双流投影＋拆分与联合投影＋拆分，涵盖自然前缀、重复噪声、显存/数值与竞争场景；不能把两核时长相加作基线。
4. 无可靠完整pair净收益或有未解数值/alias问题即停止。只有另批且取证支持后才考虑引擎option、真实全状态、独立controller forcing及2048-token双卡互换；不得跳到sealed或宣称晋升。

私有归档与精确四文件公开增量按既有授权执行，实际成功、校验值和Git身份以阶段archive-receipt/publication回执为准；原始profile/源码/PDF/运行产物不进入公开提交。
