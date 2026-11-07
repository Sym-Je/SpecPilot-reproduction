# 第 2 步：远程双卡生命周期烟测

状态：startup-preflight-failed；前两次提交被拒，用户授权改为 WeaverDev 的 a03 提交成功并启动，Git 归属预检退出，GPU 烟测未运行。不是论文性能或 lossless 验收。

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

## 尝试 a03：项目修正后提交成功，启动预检失败

- 用户明确批准仅修正项目；本次只执行一次 create，无再次提交。
- 新名称 `specpilot-p2-smoke-20261107-a03`，输出前缀 `logs/p2-remote-smoke-20261107-a03`；保留 a01/a02 证据。
- CLI help、本人凭据、精确任务名查重（total=0）及源 pin 均已核对。提交时 HEAD=`c5f794bd3b1392faaf73c625c2d7c0b901c01494`，exp/harness/controller 与 pin 无差异。
- 命令与 a02 相同，仅 `--project WeaverDev`、job-name/output 的尝试后缀改为 a03。镜像、2 H100/256Gi、源 pin、只读模型挂载、双卡烟测协议、namespace/queue/toleration 均按原命令保留；未加 nodeSelector。
- 服务端响应：2026-11-07 15:54:59 +08:00，`code=200, data=None, message=success`，request_id=`ReqID-20261107-155459-3141-e54e`；CLI 退出 0。因响应未携带 UUID，按精确 user_def_name 查询，唯一匹配 **job-65f7d61d3d7f-20261107155459**，才确认提交成功。
- namespace=qiji、project=WeaverDev，project_exists/user_in_project 均为 true。**请求 queue=qiji，服务端实际 queue=proj-31**；已由任务列表和 Kubernetes Job 双重核对，不将实际队列描述为仍是 qiji。

### 生命周期分开验收

| 环节 | 实际结果 |
|---|---|
| 提交 | PASS：code=200 + 精确查重解析 UUID |
| 容器进程启动 | 已启动：Pod 记录开始时间 2026-11-07 15:55:52 +08:00 |
| 启动预检 | FAIL：持久日志报 Git dubious ownership，脚本 exit=128 |
| 最终任务状态 | Job/Pod Failed；保存快照中的容器 exit=1，结束于 15:55:54 +08:00；与脚本退出码分开记录 |
| GPU 预检 | 未到达，不能宣称通过或将此次归因于 GPU 测试失败 |
| 双卡配对烟测 | 未运行，无 runner 输出目录、manifest、pair 或 GPU 互换验收 |

共享仓库及 .git 本机 owner 为 uid=5084/gid=2888。容器中的 Git 拒绝信任该目录；没有采集到容器进程实际 uid，不能仅凭镜像默认值断言身份。旁路 `.log` 与 `.exit-status` 已持久保存。Kubernetes 还记录 RestartJob 事件，不能把集群自身的重启事件误记为 agent 再次提交；本次仅调用一次 create。后续读取到的 Pod stdout 无有效错误内容，原因证据以持久脚本日志为准。

### 最小修复的本机验证（尚未远程重提）

先用 `GIT_TEST_ASSUME_DIFFERENT_OWNER=1` 且隔离全局/系统 Git 配置，模拟同一仓库归属不匹配：git rev-parse 退出 128 并报同类错误；再仅给该子进程设置精确 safe.directory，退出 0 并解析到冻结前 HEAD。本轮无源码实现变更，也没有修改用户全局 Git 配置。

建议下一次远程命令增加进程环境前缀：

```bash
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/gpfs/users/jixinpeng/SpecDec/SpecPilot
```

该配置仅信任当前仓库并随该进程树结束，不使用 `safe.directory=*`。保留现有源 pin/镜像/测量规则。此本机模拟只验证 Git 信任机制，不证明远程后续依赖、GPU 或 server 可用，仍需新授权才能提交下一次尝试。

### a03 证据 SHA-256

| 路径 | SHA-256 |
|---|---|
| `logs/p2-northjob-submit-20261107-a03.log` | `3fc3babca0af60ee786d240bd512ce44d7c1b395419602e20ee19651f095b7b0` |
| `logs/p2-northjob-lookup-after-a03-20261107.log` | `e7f96d8e30dd055cd741830d4ceefbb0233725baa10979ad5c0b2740b4e36458` |
| `logs/p2-remote-smoke-20261107-a03.log` | `bc5f4154ffaf6d5e1e4cdd09b6b004290b5f61f0370ba7d27ed74e7e49d2f208` |
| `logs/p2-remote-smoke-20261107-a03.exit-status` | `56292515f7d3a7110811eb8de26b3f75f82a0766aa5a1fd66ebcfcb84fe6d5ff` |
| `logs/p2-northjob-lifecycle-a03-20261107.json` | `ecb1ef103c7b7c7e2177aad478895a5cd786be1bf9b47445c907aaec2d14d2fc` |
| `RUN/specpilot-p2-smoke-20261107-a03/specpilot-p2-smoke-20261107-a03.yaml` | `8abfd2ad2a355ac633148c4f2d40e37c496436bf76473319c68d8c70476f6156` |
| `logs/p2-git-trust-check-20261107.json` | `7aa1ef8300df67366942935d613dec0e7031bd76ee8dbf266b2c5b7a92843627` |

## 决策

暂停等待新重提授权：WeaverDev 已通过服务端项目校验并创建 a03，但启动预检未通过。下一次仅为进程树增加精确 safe.directory，不修改全局 Git 配置、镜像、源 pin 或测量协议；获准后再查重并展示完整命令。

模板、启动或请求失败即停，不静默换镜像、不自动重提、不提前跑第 3 步。
生命周期验收通过后更新首页；第 3 步仍需用户批准，不能把本烟测区间用作正式晋升或论文数字。
