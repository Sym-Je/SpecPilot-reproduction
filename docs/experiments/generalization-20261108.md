# 作者 final 新数据泛化审计

日期：2026-11-08 UTC；用户已批准执行，阶段内自主安排。状态：执行/独立重放/证据归档完成；发现明确适用边界和质量告警，不是全域泛化通过。
基准：e12537cd213c74b4d1dea2f1677a82ea8bf6ab12。

## 目标及不变边界

检查冻结的作者 final 是否对新请求仍有收益，而非只适配已测30条dev。
不修改 final/stock、46开关、controller裁判或门槛；不读取现有sealed，不晋升、不写ledger/memory。
本审计是额外的公开数据外部确认，不冒充论文原sealed或自主发现。
公开数据可能存在于预训练或作者其他实验中，不能声称作者绝对未见，更不能彻底排除reward hacking。

## 揭盲前协议

- 原五领域 gsm8k/math500/humaneval/mbpp/mt-bench 各20条新题（ID100），
  新五领域中文阅读问答/科学问答/摘要/JSON答案抽取/普通对话各20（OOD100）。
- 来源使用公开上游数据的固定revision和文件SHA；不读取样本决定选哪个数据源。
  优先官方仓库；下载/许可/结构不可用时仅在生成前更正来源并记录，不依据性能换数据。
- 排除作者全部100条dev：源ID、规范化问题完全一致或字符5-gram Jaccard>=0.8均排除；
  新集合内部同样去重。固定seed=261102501，按SHA排序确定性抽样。
- 每领域按输入token排序分短/长半区，各抽10；提前选各半区2条共4条/领域，组成固定40题长度面板。
  主集200题cap2048；面板额外cap256、4096，2048结果复用主集。自然EOS，thinking/turn0/greedy/top_k1。
  短/长是领域内相对分层，不保证绝对长上下文；只接受prompt<=8192token，不裁剪提示。
- 每个cap独立执行null-pre→stock/final→null-post，各两轮fresh双server/物理换卡；
  2条32cap短预热+该条件全集全尺度预热。时序、原始HTTP、GPU/CPU遥测均保存。
- 所有实际测速stock/final输出完整FP32 own-prefix forcing；每cap新AR用于δ与stock mismatch标定。
  总体及各领域分别判定；无首分歧则δ未标定、判证据不足，不套旧值。
- 两物理轮次是同一题cluster，跨cap也是同一题，不把重复当新样本。
  几何均值和双侧95%CI调用既有controller.stats，领域等权；null取前后所有端点最大偏离。
  既有paper-aligned-v1收益/forcing规则不变。逐领域区间为未校正探索性区间；
  不根据“有几个领域显著”声称所有领域总体成立，不作多重比较后的确认性结论。
- 除tok/s，报告stock延迟/final延迟、输出长度比、EOS/截断/失败、各轮和输入长度分层。
  “有收益”与“仍约2.2倍”分开：后者仅描述点估计/区间，不新增追绿门槛。
- 任务质量：数学最终答案规范化匹配（代理）；代码测试在Landlock+seccomp+资源限额独立进程；
  中文/科学问答及JSON抽取exact/F1，摘要ROUGE-L代理。MT/普通对话无可靠语义裁判，明确未评估；
  未结束thinking/空最终答案按未作答，不能以thinking中的答案充通过。任务分数不能代替forcing。
- 一次性盲审：执行器读取私有输入/原始输出；agent只看无题目、无答案、无逐题结果的汇总。
  私有数据位于忽略的logs专用目录，0700/0600，既有sealed完全不访问。
  同UID的约定隔离不是独立第三方保密证明。结果后若修改final，此集转dev，另取新确认集。
- 一次1节点×2 H100/256Gi任务，沿用已确认镜像和WeaverDev/qiji，最长8小时（16 GPU小时）；
  完整执行/科学通过分别记录；超时/缺项不自动扩预算、不重抽题。完整原始证据及失败持久保存。

## 先写验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p7_*.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[23567]*.py'
bash -n exp/generalization_remote.sh
git diff --check
git diff --exit-code e12537c -- controller patches assets/upstream
```

CPU反例先红后绿：全部100题排除/近重复/确定性抽样、输入分层与固定面板、独立cluster、
质量提取/错误代码/秘密读取/网络/子进程/无限循环被阻断、原始证据/缺轮/假换卡/缺预热拒绝。
实际任务后从原始产物独立重放两次，验原始HTTP/计时/forcing绑定、身份与SHA；
agent只读取聚合汇总。失败/证据不足不翻绿，结果不写晋升账本。

## 执行记录

尚未提交GPU。准备阶段a01/a02均在抽样前下载失败，原日志/下载保留：
HF TLS不可达，改官方GitHub固定revision；prm800k用Git LFS pointer核验内容；
OpenBookQA仓库无数据文件，改官方2018档案（SHA256
82368cf05df2e3b309c17d162e10b888b4d768fad6e171e0a041954c8553be46）。
Dolly官方GitHub不含数据且HF不可达，摘要/普通对话改官方Stanford Alpaca固定revision；
摘要参考为合成参考、ROUGE-L仅代理，对话为无额外输入的普通指令首轮，不声称多轮泛化。
上述变更均早于抽样和任何性能结果；未因测量表现换源。
最终revision、抽样SHA、源码pin、完整命令/UUID和结果待执行后追加。

### 已通过的提交前验收

- a03下载已全部成功，但CMRC官方文件采用list/context_text/query_text结构，与SQuAD不同；
  抽样活动在完成前停止，无任何性能结果。加schema红测试再修复adapter，a04复用逐文件SHA核验的原始源，
  不改seed，不重新选取表现好的题；全部准备失败日志保留。
- a04准备完成，200题/10领域各20，固定40题/领域4题；全部100条作者dev与集合内规范化/近重复校验通过，
  独立retokenize一致，源文件SHA全部通过；40/40代码参考解在隔离器内通过。
- 数据SHA256=`7c179e5d0f84fb87b0ebcdb78a70248f15c01e51d9668ee1b72da5cdcb514486`。
  私有输入`logs/generalization-data-20261108-a04/`；只读聚合准备/状态`logs/generalization-public-20261108-a04/`。
  原始下载版本/文件SHA见该公开状态目录`preparation.json`，包含9个公开来源、9个固定文件，
  该manifest SHA256=`b78a4ba47c446e8c5490b3d4c9372ab87fa8358d5bb28b1a7eb875e380f07eaa`。
  许可标签为来源仓库/数据发布说明索引，不以代码许可证替代数据条款；不在Git再分发原始题目/答案。
- 实际prompt为59–636 token；短/长仅为领域内相对分层，**不覆盖真正长上下文**。
  长度面板比较同40题，2048点复用主集对应题，不把不同题总体误当长度因果对照。
- 新旧136项CPU回归通过，包括真实HTTP合成集成、缺预热/假换卡/原始HTTP篡改被拒；
  代码隔离使用Landlock+seccomp只读openat/禁网络/禁子进程/限额，参考解和恶意反例均测试。
  同进程代码任务测试是功能代理，不是针对有意伪造测试完成标记的恶意代码的形式化正确性证明。
- controller、patches、作者配置/原dev文件未修改；原始产物不提交Git。
  CLI当前help四个调度参数可用，凭据仅验证结构；2 H100、最长8小时/16GPU小时预算，任务名查重待核对。

### 唯一GPU提交 a01

- 2026-11-08 10:31:54–55 +08:00，create一次返回code=200/data=None；按精确名查重total=1，
  UUID=`job-611d30b86458-20261108103155`，name=`specpilot-generalization-20261108-a01`。
  请求WeaverDev/qiji，服务端实际queue=proj-31；初始Pending不是进程启动或GPU验收通过。
- source pin=`c085f8bc069228c9dd156aac578f9d99ae6427f4`，
  `logs/generalization-prep-20261108-a01/source.tar` SHA256=
  `85b31e18789c9a056e2f7e064d81e7c5859af1ed23c7bb8d3e415d277d411467`。
- 私有运行输出`logs/generalization-run-20261108-a01/`，agent只看公开状态
  `logs/generalization-public-20261108-a04/`，生命周期/提交回执`logs/generalization-prep-20261108-a01/`。
  完整最终命令留`submit.txt`及NorthJob生成的`RUN/specpilot-generalization-20261108-a01/`，无凭据入Git。

### a01失败与执行位置修正（尚无性能结果）

- a01在远程CPU自检处，隔离器正确程序被拒、死循环也提前拒；**未进入真实runner、未启动模型server、
  未生成配对测量目录**。远程具体worker stderr当时丢弃，不能未经证据断言是某个内核调用。
  node204，平台最终Failed/Pod Failed/exit1，Job retryCount=2；原文件保护阻止平台重试覆盖。
  原始remote.log、失败平台状态和空监控失败均保留，不当科学拒绝或测量结果。
- root容器以0600写公开日志，导致host UID5084监控PermissionError。只恢复两个公开诊断文件可读，
  不开放私有数据；新入口仅公开聚合文件0644，私有根仍0700。
- 本机同SP环境下root与普通身份隔离器合成测试通过，40参考解普通身份已过。
  **先于任何性能结果**将代码执行与质量评测固定移至本机CPU安全隔离器；GPU任务只做配对/forcing。
  本机controller式子进程仅读私有原始结果并发布汇总，agent仍不看样本。
  远程不再执行模型生成代码；记录能力探针和纯合成worker诊断，不将安全不可用“降级成无沙箱运行”。
- 新显式`--defer-quality`仅标`gpu_work_complete=true / scientific_acceptance_complete=false`；
  远程退出后必须完成本机质量/独立证据重放，才发布完整result。新增pending非通过反例先红后绿。
  新旧137项CPU回归通过；controller/最终实现/200题及cap/配对/统计判据不变。
- 下一尝试a02用新公开状态目录，复用同一个dataset SHA，不重抽题、不读取部分性能结果；
  新源码pin/命令先冻结并查重。此前短失败资源额外计入，不将预算或“单次提交”记录回改为零失败。

### a02执行登记（当时状态，现已结束）

- 2026-11-08 10:42:21 +08:00 create一次返回code200/data=None，精确名唯一，
  UUID=`job-6b21065b7a0e-20261108104221`；node244，02:42:54 UTC容器启动。
  资源/镜像/WeaverDev/实际proj-31/模型只读挂载/默认hostNetwork=false经服务端核对通过。
- pin=`c39c7af0b244e2669bb307ec5684c4165f16d6f6`；源码档案
  `logs/generalization-prep-20261108-a01/source-a02.tar`，SHA256=
  `c19da8e1726c92cccea411bc0a708eb8e0c2024e427d30069a84e03752c67a5b`。
  私有运行`logs/generalization-run-20261108-a02/`；公开状态`logs/generalization-public-20261108-a05/`。
  仍使用原a04 dataset SHA，未重新抽样；ID仅指同基准族新题，模板另行构造，不宣称严格同分布或论文原协议。
- 新节点纯合成探针确认kernel5.15/Landlock ABI1/libseccomp存在；具体失败为隔离后
  `ctypes.util.find_library → _findLib_gcc → tempfile.NamedTemporaryFile`无法写临时目录。
  这定位新节点环境的setup次序问题，不把它误写为内核缺Landlock，也不据此伪称已恢复a01被丢弃的stderr。
  本次固定本机安全评测，不在运行中改源码/放开写权限或重新执行候选代码。
- 远程7项非代码执行协议测试通过；本机root9项完整测试通过。公开events已记录进入2048cap前置null第一轮。
  **提交成功、容器启动、完整测量与科学验收分别记录**；目前只确认前两项，未宣称新数据收益或质量通过。
- 完整命令/回执`submit-a02.txt`、`lookup-a02.txt`、`accepted-spec-a02.json`，
  生命周期`lifecycle-a02.*`和`watch-a02.console`均在准备目录；监控只看公开状态，无样本/逐题结果。

## 最终结论

**作者final并非只对原30题有效，但也不是对所有数据都约2.2倍。**
同基准族100条新题仍有约2.17倍收益；新领域100题总体约1.53倍，其中中文阅读短回答是明显减速反例。
任务质量有需确认的告警，不能宣布质量非劣、数学lossless或已经排除reward hacking。
这不是作者故意reward hack的证据：短回答、长一些的prefill、语言和草稿接受率等因素相互混杂，
尚无隔离变量/profile证据可以归因。公开题也不能保证作者或预训练绝对未见。

### 执行和完整性

- 成功任务唯一UUID=`job-6b21065b7a0e-20261108104221`，node244，
  02:42:54–07:04:34 UTC，共4小时21分40秒。Job Completed/Pod Succeeded、容器与脚本exit0。
  522个监控快照仅见一个Pod UID、容器restart0；Job retryCount字段未设置，不把它写成平台明确报告0。
- 2 H100 80GB HBM3、driver535.154.05；固定镜像、WeaverDev/qiji/实际proj-31，
  SGLang0.5.20/torch2.13.0入口断言通过。源码始终为c39c7af的controller/exp/harness/assets；
  运行期间只有文档提交6f2fb9b，代码逐文件身份与源码tar一致，未改final/stock/46开关或模型。
- 三cap共9会话/18轮fresh双server/物理换卡；1680个正式pair/3360臂行，
  全尺度预热另1680 pair、短预热36 pair。仍只有200个不同请求；额外cap只是同40题重复条件。
- 全部实际测速的1120条stock/final输出，加280条新AR，共1400条完整own-prefix评分；
  独立checkpoint FP32 head预检通过。先完成所有计时，再评分，不用重新生成候选替代测速输出。
- GPU阶段结束后两卡均0MiB/0%，全部端口释放。之后本机CPU隔离质量与证据验收完成于07:18:27 UTC。
  40/40参考代码通过；模型代码只在本机Landlock+seccomp+资源限额下执行，没有无沙箱降级。
- a01 Failed/retryCount2及所有准备失败保留；a01未进入真实runner，不与a02合并或当性能失败样本。

### 2048 cap主要结果（200新题）

以下都是final/stock输出速率比，suite等权、request-cluster分层bootstrap10000次/seed0的双侧95%CI。
物理轮次先在请求内平均log比，不把两轮当两倍独立题目。

| 请求分组 | 不同请求 | 几何平均 | 95%CI |
|---|---:|---:|---|
| 全部10领域 | 200 | **1.823022×** | **[1.792292,1.854873]** |
| 原5类基准族新题（ID） | 100 | **2.171842×** | **[2.129914,2.216151]** |
| 新5领域（OOD） | 100 | **1.530226×** | **[1.487339,1.574006]** |

ID仅指同基准族，不保证新模板与作者模板严格同分布；不与论文原sealed的2.13×直接等同。
整体整请求延迟比stock/final=1.802438× [1.739404,1.866364]，不是只看tok/s。

| 领域（各20题） | final/stock | 未校正探索性95%CI |
|---|---:|---|
| GSM8K | 2.145462× | [2.084938,2.204475] |
| MATH500 | 2.264338× | [2.157002,2.395695] |
| HumanEval | 2.175806× | [2.085570,2.275662] |
| MBPP | 2.151019× | [2.039878,2.279429] |
| MT-bench | 2.125275× | [2.048793,2.206442] |
| **中文阅读问答** | **0.513279×** | **[0.464119,0.573095]** |
| 科学选择问答 | 2.110593× | [2.015048,2.208030] |
| 摘要 | 2.047772× | [1.961413,2.130847] |
| JSON答案抽取 | 1.826032× | [1.743851,1.919535] |
| 普通指令首轮 | 2.071239× | [1.964360,2.173694] |

中文组stock/final平均输出72.65/72.30 token，40/40轮次输出均自然EOS；
整请求延迟比stock/final=0.514568，即final约需1.94倍时间。不是只因final输出更长而显得慢。
其他9领域本批均有收益，不以总均值掩盖中文反例，也不把单域探索性CI当多重比较校正后的全域定理。
输入短/长半区整体分别1.813080×/1.833020×；这只是59–636 token的相对分层，不是长上下文测试。

### 同40题长度面板

| cap | 同40题final/stock | 95%CI | stock/最终的stop、length（各80轮次输出） |
|---|---:|---|---|
| 256 | 1.753500× | [1.706443,1.800837] | 38/42；40/40 |
| 2048（复用主集对应题） | 1.790064× | [1.742621,1.841405] | 72/8；72/8 |
| 4096 | 1.799322× | [1.760764,1.837515] | 72/8；72/8 |

stock/final平均实际输出分别196.65/199.375、493.50/552.425、698.30/757.225 token。
4096条件每臂8/80条轮次输出确实触顶，完整评分包含这些长输出；不是声称每题都生成4096。
同4道中文面板题三cap速率比约0.4263/0.4274/0.4282，增加上限没有消除该场景减速。
不能把全200题的1.823与40题4096结果直接当cap因果对比；也不因区间重叠就宣布cap效果完全相同。
256条件约一半输出截断，HumanEval/MBPP都0/4答对，不能把其token速率当作已完成任务的实用收益。

### 当前null和真实正确性

| cap | null-pre点估计 | null-post点估计 | 最大端点noise | 收益门槛 |
|---|---:|---:|---:|---:|
| 2048 | 1.002963717 | 0.999033047 | 0.3498892% | 3% |
| 256 | 0.998312027 | 0.997559412 | 0.3413052% | 3% |
| 4096 | 0.994760475 | 1.005903327 | 0.7115808% | 3% |

前后两个null均纳入各自cap的noise，没有挑会话、复用旧noise、要求全宽<0.2%或覆盖1。
4096前后有方向相反的偏移，不能因CI窄就断言没有系统漂移；当前收益/中文减速量级远大于null尺度。
这些CI描述预声明请求统计，不能消除所有系统误差或证明精确论文数字。

| cap（每个物理轮次相同计数） | 新标定δ | stock mismatch | final mismatch | 全局大margin事件 |
|---|---:|---|---|---:|
| 2048 | 0.25 | 851/107412 | 851/106898 | 0 |
| 256 | 0.25 | 46/7866 | 58/7975 | 0 |
| 4096 | 0.25 | 224/27932 | 252/30289 | 0 |

6个全局round判定的rate/event均未触发，三个总体性能门槛也通过。
分域更严格局部δ下，4096 HumanEval每轮有1个未解释大margin事件，stock本身也有1个，
未触发既有event判据；不能把全局δ=0.25下零事件写成所有局部阈值均零事件。
中文4题长度面板在256/4096没有stock/AR首分歧，局部δ无法标定，正确性标**证据不足**；
没有套旧δ。2048中文20题局部δ可标定且通过，全部面板输出仍已完整FP32评分。

**`joint_acceptance_passed=true`仅指既有总体性能＋forcing联动规则，
不代表所有领域提速、任务质量非劣或数学lossless。** promoted=false、ledger_eligible=false，账本/记忆未写。

### 任务质量及风险

| 2048条件，各20题 | stock | final | 解释 |
|---|---:|---:|---|
| GSM8K最终答案匹配 | 17/20 | 19/20 | 规范化匹配代理，不是额外lossless证据 |
| MATH500最终答案匹配 | 13/20 | 13/20 | 同上 |
| HumanEval测试通过 | 18/20 | 18/20 | 配对差CI[-0.15,0.15]，不是证明质量等价 |
| MBPP测试通过 | 15/20 | 15/20 | 配对差CI[-0.15,0.15] |
| 中文答案token-F1 | 0.971685 | 0.971685 | 不是“精度97.17%”的严格语义结论 |
| 科学答案token-F1 | 0.835256 | 0.860534 | 代理指标 |
| 摘要ROUGE-L F1 | **0.322758** | **0.302970** | **下降告警** |
| JSON schema＋答案F1 | 0.937059 | 0.987059 | 非法schema记0 |
| MT-bench/普通指令 | 未评分 | 未评分 | 无可靠语义裁判，不能宣称质量不降 |

摘要配对差=-0.0197875（约-1.98点），未校正95%CI[-0.0420161,-0.0027901]。
参考摘要来自合成数据、ROUGE-L只度量参考词序匹配，而且有多域/多cap比较，
这是值得独立确认的告警，不足以单独断言语义质量退化或作者reward hack。
4096面板HumanEval stock3/4、final2/4，配对差CI[-0.75,0]，样本太少，不能忽略也不能夸大。
本活动没有经过功效设计的语义非劣检验；不能把“CI含0”“同样答对数”或forcing通过当质量不变证明。

### 独立验收与归档

- 本机冻结评测器一次，从同一原始证据再启动两个独立CPU进程重算，三个报告JSON逐字节相同。
  `result.json`、`replay-01.json`、`replay-02.json`均在公开a05目录，SHA256均为
  `df269e986755c02b3d94810e76d75315c8572cbb6a28e4acc1b264c7600aa3a3`。
- 最终137项新旧CPU回归、shell语法/diff检查通过；源码相对运行pin无变化，
  controller/patches/作者配置和dev相对e12537c无变化。旧dev 1223文件SHA重新核验全部通过。
- 本活动**10312文件、598919466字节**的成功/失败/源快照/数据来源/原生HTTP/评分/任务质量/生命周期证据，
  清单`logs/generalization-evidence-20261108-a01.sha256`，SHA256=
  `2fc0112af7d18e7fa368fa15aa88138e0afaceef4b1cfa9b0b82dd23c2757675`，全量核验通过。
  清单及私有产物仅受控sudo/controller读取，不输出题目/答案/逐题结果，不上传GitHub。
  核验日志`logs/generalization-evidence-verification-20261108-a01.log`；Git只记录代码、协议、身份、校验值和聚合决策。

只读复核示例（必须新输出路径；需使用c39c7af冻结源码，CUDA显式不可见）：

```bash
sudo -n bash -c 'cd /gpfs/users/jixinpeng/SpecDec/SpecPilot; source harness/sglang/env.sh; CUDA_VISIBLE_DEVICES="" "$SP_PY" -B exp/generalization_audit.py --private /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/generalization-run-20261108-a02 --out /tmp/generalization-replay-NEW.json'
sudo -n bash -c 'cd /gpfs/users/jixinpeng/SpecDec/SpecPilot; sha256sum -c logs/generalization-evidence-20261108-a01.sha256 > /tmp/generalization-sha-NEW.log'
```

本阶段任务已完成，不需要继续提交或为中文结果调参追绿。下一大步骤建议先向用户提出
中文短回答性能与摘要/长代码质量告警的独立确认方案，再决定与正式sealed的先后顺序；
这不是新增的论文硬门槛，不自动进入sealed/RSI。如果之后改final，此审计集转dev，必须换新确认集。
正式sealed仍须按事先定义的论文/业务范围抽样，不能根据本次结果只挑有利领域，再宣称全域泛化。
