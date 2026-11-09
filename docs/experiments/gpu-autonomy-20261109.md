# 首轮受控 GPU 实验自治

日期：2026-11-09（北京时间）；基准`facdbbc`。用户批准完整阶段，并再次确认以下配置。

## 目标、授权与边界

复用独立受限Codex入口，跑通Master选一个方向 → direction自主设计/写代码/执行 →
真实GPU反馈 → direction继续或停止 → 原Master复核。不由主助手代做科学实验。
本阶段允许失败或无候选，不要求正收益；不宣称完整Phase 1/RSI、真实模型端到端提速或论文数字达标。

- 用户确认镜像：`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
- 项目`WeaverDev`，namespace/queue=`qiji`；沿用`infra-dev-weaver` toleration，不将它当专属节点选择器。
- 总上限2 H100 GPU小时，最多同时2 H100，最多2个有独立身份的GPU尝试；失败、冷启动与排队占卡均记账。
  最小脚本实验优先1 H100，单任务不超过26分钟，单脚本180秒。实际需求由agent提出，可信入口不得扩额。
- 模型最多16次研究回合，研究动作最多24次，隔离CPU运行最多4次；不继承旧补采或DSH授权。
- 研究角色只获得自身任务、授权stock和脱敏证据，读写scratch；不开放根仓库、旧对话、Git历史、其他方向记录。
  sealed/作者final/凭据不进入任务视图；controller/验收规则/账本/记忆不得修改。
- 新GPU能力是执行agent原样编写的有界Python脚本，允许已安装torch及授权stock、禁网络/子进程/越界文件访问。
  若脚本使用合成张量，只能报告该情景，不能冒充27B完整生成；本阶段不预设VERIFY、接受长度或kernel优化答案。
- 所有正式性能/正确性判定仍归既有controller；单卡GPU脚本输出不是配对加速比或晋升记录。

## 验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/gpu-autonomy-prep-20261109-a01
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p19_gpu_autonomy > "$OUT/tests.log" 2>&1
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py' > "$OUT/regression.log" 2>&1
git diff --exit-code facdbbc -- controller orchestrator patches costmodel assets/upstream eval ledger memory
git diff --check
```

必须实测：自身读写/CPU能力保留，角色进程及GPU脚本不能越界读取/写入无敏感canary，
规则/账本替身不可写，路径/symlink/角色冒用/重复动作/网络/子进程绕过被拒；超预算不能形成可提交请求。
只有内核探针通过后才执行研究脚本；GPU内探针也必须通过，不以本机成功代替远程验收。

GPU提交遵循northjob-submit：当前CLI帮助、本人凭据形状核对、冻结实际执行源/脚本/验收脚本及输入，
按名查重、显示完整命令/总GPU数，create一次并核对code200+UUID；不明确先查询，不盲目重提。
提交成功、进程启动、GPU/边界测试通过、研究实验完成分别记录。

代码及GPU产物须可独立审计到agent请求、原代码SHA、实际stdout/stderr/退出码、资源和Master结论。
结束后清理资源、校验归档、更新主页/交接/计划，公开审查后提交推送。实际命令和结果在运行后追加。

## 范围自检与停止条件

不建设独立上下文管理框架，不追求遮蔽已公开材料；分享成果记录来源，不冒充独立发现。
旧spawn接口不视为安全；Codex传输保留自身认证/联网，不能据此声称全部出站网络已隔离。
不新建sealed，不强制产出候选，不自动推进integration/kernel或完整RSI，不修改既有恒blocked的离线预检以伪装执行能力。
权限探针失败、预算耗尽、提交身份不明、源码不匹配或无法确认资源释放时停止并留证，不自行放宽判据。

准备证据：`logs/gpu-autonomy-prep-20261109-a01/`。当前尚无GPU任务UUID或研究结论。

## 当前实际结果：动作额度耗尽，GPU未执行

- 本机新增11测试、与既有权限测试合计28项通过；旧288项回归通过，新增严格拒绝测试后的最终回归另存regression-final.log。
- a01真实Master选方向，direction使用13工具动作/1CPU运行后触发旧Client的12次usage-update上限；没有GPU。
  原counter在异常退出前未刷新，原始错误不覆盖；后续按原生请求/执行回执补扣真实消耗。
- 修复Client可配置上限（旧探针默认仍12）、额度计数及工具文档中的源码起点，未修改agent科学脚本。
  研究回合上限16、usage-update事件上限64；两者不是精确后台API调用次数或token预算。
- a02 fresh角色重新启动基础设施尝试，不是第二轮RSI；Master自分8动作，direction自主写experiment/check/syntax并完成语法检查。
  GPU请求因方向额度耗尽拒绝。初版review入口写死stop，使Master不能用剩余阶段额度；这是接入错误，不是科学结论。
- a03保留旧回包，使用新原生thread恢复逻辑角色，明确非原thread/非新发现；Master自主继续并分配剩余3动作。
  direction将3动作用于读回两个脚本和核对stock接口，最终GPU请求仍因额度耗尽拒绝，Master按剩余额度0停止。
- 累计10研究回合、24动作、2CPU运行、30个usage-update事件、0GPU尝试；6个原生角色进程均已关闭，canary/输入未变。
- 两次独立CPU协议审计字节一致，gpu_autonomy_passed=false，GPU代码/输出绑定为null；严格模式不得通过。
  没有模型数值筛选/延迟数据、UUID、候选实现或controller晋升；假设未检验，不是被证伪。
- 原GPU总预算2小时及镜像/项目授权保持；已向用户询问追加最多4研究动作，未获授权前不启动研究或GPU。

该阶段目前未完成，不能用CPU工程验收或已写GPU代码替代真实GPU验证。

### 接续准备，不代表获准继续

恢复入口已补充原样分发本方向自己的旧脚本及SHA，避免只复制文件却不恢复研究上下文而反复消耗读回额度；
不加入其他方向答案，不改实验内容，不将恢复算新发现。未获额外动作授权前不会调用该入口。
新增回归覆盖方向额度与阶段余量的区别，以及旧12步探针默认保持、新研究入口显式设限。
公开Git只记录通用代码和脱敏状态，真实方向脚本/回包/原始输出均在忽略的logs中。
最终checkpoint新增13项测试、与既有权限测试合计30项；291项全量CPU回归通过（33.858秒），
最终CPU协议审计逐项核对原生请求、计费动作/CPU运行/usage-update事件；没有GPU证据的字段保持false/null。

### 源码身份的限制

初始两次启动保存了源码SHA和Git基准，但没有完整的逐版本源码归档；第三次恢复也未预先保存完整driver快照。
原生角色请求/响应、输入、工具代码/回执可审计，不等于完整执行源冻结与可重放已验收。
当前checkpoint源码包只标识当前工程状态，不冒充上述旧driver执行版本；正式GPU提交前仍必须冻结实际源及agent原代码。

## 未完成阶段的持久化checkpoint

- 195文件、2,985,858逻辑字节，包含准备记录、3次角色启动的请求/回包/原代码/工具回执和失败；不含GPU产物。
- 清单`logs/gpu-autonomy-evidence-20261109-a01.sha256`，
  SHA256=`cdd83282ad0d847566ad6c5c036aa04458acac85df171286b18825d6766f3c81`，全量校验通过。
- 当前8份通用源码/测试快照`logs/gpu-autonomy-prep-20261109-a01/checkpoint-source.tar`，
  SHA256=`b153b6658fbd422525dbbd5518b22e4c1c0385ae72aaf4881b0f93e7f55ae284`。
- 两次独立CPU协议审计相同；5类伪造输入/工具反馈/模型JSON/controller自报/计数器均被拒绝。
  这些不是controller正确性故障注入，也不能证明远程GPU路径通过。
- 机器状态`logs/gpu-autonomy-prep-20261109-a01/stage-checkpoint.json`：stage_completed=false、
  gpu_autonomy_passed=false、gpu_submissions=0、extra_actions_approved=false。
- 仅提交已完成本机验收的工程checkpoint与状态文档；阶段目标未达成。
  公开发布审查和最终Git身份另记`logs/gpu-autonomy-publish-20261109-a01/`，不改写以上归档。
