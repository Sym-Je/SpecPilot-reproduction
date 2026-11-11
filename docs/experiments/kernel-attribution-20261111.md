# 已有 stock 热点调用归因

## 目标与边界

用户批准接续上一轮收益诊断：由受限 Master/Direction 自主核对已有 trace 的热点 GEMM、
调用路径、形状和 dtype，区分优化优先级与取证优先级。维护者只补通用只读工具，不代做研究。
本阶段 GPU 授权为零；不提交任务，不读作者 final/sealed，不改裁判、验收、账本或其他轨道。
不要求完整 ceiling，不强迫找到赢家；若现有 graph trace 无法认证归属，返回具体最小补采需求。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_profile_links harness.test_master_decisions harness.test_skill_rsi
$PY -B -m exp.master_decisions --attribute-kernels --stage logs/kernel-attribution-20261111-a01
$PY -B -m harness.master_decisions_audit --root logs/kernel-attribution-20261111-a01
```

1. 保存既有 dirty 的逐文件 SHA，后续不得混入提交。
2. 先测再实现只读关联工具：仅授权 evidence ID、精确 kernel 名和有界分页；不开放任意路径。
   输出事件索引、correlation/External id 的匹配、歧义、graph replay 标记、CPU shape/type 白名单。
   不导出 Concrete Inputs、原始栈、prompt、token IDs 或指针；ID 匹配不是模块/关键路径认证。
   CUDA graph launch 的 CPU 包围算子不得被当成每个 graph node 的形状。
3. 复用 Campaign，新增归因任务模式；先运行定向回归，再启动新的受限研究，不复活旧会话。
   Master 自主选择是否派 Direction；不以必须派发/写脚本作为科学成功条件。
4. 沿用 CPU 保护：30分钟、16原生回合、240动作、32CPU额度、最多2方向；Master96动作/16CPU。
   单次方向最多64动作/8CPU，续派累计，不重置额度。不新增 GPU 额度。
5. 原生轨迹、工具重放、SHA、退出独立核对；据实际结果报告可认证项/未知项/最小补采，
   更新主页与交接，公开审查后仅提交本阶段源码、测试和非敏感摘要。

合理性：先最大化利用已有证据；缺元数据就明确停在缺口，不把耗时排名包装成可实现收益。

## 结果：离线归因推进，仍无可信优化赢家

新受限 Master 正常停止，1角色/4原生回合/20工具动作/13CPU额度/1次BBuf，约420.4秒。
没有派Direction、运行自写CPU脚本、修改引擎、提交GPU或生成晋升。13是broker计费额度，不是13次实验。
两次search_stock因把非目录作为搜索前缀被拒，Master自行改用授权源码读取；未扩大权限。
首次输出把compare/stop嵌套，第二次引用未注册的tool回执作为evidence ID，均按原协议拒绝；
Master自行重交，第三回合有效比较，第四回合接收历史负反馈后stop。拒绝与原答复保留，不改写轨迹。

### 实际取得的证据

| kernel | 历史调用数 | 累计work（us） | 本轮关联观察 |
|---|---:|---:|---|
| `nvjet_sm90_tst_384x8_64x4_4x1_v_bz_TNT` | 5658 | 700161.864 | 首批8条仅关联graph launch，未认证节点模块/形状 |
| `nvjet_sm90_tst_128x8_64x12_4x1_v_bz_splitK_TNT` | 5740 | 363979.396 | 首批8条与末页3条仅launch；末页另1条唯一ID关联`aten::mm` |
| `nvjet_sm90_tst_512x8_64x3_2x1_v_bz_TNT` | 165 | 139303.399 | 首批1条唯一ID关联`aten::mm`，另7条仅launch |

两条唯一关联的CPU算子事件分别记录BF16 `[8,25600]×[25600,5120]`、
`[1,5120]×[5120,248320]`。这些是原始trace中的单次字段观察，不是所有同名kernel的形状或设备dtype认证。
Master自主阅读stock的模型及logits路径，形成`project_target_hidden`与词表投影线索；
模块、target/draft归属、完整消费者、graph node映射和关键路径暴露时间仍缺证据。
不根据名字宣布FP8/shared-expert，不将graph launch的CPU包围形状赋给每个节点。

Master比较四维：GEMM路径、词表投影消费者保持diagnose；验证长度与送验选择defer，
因为真实进度/依赖/完整step成本不足。这里的先后是**取证优先级，不是优化收益排名**。
历史0.995636×反馈只用于原first-mismatch机制，不外推否定其他机制。
没有估出可信现实端到端收益，不将累计work当暴露份额，不把不同工作量普通计时与profile混算。

### 下一步提案（未自动执行）

由Master明确提出同工作量最小补采：

1. 普通计时与profile使用相同请求、输出预算、配置、并发和缓存条件，单独评估profile扰动。
2. 请求/prefill/draft/verify/accept/KV/结束边界与完整step成本；逐步实际提交量、逻辑/物理行数和graph bucket。
3. capture时模块/分支/算子/形状/dtype/消费者与replay node的稳定映射；保留stream和依赖。
4. 仍只有launch就停止模块归因；暴露时间/新增成本未明就保持收益unknown；不先实现logits融合。

本阶段不包含GPU补采授权。若继续，先审核最小协议，再另批预算/镜像与统一broker准入。

## 验收与交接

- 先红后绿：新增工具最初缺实现，测试失败保留；graph误归因、歧义、外部ID冲突、形状/类型过滤、
  有界分页、授权ID/SHA/任意路径拒绝和CPU额度/帮助schema均覆盖。10项工具测试通过。
  收尾审查补充非aten事件共用External id时也计入歧义，防止名称白名单造成假唯一；
  这是研究停止后的工具修复，原进程未热加载，原始十份启动源码保留，后续原trace重放另记。
- 研究版303项指定CPU联合回归通过，最终版304项，非仓库全量；最初扩大命令误写两个不存在的测试模块，失败日志保留，
  校正模块名后重跑，不将失败命令计为通过。
- 最终发布源码的隔离公开副本304项复验通过；不带入旧dirty、私有运行产物或其他轨道源码改动。
- 两次独立原生审计一致：4次kernel关联、4次shape观察和2次成功源码搜索从原来源重放；
  BBuf原始结果/身份、原生回包、额度与2个实际进程exit0核对通过。审计不自动认证研究判断。
  原版audit01/02和停止后修复版audit03/04各自一致；后者明确标识一个启动后变化的工具模块，
  原trace观察重放仍一致，不声称原进程使用了收尾实现。
- 十份启动源码SHA归档，与停止后修复版分开保存；0活动研究进程、0新增GPU。旧47份dirty中44份非共享文档保持SHA，
  三份共享文档仅追加本阶段段落，旧内容保留，提交时不混入旧ceiling修改。
- 角色自身inputs/规则/config/canary持久化，不复制auth或整个home；原生临时绝对路径不改写。
  临时目录清理后须按有来源归档显式恢复，不能伪造原回执。

公开仅本阶段工具/测试/任务模式/审计与非敏感摘要，不公开原始trace、配置、角色轨迹或计时响应。
归档校验与发布身份见私有阶段目录外的清单及publication回执；工程收尾不代表完整归因、GPU优化或论文数字复现。
