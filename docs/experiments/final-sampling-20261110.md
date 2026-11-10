# 作者 final 的随机采样性能验证

用户已批准执行：累计8 H100 GPU小时、最长6小时、并发2卡；失败/冷启动计入。
镜像沿用`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`，
WeaverDev、qiji namespace/queue、既有toleration及只读模型PVC，priority3。
独立预算`logs/final-sampling-run-20261110-a01/resource-state.json`；不结转或占用其他阶段预算。

## 冻结协议与先行验收

```
/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python -B -m unittest harness.test_sampling_protocol -v
```

- 仅测固定作者产物stock block8与final int-015-tlvcbn32及46个原配置开关；不修改引擎、controller、eval或sealed。
- 温度0作为greedy对照；正温度0.7、1.0时必须top_k=-1、top_p=1。不能保留top_k=1后宣称测试了随机采样。
- 20个公开dev题，5suite各4题，thinking、自然EOS、2048 cap；seed固定0、1。
- 正式每个温度两轮fresh server并物理互换GPU；同题/seed/轮配对，不要求两臂输出相同。
- 主要指标final/stock输出token速率比；先在同一题内平均seed/轮的log比，再用现有controller.stats做suite分层request-cluster 95%CI。
  20个题簇，不将80个pair视为80个独立题。另列耗时、长度、EOS/cap、各suite/轮结果。
- 报告两臂原始spec计数；final的TLV计数不保证与stock同口径，不将tokens/spec_verify_ct直接解释成可比的接受长度。
- 先做正温度兼容性预检：请求/响应和日志留证，检查报错、不同seed输出及可用logprob中的非argmax token。
  若固定final拒绝或忽略随机采样，不修改作者方案“修好再测”，报告不支持/未证实支持；不对无效条件宣称加速。
- 同seed不保证stock与final逐token一致；本阶段不以greedy argmax规则判采样无损，也不宣称采样分布保持。
- 先预检再决定是否提交正式测量，未通过正温度预检时停止扩展性能结论；旧greedy数字不冒充本次结果。

当前状态：正温度预检已结束，作者固定final不支持该随机采样模式；停止正式性能测量，不修改作者方案。

## 执行和证据

入口`exp/sampling_resource.py`的prepare/plan不提交；execute/resume经既有可信broker查重、预算、code200/UUID和终态核对。
冻结请求、实际源码tar和模型/引擎身份。所有新目录独立，不改既有研究、ceiling和Ascend执行记录。
此任务是用户要求的作者产物适用性验证，不属于自主发现、正式sealed或晋升。

## 结果：固定 final 的树验证路径仅支持 greedy

- 唯一任务：`sp-finalsample-20261110-a01-probe`，UUID `job-e40732cde3aa-20261110233451`。
  服务端code200、容器启动和GPU实际执行分别留证；任务最终Completed/exit0，表示诊断器完成，**不表示final通过**。
- stock block8与final block32均成功启动。final使用`int-015-tlvcbn32`、原46个开关，
  包括`SPECPILOT_TREE_MODE=ddtree`；重算两棵引擎树SHA与冻结身份一致。
- 三个公开dev题、每题两seed：stock在temperature=0、0.7、1.0各6次成功。
  正温度下三个题均随seed产生不同输出；附加logprob探针分别发现8和11个非argmax token，支持确实执行了采样。
- final首先完成同一道题的两次temperature=0请求；首次temperature=0.7、seed=0请求即触发：

  ```text
  NotImplementedError: SPECPILOT_TREE_MODE supports greedy requests without grammar or logprobs only.
  ```

  此请求没有grammar或return_logprob；该限制来自非greedy检查，而不是后面的logprob诊断。
  scheduler随后退出，后续连接失败。**temperature=1.0没有在存活的final服务上独立执行**，
  不能把后续连接失败当成另一轮独立反例。
- 只读核对作者原始setting覆盖文件与派生worker逐字节相同；其树模式显式拒绝非greedy请求。
  因此，当前固定final不能给出正温度下的有效加速比/CI；不是“加速比低”，也不是证明所有变体或所有推测解码不支持采样。
  关闭树模式或新增采样实现会改变受测方案，留待单独授权，不能悄悄修好后仍称同一个final。

## 验收与收尾

- 6项采样协议CPU测试通过；两次独立进程audit输出逐字节一致，并与远端结果一致。
- 独立复核18个题/温度/seed组合唯一完整、成功请求参数/原始响应绑定、原配置、引擎树、作者worker、
  logprob、任务终态、预算和GPU清理；详见`logs/final-sampling-prep-20261110-a01/independent-review.json`。
- 一次双H100预检，保守330 GPU秒（0.091667 GPU小时），冷启动/失败计入；未提交正式测速，
  未使用sealed、未写晋升账本、未证明采样分布无损。两卡收尾显存占用均为0，容器无重启。
  请求namespace/queue为qiji，服务端有效queue为proj-31，分别记录，不把队列当项目。
- 原始证据：`logs/final-sampling-run-20261110-a01/`；CPU回执：`logs/final-sampling-prep-20261110-a01/`。
  本阶段只收口作者产物适用性验证，不接管其他H100或Ascend研究，也不自动使用剩余额度。
- 67文件清单两次SHA校验一致：`logs/final-sampling-evidence-20261110-a01.sha256`，
  SHA256 `84b36b7da9154e79c8d6b2d642439400749a23835412d4ea7be8c5ddf3db6700`。
  私有归档`logs/final-sampling-evidence-20261110-a01.tar`，
  SHA256 `31072f976087bfd9f0c1c1e97a0eef70cd4f5ad42ef7280fb4e5abe5bafb7ee3`；原始产物不进公开Git。

独立复验入口（不提交GPU）：

```bash
/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python -B -m exp.sampling_run audit \
  --directory logs/final-sampling-run-20261110-a01/sp-finalsample-20261110-a01-probe/remote
sha256sum -c logs/final-sampling-evidence-20261110-a01.sha256
```
