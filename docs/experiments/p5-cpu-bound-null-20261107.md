# 第5步：受控CPU亲和性null实验

状态：预登记，尚未提交。前序为`p5-stable-null-20261107`，执行基准`1cde11b`。
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
