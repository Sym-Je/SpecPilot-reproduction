# 隔离Master自主交付详细方案

## 本阶段目标

用户批准：Master自己获取信息、比较并选定方案，主动补齐核心设计，交付可直接交给Direction实施的首版方案。
不是自动跑完整实验，不要求用户逐项追问，也不由维护者提供算法答案。
允许恢复同一逻辑Master自己的上一阶段资料，不提供其他agent方案或维护者的候选解法；恢复材料明确记复用。
原生线程已关闭时使用新线程重放自己的材料，不冒称原线程恢复或一次新的独立发现。

本阶段0GPU、不派Direction、不启动模型server、不恢复旧预算，不修改引擎/controller/规则/账本，不读sealed/凭据/作者final。
沿用用户批准的Master原生同等权限、两类禁区仅prompt约束，平台沙箱及审批不变；不扩大其他角色或Ascend权限。

## 先行验收与主要流程

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native
$PY -B -m harness.master_native prepare --directory logs/master-native-design-20261112-a01
$PY -B -m harness.master_native check --directory logs/master-native-design-20261112-a01
```

1. 保存既有工作树与保护文件身份；校验上一阶段冻结的Master自身资料及输入，并记录重放来源。
2. 给Master目标、约束、统一交付标准，不指定必须选择哪项，也不提供科学设计提示。
3. Master自主识别缺口、补源码/文献/CPU证据，选定一个合理首版，完成算法、伪代码、数据结构和参数依据。
4. 自行交付调用点、option/default/fallback、正确性风险、完整成本/收益条件、最小验证协议、失败/停止条件。
5. 交付前自查：是否还把核心算法选择留给用户或Direction？若是，继续完善，不能把方向清单标成可实施。
6. 维护者独立复核来源、完整性与可实施性，问题交回同一逻辑Master自行修订，只反馈缺口、不代给答案。
7. CPU检查和事后文件对比通过后，归档实际材料，公开同步方案摘要和下一步；不把详细设计当GPU正确性/收益已通过。

## 完成判据

必须有一个明确选定的首版，不只是多个待选tactic或“继续研究”。核心行为、参数初值/依据、输入输出和状态不变量可据此实现。
Direction仍自主选择工程、调试和实验细节，不需要重新发明核心机制。
不可通过编造收益、实现状态或测试CLI满足格式；未知实验参数须有明确校准方式，未存在的接口标成计划。
如果现有证据不能支持任何合理首版，必须交付明确的证据缺口及最小取证，不谎称目标达成。
对禁读行为只能复核可得轨迹；文件SHA不变不证明未读取。正式数字和晋升仍归独立controller。

## Master交付的明确首版

版本`K1-paired-split2-v1.1`，同一逻辑Master复用自己的研究并自主细化，不是维护者指定的算法。
本轮不再停在“小M tactic/可选融合”的方向描述，选定唯一机制：
**配对gate/up的BF16 tensor-core Split-K=2 producer，加保留BF16中间舍入边界的CUDA归约SwiGLU；down projection不变。**
只用于H100 SM90、TP/DP/PP=1、greedy DFlash target verify；首版不改draft或token选择。

### 算法与参数

- 输入X为BF16 `[8,5120]`；权重W为BF16 `[34816,5120]`，前后各17408行为gate/up。
- K明确分成`[0,2560)`和`[2560,5120)`。每个CTA共享X tile，分别算gate/up两路FP32部分和，不用atomic、量化或权重pack。
- 固定`BM=16, BN=64/branch, BK=64, split=2, warps=4, stages=3`；producer为544个CTA，M8以mask处理其余8行。
- P布局为FP32 `[split=2,row=8,branch=2,column=17408]`；CUDA epilogue用256线程、每线程8个输出，共68个CTA。
- epilogue先FP32相加，再分别对gate/up执行BF16 RNE舍入，widen至FP32后用stock CUDA SiLU乘up，最后输出BF16 `[8,17408]`。
- 保留BF16边界不等于GEMM bitwise等价；Split-K改变归约顺序，CPU已构造不等价反例，必须由原controller规则判定是否可接受。
- 上述是未测参数初值。首次仅跑该点；最多再试`(warps,stages)=(4,2),(8,2)`，核心算法/tile/split/精度不变，不进行无限tactic搜索。

### 接入和退路均已明确

计划option为`specpilot_bf16_mlp_tactic`，default=`stock`、enabled=`paired_split2_v1`，尚未实现。
接入共享`Qwen2MoeMLP.forward`及dense target的两个真实decoder调用点，显式传递runner/ForwardBatch资格context；不改全局GEMM dispatcher。
CPU/非目标shape、draft、非greedy、量化/adapter/hooks、特殊数值模式等不满足资格时走原stock。

graph必须有独立`mlp_variant`维度，保留原size/stream/LoRA/attention语义与stock图；不能只加Python if后假定replay生效。
只额外capture目标batch1/width8稳定路径；capture、can_run、load_batch与replay共用resolver，核对精确key存在及weight generation，否则stock。
P/A按device、execution lane、capture instance预分配，串行层可复用、并发图不共享；关闭PDL的影响纳入实际完整pair成本。
编译/分配/capture等launch前失败可退stock；CUDA运行错误须失败当前请求并清洁重启，不能吞异常后在脏context重试。

### 成本与证伪

每次权重356,515,840B；P为2,228,224B，P+A常驻2,506,752B/instance；相对stock中间结果增加3,342,336B logical流量。
有效GEMM计算2.852GFLOP，BM16候选padded计算5.704GFLOP；不将padding、寄存器、graph pool、准备摊销或失去的overlap当免费。
stock pair与新pair均名义两次launch，不声称少一次launch。候选pair/step实际时间、真实暴露次数和净收益全部保留unknown。
例如假设每pair省5微秒、64次全额转移、额外集成100微秒，条件节省220微秒/step；另一情景会亏损，不是实测加速比。

未来Direction依序实施：取得独立可执行验收/新资源授权→固定producer/epilogue→完整pair及pair+down微基准→有限资源校准→option/graph接入→连续完整step/状态检查→独立controller双卡互换dev验收。
每一步有明确失败/停止条件，局部无收益或数值不通过不进入整套引擎；所有未来GPU测试脚本均标计划，不伪称已有CLI。

## 自主自审与独立复核结果

Master自行发现并修订了错误decoder类名、context传递、graph replay路由、workspace生命周期、mutation witness和误用69层计数等问题。
首次CPU测试未杀死遗漏BF16边界的mutant，保留exit1并修复样本；随后10类CPU检查通过，包含完整地址覆盖、故障注入、真实K5120反例和135个条件成本情景。

维护者独立重放CPU输出逐值一致，独立核对byte/FLOP/CTA成本、stock activation边界、graph key定义和30份来源哈希；238份自有重放材料未变。
维护者首次成本检查误将每个split的X加载都按完整K重复计算，已保留失败并修正复核公式；没有修改Master设计或科学/裁判判据。
保护文件事后比较与4项postcheck回归以阶段回执为准；禁读行为不因SHA一致而获证明。

结论：**详细方案交付目标达成，可交Direction开始首版实施；不是GPU实现、数值正确性、实测收益或完整RSI已通过。**
本阶段0GPU、0Direction。实际方案/机器设计/自审/回执位于`logs/master-native-design-20261112-a01/research/`，公开只同步摘要和身份，不发布原始stock/trace/私有上下文。
