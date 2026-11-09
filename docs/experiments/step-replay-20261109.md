# Stock逐步观测与真实线性链重放

日期：2026-11-09 UTC。基准`42c1329f0a41d1003e5f53518f710f24ff47f338`。
状态：执行中；不实施优化、不改controller，不读取final实现或sealed。

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
