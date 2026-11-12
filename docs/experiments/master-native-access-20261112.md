# Master原生权限入口

## 授权与范围

2026-11-12用户明确要求Master使用与主助手相同的权限，不再对controller/规则/账本写入，
或sealed/凭据/本轮禁止参考的作者final读取设置角色专用强制隔离，仅在prompt禁止，任务后检查。
这是本入口的明确例外，不自动改变Direction、Integration、Kernel或已有受限入口。

使用宿主原生`spawn_agent`、`fork_context=false`，不覆盖模型，不再经过旧的只读research代理。
继承父会话实际可用工具、沙箱与审批，不改平台权限，不自动批准提权，不使用绕过沙箱的参数。
因此“与主助手相同”不代表超出主助手权限的无限宿主写入。官方说明：
https://developers.openai.com/codex/multi-agent

原生角色实际工具清单仍由平台提供，不凭继承规则宣称每个工具都已可用；本次不验证再派子agent或GPU执行。

本次只验证工具可用性，0GPU；不恢复链长实验，不提交NorthJob，不改动Ascend。
GPU预算、镜像和外部任务提交授权仍独立，不能由权限开放推导为新增资源授权。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native
$PY -B -m harness.master_native prepare --directory logs/master-native-access-20261112-a01
$PY -B -m harness.master_native check --directory logs/master-native-access-20261112-a01
```

1. 保存原工作树身份及controller、ledger、明确列出的验收规则文件摘要；不扫描sealed或凭据。
2. 原生Master以同等权限读取授权stock、写自己的scratch、执行CPU脚本并尝试公开网络访问。
3. 不故意读真正禁区或写真正controller来“证明权限”；工具能力由实际正常操作验证。
4. 完成后对比保护文件，保存agent身份、答复、退出与测试回执。文件新增、删除、改写均报告。
5. 读取行为只能结合可取得的工具轨迹人工复核；哈希不变不证明从未读取。

## 研究模式

后续Master可自主读stock、调研文献、使用BBuf、写分析/候选代码、设计profile与安排研究。
研究任务另行写清范围及资源；不能把本次工具探针称作有价值方案、真实profile或RSI已完成。
仅有prompt约束时，科学隔离与独立发现的证明力度低于原强制隔离方案，必须如实披露。

## 本次结果

- 实际原生Master已读取授权stock、用apply_patch写CPU脚本并执行，固定算术校验338350。
- 首次系统Python urllib返回308；角色自主记录Location并跟随公开OpenAI文档重定向取得200，保留首次失败及修复过程。
- 原生环境显示workspace-write、auto_review，与父会话同一权限配置；不另加角色research-only过滤，不代表root或无限资源。
- 4项postcheck正反例及469项指定联合回归通过；仅本入口文件发布副本另行复验，结果见阶段回执。
- 事后controller、ledger及列明规则文件摘要无变化；不能凭此宣称未读取禁区，也未对未覆盖的权限或读取路径提供证明。
- 本次0GPU、0优化研究，不恢复已停止链长轮；旧研究失败/恢复及未收尾状态仍保留。
- 新Master入口仅由宿主原生子agent启动；旧exp.master_open/chain_review入口未被静默改造成原生模式。

私有证据目录为`logs/master-native-access-20261112-a01/`，包括实际agent身份、prompt、probe、前后摘要、回归与公开同步回执。
不公开原始角色上下文或运行产物，不读取凭据/未公开验证数据来做归档。
