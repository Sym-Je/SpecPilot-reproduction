# 第 5 步：固定全尺度预热与受监控 null 复验

状态：准备。基准 `1f7e551`，用户授权本大流程内部自主实现、调试及复验。
授权不包括放宽判据、挑选会话、访问 sealed、修改作者实现或设置共享 GPU 时钟。

## 执行前固定的协议与验收

- 原 A1 的20个 dev 请求、每 suite 4条、turn0、2048 cap、自然 EOS、greedy/thinking。
- 原镜像 digest、stock tree/block8、模型不变。仍为1节点×2 H100、256Gi，最多同时2 GPU。
- 先原有两次32-cap预热，再固定完整运行全部20条2048-cap请求一次，均不计入正式样本；
  每条预热原样记入独立 warmup.jsonl。没有“预热到CI通过”的自适应循环。
- 每会话预先固定4轮 fresh双server，GPU分配0/1、1/0、0/1、1/0；
  A/B端口分配前两轮正常、后两轮交换，使每臂各经历每种GPU×端口组合一次。
  进程启动和HTTP任务提交顺序均为A/B、B/A、B/A、A/B；HTTP任务另使用双线程屏障，
  记录实际时序，不把屏障当作真正完全同时发包的保证。
- 两次独立会话，不能把两个会话合并平均后掩盖失败。每会话仍只有20个不同请求，
  四轮在同一请求内聚合，不冒充80独立请求。每会话80 pair/160臂行，总160 pair/320臂行。
- 正式统计复用 controller：suite等权、request-cluster log bootstrap、双侧95% CI、seed0、10000次。
  **每会话CI全宽<0.002**，两次都须通过。noise仍为区间端点距1的最大距离，不能当成半宽。
  点估计与系统性偏移独立报告，即使区间窄也不声称无偏；无lossless/晋升/论文数字结论。
  本轮额外工程自检要求两会话CI都覆盖1，防止“窄但明显偏移”被当成稳定目标达成；
  这是比原精度门禁更严格的条件，不冒充论文新增判据、不替代原noise定义。
- 每2秒记录两卡频率/温度/功耗/利用率、进程CPU亲和性/CPU累计时间/cgroup状态。
  只读监控；不设置 GPU clock，不杀未知进程，不改变引擎或请求内容。
  监控覆盖启动、预热和测量，其开销属于本协议，不能称为零开销。
- 默认不启用新协议，旧 AR/stock/final 诊断与验收保持原行为。新路径由显式 stable-null option 启用。
- 验收必须检查实际预热覆盖、独立计时文件、四轮GPU×端口交叉、HTTP时序及监控覆盖；
  标志存在但证据缺失必须拒绝。生命周期成功与精度通过分开记录。

先写并运行CPU契约测试（应先红），再实现，最后执行：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p5_stability.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'
bash -n exp/p5_remote_stable.sh
git diff --check
```

NorthJob 每次先查重、展示完整命令/总GPU，create一次并核对code200与唯一UUID。
project=WeaverDev、namespace/请求queue=qiji、实际queue另记，原toleration不变。
无新image确认需求：沿用用户已确认 `harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。

首个固定协议若未过，保留所有结果，基于新增证据诊断并预登记实质修正再执行；
不能同配置盲重跑追绿。用户已允许本大流程内部自主调试，涉及额外权限/共享硬件设置仍须单独审批。

## 执行记录与结果

- 新协议契约先红：`logs/p5-stable-null-prep-20261107-a01/red.log`。
  实现后9项初测通过，再补偏移/缺失计时/反向提交身份测试，新旧最终 **91/91** 通过。
- 历史A1/A2/A3统计及旧null结果复算通过，旧null两会话精度仍为false/true，没有回改。
- 新入口 `exp/p5_remote_stable.sh <新输出目录> <冻结A1目录>`，两会话顺序执行。
  启动模型前先验证GPU监控能力，无法获取时明确失败，不跑完后假装监控存在。
- 截止提交准备，当前CLI帮助已核对、任务名 `specpilot-p5-stable-20261107-a01` 精确查重total=0。
  没有升级CLI、没有替换已确认镜像。真正提交前展示完整命令与资源。
- GPU复验结果待执行。真实 scorer/故障注入/sealed/RSI不属于本次噪声稳定化验收。
