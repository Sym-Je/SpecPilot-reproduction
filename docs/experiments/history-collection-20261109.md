# 独立接受历史计数采集与固定规则筛选

日期：2026-11-09（北京时间）。基准`40e45f8c0b91732406ca6cc9a3f1712c0cd91e25`。
用户批准：GSM8K/HumanEval各2个新dev请求、两次fresh采集、原T001 CPU确认；1H100、总上限30 GPU分钟。
另明确允许沿用底层模板适配添加只读模型PVC。只做stock诊断，不是单卡A/B；不报加速或晋升。

## 固定协议与停止规则（实现前登记）

- 源池为既有作者dev两suite各20题，不修改eval。排除原3诊断请求的ID、token输入SHA及可关联的规范文本SHA。
  全池按规范文本/token SHA去重；别名只保留稳定ID排序首项。以
  `SHA256(history-confirmation-v1|suite|input_sha256)`排序，每suite取前2项；不依据输出、接受量或预测结果选题。
  清单、源池SHA、排重和选择均在GPU提交前由受控程序冻结；题目和token级产物私有保管，不提供给agent。
- 沿用已验收stock诊断副本，原stock/观测钩子/默认关闭行为不变；block8、greedy、seed0、2048cap、自然EOS。
  1GPU上两次fresh server各运行短预热、4题全尺度预热、4题正式采集。不是方案比较，无性能结论。
- 每份真实链必须绑定原生HTTP/模型配置/运行树及观测模块SHA，并用既有线性重放器复验；两轮输出/接受序列一致。
  不一致、缺链、失败或超时则保留失败记录并停止，不换题/规则/预算追绿，不自动重新提交。
- 沿用T001整请求留一、前一步计数预测、首目标排除、仅训练请求拟合的均值/中位数/同suite常数。
  4新题单独评估，不混旧3题，两轮合并为4独立请求；每请求严格优于所有适用常数只作既定规则的保守筛选。
  未通过则停止固定一步规则路线，不代表否定全部历史策略；通过也只是4题初筛，不证明总体泛化/预算收益。
- 最多1节点×1H100/128Gi，30分钟Pod硬期限、禁Job重试，前台监督所有进程；不自动提交第二次。
  项目沿用已批准修正的WeaverDev，namespace/请求queue=qiji，toleration仍infra-dev-weaver，三者不混淆。
  沿用已确认镜像digest `harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
  提交前重读CLI help/查重、完整命令和总GPU展示；code200+精确UUID、启动、科学验收分别记录。

## 先写验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p14_history_collect
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
bash -n exp/history_collect_remote.sh
git diff --exit-code 40e45f8 -- controller orchestrator patches costmodel assets/upstream ledger memory
git diff --check
```

先红后绿覆盖选择不受输入顺序/别名影响、旧诊断与规范文本重复排除、样本不足拒绝、重复漂移拒绝、
训练测试隔离、无性能结论、单卡模板限制/只读挂载/30分钟期限/禁重试。
远程后独立CPU审计重放两次、真实链故障注入、SHA归档、资源清理、原master评估及README/HANDOFF提交推送。
新入口不绕过原固定3题入口，不改controller/原观测机制；不读取final实现、sealed，不实现预算option或RSI。

## 当前状态

执行源码pin=`6d0676b618bd73d9a55cda6e569780fac042191e`，source.tar SHA=
`327a6f40a235384f8f9fa2d4dfb7a561ca872ccff8bb36db2cf8e056cbd925c8`。
10项定向/234项CPU回归通过；原5598项真实链归档复验通过。manifest在提交前冻结，SHA=
`c52c30e0494bf4f925a71e716f5cf321c77d9ab2882c331830f4b7ff63b25272`。
新4题输入长度111/109/231/338；不含旧诊断ID/token输入及可关联规范文本重复。

已create一次code200/dataNone；精确查名解析服务端`name`字段UUID=
`job-a0d49c75347b-20261109123806`。最初解析器只找job_uuid/job_name而失败，未再次create；原查询保留。
当前node233/实际queue=proj-31，1H100/128Gi、原镜像digest/只读模型挂载/1800秒Pod期限已核对。
预检sglang0.5.20/torch2.13.0/恰好1H100通过；仍在采集，未得到确认结果。

**调度偏差：**提交YAML明确请求maxRetry=0，但服务端返回spec不含该字段，且保留PodEvicted/PodFailed→RestartJob策略。
不能宣称服务端已禁重试；没有静默修改在线Job或重复提交。增加本机前台budget_guard，监控原Pod UID/
容器重启/可见Job重试；发现替换/重启则终止这个精确UUID，或最迟自创建1700秒时终止，以保守守住30GPU分钟。
该有依据的停止只针对本次自有任务，正常结束不删除。原生Pod1800秒期限同时保留。
最终报告必须区分请求配置、实际返回配置与观察到的生命周期，不用缺失retryCount冒充零重试证明。

## a01失败与已批准的a02修复

a01单次create已明确Failed/exit1。04:38:29–04:41:25 UTC共176秒，容器折算2.9333 GPU分钟；
为总预算保守按创建04:38:06至结束199秒计费，剩1601秒，约26.7分钟。
单Pod UID、容器restart0；Job retryCount最终为1，不能称其为零，也没有观察到第二个Pod或容器启动。
原server已成功就绪并完成1次32token短预热，但事件调用`phase`关键字与位置参数重名引发TypeError；
不是模型/引擎故障，尚无正式四题采集。原输出/日志/失败目录保留，不作确认数据。

用户已明确批准修复验收后再提交一次，镜像/四题/1H100及总30GPU分钟不变。
新增CPU生命周期回归真实走两轮18次请求的外层逻辑，已先重现相同TypeError，再只改日志字段为stage；
fake server/client结果只用于工程测试，不是实际采集。新模板明确PodFailed/PodEvicted→AbortJob，
不依赖maxRetry=0是否被服务端省略；a02须核对实际返回策略。新Pod期限1560秒、runner1440秒+
60秒清理，外部监控自创建1500秒停止；即使算上a01的199秒，仍在1800秒总预算内。
新任务用a02独立pin/tar/目录/UUID；原预登记选择、预测和两轮契约均不改，不合并失败预热数据。
