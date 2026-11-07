# P5-readiness — 第 5 步真实裁判前置审计（非 sealed Phase 5）

状态：blocked。第 5 步已开始，前置审计完成；真实正确性、噪声与晋升仍未完成。
用户批准本阶段不等于允许修改 controller；本次只做 CPU 只读审计，没有提交 GPU 任务。
基准：`a120552f76c8e3e94f353db82ea040fed5b895e0`，开始时工作树干净。

## 目标与预先验收

确认现有 controller 是否具备进入真实 correctness / null calibration 的条件。
本审计只调用已有接口、使用合成 token 和内存 fixture；不实现新裁判、不改变生产判据、
不写 controller / ledger，不读取 sealed 或作者实现。不将合成输入称为真实故障注入。

既有依据：`docs/02-acceptance.md` §1、§4、§5；
`docs/11-reproduction-plan.md` §3.4、§7。执行前固定以下反例：

| 检查 | 应有行为 | 依据 |
|---|---|---|
| 无请求 / 空 token 序列 | 拒绝，不可得到 lossless=True | §7.6 空样本拒绝 |
| 候选丢失后缀 / 多出后缀 / 丢失整条输出 | 拒绝，不可只比较共同前缀后接受 | §7.6 长度与缺 token 拒绝 |
| 同一 4096-token 序列自比 | 不崩溃，不能因长度长而误判 | §7.5 真实长输出前置 |
| 1000 token 全部分歧 | rate rule 必须识别显著超出 0.5pt 的分歧 | T1；分别检查 rate 与 event |
| 合成 2.5% 增益、noise=0、输出分歧 | 不得绕过输出分歧 >3% 的既有附加要求 | T2；不是实测性能 |
| stock/stock 编排入口 | 两个实例可独立命名、fresh server、物理换卡 | §7.1；现有 CLI 若拒绝则记缺口 |

真实 scorer、FP32 LM head、共同前缀评分、margin/delta、真实注入与 null 会话还须提供运行证据；
上述合成反例即使全通过，也不能据此声称真实验收完成。
审计 exit=1 表示裁判未就绪，属于必须保留的失败证据，不改判据使其变绿。

执行命令（先登记，后实现与执行）：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
mkdir -p logs/p5-readiness-20261107-a01
"$PY" -B exp/p5_readiness_audit.py \
  --out logs/p5-readiness-20261107-a01/audit.json \
  > logs/p5-readiness-20261107-a01/audit.log 2>&1
"$PY" -B -m unittest discover -s harness -p 'test_p[23]*.py' \
  > logs/p5-readiness-20261107-a01/regression.log 2>&1
git diff --exit-code a120552 -- controller
git diff --check
```

不执行会访问 sealed 的隔离测试，也不运行需要 GPU 的历史 G4 来冒充 27B 测试。
资源预算：本机 CPU、0 GPU、0 NorthJob create；每个反例最多 4096 token。
输出使用独立新路径，禁止覆盖历史 P2/P3 证据。

## 执行与结果

### a01：只读审计

- 新增 `exp/p5_readiness_audit.py`：有上限的合成反例、已有 controller 接口、独立输出路径；
  不访问模型、HTTP server、GPU、sealed 或作者实现，也不写账本。
- `audit.json` 和 `audit.log`：`logs/p5-readiness-20261107-a01/`。
- 实际退出码 **1**；9 项契约检查 **0/9 通过**，不按失败数量推断独立根因数量。
- 新增审计脚本自身的 7 项测试，全部通过；原 P2/P3 回归 50/50 通过。
  **测试脚本能准确报告失败，不等于 controller 已修复。**
- 没有 NorthJob create，没有新 UUID，没有 GPU 进程启动或新的真实性能数字。

| 反例 | 实际观察 | 影响 |
|---|---|---|
| 空请求与空 token（2 项） | `n=0, lossless=True` | 无证据被当成通过 |
| 少尾部、多尾部、整条输出缺失（3 项） | 只比较 `zip` 共同前缀，均 `lossless=True` | 不完整输入未 fail closed |
| 4096 个完全相同 token 自比 | `OverflowError: int too large to convert to float` | 长输出判定数值不稳定 |
| 1000/1000 token 分歧 | Wilson 下界 0.9961731，但 `rate_flagged=False` | rate rule 独立失效；event rule 此例仍拒绝，不能说整例被接受 |
| 合成 2.5% 增益、noise=0、输出不同 | `output_identical=False, promoted=True` | HTTP compare 未接入 T2 的输出分歧附加要求；不宣称真实候选曾被误晋升 |
| `stock stock` 的非执行计划 | argparse exit=2，要求两臂名称不同 | 现有编排不能直接执行真实 stock null；不能伪装成 AR |

### 静态审计与未验证项

1. `controller/token_force.py` 的输入只有两组 token 列表；没有候选自身共同前缀上的
   teacher-forced target logits、FP32 LM head、argmax/margin、stock 首次分歧复现数据。
   默认 `base_rate=0.0072` 来自论文，不是当前部署的实测基线。`delta` 参数未参与计算。
2. `rate_flagged = (rate - base_rate) - low > 0.005` 不是对分歧率增加的正确下界检验；
   event 目前统计所有不等 token，没有 `margin > 2*delta` 事件筛选。
   这里指出实现缺口，不在 agent 侧另立正式统计裁判。
3. `controller/stats.py:binom_one_sided` 直接计算大组合数；4096-token 自比已触发数值溢出。
4. 历史 G4 用 TinyLM/replay 的 token/accepted 故障；不是 27B 上“2048 token 之后、
   每第 7 个 vocab id 加 bias=2”的真实注入。结构合法不等于任务精度区间重叠，
   不能把旧 G4 的 E4 解释成真实精度对照已完成。
5. `HttpPairBench.calibrate` 不负责重启与物理换卡，也不强制两实例同一 stock 身份；
   G7 默认同 URL 的自比不能替代独立双 server 的真实 null 会话。
6. `paired_ci(alpha=0.05)` 输出 5% / 95% 端点：下界可称单侧 95%，但两端合看是中心 90%，
   不是双侧 95%。当前 P3 诊断用 log-ratio bootstrap 的 2.5% 端点，两者不能混名。
7. 维护者须明确 session / 请求 / suite 层级、区间构造和噪声定义，并保留
   `docs/02` 的 **null 区间全宽 <0.2%** 要求；不能把全宽误作半宽或距 1 的距离。
   当前没有真实噪声数值，不使用 mock 3.11% 或 A1/A3 两轮点估计差值替代。

### 维护者交付顺序（未授权实施）

1. 先修空样本、长度完整性与稳定统计计算，并让上面的最小反例不再暴露漏洞。
2. 给出真实 stock scorer 的接口与可执行验收：沿候选各自前缀评分，
   校准 FP32-head 参考、stock mismatch、margin/delta；rate/event 分开验收。
3. 用真实 4096-cap 输出完成规定的 logit-bias 故障注入与等价归约对照；
   自然 EOS 未达注入位置的请求不能算注入成功。任务精度对照不能替代 token 级裁判。
4. 维护者确认正式 CI/噪声契约后，补显式 stock-a/stock-b 实例身份（底层均为 stock），
   按固定 dev 协议完成多次 fresh 双 server / 物理 GPU 互换会话；
   每次会话先标定，再作候选对照，不能拿跨会话历史噪声充数。
5. 正确性、噪声与输出分歧门槛集成后，才谈正式晋升；仍不自动建立 sealed 或启动 RSI。

这份清单不是 controller 修改授权。用户需明确授权该目录的限定修改，
或由维护者交付上述接口与验收后，agent 才能继续接入真实实验。

### 复验与证据归档

已使用新的 `logs/p5-readiness-20261107-a02/` 复验，没有覆盖 a01。
两次 9 项观察逐项相同，审计均 exit=1；controller 源码哈希一致且与基准无 diff。
复验同时执行 `python -B -m unittest discover -s harness -p 'test_p[235]*.py'`，
**57/57 通过**（7 项新审计工具测试 + 50 项既有回归）。
`git diff --check` 与 P2 a05 / A1 / A2 / A3 四份历史清单复核 exit=0。

| 证据 | 持久位置 | SHA-256 |
|---|---|---|
| 两次审计、测试、只读校验等共 12 个文件 | `logs/p5-readiness-evidence-20261107.sha256` | `5dc42cbdc0ba68dba02ccc2c3abfdce6955ea293c6b58a1d0a9af091ab1c3480`（清单自身） |
| 完整新增执行代码与工具测试快照，20480 bytes | `logs/p5-readiness-20261107-a02/audit-source.tar` | `ec32a911e584a8a5724ead185ccf24d3e7af759736acdd436473ad4bed8651f7` |
| 命令、退出码与重复性验收，1597 bytes | `logs/p5-readiness-20261107-a02/verification.json` | `9abba9b7850350f9499479d184aec522fa1b73d46378e1afe911af61a19f99c0` |

清单用 `sha256sum --check --quiet logs/p5-readiness-evidence-20261107.sha256` 复核通过。
审计记录中的 HEAD 是基准 a120552；实际新增代码由清单中的源快照固定，
不能把尚未提交时的 HEAD 误当作本次完整执行代码。
源码、测试、报告及首页/交接随本审计里程碑提交；原始 JSON 与日志不进 Git。

## 结论与下一步

已复现 controller 前置缺口；**第 5 步 blocked，不是 completed**。
已有 A1/A2/A3 性能诊断结论保持原范围：不因新审计撤销原始测量，
也不因 2.2219× 的收益而豁免正确性。没有正式 lossless、噪声地板、晋升或 ledger 标识。
下一步需要维护者权限/交付，不能通过只改 harness 绕过裁判。
