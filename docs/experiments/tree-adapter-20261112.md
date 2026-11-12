# 真实树适配：先执行与正确性，再看性能

## 目标和授权

用户批准由Master评估范围、Direction自主实现真实stock候选，先检查执行与正确性，再独立dev验收。
本阶段新上限8 H100 GPU小时／8小时／并发2卡；失败和冷启动计入，旧余额不结转。
沿用已确认镜像digest、WeaverDev/qiji、只读模型PVC、原toleration和higher-priority-job。
日期按北京时间。不能读取作者final/sealed，不改controller、科学规则、账本或可信memory，不接管Ascend。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_tree_adapter harness.test_source_candidate harness.test_source_research harness.test_role_turn
```

1. 保存47份旧dirty，重验上阶段公开事实与原生报告，独立登记预算。
2. Master自主评估真实适配范围、潜在净收益、风险和停止条件；Direction先写验收再实现受控源码option。
   复用已有受限入口和source-option-v1，不再以玩具契约代替真实适配；default-off必须stock。
3. Direction经自身工具运行CPU自检；只有当前patch与自检SHA绑定成功才接受真实执行请求。
4. 可信broker先预检真实引擎隔离，再执行最小候选；提交前核对CLI、查重、展示完整命令/资源，
   单次提交并核对code200/UUID。研究角色不持有NorthJob权限，不得自己批准准入。
5. 诊断不构成lossless/晋升；拟保留候选交原controller完整dev联合验收，正确性通过才解释性能结论。
   检查真实分支路径、状态与提交；失败由Direction自行修复，达到预算/停止条件则如实结束。
6. 审计作者身份、源码、回执、实际退出、GPU预算；归档、公开副本回归和主页/交接更新后提交推送。

不强求正收益，也不要求为启动GPU而提交不可信补丁。若最小适配仍超出可信执行能力，明确缺口，不能绕过限制。
Master可以依据实现成本换方向；不得把换方向或合成测试通过包装成真实树跑通。

## 执行接续（进行中，不是最终验收）

唯一资源账本为`logs/tree-adapter-20261112-a01/resource-state.json`，8GPU小时/8小时/2卡不因续接重置。
初始计划与失败在`a01/`，首轮真实实验在`logs/tree-adapter-20261112-a02/`，
当前目标覆盖复核与后续取证在`logs/tree-adapter-20261112-a03/`；这都是同一阶段的attempt，不是新余额。

- Master独立核对stock已有父索引/树verify入口，Direction自己写6个edit，修改worker与decode graph runner。
  最小原型是固定block8、共享祖先与两个同父叶子，使用真实draft词表ID，非N16树或玩具状态。
- 原始Direction请求仅缺一个JSON根括号；原文/退出均保留，未手改科学字段。
  受限逻辑续接恢复自身原生写入，重新执行自检并重交请求；现入口支持同角色有界格式修复。
- 预检与两次候选任务均单次create、code200及UUID核对。Job.spec为higher-priority-job；
  Pod没有继承该priorityClassName，不能宣称不会被抢占。请求queue=qiji，实际Volcano queue=proj-31，
  与此前WeaverDev任务映射一致；namespace仍为qiji，未改调度参数。

| 任务 | UUID | 执行状态与科学结论 | 保守GPU秒 |
|---|---|---|---:|
| preflight01 | job-971fec106f87-20261112010017 | Completed/exit0，GPU隔离与stock/stock两轮预检通过 | 2214 |
| candidate01 | job-d4a688a499f8-20261112012242 | Aborted/exit1，真实VERIFY/父状态已命中，但KV索引Int/Long冲突；无有效pair | 1164 |
| candidate02 | job-4bc75d65e584-20261112013738 | Completed/exit0，但10/10输出不一致；不能保留或解释性能收益 | 2408 |

Direction自己修复dtype并补静态检查；第二次运行真实提交完成，跨轮各题首差位置重复为3/30/11/28/32。
完整日志可见替代叶接受提交；仅看尾部不能证明未覆盖。没有真实父状态数值等价或lossless证明。
主助手只提供自身实验完整日志、paired输出和字面计数，不代做科学修复；反馈增强不改变原性能/正确性字段。

Direction停止坏候选后，Master以finish表达stop，旧编排器因角色协议混淆退出。
原退出保留；入口现记录等价stop别名并对追加分配做有界协议修复，不改科学结论或controller规则。
因为用户的真实适配目标未完成，进行一次明确标注的覆盖复核：不强迫正收益，不原样重跑坏版，
Master自主判断是否有廉价定位/差分。它已核对完整证据并继续分配受限Direction研究。

当前Direction的父快照/寄存器路径差异只是假设，未认定根因。下一项实际动作仍由Direction自主设计。
同阶段已通过预检按UUID/原始数据独立重放后复用，不重复初始化。尚未请求controller dev gate或sealed，
尚未产生可保留的真实引擎候选。最终提交、归档与科学结论在全部收尾后补充。

## 实际结果：真实路径已执行，正确性目标未完成

以上为逐步接续时的历史状态。本阶段最终没有通过真实树正确性验收，也没有有效优化收益或晋升。

第四个已提交任务是Direction自主设计的真实激活差分，不是维护者替它设计研究：

| 名称 | UUID | 执行结果 | 保守GPU秒 |
|---|---|---|---:|
| a03-03 | job-bf9ad94bea91-20261112022402 | Completed/exit0；两轮10个pair仍全部输出不一致 | 2314 |

两轮均重新启动并互换GPU，5类各1题、256-token上限。差分诊断对每轮前256次被观测调用、
两条叶路径分别比较：SSM局部输出与快照均未见差异；conv快照每条叶路径256次都有差异，
conv输出各有一次约5.96e-8差异。此结果只涵盖观测窗口，不认证全部执行或lossless。

Direction继续自主读取stock，定位链式启动所用重叠conv快照窗口与运行时树分支的布局不相容，
提出独立连续窗口修复，完成7个edit和SHA绑定的CPU检查；不再将父快照/寄存器精度差异当作已证实根因。
但窗口问题不足以解释全部早期输出分歧，尤其首差位置3；完整attention/提交与数值正确性仍未知。
修复请求`sp-treeadapter-20261112-a03-04`及其代码、原生作者与CPU回执均保留，**没有提交GPU**。
不能写成“修好了”、controller通过或自主发现有效优化。

### 中断、预算与管理收口

后续接手时，原研究及证据交付进程已经不在；原`result.json`仍为running，未取得正常退出回执。
只按原始birth身份核对进程已消失，退出码未知，不伪造exit0，也不把原running结果改成completed。
中断的具体外部原因未确定；不推断为模型/GPU错误。

该阶段原墙钟已不足以容纳未改动的30分钟任务加20分钟准入预留，可信入口没有提交最后请求，
也没有重置8小时授权。另启一次零工具的同逻辑Master管理评议，直接提供其自身历史、
Direction原生请求和真实反馈；实际结论为defer。该评议不算新研究轮或正常闭环完成。

- 4个真实任务共8100 GPU秒，即2.25 GPU小时；峰值2卡，全部已终止，0活动GPU任务。
- 还有1个已冻结但未准入/未提交的修复请求，不把请求数当提交数，也不向其虚构GPU耗时。
- 未运行独立controller dev gate、token forcing或sealed，未写晋升账本/可信memory。
- 既有坏补丁不保留为基线；源码/反馈恢复均标注自身复用，覆盖复核和管理接续单独归因。

### 可复核入口

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m harness.source_audit --directory logs/tree-adapter-20261112-a03 \
  --history-root logs/tree-adapter-20261112-a01 \
  --history-root logs/tree-adapter-20261112-a02 \
  --resource-state logs/tree-adapter-20261112-a01/resource-state.json \
  --limits-json '{"gpu_seconds":28800,"wall_seconds":28800,"concurrent_gpus":2}' --interrupted
```

审计重数全部attempt的原生回合/工具/CPU和源码请求，验证旧预算不重置、真实CPU作者与GPU源码SHA、
原始配对数据、未提交请求、不可变输入和中断进程身份。`--interrupted`只记录工程中断，
不得将未知退出码或尚未执行的修复变成科学验收通过。

下一阶段需重新批准资源后，由研究角色复核同一修复身份并执行既定最小诊断；
只有局部状态、完整输出和覆盖证据均满足要求，才由Master判断是否交独立controller。
不直接进入Integration、Kernel或RSI，不为了产生正结果绕过正确性。

### 工程验收范围

390项指定CPU回归通过，覆盖源码option/受限角色/续接/原生作者/工具分页/资源/既有研究流水线。
先前联合运行暴露的测试全局状态泄漏已在新增fixture中隔离；另1项未修改的旧子进程继承测试
在本机单独运行仍因UID线程数超过RLIMIT_NPROC=512而报EAGAIN，不提高安全额度、不写成仓库全绿。
真实GPU隔离预检另有实际通过证据，不能由CPU异常推断真实GPU隔离失败或反之。

跨attempt审计共331动作（含4次源码实验请求）、32份CPU额度、12原生回合（含1次零工具管理评议）。
4次请求中3次为候选实际提交、1次未提交；另有1次stock预检，所以总GPU任务为4。
10个进程取得可信正常退出回执；中断阶段6个已登记进程核对消失但退出码未知。
三次原始证据增强交付逐项复核核心反馈未改、原始文件SHA及日志/配对复制；
最早一次producer字段缺失保留，依实际源码快照说明，不追补成当时已有字段。

审计与管理评议不授予Phase4打开许可，CPU与GPU诊断完成也不等于真实树正确性目标完成。

390项相同定向测试在仅含暂存公开内容的干净副本上复验通过；两次完整收尾审计结果一致。
原始产物与角色自身上下文私有归档共9615文件，逐文件双次SHA及压缩包成员回读核对通过，未复制凭据。
归档位置`logs/tree-adapter-20261112-archive/evidence.tar.gz`，SHA256：
`fb5044bf0f24a62bd0b564c5304d2af68c2be6953a22dd2146a227ce5ae8bec2`。
索引`logs/tree-adapter-20261112-archive/inventory.json`，SHA256：
`4f4bd369775429337a66e254f39d4e7ed4f1469fead13703d841c62e94486f03`。
公开只同步工具、测试、计划与摘要；不发布原生轨迹、配对输出、角色工作区或未验证补丁原始产物。
