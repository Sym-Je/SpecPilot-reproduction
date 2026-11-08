# final 反例独立确认

状态：用户批准执行；协议在取样和新性能结果之前冻结。基准提交36166c7。

## 目标与边界

固定作者final、stock、46开关、controller和既有paper-aligned-v1规则。
确认中文问答减速、摘要代理分数下降和长代码失败是否在新题上复现。
不读已有sealed，不写ledger/memory，不进入RSI，不以未显著证明非劣。

## 预声明协议

- 中文CMRC2018新60题、摘要DialogSum新60题、HumanEval新40题。
  排除作者全部100条dev、上轮全部200题的源ID（同源时）和规范化/近重复提示；
  新集内部也去重。固定seed=261102501-confirmation-v1，各领域输入长度半区等额抽样。
- 摘要改用DialogSum人工参考，以减少上轮Alpaca合成参考的局限。
  test集三份人工参考中固定使用summary1，不依据模型输出选择参考。
  **不同数据源的无退化不能推翻旧Alpaca上的下降，也不能把差异归因于参考质量。**
  这是外部质量告警复核，而不是同分布严格重复；ROUGE-L仍不是语义裁判。
- 主条件2048cap只运行中文与摘要120题；代码40题独立4096cap。自然EOS、thinking、greedy、top_k1。
  每条件null-pre → stock/final → null-post，各两轮fresh双server、物理换卡。
  短预热2题32cap，再全条件全尺度预热；保留所有null、失败、原始HTTP和遥测。
- 主要端点恰好3个：中文请求延迟比stock/final；摘要ROUGE-L的final-stock均值差；
  代码测试通过率的final-stock均值差。同题两物理轮平均后才计一个独立cluster。
  使用既有controller.stats bootstrap，报告普通95%区间及Bonferroni同时区间
  （每端点双侧98.333333%）；仅同时区间完全低于1/0时称相应反例得到确认。
  区间跨界称证据不足，不写“问题消失”或“质量非劣”。未设最小效应量/非劣界。
- 其余吞吐、输入分层、输出长度、EOS/截断、各轮结果为诊断；不据它们替换主要端点。
  生成长度上限不是实际输出长度，不把跨卡重复当新题。
- 全部实际stock/final输出完整FP32 own-prefix评分；每条件新AR标定δ与stock mismatch；
  使用既有correctness规则，局部无首分歧即证据不足，不套旧δ。语义质量不代替forcing。
- agent不看题目、答案和逐题输出；受控执行器读取私有数据，只发布汇总。
  本机Landlock/seccomp安全隔离执行代码，不在远程无沙箱运行。
- 一次1节点×2 H100、256Gi，沿用已确认digest镜像和WeaverDev/qiji；
  最长8小时（最多16GPU小时），不因结果不好扩样/改final/更换样本。

## 先写验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p8_confirmation.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235678]*.py'
bash -n exp/confirmation_remote.sh
git diff --check
git diff --exit-code 36166c7 -- controller patches assets/upstream
```

先红后绿覆盖旧集排除、固定seed、长度分层、条件划分、独立cluster、同时区间、
缺轮/篡改SHA/缺质量/假换卡拒绝。数据独立retokenize、源SHA、40参考代码验收后才提交GPU。
提交前当前CLI help、精确名查重、完整命令/2GPU展示；一次create并核对code200+UUID。
执行成功不等于科学验收；本机质量完成后从冻结源码独立重放两次并核对逐字节一致，原证据SHA归档。

## 执行记录

准备a01在抽样前因DialogSum test schema为summary1/2/3而非summary停止；
仅查看500行的字段名聚合，未查看题目/答案。schema红测试后适配固定summary1，
失败目录和日志保留；a02重新准备，不曾启动GPU或产生性能结果。

a02准备及独立复验通过：160题，作者100dev与前审计200题排除，独立retokenize、源SHA、
40参考代码隔离执行均通过；146项CPU回归通过。数据目录`logs/confirmation-data-20261108-a02/`，
公开聚合`logs/confirmation-public-20261108-a02/`，准备日志`logs/confirmation-prep-20261108-a01/`。
dataset SHA=`03f72f87aa3422197de540838fc9a7ae2f1494415e97e9a4ed5e13ce4f786e2e`。
输入中文250–824、摘要129–1006、代码104–468token，长度分层仅相对，不是长上下文验证。
DialogSum revision=`848cc8c05e0a04def79326539de827f1b28786a0`，固定summary1，
CMRC/HumanEval复用逐文件SHA验证的上轮同revision官方源。未查看样本/答案/逐题输出。

### 唯一GPU提交a01（运行中）

- source pin=`65364f55ae0d367438f11efaa1c06332c2ebc717`，源档案
  `logs/confirmation-prep-20261108-a01/source.tar`，SHA256=
  `ac85e3ca050e50a614ceb4f840e7023dcebb1d7a0932bf1bec67d84de371328b`。
- 当前CLI3.3.11 help已核对；凭据结构有效但不输出。精确名查重total0，create一次返回code200/dataNone，
  精确名`specpilot-confirmation-20261108-a01`唯一解析UUID=`job-a99898c2f332-20261108164059`。
- 2026-11-08 08:41:27 UTC容器在node208启动；服务端镜像、2H100/256Gi、禁hostNetwork、
  模型只读挂载、toleration均验收。项目WeaverDev、请求namespace/queue=qiji、实际queue=proj-31。
- 完整提交命令与回执`logs/confirmation-prep-20261108-a01/command.txt`、`submit.txt`，
  生成模板`RUN/specpilot-confirmation-20261108-a01/specpilot-confirmation-20261108-a01.yaml`。
  私有运行`logs/confirmation-run-20261108-a01/`，agent只看公开a02聚合状态；
  生命周期监控`logs/confirmation-prep-20261108-a01/lifecycle.*`。
- 当前仅确认提交和进程启动，尚无科学验收结果。不要重复create或修改运行代码。
  结束后本机隔离质量、独立重放两次、原始证据校验，结果按预声明规则报告。
