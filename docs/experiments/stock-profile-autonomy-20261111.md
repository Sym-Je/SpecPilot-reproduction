# 按需stock profile与自主诊断

用户批准执行本阶段，另确认新上限8 H100 GPU小时／12小时／最多并发2卡；
失败、排队与冷启动计入，旧余额不结转。沿用已确认镜像digest、WeaverDev、qiji、
既有toleration与只读模型PVC，显式higher-priority-job。日期为北京时间。
唯一阶段目录`logs/stock-profile-autonomy-20261111-a01/`，起点`826a4be`；
47个既有dirty文件先留SHA，不发布旧ceiling，不接管Ascend，不读旧私有验证正文。

## 目标与边界

让研究角色自主申请公开dev的canonical stock profile，经可信执行器采集，
得到带SHA的新evidence ID，并自主调用固定版本BBuf工具分析。未知形状允许
profiler-only；没有可靠依据时compute/pipeline明确不可用，不猜填VERIFY工作量。
profile开销下的耗时不作正常服务性能、配对收益或晋升数据；不以前置完整ceiling为目标。

## 先行验收与流程

1. 核对既有采集/沙箱/技能接口；登记新预算、版本、动作schema与验收。
2. 可信collector仅接受固定公开workload ID、固定preset和有界理由，不接受路径、
   任意提示、shell、环境变量、overlay、server flags或sealed；执行受信stock。
3. 固定采集record_shapes/stack/annotations、有限窗口和产物上限，保留真实API请求、
   原始trace、生成包、GPU/模型/引擎/源码身份和退出清理；缺失证据不写成功。
4. profile-only工具独立分析；缓存绑定输入与工具版本，未知不等于零成本。
5. CPU fixture先红后绿，验证越权/替换/超限/不完整trace拒绝；小型真实GPU验证
   之后才开放给新的受限Master与研究角色，不复活旧sealed轮。
6. 新Master自主决定诊断方向，角色自主申请证据、分析、迭代并决定继续/停止；
   维护者不代写科学优化。已有source/controller通路按需复用，未运行的阶段不算完成。
7. 独立核角色/任务终态、预算、证据与未知项；更新主页/交接，公开审查后提交推送。

预登记命令（模块随实现增加）：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_profile_capture harness.test_profile_resource \
  harness.test_profile_autonomy harness.test_skill_diagnostics harness.test_skill_rsi -v
```

真实验收区分：提交code200/UUID、进程启动、有效CUDA trace、原包重算、
角色自主使用分别记录。即使record_shapes=true，CUDA graph也可能缺少完整形状或
kernel归因，必须如实保留限制，不把eager诊断当图模式性能证据。

## 当前执行证据

147项指定CPU回归通过，含profile-only/形状事实/资源计费与受限入口检查。
shape事实有trace SHA和event索引，最多16签名，不认证VERIFY、层或kernel工作量。
目前仅支持graph-128，eager请求明确拒绝，不能声称已适配全部profiling方式。

preflight01仅准备，未提交。preflight02查重后只create一次、code200，
UUID`job-a670da353948-20261111094539`，实际higher-priority-job，
最终Aborted/exit1、33 GPU秒。root bootstrap、单H100、SGLang0.5.20检查通过；
失败在误要求draft也有分片checkpoint index，尚未启动server或产生CUDA trace。
失败同时暴露host对未发布root输出stat的PermissionError；资源终态/计费已落盘，
补登记失败反馈并保留原日志，未重写旧提交。两个权限/失败fixture先红后绿，
40项资源相关回归通过。修复仅涉及采集布局与公开dev错误证据发布，不改sealed规则。

preflight03已Completed/exit0，UUID`job-7d68849bfda0-20261111095858`，613 GPU秒，
单H100实际higher-priority-job；两任务合计646秒。模型布局现兼容分片/单文件safetensors，
权重全SHA/size由可信collector流式记录、不复制巨文件；host只核controller回执，
metadata和trace由host重算，不假称host能访问原模型。
首次host复核发现dev Python缺transformers；使用已装sp-sglang1520的固定CPU adapter、
禁CUDA可见性、核全冻结源码后重新tokenize/audit，通过；没有因此提交新GPU。

真实trace含90047个CUDA kernel，GPU kernel work约2321.66ms、busy union约1966.00ms、
span约2173.49ms；均是profiler窗口，不是正常请求时延/吞吐或优化收益。
BBuf extract/profiler核对通过，36957个CPU事件确有Input Dims；with_stack=true仍没有
可确认stack，故stack状态unknown。维度事实不自动认证VERIFY/层/kernel关联，
workload保持null、compute/pipeline不可用；补分页使角色能自主查询前16项之后的形状。
最新187项指定CPU联合回归通过，不代表全仓库/其他平台全绿。

## 收口验收（执行前登记）

待研究角色自主结束后，独立执行两次：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
STAGE=logs/stock-profile-autonomy-20261111-a01
$PY -B -m harness.profile_autonomy_audit --root "$STAGE" > "$STAGE/closeout-audit-01.json"
$PY -B -m harness.profile_autonomy_audit --root "$STAGE" > "$STAGE/closeout-audit-02.json"
cmp "$STAGE/closeout-audit-01.json" "$STAGE/closeout-audit-02.json"
$PY -B -m unittest harness.test_engine_research harness.test_p18_research_boundary \
  harness.test_profile_autonomy harness.test_profile_autonomy_audit harness.test_profile_capture \
  harness.test_profile_only harness.test_profile_resource harness.test_skill_diagnostics \
  harness.test_skill_rsi harness.test_skill_rsi_audit harness.test_skill_rsi_pipeline \
  harness.test_source_boundary
```

审计须重算实际trace和研究诊断，核对原生角色谱系、同角色证据注册、完整执行命令、
失败与成功任务的终态/计费、进程出生与退出；不以角色自报或相互一致的缓存替代原始证据。
封存仅包含本阶段host可见的授权产物，并明确记录不可读项；两次全SHA复核后才更新主页和发布。
公开只提交本阶段源码、测试和脱敏摘要，旧ceiling改动原样保留、不混入提交。

## 独立工程复核与修复

复核发现五项工程缺口：缓存kernel统计未重算、完整argv绑定不足、初始evidence未在启动前
绑定选定preflight、prepare失败可能留下孤立动作计数、CPU fallback重算覆写原unit元数据。
新增13项故障回归先红后绿，修复后190项定向检查通过；不改controller或科学门槛。
运行中的campaign未重启、未热加载修复；实际加载源保留在`host-loaded-source/`，
后续独立收口审计使用修复后的验证器重算既有原始证据。源包和各任务的版本身份分别记录。

运行中231项联合回归曾有一项既有source-boundary测试失败：同UID的原生角色线程超过
该CPU探针512进程限额，探针后续fork返回EAGAIN；不放宽限制，待角色全部退出后原命令复验。
失败日志保留在`skill-tests/continuation-joint-regression.log`。

## 最终结果

本轮六科学角色自主完成：Master、三方向、Integration、Kernel。共15个原生回合、
80个工具动作、4次Python执行、5次BBuf调用；另有2次源码诊断和2次自主profile请求，
阶段动作总数84。Master最终选择stop，不为耗完预算而重跑。

| 角色 | 自主动作与证据 | 结论 |
|---|---|---|
| d1 | 自主申请profile-01，拿到同角色evidence ID后调用BBuf及读取stock源码 | 无可靠调用栈/源码关联，未猜测形状或提交候选 |
| d2 | 自写BV64分块option与CPU自检，双卡/10题/2048上限/两轮fresh换卡 | candidate/stock=0.891258，95% CI [0.888961,0.893725]，停止 |
| d3 | 自写CPU长度上界复用option与CPU自检，同一双卡协议 | 0.998749，95% CI [0.997223,1.000138]，无可信收益，停止 |
| Integration | 自主检查Master共享证据；shared_candidates为空 | 无科学组合实验，不把空跑算整合完成 |
| Kernel | 自主申请profile-02并调用BBuf、核对完整stock源码 | 图内真实路径/形状仍未认证，未实现或运行优化候选 |

这里的d2/d3是研究角色自写候选，**不是作者final**。区间来自controller统计代码，
但仍只是公开dev诊断；未做本轮独立联合dev gate、GPU数值/lossless、sealed或晋升验收。
五次BBuf调用来自Master、d1和Kernel；其他角色获得接口但未调用，不声称每阶段均有实际工具实验。
profile工作占比不是请求关键路径或可实现收益，未知workload不自动转换为compute/pipeline估计。

| 任务 | UUID | 终态 | 保守GPU秒 |
|---|---|---|---:|
| preflight02 | job-a670da353948-20261111094539 | Aborted | 33 |
| preflight03 | job-7d68849bfda0-20261111095858 | Completed | 613 |
| profile-01（d1） | job-8d586882e3ca-20261111103308 | Completed | 550 |
| direction-d2-01 | job-03e2283aa627-20261111104657 | Completed | 2798 |
| direction-d3-02 | job-d9e63ceec786-20261111111512 | Completed | 2708 |
| profile-02（Kernel） | job-68c19483712e-20261111114109 | Completed | 564 |

提交code200/唯一UUID、进程启动、实际任务终态分别核对；实际priority均为higher-priority-job。
累计7266 GPU秒=2.018333 H100 GPU小时、峰值2卡，未超8小时/12小时/2卡上限。
最终NorthJob新查询六任务均终态；原生角色/受信辅助进程12个均退出，无在途GPU或继续搜索。

首次完整审计保留在`closeout-audit-01.stderr`：d3的一次原生JSON结尾多出一个右括号，
执行器正确拒绝并让同角色自行修复，但旧审计误要求该拒绝回合也有成功response侧车。
新增6项回归：只允许实际解析失败、没有伪造成功侧车、下一原生回合精确包含原错误反馈、
重试次数有界；有效JSON缺失侧车、末轮坏JSON仍拒绝。旧通用审计默认不开放此模式。
未补造或改写任何原始模型答复；格式失败仍计入15回合与预算。

最终`closeout-audit-03.json`和`04.json`两次独立重算字节一致，包含原始trace统计、
GPU诊断、完整命令/源包/角色来源、CPU回执、同角色evidence及进程退出复核。
最终250项指定CPU联合回归通过；只用HEAD加本阶段18个源码/测试文件的干净副本也通过250项。
原231项运行中fork失败不抹除，退出后既有限制原样复验通过。

原始证据索引为`logs/stock-profile-evidence-20261111-a01.sha256`；机器收口状态在
`logs/stock-profile-closeout-20261111-a01/stage-result.json`，发布与远端身份单列于
`logs/stock-profile-publication-20261111-a01/`。仅host可读的授权产物参与归档，失败预检的
root-only输出目录单独列不可读项；没有扩大权限或声称核验了不可读内容。
6714个文件/268003711字节已两次全SHA复核通过；另跳过两份源码格式配置符号链接。
索引SHA256为`eb51db55c14d154500897e2b03413d31f0523edaf182dd7d058c69fbe40cc977`。

**完成的是按需观测、受限工具和自主研究反馈链，不是正向优化或完整RSI。**
下一步先审核最小运行时归因能力与新研究方案，不恢复旧私有验证、不自动补ceiling或提交GPU。
