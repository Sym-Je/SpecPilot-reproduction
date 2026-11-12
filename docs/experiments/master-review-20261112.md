# Master研究决策要求与CPU验收

## 授权与边界

用户批准落实四项要求：方向须有来源与净收益估计；否定判断主动查找反例；
失败须分类；信息不足自主提出最小取证。不修改controller/验收规则，不读sealed或作者final实现，
不接管Ascend、不启动真实模型角色或GPU任务、不结转旧资源授权。
原47份dirty按`logs/master-review-20261112-a01/preexisting-dirty.json`保留。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_review harness.test_open_research
```

先写失败测试，再实现：
1. 虚构、失败、跨角色或被修改的引用不可作为成功证据，引用绑定真实工具回执与SHA。
2. 方向比较包含条件收益/新增成本/未知项/最小实验；unknown合法，不强迫正收益。
3. 配置block_size=8本身不能认证运行16不可能；否定判断须反例取证或具体受阻原因。
4. 启动失败不能当科学假设被否定，分类允许不确定并保留替代解释。
5. 信息缺口须有最小取证建议；资源/能力不足可明确停止，不无限重试。
6. 接通新H100开放研究Master入口并测试拒绝→反馈→修订路径；旧历史回执不重写。

## 合理性自检

程序能验证引用的归属、身份、可获得性、类型与决策结构，不能证明自然语言推理必然正确。
规则不内置链长16的答案，不自动删除Direction的guard，不将CPU fixture写成真实Master能力提升、
GPU正确性或科学收益。独立controller依旧决定正确性与晋升。

## 实现与接入

`harness/master_review.py`提供版本化决策结构、原生形状的工具请求/返回匹配、引用归属与SHA绑定、
条件decode收益重算、否定判断取证、失败分类及下一步检查。不能仅填写一个虚构路径通过。
信息不足的收益可unknown；条件估计不是端到端实测，也不把额外成本默认为零。
来自scratch的自述不是权威证据；不可用工具回执只可解释取证阻塞，不能支持科学结论。

`exp/master_open.py`的新Master最终决策必须通过检查，最多3次有来源的修订；
每次接受/拒绝、实际答复、证据摘要与SHA持久化到`master-reviews/`。
Direction保持自己的研究输出协议，不代填Master表格；profile取证仍沿原有可信准入与预算，
决策检查不阻止获取信息，也不新增任何GPU授权。
`harness/master_open_audit.py`仅对声明包含新模块的运行要求复核决策记录，旧阶段原样重放，不追溯伪造新标准。

## 已完成验收

- 初始缺模块、缺离线覆盖与异常工具回执处理均保留先红后绿证据。
- 指定联合回归通过；精确最终数量、公开副本复验及旧实验重放见本阶段`closeout.json`。
- 持久合成案例经实际`OpenCampaign.model_response`入口：将配置8断言为无法运行16被拒；
  修订为未证实假设、保留最小实验并说明本阶段无GPU授权后被接受。
- 两次离线复核均为1接受/1拒绝/2答复，结果相同；删除记录、改写答复或原生形状的工具返回均可被测试检出。
- 原生形状的工具帧和模型返回由CPU fixture构造，无真实模型、网络检索或GPU运行。
  不能将此写成Master实际已主动查反例、自主修复，或已测到正确性/性能收益。

```bash
$PY -B -m harness.master_review --directory logs/master-review-20261112-a01/cpu-fixture
```

`AGENTS.md`已写入四项长期要求。旧CPU/源码接续入口和Ascend未自动接入；
尚缺新规则下的真实Master研究复验，未来须另审研究任务及资源。
程序不认证事实语义、证据是否充分、反例检索是否全面或模型是否隐瞒关键判断；
有来源的错误推理仍可能通过结构检查，必须结合独立实验与controller，而不是把表格当科学裁判。

原47份dirty保留；完成公开审查后只提交本阶段代码与脱敏摘要，持久证据在`logs/master-review-20261112-a01/`，
发布与归档身份见`publication.json`，不公开原始运行产物或凭据。
