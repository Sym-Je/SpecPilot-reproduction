# 中文短答减速：匹配因素与执行阶段诊断

状态：执行、补采、阶段归因、独立重放、归档完成；验证循环工作量是匹配探针中的主要差异，非单纯短输出。基准496ab11。

## 目标与边界

固定作者stock/final及46开关，不改controller/patches/作者配置，不碰sealed/RSI/ledger/memory。
区分语言相关、实际输出长度相关与输入处理/草稿/验证开销的证据；不是训练模型或追论文数字。
匹配实验只能识别本合成工作负载中的条件效应，不等于证明中文语言本身是普适原因。

## 预声明流程

1. 十二个独立合成事实卡，每张生成语义对应中英文任务，短答/详细答两种指令。
   输入完整chat模板精确512/1536token，语言对应的无关背景padding，不裁剪事实和问题。
   事实卡为独立cluster，语言/长度/物理轮次均为同卡重复，不冒充更多独立样本。
   合成匹配不是自然文本分布，padding本身和翻译差异是限制。
2. 自然组：12卡×2语言×2输入长度×2回答指令=96请求，2048cap自然EOS。
   记录实际输出分布、EOS/截断、短/长指令是否真正拉开长度；不因不遵从指令删样/换题。
3. 固定长度组：同卡短答指令的48请求，分别精确生成64/256/1024token。
   显式ignore_eos=true，其余greedy/top_k1不变；是长度干预，**不能当自然任务收益或质量结论**。
   EOS后的延续可能改变token难度与草稿表现；长度对比不能单独证明“只有固定开销”这一机制。
   解释时核对EOS后延续与不同预算的共同前缀稳定性，只作为辅助诊断，不替换三主要端点。
   每个条件null-pre→stock/final→null-post，各两轮fresh双server/物理换卡，2短预热+全集全尺度预热。
4. 三主要条件对比：固定64token的中文/英文加速比之比；固定1024/64token的加速比之比；
   固定1536/512输入的加速比之比（跨三个输出预算等权）。以12事实卡做cluster，
   调用controller.stats，普通95%与三项Bonferroni同时区间；区间跨1标证据不足。
   每条件直接配对请求延迟比stock/final为主；token速率、轮次/细分格为诊断。
5. 正式计时结束后另起两轮fresh/换卡，只做诊断探针：固定首卡、512输入、中英文，
   1token往返作为“输入处理+首次解码+HTTP”代理，**不叫纯prefill**；
   64/1024token使用公开/start_profile、/stop_profile采CPU/GPU trace，不读作者实现。
   保存OpenAPI schema、所有成功/失败调用、trace和SHA，profile耗时绝不混入正式性能。
   仅明确命名scope用于阶段归因，重叠scope不相加；未知GPU kernel不猜成draft或verify，
   无阶段scope则明确“不能分解”，保留未归因比例。final spec_verify_ct仅作未验证计数，不直接当接受率。
6. 无引擎修改，本阶段不新增语义非劣/lossless宣称；固定长度不是正常完成任务。
   复用已验收裁判计时/统计，不在harness另设晋升规则。本次不晋升、不写账本。

## 预算及停止规则

一次普通bash NorthJob：1节点×2H100，256Gi，最长8小时（16GPU小时），沿用已确认digest镜像、
WeaverDev/qiji/原toleration。无RDMA/hostNetwork，不因结果不好扩样。
profile公开接口或权限不可用只记能力限制，不改引擎/不无证据分摊时间；profile总产物上限4GiB，
达到上限停止额外profile并报告缺项，不删除已生成证据。故障/缺轮不能报执行通过。

## 先写验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p9_diagnosis.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[2356789]*.py'
bash -n exp/diagnosis_remote.sh
git diff --check
git diff --exit-code 496ab11 -- controller patches assets/upstream
```

先红后绿：因素完整/精确输入长度/无截断、自然和强制模式不能混淆、实际固定输出必须相等、
独立事实卡cluster、对比方向/Bonferroni区间、原始HTTP与换卡/预热证据、trace重叠/未知scope不误归因。
每步验收后继续；提交前当前help/查重/完整命令与总GPU展示，create一次，code200+精确UUID。
结果两次独立进程重放一致，原产物SHA归档；阶段结束更新README/交接并推送私有origin。

## 准备验收

160项CPU回归、shell语法/diff检查通过；controller/patches/作者config/dev相对496ab11无变化。
数据精确512/1536输入和独立进程retokenize通过，96自然请求/48固定请求每预算、12独立事实卡。
私有数据`logs/diagnosis-data-20261108-a01/`；公开聚合`logs/diagnosis-public-20261108-a01/`；
准备日志`logs/diagnosis-prep-20261108-a01/`。dataset SHA=
`0d92ecbdd62cc57473fd97f692183013314f4d271ead9fa30e739fea8eab4b30`。
现有CLI3.3.11 help及凭据结构已核对，不输出凭据、不升级；尚未提交GPU。

## 唯一GPU提交a01（运行中）

- source pin=`629eb4268dcf49bed41e1266f0f159426dc7444a`；
  `logs/diagnosis-prep-20261108-a01/source.tar` SHA=
  `2411dcc0208573d3ab8af7203948374ebc5816884093bb580cafa9f199401a67`。
- 精确名查重total0，create一次返回code200/dataNone，按精确名唯一解析
  UUID=`job-89c6c8cd6c11-20261108200750`，name=`specpilot-diagnosis-20261108-a01`。
- 2026-11-08 12:08:18 UTC在node244启动。服务端2H100/256Gi、原digest、只读models、
  禁hostNetwork、toleration核对通过。项目WeaverDev，请求namespace/queue=qiji、实际queue=proj-31。
- 完整命令`logs/diagnosis-prep-20261108-a01/command.txt`，回执`submit.txt`与精确查询`lookup-after.txt`；
  模板`RUN/specpilot-diagnosis-20261108-a01/specpilot-diagnosis-20261108-a01.yaml`。
- 私有运行`logs/diagnosis-run-20261108-a01/`，agent只看公开a01聚合状态；
  生命周期`logs/diagnosis-prep-20261108-a01/lifecycle.*`。尚无科学验收，不重复create，不改运行代码。

## 正式计时完成；profile采集器修复（协议修订，仅辅助证据）

- 原任务Job Completed/Pod Succeeded/容器与脚本exit0，node244，12:08:18–17:34:34 UTC，
  5h26m16s；所有四条件/十二会话/二十四轮计时及前后null验收完成，原始证据不改、不重跑。
- 初次16个profile探针均JSONDecodeError。JSON-only NativeClient在解析非JSON成功响应前抛错，
  原始失败载荷未保存，不能凭异常猜出具体响应文本；OpenAPI schema和原失败记录保留。
  原1token代理仍有效；初次profile不能记为已获得阶段trace。
- 修复仅新增`exp/diagnosis_profile.py`独立ProfileClient：原生profile start/stop可接受JSON/纯文本，
  记录HTTP状态/content-type/原始字节base64与SHA；不修改controller.NativeClient或原计时源码。
  只在公开schema支持时开启detailed_annotations，未知scope仍不猜归因。
- 163回归通过；新增`diagnosis_profile_remote.sh`仅补采原定两轮fresh/换卡的profile探针，
  同一原始dataset/模型/引擎/46开关，不运行正式null/candidate测量。
  原始主报告仍由629eb42冻结源独立重放，修复profile另有source pin和单独报告，不能回填覆盖旧失败。
- 原计划一次提交因采集器错误修订为额外一次profile-only任务，**不是追加独立性能样本**。
  原任务已结束才提交；仍最多同时2GPU，补采最长1小时。
  原5h26m16s＋补采上限1小时（另有短初始化）仍小于原8小时/16GPU小时总预算，不扩大资源上限。
  新任务同skill当前help/唯一名查重/完整命令与2GPU展示/code200+UUID规则。
- 辅助EOS后延续和跨预算共同前缀审计只读原始输出、仅发布聚合，源SHA单独绑定；
  不改变三主要端点/样本/区间，也不把输出前缀相同当lossless证明。

### profile-only补采提交

- 当前help和精确名查重total0后create一次，code200/dataNone，精确唯一UUID=
  `job-72e589efab39-20261109014404`，name=`specpilot-diagnosis-profile-20261108-a01`。
  2026-11-08 17:44:24 UTC在node244启动（UUID日期是服务端+08时间，实验日期仍按UTC）。
- source pin=`74afcee9077baa7da7c60113673e8b7d34fa1e83`，profile-source.tar SHA=
  `095da269bae0ba8d647ed6c2d21d01914e43118e305f20ae0325482cd53955bf`；
  新私有`logs/diagnosis-profile-run-20261108-a01/`，新公开`logs/diagnosis-profile-public-20261108-a01/`。
- 服务端原digest/2H100/256Gi/禁hostNetwork/只读models已核对，项目WeaverDev，实际queue=proj-31。
  完整命令`logs/diagnosis-prep-20261108-a01/profile-command.txt`，回执`profile-submit.txt`，
  生命周期`profile-lifecycle.*`，模板`RUN/specpilot-diagnosis-profile-20261108-a01/`。
- 原正式result/replay-01/replay-02已逐字节一致，SHA=
  `f998dcadd38d07647256898d6719184f21d351bd3957847e48dd63de8183af4b`。
  补采开始有成功trace，尚待完整验收，不把原16失败翻成成功或合并新正式性能样本。

### 补采完成与CPU阶段标签适配

- 补采16/16成功，Job Completed/Pod Succeeded/脚本与容器exit0，17:44:24–17:56:10 UTC，11m46s。
  原始HTTP证明32次start/stop均HTTP200，响应没有Content-Type，内容为纯文本
  `Start profiling.\n` / `Stop profiling. This will take some time.\n`；支持采集器不兼容诊断。
- 两任务总占卡11.267778 GPU小时（原16GPU小时预算内），同时最多2GPU；两卡最终0MiB/0–1%，端口释放。
- 原保守固定scope白名单未识别带形状的动态标签，故初次profile报告的GPU阶段未归因100%保持原样。
  真实trace已公开标注`step[DRAFT ...]`、`step[VERIFY ...]`、`step[EXTEND ...]`，
  新增CPU-only `exp/diagnosis_trace.py`只对这类明确语法做阶段关联：同线程scope包含的CPU launch，
  再按原生correlation绑定GPU kernel。重叠不同阶段、未知标签或不明确correlation全部保留未归因。
  不从kernel名称猜阶段，不回改trace，不把累计GPU kernel时间当完整请求耗时占比。
- 这是观察运行时标签后的辅助诊断registry，不是修改三主要端点/晋升门槛；独立源码SHA和Git pin冻结，
  四项合成红/绿反例验证嵌套/未知/歧义不误归因；完整167项CPU回归通过。

## 最终结论

**不能再把中文减速只解释为“回答太短，固定成本摊不开”。**
精确匹配输入和实际64token输出后，中英文的final收益仍明显不同；允许生成到2048的长答指令中，
中文也未恢复收益。单个预选匹配探针的阶段trace把主要GPU工作差异定位到VERIFY循环。
这不是证明所有中文必慢，也没有确认哪一个作者开关或实现存在错误。

### 三个预声明主要对比（12独立事实卡）

记S=stock请求耗时/final请求耗时，S>1表示final快。以下是**收益系数之比**，不是两种语言原始速度之比。
同时区间按三项Bonferroni，每项双侧98.333333%；所有语言/输入/物理轮次先在同一事实卡内聚合。

| 对比 | 点估计 | 同时区间 | 解释 |
|---|---:|---|---|
| 固定64token，S中文/S英文，跨两输入长度等权 | 0.408755 | [0.394764,0.424361] | 匹配长度后仍有语言/请求内容相关差异，不是只因实际输出更长 |
| 固定实际输出，S1024/S64，跨语言/输入等权 | 1.794214 | [1.650111,1.961477] | 强制长输出收益提高；含EOS后延续，不能单独解释为固定成本摊销 |
| S输入1536/S输入512，跨语言/三输出预算等权 | 1.024434 | [0.942193,1.105345] | 未确认总体输入长度主效应；不等于输入处理无成本 |

单一事实卡模板的12个数值变体，不是12个领域或自然请求总体；翻译、padding与语言共同变化，
只能称本匹配工作负载中的条件证据，不能宣称已隔离语言的所有语义/分词/任务因素。
bootstrap区间描述这些条件下的样本变化，不消除全部系统误差。

### 直接配对条件（普通95%区间）

| 模式 | 输入token | 实际输出/生成规则 | 中文S | 英文S |
|---|---:|---|---|---|
| 固定长度 | 512 | 精确64 | 0.619186 [0.599756,0.635552] | 1.490048 [1.448480,1.539291] |
| 固定长度 | 1536 | 精确64 | 0.566826 [0.547888,0.586515] | 1.409761 [1.371058,1.450099] |
| 固定长度 | 512 | 精确256 | 0.748427 [0.721349,0.778876] | 1.926191 [1.807651,2.040659] |
| 固定长度 | 1536 | 精确256 | 0.755788 [0.677439,0.852342] | 2.199215 [2.024388,2.374797] |
| 固定长度 | 512 | 精确1024 | 1.091313 [0.936444,1.304707] | 2.354244 [2.089402,2.679151] |
| 固定长度 | 1536 | 精确1024 | 1.220681 [1.101417,1.380469] | 2.436188 [2.201385,2.677627] |
| 自然EOS允许，长答指令 | 512 | 两臂均2048触顶 | 0.665814 [0.611591,0.720716] | 2.185057 [2.049487,2.327667] |
| 自然EOS允许，长答指令 | 1536 | 两臂均2048触顶 | 0.656750 [0.609598,0.706371] | 2.318001 [2.196065,2.434580] |

即固定64token时中文final耗时约stock的1.62/1.76倍，而英文final更快；
长答指令均生成2048时，中文final仍约需1.50/1.52倍时间，不能只用“太短”解释。
但长答组每臂96轮次输出全部触顶，**不是已经完成任务的实用收益或语义质量验证**。

短答指令也不保证实际短：中文512输入时stock/final实际平均711.25/480.50token，
1536输入388.75/401.58；英文约92token。不能把指令标签当作实际长度匹配，
更不能把这个合成中文短答组直接替代先前真实CMRC约75token的反例。

### 强制长度的重要局限：EOS之后发生了什么

- 固定64时两臂均0/96轮次输出遇EOS；这里的中英文收益差不是EOS后的延续造成。
- 固定256时stock62/96、final68/96遇EOS；EOS后token占36.9303%/38.5661%。
- 固定1024时stock88/96、final94/96遇EOS；EOS后token占71.5820%/75.0122%。
  所以“强行生成更久就变快”不能证明真实任务只需拉长回答，也不能证明唯一原因是固定成本。
- 各臂64-vs256、64-vs1024四组比较均96/96共同前64token相同。
  这支持预算干预未改变本批前64token，但**不是stock/final互相等价或数学lossless的证明**。

### 阶段定位：差异主要在验证循环，而非输入扩展

仅一个预选合成事实卡、512输入、精确64输出；下表是两物理换卡轮次的均值。
成本单位是**累计GPU kernel毫秒**，不是HTTP请求延迟，也不是端到端墙钟时间的可相加百分比。

| 臂/语言 | EXTEND kernel ms | DRAFT kernel ms | VERIFY kernel ms | VERIFY标签次数 |
|---|---:|---:|---:|---:|
| stock中文 | 44.774 | 32.969 | 354.343 | 14 |
| stock英文 | 44.901 | 28.277 | 303.833 | 12 |
| final中文 | 71.698 | 37.349 | 774.647 | 38 |
| final英文 | 71.849 | 10.603 | 204.341 | 10 |

- final中英文EXTEND几乎相同；VERIFY工作量却明显不同。final每次VERIFY标记对应的
  累计kernel时间约20.39/20.43ms，主要差异表现为调用次数38对10，而不是每次中文验证突然更贵。
- 在这个探针里，中文final相对stock的验证工作增加，英文则减少，支持把下一层诊断聚焦在
  草稿/树/TLV验证循环为什么需要更多次VERIFY，而不是只盯prefill或回答长度。
- **没有把原生spec_verify_ct直接当统一接受率。** 标签次数也不等于已审计的accepted-token指标，
  尚未分离草稿接受分布、树策略、TLV语义和具体开关的因果贡献；不据此判定某补丁失效。
- 精确阶段语法加同线程launch/correlation归因后，16个trace未归因kernel时间占1.083–1.201%。
  未知/歧义仍保留；原严格白名单报告的100%未归因文件不覆盖，CPU适配结果另存。
- 1token代理：stock中文74.84/75.61ms、英文81.28/82.42ms；final中文88.11/86.20ms、
  英文88.93/89.29ms。它包含输入处理、初次解码及HTTP，且仅1题，不叫纯prefill或总体估计。

### 验收、失败与资源

- 12正式会话/24物理轮次，1440正式pair/2880臂行、1440全尺度预热pair、48短预热pair；
  96自然请求变体、每预算48固定变体，但主要统计独立单位始终12事实卡。
- 自然/64/256/1024的前后null全部纳入，noise分别0.335057%/0.955354%/0.072781%/0.197837%。
  不挑null、不要求CI覆盖1或全宽0.2%。不把诊断变成新论文验收门槛。
- 167项最终CPU回归、shell语法、diff检查通过；controller/patches/作者配置与dev相对496ab11无变化。
  原正式计时源码保持629eb42，profile修复保持74afcee，CPU阶段适配保持独立版本，不混淆执行身份。
- 原任务648生命周期快照、补采18快照各只见单Pod UID/restart0；Job retryCount均未设置，
  不伪称服务端明确无平台重试。两个任务不重叠，按容器时长折算11.267778GPU小时，低于原16预算。
- 初次profile16个JSON解析失败及原始缺失响应字节的局限保留；补采32次HTTP原始字节/SHA、
  16完整trace与source信息保留。一次公开汇总普通UID写入因root0755目录被拒，随后仅用受控发布器
  写公开聚合，未开放私有数据权限。没有修改失败JSON或重测正式数字。
- 两卡最终显存0MiB，利用率0–1%，端口释放；所有GPU监控/CPU重放进程均结束。
  未sealed、未RSI、未写ledger/memory、未晋升；没有新增语义非劣或数学lossless结论。

### 版本、重放与归档

- 正式源629eb4268dcf49bed41e1266f0f159426dc7444a及source.tar SHA见提交记录；
  正式result/replay01/replay02逐字节一致，SHA=
  `f998dcadd38d07647256898d6719184f21d351bd3957847e48dd63de8183af4b`。
- 补采源74afcee9077baa7da7c60113673e8b7d34fa1e83及profile-source.tar SHA见补采记录；
  profile result/replay01/replay02逐字节一致，SHA=
  `0a11c217cfe8736d41aa1c22a54d8c8996481bd896b68cd97f0f39e5536eb87a`。
- EOS辅助审计独立重放一致，SHA=
  `1cd84c1d187f89d87fc765001054b0560aa7beddf81f33b6d02680630edbc66c`。
- CPU阶段mapper pin=`d7a5fd2c0558c2d939546807d7451575bae12ff4`，trace-source.tar SHA=
  `b3b19e600797960b2fe79b916aba088438749c0d0a4eb6bb78b664bd6c85bacb`；
  trace-stage-audit/replay逐字节一致，SHA=
  `e6e6a99ee81f18aee0644259b6d12bc4c241fdab07397f5803e97c57b5066e64`。
- 所有可用成功/失败、源快照、HTTP、原始计时/trace、生命周期证据6509文件/507041718字节；
  清单`logs/diagnosis-evidence-20261108-a01.sha256`，SHA=
  `3e970173a509dfe501f70db89f8ea4b77265da52cd24b9b18ae7444624812aee`，6509逐文件核验全过。
  核验日志`logs/diagnosis-evidence-verification-20261108-a01.log`。前阶段5928文件SHA复验也全过。

只读聚合入口：`logs/diagnosis-public-20261108-a01/`、`logs/diagnosis-profile-public-20261108-a01/`。
不要手工读私有逐题输出、不要重跑已完成任务、不要为追绿新增样本或改final。
第一层机制定位完成；下一大阶段先报方案由用户决定，可继续审计验证循环，也可回到论文规定工作负载主线。
