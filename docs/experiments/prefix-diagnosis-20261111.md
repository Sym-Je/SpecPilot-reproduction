# 长上下文收益收窄：最小离线诊断

用户要求区分接受量下降与Attention成本增加。本步只复核已收口的
[原题加干扰前缀实验](prefix-context-20261111.md)，不改stock/final，不新增GPU任务，
不使用旧阶段余额，不接管其他研究，不读取sealed或写晋升账本。

## 先行验收与范围

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B logs/prefix-diagnosis-20261111-a01/analyze.py
```

- 必须覆盖既有100pair/200份原始HTTP回执；逐份核SHA、题目/轮次、token和计数一致性。
- 直方图次数/加权和须分别匹配verify计数/草稿计数；明确EOS或输出上限的尾部裁剪。
- 对照冻结stock/final源码，区分scheduler外层提交周期与TLV内部Q-step，不能把同名字段
  当成同等成本的一次target forward，也不能拿固定分母的accept rate比较两臂。
- 只重述controller已测吞吐；本地计算只用于诊断，不生产晋升数字。
- 日志若无请求级prefill/decode和kernel时间，就保留unknown；日志吞吐、启动耗时及
  秒级时间戳都不冒充精确阶段耗时。输出长度改变不是固定工作量对照。

完整复算、源码身份与验收结果存于私有目录`logs/prefix-diagnosis-20261111-a01/`。
原始请求、输出和作者源码不进入公开报告。

## 结果：接受推进量没有随长度大幅下降

下表是20次观测（10题×2轮）的请求级中位数，单位为**输出token/外层提交周期**，
不是每次target forward的接受量；两个物理轮的该统计分别重算一致。

| 完整输入 | stock | final |
|---|---:|---:|
| original，68–259 token | 4.694 | 12.950 |
| 2K | 4.766 | 12.511 |
| 8K | 4.547 | 12.695 |
| 32K | 4.375 | 13.003 |
| 64K | 4.551 | 12.588 |

original到64K，stock约下降3.0%，final约下降2.8%；final各档仍约12.5–13.0。
排除bonus后的草稿计数/外层周期中位数，final为11.982→11.612，也未出现整体崩塌。
这**不支持“本次整体收益从2.18×降到1.16×，主要是接受推进量暴跌”这一简单解释**。
不据此排除单题接受量变化，样本仅10题，前缀还会改变生成内容和自然EOS长度。

### 为什么这里不能直接称统一的接受长度

冻结源码核对结果：

- `tokenizer_manager._calculate_spec_decoding_metrics`中的`spec_accept_length`确为
  `completion_tokens / spec_verify_ct`；不是独立采集的TLV内部接受量。
- `batch_result_processor._resolve_spec_v2_tokens`在返回scheduler的提交结果上加一次
  `req.spec_verify_ct`，直方图记录这次返回的草稿计数。
- final的`dflash_worker_v2._d8r_q_step`内部递归执行Q-step，返回链而不向scheduler提交；
  外层再做exact verify并返回`GenerationBatchResult`。因此外层计数不单独统计Q-step。
  它可用于同一冻结final跨长度的推进量诊断，不能与stock当成等价成本的target调用比较。
- 两臂的`spec_accept_rate`还使用各自block减一的固定分母，不能拿其数值直接比较树覆盖率。
- prefill可生成首token，最后一轮还受EOS/输出上限裁剪；200份回执的
  `草稿计数+外层周期数-实际输出数`范围为stock −1…6、final −1…16。
  所以计数推进量与最终可见输出不是严格相同口径，不能把尾部差值当成计数坏掉。

## 结果：共同时间成本增加，但无法精确归因

| 条件 | stock平均完整请求耗时 | final平均完整请求耗时 |
|---|---:|---:|
| original | 6.460秒 | 2.867秒 |
| 64K | 14.391秒 | 11.183秒 |

两臂分别增加约7.93秒和8.32秒，和“长输入增加共同成本、稀释final收益”的解释相容。
但两臂/各条件的输出token数不同；这些均值不构成固定工作量的阶段分解或因果证明。

四份server日志只有Prefill/Decode批次日志、窗口吞吐和秒级时间戳，未保存请求级
prefill/decode分时或验证阶段kernel trace。源码确认Prefill日志的input throughput分母是
距上次Prefill统计的时间间隔，可能夹有其他阶段，**不能反推纯prefill耗时**；
startup timings只描述冷启动，也不能用来分解正式请求。

因此本次结论分三级：

1. **已观察到：**外层接受推进量总体稳定，端到端收益明显收窄。
2. **支持但未证实：**长上下文的时间成本增加，比“整体接受推进量骤降”更符合当前观测。
3. **仍未知：**prefill稀释与decode Attention分别贡献多少；Attention是否成为主要瓶颈。
   TLV内部Q/exact各阶段接受量也没有独立计数，不能声称排除了所有接受相关变化。

## 验收与接续

- 覆盖100pair/200份HTTP及200份server身份回执，逐份SHA、题目/轮次、换卡、输出token、
  原始计数和直方图守恒检查通过；stock/final整树SHA与正式实验冻结身份一致。
- 复算两次结果逐字一致，另一路直接读取原始计数重算全部中位数一致；
  篡改回执和破坏直方图的合成反例分别被SHA与守恒检查拒绝，无原始产物改写。
  初版诊断脚本错把rid当成裸题号，验收立即失败；按既有
  `round|题号|r0|A或B|measure`格式修正后全量通过，未放宽计数规则。
- 仅离线CPU；新增GPU任务0，GPU用量0，不触碰作者实现/controller/eval/ledger/memory。
- **离线最小诊断已完成，精确瓶颈归因未完成。**若要继续，只需冻结原始/64K两个端点的
  少量同题，补请求级prefill/decode分时和验证阶段Attention trace；无profiler计时与profile
  诊断分开，TTFT不能冒充纯prefill，不扫N、不修final。新GPU额度和镜像须另行确认。
