# 最大研究权限下的Master自主诊断与方向竞争

## 目标与授权

用户批准完整阶段：扩大授权stock源码阅读、研究工作区与受控源码option能力；
Master主动获取信息、估计净收益、派发互补方向，Direction自主设计与迭代，controller独立验收。
不指定双叶树，不强迫产生正收益，不以工具限制当科学反证。

新上限16 H100 GPU小时／12小时／最多并发4卡；失败、排队、冷启动计入，不结转旧余额。
沿用已确认镜像digest、WeaverDev、qiji、只读模型挂载/toleration，显式priority=3并核对实际Job。
不改controller/验收规则/账本，不读sealed/凭据/作者final，不接管Ascend。

## 先行验收与流程

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_open_research harness.test_source_candidate harness.test_research_knowledge
```

1. 保存旧dirty与身份，登记新授权；先测边界再改实现。
2. 授权stock文本阅读包括C++/CUDA/Triton/配置，支持研究工作区多种源码文件。
   保留内核隔离，不开放宿主shell、凭据或研究角色直接NorthJob。
3. 源码option新增宽范围协议，允许新增runtime/kernel源码文件；默认仍选原stock，
   校验原始SHA、声明文件全集、独立候选树与当前CPU自检。旧v1行为不变。
4. Master自己读源码/调研/BBuf，必要时请求真实profile；比较四维机会及新增成本、未知项和证伪实验。
   Direction自行实现/测试/修复；不把完全相同输出冒充唯一lossless判据。
5. 真实任务走可信准入、查重、完整命令及总卡数展示、单次提交、code200/UUID与生命周期核对。
   拟保留候选依既有controller开发正确性/token forcing与配对性能规则验收，不开放sealed。
6. 有正确性依据的机制再整合；Kernel按实际热点自主研究。没有候选可以停止，不虚构完整RSI。
7. 审计真实作者、反馈、资源和退出；归档与公开审查，更新主页/交接后提交推送。

## 合理性自检

放宽的是研究空间，不是裁判与资源权限。文本源码可读不代表对应二进制路径已认证；
新增CUDA源码可提交不代表编译、数值和真实调用已成功。通路缺项须明确，不用提示词宣布能力完成。
研究选择由Master负责，主助手只维护通用设施和审计。原树修复保留但不预选为本轮方向。

## 实际执行与结果

唯一目录`logs/master-open-20261112-a01/`，唯一资源账本`resource-state.json`。
154项入口检查通过；追加式源码恢复、完整日志交付、JSON转义与CRLF日志SHA重放均先红后绿。
真实Master已主动读stock、公开检索、BBuf和自写CPU分析，比较四维后选择两路：
固定链长8/16，以及BF16小M线性层调度；暂缓树，不继续预设的双叶修复。
Direction均已自主实现v2 option、成功CPU自检并请求真实诊断；CPU通过不是正确性验收。

|任务|UUID|终态|保守GPU秒|
|---|---|---|---:|
|preflight01|job-1f1059eb5496-20261112084923|Completed / exit0|2138|
|direction-d1-02|job-a9cc33edf87e-20261112090930|Aborted / exit1|1296|
|direction-d2-01|job-1db1479205b4-20261112090930|Completed / exit0|2426|
|profile-01|job-06cf2db6d74c-20261112093436|Completed / exit0|651|

四任务前缀均为`sp-masteropen-20261112-a01-`。合计6511 GPU秒=1.808611 GPU小时，0活动GPU。
每次单独查重/展示完整命令/准入，code200、UUID、实际启动和终态分别有回执；未重复提交。
实际Job为higher-priority-job，Pod priorityClassName仍null；请求qiji、实际Volcano queue=proj-31。
镜像digest、实际GPU数与模型只读挂载经核对；优先级不保证免抢占。

- **d1**：Direction自加checkpoint block_size>=16检查遇实际8后拒绝启动，未形成配对数据；
  不是引擎不能运行16的证明。原摘要只有server exited(-9)，研究角色未获自身完整日志，因而合理停止而非盲重试。
- **d2**：候选tiny_gemm路径覆盖M1..8/N96/K5120，5请求/10pair/两轮fresh与换卡，
  candidate/stock吞吐几何平均0.9660407318×，95%区间[0.9253396630,1.0136212080]。
  未见可靠收益，Direction自主stop；只属公开dev诊断，不是正式正确性/token forcing、晋升或普遍无效证明。
- **Integration**：没有正确性已验收机制可组合，合理stop，不冒充完成真实补丁整合。
- **Kernel**：自主读stock/CUDA与BBuf并申请math500:0/graph-128采样。
  复现GEMM累计work热点，但尚缺模块/阶段/关键路径认证；没有新kernel候选。

原研究正常`research_complete`，179工具/实验动作、39 CPU额度、2源码实验请求、12模型回合。
没有controller dev gate、sealed、晋升或新增可信memory。新CUDA文件支持只经CPU/bundle测试，
本轮实际GPU只修改已有Python文件，不能宣称任意新增kernel编译执行已验证。

## 通用日志交付修复与自主复核

新增授权执行产物导出，绑定阶段/Direction owner并核对复制SHA；可读取自身launcher日志、源码和配对原始数据，
不导出凭据、sealed、权重或其他方向私有推理。主助手不替Direction改guard或指定科学修复。
原研究结束后在`observability-continuation/`执行明确标注的同逻辑Master接续，自己的原生答复/scratch恢复有来源；
原预算、累计调用与停止记录完整保留。首个入口因直接匹配转义JSON失败，未启动模型，证据留`observability-start-failed-01/`。
修复后Master完整分页读取真实d1日志，确认自设guard原因，仍自主stop；未恢复Direction或新增GPU。
最终累计187动作、39 CPU额度、2源码实验请求、13模型回合、81 usage更新。
这证明证据可交付与自主管理决策，不证明已能发现有效优化。

## 收尾验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m harness.master_open_audit --directory logs/master-open-20261112-a01 --include-observability-stop
```

审计分别核对原研究与接续，重算原生作者/CPU/公开知识/BBuf/真实任务/累计预算/日志SHA/实际退出。
最终指定回归、公开副本、双次独立审计、持久归档和发布身份见私有`closeout.json`与`publication.json`。
最终指定433项回归通过；原研究加观测接续两次独立审计一致，实际12个研究进程退出已核对。
公开副本复验需只读Git身份和4份历史公开诊断JSON；未配置时的2错/1错均保留，
补齐相同已授权测试依赖后复验，不把宿主证据依赖说成无需准备即可运行。
原47份dirty按初始清单保留；公开只发布本阶段代码/脱敏摘要，不含研究私有上下文、GPU原始产物或凭据。
不是仓库全量全绿：宿主UID线程数导致的旧RLIMIT_NPROC测试环境限制仍单独记录，未借此放宽裁判。
