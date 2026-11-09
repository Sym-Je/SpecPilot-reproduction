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

准备实现与CPU验收；尚未提交GPU，尚无独立预测结果。
