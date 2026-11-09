# 第三阶段：direction自主修复与完整微实验

日期：2026-11-09，北京时间；基准`3abeca0`。用户批准完整探索窗口，并确认沿用镜像和项目。

## 目标和权限

Master分配完整调试预算；direction自主复核自身诊断、编写修复和CPU fixture、执行GPU并按反馈迭代。
主助手只维护通用执行/权限/审计，不代写科学代码，不替agent作研究决策，不放宽原容差或科学判据。
允许负结果或停止；成功仅表示微实验可解释，不是27B端到端提速、controller晋升或论文数字复现。

## 本阶段授权

- 总上限3600 H100 GPU秒，最多同时1卡，最多3次研究任务，每次Pod硬期限900秒；失败和冷启动计入预算。
- 镜像`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
- 项目WeaverDev，namespace/queue请求qiji，原infra-dev-weaver toleration及只读模型PVC；每任务1H100/128Gi。
- 新阶段独立计数，旧阶段全部代码/错误/计数保留。内部上限64动作/8研究CPU运行/24研究回合/128usage事件。
  Master在总上限内自主分配、重分配；direction可请求预算，不能自行扩额或直接提交NorthJob。
- 每脚本180秒；研究代码仍禁子进程/网络/越界访问；固定可信依赖预加载沿用已验证实现。
- GPU前必须有direction自身CPU自检成功回执，与本次科学脚本SHA绑定。CPU只有标准库，不冒充真实算子数值验证。

## 验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/gpu-autonomy-stage3-prep-20261109-c01
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p21_gpu_iteration harness.test_p20_gpu_stage harness.test_p19_gpu_autonomy > "$OUT/tests.log" 2>&1
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py' > "$OUT/regression.log" 2>&1
git diff --exit-code 3abeca0 -- controller eval ledger memory patches costmodel assets/upstream
git diff --check
```

fixture检查900秒/3次契约不可扩额、旧契约兼容、CPU自检与代码绑定、阶段内Master分配不超剩余预算。
实际验收分开记录：agent原代码来源、CPU故障复现/修复、GPU筛选、延迟原始数据、角色决策和资源终态。
若判据被放宽、证据不匹配或权限探针失败，不可宣布有效实验；有候选才交controller。

GPU每次先核对CLI帮助/凭据形状，精确查名，显示完整命令/总GPU数，create一次并确认code200+UUID；不确定不重提。
运行后追加实际结果，更新主页/计划/交接，冻结原始证据并公开审查后提交推送；不发布原始研究代码或上下文。

## 实际结果：自主修复和微实验目标完成

Master自主选择继续原`verify-attention-block-scaling`方向，分配24动作/4CPU运行/2GPU尝试。
direction自行修改其筛选脚本、编写CPU回归fixture并申请运行；主助手没有代写科学修复。
最终4研究回合/8动作/1研究CPU运行/1研究GPU尝试/10个usage-update事件。
这些不是精确后台API请求数或token账单。实际无需预算重分配，request_budget额度检查只经fixture验证。

### 自主修复与判据完整性

- 原错误来自同一方向上一阶段的真实GPU失败，旧反馈与代码原样接续、来源明确；修复不算新算法发现。
- direction添加自己的GQA哨兵映射辅助函数并接入原筛选，未改原FP32参考容差、位置哨兵容差或三个测试长度。
  计时脚本与旧版本逐字节相同，原11轮/每组40次/20次预热及中位数阈值均保留。
- 其CPU fixture从实际生产筛选中AST提取新函数，模拟矩阵接口，覆盖3种头数关系、3种长度、2种查询宽度，共18例。
  使用不同KV头偏移来区分分组映射错误，并检查分析式因果位置均值；复现旧形状问题后验证修复，不是仅语法检查或打印常量。
- 本次CPU成功回执含科学代码SHA，GPU入口强制匹配当前实验/筛选代码。独立重放该CPU fixture两次，输出均与原生回执字节一致。

实验脚本SHA仍为`d0fe34655ede755c9c014e4f87aed170396a38c154c42065f310f58effb984e9`；
direction修复后的筛选SHA为`f31d1102e5d301ca5fe28c8eca571653b559d11e713466cb69ba831b2c95798d`。
原代码、实际write_file请求和工具回包只保留在忽略的logs，不上传公共Git。

### GPU执行与有限科学结论

任务`specpilot-stage3-20261109-c01-r01`，UUID=`job-4fdd307bbdb9-20261109202445`。
提交前查名无匹配，展示完整命令/1GPU资源摘要，create一次返回code200，native name及Kubernetes身份核对通过。
最终Job Completed/Pod Succeeded/容器exit0；观察1个Pod UID、restart0，服务端maxRetry/retryCount无值，不宣称集群零重试。
使用确认的镜像、WeaverDev和只读模型挂载，队列请求qiji、服务端实际proj-31；Pod硬期限900秒。
创建至结束保守43GPU秒，容器26秒，3600秒总预算内；资源已释放，两个角色进程均exit0关闭，输入/canary未变。

真实H100、SGLang0.5.20，BF16/batch1/24查询头/4KV头/head_dim256。
实验内筛选及另一个独立进程中的研究筛选均通过，保留原数值和因果位置判据，8类权限拒绝探针均通过。
以下仅为**单GPU内交替查询宽度的合成算子微实验**，不是双卡配对验收、controller性能数字或端到端加速比：

| 总KV长度 | q8/q1耗时比中位数 | 原协议判定 |
|---|---:|---|
| 512 | 1.004447 | 小于8 |
| 2048 | 0.997850 | 小于8 |
| 8192 | 1.003922 | 小于8 |

独立从原始11轮q1/q8耗时重算每轮比值、中位数、极值及原阈值判定，均与原输出一致。
按预先约定的微实验协议，本次支持“查询宽度8不需要8倍耗时”的有限假设；Master自主停止，不为了用完预算继续跑。
2048组异常单查询轮次原样保留，没有删除或修改判据。范围不是置信区间，本阶段没有出CI。
计时为eager调用外围CUDA事件，包含调用间隙和分配影响，不能分离纯kernel耗时，也不能据此认定真实部署瓶颈。
只覆盖连续KV、全局因果注意力；不覆盖分页缓存、树掩码、局部注意力、调度或图重放。
没有真实27B生成、端到端提速、lossless、候选option实现、controller验收/晋升或完整Phase1/RSI证明。

## 最终验收与证据

- 25项定向/303项全harness CPU回归通过（38.910秒），保护目录零改动，旧314文件归档SHA复核通过。
- 两次独立GPU来源审计字节一致，核对角色原生请求/恢复来源、作者代码、CPU代码绑定、实际冻结源tar、原始输出和预算。
- 两次独立CPU重放通过，微实验原始数据重算通过；6类工程篡改副本全部被拒，不是controller数值正确性故障注入。
- 本人容器创建的2个外层包装日志仅恢复本人所有权供归档，内容未修改；原始stderr、stdout和退出回执完整保留。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/gpu-autonomy-stage3-closeout-20261109-c01
"$PY" -B -m harness.gpu_autonomy_audit --directory logs/gpu-autonomy-run-20261109-c01 > "$OUT/audit-01.json"
"$PY" -B -m harness.gpu_autonomy_audit --directory logs/gpu-autonomy-run-20261109-c01 > "$OUT/audit-02.json"
cmp "$OUT/audit-01.json" "$OUT/audit-02.json"
```

首次独立验证入口`logs/gpu-autonomy-stage3-closeout-20261109-c01/verify.py`，回执`verification-first.log`；
该入口在新目录执行CPU重放，已有产物不要覆盖。完整机器状态见同目录`stage-result.json`：
`stage_goal_met=true`、`autonomous_repair_and_experiment_completed=true`、`scientific_microexperiment_completed=true`，
同时`controller_accepted=false`、`candidate_promoted=false`、`full_phase1_completed=false`、`real_engine_rsi_completed=false`。

证据目录为`logs/gpu-autonomy-stage3-prep-20261109-c01/`、`logs/gpu-autonomy-run-20261109-c01/`和上述closeout。
每次角色启动及GPU执行前均冻结实际源，角色仅接续自身方向的历史，没有开放根Git/其他方向/作者final或sealed。
最终清单`logs/gpu-autonomy-stage3-evidence-20261109-c01.sha256`，身份与统计见同名json，不覆盖旧归档。
共126文件/4,835,333逻辑字节，两次全SHA通过；清单SHA256为
`e52b13d9550139145010e90dee311f4608a99c4bb8633c63bbf8307dcdd8f321`。
Git同步回执单列`logs/gpu-autonomy-stage3-git-sync-20261109-c01.json`避免清单自引用。

## 下一阶段建议（待批准，不执行）

由Master根据真实微实验及已有stock证据，评估如何映射到真实部署路径，再分配下一项验证或可开关候选实现。
不将本次算子比值换算为整模型收益，不强制继续VERIFY或作者final机制，不直接进入integration/kernel/sealed。
