# Stock逐步观测与真实线性链重放

日期：2026-11-09 UTC。基准`42c1329f0a41d1003e5f53518f710f24ff47f338`。
状态：真实观测与线性重放工程验收完成；不实施优化、不改controller，不读取final实现或sealed。

## 授权与目标

用户批准逐步接口/重放阶段，另明确批准在独立stock诊断副本中阅读必要的SGLang调度/DFLASH源码、
实现默认关闭的只读钩子。原stock只读且canonical hash不变；不读取final实现。
目标是解释输出/计数差1及验证标签偏移，验证观测记录可离线重建实际输出，不求性能收益。
以下为本地T0工程契约，沿用controller现有HTTP/生成身份检查；不新增或放宽T1/T2/论文判据。

## 验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p12_step_replay
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
git diff --exit-code 42c1329 -- controller patches agents orchestrator assets/upstream costmodel
git diff --check
```

先红后绿：关闭时不访问tensor或写日志；开启必须独占新私有目录；原始记录SHA、请求/树身份和原生HTTP输出绑定。
离线独立计算最长匹配前缀、bonus和提交token，拒绝错accepted/bonus/顺序/漏步/错输出/错hash。
覆盖0接受、全接受、prefill首token、EOS与2048上限裁切，以及overlap中已生成但未提交的尾步。
CPU构造轨迹只验证重放器，不能冒充真实模型结果；真实记录不存在时不宣称采集或重放完成。

## 最小观测契约

- 仅stock/block8/greedy/单请求/无grammar路径；其他路径显式拒绝，不静默降级成伪重放。
- worker记录原始8个candidate（首位为当前token）、8个target argmax、正确草稿数、bonus、提交长度与提交token。
  不重算logits、不覆盖tensor或改变接受/调度算法。开启后的CPU同步/日志时间不进入性能结论。
- scheduler在prefill首token和decode完成finish更新后记录内部output_ids、finished_len、finish reason、
  原生verify/correct计数及histogram；同时记录请求输入hash和贪心/结束参数。
- 每进程私有追加JSONL，显式schema、pid/序号、request rid；关闭时不导入观测模块。
  实际源码/树/模块hash、原生HTTP响应及各流SHA必须绑定。未提交overlap尾步单独报告，不能算实际接受步。
- 重放输出=初始prefill token+各实际提交的(匹配草稿+bonus)，最后按原生finished_len裁切；
  以独立EOS/长度检查与HTTP输出核对。不能把线性stock链称为最佳树搜索或tau_best。

## 真实烟测协议（准备通过后才提交）

复用上一阶段10题，受控程序固定取那道代数异常题及2道正常对照；不手工读题/答案，不重跑20pair性能活动。
两模式分别比较原stock与诊断副本关闭/开启，每模式两轮fresh并物理换卡：3题/2048cap/自然EOS，
共12pair/24臂行。每server短预热及全部3题全尺度预热，测量调用既有controller传输。
只验输出、身份、采集完整性和重放；不输出加速比或晋升，观测耗时不当无干扰逐步时间。

沿用已确认镜像digest、WeaverDev/qiji/原toleration、只读models挂载；最多1节点×2H100/256Gi，
GPU执行最多1小时/2GPU小时。提交前当前help→查重→展示完整命令/总2GPU→create一次→核对code200+UUID。
真实结果独立CPU重放两次，故障注入验收、SHA/清理、README/交接与私有GitHub同步后停止。
API/真实路径不匹配时保留失败证据，不扩题追绿、不改controller，不自动启动优化或RSI。

## 必须分开的结论

1. 源码解释只是待检验假设，不能直接把旧36/40翻绿。
2. 本次解释计数不追认旧记录拥有当时没采集的逐步证据。
3. 同链重放不等于全域lossless、FP32判据、完整lattice最优树、成本三因子或性能晋升。
4. profiling标签与调度/提交步数的映射必须来自记录；若本次未启profiler，只能验证overlap尾步，不能冒充同一次trace标签对齐。

## CPU准备结果

- 8定向/210总回归通过；红测试、扩展测试与全回归日志在`logs/step-replay-prep-20261109-a01/`。
- 独立两次构建tree SHA一致：`cb27466a4093b6c6d07bc1b217e78b59e52fbaa61384bcb965e441bb3143b24b`。
  原stock SHA保持`e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff`。
  逐文件比较仅worker/scheduler两处源码文件有插入，另增runtime；无其他内容改动。
- 主bundle=`logs/step-replay-bundle-20261109-a01/`，重复构建=`logs/step-replay-build-check-20261109-a01/`。
  runtime SHA=`fc825e599aa337c307bab9bd87b0e779c9cb23854e6b113444154d707c01c91a`。
- 受控选择为首跨suite正常、唯一重复异常、首同suite正常；公开只保存角色/suite/输入长度，
  `logs/step-replay-public-20261109-a01/selection.json`。真实采集与解释仍待执行。

## 冻结与任务索引

- 执行pin=`e65925c337ab06b7327feab5d627576f418e9c8c`，源码tar SHA=
  `01cf21f10a2075ccd19388d32925a4583d55833b78097896e194f125eb90a8e0`。
- 当前CLI help、凭据非空及完整源码快照核验通过；任务名查重为0，展示完整命令/总2GPU后只create一次。
  服务端code200/dataNone，精确查名UUID=`job-7021a7f03f72-20261109101400`，WeaverDev/实际queue=proj-31。
- 准备目录`logs/step-replay-prep-20261109-a01/`，公开`logs/step-replay-public-20261109-a01/`，
  私有`logs/step-replay-run-20261109-a01/`。CLI YAML在对应`RUN/specpilot-stock-step-replay-20261109-a01/`。
  提交成功与实际启动/科学验收分开记录，运行中不改执行源码或commit。

## 真实结果与解释

### 输出计数差1：prefill首token与末尾裁切，而非本次观察到生成错误

两轮物理换卡均得到以下完全一致的逐步计数：

| 固定角色 | prefill首token | 正确草稿 | 已提交验证步（各有1 bonus） | 内部累计输出 | EOS后裁切 | HTTP实际输出 |
|---|---:|---:|---:|---:|---:|---:|
| 跨suite正常/gsm8k | 1 | 344 | 81 | 426 | 1 | 425 |
| 原异常/HumanEval | 1 | 1312 | 413 | 1726 | 0 | 1726 |
| 同suite正常/HumanEval | 1 | 604 | 155 | 760 | 1 | 759 |

真实链的记账关系是：`输出 = prefill首token + 正确草稿 + 已提交验证步 - 末尾裁切`。
原异常题`1+1312+413-0=1726`，此前条件公式漏了prefill的1。
两个正常对照恰好末尾各裁掉1，使prefill的1被抵消，所以旧公式看起来相等。
这里通过候选/target argmax独立计算匹配前缀、bonus及逐步提交，并与原生HTTP最终输出核对，
不是只根据汇总计数倒推出解释。三题都自然EOS，2048只是cap，未强行生成满2048。

24条新生成输出hash全部与原a01对应stock输出相同，原异常题的差1及输出在本次完整复现。
旧`counter_observation`及36/40判定保持原状，不把当时缺少的逐步证据追写进去；
这里只解决该额外诊断条件的解释，不是修改正式正确性判据或证明全域无损。

### 多执行一步：真实overlap尾步已观察到，但未冒充旧profile逐条对齐

三题每轮worker实际验证82/414/156步，scheduler只提交81/413/155步，均有1个未提交尾步。
重放逐一验证该尾步的候选/目标判断，并明确不把它计入实际接受量。
这给“实际执行数与原生已提交计数相差1”提供了真实路径证据，支持解释此前短请求的标签偏移。
本次没有开profiler，故`profile_label_alignment_verified=false`；未将新worker日志伪装成旧trace的逐条映射。
先前长请求128步窗口仍不能直接用来代表完整请求的全部验证步。

### 观测开关与离线重放

- 原stock vs副本关闭、原stock vs副本开启，各两轮fresh并物理换卡，12pair/24臂行全部输出一致。
  默认关闭没有step目录/流；开启的实际runtime路径、module SHA和observer tree SHA均与bundle一致。
- 仅开启模式6个真实请求轮次采集接受链；两个独立CPU进程重放与远程result逐字节一致，SHA=
  `6446c21f635ece6c45685e819202b22d04c95fcbe66805f1452e5ee87b4dc406`。
- 每个真实轮次分别破坏accepted、bonus、删一步、改输出，24个故障副本全部被重放器拒绝。
  原始证据未改；这是本地接口自检，不是论文Fig4/event-rule故障注入实验。
- 完整CPU回归210项、shell/diff及原生HTTP生成身份检查通过；8个fresh测量server全部停止。
  未修改controller/原stock/旧成本模型；原stock canonical仍为e5472c4f...。

## 生命周期、归档与边界

- 唯一NorthJob已Completed，Pod Succeeded，容器与脚本exit0；node244/实际proj-31，
  镜像digest、2H100/256Gi、只读models、无hostNetwork/privileged均核对。
  容器2026-11-09 02:14:23–02:30:14 UTC（UTC+08为10:14:23–10:30:14），951秒/15分51秒，
  折算0.528333GPU小时，2预算内。33监控快照仅见单Pod UID、容器restart0；Job retryCount未设置。
- 两卡均0MiB/利用率0%，端口释放，全部监控/CPU会话结束；没有遗留GPU任务或重复提交。
- 新5598文件/92137799逻辑字节全部SHA通过，清单`logs/step-replay-evidence-20261109-a01.sha256`，SHA=
  `d501afd8a1d0418ac81b0db36e6e57133c8d004f24dad2ef8e7f690a42fc2e3a`。
  校验日志`logs/step-replay-evidence-verification-20261109-a01.log`；前阶段393项也复验全过。
  私有run/bundle/重复构建、原始step流不上传Git，Git只追踪源码、协议、脱敏索引与决策。
- 完整验收入口`logs/step-replay-prep-20261109-a01/acceptance.sh`，输出`acceptance-final.log`，exit0。
  CPU重放必须新输出路径；后续源码变化应建立对应e65925c冻结源码环境，不能绕过source hash。
- 没有输出速度收益、损失率判据或晋升。观测本身有CPU同步/日志开销，其耗时不能作无干扰T_step。
  这是线性stock实际链重放，不是完整lattice最佳树/tau_best，也不是全域lossless或完整三因子。

**决策：本阶段完成。** 下一大步骤先报VERIFY主要kernel-class工作量/byte来源与匹配无干扰步计时方案，
获批准后再补成本模型；不扩大题集掩盖接口缺项，不自行开始优化、RSI、sealed或controller改动。
