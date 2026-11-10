# 单次 Master coverage-review 工程验收

先登记 CPU 定向验收（非 GPU／科学验收）：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_skill_rsi_continue -v \
  > logs/skills-rsi-20261110-b01/controller-tests/coverage-review-tests-first.log 2>&1
$PY -B -m unittest harness.test_skill_rsi_continue harness.test_skill_rsi_pipeline \
  harness.test_skill_rsi_audit harness.test_skill_rsi -v \
  > logs/skills-rsi-20261110-b01/controller-tests/coverage-review-regression.log 2>&1
```

判据：原 stop／证据／计数不变；同一预算、上限、started；只重放 Master
自己的决策／工具反馈及共享诊断，不读 direction 私人推理。弱收益单项允许
由 Master 自主选择独立正确性复核，不人为挑赢家。仅一个新原生 Master，
最多三轮（仅模型 JSON／协议修复可重试），32 动作／4 CPU 次且受原剩余额度
约束。没有 GPU 提交或自动 dev／Integration／Kernel。重复或不确定的启动
拒绝，不能删除 marker 重开。无剩余额度在创建原生进程前拒绝。

实际新 bootstrap／受限原生进程须有 broker 亲生子进程 birth、wait exit、
shutdown registry；初始化失败仍须收口。fixture 使用非敏感 tmp 和短 CPU
子进程，不调用模型。失败不是通过，异常落 needs_attention。

待定向测试通过后可运行：

```bash
$PY -B -m exp.skill_rsi_continue \
  --parent /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01 \
  --out /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01/coverage-review-01
```

这是新线程的显式自身上下文重放，不是旧线程 resume／热加载。
旧 host 已自然退出，原 GPU／证据不重做、不改写。
输出只可为 stopped 或 controller_review_requested；后者只是交接请求，
不代表正确性／性能／整合／kernel／sealed／RSI 已完成。

## 显式一次分页纠正（先行验收）

coverage-review-01 的回答明确未读全输入；保留其 stop 原包，但不能当成
完整 coverage 科学 stop。通用工具分页修复由主助手维护，本子任务不改
`agents/autonomy.py` 或 `harness/research_tools.py`。

```bash
$PY -B -m unittest harness.test_research_paging harness.test_skill_rsi_continue -v \
  > logs/skills-rsi-20261110-b01/controller-tests/coverage-repair-tests-first.log 2>&1
$PY -B -m unittest harness.test_research_paging harness.test_skill_rsi_continue \
  harness.test_skill_rsi_pipeline harness.test_skill_rsi_audit harness.test_skill_rsi -v \
  > logs/skills-rsi-20261110-b01/controller-tests/coverage-repair-regression.log 2>&1
```

判据：`--repair-from` 必须指向原 claim 的已退出直接子目录；验证原生
wire／response／输入／原父阶段 SHA、真实进程 birth/exit registry；所有旧
claim/result 不删除、不改。只允许一个单独 repair claim，不允许连锁 repair。
计数从 prior.counters_after 接续且独立重算先前工具收费，不增加阶段上限；
同 budget/started、零 GPU。工程修复源码与旧工具 request/response SHA 入新输入。
新 Master 先 help，按 next_offset 分页读完 evidence.json；结果从真实绑定的
tools request/response 重算 offset/next_offset/total_chars/同 SHA 片段覆盖。
缺页或未先 help 时状态为 `incomplete_context`，保留模型回答但不产生交接，
不能当成科学 stop/review，也不自动再修理。只由 Master 自主选择，不人工指定候选。
分页 fixture 覆盖 >12k、Unicode、默认首段、末尾、负数/布尔/超界 offset、
额外字段与路径逃逸；repair fixture 覆盖历史篡改、未退出、重复 repair、
累计计数及新进程闭合。只使用 tmp/CPU 子进程，不运行模型/GPU。

交付后由主助手显式运行（本子任务不启动）：

```bash
$PY -B -m exp.skill_rsi_continue \
  --parent /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01 \
  --out /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01/coverage-review-repair-01 \
  --repair-from /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01/coverage-review-01
```

真实父目录交付前只读校验（不 prepare 新目录、不写 claim、不启动模型）：

```bash
$PY -B - <<'PY' > logs/skills-rsi-20261110-b01/controller-tests/coverage-repair-prior-check-01.log 2>&1
from pathlib import Path
from exp.skill_rsi_continue import repair_context
root = Path('/gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01')
context, counters, packet = repair_context(root, root / 'coverage-review-01')
print({'prior_verified': True, 'counters_after': counters,
       'prior_tool_receipts': len(context['prior_tool_receipts'])})
PY
```
