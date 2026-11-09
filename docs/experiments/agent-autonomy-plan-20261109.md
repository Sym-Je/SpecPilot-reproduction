# Master统筹与Direction自主实验能力：首阶段CPU验收

日期：2026-11-09（北京时间）。状态：首阶段真实CPU自治回路已验收；不授权GPU。
用户已停止主助手人工推进的接受历史补采；保留旧代码/证据，不判断点子无效，不算自主探索完成。

## 目标

让direction自行提出可证伪假设、设计并编写实验、调用执行工具、解释反馈并决定下一次行动；
master负责方向拆分、预算分配、跨方向统筹和继续/终止决策。主助手不替它指定VERIFY、接受预测或选题规则。
自主性是受预算和权限约束的实验行动权，不是给agent修改裁判或宣称收益的权力。

## 主要流程

1. 核对现有真实agent桥接的缺项：当前direction只能选择少数CPU算术工具，尚不能自主写/执行实验。
   定义master计划、direction行动、工具反馈、迭代/停止和汇总的状态接口，先写可执行验收。
2. 给direction受控能力：读必要stock代码与公开证据，在隔离可写目录编写实验，运行CPU检查，
   申请事先批准预算内的GPU任务。只按路径/资源/安全边界审查，不由主助手决定科学假设或实验答案。
3. 接通实际行动回路：direction输出动作→执行层运行→返回完整退出状态/证据引用→原direction继续。
   正常错误可在预算内自行修复；预算耗尽、证据不足或已证伪均可终止，不强求成功候选。
4. master真正统筹：分配剩余预算和工作范围，收集各方向证据，决定继续/停止/交集成角色；
   不把它降为主助手已作决定后的文字汇总，也不让固定registry代替真实决策。
5. 先做CPU工程验收，再做真实agent端到端烟测，验证自主设计→真实执行→反馈→继续/停止。
   禁止只调用算术接口后宣称完整搜索。GPU部分必须另有明确镜像、资源上限与任务提交授权；
   阶段授权内的小动作自主安排，高风险/超预算/不明确的提交仍按NorthJob规范处理。
6. 记录提示/动作/实际工具回执、代码diff与身份、命令/退出码、预算消耗、失败及停止原因，
   更新GitHub进度。仅当具备实施依据才提出默认关闭option，性能与正确性结论仍由controller生产。

## 简要自检与边界

- 不再安排接受历史方向的采样，不预置优化方向或作者final答案；旧证据可供引用，不当新发现。
- 允许真实失败和“证据不足”；端到端工程烟测成功不等于优化成功、总体泛化或论文数字复现。
- controller只读、sealed不可访问、ledger/memory不得由agent写入；实现仍须option默认stock。
- 权限隔离需实际验证，不能只靠提示语声称物理隔离。工具权限不足时如实列为缺项，不让主助手代做实验掩盖。
- 正式性能验收仍为双卡同请求/换卡；单臂诊断不得冒充paired CI。新门槛不能由实现者自行放宽。

用户已用“开始”批准上述首阶段；本文件不授权GPU或完整自主优化搜索。

## 本阶段验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p15_autonomy
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
git diff --exit-code 12f08a0 -- controller orchestrator patches costmodel assets/upstream ledger memory
git diff --check
```

实现通用write_file/read_file/read_stock/list_stock/run_python接口，不新增专用科学算法工具。
CPU脚本仅可读自身工作目录/公开证据和运行库；代码写入由broker执行，脚本运行时文件系统只读，结果经stdout/stderr返回。
实际Landlock+seccomp验证越界读写、网络、子进程和GPU设备被拒绝，限制CPU/内存/输出/墙钟；不可用就拒绝执行，不降级。
子agent后端自身的工具访问只能按提示约束，不能把脚本执行沙箱说成模型后端的物理隔离。
master自主分配最多2个方向和预算，可依据真实反馈继续/停止；direction编写任意受控CPU实验并依反馈迭代。
真实agent探索最多24个broker动作、8次CPU运行，每次6秒墙钟/3秒CPU/768MiB/每流64KiB输出；GPU预算固定0。
工程回归fixture单独记录，不冒充真实agent实验或新增研究样本。
允许证据不足或假设被否定；验收至少记录一次真实agent自产脚本执行与后续决策，不预置方向/预测器/样本规则。
旧接受历史补采保持取消；不继承旧聊天、作者答案或固定registry，不以调用旧算术接口冒充新执行能力。
工具回包/代码/退出码/实际角色回执/版本/预算均绑定，两次CPU审计及完整回归后更新主页与交接并推送。

## 执行身份与自主分工

执行pin=`ff96c81535d035d06409b38e80fb099530e70a37`，源码tar SHA=
`9f9e2d06426f6ca9fb21301b87718a3bd180e9636fab65dfed50ff7a540ae09b`。
11项定向/246项总CPU回归通过，包含真实隔离拒绝、脚本失败→修复反馈、master追加预算和全桥接审计篡改检查。
这些测试的模型回包是显式fixture，不充当真实agent推理；以下运行另用真实后端。

本轮fresh master自主分配两个方向：boundary-accounting-invariants与prefix-distribution-ordering，
各10 actions/3 runs，保留4 actions/2 runs。不是主助手指定方向或四题协议。
真实角色仅通过通用action回路，自行给出代码/命令选择；transport driver不改写代码或科学结论。
记录在`logs/autonomy-{prep,run,public}-20261109-a01/`，driver程序、精确提示/原回包/执行stdout/stderr均持久化。
本轮已结束，三角色全部关闭；GPU预算0，旧补采保持取消，控制器及作者资源不变。

## 实际回路与Master决定

- 实际3个fresh角色、12个模型回包；master分配20 actions/6 runs，保留4/2，最终消耗8 actions/4 runs。
  两次finish不计实验动作消耗；完整工具轨迹10条，不伪称10次CPU实验。
- T002、T006、T009退出码0；T004为1：direction自己的mutations.py无法定位本地experiment模块。
  原始失败完整反馈给同一direction，由它在T005自行修复加载方式，T006成功；主助手没有代改科学脚本。
- 两direction都根据实际结果finish；原master在R012决定两方向均stop、追加预算0。
  真实运行没有触发追加预算；追加/继续能力仅由工程fixture验证，不能说本轮实际进行了重分配。

| Master自行分配的方向 | Direction实际CPU证据 | Master结论与边界 |
|---|---|---|
| boundary-accounting-invariants | 6条既有记录满足统一计数关系；合成单字段扰动可检出，但守恒耦合修改可通过 | 已有3请求的代数相容，不是执行/token正确性或lossless充分证据；停止追加合成枚举 |
| prefix-distribution-ordering | 精确有理数与整数交叉乘法一致，10对suite中2对出现阈值排序反转 | 否定给定筛选后聚合直方图的统一一阶随机占优全排序；不外推请求总体，不据此选优化算法 |

本轮是通用CPU行动能力验收，不是新优化发现。已有计数解释的复核和合成检查不能计为新发现或新模型样本。
没有GPU采样、改变算法后的生成、默认关闭优化option、controller正式验收、晋升、sealed或真实多轮RSI。

## 独立验收与限制

- 11项原定向及3项独立完整性测试、249项总CPU回归通过；完整日志`logs/autonomy-prep-20261109-a01/acceptance-with-integrity.log`。
- 两个独立CLI审计进程与原结果逐字节一致，结果SHA=
  `dcd8cf7cfdad9ca2e4d1c3d88ee68f57518aa527512a0c405aa0b2af2ef8a18f`。
  审计重建提示、预算和回执/代码/输出绑定，不是重新调用模型，也不是重新执行科学实验获得独立样本。
- 编辑解析回包、退出码、agent代码、预算投影、issued prompt共5类篡改全部拒绝；
  `logs/autonomy-public-20261109-a01/audit-faults.json`。这是工程完整性故障，不是论文token-forcing门禁。
- 收尾增加独立只读`harness/autonomy_integrity.py`，不改已执行源码或研究规则：2份工作区输入与发给角色的证据
  逐字节相同，3份最终脚本与direction写入记录SHA一致，4次执行均有施加内核限制后的bootstrap标记。
  额外测试输入损坏、脚本改变、额外文件、缺bootstrap会拒绝；此后置验收代码身份由最终Git提交与校验文件记录，
  不冒充它已在ff96c81执行tar中存在。实际角色代码与科学输出未重跑或改写。
- 物理隔离证明只适用于CPU脚本执行进程：Landlock+seccomp拒绝越界读写/网络/子进程/设备。
  模型后端自身其他工具仅按提示约束，不能据此宣称模型运行时的工具权限已物理隔离。
- 使用当前Codex子agent工具作为模型后端；不是仓库内独立部署的LLM服务。继承默认模型，精确模型ID、
  token用量与内部工具轨迹不可得；客户端回执不是后端签名，不记录隐藏思维链。

**决策：真实CPU实验自治首阶段通过。** 主助手只建设/验收通用能力，不把master已停止的研究转成人工后续实验。
下一大步骤先报通用GPU工具/资源审批及候选到controller的交接方案获批，不自动提交GPU或恢复旧支线。

新109文件/3200858逻辑字节全部SHA复核通过，清单`logs/autonomy-evidence-20261109-a01.sha256`，
清单SHA=`53c82d863f8354945969d9fe42d5311963fb83b03bd36c89e981547f91f5ffa5`。
摘要`logs/autonomy-evidence-20261109-a01.summary.json`，复核日志`logs/autonomy-evidence-verification-20261109-a01.log`。
后置完整性校验器及测试的源SHA单列于`logs/autonomy-prep-20261109-a01/integrity-source.sha256`，代码另由最终Git提交追踪。
