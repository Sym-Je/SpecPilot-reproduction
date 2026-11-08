# 真实候选接入与 no-op 双卡烟测

日期：2026-11-09 UTC+08；基准 `dc1f2ef9c5bc193e59bd3c128a4563b9a145aacd`。
状态：实现、真实双卡烟测、独立重放与归档全部完成。执行日志保留 UTC。

## 目标和范围

新增独立 candidate 的身份、stock同源构建、启动开关、配对和评分接入，不修改controller。
第一版明确只支持一个启动参数option：`draft_tokens`，关闭时固定stock=8。
烟测中开启值也为8，是刻意无行为变化的接线检查，不算新机制或自主发现；
不声称已支持任意源码patch，也不把同token输出当作lossless证明。
candidate engine从stock复制并程序化校验canonical hash，不手工阅读作者引擎实现。
既有AR/stock/final入口保持原样；不碰eval/sealed、ledger或memory。

## 执行前验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p10_candidate
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p[2356789]*.py'
bash -n exp/candidate_remote.sh
git diff --check
git diff --exit-code dc1f2ef -- controller patches agents costmodel orchestrator assets/upstream
```

先红后绿：stock默认8、有效开关、spec/config/实际engine篡改拒绝、未知字段/非法类型拒绝、
构建不能覆盖已有目录、外链/断链/目录链拒绝且合法内部相对文件链接保留并计入hash、
环境污染清理、实际server参数错配拒绝；
CPU真实HTTP模拟验证fresh双server/物理换卡/原始HTTP捕获/完整请求和输出一致性。
评分复用NativeClient/FP32 stock scorer及controller的原始输出绑定校验，不能自写lossless规则。

## 远程 smoke 预声明

- 已确认镜像沿用 `harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
- WeaverDev / namespace qiji / 请求queue qiji，沿用已确认toleration；1节点×2H100、256Gi。
  禁RDMA/hostNetwork；bash/nproc=1。最多1小时，即2GPU小时，不因性能结果追加实验。
- 关闭、开启两种模式分别做两轮fresh双server并物理换卡；每suite1条，共5条已公开dev请求，
  64token cap，自然EOS；合计20pair/40臂行，不把两模式和物理重复当新独立样本。
- 两模式必须都与stock实际输出一致；这只是no-op/default回归，不是一般候选的正确性标准。
  计时数据由既有HttpPairBench产生，但本smoke不提供正式性能/晋升判定，不套历史noise/δ。
- 测速全部结束且GPU释放后，启动stock FP32 scorer，评分全部40条实际输出并核验自身prefix/
  原始生成绑定；不以短烟测估计δ或宣称rate/event门禁通过。
- 记录提交、启动、GPU/接口验收三个独立状态；退出前保存持久产物、清理两卡/端口。
  当前help→任务名查重→展示完整命令/2GPU→create一次→code200+精确UUID；不明先查重。
- 完成后CPU独立重放、SHA归档、更新README/HANDOFF/索引并推送私有origin。

## 执行与结果

- 17项新CPU/真实HTTP测试通过，167项历史回归通过。未修改controller、作者配置/引擎实现或三臂入口。
- 红测试保存于准备目录`red-tests.log`、`red-integration-tests.log`、`red-launch-tests.log`。
  首次实际stock契约因唯一合法内部相对`.clang-format`文件链接被过度拒绝，空`stock-contract.json`
  和`red-internal-symlink.log`保留；修复复制保留内链且canonical hash不变，`stock-contract-02.json`通过。
  只查看链接元数据和程序hash，未手工读作者实现。
- 实际历史server参数schema与新候选启动参数逐项一致，`launch-compatibility.json`无差异；
  这只是静态兼容性证据，不替代本次启动验收。
- 下文追加实际源码pin、任务UUID与验收；本阶段不自动进入真实搜索或sealed。

### 冻结、提交和启动（不等于科学验收）

- 执行源码pin=`d526f763b3c003f84e8a0e91a8adf5a5db8e87ba`；
  `logs/candidate-prep-20261109-a01/source.tar` SHA=
  `94e1a6cc8d5ea734ab57021c0d09d00752e57a88670689427c022fe6362c9915`。
  tar仅含controller/exp/harness及已公开dev/config，不含sealed、凭据或作者引擎实现。
- 独立bundle=`logs/candidate-bundle-20261109-a01/`，spec SHA=
  `4b55bd2d3d232d25ee7107f74e902bc7c9ab0359a1eec044b1586a50925f8037`。
  完整stock canonical SHA=`e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff`。
- 当前CLI3.3.11的create help已核对，不升级；两次查重均total=0。
  完整shell-escaped命令与资源见`create-command.txt`，通过既有双卡/只读models挂载适配器
  `exp/p2_northjob.py`调用NorthJob CLI；未新增内部提交接口或手写调度YAML。
- create只执行一次，服务端`code=200,data=None`；首次自动解析器未取得UUID，按规范精确查名，
  唯一`user_def_name`解析到`job-4fcf9416b13f-20261109072806`，不是再次提交。
  `submit.txt`、`post-submit-query.txt`、`submitted-identity.json`均保留。
- 2026-11-08 23:28:33 UTC容器启动，node233；镜像digest、2GPU/256Gi、只读models挂载、
  hostNetwork关闭已核对，实际queue=proj-31。H100/torch2.13.0/SGLang0.5.20实际预检通过。
  正式运行`logs/candidate-run-20261109-a01/`及同前缀`.log/.exit-status`，原始逐题输出不手工查看。
- 上述为当时提交/启动记录，不代替验收。运行中未改源码或commit，仅更新文档；
  监控`logs/candidate-prep-20261109-a01/lifecycle.*`前台运行，已结束，未重复create。

### 最终验收

| 项目 | 结果 |
|---|---|
| CPU回归 | 新17项 + 旧167项，共184项，通过；`final-regression.log` |
| 真实启动 | 测量8个fresh server、两模式各两轮物理换卡；另起1个stock FP32 scorer |
| 请求和输出 | 5独立公开dev请求，20pair/40臂行；所有20对输出相同，默认与开启no-op均过 |
| 运行路径 | 4个candidate runtime receipt均解析到独立bundle内的sglang；源树与stock canonical SHA相同 |
| 原始证据 | controller验证HTTP请求/输出/启动身份/时序；8个预热pair另存，未冒充正式样本 |
| 评分接入 | 40条实际测速输出、2560 token均完成stock FP32-head自身prefix评分及controller绑定检查；head preflight通过 |
| 生命周期 | Job Completed、Pod Succeeded、容器/脚本exit0；两卡0MiB、利用率0/1%，端口释放检查通过 |
| 独立重放 | 两独立CPU进程02/03与远程result.json逐字节一致 |
| 预算 | 容器23:28:33–23:40:24 UTC，11分51秒；按2GPU×容器时长折算0.395GPU小时，低于2预算 |

上述UTC时间对应2026-11-09 07:28:33–07:40:24 UTC+08。23个监控快照仅观测到1个Pod UID、
容器restart0；Job retryCount字段未设置，不将其冒充服务端保证的全任务零重试。
全部40臂行实际均64 token且length触顶，允许自然EOS但本样本没有自然结束；不是完整任务质量验证。

CPU首个离线重放01因sudo的PATH找不到git失败，`replay-01.log`原样保留。
仅在后续受控进程显式传入原PATH和仓库safe.directory，未改全局配置或任何判据；
02/03重放成功，无新GPU执行。三份结果SHA均为
`eccc657de223a957ee59a7847705844008df077b8fd7fdcdd14d29f1fe619ebf`。

**边界：**`correctness_passed=null`、`performance_passed=null`、`promoted=false`、`ledger_eligible=false`。
这里证明的是接线、no-op默认回归与评分证据可用，不是rate/event正确性门禁或性能晋升通过，
也不是语义非劣、数学lossless、任意源码patch支持、真实自主发现或论文sealed数字复现。
未调用旧mock loop，controller/patches/agents/costmodel/orchestrator/作者配置/dev均未修改。

### 归档与复核

本阶段2970个校验项、逻辑校验字节38058598（包含1个保留的内部相对文件链接及CLI生成YAML），
清单`logs/candidate-evidence-20261109-a01.sha256`，SHA=
`9249c02f1a26a4856d01d412a3c7b635a28bf29b32684856873679613126ed4e`。
全部校验通过，日志`logs/candidate-evidence-verification-20261109-a01.log`。
上一阶段37项准备证据也复验通过；原始生成/评分/引擎快照不上传Git，Git仅追踪源码和脱敏索引。
CLI生成YAML位于`RUN/specpilot-candidate-noop-20261109-a01/specpilot-candidate-noop-20261109-a01.yaml`。

当前源码仍与执行pin一致，只有文档后续更新，可如下CPU复核；输出必须使用全新路径。
未来源码改变时需另建对应冻结源码的受控复核环境，不覆盖当前编辑或既有证据。

```bash
ROOT=/gpfs/users/jixinpeng/SpecDec/SpecPilot
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
sudo -n env PATH="$PATH" CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$ROOT" \
  "$PY" -B "$ROOT/exp/candidate_smoke.py" audit \
  --directory "$ROOT/logs/candidate-run-20261109-a01" \
  --out "$ROOT/logs/candidate-prep-20261109-a01/replay-NEW.json"
sudo -n sha256sum -c logs/candidate-evidence-20261109-a01.sha256
git diff --exit-code d526f76 -- controller exp harness assets/upstream
git diff --check
```

**决策：本阶段完成，无运行任务。** 下一大步骤先报告代表性stock profiling/replay和实测成本模型方案，
获用户允许再执行；真实proposer、任意源码option扩展及正式晋升/账本集成仍需后续交付。
