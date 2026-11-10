# 历史科学 snapshot 与 controller-only 追加审计

先行工程验收，不提交 GPU，不读取 sealed/private 正文，不改旧证据：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_skill_rsi_audit -v \
  > logs/skills-rsi-20261110-b01/controller-tests/prefix-audit-tests-first.log 2>&1
$PY -B -m unittest harness.test_skill_rsi_audit harness.test_skill_rsi_pipeline \
  harness.test_skill_rsi_continue harness.test_research_paging harness.test_skill_rsi -v \
  > logs/skills-rsi-20261110-b01/controller-tests/prefix-audit-regression.log 2>&1
$PY -B -m harness.skill_rsi_audit \
  --directory /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01 \
  > logs/skills-rsi-20261110-b01/controller-tests/prefix-audit-real-01.json
```

判据：pipeline.resource_state 的 jobs 是 live 的完全相同、有序前缀；非 jobs
字段（包括 started/授权上限）完全不变，所有名称/UUID 唯一。只对原 prefix
重算科学角色、原 counters、反馈及正确性；不把追加工程任务算作科学动作。

尾部仅允许同预算的 phase4-controller、maintenance_stock_control=true、
controller-negative-control。单独核对 request/plan/submitted code200/UUID、
查重查询、真实终态与容器退出、保守计费、源码归档 inventory/逐文件 SHA、
bundle manifest 的 canonical stock 身份。完成任务仅重算公开 aggregate／
controller-only replay 引用，不读 private 正文；失败保留 failed，不能 through。
拒绝历史变更、截断、重复、未知/科学尾部、active/不确定提交、费用/归档替换。

报告科学 prefix sealed_used=false 与 controller extension 分开；总费用、
终态数及并发峰值按完整 live 计算，不忽略尾部。失败 extension 的 sealed
访问情况不凭失败状态猜测。审计期间 live 变化则拒绝，不写假定稳定快照。
保留 real-audit-01.json 原 SHA、pipeline 原包及唯一预算，另写新审计产物。

controller.phase4_final 的 legacy observer 另有 live==snapshot 检查和 audit
源码 SHA 绑定；主助手须同步采用 prefix 审计结果并重新 observe，不改旧证明。
