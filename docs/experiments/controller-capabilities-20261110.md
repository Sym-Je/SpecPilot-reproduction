# Controller 能力工程复核（2026-11-10）

## 授权、范围与先行验收

本次为工程验收协作，不是科学 Direction；只新建本文与
`harness/test_controller_capabilities.py`，不修改 controller、eval、既有文件，
不提交 Git、不提交 GPU、不读取真实 sealed、作者 final 或 Ascend 数据。
运行产物按用户要求留在 `logs/skills-rsi-20261110-b01/controller-tests/`。

以下命令在实现前登记。所有 shell 执行均使用 `require_escalated`；
测试使用前台 TTY、`-B` 禁止字节码写入，完整输出落盘，只回读尾部。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/skills-rsi-20261110-b01/controller-tests
mkdir -p "$OUT"
set -o pipefail
$PY -B -m unittest harness.test_p5_paper_policy harness.test_p5_scored_forcing \
  harness.test_p6_dev_campaign -v > "$OUT/existing.log" 2>&1
status=$?; tail -n 12 "$OUT/existing.log"; exit "$status"
```

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/skills-rsi-20261110-b01/controller-tests
set -o pipefail
$PY -B -m unittest harness.test_controller_capabilities -v > "$OUT/capabilities.log" 2>&1
status=$?; tail -n 18 "$OUT/capabilities.log"; exit "$status"
```

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/skills-rsi-20261110-b01/controller-tests
set -o pipefail
$PY -B -m unittest harness.test_p5_paper_policy harness.test_p5_scored_forcing \
  harness.test_p6_dev_campaign harness.test_controller_capabilities -v \
  > "$OUT/combined.log" 2>&1
status=$?; tail -n 18 "$OUT/combined.log"; exit "$status"
```

验收判据来自 `docs/02-acceptance.md` 与现有 controller 函数，不改阈值：

- 健康近并列候选通过 forcing；2048 之后的合成大 margin 错误触发 event rule。
  另用稀疏故障区分 event 与 rate 两条规则，不能只看到总拒绝便声称 event 生效。
- 原生 generation、own-prefix forcing、实际计时输出、生成器与 SHA 必须绑定；
  缺轮、半对、未换卡、原始证据替换均 fail closed。
- stock-null 最大端点距离噪声、`LB - 1 > 0.01 + 2 * noise`、
  分歧输出的 3% 保守阈值、两轮正确性联动沿用现实现；缩小 noise 不得绕过复算。
- fixture 复用 `harness.test_p5_scored_forcing` 与
  `harness.test_p3_baseline_validation`（同 `test_p6_dev_campaign` 的复用方式）；
  被测 controller 不 mock。合成证据中的 `final` 仅是现有接口规定的候选臂标签，
  不代表读取或运行作者产物，不是 GPU 验收、不产生晋升或账本写入。
- 如发现低层接口只验证摘要格式、缺少可信绑定，保留可复现证据并记录缺口，
  不通过改 controller 或降低判据把它写成已防住。

## 执行结果

2026-11-10 UTC 完成；最终代码身份核对时间 `13:59:38Z`。
工作区 HEAD 为 `ffeab9d41653f013747db9f058cb4487f0ec3166`，含其他协作者既有未提交改动；
本协作者未改动那些文件。新增测试最终 SHA256：
`e9ba2c28266e82c18d5af696a96f236b4eb31c8d2467f97342ddd0c9bbf60a91`。
被测 controller、统计实现与复用 fixture 的 9 个文件在运行前后 SHA 一致，
记录为 `identity.log` / `identity-final.log` / `source-recheck.log`。

| 执行 | unittest 数 | 退出码 | 结果/证据（均相对产物目录） |
|---|---:|---:|---|
| 既有 paper-policy / scored-forcing / dev-campaign | 16 | 0 | `existing.log`，6.793s |
| 新模块初次运行 | 36 | 1 | `capabilities-attempt-01.log`，4 failures / 1 error，6.437s |
| 修复 fixture 根目录后 | 37 | 0 | `capabilities.log`，7.545s |
| 最终版本联合回归 | 53 | 0 | `combined.log`，13.723s；`exit-status.log` |

初次失败为**本次测试 fixture 的路径错误**：生成证据临时目录不在 campaign 的
声明根目录内，真实 `read_bound` 正确拒绝。只修复新测试的证据目录，未放宽裁判；
首次失败日志保留。随后增加 forcing→两轮合并→performance 的真实函数联动测试；
最终联合回归包含两个不同 forcing trace 的健康回执。
日志与身份清单的校验值见 `SHA256SUMS`，已执行 `sha256sum -c` 全部通过。

### 验收覆盖与真实观察

新模块共 **37 个测试方法**（forcing 13、campaign 11、policy 13），包括 subTest
变体；不把 subTest 或重复回归累计为新增测试数量。被测 controller 函数未 mock。

- **健康与两种故障独立复核：** 合成首次 stock/AR 分歧的 margin 为 0.1，真实
  `calibrate_delta` 得到 δ=0.125；4096 token 的健康近并列 trace 通过两条规则。
  在零基 index 2048–2059 设置 12 个 margin=2 的错误：rate rule **不触发**，
  event rule **触发**（p<0.025），无解释事件，正确性拒绝。
  同一合成请求使用2048+2048的 own-prefix generation 包，第二段的每7个 vocabulary ID
  bias=2，`validate_injected_generation(..., vocabulary_size=28)` 验证通过。
  vocabulary=28 与合成 logprob 仅用于工程契约，不是实际模型故障注入结果。
  另有2048个 margin=0.1 的错误单独触发 rate rule 而不触发 event rule。
- **输出/评分/证据绑定：** 生成 token、计时行引用的原生包、prompt、generator、
  forcing 自身上下文及评分必须一致。即使另一包内容相同，只替换计时行包引用也拒绝。
  scorer/generator/generation/score 四类 SHA 替换、原包字节变化、改完包重算 SHA
  但语义不符、伪造 score/解释、出界路径均拒绝。δ、stock counts 重写也不能绕过复算。
- **配对会话完整性：** 新 fixture 通过真实 `validate_session`，30请求、60 pair、
  两轮合成换卡和不同进程标识。缺完整轮/完成标记、缺半对、两臂共用一张卡、
  两轮不换卡（同步改 deployment 与所有计时行）、删 full warmup、复用进程标识、
  原包输出与行不一致、伪造 summary 均拒绝。时间、GPU UUID、进程标识都是合成值。
- **噪声/收益不降标：** noise=2% 时阈值为5%，4%收益拒绝、6%通过 readiness；
  noise 改0即使重算摘要仍因原区间复算被拒。缺/重排/重复 null session、错 campaign /
  protocol、historical replay 均拒绝。输出分歧维持3%地板，等于阈值仍拒绝；
  均值高但95%下界低不通过，正确性失败不能用10倍合成收益抵消。
  所有通过均不产生 `promoted` 或 `ledger_eligible`。

### 两个已复现的低层信任边界（不是“已防住”）

最后两个 `test_low_level_*` 是**当前行为刻画**，不是保护性通过判据；
它们的 `ok` 明确表示下面两种情况可被低层函数接受：

1. `candidate_verdict` 只检查 correctness 的 `evidence_sha256` 格式，**不验证该摘要
   与正文绑定**。把两轮失败回执的 `correctness_passed` 改成 true、保留旧摘要，
   直接调用此函数会得到 `eligible_for_promotion=True`。
2. `combine_correctness` 要求长度2和摘要格式，但**不能建立两个独立物理轮的身份**；
   将同一个健康回执复制两次也通过。

这些函数不能作为接收 agent 自报 receipt 的可信验收入口。现有 `validate_campaign`
源码在高层重新执行两轮 forcing、比对磁盘 verdict、由实际输出计算 output_identical，
然后才调用上述函数；本次没有证明整个高层活动可被这两种方式绕过，也不能声称已对任意
agent 输入提供独立防护。角色 broker 必须保持：独立 controller 重算证据，
不能直接采信角色传入的 correctness、output_identical、groups 或 null 区间。
本次授权不允许改 controller，因此仅报告并提供可复现测试。

### 剩余缺口与交付边界

- 未构造并运行完整 `validate_campaign` 的 null-pre→candidate→null-post→独立 FP32
  head preflight→逐请求评分活动；覆盖为真实子接口的合成会话与联动回归。
  源码中的高层防护不等于本次完整端到端验收通过。
- 未验证真实 GPU、真实模型 FP32 head、真实浮点归约等价、实测 stock-null、
  真实4096输出故障注入、独立 dev 配对性能或任何 sealed / Phase4；不据此判 lossless。
  既有 dev-campaign 中本地 HTTP 回归使用合成 server，也不是模型推理。
- 未认证任意可写证据目录的来源；SHA 是内容完整性而非签名，若攻击者能全量重写原始包
  与所有引用，仅靠格式检查和自洽摘要不能证明真实执行，仍依赖可信 controller/broker 权限。
- 本次新增 GPU/API 消耗为0，无 ledger/memory 写入，无提交/推送；只交付两个新文件。
  主助手另行负责 BBuf 角色 broker 与真实 GPU 通路，本次不重复实施或宣称其完成。
