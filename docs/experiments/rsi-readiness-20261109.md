# 真实 RSI 准入准备：基线、护栏与接口缺项

日期：2026-11-09（UTC+08；执行日志保留 UTC）。状态：准入核对完成，真实搜索尚未就绪。
基准提交：`c05d17d46446c31f3044943a7423c444583207a6`。

## 目标与授权范围

用户批准结束作者 final 泛化诊断，核对已有证据，准备从 stock 开始的真实自主优化。
本阶段只做 CPU 回归、历史证据重放、缺项清单和进度归档；不提交 GPU，不运行搜索，
不修改 controller、引擎、option 或请求集，不读取 sealed，不写晋升账本或记忆。
已有泛化与诊断结果不因回到主线而撤销，也不再追加接受长度诊断。

## 先写验收

执行脚本：`logs/rsi-readiness-20261109-a01/acceptance.sh`。

```bash
bash -n logs/rsi-readiness-20261109-a01/acceptance.sh
bash logs/rsi-readiness-20261109-a01/acceptance.sh \
  > logs/rsi-readiness-20261109-a01/acceptance.log 2>&1
git diff --check
git diff --exit-code c05d17d -- controller patches agents costmodel orchestrator harness exp assets/upstream
```

脚本显式禁用 CUDA；先跑 paper-policy/dev 联动定向测试，再跑 P2/P3/P5–P9 回归。
随后逐文件核验真实裁判、dev、泛化、反例确认、诊断五阶段已有 SHA 清单；只以受控
`sudo -n sha256sum` 读取受限证据字节，不展示题目、答案或逐题输出。
真实裁判与30题 dev 各在两个独立进程重放，输出写全新目录；初始验收额外要求dev与原公开汇总逐字节一致。
本脚本只验证既有 controller 判定，不新设或放宽研究判据；历史通过不能作为新活动的校准。

## 基线与范围

- 搜索起点固定为既有 H100/Qwen3.8-27B/DFlash2/SGLang v0.5.20 stock，block=8，
  不加载作者 final 覆盖层及46开关。未来启动仍须绑定完整树 hash、配置、模型和镜像身份。
- 作者 final 只作已知参考产物，不算自主发现；本阶段不向正式账本登记基线。
- 原5基准族的新100题收益2.171842×，只支持已测同类新题的速度泛化；
  独立中文60题请求延迟比0.539657×的反例必须同时保留，不用总体均值掩盖。
- 已见聚合结果的数据若用于选候选，必须视为开发/回归证据，不能再次冒充独立确认。
  不将现有私有样本复制进 eval，不手工读题；具体回归集由维护者/受控流程管理。
- 中文回归用于暴露适用边界，不能未经审批把“所有领域都快”加成论文硬门槛。
  原速度口径与请求延迟口径分开报告，不混合成一个奖励。

## 已有证据与缺项

| 组件 | 已有证据 | 本阶段结论 / 后续缺项 |
|---|---|---|
| stock基线与配对计时 | AR/stock、fresh server、双卡物理换卡已通过 | 复用工具，不再重复作者基线追数字 |
| 真实正确性裁判 | FP32自身prefix评分、δ标定、健康/归约控制、post2048故障拒绝 | 复核历史判定；并非数学lossless或全域语义非劣证明 |
| 当前活动噪声与dev联动 | 30请求前null→候选→后null，两轮均过 | 仅属于原活动；下一候选必须重新标定，不携带旧noise/δ |
| 候选引擎与option接入 | 现有配对CLI仅ar/stock/final，dev活动固定stock/final | 缺独立candidate构建/身份/default=stock契约与真实启动适配 |
| profiling与成本模型 | 已有公开profile采集、明确标签/correlation阶段归因 | 仅诊断probe；缺代表性stock/replay与真实三因子。floors.decompose仍kernel=1 |
| proposer | 提示词和固定registry策略存在 | loop.Proposer为确定性枚举，未接实际LLM提案/实现/预算轨迹 |
| 晋升与账本 | paper_policy给出只读pre-promotion verdict | scope明确no campaign integration/ledger mutation；正式真实候选状态机尚缺维护者交付 |
| sealed和记忆 | 隔离约定与mock骨架存在 | 未开展；须维护者/controller落实，不能由agent读集或写正式记忆 |

接口缺项来自公开本地源码核对：`exp/p3_pair_run.py:38`、`exp/dev_campaign.py:48`、
`controller/dev_campaign.py:222`、`controller/paper_policy.py:107`、`orchestrator/loop.py:56`、
`costmodel/floors.py:62`。未读取作者引擎实现。

## 准入与停止规则

沿用 `docs/02-acceptance.md` 的 `paper-aligned-v1`，本阶段不改规则：

1. T0先验收option关闭时复现stock与相应机制契约；没有可执行验收不实现候选。
2. 同活动同协议前后stock null全部纳入，独立请求聚类，物理轮次不充当新样本；
   身份漂移、半对、缺轮、失效校准必须拒绝，不套旧活动noise。
3. 对实际测速输出沿自身prefix做stock FP32-head评分，重新标定δ与stock mismatch；
   rate/event都过，才讨论性能。stock-path解释尚缺时不伪造解释或删异常事件。
4. 收益下界与含实测noise的阈值比较；输出不同时沿用现有保守约3%规则。
   不再追求null区间必须覆盖1或全宽0.2%，也不把forcing通过叫语义质量非劣。
5. agent提案不等于晋升；正式candidate/current-best身份、判定和账本绑定由维护者交付，
   当前controller只读readiness输出不作为正式晋升，更不能直接调用mock loop冒充真实RSI。
6. 先完成开发阶段的候选接口和代表性profile/replay，再按获批计划决定sealed准备顺序；
   sealed在Phase 4才由controller加载，通过前不写promoted memory。

## 下一大步骤建议（未执行，须另获批准）

补齐真实候选的可执行契约和接入设计：从 stock 出发定义candidate manifest、option默认值、
构建身份、启动参数及T0命令，核对哪些现有裁判接口可直接复用，哪些需要维护者明确授权。
同时预声明代表性stock profiling/replay所需字段、缺失处理与成本模型单位，不用中文反例
反向指定“该发现哪个优化”，不照抄作者final。先完成CPU接口验收，再单独申请GPU诊断预算。

这一步是后续真实搜索的基础设施，不承诺已经实现多轮闭环；本阶段也不授权任何controller修改。

## 验收脚本的格式差异与修正

初次11项定向测试、167项回归、五阶段25319清单项全部通过；两次裁判/dev重放也已完成。
初次脚本在“dev重放 vs 原公开汇总”的字节比较处exit1，原`acceptance.sh`和`acceptance.log`
原样保留。查明原`joint-acceptance.json`为31220字节、CLI重放为31219字节，
**仅原文件多一个末尾换行，JSON对象完全相同**；不是统计/正确性判定变化。

不修改controller或原始证据，新增`logs/rsi-readiness-20261109-a01/acceptance-final.sh`收尾：
先核验已完成的日志数及输入清单身份，再于新03/04路径各重放一次；四份新CLI输出须逐字节一致，
dev还须与历史`replay-01.json`、`replay-cli-02.json`逐字节一致。
原汇总须严格等于CLI字节加单个`\n`且JSON对象相同，不泛化为忽略任意差异，也不放宽研究门槛。

```bash
bash -n logs/rsi-readiness-20261109-a01/acceptance-final.sh
bash logs/rsi-readiness-20261109-a01/acceptance-final.sh \
  > logs/rsi-readiness-20261109-a01/acceptance-final.log 2>&1
```

## 本次验收结果

- CPU活动：2026-11-08 22:52:53–22:56:43 UTC，即2026-11-09 06:52:53–06:56:43 UTC+08。
- 11项定向测试通过；完整167项CPU回归通过（包含定向覆盖，不合计成178个独立测试）。
- 五阶段1347/1223/10312/5928/6509清单项，合计25319项，SHA全部通过；
  这是已有清单覆盖的证据项，不声称25319个互不重复实验或独立样本。
- 真实裁判与dev各四个独立进程重放一致；dev亦与两份历史CLI输出逐字节一致，
  原公开汇总严格仅多单个末尾换行，数值及判定不变。初次格式比较exit1保留，收尾脚本exit0。
- dev重放SHA=`840502614d4bbd84c743ea377838e22e457a64cbaa6e283e2e53bc728fed172f`；
  裁判重放SHA=`ad1238a1fbc7ccf67ea7b176ed8a3f2fffe1079535e0c5f9a76b4f03e41d9d3c`。
- 新证据37文件、2380283字节；清单`logs/rsi-readiness-evidence-20261109-a01.sha256`，
  SHA=`f3d90b8237a340274b77c889ef1a3e7e84de6c1427f569a20c5f66178ecea23f`，全项核验通过。
  核验日志`logs/rsi-readiness-evidence-verification-20261109-a01.log`，原始证据不上传Git。
- shell语法与diff检查通过；controller/patches/agents/costmodel/orchestrator/harness/exp/
  作者资源相对基准无变化。本阶段只更新文档，未新测任何性能或宣称新候选通过。
- `gpu_tasks_submitted=0`、`promoted=false`、`ledger_eligible=false`；无sealed/RSI/记忆写入。

**决策：准备阶段完成，不是完整真实RSI就绪。** 不重复测作者final；下一大步骤先报
candidate接入/T0方案获批。若需要controller变更，单独列明维护者交付和授权范围，不能绕过。
