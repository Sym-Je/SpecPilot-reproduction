# 第5步：真实校准与token-forcing裁判

日期：2026-11-08（Asia/Shanghai）。状态：执行前登记。
基准`e6e55a6f4c3535c8f0515ee0654e95fb2d684b4f`。用户明确允许本阶段修改controller，
授权仅限校准与正确性验收；阶段内部自主调试，不自动sealed/RSI/正式晋升，不放宽正确性要求。

## 顺序与先验收契约

1. CPU契约先红再实现：版本化paper-aligned校准、完整teacher-forced分数解析、margin-aware判定；
   保留所有legacy默认行为，不改旧JSON/失败记录。无校准或真实分数时必须fail closed。
2. 先做一次NorthJob接口探针，原镜像/WeaverDev/qiji/原toleration，1节点×2 H100/256Gi。
   GPU0普通AR、GPU1 stock-tree FP32-head scorer；只检查公开接口、分数对齐、logit_bias和hidden states。
   这是正确性探针，不是性能测量，没有stock/final新加速比或晋升。
3. 接口验证后冻结完整正式dev正确性协议，在同一20个A1 dev请求上做fresh AR/stock生成及评分、
   stock首次偏离AR的δ标定、正常重复对照；4096-cap故障实验在满足长度条件的固定请求范围执行。
   不读取作者机制实现，不修改引擎文件，不使用sealed，也不重跑AR/stock/final性能基线。
4. 新旧CPU回归、真实判据、证据重放/校验、生命周期/清理分别验收，更新首页/交接并提交推送。

### 校准与性能策略（显式新API，旧API保持）

- 噪声使用匹配协议的stock null、suite等权request-cluster log bootstrap，固定10000次/seed0，
  使用双侧95%CI的保守下端作为性能下界，明确不是论文指定的具体bootstrap算法。
- noise=`max(abs(L-1),abs(U-1))`；对事先指定的全部独立null会话取最大值，不能挑低噪声会话。
  报告全宽/偏移，但不因0.2%或覆盖1单独拒绝；来源、请求、模型、GPU环境、轮次/采样协议须绑定。
- 新策略必须显式指定`paper-aligned-v1`，无完整匹配校准或真实正确性证据不得给出正式promoted。
  `LB(speedup)-1 > 0.01+2*noise`，输出分歧时还须>0.03。保留旧诊断，不追溯晋升历史结果。

### 真实评分与正确性

- 由controller调用stock引擎`--enable-fp32-lm-head`，对每条待测输出自身上下文做teacher forcing；
  保存原始HTTP请求/响应、server参数/源身份、每个token的argmax/自身log-prob、margin和prefix hash。
  输入和输出均须完整且非空，token/logprob位置必须能用单token前缀探针独立核对；缺失拒绝。
- δ来自本次stock与AR第一次不同处两token的log-prob差，向上取整到1/8；不抄论文0.72%或固定δ。
  缺少实际首次分歧证据时明确报告未能标定，不假装给出论文δ。
- rate rule采用候选mismatch率下界减stock上界>0.005；两边各用单侧97.5% Wilson界，
  是本地Bonferroni保守差值下界选择；需注明token-Bernoulli近似，不冒充论文披露的精确方法。
- event仅计margin>2δ的不匹配。解释必须绑定相同prefix的stock复现或prefill形状敏感性原始证据；
  不接受agent自填explained布尔。无法解释的事件与stock比较，使用有限stock样本的保守上界，
  不把stock零观测当成真实概率零；事件显著性与stock上界合并控制总α=0.05。
- 原token-list诊断仍不是真实forcing，新的正确性通过也不是性能晋升或lossless数学证明。

### 故障与等价控制的覆盖要求

- 真模型生成时原生logit_bias：新生成2048 token之后，对id%7==0的所有词表项加2。
  允许在2048边界拆成两次生成，但健康对照必须使用相同分段，明确与单次server内注入的区别。
  只有实际到达注入位置、发生偏置且有post-2048 token的请求算覆盖；自然EOS过早不能算注入成功。
  不ignore_eos、不编辑已经生成的token、不用随机假token冒充真实注入。
- 等价归约控制优先用同一真实hidden state、同一checkpoint FP32 LM head、不同分块累加顺序，
  检查head/argmax对齐并在真实生成/评分中应用；不将更换权重、降低精度或任意编辑输出称作等价归约。
- 健康stock/等价控制不得被误拒，故障必须由event rule拒绝；任务精度不能代替此验收。
  能力探针不足以宣称上述正式回归已通过，完整协议/覆盖规模在正式运行前继续冻结。

## 执行前验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p5_scoring.py'
"$PY" -B -m unittest discover -s harness -p 'test_p5_paper_policy.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'
bash -n exp/p5_serve.sh
git diff --check
```

真实探针入口`exp/p5_api_probe.py`，正式forcing/判定入口后续冻结；所有大输出落盘。
每次NorthJob提交前按skill核对help、凭据、路径、查重、展示完整命令/总GPU，create一次，
核对code=200和唯一UUID；镜像沿用用户已确认digest，不静默改镜像或不明确重提。

## 实施与结果

- 新评分/策略7项契约先红（缺模块），实现后新旧105项回归通过；旧98项仍过。
  中间mock漏HTTP status字段导致一次测试失败，补齐fixture后通过，未放宽解析契约。
- 普通公开API构造签名已离线核对，原生SamplingParams支持logit_bias，GenerateReqInput支持
  input logprob/top logprob/hidden states；只说明接口存在，不代表27B真实运行已通过。
- 短探针任务名`specpilot-p5-score-probe-20261108-a01`，查重、冻结与提交结果后续追加。

### 接口探针a01

- 最终查重total=0，2026-11-08 06:49:03 +08:00唯一create code=200/data=None，
  随后精确名total=1解析UUID=`job-150fd4f87c99-20261108064903`，初始Pending。
- 1节点×2 H100/256Gi、原镜像、WeaverDev、namespace/请求queue=qiji、实际queue=proj-31、
  原toleration和只读模型挂载不变；没有升级CLI或盲目重提。
- 执行pin=`d212cc4a26d2c4aea0432bf9238f4ef29876f564`，完整源tar在prep目录，
  SHA256=`c78b0721e61771138d08929247ca08c5ba43a31fa80b1bd160db44ded8390399`。
  原始输出`logs/p5-score-probe-20261108-a01/`及同前缀`.log`/`.exit-status`；
  提交与生命周期在`logs/p5-real-controller-prep-20261108-a01/`。

- a01于node204启动（06:49:28 +08:00）；两server完成模型初始化，但server-info适配失败：
  真实接口返回顶层`enable_fp32_lm_head=true`，而初版解析器只接受嵌套server_args。
  因此没有开始teacher-forced评分，不是引擎缺少FP32功能。失败与原始响应均保留。
- 首次主进程失败后，平台又创建了一个同名Pod，06:53:44–06:53:46 +08:00退出1；
  新Pod的restart_count=0不能当作整个任务从未重试。输出目录保护在模型启动前拒绝重复执行，
  不把平台重试当用户重复create；原始生命周期和补充Job事件/状态均已保存。
- 真实响应重放与新增flat/nested冲突测试通过；未改变FP32必须启用或完整logprob对齐要求。
  新margin-aware分数契约4项先红后绿，新旧最终110项CPU回归通过。
  a02复验只修适配、补失败清理与多能力错误收集；不是重复原配置追性能数字。

### a02与正式运行前协议补充

- a02一次create code200，UUID=`job-bbce4ab81d16-20261108065758`，source=`3e6056a`。
  06:58:19 +08:00 node204启动，真实FP32-head标识、8 token完整teacher forcing及单token前缀对齐、
  原生logit_bias均通过。hidden states请求bool=true被解释成full模式，超过server的last上限而HTTP400。
  公开构造签名与实例确认`return_hidden_states='last'`合法，下一次只修请求模式。
  失败清理证据两卡均0 MiB，GPU0采样util=1%，不伪称两卡0%利用率。
- 平台默认会重试失败Pod，a01 Job retryCount实为2；不能把最终Pod的restart_count=0当整个任务无重试。
  目录防覆盖保护阻止重试再次加载模型。a02起监控加入pod_uid/job_retry_count。
- 正式运行前先执行last-mode hidden state与独立FP32-head数值预检，失败则不进行长生成。
  权重只从本机checkpoint的lm_head读取，以同一FP32权重/hidden比较整段与8分块逆序累加；
  禁用本进程TF32，记录张量SHA、源码SHA和实际差值。native/独立head log-prob及选择margin容差预定1e-3。
  这不是允许candidate改变logits的容差，也不修改δ/rate/event阈值。
- 完整dev协议预定：原A1全部20请求、greedy、自然EOS、2048 cap；fresh AR与stock8各生成一遍，
  stock再独立请求一遍作健康控制，20对首分歧标定δ。作者final32/46开关另作产物正确性对照，
  不算独立发现，结果不预设通过。
- 故障覆盖范围在看故障结果之前固定：本轮AR生成恰达2048且finish_reason=length的全部请求。
  在同一AR prefix后各生成健康/每7词表项+2的尾段，尾段cap2048；另生成同请求stock8的4096-cap基线。
  仅实际覆盖注入的输出计数；若无符合长度请求或post-2048总token不足1024，覆盖失败，不修改EOS。
- 等价归约控制固定每suite第1条、每条64 cap；controller按8分块逆序FP32 head实际选token，
  同时记录native与整段FP32参考。为保持可重放的原生生成证明，控制要求逆序选择与native选择一致；
  若遇不一致，报告接口/证明覆盖不足，不静默改回native或称该差异为错误。明确报告实际不同token数。
- 对大margin事件按请求manifest顺序/位置顺序，最多前200个做相同prefix、不同prefill长度评分审计；
  超过上限保持unexplained，不抽掉。仅候选token在替代prefill成为argmax时作保守解释，记录原始证据。
- 本阶段不会新测加速比；旧null只在显式historical replay模式核验新策略，不授权历史晋升。
  正式候选活动仍必须用事先冻结且匹配的当前null。当前阶段目标是实际stock mismatch/δ、
  健康/故障/等价控制、作者final独立正确性判定，以及版本化判据的可执行证据。

### 正式runner冻结

- `exp/p5_real_run.py`串接以上固定协议，`exp/p5_remote_real.sh`持久日志/exit并设10800秒总上限；
  head预检与320-token-cap归约控制各独立子进程，上限1800秒，退出释放外部head显存。
  先单独起scorer并做head预检，通过后才起AR，避免预检失败浪费AR冷启动。
- 全部原始请求/响应、server身份与生成segments逐文件带SHA；每条trace保存后立即重放验证。
  scorer GPU1持续使用同一身份，GPU0依次fresh AR/stock/final，明确这不是性能配对测量。
- 审计仅实现相同prefix的prefill-length解释，尚未实现stock-path replay解释；不能将未解释事件
  擅自消除。各cohort独立最多200事件，超出的全数留作unexplained。
- `acceptance.json`区分裁判回归就绪与作者final正确性结果：健康四组均过、故障event拒绝、
  post2048总token≥1024才有judge_ready；作者final独立拒绝不伪装裁判失败或作者通过。
  不论结果如何本阶段promoted/ledger_eligible均为false，next_stage_allowed不代表自动进入下一阶段。
- 117项CPU测试、三个shell语法检查和diff检查通过；真实head、δ及故障/健康回归仍待GPU实测。
  首次正式任务名`specpilot-p5-real-forcing-20261108-a01`已查重total=0；提交前再查并记录完整命令。
