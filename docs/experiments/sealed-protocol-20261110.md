# Phase 4 冻结与证据协议（维护者工程接口）

## 独立 finalizer 与追加审查：实现前验收

用户授权新增 `controller/phase4_final.py`、`harness/test_phase4_final.py`。runtime保守false
不变；独立进程在真实dev重算、冻结候选、角色出生退出、当前sealed重算、受信GPU终态、
封存SHA全部满足后才可T3 true，promotion/ledger仍false。不用占位缺项永久阻塞。

```bash
$PY -B -m unittest harness.test_phase4_final -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/finalizer.log
```

仅CPU fixture验收：缺项/身份不符/源漂移、dev仅自报passed、角色仍活跃或退出晚于揭盲、
终态失败/重启/错误image/错误Job优先级、封存不完整或篡改均拒绝。合成可信回执正例不
冒充真实GPU；科学validator仍调用原controller，不改阈值。优先级只核对Job.spec字段，
Pod无同名字段正常。动态source_cache和source_candidate传递依赖纳入冻结/归档，
head reference文件绑定当前Phase4输入。准备元数据时不要求研究已停，执行前检查停机。

## 用户澄清：科学要求与工程边界（本节覆盖旧网络强制表述）

完整 network namespace/privileged pod **不是论文 T3 要求，也不是本轮前置条件**。
默认保留推理所需网络/IPC，不宣称网络隔离；`private_network` 仅可显式启用为工程增强。
必要边界仍是 controller 与研究角色独立 UID、0700 私有证据，候选推理的60010/60011
UID+Landlock+seccomp不能读controller目录。正式执行前可信broker须关闭所有研究角色，
只向角色/外部返回聚合，原始请求、逐请求输出和私有证据不可回流。当前代码不冒充已经
验证了 broker 完整角色清单或封存，主助手须独立核对实际停机/执行/终态/封存证据。

论文/本任务 T3 必保留：冻结候选与未见请求、两轮 fresh server 和物理换卡配对、常规
2048及4096上限 forcing、原 controller 正确性与配对性能判据。源码/原包绑定、0700/UID
和角色停机是必要工程边界；全网络隔离、privileged pod、挂载namespace不是新增科学门槛。
FP32 preflight/健康/故障/归约回归及既有1024尾部覆盖是现有裁判工程验收，不冒充论文
另列的数值硬门槛。缺真实运行仍保守 `t3_passed=False`，不因默认关闭网络增强而改true。

变更先行验收：保留旧测试，新增默认 guard 在 unshare 明确不可用时仍不调用它的 CPU
fixture；显式 `--isolate-network` 才使用该增强，增强失败不得静默声称隔离成功；不增加
任何 read/device/executable 授权。执行既有 runtime/sealed 及 controller CPU 命令，新增
日志为 `runtime-boundary.log`、`runtime-boundary-existing.log`，不运行 GPU、不读真实 sealed。

## 先行验收（实现前登记）

本次仅新增本文、`controller/sealed_protocol.py`、`harness/test_sealed_protocol.py`。
不修改既有裁判/规则/数据，不读实际 sealed、作者 final 或 Ascend，不提交、不跑 GPU。
执行日志为 `logs/skills-rsi-20261110-b01/sealed-tests/`；测试数据仅为非敏感 tmp fixture。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
mkdir -p logs/skills-rsi-20261110-b01/sealed-tests
set -o pipefail
$PY -B -m unittest harness.test_sealed_protocol -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/protocol.log
$PY -B -m unittest harness.test_p5_paper_policy harness.test_p5_scored_forcing \
  harness.test_p6_dev_campaign -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/existing.log
```

可执行判据：健康 fixture 通过协议/原生评分重算；候选/输入漂移、dev 提示词
重命名、空/重复请求、宽权限或研究目录重叠、冻结校验和替换、缺轮、未换卡、任一臂
复用进程、非并发配对、缺 warmup/telemetry、原始包或测速输出替换、缺 cap/forcing、
不完整分数/错误 head、后 2048 大 margin 故障均被拒；高噪声和收益不足不能晋升。
健康 fixture 也不得产生 T3、ledger 或 promotion。

## 接口选择与边界

已检查 `controller/dev_campaign.py`、`controller/scored_forcing.py`、
`controller/paper_policy.py` 及 `harness/baseline_validation.py`。旧 dev campaign
是 `dev-joint-v1`、固定每 suite 6 条和 2048 cap；底层 paired-run 同样硬编码
2048，不能复用其 passed 字段或重命名成 sealed。

新接口仅供可信 controller 调用，冻结摘要须由调用者在研究进程不可写的位置保管。
私有目录及请求输入均须 owner-only、owned by controller；请求输入不得位于任何
研究可见目录，研究已见提示词 hash 集在候选冻结时固定。重名 ID 不决定 unseen，
提示词 hash 相交即拒。该检查不能凭空证明研究历史完整，亦不能隔离同 UID 进程；
真实运行须由可信 broker 落实独立 UID、私有证据和角色停机，不能把 Python API 当安全
沙箱；不强制完整网络或挂载 namespace。

冻结候选后才载入请求；冻结绑定候选/stock tree、源码及部署文件 SHA、launch 参数、
已见输入 hash、研究可见目录。未见请求仅存 controller 私有状态，不返回给研究角色。
常规 2048 和长输出 4096 各自要求 null-pre → candidate → null-post，均两轮物理
换卡/fresh server；完整短/全量 warmup、原生 HTTP、时序、GPU/进程 telemetry。
自然 EOS 保留，不要求所有请求生成满 cap；4096 不能以 2048 结果或截断替代。

正确性从原始 FP32 scorer 包重算，逐轮逐 cap 绑定原测速输出；AR 首次偏离标定 δ、
stock mismatch、rate/event 判据调用原 controller。噪声由每 cap 两个预登记 null
原始配对重算，物理轮次按 request cluster 聚合，沿用原 controller 双侧 95% CI、
最大端点离 1 的 noise 与 `candidate_verdict`，不新增/放宽科学阈值。

本模块不是 GPU runner，不加载实际 sealed 路径，不写 ledger/记忆。协议证据通过
不等于真实 T3；返回值始终 `t3_passed=False`、`promoted=False`、
`ledger_eligible=False`。主助手仍须接可信 Phase4 runtime、独立进程隔离、真实
FP32 head preflight/健康与故障及归约回归、候选 dev/T0 先决证据、可信测量身份与终态
归档，并由独立 controller 决定 final。不会信任上传的 `passed` 布尔值。

## 精确 API 与 runtime 接线

仅以下三个函数为公开入口（无 CLI、无自动执行、无 ledger 写入）：

```python
freeze_candidate(private_root, *, artifacts, arms, launch_protocol, gpus,
                 seen_input_hashes, research_roots) -> reference
open_phase4(freeze, request_path) -> reference
validate_phase4(opened, evidence) -> dict
```

`reference` 统一为 `{"path": absolute_path, "sha256": raw_file_sha256}`，不是路径字符串。
controller 必须保存返回 SHA 锚点，不能接受研究角色重新上传的 freeze/opened 锚点。
freeze/opened 文件以 O_EXCL、0600 写入新建的 0700 私有目录；拒绝符号链接、
宽权限、owner 不匹配以及与 research roots 的祖先/后代重叠，不替用户修改旧目录权限。
同 UID 的研究进程及 root 仍可绕过这些权限，因此研究模型不得使用 controller UID 或
读取其私有目录；不由此要求完整网络/挂载 namespace。

- `artifacts`：非空名称→文件路径映射，调用者应列全候选/stock 源码快照、模型/镜像
  身份、option/deployment 配置等实际执行依赖；每次 open/validate 重读 SHA。
  此 API 不自行遍历引擎或证明声明的 tree SHA 就是已加载代码，后者属可信 runtime。
- `arms`：严格顺序 stock/candidate，字段 `name, tree_sha, block, env`；stock block=8、
  env 为空，沿用当前 stock 校准契约；candidate 单独固定，不继承其他候选通过状态。
- `launch_protocol`：至少含 `model_path`，应完整冻结实际服务参数；逐臂 server-info 原包
  必须满足这些键及 DFLASH/block。`gpus` 为两个不同卡的 `{index, uuid, name}`。
- `seen_input_hashes`：完整研究已见提示词 SHA 清单；清单完整性是 controller 的责任。
  `research_roots` 必须明确列出全部研究可见目录。不得用改 ID/suite 或 dev 路径名规避。
- `request_path`：0700 父目录下的 0600 私有 JSON 请求列表，元素为
  `{id, suite, turn: 0, input_ids, input_sha256}`；非空、ID/输入均不重复且 hash 未见。
  open 在 freeze 之后执行，仅允许成功创建一次 phase4 状态，绑定原文件 SHA/请求顺序。
  输入原文件后续必须保留，validate 会再核对；open 的返回引用本身不含请求正文。

### evidence 文件结构

所有证据引用及其递归原生 HTTP/score 引用必须位于私有 controller root 内：

```text
protocol: controller-phase4-v1
phase4_sha256: opened.sha256
sessions: 按 cap=2048,4096，各自 null-pre,candidate,null-post 的顺序
  - {cap, phase, source: reference(session)}
forcing: 按 (2048,1),(2048,2),(4096,1),(4096,2) 的顺序
  - {cap, round, stock: [reference(trace)], candidate: [reference(trace)],
     ar: [reference(trace)], prefill_audits: [reference(trace)]}

session: {protocol, cap, phase, rounds: [reference(round1), reference(round2)]}
round:
  protocol, cap, round, complete: {pairs: request_count, exit_code: 0}
  started_unix < ready_unix < warmup_complete_unix < finished_unix
  assignments: 两项 {arm, gpu, port, process: {host_boot_id, pid, start_ticks}}
  warmup: requests[:2] 的 short，然后全部 requests 的 full
    - {phase: short|full, a: sample, b: sample}
  pairs: 全请求原顺序 [{id, a: sample, b: sample}]
  telemetry: 至少两个处于测量区间内的快照
    - {time_unix, gpus: [{uuid, clocks_sm_mhz, clocks_mem_mhz, temperature_c, power_w}],
       arms: {arm_name: process}}
```

同 cap null 使用冻结 stock 的克隆，arm 名为 stock-a/stock-b；不使用 candidate 的
tree/block/env。所有 cap/phase 的 GPU 身份固定，各 session 第二轮反转物理卡。
所有臂的 `(host_boot_id,pid,start_ticks)` 全活动不复用；轮/phase 不重叠。
warmup short cap=32、full cap=当前 cap，pair 两臂时间必须重叠，不能串行冒充。

`sample` 沿用 `dev_campaign.validate_packet` 所需的真实 HTTP 样本：
`id,suite,turn,round,arm,tree_sha,block,gpu_uuid,input_sha256,output_ids,output_sha256,
completion_tokens,max_new_tokens,latency_s,tokens_per_s,finish_reason,raw_evidence,
generator,client_timing`。`generator` 为既有 NativeClient server identity；其原包需
`started_unix`，必须来自当前 fresh server 生命周期。`client_timing` 为原 transport 的
`step_start_ns,http_open_start_ns,body_complete_ns,step_end_ns,url,started_unix`，另需
可信 wrapper 捕获 `finished_unix`，并与实测 latency 一致；现有 Arm 不直接提供此字段，
因此不能把旧 dev 文件不经真实执行接入就当新协议。所有速率、输出长度/哈希、采样 cap、
原始生成包、配置及端点均重算核对。自然 EOS 可以小于 cap，score 必须覆盖实际完整输出。

trace 使用原 `scored_forcing.load_score_trace` 格式，不另建分数/阈值定义。
stock/candidate 每轮都须对应原 timed row 的同一个 generator 和原始 generation segment；
AR 必须冻结 stock tree/非 speculative，scorer 为 stock tree/非 speculative/FP32 head。
所有 score 原包时间须晚于本活动全部测速完成，避免干扰；δ 无观测偏离时明确拒绝校准，
不填论文常量。不消费上传的 correctness/performance/passed 布尔结果。

### 输出与未接能力

完整结构不合格抛 `ValueError`，缺文件可抛原 IO/JSON/schema 错误；均为 fail closed。
科学判据不通过则返回 `protocol_evidence_passed=False` 和逐 cap 原 controller verdict：
`caps[].correctness`、`caps[].noise_calibration`、`caps[].performance`。
每 cap correctness 含两轮原分数事件/rate/δ/证据 SHA；noise 来自全部预登记 null，
不是接受调用方提供的一个噪声数字。即便通过也始终返回 `t3_passed=False`、
`promoted=False`、`ledger_eligible=False` 和 `missing_runtime`。

主助手后续应接：受信新 runner（不是复制 dev 数据）、独立 UID/0700/研究角色停机与完整研究访问
历史、加载源码/镜像/模型/硬件和 fresh server 进程的独立来源证明、真实 head preflight/
健康/故障/归约回归、T0/dev 先决验收及任务清理/终态/归档；最后由独立 controller final
入口消费这些证据。此模块未实现以上 runtime，更未执行实际 T3 或复现论文 sealed 数字。

## CPU 实测记录

先行命令已执行；仅非敏感 tmp fixture 和既有本地 HTTP fixture，不使用 GPU。
首次暴露旧 dev 时序 helper 固定三阶段的问题，已改为新协议长度无关时序校验，不修改旧
helper；扩展测试又发现测试重存 opened fixture 权限过宽，已修正 fixture 为 0600，
不降低生产权限规则。失败日志保留为 protocol.log/protocol-r03.log；protocol-r02.log
为基础 10 项通过。

- `protocol-r04.log`：13/13 通过（14.084 秒，exit 0）；含健康 fixture、自然 EOS、
  有效但非 timed-output 的替换 trace、完整性/隔离/时序拒绝及后 2048 故障 event-rule 拒绝。
- `existing.log`：既有 paper-policy/scored-forcing/dev-campaign 共 16/16 通过
  （6.072 秒，exit 0），未改其代码或阈值；不是全仓库回归。
- 成功 fixture 中每个 cap 的两轮 forcing 均重算；较大实测 noise 提高原阈值，收益不足
  返回不通过。空缺和篡改证据 fail closed，伪造 passed 字段不能改变判定。
- 最终文件/测试日志 SHA 与范围核对另存同一私有日志目录 `identity-final.log`。
  未运行实际 T3；无 GPU、账本/记忆写入、晋升、commit 或 push。

## Runtime 接线：先行验收（第二侧任务，实现前登记）

新增范围仅 `exp/phase4_run.py`、`harness/test_phase4_run.py`，并可更新本 controller
模块和本文；保留既有协议测试，不改其他 runner/裁判，不运行 GPU、不读真实 sealed。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
set -o pipefail
$PY -B -m unittest harness.test_phase4_run harness.test_sealed_protocol -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/runtime.log
$PY -B -m unittest harness.test_p5_paper_policy harness.test_p5_scored_forcing \
  harness.test_p6_dev_campaign -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/runtime-existing.log
```

新增 fixture 判据：私有请求只在可信 runtime guard 内打开；严格 2 cap×3 phase×2
fresh/换卡 round，全部测速结束才评分；stock/candidate trace 绑定原 timed row；缺
preflight/健康/故障/归约证据明确阻塞；错误/清理失败不产生完整 receipt；回执始终不
授权 T3。另验实际 `run_round`+本地 HTTP fixture 的 schema 转换，不以 mock passed
代替原 controller 分数重算。生产入口必须核对冻结 bundle/执行源身份，不开放角色回调。

已核对：`score_campaign` 固定旧 dev 路径/2048，不整体调用；复用其 Campaign 原始
评分/生成/audit 方法。`p5_real_run.run` 固定旧20条并涉及作者产物，禁止调用；只复用
stock-only `fresh_generations`/原 forcing 规则。head_reference 支持自定义 reference/
URL/device，但固定当前248320×5120 checkpoint，缺能力就阻塞，不改 head/science。
既有 SourceServer boundary 如实保留 `network_isolated=False`；网络/IPC是推理必要能力，
不以此阻塞 sealed。所有原包、日志与研究源码可写缓存仍须留在不可被研究角色读取的
UID/私有文件边界内，正式执行前关闭研究角色。namespace仅为可选增强，尚未实跑 GPU。

### 已实现的 runtime API（未执行 GPU）

`exp.phase4_run` 新增以下可信 controller 入口：

```python
freeze_bundle(bundle, private_root, *, gpus, seen_input_hashes, research_roots) -> reference
check_bundle(bundle, freeze) -> (private_root, frozen_manifest, stock_spec)
run(bundle, freeze, request_path, *, isolate_network=False) -> reference(runtime_result)
```

当前仅支持既有 `source-option-bundle-v1`（包含冻结 stock base、默认关闭的 source
option、实际 candidate tree）；不把启动参数 bundle、dev 目录或作者产物改名接受。
`freeze_bundle` 在不打开请求的情况下调用原 `load_bundle` 做完整 tree/编辑/hash 核对，
再冻结两个实际 arm、完整 launch 参数、所有列出的 runner/controller 依赖源码 SHA、
baseline config、target config/index。freeze 之后其中任一字节漂移就必须重冻结；
主助手仍在修改的 source 预检不能直接混入旧 freeze。外部资源/镜像、完整权重及依赖
身份仍须 broker/独立验收绑定，不能把该源码清单叫作完整依赖证明。

CLI（仅登记，未执行；不带 `--execute` 只检查 bundle/freeze，不读请求、不碰 GPU）：

```bash
$PY -B /gpfs/users/jixinpeng/SpecDec/SpecPilot/exp/phase4_run.py \
  --bundle /controller/frozen-bundle \
  --freeze /controller/private-run/freeze.json --freeze-sha256 FREEZE_SHA \
  --request-path /controller/private-input/requests.json --execute
```

这不是研究 tool，不允许通过 broker 把此入口或 `execute_schedule` 的 Python callback
交给研究角色。`execute_schedule(freeze, request_path, runtime)` 仅为可信进程内的
可测试 adapter seam；生产 `run` 固定使用 `LiveRuntime`，CLI 不接受 callback、任意
server/score 脚本或 `runtime_passed`。

生产顺序：

1. `_frozen` 重核 SHA、bundle、arm/launch 与执行源码身份；仅支持 GPU indices [0,1]
   和当前固定四端口，因为复用的 stock scorer/head launcher 有此约束。
2. 默认**不调用 unshare/setns，不检查 CAP_SYS_ADMIN，不要求 privileged pod**。
   guard 如实记录 `network_isolated=False`，保留网络/IPC。核对当前 GPU UUID/name/index
   和空闲状态，拒绝已使用 source UID60010/60011 的进程，取得既有双 GPU lock。
   broker须在调用前停止所有研究角色，并独立保存角色清单/停机证据；本扫描只检查source
   UID占用，不能证明完整研究角色停机，所以回执标记 `research_shutdown_verified=False`。
   controller是独立可信UID且私有目录0700；现有SourceServer的UID-drop启动器仍需其
   既有权限，这不是新增privileged-pod/完整namespace门槛，不新增任何授权。
   仅显式 `--isolate-network` / `isolate_network=True` 才进入单线程UID0的namespace增强，
   核对新namespace/loopback并恢复；选择增强而不可用时明确报错，不静默声称增强成功。
3. guard 内由 controller 调用 `open_phase4`。root/输入保持 owner-only；请求、原始包、
   source 输出和评分日志只写 private root，CLI 只输出状态与结果引用，不回传请求正文。
4. 每 cap 按三 phase 各两轮调用原 `p3_pair_run.run_round(stable_null=True)`；两次
   fresh server 和物理反转 GPU，短/全量 warmup、同步测量和原始 HTTP 原样复用。
   `PrivateSourceServer` 继承既有 readiness/stop，只补私有启动：相同可信 pipe/UID-drop/
   Landlock/seccomp，缓存为 root-owned 0710、专用 GID 的父目录下的 source-owned work。
   source 不能 chmod 上级目录把请求缓存开放给其他 UID；停止时清掉整个 sandbox。
   原 boundary receipt 如实保留 `network_isolated=False`；只有选择增强且实际建立时才
   另存外层namespace证据，不篡改旧receipt。不宣称完整对抗性网络/IPC隔离。
5. `TimedSourceArm` 复用 SourceCapturedArm 的实际 generator/raw。finished_unix 使用
   已记录 wall start 加实测 monotonic duration 投影，不把磁盘落盘耗时计入生成 latency。
   `normalize_round` 只转换原 complete/deployment/events/process/stopped/warmup/pairs/
   telemetry，缺停止证据拒绝，不凭空补 process/时钟/样本；schema 再由原 sealed 协议重算。
6. **全部六个 session/十二轮测量完成后**才启动 stock-only scorer，复用 Campaign 的
   generate/save_trace/audit 与 stock-only `fresh_generations`，不调用旧 dev 主活动或
   `p5_real_run.run`，从而不读取旧20题或作者 final。
7. 真正运行 `head_process(preflight)`、健康 stock/AR、健康2048+tail、stride7/bias2 的
   后2048故障、4096 stock、FP32逆序8分块归约 control。核对当前 checkpoint/head源码/
   config/index SHA、FP32/TF32/shape、原生 hidden-state 包、prefix、数值误差和 control
   输出绑定；再用原 calibrate_delta/stock/judge 与注入包验证重算，不接受 passed 摘要。
   故障必须 event-rule 拒绝且保留既有1024 post2048 token最小覆盖；AR没达到2048、
   无首次偏离可标δ、head能力不符、健康/归约被拒等，均明确阻塞，不调阈值或强迫 EOS。
8. 另生成4096-cap AR；每 cap 每物理轮分别评分**原测速 stock/candidate 输出**，
   绑定原 generator 与 generation segment，并按需采集原 prefill audit；不另生成
   一个“相似 candidate 输出”顶替。依原 controller 逐轮、逐 cap 重算 forcing/噪声/性能。
9. 停止所有拥有的服务、确认端口和 GPU 空闲，退出 guard（仅增强启用时恢复namespace），
   最后才写完整 runtime-result；任何轮/评分/清理失败均不写完整 result。生产失败另有
   private `runtime-failed.json`，CLI 返回1且不打印异常正文/请求。活动不支持中途续跑或
   覆盖旧目录，避免挑选或复用半成品。

主要私有产物：`runtime.log`、`runtime-isolation.json`、每 cap/phase 的原始 round 目录
及严格 schema JSON、`scoring/` 的 preflight/control/所有 trace/注入证据、
`phase4-evidence.json`、`runtime-result.json`。`validate_science` 还要求 science 回执
绑定当前 opening SHA、score/head 时间晚于全部测速；复用旧回执或自报通过不算。

### 状态、缺项与本轮验收

- `runtime_status=blocked`：缺当前 preflight/回归、科学拒绝或性能/forcing不通过。
  没有可执行 FP32 head/足够注入尾部/δ 标定时生产路径失败并封存，而非给假通过。
- `evidence-ready-awaiting-independent-final` 仅表示本入口已收集并重算这组证据，
  **不是 T3**。结果始终 `t3_passed=False/promoted=False/ledger_eligible=False`，还列出
  `unverified_final_requirements`。原保守 sealed controller 接口未改。
- 科学缺项：冻结未见请求上的真实两轮fresh/换卡、常规/4096 forcing、正确性和性能
  尚未执行，不能宣称完成T3。工程缺项为本新runner的真实H100/UID/0700边界复验、
  head加载与回归、独立T0/dev、角色停机与源码/模型/硬件/进程身份、任务终态和封存。
  主助手独立核对这些实际证据；网络namespace/privileged不是本轮缺项或科学闸门。
- `runtime-r02.log`：新增 runtime 11 项＋保留 sealed 13 项，共 **24/24** 通过，23.463秒。
  包含真正本地 HTTP 的 run_round→normalize→严格协议校验（不是 GPU）、12轮调度与评分
  时序、guard/清理失败、私有输入、真实 tmp bundle 全源冻结、head数值/原包/时间拒绝。
- `runtime-existing.log`：既有三个 controller 模块 **16/16** 通过，5.560秒；不是全仓库。
  `runtime.log` 为前一版22项通过记录；无失败测试被改为跳过。源码/日志 SHA 另存
  `runtime-identity.log`。当时本侧任务只新增 runner/test 并补本文，未改旧裁判、旧测试或规则。

### 网络边界澄清后的接口与验收

初版强制namespace的接线已被用户澄清撤销；历史日志保留，不翻为GPU完成。
默认 `run(..., isolate_network=False)` 与 CLI 无 `--isolate-network` 时，缺unshare/privileged
不影响调度入口。该选项只影响额外隔离方式，不改变caps、轮次、hash/正确性/性能判据。
`MISSING_RUNTIME` 也仅澄清UID/私有证据边界文字，T3/promoted/ledger仍始终false。
`unverified_final_requirements` 明确包含broker全部研究角色停机证据，不消费自报passed。
CLI仍只返回聚合状态与controller私有回执引用，不向角色返回逐请求或score原文。
最终CPU测试与SHA记录见 `runtime-boundary.log`、`runtime-boundary-existing.log`、
`runtime-boundary-identity.log`；不是实机namespace/UID/GPU完成证明。
本次 runtime＋保留sealed测试 **26/26** 通过（23.058秒），既有controller **16/16**
通过（6.037秒）。执行源码已变化，真实执行前必须重新生成freeze，不能复用旧SHA锚点。

## 请求池与 resource 接入：先行验收（实现前）

新增 `controller/sealed_cohort.py`、`exp/phase4_resource.py`、必要的
`exp/phase4_remote.sh` 和 `harness/test_phase4_resource.py`；只补本文与必要自身runtime，
不改 `skill_rsi.py`、既有broker/规则/数据。不提交GPU，不读取真实sealed正文。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
set -o pipefail
$PY -B -m unittest harness.test_phase4_resource harness.test_phase4_run \
  harness.test_sealed_protocol -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/resource.log
$PY -B -m unittest harness.test_engine_research harness.test_p5_paper_policy \
  harness.test_p5_scored_forcing harness.test_p6_dev_campaign -v \
  2>&1 | tee logs/skills-rsi-20261110-b01/sealed-tests/resource-existing.log
bash -n exp/phase4_remote.sh
```

判据：仅非敏感tmp数据；候选冻结后controller按hash/seed盲选，排除完整dev索引和全部
已用输入（不以改ID绕过），同prompt协议、每suite足量、hash/正文核对、重复/权限/路径/
源文件漂移拒绝，主助手只获计数/摘要。完整dev索引必须由维护者权威登记，不能将已跑
子集标成全dev；接口绑定所有源索引SHA并说明该完整性责任，不伪造未见证明。
resource只注入现有32h/24h/4卡Budget，不创建第二账本；错误Budget路径/限额、重复任务、
缺停机/终态/独立重算证据拒绝或保守不通过；全部提交行为用mock检验，真实submit次数0。
远端保留0700原始证据、私有日志和可重放源码，不向主助手返回原始日志尾/ID/正文。
显式priority3、原镜像/项目/只读模型/查重/一次create契约复用现有engine_resource，默认
不privileged、不unshare。正式final仍需终态、controller独立重算与封存，T3不自动翻true。

## 追加验收：索引生成、负对照、独立终审（实现前登记）

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_phase4_final harness.test_phase4_resource \
  harness.test_phase4_run harness.test_sealed_protocol -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/final-resource.log 2>&1
```

只用tmp fixture：自动生成全100原dev hash和所有已用hash排除索引、固定来源/seed/counts，
不需人工pool index；14400是单job上限非默认必用，仍由唯一Budget.reserve核剩余预算。
冻结maintenance_stock_control用途，两臂canonical stock/default-off，不能切换成科学候选。
execution_completed/protocol_verified/scientific_ready/correctness_passed/performance_passed分别报告；
完整科学拒绝不是基础设施失败，control无收益且健康/故障/归约真实回归完整才expected_rejection。

新增controller/phase4_final.py及harness/test_phase4_final.py：真实子进程出生与wait退出回执、
退出早于揭盲、跨UID拒绝、私有证据完整SHA封存、可信Kubernetes原始Job/Pod终态绑定、
重跑dev/sealed/science/cohort验证、独立进程要求。fixture必须覆盖真通过分支与缺项拒绝；
不接受研究自报passed。终审必须在原controller UID/相同绝对路径和镜像中运行，host UID5084
仅生成/读取非sealed元数据及聚合，不放开root0700/0600。T3不是promotion/T4/ledger。

## 最小接续验收：legacy停机证明仅支持负对照（实现前）

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_phase4_final -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/legacy-shutdown-tests.log 2>&1
$PY -B -m unittest harness.test_phase4_resource harness.test_phase4_run \
  harness.test_sealed_protocol -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/control-resource-tests.log 2>&1
```

新tests只验legacy观察/冻结/远端核对和新入口birth/exit工具，不宣称独立finalizer已验收。
legacy观察必须真实调用harness.skill_rsi_audit.audit，绑定原pipeline/source archive、完整
Master+3direction+Integration+Kernel六角色native清单与exit0，旧六PID当前任何一个存在即拒绝，
不猜startticks；扫描同broker UID的工作区/cwd/会话环境及全host可见命令行，权限不足则拒绝。
0700/0600可信观察记录historical_birth_identity_unavailable=True；远端按broker UID、SHA、
审计源码及原始证据核对。只允许maintenance_stock_control，科学候选仍要求新birth/exit证据。
历史resource-state在观察时另存副本并与pipeline快照核对；后续同一Budget.reserve追加Phase4
不应破坏已冻结的旧阶段审计。公共preparation元数据可生成cache/sources.json和used dataset
引用，host不stat/read私有源；最终root按固定revision/SHA复验复制，不能把旧dataset当新pool。

本轮control采用同GPU job内独立root子进程重算与私有证据SHA封存，host仅核Kube终态、
已冻结source/request及公开聚合SHA。验收追加：封存不含自身及仍打开的bootstrap/controller/
replay日志，明确列出这些非科学证据例外；原始日志仍留0700内。封存覆盖请求池/选择/原测速/
forcing/head回归/代码等已关闭证据，独立重算SHA与封存SHA仅以聚合返回。host不能重读私有
文件，不宣称已执行root后终态T3 finalizer，不为负对照增加GPU或CPU job。

真实布局追加验收：root没有source.tar，不构造历史root归档。读取保留的
host-loaded-identity.json，绑定其指向的首个诊断逐请求source.tar/source-identity.json及
host-start-skill-rsi.py，核copy SHA==回执script SHA==tar内exp/skill_rsi.py SHA。
这是当时运行期间保留的host加载源码身份记录，不是出生证明；每个GPU归档仍由原audit验证。
角色work/home/canary实际共用独立/tmp/specpilot-codex-role-*父根，核绝对无symlink、owner、
父根0700、home0700、work不可被其他用户写；不要求其位于日志角色目录。
新增真实codex_boundary.prepare生成的非敏感manifest fixture（伪凭据/不启模型/GPU）、
无rootarchive通过与归档/host副本SHA漂移拒绝；完成代码冻结后另做本机真实legacy观察，
不读取private/sealed，失败回执保留。观察后修改任何绑定源码必须重新观察，不能复用旧SHA。

coverage-review补充验收：observe接受extra_shutdown_registries，另核真实birth/exit/close_registry，
原六角色与额外角色分别计数冻结；若coverage-review-*/processes目录已存在但未提供其闭合
registry则拒绝，不因旧pipeline为research_complete忽略新Master。CLI可重复指定
--extra-shutdown-registry。观察必须等待coverage完成；组合proof仍仅用于负对照，保留原六
historical_birth_identity_unavailable=True。

control身份验收：request/remote/replay/aggregate的candidate_tree_sha必须是实际stock树，
原bundle优化树仅作为bundle_candidate_tree_sha元数据保留并由bundle manifest冻结；错身份
必须在揭盲前或独立重算时拒绝。seed/counts不因control或身份修复改变。

## 本轮负对照接入与当前验收

`control-final-cpu.log`：legacy/birth工具、resource/cohort、runtime、保留sealed协议共
**66/66 CPU检查通过**（48.344秒）；包括真实prepare生成的独立tmp工作区、无root archive、
host加载副本/逐请求tar漂移拒绝、额外coverage bootstrap/native真实子进程闭合、原六旧PID
存在/会话残留拒绝、stock实际测量树身份、job内独立重算与私有SHA封存。
`control-existing-tests.log`：原Budget/paper-policy/scored-forcing/dev-campaign **34/34**
通过（9.571秒）；`bash -n exp/phase4_remote.sh`通过。不是GPU或完整finalizer验收。

真实停机观察尚未执行：用户随后启动显式repair-review，要求等待其自然退出。
第一次coverage因brief/分页/schema能力不足的原始记录保留，不称完整科学裁决。
下列仅为待维护者执行的接线示例，所有闭合registry（含第一次coverage和repair）均须提供，
绑定源码在观察之前定稿、此后不再修改；缺目录对应registry会拒绝。

```python
import json
from pathlib import Path
from controller.phase4_final import observe_legacy_shutdown
from exp.phase4_resource import prepare, execute
from exp.phase4_run import reference

stage = Path('/gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/skills-rsi-20261110-b01')
proof_dir = stage / 'sealed-tests/legacy-observation-final-01'
proof_dir.mkdir(mode=0o700)
registry = observe_legacy_shutdown(stage, proof_dir,
    extra_shutdown_registries=[reference(path) for path in closed_review_registries])
proof = json.loads(Path(registry['path']).read_text())
research_roots = sorted({context for role in proof['roles'] for context in role['contexts']})
cohort = json.loads((stage / 'phase4-preparation/cohort-spec.json').read_text())
job = stage / 'sp-skillrsi-20261110-b01-phase4-stock-control'
prepared = prepare(job, bundle=existing_measured_bundle, cohort=cohort,
    shutdown_registry=registry, research_roots=research_roots, budget=existing_stage_budget,
    deadline=14400, maintenance_stock_control=True, isolate_network=False)
# 维护者另行核对prepared/plan.json与唯一Budget剩余额度；下一行会真实提交GPU。
# result = execute(job, job / 'source.tar', existing_stage_budget)
```

`closed_review_registries`是本阶段所有额外review的实际shutdown-registry.json路径；
`existing_stage_budget`是主执行器已持有的同一个32GPUh/24h/并发4卡Budget，不创建新账本。
接口参数是`maintenance_stock_control`，不是`maintenance_control`。
controller CLI也可独立运行：`python -B -m exp.phase4_resource legacy-shutdown --pipeline STAGE
--output NEW_PRIVATE_DIRECTORY --extra-shutdown-registry CLOSED_REGISTRY`，最后一个参数可重复。
该CLI只生成0700/0600停机证明，不提交GPU；审计失败不产生可用legacy-shutdown.json。

host只传当前cohort-spec及metadata SHA；controller root在最终job中读取五份原dev、全部
used refs和旧固定公共源cache，生成新pool/index再按冻结seed/counts盲选。host不打开这些
private文件。`cache_from_public(preparation_ref, private_source_root, destination)`仅构造
cache与used引用，不stat/read私有树；root复验revision/SHA并复制，无需九源再下载。
本轮5suite各1题是小规模架构验证，不是论文100题数字复现。

job内独立controller子进程调用`write_private_replay`，重算真实协议/科学回归/cohort，
封存`job-evidence-seal.json`；只发布聚合与private_replay/private_evidence_seal SHA、封存
文件数。host在GPU真实终态后核Kube优先级/exit/restarts、source/request/public replay SHA。
不为control增加CPU job；root后终态T3 finalizer未执行/未验收。`finalize`等原型不作为本轮
执行入口。control的t3_passed/promoted/ledger_eligible/controller_accepted始终false。
execution_completed与scientific_ready、correctness/performance、expected_rejection分别报告；
无收益且实际健康/错误注入/归约回归齐全时，完整负对照属于预期科学拒绝，不是设施失败。

## 跨节点legacy修正验收（实现前）

host观察继续真实重算完整audit、检查原六角色tmp owner/权限/immutable SHA和/proc。
proof分别冻结共享原生/源码/归档SHA与host临时文件SHA；仅列canary、rules、evidence、config，
不复制或读取auth。remote仅重验共享GPFS证据、可信broker UID/0600/SHA回执及其中已冻结的
host观察元数据，不stat/read/resolve原host的/tmp，不重观host/proc。提交前同host检查仍真实
重查tmp/proc；正常科学候选及final路线保持严格默认行为。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_phase4_final -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/legacy-cross-host-tests.log 2>&1
$PY -B -m unittest harness.test_phase4_resource harness.test_phase4_run \
  harness.test_sealed_protocol -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/control-cross-host-regression.log 2>&1
```

新增fixture对全部旧角色tmp的stat/read/open/resolve强制ENOENT；control远端验证应通过且
不得调用host观察器，共享native或receipt漂移仍必须拒绝。当前repair仍运行，本侧不做
真实observe/prepare/submit；旧source inventory随代码变更失效，交付时重新生成。

安全错误回执追加验收：root异常完整traceback只存0700/0600内，public error.json仅有异常
类型、可信源码相对文件/函数/行号、私有trace SHA及request/source SHA，无str(error)、
局部变量、原始源码行、请求/输出/ID或private绝对路径。host严格schema核对后仅转发安全
字段，不回收原始trace、不另建任务。fixture注入含敏感正文的异常并验证完全不进入public。
repair现已结束，待跨机fixture通过且源码定稿后，只做本机真实legacy观察，不prepare/submit。

### 跨机修正交付状态

`legacy-cross-host-tests.log` **15/15通过**（19.818秒）；旧角色tmp的stat/lstat/read/open/
resolve均被fixture强制ENOENT，默认remote验证及附加闭合registry仍通过，且禁止调用
host角色stat/proc观察器；共享native与receipt SHA漂移仍拒绝。
`control-cross-host-regression.log` **53/53通过**（34.617秒），包含安全错误回执注入、
私有trace 0600/SHA、public不含异常正文、host失败反馈安全转发与非法private帧路径拒绝；
`bash -n exp/phase4_remote.sh`通过。合计68项CPU检查，不是GPU验证。

`validate_legacy_shutdown(..., check_current_host=False)`只验证共享证据与可信冻结host观察。
`research_stopped`在提交前显式传True，仍在原broker host实际检查tmp/proc。
host proof新增`host_temporary_files`仅含四类不可变文件SHA，无auth拷贝或正文；共享
`original_files`不再包含host tmp文件。真实host检查01已据主助手回执成功（原六+额外四
进程），不是本侧重新执行；本次源码变更后必须新目录observe02，旧proof不能用于提交。

root异常时`publish_safe_error`保存private/error-trace.json并发布error.json，host的
`safe_error_feedback`严格检查字段及request/source SHA；execute失败只转发safe_error，
不附私有路径/原始日志/异常文本。现有成功聚合schema和科学阈值未变。
终版代码清单另存`control-cross-host-source-sha256.txt`及
`control-cross-host-execution-sources.json`；此前control-final清单是历史版本，不复用。
本侧到此停止修改绑定源码，不执行observe02/prepare/submit，交维护者按既有调用执行。

## control01启动前设施失败：umask077与稳定盲选（先行验收）

据维护者终态回执，control01只消耗144 GPU秒，在READY空管道处JSONDecodeError，尚未
测量/生成，无科学反馈。本次不读取root私有trace、不新增GPU；先用真实umask077文件与
CPU子进程/pipe重现权限及EOF，再仅显式开放无敏感allowed探针0444、trusted-bootstrap
目录0755及可信bootstrap代码0444。controller-private0700/0600、canary0600、UID/Landlock/
seccomp及ROOT授权范围不变。host fixture不宣称完成真实UID60010/60011降权或GPU验证。
空/畸形READY应明确BoundaryHandshakeError，仍由已有safe error仅导出代码帧和私有trace SHA。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_phase4_run.Phase4RunTests.test_umask077_private_boundary_permissions_and_cpu_ready \
  harness.test_phase4_run.Phase4RunTests.test_private_boundary_empty_or_malformed_pipe_is_explicit \
  harness.test_phase4_resource.CohortTests.test_blind_selection_is_stable_across_private_directory_relocation -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/control01-startup-repro.log 2>&1
$PY -B -m unittest harness.test_phase4_final harness.test_phase4_resource harness.test_phase4_run \
  harness.test_sealed_protocol harness.test_source_research -v \
  > logs/skills-rsi-20261110-b01/sealed-tests/control01-startup-regression.log 2>&1
```

盲选排名改为冻结seed+id+suite+input_sha256，不含job-specific request.path；fixture将相同
pool搬到另一私有目录，必须选出相同身份及次序。seed/counts/完整dev与used排除不变。
这是生成/测量前设施失败后的可复现性纠正，不是凭收益换题；旧selection和失败证据保留。
若不做额外controller迁移，旧selection不自动跨旧代码freeze复用；本次只保证稳定算法下
相同pool身份在后续目录/重试之间不漂移，不把改后的选择冒充与旧path排名完全相同。
同一32GPUh Budget保留144秒已消耗成本；后续仅维护者以新job名/新freeze/剩余额度重试。

### prefix audit接线验收（实现前）

复用Locke已验收的skill_rsi_audit.audit：旧pipeline的8job/9234秒作为不变历史prefix，
已终态control01的144秒另列extension，总快照9job/9378秒，不重置或改写旧snapshot。
proof同时冻结历史snapshot及观察时live snapshot；shared original_files仅枚举冻结的9job
公开文件（包括extension的public error/result/replay），绝不递归private。remote按该9job
快照重算清单，不动态枚举新预算行。live必须仍有完全不变的9job prefix；最多允许追加
当前request/plan/source/proof绑定且同Budget的新2卡预留，不允许未知、其他或多条active行。
observe时仍要求所有历史/extension全终态并通过独立prefix审计，不能以预留许可逃审。
fixture覆盖terminal extension后observe、绑定新预留、tmp不可见remote、原prefix/公开文件
漂移及未知/active扩展拒绝；完成后仅做真实observe03复验，绝不prepare/submit GPU。
