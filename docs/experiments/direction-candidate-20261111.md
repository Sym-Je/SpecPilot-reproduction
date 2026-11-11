# 接受量证据之后：Direction 自主最小候选研究

## 授权、目标和边界

用户批准本阶段：累计4 H100 GPU小时、最长4小时、最多并发2卡；失败和冷启动计入，旧余额不结转。
沿用已确认镜像digest、WeaverDev/qiji、只读模型挂载、toleration和higher-priority-job。
先复用已验收的接受量/路径/计时证据，由Master分配Direction实际研究，
不是重复Master的条件算术，也不是维护者代写科学实验。无可信候选可以停止。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_decisions harness.test_acceptance_headroom harness.test_headroom_evidence
$PY -B -m harness.master_decisions_audit --root logs/direction-candidate-20261111-a02 --terminal-review
```

1. 保存旧dirty和三份共享文档，不混入阶段提交；独立登记新资源上限。
2. 复用历史SHA绑定回执，通过原证据出口重验，向Master分享公开stock事实，不分享旧角色私有推理。
3. Master自主选最小候选，Direction自主读stock、先写自检、设计/执行/修复CPU实验并返回可执行方案或反证。
   不把线性block16当N16树，不把离线oracle标签当线上输入，不强求正收益。
4. 若提出可执行GPU实验，由可信执行器核对CPU回执、源码option、预算、镜像/挂载和任务查重；
   展示完整命令/总卡数后只提交一次。研究角色没有提交权限。
5. 拟保留候选必须经现有controller独立dev正确性及配对性能验收；CPU自检不是lossless，
   诊断也不是sealed晋升。不可行/证据不足则封存阴性结论，不凑GPU任务。
6. 原生角色、实际脚本、反馈、资源、退出码独立审计，指定回归与公开副本复验，归档并更新主页和交接。

CPU自主研究沿用原受限工具、30分钟/16回合/240动作/32CPU额度/2方向保护；
本阶段4小时为整个资源阶段上限，不自动延长单次研究进程的保护。
本阶段不改controller/规则/账本，不读final/sealed，不接管Ascend。

## 合理性自检

先确认候选语义及可执行路径，能减少无效GPU初始化；真正研究由Direction完成。
但不能以工具测试通过代替科学实验完成，也不能因已有接受量空间就预言端到端提速。
源码执行若超出现有可信路径，明确记录缺口，不绕过隔离直接运行。

## 实际执行结果

**本阶段完成了Direction最小CPU候选研究及反馈复核，没有完成真实树引擎实现或GPU验收。**

- Master依据已复核历史接受量/图路径/同cohort计时，比较四维后选择tree16-selection。
  历史N16进度比1.164613只是完整step成本的条件盈亏门槛，不是本候选实测收益。
- Direction自主读stock、先写自检、实现D7/含anchor N16的前缀闭合候选。
  当前token是合成候选索引，线上选择仅用draft一元分数，没有使用未来target/oracle标签。
- 初次自检因CPU额度耗尽被拒，原生入口300秒超时；失败、28次工具动作及8份CPU额度原样保留。
  新受限逻辑续接只重放该角色自己的代码/回执，Master只得到状态、自己的决策和最终Direction报告。
  续接沿用同一阶段累计计数，不算独立发现或新一轮RSI。
- Direction自行修复CPU恢复写入限制和本地模块导入问题，最终自检exit0：100组合成分数、
  预算1/2/8/16，2700次节点/提交检查，6类人为分叉错误被检测。两次独立隔离CPU重放输出相同。
  这只是玩具状态契约，不证明真实attention/KV/SSM、近并列FP32或真实模型lossless。
- Direction判断当前产物还不是stock树适配器，不建议GPU：需要分离draft深度/verify节点数、
  映射真实token、ancestor mask/depth位置、父状态执行、greedy接受路径及原子提交/回滚。
  这些是待实现/待验证项目，不把源码推断写成真实GPU验证。
- Master收到该原生报告后明确stop、gpu_request=null；不是判定树方向无效，而是不满足真实执行门槛。
  未生成可保留的真实引擎候选，因此没有controller dev gate、sealed或晋升。

### 工程异常及处理

原CPU编排器在方向返回后因固定预留300秒拒绝最终Master回合，并非真正耗尽30分钟。
原异常结果保留，不改写为正常pipeline完成。随后进行零工具的有界管理审核，仍受整体4小时授权约束：
首次审核把上下文只放文件却关闭读工具，Master正确报告缺证据；第二次因沿用即将到期的旧时限中断；
第三次直接交付原生报告和Master自身历史，取得有效stop。失败审核不删除，也不算研究进展。

已修复未来入口：单回合使用有界时限；每回合重新依据剩余时间设置，临近收尾不固定预留300秒；
中断也在finally计入实际工具/CPU额度；续接核对原生wire及退出回执，拒绝未审计的嵌套续接。
这些收尾修复没有热加载进已结束角色，冻结启动源码与post-run修改分别记录。

`--terminal-review`是明确的异常工程收口审计，不放宽controller科学门禁，也不声称正常闭环完成。
它额外核对报告确实出现在Master提示中、失败/成功审核累计计数及实际进程退出。
默认审计仍拒绝该异常pipeline；不能只凭某份审核输入文件存在就声称反馈已交付。

### 资源和证据

- 授权4 GPU小时/4小时/并发2卡；实际新增NorthJob=0、GPU小时=0，没有待提交任务，余额不自动结转。
- 研究与管理审核累计76工具动作、19份CPU额度、11次原生请求；其中2次中断、9次完整响应。
  CPU额度包括搜索/分析，不等于19次自写脚本运行。Direction实际执行3次脚本，2次失败、1次成功；
  另有2次维护者独立重放，仅作回执验证，不算Direction新研究。
- 原始失败：`logs/direction-candidate-20261111-a01/`；逻辑续接、CPU输出及最终审核：
  `logs/direction-candidate-20261111-a02/`。保持14份实际子进程退出回执，未留下研究服务。
- 本轮不读final/sealed，不改controller/规则/账本或可信memory，不接管Ascend；47份原dirty独立保留。

后续若获批，仍应由研究角色自主设计真实树适配与分支差分验证；维护者只提供通用受控通路。
不能跳过实际路径和独立dev正确性，直接用线性block16计时或合成契约宣称N16树收益。

## 最终验收

- 243项指定CPU联合回归通过，排除全部旧dirty和私有产物的公开源码副本同243项通过；不是仓库全量测试。
- `audit-02.json`/`audit-03.json`完全一致；原生工具/CPU作者/反馈交付/旧证据/启动源码及实际退出核对通过。
  显式标记异常工程收口、原pipeline未正常完成，不以审计通过认证研究结论。
- 2700项方向自检独立隔离重放两次一致；14个子进程退出码0且均已消失。
- 47份原dirty保留，仅给三共享文档追加本阶段段落，不混入旧ceiling或Ascend修改。
- 原始证据仅私有SHA归档；阶段提交/远端校验以`logs/direction-candidate-20261111-publication.json`为准。
