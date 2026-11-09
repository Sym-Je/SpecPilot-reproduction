# GPU自治第二阶段：依赖复验与原方向接续

日期：2026-11-09；基准`d76eea0`。用户批准执行，并确认本阶段资源参数。

## 目标与边界

先证明依赖能在必要权限下加载，再由Master自主决定是否接续原方向，direction自主实验与迭代。
不由主助手设计科学实验，不要求正结果，不改controller、sealed、验收规则、账本或作者实现。
预检成功不是科学实验完成；合成张量结果不是27B端到端性能或lossless证据。

## 新阶段资源授权

- 总上限3600 H100 GPU秒，最多同时1张H100。
- 依赖预检最多1次，Pod硬期限600秒；研究最多2次，各1200秒。失败和冷启动计入总预算。
- 沿用已确认镜像digest `harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
- 项目WeaverDev、namespace/queue请求qiji、原infra-dev-weaver toleration；每任务1H100/128Gi，模型PVC只读。
- 本阶段独立计数，旧阶段16回合/26动作/2GPU尝试不抹去、不冒充仍有余额；恢复自己的脚本明确标注复用。
  新研究内部上限16回合/28动作/4CPU运行/2GPU尝试，Master仅在这些上限内分配。
- 预检失败则不启动研究GPU；预算不足、身份不明、保护边界失败、源码不匹配则停止。
  不盲目重复提交；单次create后精确查名确认code200及UUID。

## 验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/gpu-autonomy-stage2-prep-20261109-b01
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p20_gpu_stage harness.test_p19_gpu_autonomy > "$OUT/tests.log" 2>&1
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py' > "$OUT/regression.log" 2>&1
git diff --exit-code d76eea0 -- controller eval ledger memory patches costmodel assets/upstream
git diff --check
```

新增fixture须证明：旧契约兼容，新600/1200秒契约不可扩额，阶段接续只复制自身脚本/反馈且不清除历史。
GPU预检在相同worker边界下加载原实验需要的公开依赖并记录8类拒绝探针、版本、真实设备和退出码。
研究脚本由direction原样提供；每次冻结源tar、输入和筛选脚本，原始输出交回角色；成功/失败都可审计。
有候选才交controller；只做微实验时不声称独立controller已经验收。

## 流程与记录

1. CLI/凭据形状/PVC/预算预检及CPU回归。
2. 只提交一次依赖预检，核对真实GPU和权限边界。
3. 通过后启动受限Master；向它提供原方向自己的计划、脚本和真实反馈，自主决定继续或停止。
4. direction自主编写/运行/修复，Master复核；不以主助手补实验替代研究自治。
5. 独立核对来源、原始输出、资源和结论，更新主页/交接并审查公开内容后推送。

准备证据：`logs/gpu-autonomy-stage2-prep-20261109-b01/`。实际命令、UUID、结果与最终清单运行后追加。

## 实际执行与结果

**阶段执行已收口，但“首次有效科学测量”的目标未达到。** 依赖与受控算子执行已推进，
最终停在direction自己编写的筛选脚本错误；没有有效延迟数据或候选晋升。

| 类型 | UUID | 终态 | 结果 |
|---|---|---|---|
| 依赖预检 | `job-2ea20f106d5c-20261109191521` | Completed/exit0 | 真实H100、公开依赖导入和8类权限拒绝探针通过；59保守GPU秒 |
| 研究1 | `job-d8bd211a0273-20261109192612` | Aborted/exit1 | FA3延迟加载触发FlashInfer的`ptxas --version`子进程，被边界拒绝；41秒 |
| 研究2 | `job-258e42aa7878-20261109193328` | Aborted/exit1 | 可信预加载通过、8类探针仍全通过；随后筛选头维度不匹配退出；34秒 |

三次均先精确查名无匹配、显示完整命令/总GPU数，再各create一次，code200并由native name和Kubernetes确认UUID。
镜像、WeaverDev、qiji及只读模型挂载与授权一致；服务端实际queue为proj-31。
每任务观察到一个Pod UID、容器restart0，全部容器已终止。服务端maxRetry/retryCount无值，不宣称集群级零重试。
总计134保守GPU秒、67容器GPU秒，均在3600秒上限内；停止是研究尝试上限及Master决策，不是GPU时间用尽。

### 接入错误与自主决策

- b01的新预检证明最初未发给direction，它仅复述旧失败而未申请GPU；Master据实际空反馈自主决定继续。
  修正的是基础设施反馈分发，不是实验内容。
- b02的3个方向动作耗尽，GPU请求被拒；Master把“不得扩额”误解为不得分配阶段未用额度而停止。
  明确每个GPU请求也需1个action、Master可在阶段总上限内重分配后，b03由Master自主决定继续，旧stop及计数保留。
- 研究1失败后Master因没有已知可行修复路径而停止。主助手只读检查必要stock/公开依赖，定位到固定导入的版本探测。
  新执行器在运行任何研究代码前，可信初始化固定已安装的`sgl_kernel.flash_attn`并检查来源在sys.prefix内。
  不预加载direction选择的模块，不执行研究脚本，不改变stock算子或科学判据。
- b04向Master提供明确的工程修复说明、尚未GPU验证状态和真实错误，Master自主批准唯一剩余研究尝试。
  随后真实GPU证明预加载成功；研究代码执行前仍施加原Landlock/seccomp，8类拒绝探针全部通过，未开放研究子进程权限。

最终累计15研究回合/8动作/0研究CPU运行/2研究GPU尝试/19个usage-update事件，预检另计1次。
这些计数不是精确后台API请求数或token账单。8个新原生角色进程均exit0关闭，输入及无敏感canary未变。
每次角色启动和GPU执行前均冻结实际源tar；新阶段及各次恢复均保存自己的代码/反馈来源，非新独立发现。

### 科学结果与未完成项

研究2已经越过原导入/子进程故障，筛选比较时实际报出查询头张量`[1,24]`与KV头参考`[1,4]`不匹配。
**direction自行诊断为其GQA位置哨兵参考没有按查询头分组展开**，并明确不是注意力数值错误或延迟假设证伪。
该诊断尚未由修正后的筛选复测确认；主助手未修改科学脚本，也没有为了通过而放宽容差或判据。
两次科学脚本均与上一阶段原样相同，实验SHA为
`d0fe34655ede755c9c014e4f87aed170396a38c154c42065f310f58effb984e9`，筛选SHA为
`046b834bec017073344408632c63c3a87863a6bd80701ec57eb6c9c3e4f030fd`。
工程反馈上下文因新预检/修复说明而更新，各自冻结绑定，不能要求不同上下文哈希相同。

筛选没有完整通过、acceptance未执行、实验stdout为空，未进入延迟测量。
Master最终stop；不得把剩余GPU时间换成第三次研究尝试。不支持或否定原假设，无真实27B生成、
端到端加速、lossless、controller验收、候选晋升或论文数字结论。

## 最终验收与证据

- 38项定向/299项全harness CPU回归通过（全量37.021秒）；controller/eval/账本/记忆/stock/作者实现零改动。
- b01/b02无GPU审计、b03/b04真实GPU来源/原代码/源tar/原始输出/预算审计通过；b04两次独立审计字节一致。
- 新增5类协议篡改在隔离副本中均被拒，属于工程来源审计，不是controller数值正确性故障注入。
- 收尾验证最初误把更新过的工程反馈输入也要求哈希一致，已改为核对所有scratch代码不变、分别绑定各上下文。
  后续复制验证暴露6个容器root创建的外层包装日志不可读，仅将本阶段本人三任务的6文件恢复本人所有权后归档；不改内容。
  这些工程验证失败及处理记录保留，不覆盖科学失败或旧阶段证据。
- 上一阶段363文件SHA清单完整复核通过；本阶段另建新清单，不覆盖既有归档。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/gpu-autonomy-stage2-closeout-20261109-b01
"$PY" -B -m harness.gpu_autonomy_audit --directory logs/gpu-autonomy-run-20261109-b03 > "$OUT/audit-b03.json"
"$PY" -B -m harness.gpu_autonomy_audit --directory logs/gpu-autonomy-run-20261109-b04 > "$OUT/audit-b04-01.json"
"$PY" -B -m harness.gpu_autonomy_audit --directory logs/gpu-autonomy-run-20261109-b04 > "$OUT/audit-b04-02.json"
cmp "$OUT/audit-b04-01.json" "$OUT/audit-b04-02.json"
"$PY" -B "$OUT/verify.py"
git diff --exit-code d76eea0 -- controller eval ledger memory patches costmodel assets/upstream
git diff --check
```

机器状态`logs/gpu-autonomy-stage2-closeout-20261109-b01/stage-result.json`明确：
`dependency_import_preflight_passed=true`、`trusted_runtime_preload_gpu_verified=true`，
但`original_goal_met=false`、`scientific_experiment_completed=false`、`controller_accepted=false`。
driver/audit沿用的completed/gpu_autonomy_passed仅代表执行/反馈，不替代这些科学字段。

主要证据：`logs/gpu-autonomy-stage2-prep-20261109-b01/`至b04、`logs/gpu-autonomy-run-20261109-b01/`至b04、
`logs/gpu-autonomy-preflight-20261109-b01/`及上述closeout目录。
最终清单`logs/gpu-autonomy-stage2-evidence-20261109-b01.sha256`，统计与身份见同名json。
共314文件/12,185,277逻辑字节，两次全SHA通过；清单SHA256为
`1767ae60ca82564559175754911fa09a922354bbef573238b2666308bd2e7e82`。
Git同步回执单列`logs/gpu-autonomy-stage2-git-sync-20261109-b01.json`，不放入证据清单避免自引用。
公开Git仅发布通用实现和脱敏阶段记录，不发布方向原代码、原始响应或运行产物。

## 下一阶段建议（待批准，不执行）

让direction自主修复其筛选并先用不占GPU的头维度fixture自检，再由Master决定是否申请新GPU预算复验。
主助手只补通用工具，不代写GQA修复，不把同一脚本复用或失败反馈当成自主优化发现。
当前阶段不再提交，不进入integration/kernel、sealed或DSH。
