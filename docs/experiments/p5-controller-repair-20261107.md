# 第 5 步：裁判修复与真实验收准备

状态：in-progress。基准 `b5c7706`；用户明确回复“允许修改”，授权本阶段
`controller/` 正确性与统计实现修复。不是 sealed、放宽门槛或独立 RSI 的授权。

## 先固定验收，再实现

1. 空请求、空 token、缺失/多出输出、非法 token、非法统计参数一律拒绝。
2. 二项尾概率须与小样本精确枚举一致，支持 n=4096/100000、p=0/1，概率有限且在 [0,1]。
3. rate rule 使用分歧率下界与基线之差 >0.005；旧 token-list 入口只能作诊断，
   不将其伪装成真实 margin-aware forcing。保留旧 mock 基线参数但明确不是当前实测值。
4. HTTP 输出分歧时，性能增益下界须同时大于 `1%+2*noise` 和 3%；
   拒绝负/非有限噪声；即便该性能条件通过，也不代表真实 correctness 或晋升通过。
5. stock/stock 明确生成 stock-a、stock-b 两个实例，均启动 stock 引擎及 block=8，
   文件不碰撞，fresh server/物理换卡及清理仍由既有编排执行。不允许其它同名比较。
6. 原审计 9 项逐项通过；审计仍 exit=1、production_ready=false，直到真实证据完备。
   不改旧审计输入或把真实前置缺失硬编码成通过。
7. 原 50 项回归、7 项审计工具测试及新增裁判测试通过；P2/P3 全部历史产物校验一致。

执行命令：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p5_controller.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'
"$PY" -B exp/p5_readiness_audit.py --out <独立新目录>/audit.json
git diff --check
sha256sum --check --quiet logs/p5-readiness-evidence-20261107.sha256
```

先红后绿的测试输出使用独立 logs 目录保留。没有真实运行证据的项目仍标未完成。
不改动历史报告/清单，不覆写 ledger，不读取 sealed 或作者实现源码。

## 真实链路的独立边界

真实 scorer 必须沿候选自己的前缀评分，记录 target argmax、候选 gap、FP32-head 身份、
stock mismatch 与 delta 标定来源；普通输出一致性不能替代。若只有不同 backend 的
Transformers 参考或 BF16 logprobs，只能标参考诊断，不能声称 stock-engine FP32 forcing 完成。

真实 null 先固定原 20 条 dev 请求、2048 cap、warmup=2、两轮 fresh server/物理换卡；
每次会话独立报告，至少两次会话，不把两轮当独立请求。CI 全宽 <0.002 的要求不变，
未达标则如实失败，不追跑到碰巧变绿，不将跨会话均值冒充会话内噪声。
NorthJob 沿用用户已确认镜像/WeaverDev/qiji/原 toleration 与 2 H100，
每次提交按 skill 查重、展示完整命令、核对 code=200 和 UUID。

## 结果

- 旧缺陷先红：16 项新增契约测试执行失败（含多个 subTest），记录 `logs/p5-controller-repair-20261107-a01/red.log`。
- 修复后新增 16 项及新增 null/分层统计 6 项通过，最终新旧 **79/79** 通过。
- 原审计输入未变，9/9 合成前置检查通过；审计仍 exit=1、production_ready=false，
  因真实 FP32-head scorer、stock mismatch/delta、真实注入及 null 证据尚未齐备。
- 修正旧 G4 的长度故障处理：完整性校验主动 ValueError 即正确拒绝，
  不再要求一个不完整序列继续进入 rate/event；没有运行 GPU G4 冒充真实 27B 验证。
- 真实 null 入口 `exp/p5_remote_null.sh <新目录>`，一次 2-H100 任务顺序运行两次独立会话，
  每会话 20 请求/2048 cap/两轮 fresh server/物理换卡。由 `controller/null_validation.py`
  校验身份、覆盖、独立实例输出稳定性，并给 suite-stratified request-cluster 双侧 95% CI。
  `noise=max(|upper-1|,|1-lower|)`，同时单独检查 **区间全宽 <0.002**。
  生命周期 exit=0 不等于 precision_passed；门槛不达标仍保存全部结果，不产生晋升。
- PDF §3.3 已重新核对：delta 是 stock 首次偏离 AR 的最大 margin，向上取整至 1/8；
  event 是 margin>2delta 且经 stock replay / prefill-length 审计仍无法解释的事件，
  不是普通 token 不同的计数。旧 token-list 入口现明确标诊断，不拿它冒充真实 scorer。

下一内部步骤：按已登记协议提交一次远程 null 校准，保留调度/启动/测量/清理/统计各层结果。
