# 第 5 步：裁判修复与真实验收准备

状态：基础修复完成，真实噪声验收未通过；第 5 步整体未完成。基准 `b5c7706`；用户明确回复“允许修改”，授权本阶段
`controller/` 正确性与统计实现修复。不是 sealed、放宽门槛或独立 RSI 的授权。

## 先固定验收，再实现

1. 空请求、空 token、缺失/多出输出、非法 token、非法统计参数一律拒绝。
2. 二项尾概率须与小样本精确枚举一致，支持 n=4096/100000、p=0/1，概率有限且在 [0,1]。
3. rate rule 使用分歧率下界与基线之差 >0.005；旧 token-list 入口只能作诊断，
   不将其伪装成真实 margin-aware forcing。保留旧 mock 基线参数但明确不是当前实测值。
4. HTTP 输出分歧时，性能增益下界须同时大于 `1%+2*noise` 和 3%；
   拒绝负/非有限噪声；即便该性能条件通过，也不代表真实 correctness 或晋升通过。
5. stock/stock 明确生成 stock-a、stock-b 两个实例，均启动 stock 引擎及 block=8，
   文件不碰撞，fresh server/物理换卡及清理仍由既有编排执行。不允许其它同名比较。
6. 原审计 9 项逐项通过；审计仍 exit=1、production_ready=false，直到真实证据完备。
   不改旧审计输入或把真实前置缺失硬编码成通过。
7. 原 50 项回归、7 项审计工具测试及新增裁判测试通过；P2/P3 全部历史产物校验一致。

执行命令：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p5_controller.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'
"$PY" -B exp/p5_readiness_audit.py --out <独立新目录>/audit.json
git diff --check
sha256sum --check --quiet logs/p5-readiness-evidence-20261107.sha256
```

先红后绿的测试输出使用独立 logs 目录保留。没有真实运行证据的项目仍标未完成。
不改动历史报告/清单，不覆写 ledger，不读取 sealed 或作者实现源码。

## 真实链路的独立边界

真实 scorer 必须沿候选自己的前缀评分，记录 target argmax、候选 gap、FP32-head 身份、
stock mismatch 与 delta 标定来源；普通输出一致性不能替代。若只有不同 backend 的
Transformers 参考或 BF16 logprobs，只能标参考诊断，不能声称 stock-engine FP32 forcing 完成。

真实 null 先固定原 20 条 dev 请求、2048 cap、warmup=2、两轮 fresh server/物理换卡；
每次会话独立报告，至少两次会话，不把两轮当独立请求。CI 全宽 <0.002 的要求不变，
未达标则如实失败，不追跑到碰巧变绿，不将跨会话均值冒充会话内噪声。
NorthJob 沿用用户已确认镜像/WeaverDev/qiji/原 toleration 与 2 H100，
每次提交按 skill 查重、展示完整命令、核对 code=200 和 UUID。

## 结果

- 旧缺陷先红：16 项新增契约测试执行失败（含多个 subTest），记录 `logs/p5-controller-repair-20261107-a01/red.log`。
- 修复后新增 16 项及新增 null/分层统计 6 项通过，最终新旧 **79/79** 通过。
- 原审计输入未变，9/9 合成前置检查通过；审计仍 exit=1、production_ready=false，
  因真实 FP32-head scorer、stock mismatch/delta、真实注入及 null 证据尚未齐备。
- 修正旧 G4 的长度故障处理：完整性校验主动 ValueError 即正确拒绝，
  不再要求一个不完整序列继续进入 rate/event；没有运行 GPU G4 冒充真实 27B 验证。
- 真实 null 入口 `exp/p5_remote_null.sh <新目录>`，一次 2-H100 任务顺序运行两次独立会话，
  每会话 20 请求/2048 cap/两轮 fresh server/物理换卡。由 `controller/null_validation.py`
  校验身份、覆盖、独立实例输出稳定性，并给 suite-stratified request-cluster 双侧 95% CI。
  `noise=max(|upper-1|,|1-lower|)`，同时单独检查 **区间全宽 <0.002**。
  生命周期 exit=0 不等于 precision_passed；门槛不达标仍保存全部结果，不产生晋升。
- PDF §3.3 已重新核对：delta 是 stock 首次偏离 AR 的最大 margin，向上取整至 1/8；
  event 是 margin>2delta 且经 stock replay / prefill-length 审计仍无法解释的事件，
  不是普通 token 不同的计数。旧 token-list 入口现明确标诊断，不拿它冒充真实 scorer。

已完成一次远程 null 校准，提交/启动/测量/清理均有证据；统计精度门禁未通过，停止正式晋升推进。

## 真实 null：a01

- 源 pin：`dbebc6b88e97b893d7a0afd2a326a8ed37fd1bbc`；未更改模型、引擎树与已确认镜像。
- 名称 `specpilot-p5-null-20261107-a01`，提交前精确查询 total=0。
- 2026-11-07 21:01:40 +08:00 返回 code=200/data=None；随后精确名称唯一匹配
  UUID **`job-3c6565eedef3-20261107210140`**，不是依靠 CLI exit=0 推断成功；没有第二次 create。
- 1 节点 ×2 H100，256 GiB，普通 bash、nproc=1，禁 RDMA/hostNetwork。
  project=WeaverDev，namespace=qiji，请求 queue=qiji、服务端实际 queue=proj-31；
  toleration=`key=task-type,operator=Equal,value=infra-dev-weaver,effect=NoSchedule`。
- image=`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
  主 PVC=jixinpeng-pvc，模型 PVC=share-readonly/models，双层 readOnly，未更换镜像或升级 CLI。
- Pod `job-3c6565eedef3-20261107210140-master-0` 在 node233 启动，实际 image/GPU/hostNetwork 已核对。
  首轮两个 stock server 均在 21:05:51 +08:00 ready，不能把此时记为测量完成。
- 原始输出：`logs/p5-stock-null-2048-20261107-a01/`；外围日志与脚本退出码使用同名前缀。
  CLI 帮助、查重、提交回执和 Pod 资源证据：`logs/p5-controller-repair-20261107-a01/`。
- YAML：`RUN/specpilot-p5-null-20261107-a01/specpilot-p5-null-20261107-a01.yaml`，不进 Git。
- 实际启动命令（NorthJob 参数为上述值，所有选项先于 user command）：

```bash
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory \
GIT_CONFIG_VALUE_0=/gpfs/users/jixinpeng/SpecDec/SpecPilot \
P5_EXPECTED_COMMIT=dbebc6b88e97b893d7a0afd2a326a8ed37fd1bbc \
bash /gpfs/users/jixinpeng/SpecDec/SpecPilot/exp/p5_remote_null.sh \
  /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/p5-stock-null-2048-20261107-a01
```

- 最终生命周期：Job=Completed、Pod=Succeeded，容器/脚本 exit=0、restart=0；
  2026-11-07 21:02:04–21:18:55 +08:00，在 node233 完成。两会话清理均为两卡 0 MiB/0%。
- 数值计算另外与已安装 SciPy 的 binom.sf 独立核对 95 组（n 最大100000，含 p=0/1），
  全过，最大绝对误差 `1.3855094849191119e-10`。没有给 dev 环境新增运行依赖。
- 引擎黑盒 `launch_server --help` 确认有 `--enable-fp32-lm-head`，
  但“存在开关”不等于已取得逐位置评分/校准/事件审计证据；真实 forcing 仍待实现验证。

## 两会话实测结果与停止决定

两会话各 40 pair/80 臂行，总计 **80 pair/160 臂行**，但仍只有原 20 个不同请求，
不是 40 或 80 个独立请求。每会话两轮 fresh server / 物理 GPU UUID 互换；
同请求输出在两实例、两卡位及两会话间一致。身份与请求逐项绑定 A1，未更换样本。

| 会话 | stock-b / stock-a 几何平均 | 分层双侧 95% CI | CI 全宽 | noise（距1的最大端点距离） | 全宽 <0.2% |
|---|---|---|---|---|---|
| 1 | 0.9999525264× | [0.9986248088, 1.0012594020] | **0.2634593%** | 0.1375191% | **未过** |
| 2 | 1.0033328725× | [1.0026846326, 1.0039834119] | **0.1298779%** | 0.3983412% | 通过 |

**整体 precision_passed=false，独立精度门禁 exit=1。**
这与生命周期 exit=0 不矛盾：任务成功执行并留下了未达标的测量证据。
第二会话虽区间窄，但中心偏离 1；不能把半宽当噪声、只挑第二次，
也不能把两个会话平均后宣称“每次会话都通过”。未重复 create、未删异常点、未追跑到变绿。

测量 pin=dbebc6b。原始结果 `ci95` 继承 P3 的 pooled 诊断字段，
真正用于本次门禁的是 `interval` 中的 suite-stratified CI。
测量结束后仅澄清 reader 字段：`ci95` 指向分层 CI，旧字段另存 `diagnostic_pooled_ci95`；
没有改原始 JSONL/JSON，也没有改变判定。独立复验输出
`logs/p5-controller-repair-20261107-a01/independent-null-reaudit.json`，两次会话所有区间/噪声/判定与原始结果相同。

后续应先定位预热/稳态与 server 角色相关的时序偏差，预登记新的稳定性协议后再验证，
不能放宽 0.2% 门槛。FP32-head scorer、stock mismatch/delta、真实 post-2048 注入、
等价归约对照仍未完成；这次只证明基础漏洞已修、真实测量链路可审计，**没有证明 lossless**。
无正式晋升、无 ledger 写入，不建立 sealed、不进入 RSI。

## 最终验收与归档

- 最终新旧测试 **79/79**；其中最后一次 reader 元数据调整曾因测试 fixture 缺少 method 字段报错，
  补全 fixture 后重跑通过，前次失败日志也保留，没有覆盖。
- 9 项旧反例全过；95 组 SciPy 交叉核验通过。shell 语法、`git diff --check` 通过。
- A1/A2/A3 实际统计重新复算通过，P2/P3 及初始 P5 审计全部历史 SHA 清单保持完整。
- 78 文件证据清单 `logs/p5-controller-repair-evidence-20261107.sha256`，
  清单自身 SHA=`170479f90a00a324865fe3430f9ab066906e19b213d52cdbef997fc9790f0c4d`，复核通过。
- 完整当前 controller/exp/harness/gates 执行代码快照（不含 sealed、模型、凭据）：
  `logs/p5-controller-repair-20261107-a01/final-source.tar`，
  SHA=`898b29b34da34dc9a6c3c68bcb9587b2f69142c4152f4cc098155ededeff8116`。
- 源 pin、源文件哈希、请求/输出一致性、生命周期、门禁和测试验收沿日志可追溯；
  代码/报告/主页/交接提交并推送私有 GitHub，原始产物不入 Git。当前无运行中任务。
