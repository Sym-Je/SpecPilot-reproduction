# Canonical 正确性 reference 与当前栈性能基线分离

## 授权与先行验收（实现前登记）

仅修改 `controller/dev_campaign.py`、`exp/engine_dev_gate.py`、`exp/dev_campaign.py`，
新增 `harness/test_controller_reference.py` 与本文。维护者有限授权；不改科学阈值、
不读真实 sealed/作者 final、不提交 GPU、不 commit。其他工作区改动保留。

先登记以下定向验收，所有 shell 均 `require_escalated`，长任务前台 TTY，输出落盘：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/skills-rsi-20261110-b01/controller-tests
mkdir -p "$OUT"
$PY -B -m unittest harness.test_controller_reference -v > "$OUT/reference.log" 2>&1
status=$?; tail -n 24 "$OUT/reference.log"; exit "$status"
```

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/skills-rsi-20261110-b01/controller-tests
$PY -B -m unittest harness.test_p5_paper_policy harness.test_p5_scored_forcing \
  harness.test_p6_dev_campaign harness.test_controller_capabilities \
  harness.test_controller_reference harness.test_engine_research \
  > "$OUT/reference-regression.log" 2>&1
status=$?; tail -n 24 "$OUT/reference-regression.log"; exit "$status"
```

验收要求：旧流程没有独立 reference 时行为和阈值保持；当前优化栈只用于性能比较
和匹配的 bracketed stock-null；teacher、AR、delta 与 stock-rate 使用 canonical stock。
当前测量 stock/final 均必须绑定自己的 forcing；reference 必须有实际原生生成包与
评分，不接受一个 bool、自报计数或改名的优化栈。错误身份/输出/输入/SHA/缺项应拒绝。
用非敏感临时文件/localHTTP验证真实 controller 函数；替代 GPU 生命周期与 head
子进程的 fixture 不等于 GPU 科学验收。

## 已实现 schema

- `campaign.reference_tree_sha`：`run_gate` 从可信 `spec.stock_tree_sha` 写入，64位小写
  SHA256。缺省回退旧 `null_arms[0].tree_sha`，不要求旧活动补字段。
- `candidate_arms[0]` 是性能比较基线栈；`null_arms` 是该栈两个同配置副本。
  若其 tree SHA 不同于 reference，则必须独立生成 canonical reference-stock。
- 独立 reference 文件为 `correctness/reference-stock/<request-id>.json`，原生包为
  `correctness/reference-stock-raw/`；同 cohort 可供两个物理性能轮校准使用。
  AR 与 scorer 始终经可信 `arm_specs(['ar'], environment)` 获取原始 stock 引擎，
  启动前核对 reference SHA；reference-stock 经 `arm_specs(['stock'], environment)`，
  不从比较基线或 candidate 的源码 bundle 启动。
- `correctness/round-NN-stock/` 仍表示**实际计时比较基线输出**的 forcing，不改名或删掉。
  `round-NN-delta.json`、`round-NN-stock.json` 在独立 reference 模式下则由
  `reference-stock + ar` 计算，`round-NN-verdict.json` 对 candidate 做既有判定。
- 性能 stock-null 需要支持当前栈的同臂配对，不可继续硬要求 canonical engine 的
  `arm_specs` 身份；新路径仍检查请求/两轮换卡/输出一致/来源/时间/原包，使用同一个
  request-cluster bootstrap 与既有最大端点距离 noise 及既有 candidate 阈值。
- `candidate_arms` 的名称仍为 `stock` / `final`，`null_arms` 仍为 `stock-a` /
  `stock-b`；`final` 仅是候选 schema 槽。比较栈的 `tree_sha`、`block`、`engine`、
  `env` 在两个 null 副本上必须完全对应，不能用另一栈的 null 掩盖噪声。
- 独立 reference 模式额外校验 AR/reference-stock 的原生请求参数：
  `sampling_params={temperature:0, top_k:1, max_new_tokens:2048, ignore_eos:false}`，
  单段完整输出、原始 HTTP 200、非空且不超过2048 token、stop/length 合法结束；
  length 必须达到2048。生成与评分时间不得早于 null-post 完成。
  reference-stock 必须为 canonical tree、DFLASH、block=8、非 FP32 生成器；
  scorer 必须是同 canonical tree 的 FP32/非 speculative teacher，AR 不得带 bias。
- 显式声明 reference 的活动结果额外返回 `reference_tree_sha` 与
  `independent_reference_stock`。后者仅为说明字段：是否通过仍由原包重读、
  校准复算与 forcing 决定。旧无字段活动不增加这两个结果字段。
- 既有 `protocol_id` 算法与 `dev-joint-v1` 不变；每个物理会话 manifest 必须
  与顶层 `reference_tree_sha` 一致。独立 reference 活动对磁盘 delta/calibration
  文件也逐项与复算值比较，不能只保留一个自报 correctness bool。

## 实现与结果

### 变更位置与兼容性

- `exp/engine_dev_gate.py` 从 `spec.stock_tree_sha` 固定记录 reference，不从比较栈
  推断 teacher；保留此前已有的 `server_factory` / `arm_class` / `candidate_origin`
  接口，未覆盖其他协作者的既有改动。
- `exp/dev_campaign.py` 启动前核对已安装 canonical 引擎 SHA。比较栈不同才额外
  串行启动 canonical stock 生成 reference-stock；两个性能轮复用该 cohort，
  不把它声称为两次独立 reference 采样。两个实际 stock 轮的输出仍逐条 forcing。
- `controller/dev_campaign.py` 重新加载和检查 reference、AR、计时 stock/final、
  原生包、身份、SHA、前缀、输出与时间。delta/stock-rate 仅取 reference-stock。
  优化比较栈的 bracketed null 走同等完整性校验与现有统计函数；canonical 旧路径
  仍调用原 `validate_null` / `calibrate_null_runs`。
- 没有改 `scored_forcing` / `paper_policy`、统计阈值、ledger 或 eval。

### 定向测试结果

产物目录统一为 `logs/skills-rsi-20261110-b01/controller-tests/`：

| 运行 | 测试方法数 | 退出码 | 结果 |
|---|---:|---:|---|
| 首次新模块 | 14 | 1 | `reference-attempt-01.log`，86.353s，4 failures |
| 修复合成 null 时间后 | 15 | 0 | `reference.log`，94.404s |
| 最终版本联合定向回归 | 86 | 0 | `reference-regression.log`，114.781s |

联合86项=此前53项+本次新增15项+既有 engine-research 18项，不累计 subTest 为新增数量。
首次失败是 fixture 继承了候选6%速度差作为 null：真实裁判因此测出约6%噪声并提高
收益门槛，正确拒绝了6%候选。本次只把两个同配置合成 null 的时长设为相同，
没有降低阈值。随后增加有 bias 的 AR 拒绝测试；最终回归又覆盖截断 length
与两个测量臂使用优化 teacher 的拒绝。所有首次失败日志保留。

新增测试执行完整 `score_campaign`→`validate_campaign` 真实函数链，包括三个性能
会话、各两轮换卡、请求/telemetry/原包校验、delta/stock-rate、audit、forcing、noise
与最终 verdict。Fixture 替代 GPU 空闲检查、引擎生命周期、原生请求的合成响应、
独立 checkpoint head 子进程，以及旧 null 路径的本地安装路径发现；不是 GPU 运行。
`Campaign`、`NativeClient.score`/原包解析与 controller 判定函数未替换。

关键观察：

1. 无 reference 字段的旧路径与显式 canonical 比较基线均通过，只有 scorer/AR
   两次启动，没有多生成 reference-stock。
2. 比较栈 tree=b、candidate tree=c、canonical tree=a 的健康候选通过；实际生成
   reference-stock 并绑定 canonical 引擎，两个轮次 δ 都为0.125，stock counts
   都为960 token/30个合成近并列 mismatch/0个大 margin 事件，而不是比较栈计数。
3. 故意让比较栈和候选都携带同类大 margin 错误：性能通过，两个 candidate 轮
   都被 canonical event rule 拒绝；已优化栈没有抬高候选容忍度。
4. 缺 reference 请求、错 generator/scorer tree、输入/输出/证据 SHA 替换、
   更换实际计时包引用、重哈希后的 bias/cap/时间/截断 length、优化 AR/teacher、
   伪造 stored delta、会话 reference 漂移、null 输出不一致均拒绝。
5. 已安装 canonical 引擎不匹配 reference 时，在任何 correctness 引擎启动前拒绝。
   所有通过仍 `promoted=False` / `ledger_eligible=False`。

### 身份与运行缺项（交付主助手）

- HEAD 为 `ffeab9d41653f013747db9f058cb4487f0ec3166`；含阶段内既有未提交代码。
  最终四个代码文件 SHA 见 `reference-identity.log`；命令退出码见
  `reference-exit-status.log`。运行日志校验清单为 `reference-SHA256SUMS`。
- 未提交 GPU、未执行真实 canonical stock 的额外生成、未实测该分离路径的 GPU
  资源/清理/预算耗时、未运行真实 head preflight；本次是非敏感临时文件工程回归。
  临时原包随 fixture 清理，由测试源码可重建，不当作 GPU 测量档案。
- 主助手仍需冻结并打包这三处运行代码，安装可信 canonical `...-stock` 引擎，
  使 `arm_specs(['ar'/'stock'])` 的 TREE_SHA 等于 `spec.stock_tree_sha`，不可用
  比较 baseline 的 bundle 代替。额外 canonical stock cohort 的实际耗时须计入
  同一阶段预算，未授权新资源或自动重试。
- 比较基线来源/曾通过正确性、补丁链身份、candidate 基于 canonical 且包含所有
  父补丁，由主助手的 source bundle/broker/Master 选择路径负责；本次不实现
  或代替这些外部证明。传入 `arms[0]` 必须已命名为 `stock`。
- 上个子任务记录的低层 receipt 信任边界仍存在，未扩权修改。应继续只允许可信
  controller 重算入口，不对角色暴露可自报 correctness/groups/null 的捷径。
  没有 sealed、作者 final 或科学晋升结论，没有 commit/push。
