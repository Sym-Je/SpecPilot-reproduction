# 第 2 步：远程双卡生命周期烟测

状态：submission-rejected；用户已批准第 2 步并确认镜像，首次提交被项目权限拒绝，远程验收未运行。不是论文性能或 lossless 验收。

## 目标与固定协议

- stock/final，5 suite 各 1 请求，64 token 上限，1 次统一预热，2 轮物理 GPU 互换。
- 1 节点 × 2 H100 80GB；256Gi 内存，关闭 RDMA 和 hostNetwork，测量进程最多 3600 秒。
- 预期 10 个完整 pair / 20 条臂记录；不以短序列加速比判定通过。
- 镜像：`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
- 复用共享 `sp-sglang1520` 环境及派生引擎树；不采用镜像内未知版本的引擎。
- 主 PVC `jixinpeng-pvc` 挂用户目录；额外 `share-readonly` 的 `models` 子路径只读挂到 `/gpfs/models`。
- 执行源 commit 在提交命令的 `P2_EXPECTED_COMMIT` 固定；远程比对 exp/harness/controller，日志同时记录源 pin 与当时 HEAD。

## 验收（实现前已规定）

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s harness -p test_p2_northjob.py
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s harness -p test_p3_pair_run.py
bash -n exp/p2_remote_smoke.sh
git diff --check && git diff --exit-code -- controller
```

本地结果：9/9 新测试、15/15 编排回归通过；真实 NorthJob 模板离线检查通过，不代表已在 GPU 执行。
远程必须通过：版本与两张 H100 80GB 检查、两个 fresh server 的两轮执行、请求内容一致、实际 GPU UUID 互换、完整原始行、清理及持久存储。
机器验收：`exp.p2_northjob.validate_smoke()`；保留 `p2_acceptance.json` 且 `.exit-status` 为 0。

## 尝试 a01

- 计划名称：`specpilot-p2-smoke-20261107`；提交前查重为空，拒绝后再次查询 total=0。
- 入口：`exp/p2_northjob.py`（仅追加只读挂载后委托原 NorthJob CLI），任务运行 `exp/p2_remote_smoke.sh`。
- 输出目录：`logs/p2-remote-smoke-20261107-a01/`；旁路 `.log` / `.exit-status` 记录早期失败。
- 提交回执：`logs/p2-northjob-submit-20261107-a01.log`；生成 YAML/JSON 位于忽略的 `RUN/`。
- 执行源 pin：`d6c49578a140a755cf92e73c9ba5e59442902781`；已推送私有 origin，未修改 controller。
- 提交响应时间：2026-11-07 06:46:44 UTC；HTTP 403，业务 code=40301，`用户 jixinpeng 不属于项目 default`。
- request_id：`ReqID-20261107-144644-3217-4b66`；CLI 退出码 1，无 code=200、无 job_uuid，不认定创建成功。
- 提交后只读查重：`logs/p2-northjob-lookup-after-a01-20261107.log`，data=[]、total=0。
- 生成模板：`RUN/specpilot-p2-smoke-20261107/specpilot-p2-smoke-20261107.yaml`；无 JSON 回执。
- 远程开始时间 / 验收结果：未启动；输出目录、旁路运行日志及退出码文件均不存在。未生成配对数据，不能标记第 2 步完成。
- 原始 manifest、逐请求记录、server 日志及 SHA-256 清单：待生成，未完成归档。

### 本次提交证据 SHA-256

| 路径 | SHA-256 |
|---|---|
| `logs/p2-northjob-submit-20261107-a01.log` | `2174aa581c5ef234c0de80e0676a8f48b5ca462827ca1278849a614784e5c151` |
| `logs/p2-northjob-lookup-after-a01-20261107.log` | `c81b184c54803cd10d7730cbc129c15f5c7ef032cf2ea5291e24814634e052ad` |
| `RUN/specpilot-p2-smoke-20261107/specpilot-p2-smoke-20261107.yaml` | `39b925aba531f70ac40b899e898447ae3da487c4de21afb6b247d0806e4aba8e` |

以上证据保存在共享工作区，不将完整提交日志或模板上传 GitHub。

## 决策

暂停：需确认账号可用的 `--project` 并获得重提授权。镜像保持用户确认的 digest，不因项目权限问题更换镜像；本次没有尝试第二次 create。

模板、启动或请求失败即停，不静默换镜像、不自动重提、不提前跑第 3 步。
生命周期验收通过后更新首页；第 3 步仍需用户批准，不能把本烟测区间用作正式晋升或论文数字。
