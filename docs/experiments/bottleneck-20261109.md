# Stock 真实瓶颈、计数审计与部分成本模型

日期：2026-11-09 UTC。基准 `a04972c2bc96c11e78816255cc5bafce610f3b09`。
状态：用户批准执行，先验收后实现；不实施优化，不修改controller或作者引擎。

## 目标和预声明协议

1. 原5基准族各前2条公开dev，共10个独立请求；先跨suite第1题，再跨suite第2题。
   greedy/thinking、2048 cap、自然EOS，不挑快题、不强行生成满上限。
2. 无profiler的stock/stock两轮fresh双server并物理换卡，20pair/40臂行。
   每轮2条短预热及完整10题同尺度预热；所有计时由既有HttpPairBench产生。
   这不是候选晋升，不将10题诊断当正式30题dev，也不套旧noise/δ。
3. 以上计时全部结束、GPU释放后，再在GPU0/GPU1各起一个fresh stock server；
   同10请求同2048 cap，逐请求独立profile，共20个探针，不与计时混跑。
   使用公开start_profile的`num_steps=128`、record_shapes、detailed_annotations；
   不指定语义不明的absolute start_step。trace仅对应前128个**公开profiling步**，不预称128次VERIFY。
   短请求可能完整，长请求可能仅早期窗口；不将窗口归因外推为整请求墙钟占比。
4. trace总文件预算4GiB，达到后停止额外采集并如实记录剩余缺项，不删证据或追绿。
   API自动结束后stop若返回非200，仅在保存原响应且已有有效trace时记录为控制响应异常，
   不把失败HTTP翻绿；没有有效trace则该探针不可用。失败、早期窗口偏差均报告。
5. 复用明确`step[MODE ...]`标签、同线程launch、原生correlation归因；未知保留。
   区分累计kernel工作时间、单设备GPU kernel忙碌区间并集与trace跨度；并集不含独立copy/memset，不能从中直接推出CPU开销。
6. 原生metadata提供accept histogram/计数/accept_length，但暂不假定其语义：
   核查直方图总数/加权数、计数别名、输出/验证比、rate与末步截断的代数一致性。
   对外分别命名“报告正确草稿数/步”和“实际输出token/报告验证计数”，不混称接受长度。
7. 公开OpenAPI未发现lattice/replay导出路径；每步候选token、条件目标判断和最佳树未知，
   不拿block=8代替tau_best，不用TinyLM replay冒充真实Qwen/SGLang replay。

## 验收命令（实现前冻结）

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p11_observations harness.test_p11_stock_profile
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
bash -n exp/stock_profile_remote.sh
git diff --check
git diff --exit-code a04972c -- controller patches agents orchestrator assets/upstream
```

先红后绿：时间并集不双计重叠、多设备不冒充同一墙钟、未知归因不猜、负值/NaN拒绝；
直方图与最终输出长度不同不自动判错误、缺/坏计数不发明接受率；
没有真实lattice/每类byte-FLOP/匹配无干扰step计时就不能输出完整三因子。
CPU/真实HTTP测试验证控制器原始生成绑定、计时/profile不混用、缺轮/卡位错拒绝、profile响应与trace完整性。

## 成本模型边界

旧`costmodel/floors.py`保留，不把其kernel=1的简化分解当论文完整模型。
新增证据层：观测字段、来源/覆盖率和缺项必须随值提供。
仅在公开trace中存在明确BF16 `aten::mm/bmm`形状与无歧义launch关联时，计算该子集的
名义roofline表：60% dense peak、90%名义带宽，张量I/O按冷读写一次作**情景假设**。
这不是实测DRAM流量或全验证pass下限；CUDA graph缺少形状时保留未知，不从kernel名字猜FLOPs。
tau_best缺真实候选格、完整T_floor缺每类工作量、T_step缺同协议无干扰逐步时间时，
对应因子均为null，不能填1、相乘或宣称headroom已量化。

## NorthJob资源和停止规则

沿用已确认镜像digest `harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`，
WeaverDev / namespace与请求queue=qiji / 原toleration，1节点×2H100/256Gi，bash/nproc1，
禁RDMA和hostNetwork，GPU执行最多1小时（2GPU小时）。当前help、查重、完整命令与2GPU展示后create一次。
code200+精确UUID、启动、科学验收分别记录；不明确先查重，不盲重提。
完成后CPU独立重放/SHA/资源清理/进度与阶段提交推送；不碰sealed、ledger、memory或自主搜索。

## 实际执行与结果

CPU准备完成，远程待执行。准备目录`logs/bottleneck-prep-20261109-a01/`。
新增16项、全200项CPU回归通过，日志`final-source-tests.log`；shell语法及diff检查通过。
相对基准，controller、patches、agents、orchestrator、作者资源和旧floors均未修改。
已保存历史公开schema与metadata形状探针，仅用于接口设计；不能冒充本次实时能力与测量。
