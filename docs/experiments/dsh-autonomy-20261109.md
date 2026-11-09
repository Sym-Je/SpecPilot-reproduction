# dsh接管CPU自主实验调度：阶段计划与验收

日期：2026-11-09（北京时间）。历史计划：用户随后改为先用Codex复现，dsh迁移后置，本阶段停止继续实施。
仅完成已安装包/配置元数据及无凭据网关连通检查（直连超时、代理TLS断开），无dsh运行代码、原生续轮或真实研究验收。
以下保留原计划，不是当前待执行主线。基准为`2e069e6`，不提交GPU或恢复旧补采。

## 目标和角色

用已安装的dsh原生agent、goal-round-driver及JSONL持久化组件，验证自动续轮、恢复和受控工具。
之后仅在既有模型连接可用时，运行一个Master和一个direction的最小真实CPU实验。
研究方向/脚本/反馈后的决策由角色自行产生；主助手只提供通用桥接、预算、权限和审计。
不把自写Python循环称作dsh原生续轮，不把fixture回复称作真实研究。

## 预算和停止条件

- 本阶段GPU预算0；真实模型最多16次请求，broker最多24动作、4次CPU运行。
- CPU沿用6秒墙钟/3秒CPU/768MiB/每流64KiB，禁宿主越界读写/网络/子进程/设备。
- 不擅自换模型；优先核查现有headless配置的northgate/claude-opus-5-5。
  连接不可用就保留失败，不用Codex回包冒充dsh真实模型，不复用Codex登录凭据。
- 工程fixture允许预设回复和故障，仅验证协议与恢复。真实研究允许停止/证据不足，不强求修复或候选。
- 不修改controller，不访问sealed/作者final/受限题目或输出，不实现优化option或开启RSI。

## 验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p17_dsh_autonomy
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
git diff --exit-code 2e069e6 -- controller orchestrator patches costmodel assets/upstream ledger memory
git diff --check
```

必须由实际安装的dsh包完成：原生自动续轮≥3轮、JSONL事件重放、进程重启后恢复原会话、
恢复不重复已完成动作/扣费、未决动作不盲目重放、工具集合只含broker、
未知工具无法执行、CPU脚本越权被内核拒绝、代码与输出/退出码及预算可追踪。
mock/replay和真实模型结果分别记录；恢复过程的显式重新激活不冒称零人工策略恢复。
若模型网关仍不通，应完成不依赖它的工程验收，但全阶段标为受阻，不能宣称真实dsh自治通过。
