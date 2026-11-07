# 第 2 步：远程双卡生命周期烟测

状态：submission-rejected；用户已批准第 2 步并确认镜像，两次提交分别被默认项目权限及指定项目不存在拒绝，远程验收未运行。不是论文性能或 lossless 验收。

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

## 尝试 a02（用户明确授权重提一次）

- 名称：`specpilot-p2-smoke-20261107-a02`；新建尝试名和输出路径以保留 a01 证据，不覆盖旧模板。
- 提交前已核对 NorthJob 3.3.11 的 create help 支持全部指定参数；本人 userinfo.conf 的 username/password 非空，不输出凭据值。
- 项目：`infra-dev-weaver`；namespace/queue：`qiji`；toleration：`key=task-type,operator=Equal,value=infra-dev-weaver,effect=NoSchedule`。三者职责不同，未新增 nodeSelector，不声称只能调度到指定池。
- 资源及协议不变：普通 bash，1 节点 × 2 H100 = 2 GPU，256Gi；stock/final、5 请求、64 cap、两轮物理换卡。镜像 digest、只读模型挂载及源 pin `d6c49578a140a755cf92e73c9ba5e59442902781` 不变。
- 提交时仓库 HEAD：`67b9e4b95eac71885b4c667f7c53dd0038f9630b`；已确认 exp/harness/controller 与源 pin 无差异。
- 提交前查重 total=0，完整回执及退出码保存在 `logs/p2-northjob-submit-20261107-a02.log` / `.exit-status`；只执行一次 create。
- 服务端响应时间：2026-11-07 15:23:13 +08:00；HTTP 400 / code 40005，`项目 infra-dev-weaver 不存在`；request_id=`ReqID-20261107-152313-2282-3396`；CLI 退出码 1。
- 提交后查重：`logs/p2-northjob-lookup-after-a02-20261107.log`，data=[]、total=0；无 code=200、无 job_uuid，不能认定提交成功。
- 生成模板离线核对：project annotation、namespace、queue、toleration 均与用户指定一致；镜像及 2 GPU/256Gi 无变化。不是远程验收通过。
- 生命周期分别记录：**提交被拒绝；远程进程未启动；GPU 烟测未运行**。运行输出目录 `logs/p2-remote-smoke-20261107-a02/`、旁路 `.log` 和 `.exit-status` 均未生成。

### 最终执行命令

```bash
/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python -B exp/p2_northjob.py create \
  --job-name specpilot-p2-smoke-20261107-a02 \
  --project infra-dev-weaver \
  --workspace /gpfs/users/jixinpeng/SpecDec/SpecPilot \
  --nnodes 1 --nproc-per-node 1 --gpu-per-node 2 --gpu-resource h100 \
  --mem-per-pod 256 --no-rdma --k8s-no-hostnetwork \
  --k8s-namespace qiji --k8s-queue qiji \
  --k8s-toleration key=task-type,operator=Equal,value=infra-dev-weaver,effect=NoSchedule \
  --k8s-pvc-name jixinpeng-pvc --k8s-pvc-mount-path /gpfs/users/jixinpeng \
  --k8s-images harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798 \
  'P2_EXPECTED_COMMIT=d6c49578a140a755cf92e73c9ba5e59442902781 bash /gpfs/users/jixinpeng/SpecDec/SpecPilot/exp/p2_remote_smoke.sh /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/p2-remote-smoke-20261107-a02'
```

### a02 证据 SHA-256

| 路径 | SHA-256 |
|---|---|
| `logs/p2-northjob-submit-20261107-a02.log` | `7596f140b43da9af27ba2371222a1e8381176b648808518321465c109632ad47` |
| `logs/p2-northjob-lookup-after-a02-20261107.log` | `c81b184c54803cd10d7730cbc129c15f5c7ef032cf2ea5291e24814634e052ad` |
| `RUN/specpilot-p2-smoke-20261107-a02/specpilot-p2-smoke-20261107-a02.yaml` | `c02854034de8b4e26b15c76bcaccbdfe15afd6b04555b3c5750009e3aee723b5` |

## 只读诊断：项目登记与旧任务注解不同

用户要求排查原因，本轮未执行 create/update/delete，也未修改 CLI 或凭据。

- CLI 3.3.11 直接将 `--project` 同时传入 YAML 注解及提交 HTTP JSON；未发现适配入口把项目重写成其他值。
- 使用本人 `~/.config/northjob/userinfo.conf`，账号 jixinpeng；当前后端 `10.1.2.7:31000`，无 `K8S_SERVER_HOST` 覆盖。认证和任务列表查询均成功，不能把本次错误归因于密码缺失。
- `northjob get --creator jixinpeng --group qiji --page-size 30` 的响应已落盘。该查询也返回了其他 creator 的记录，因此诊断只采用下表两条 `job_creator=jixinpeng` 的记录，不能仅凭查询过滤器认定归属。

| 本人任务 UUID | project | project_exists | user_in_project | 状态 |
|---|---|---|---|---|
| `job-069b464a3083-20261107001603` | infra-dev-weaver | false | false | Completed |
| `job-d512d77f776a-20261106113534` | WeaverDev | true | true | Running |

这两条任务均通过 Kubernetes 只读 GET 交叉核对：project 注解与 API 一致，namespace/queue 均为 qiji，creator 均为 jixinpeng。旧 infra-dev-weaver 任务确实保留了同名项目注解及 `task-type=infra-dev-weaver:NoSchedule` toleration，但服务端不把这个注解值识别为当前有效注册项目。无法据此确定它原来经过哪条创建路径，或项目登记是否后来改变。

结论：a02 在服务端项目登记校验处被拒绝，尚未进入镜像、进程或 GPU 测试阶段。当前有证据支持的项目名为 **WeaverDev**，而 **infra-dev-weaver 仍保留为用户指定的 toleration 值**；项目名称、namespace/queue 和节点准入条件必须分开设置。

建议下一次只改 `--project WeaverDev`，其余镜像、资源、请求协议、qiji namespace/queue 和 toleration 不变；须获得新的重提授权。此诊断不证明新提交一定成功，不证明 GPU 项目配额、节点调度或引擎兼容性通过。

### 诊断证据 SHA-256

| 路径 | SHA-256 |
|---|---|
| `logs/p2-project-diagnosis-20261107.json` | `cd8e138883ab6985833fb1f46ecb901b8797ee93e22a6fcdca63df836567e466` |
| `logs/p2-project-diagnosis-myjobs-20261107.log` | `e014a565c7eebc7a1b4b548dd9873b7905f4720d64271d50584d095971c55dec` |
| `logs/p2-project-diagnosis-k8s-20261107.json` | `4cf06fc65e70358080a6f1b568ec819d8c16a8fb540b6d33e2c2cd78777e4bf5` |

## 决策

暂停等待新重提授权：只读证据已定位 WeaverDev 为有效项目，尚未提交验证；不更换镜像或调度约束。此前授权仅执行一次 a02 create，诊断阶段没有继续重试。

模板、启动或请求失败即停，不静默换镜像、不自动重提、不提前跑第 3 步。
生命周期验收通过后更新首页；第 3 步仍需用户批准，不能把本烟测区间用作正式晋升或论文数字。
