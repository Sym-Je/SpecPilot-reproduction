# 中文短答减速：匹配因素与执行阶段诊断

状态：用户已批准执行，数据/源码/验收冻结，GPU运行中。基准496ab11。

## 目标与边界

固定作者stock/final及46开关，不改controller/patches/作者配置，不碰sealed/RSI/ledger/memory。
区分语言相关、实际输出长度相关与输入处理/草稿/验证开销的证据；不是训练模型或追论文数字。
匹配实验只能识别本合成工作负载中的条件效应，不等于证明中文语言本身是普适原因。

## 预声明流程

1. 十二个独立合成事实卡，每张生成语义对应中英文任务，短答/详细答两种指令。
   输入完整chat模板精确512/1536token，语言对应的无关背景padding，不裁剪事实和问题。
   事实卡为独立cluster，语言/长度/物理轮次均为同卡重复，不冒充更多独立样本。
   合成匹配不是自然文本分布，padding本身和翻译差异是限制。
2. 自然组：12卡×2语言×2输入长度×2回答指令=96请求，2048cap自然EOS。
   记录实际输出分布、EOS/截断、短/长指令是否真正拉开长度；不因不遵从指令删样/换题。
3. 固定长度组：同卡短答指令的48请求，分别精确生成64/256/1024token。
   显式ignore_eos=true，其余greedy/top_k1不变；是长度干预，**不能当自然任务收益或质量结论**。
   EOS后的延续可能改变token难度与草稿表现；长度对比不能单独证明“只有固定开销”这一机制。
   解释时核对EOS后延续与不同预算的共同前缀稳定性，只作为辅助诊断，不替换三主要端点。
   每个条件null-pre→stock/final→null-post，各两轮fresh双server/物理换卡，2短预热+全集全尺度预热。
4. 三主要条件对比：固定64token的中文/英文加速比之比；固定1024/64token的加速比之比；
   固定1536/512输入的加速比之比（跨三个输出预算等权）。以12事实卡做cluster，
   调用controller.stats，普通95%与三项Bonferroni同时区间；区间跨1标证据不足。
   每条件直接配对请求延迟比stock/final为主；token速率、轮次/细分格为诊断。
5. 正式计时结束后另起两轮fresh/换卡，只做诊断探针：固定首卡、512输入、中英文，
   1token往返作为“输入处理+首次解码+HTTP”代理，**不叫纯prefill**；
   64/1024token使用公开/start_profile、/stop_profile采CPU/GPU trace，不读作者实现。
   保存OpenAPI schema、所有成功/失败调用、trace和SHA，profile耗时绝不混入正式性能。
   仅明确命名scope用于阶段归因，重叠scope不相加；未知GPU kernel不猜成draft或verify，
   无阶段scope则明确“不能分解”，保留未归因比例。final spec_verify_ct仅作未验证计数，不直接当接受率。
6. 无引擎修改，本阶段不新增语义非劣/lossless宣称；固定长度不是正常完成任务。
   复用已验收裁判计时/统计，不在harness另设晋升规则。本次不晋升、不写账本。

## 预算及停止规则

一次普通bash NorthJob：1节点×2H100，256Gi，最长8小时（16GPU小时），沿用已确认digest镜像、
WeaverDev/qiji/原toleration。无RDMA/hostNetwork，不因结果不好扩样。
profile公开接口或权限不可用只记能力限制，不改引擎/不无证据分摊时间；profile总产物上限4GiB，
达到上限停止额外profile并报告缺项，不删除已生成证据。故障/缺轮不能报执行通过。

## 先写验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p9_diagnosis.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[2356789]*.py'
bash -n exp/diagnosis_remote.sh
git diff --check
git diff --exit-code 496ab11 -- controller patches assets/upstream
```

先红后绿：因素完整/精确输入长度/无截断、自然和强制模式不能混淆、实际固定输出必须相等、
独立事实卡cluster、对比方向/Bonferroni区间、原始HTTP与换卡/预热证据、trace重叠/未知scope不误归因。
每步验收后继续；提交前当前help/查重/完整命令与总GPU展示，create一次，code200+精确UUID。
结果两次独立进程重放一致，原产物SHA归档；阶段结束更新README/交接并推送私有origin。

## 准备验收

160项CPU回归、shell语法/diff检查通过；controller/patches/作者config/dev相对496ab11无变化。
数据精确512/1536输入和独立进程retokenize通过，96自然请求/48固定请求每预算、12独立事实卡。
私有数据`logs/diagnosis-data-20261108-a01/`；公开聚合`logs/diagnosis-public-20261108-a01/`；
准备日志`logs/diagnosis-prep-20261108-a01/`。dataset SHA=
`0d92ecbdd62cc57473fd97f692183013314f4d271ead9fa30e739fea8eab4b30`。
现有CLI3.3.11 help及凭据结构已核对，不输出凭据、不升级；尚未提交GPU。

## 唯一GPU提交a01（运行中）

- source pin=`629eb4268dcf49bed41e1266f0f159426dc7444a`；
  `logs/diagnosis-prep-20261108-a01/source.tar` SHA=
  `2411dcc0208573d3ab8af7203948374ebc5816884093bb580cafa9f199401a67`。
- 精确名查重total0，create一次返回code200/dataNone，按精确名唯一解析
  UUID=`job-89c6c8cd6c11-20261108200750`，name=`specpilot-diagnosis-20261108-a01`。
- 2026-11-08 12:08:18 UTC在node244启动。服务端2H100/256Gi、原digest、只读models、
  禁hostNetwork、toleration核对通过。项目WeaverDev，请求namespace/queue=qiji、实际queue=proj-31。
- 完整命令`logs/diagnosis-prep-20261108-a01/command.txt`，回执`submit.txt`与精确查询`lookup-after.txt`；
  模板`RUN/specpilot-diagnosis-20261108-a01/specpilot-diagnosis-20261108-a01.yaml`。
- 私有运行`logs/diagnosis-run-20261108-a01/`，agent只看公开a01聚合状态；
  生命周期`logs/diagnosis-prep-20261108-a01/lifecycle.*`。尚无科学验收，不重复create，不改运行代码。

## 正式计时完成；profile采集器修复（协议修订，仅辅助证据）

- 原任务Job Completed/Pod Succeeded/容器与脚本exit0，node244，12:08:18–17:34:34 UTC，
  5h26m16s；所有四条件/十二会话/二十四轮计时及前后null验收完成，原始证据不改、不重跑。
- 初次16个profile探针均JSONDecodeError。JSON-only NativeClient在解析非JSON成功响应前抛错，
  原始失败载荷未保存，不能凭异常猜出具体响应文本；OpenAPI schema和原失败记录保留。
  原1token代理仍有效；初次profile不能记为已获得阶段trace。
- 修复仅新增`exp/diagnosis_profile.py`独立ProfileClient：原生profile start/stop可接受JSON/纯文本，
  记录HTTP状态/content-type/原始字节base64与SHA；不修改controller.NativeClient或原计时源码。
  只在公开schema支持时开启detailed_annotations，未知scope仍不猜归因。
- 163回归通过；新增`diagnosis_profile_remote.sh`仅补采原定两轮fresh/换卡的profile探针，
  同一原始dataset/模型/引擎/46开关，不运行正式null/candidate测量。
  原始主报告仍由629eb42冻结源独立重放，修复profile另有source pin和单独报告，不能回填覆盖旧失败。
- 原计划一次提交因采集器错误修订为额外一次profile-only任务，**不是追加独立性能样本**。
  原任务已结束才提交；仍最多同时2GPU，补采最长1小时。
  原5h26m16s＋补采上限1小时（另有短初始化）仍小于原8小时/16GPU小时总预算，不扩大资源上限。
  新任务同skill当前help/唯一名查重/完整命令与2GPU展示/code200+UUID规则。
- 辅助EOS后延续和跨预算共同前缀审计只读原始输出、仅发布聚合，源SHA单独绑定；
  不改变三主要端点/样本/区间，也不把输出前缀相同当lossless证明。

### profile-only补采提交

- 当前help和精确名查重total0后create一次，code200/dataNone，精确唯一UUID=
  `job-72e589efab39-20261109014404`，name=`specpilot-diagnosis-profile-20261108-a01`。
  2026-11-08 17:44:24 UTC在node244启动（UUID日期是服务端+08时间，实验日期仍按UTC）。
- source pin=`74afcee9077baa7da7c60113673e8b7d34fa1e83`，profile-source.tar SHA=
  `095da269bae0ba8d647ed6c2d21d01914e43118e305f20ae0325482cd53955bf`；
  新私有`logs/diagnosis-profile-run-20261108-a01/`，新公开`logs/diagnosis-profile-public-20261108-a01/`。
- 服务端原digest/2H100/256Gi/禁hostNetwork/只读models已核对，项目WeaverDev，实际queue=proj-31。
  完整命令`logs/diagnosis-prep-20261108-a01/profile-command.txt`，回执`profile-submit.txt`，
  生命周期`profile-lifecycle.*`，模板`RUN/specpilot-diagnosis-profile-20261108-a01/`。
- 原正式result/replay-01/replay-02已逐字节一致，SHA=
  `f998dcadd38d07647256898d6719184f21d351bd3957847e48dd63de8183af4b`。
  补采开始有成功trace，尚待完整验收，不把原16失败翻成成功或合并新正式性能样本。
