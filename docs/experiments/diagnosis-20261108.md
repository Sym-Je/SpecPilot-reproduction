# 中文短答减速：匹配因素与执行阶段诊断

状态：用户已批准执行；先冻结协议和验收，未提交GPU。基准496ab11。

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
