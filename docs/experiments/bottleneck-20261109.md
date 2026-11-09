# Stock 真实瓶颈、计数审计与部分成本模型

日期：2026-11-09 UTC。基准 `a04972c2bc96c11e78816255cc5bafce610f3b09`。
状态：远程执行及两次独立重放完成；本阶段诊断验收通过，完整三因子成本模型仍未完成。
不实施优化，不修改controller或作者引擎。

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

### a01提交与版本身份

- 执行pin=`a102b64c0173aa9b72e126778005a137bad174fc`；源码tar位于准备目录，SHA=
  `6c6d11a53f6b20971ab3304f670540b04a2536a66b61cc56519e4a1da72ee2a9`。
- 当前help/凭据非空/源码快照核对通过，精确任务名查重为0；完整命令`create-command.txt`。
  仅create一次，code200/dataNone后精确查名取得UUID=`job-fa7aeb0532ed-20261109083627`。
  项目WeaverDev，namespace与请求queue=qiji，实际queue=proj-31；未使用默认项目。
- YAML=`RUN/specpilot-stock-profile-20261109-a01/specpilot-stock-profile-20261109-a01.yaml`，
  saved_json_path=None。1节点×2H100/256Gi/原镜像digest，模型只读挂载。
- 私有原始目录`logs/bottleneck-run-20261109-a01/`；公开聚合目录
  `logs/bottleneck-public-20261109-a01/`；监控保存准备目录`lifecycle.*`。
  已见node244及两H100/版本预检通过；提交成功与科学验收分开，结果仍待完成。

### a01发现与补采验收（实现前）

- 原任务Completed/exit0，20pair/40臂行通过，但只有4/20 profile，16条被安全隔离，不算完成。
  两次CPU重放与原result字节一致。500原始响应保留，原生server日志明确报告
  `RuntimeError: Profiling is not in progress. Call /start_profile first.`，不是仍在采集。
- 修复只增加停止调用前后**新日志切片**的路径/偏移/长度/SHA绑定；只有500且该次切片精确含上述
  原生异常才允许下一次start，HTTP500仍为失败。旧日志、坏hash、其他500不得获得此状态证明。
  不改引擎，也不把500改成200。先红测试，再实现。
- 独立profile-only新attempt，两fresh stock重新采同20探针；不重跑或覆盖原计时。
  128步/2048cap/全尺度预热及4GiB预算不变，计时仍绑定原pin，补采单独pin/UUID。
  补采最多35分钟，加原18分18秒不超过总1小时/2GPU小时预算。
- 验收：新日志证据测试与全CPU回归、原计时原始绑定验证、20探针实际覆盖、补采独立重放两次、SHA及清理。
  计数36/40代数一致；4条来自同一HumanEval题，输出比“正确草稿+验证步”多1，
  先保留为未解释，不修改引擎或放宽计数判据追绿。
- 补采实现CPU验收202项通过（a02/final-source-tests.log）；红测试确实捕获500隔离问题。
  首次全回归仅新repair测试fixture遗漏ports失败，修正fixture后全绿；不修改生产判据。
  profile-only入口保留原计时manifest/result/source pin及tar hash，审计仍核对原始HTTP/换卡。
- a02冻结pin=`5ed0302e123ae51af3c669ffc6bf1350a64672e4`，源码tar SHA=
  `17afdc16a78a30185ad375fb756f147c547ef052b3b0807d7d994fe45c835d47`。
  prep/public/private分别为`logs/bottleneck-{prep,public,run}-20261109-a02/`。
  新任务名查重0，完整命令展示后仅create一次code200/dataNone，精确查名UUID=
  `job-46790c2ece9b-20261109090434`，WeaverDev/实际proj-31；35分钟限时，未重跑计时。

## 实测结论

### 1. 当前优先分析VERIFY，不等于已找到可实现的优化

10个独立请求、两物理卡重复，共20个窗口，按请求等权的**窗口内累计kernel工作时间**：

| 明确阶段标签 | 份额 |
|---|---:|
| VERIFY | 89.5782% |
| DRAFT | 8.2852% |
| EXTEND | 0.9770% |
| DECODE | 0%（未观察到该标签） |
| 未归因 | 1.1596% |

全部窗口累计kernel时间58.7568秒，各窗口单设备kernel区间并集累计49.7258秒。
二者不可混称墙钟，区间并集亦不含独立copy/memset。不得用89.6%推断整请求收益上限或CPU开销。
12个窗口只有127个VERIFY标签，对应早期采集；另外8个窗口标签数比原生verify_ct多1。
因此128个公开profiling步、标签数、原生验证计数不是可直接互换的三个单位。
没有将长请求的早期窗口外推到2048完整请求，也没有将两卡重复当20个独立样本。

### 2. 接受计数：36/40行满足全部预声明代数约束，一题仍未解释

失败4行属于同一HumanEval题的两卡×两轮，不是4个独立反例：
实际输出1726、报告正确草稿1312、报告验证413，后两者相加1725，少1。
直方图总数/加权数和原生别名能对齐，但“每次验证加1再只做末尾裁切”的条件关系不成立。
原记录与判据不改，不能声称已审计每步接受路径，也不能据此断言引擎生成错误。

同源无profiler计时每suite仅2独立请求；以下仅描述该诊断，不是新正式性能CI：

| suite | 请求耗时中位数ms（8臂行） | 实际输出均值token | stop / length臂行 | 全代数约束通过 |
|---|---:|---:|---:|---:|
| gsm8k | 1582.76 | 367.0 | 8 / 0 | 8 / 8 |
| math500 | 6409.65 | 1252.5 | 4 / 4 | 8 / 8 |
| humaneval | 6890.64 | 1242.5 | 8 / 0 | 4 / 8 |
| mbpp | 9686.00 | 1852.5 | 4 / 4 | 8 / 8 |
| mt-bench | 7545.61 | 1160.0 | 4 / 4 | 8 / 8 |

### 3. 成本模型：只得到很小的可识别子集，不能计算完整headroom

- 可无歧义关联BF16 mm/bmm共4216项，其累计kernel仅300.332ms，约占全部累计kernel的0.5111%。
  该子集的名义冷内存roofline情景272.892ms；不是实测DRAM、全验证pass下限或全局kernel效率。
- CUDA graph隐藏的形状及其他kernel仍未知，不能从kernel名称倒猜FLOP/byte。
- 当前公开schema无真实token lattice/replay导出路径，metadata直方图不能恢复候选token和目标判断。
  没有拿block8或TinyLM替代真实tau_best。
- tau/kernel/overhead与ceiling全部null，complete=false；缺项是本次明确核查的能力边界，
  不是可填1消除的实现错误。架构观察层已接入，不等于论文完整成本模型或数字复现。

## 最终验收、资源与决策

- 202项CPU回归通过；两个attempt的原始生成/预热/时序/换卡/进程/源码tar及模型config绑定验证通过。
  a01为4个测量server+2个profile server；a02仅2个fresh profile server，未重跑无profiler计时。
- a01只有4/20 profile，失败与隔离全部保留；a02为20/20，12次stop HTTP500仍计为错误，
  均有该次新原生日志切片的偏移/长度/SHA证明采集已停止，后续start才获准。未修改引擎或HTTP状态。
- a02两次独立CPU重放与远程result逐字节一致，SHA=
  `0300ac0bbc18a241ffcd6bc74a67bc2cd751474cb4db8e9a2e2503d866085ab1`。
  a01两次重放同样一致，SHA=`81b347f726e2e4409c7924a75397211f7b60a2fc2294cd9652e600929121ff33`。
  a01重放使用a102b64，a02使用5ed0302；未来源码变化时需用相应冻结源码受控重放，不覆盖当前checkout。
- 两任务均node244、Job Completed/Pod Succeeded、容器与脚本exit0；实际镜像digest、2H100/256Gi、
  模型只读挂载、无hostNetwork/privileged均核对，两个任务不重叠。
  a01 00:36:55–00:55:13 UTC（1098秒），a02 01:04:58–01:19:01 UTC（843秒），
  合计32分21秒、按容器时长折算1.078333 GPU小时，原2预算内。
- 监控38/29个快照各只见1个Pod UID、容器restart0；Job retryCount未设置，不扩称服务端保证零重试。
  两卡0MiB/利用率0–1%，端口释放，监控结束；profile补采证据141173413字节，低于4GiB。
- `promoted=false/ledger_eligible=false`；无候选、sealed、真实RSI、账本或记忆写入，无lossless声明。

**下一大步骤建议（另获批准）：**先由维护者提供最小只读逐步计数/lattice导出与匹配无profiler步计时，
在相同10题中解释原生计数和标签偏移，再补VERIFY主要kernel-class的工作量/byte来源。
不扩测试集或重跑final来替代这些接口，不在缺依据时强行输出三因子或启动自主搜索。

### 归档与复核入口

新393文件、181717264逻辑字节，清单`logs/bottleneck-evidence-20261109-a01.sha256`，SHA=
`05cafb7ebff1a06eb44664321a282cb59a43f0dfc9046c2da0b1d4eb98b719c3`；全项通过，
日志`logs/bottleneck-evidence-verification-20261109-a01.log`。前阶段candidate的2970项也全部复验通过。
原始逐题数据/trace只持久归档，不上传Git；Git追踪源码、脱敏汇总与两任务索引。
补采聚合`logs/bottleneck-public-20261109-a02/analysis.json`，完整验收入口为
`logs/bottleneck-prep-20261109-a02/acceptance.sh`，输出`acceptance-final.log`，exit0。
未来重放必须指定新输出路径；源码变化时先建立相应冻结版本的受控环境，不能绕过源码hash检查。

```bash
sudo -n sha256sum -c logs/bottleneck-evidence-20261109-a01.sha256
git diff --exit-code 5ed0302 -- controller exp harness costmodel assets/upstream
git diff --check
```

本阶段完成，无运行任务；完整成本模型缺项单独报告，未自动进入下一阶段。
