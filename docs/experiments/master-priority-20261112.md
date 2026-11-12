# Master自主复核实施优先级

## 目标与边界

用户批准：让Master自主补齐局部可实现收益、实际适用/临界路径暴露、端到端净收益的依据，并与其他方向比较；证据不足就降级，而非直接完整实现。
本轮同一逻辑Master重放自己的290份材料，记录来源与复用，不算新独立发现。原生角色身份见`logs/master-priority-20261112-a01/native-agent.json`。
本阶段0GPU/NPU、0NorthJob、0模型server、0Direction，不改引擎/controller/规则/账本，不读sealed/凭据/作者final，不接管Ascend。
原有62份dirty保留；主助手只提供统一交付/审计标准，科学分析、比较与决定由Master自主完成。

## 先行流程与验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native
$PY -B -m harness.master_native check --directory logs/master-priority-20261112-a01
$PY -B logs/master-priority-20261112-a01/review.py
```

先固定`ACCEPTANCE.md`，核对输入并保存旧工作；Master自主取证/计算/反例检查/比较/自审；维护者独立重放、保护检查后归档公开同步。
实际研究位于本阶段`research/`，原始材料不提交公开Git。交付验收不替代独立controller正确性与性能晋升。

## 完成的研究判断

没有候选得到足够证据支持整引擎实施，端到端预期保留unknown；K1从详细首版降级为有界完整算子对证伪。
推荐的是取证顺序，不是已测收益排名：E0同路径成本/暴露桥接→K1完整pair→T1最小真实分叉/全step→L1 logits消费链；N1融合/S1调度暂缓，B0当前M8直接切换backend的捷径停止。

历史十请求、两普通计时重复共5308个已提交verify。十份profile中target gate/up共170496次，draft另13320次；每请求多一个target图，合计640个额外target调用，其原因及是否属于可省墙钟仍unknown。
完整候选资格与因果暴露次数不能从结构层数或低overlap推出，仍未识别；不能把69层混合热点或kernel work占比当端到端可省比例。
K1不减少权重读取，也不减少名义两次launch；新增scratch流量、padding、数值、graph/分发与准备成本均需计入。

只在每verify有64次适用调用、完全有效暴露、额外100µs/verify、无固定准备成本的假设下，等请求平均墙钟下降1%/3%/5%需要完整pair分别净省5.385/13.031/20.677µs。
这些是反求投入门槛的条件算术，不是性能预测、置信区间或controller晋升阈值；实际局部节省和暴露尚未测得。

## 验收结果、故障与边界

原生连接传输中断时数值分析和13项CPU自检已落盘，恢复同一线程补写交付，不重跑取证、不算科学反证。
早期probe脚本的路径/gzip读取错误已自主修复；probe01旧源码未留存，只保留执行前SHA/堆栈，不用当前代码冒充失败原版。
Master完成自审、13项CPU检查及自身离线逐字节一致性复验；原生角色已关闭。维护者在独立副本重放分析与13项检查，除两个副本路径字段归一化外，JSON逐值完全一致。
维护者另核对68条来源记录/64个不同路径的SHA及成功采集回执，独立复算byte/FLOP/CTA与12个反求门槛；重读首份原始trace的89391个kernel，target gate/up为5248次，角色/work/区间并集核对通过。
4项`harness.test_master_native`回归、旧59份其他文件及3份共享文档原内容保留检查、290份自有材料和controller/账本/指定规则摘要检查通过。
Master自审将网络恢复误记为用户通知，实际是主助手在平台报错后发送同线程恢复指令；此来源归属更正记录于独立review，原研究文本冻结保留，不影响数值与排序。
详细回执见`independent-review-checks.json`、`independent-review-decision.json`及`preservation-final.json`；原始研究与失败记录私有持久归档，不提交公开Git。

本阶段完成的是**优先级判断与降级决定**，不是正收益证明。归档/发布身份以本阶段最终回执为准，不声称GPU正确性、提速或完整RSI；文件不变不证明未读禁区。
下一阶段按Master建议另审资源，由Direction自主执行最小同路径成本/暴露取证，再决定是否做K1完整pair及其他候选的判别；不由维护者持续代做科学实验。
