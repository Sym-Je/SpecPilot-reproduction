# 第5步：受控CPU亲和性null实验

状态：预登记的一次实验已执行、验收与归档；两会话一过一未过，稳定化目标未达成。
后续资源隔离诊断等待可执行的官方资源配置，不追加同配置追绿。前序为`p5-stable-null-20261107`，准备基准`1cde11b`，
执行pin=`794219b12ef96e9092a60a08ffba662771f5ff3a`。
用户授权在稳定化大流程内自主调试；不改controller、不放宽门槛、不读取sealed、不改GPU时钟。

## 假设与固定修正

前序完整预热后两会话CI全宽均<0.2%，但均约+0.2%偏移。调度主线程在96个CPU内迁移，
其他server进程可用192个CPU；8轮GPU频率稳定，服务端仍有偏移。CPU迁移/调度是一种假设，
并非已证实根因。本实验只验证固定本任务CPU亲和性能否得到稳定null，不声称分离每种CPU原因。

- 所有请求、模型、stock引擎、镜像、4轮GPU×端口交叉、预热、两独立会话及controller统计完全沿用前序。
- 新option `--pin-cpus`仅允许与`--stable-null`同时使用，默认关闭，旧实验原行为不变。
- 两server就绪后，依据各自scheduler已自动选择的NUMA CPU集合及sysfs物理核拓扑，
  按GPU UUID排序确定不重叠物理核。每个NUMA集合跳过最前两个物理核后，每GPU分配9个物理核，
  scheduler主线程使用一个逻辑CPU，其余本任务server线程使用另8个物理核各一个逻辑CPU。
  不是CPU独占预留，外部进程仍可能竞争；不修改外部进程、cgroup或CPU频率。
- 同会话第一轮确定GPU→CPU映射，后续轮次沿用映射，随物理GPU而非方案标签换卡。
  两次固定施加：server就绪后和完整预热结束后；没有按测量结果自适应调整。
- 操作前每次重新核对进程是本runner启动的server的后代，检查PID/start_ticks以防PID复用；
  权限不足、物理核不足、无法读取拓扑或进程身份不明均失败，不悄悄降级。
- 逐次保存亲和性操作证据；每2秒监控额外记录本任务所有server线程的CPU mask。
  测量期任何scheduler主线程逃离固定核、其他线程逃离对应GPU CPU集合，验收失败。
  额外监控不是零开销，实际采样耗时照常记录。
- 每会话仍须controller CI全宽<0.002，并且覆盖1，两会话都过才称本协议稳定；不合并平均。
  不删除请求或读数，不改noise定义，不写晋升账本，不宣称真实正确性已过。
- 只提交一次本新协议。若仍未过，归档失败和新增证据，不同配置重复追绿不属于方案。

## 先验收再实现

先执行新CPU绑定契约测试，应先红；再实现、运行所有新旧回归。验收命令：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p5_cpu_affinity.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'
bash -n exp/p5_remote_stable.sh
git diff --exit-code 1cde11b -- controller
git diff --check
```

真实验收入口为`harness.cpu_affinity.validate_cpu_bound()`，只扩展执行身份验收，
性能数字与区间仍由现有`controller.stability_validation.validate_stable()`产生。
先保存`cpu_acceptance.json`，再检查两会话原有稳定性结论。

NorthJob继续使用原镜像、WeaverDev、qiji namespace/请求queue、实际queue另记、原toleration、
1节点×2 H100/256Gi；查重→展示完整命令→create一次→code200与唯一UUID→生命周期与验收分别核对。

## 实施与执行记录

- 新CPU绑定契约先红（缺option/helper），随后7项CPU契约及新旧 **98/98** 回归通过。
  包括真实owned子进程亲和性/不改变父进程、物理核去重、缺证据与线程逃逸拒绝、controller CI不变。
  中间一轮测试fixture缺manifest字段与mock参数不兼容，修复fixture后复验通过，未放宽实现判据。
- controller相对`1cde11b`零改动；shell语法与差异检查通过。A1/A2/A3、旧null与前序stable-a01
  均重新复算；前序stable-a01逐字段一致，未把历史失败改成通过。
- CPU绑定只修改本runner拥有的进程/线程mask；不占有CPU、不设置全局亲和性或共享GPU clock。
  实测仍待NorthJob；任务名`specpilot-p5-cpu-null-20261108-a01`初次查重total=0。

- 最终查重仍total=0，2026-11-08 00:36:47 +08:00唯一create code=200/data=None，
  精确名查询唯一UUID=`job-788af093f15c-20261108003647`，初始Pending；实际queue=proj-31。
  原镜像/WeaverDev/qiji/原toleration/2 H100/256Gi保持不变，前序任务已结束，未同时占4卡。
- 原始输出`logs/p5-cpu-bound-null-20261107-a01/`，提交/监控/回归/完整源快照在同前缀prep目录。
  源tar SHA256=`6558edfaea0377705f30c94e202ee3d91dcb3ddb74f47b98b710c70a9136f3da`。

## 实际结果

`job-788af093f15c-20261108003647`在node131执行，2026-11-07 16:37:05–17:22:20 UTC。
Job=Completed/Pod=Succeeded，容器/脚本exit=0，restart=0；此exit仅表示生命周期完整。
两会话各80 pair/160臂行，合计160 pair/320臂行；另176对预热不计入样本，
每会话仍只有20个不同请求，两会话不合并平均。两会话结束两卡均0 MiB/0%。

| 会话 | stock-b/stock-a 几何均值 | 分层双侧95% CI | CI全宽 | noise | 覆盖1 | 稳定化 |
|---|---|---|---|---|---|---|
| 1 | 1.0002672639252694 | [0.9998000779631615, 1.0007914498349078] | 0.0991371872% | 0.0791449835% | 是 | 通过 |
| 2 | 0.9990706079835362 | [0.9977318286820704, 1.000356733732648] | 0.2624905051% | 0.2268171318% | 是 | **未通过：全宽超过0.2%** |

两会话CPU执行验收均通过、区间均覆盖1，但第二会话精度未过，整体stable_passed=false。
独立稳定性门禁`logs/p5-cpu-bound-null-prep-20261107-a01/gate.py`明确exit=1，
`stability-gate.log`/`.exit-status`留存；不能挑首会话或仅看Job成功就称目标完成。

### 已验收的证据

- 源pin及逐文件SHA、原A1请求/模型/采样、stock树与block8匹配；controller相对`1cde11b`零修改。
- 8轮fresh双server、物理GPU×端口交叉、完整预热、逐请求HTTP时序及CPU/GPU监控通过。
- 两会话GPU/CPU映射完全相同：`GPU-36e9d0ec-5da3-363f-4540-f0593919394d`主核2/后台3–10；
  `GPU-cf5af737-ae15-e23b-40ba-4cea449aec4f`主核50/后台51–58。
  ready与完整预热后两次绑定均有证据；测量期间所有采样的server线程mask均符合固定映射。
- 所有请求跨臂/卡/轮/会话输出SHA相同，每对verify计数相同；这不是FP32-head forcing或lossless证明。
- 独立审计调用原controller产生的结果逐字段匹配持久记录，两次重放JSON完全相同。
  8轮正式测量采样到的SM频率均1980 MHz；实际HTTP发起最大时差为会话1的0.282497ms、
  会话2的0.259557ms。监控每次平均约0.243–0.265s，开销已包含在本协议环境中。
- 新旧98/98回归、shell语法、历史A1/A2/A3/null复算、前序stable-a01的141文件清单检查通过。

### 残余问题与停止边界

- 第二会话约80.57%的分层bootstrap方差来自HumanEval（按suite内log值的bootstrap方差分解，
  不是删样本后的重算）。例如第三轮`humaneval-114`双臂约3.797/3.944s，
  server e2e约3.794/3.942s，差异不是仅发生在HTTP计时末端；不能删除此请求来缩窄区间。
- 实际Pod API核对QoS为**Burstable**，CPU request/limit都没有；只有memory=256Gi与GPU=2。
  所以本实验是亲和性控制，**不是独占CPU实验**。当前CLI的`create --help`没有CPU预留或独占参数。
  资源快照与方差分解在prep目录`variance-and-resource-diagnosis.json`。
- 两秒GPU状态采样不能排除更短的瞬态，现有证据也没有逐核调度等待/外部负载；
  **不能断言共享CPU就是根因，也不能宣布CPU绑定已经解决问题。**
- 预登记的一次受控修正已用完，不再追加相同配置/修改样本数碰运气。后续需先确认集群支持的
  CPU隔离资源与官方提交方式，再登记可区分主机调度等待和引擎/GPU瞬态的新诊断。
  不擅自改共享集群设置、升级CLI或手写Volcano提交；已向用户询问可用隔离资源信息。
- 本轮没有lossless/晋升/论文数字结论，不读sealed、不进入RSI、不写晋升账本。

## 可重放验收与归档

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'  # 98项应通过
"$PY" -B logs/p5-cpu-bound-null-prep-20261107-a01/gate.py  # 预期exit=1，保留失败
"$PY" -B logs/p5-cpu-bound-null-prep-20261107-a01/reaudit.py
sha256sum -c logs/p5-cpu-bound-null-evidence-20261107-a01.sha256
git diff --exit-code 1cde11b -- controller
```

161文件/280099512 bytes清单：`logs/p5-cpu-bound-null-evidence-20261107-a01.sha256`。
清单SHA256=`3b76e931a655ea915d97a1fae2e13766c8d1d87e46514a12a155573ac1f23a8d`。
完整源tar、提交回执、生成模板、生命周期、原始JSONL/监控、独立复算及失败门禁均在持久共享工作区；
Git只追踪代码、协议、进度与证据索引，不提交这些大产物或凭据。
