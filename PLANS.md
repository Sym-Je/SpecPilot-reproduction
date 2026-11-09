# 当前执行计划

日期：2026-11-09。入口为[HANDOFF](HANDOFF.md)，长期规则为[AGENTS](AGENTS.md)。

当前用户已授权本地8卡Ascend、DSH＋Claude 5.5与500美元API上限；MRV2可不用。旧H100/NorthJob提案仍不自动执行。

1. 冻结dev60/validation40及9组baseline协议。已完成；validation不参与研究。
2. 完成预算/恢复/真实MCP边界验收。已完成；22项定向测试及真实工具探针通过。既有278项回归因旧H100路径及Landlock环境不满足而未全过，详见阶段记录。
3. 跑完MRV1同步调度、固定DSpark K7的9组dev baseline并独立审计。进行中；异步C32失败、瞬态监控断线及重试保留。
4. 真实DSH调度器等待baseline，通过后Master自主选方向/预算，Direction串行设计、执行、迭代。通用基础设施不代做科学研究、不预设收益。
5. 最多3个方向，各最多3次NPU实验；每次LLM调用预占，不退款释放未确认费用，累计不超过500美元。NPU使用机器已有互斥锁，不中止其他已授权工作。
6. 研究停止后冻结唯一实测候选，独立程序打开validation做最后比较；不回流调参。若无候选，报告无收益并仅完成基线终测。
7. 保留服务、报告真实绝对吞吐/延迟和限制，归档源码身份/原生DSH轨迹/可信工具结果；公开仓库仅同步代码与非敏感摘要。

阶段文档：[Ascend执行与验收](docs/experiments/ascend-ctrip-dsh-20261109.md)。
串行筛选及终测不替代受保护controller的配对晋升；历史teacher参考不是已核实正确答案。
