# final 反例独立确认

状态：执行、质量、两次独立重放、证据归档完成；中文性能反例确认，摘要/代码退化证据不足。基准提交36166c7。

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

### 唯一GPU提交a01（当时运行中，现已结束）

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

### GPU完成与CPU质量适配

- GPU最终Job Completed/Pod Succeeded，容器与脚本exit0，08:41:27–10:49:13 UTC（2h7m46s）；
  255生命周期快照只见一个Pod UID、容器restart0，Job retryCount字段未设置。
  两卡均0MiB，利用率0/1%，端口已释放。两条件/四轮全局forcing均通过，新δ均0.25，零大margin事件。
- 初次本机质量完成器失败于中文参考类型：60题共180参考中179个str、1个有限float；
  前审计20中文题60参考全str。只查看类型计数，没有查看题目/参考值/输出。
  原本机失败log、partial quality、controls和全部GPU原始产物保留，不覆盖。
- 新CPU评测器只把含非字符串参考的中文题辅助质量标为缺测，不猜测/强转答案，
  **全部60中文性能题和全部160题forcing仍保留**。摘要/代码主要端点不允许缺测。
  不换样、不重测GPU、不改阈值或controller。三主要端点、同时区间方法不变。
- CPU修复独立冻结源码pin/tar，与GPU执行pin分开记录；新评测目录
  `logs/confirmation-evaluation-20261108-a01/`。验收绑定原GPU源/数据SHA、验证controller逐文件相同，
  从原生测速输出重做质量并独立复验；源archive及失败路径都归档。

## 最终结论

**final并非普适加速：中文短回答减速在独立60新题上再次确认。**
摘要/代码未独立确认质量下降，但不等于已证明质量非劣，更不能排除所有reward hacking。
不据此指控作者故意reward hack；当前证据说明工作负载适用边界，不是因果根因或意图。

### 三个预声明主要端点

下表区间为三端点Bonferroni同时区间，每端点双侧98.333333%，不是逐项普通95%。
两物理轮先在题内聚合；独立样本分别60/60/40，不是120/120/80。

| 端点 | 点估计 | 同时区间 | 结论 |
|---|---:|---|---|
| 中文请求延迟比stock/final | 0.539657× | [0.504294,0.577406] | **性能反例确认**，final几何平均耗时约stock的1.853倍 |
| 人工参考摘要ROUGE-L，final-stock | -0.002707 | [-0.010846,0.004635] | 证据不足，未独立确认下降，也未证明非劣 |
| 4096代码通过率，final-stock | +0.050000 | [-0.050000,0.175000] | 证据不足，未独立确认下降，也未证明非劣 |

摘要stock/final ROUGE-L=0.259538/0.256830，均值差约-0.27个百分点；
这里使用DialogSum人工参考，而旧告警来自Alpaca合成参考，**不能用本轮跨源结果推翻旧告警**。
未做可靠语义盲评，ROUGE-L只反映参考重叠。代码平均通过率82.5%/87.5%，
区间仍容许下降5个百分点，不能以点估计提高5点宣布非劣或提高。

### 配对性能与实际输出（普通95%区间，诊断端点）

| 工作负载 | final/stock token速率 | 完整请求延迟比stock/final | stock/final平均实际输出token |
|---|---|---|---|
| 中文60，2048cap | 0.548305 [0.519685,0.577294] | 0.539657 [0.510465,0.570354] | 76.267 / 77.533 |
| 摘要60，2048cap | 1.955279 [1.910993,1.999918] | 1.885706 [1.808570,1.957133] | 214.300 / 242.333 |
| 代码40，4096cap | 2.183044 [2.115854,2.264086] | 2.167079 [1.936085,2.435396] | 1151.100 / 1125.150 |

中文两轮延迟比分别0.540145/0.539170，stock/final平均请求延迟0.450282/0.857574秒；
每臂120轮次输出全部自然EOS。输出长度只差约1.7%，不能解释近一倍的耗时差。
摘要每臂120轮次输出也全部自然EOS。代码stock80轮次输出72stop/8length，
final76stop/4length；完整FP32评分与代码质量均涵盖触顶结果，没有删掉失败/长输出。
尚未隔离输入长度、短答固定开销、prefill、语言和接受率，不断言“中文本身导致减速”。

中文辅助质量F1仅59题可评：stock0.943936/final0.934269，普通95%差区间
[-0.030508,0.001507]。1题参考类型异常已标缺测；60题测速和全部forcing未删。
这是辅助指标，不替换三主要端点，也不作为语义非劣证据。

### 正确性、噪声与完整性

- 2048/4096cap各前后null都计入，noise分别0.6597425%/0.4177801%；
  不挑会话、不要求CI覆盖1或全宽0.2%。中文减速幅度远大于这些null尺度。
- 两条件各两轮新δ均0.25：每轮stock mismatch112/17434、368/46044；
  final119/19192、369/45006；全局和中文/摘要/代码局部rate/event均通过，零大margin事件。
  既有forcing规则通过不是数学lossless或语义质量非劣证明。
- 6会话/12轮fresh双server/物理换卡；960正式pair/1920臂行、960全尺度预热pair、24短预热pair。
  实际候选640条输出及新AR160条，共800条完整FP32 own-prefix评分；独立checkpoint head预检通过。
- 148项最终CPU回归、shell语法与diff检查通过；controller/patches/作者config/dev相对36166c7无变化。
  原泛化审计10312文件SHA重新核验全过。未sealed、未RSI、未写ledger/memory，无晋升。

### CPU版本、重放与归档

- GPU执行源始终65364f55ae0d367438f11efaa1c06332c2ebc717，运行中只做文档提交1437112。
  CPU评测器独立pin=`bb5b8fbcdf1bc1da32ddb474b12af9d8c57702ff`，
  `logs/confirmation-prep-20261108-a01/evaluator.tar` SHA=
  `631d8a4c222c6e9bd20937e14819fdbd77c28956d7d4a29a61ac9e0f30ad9678`。
  两个源pin明确分离，GPU原始产物/旧partial quality保持原样。
- 第一次修复完成器在创建评测目录前发现sudo PATH无git，原失败log保留；
  仅进程PATH加入`/gpfs/users/jixinpeng/.local/bin`及指定仓库safe.directory后执行，
  没改全局配置/系统权限或代码。最终11:10:49 UTC统一验收完成。
- 两个独立CPU进程从冻结源/原始HTTP/评分/质量重新验收；result.json与replay-01/02.json
  **逐字节相同**，三份SHA=
  `b07cf371ca03c20bc66b844fe7048e9f12a9e28a045af46b6d2f772bc6657c77`。
- 所有成功/准备失败/CPU失败、源档案、数据来源和生命周期证据共5928文件/272733966字节；
  清单`logs/confirmation-evidence-20261108-a01.sha256`，SHA=
  `29bfb790646ab81cfcab9035071d904a96cfa82fb66ada6be9238f4923bfebbf`，逐文件核验全过。
  核验日志`logs/confirmation-evidence-verification-20261108-a01.log`。
- GPU最终结束08:41:27–10:49:13 UTC，2h7m46s，观测单Pod/restart0；
  Job retryCount字段未设置，不伪称服务端明确0。两H100显存0MiB，最后遥测利用率0/1%，端口释放。
- 所有前台GPU监控/本机质量/重放进程均结束。没有新GPU重提或最终实现修改；
  不因结果追加样本/追绿。下一大阶段须先报计划并获用户允许。

复核命令（从CPU冻结源运行，显式CUDA不可见，输出必须使用新路径）：

```bash
sudo -n bash -c 'cd /gpfs/users/jixinpeng/SpecDec/SpecPilot; source harness/sglang/env.sh; CUDA_VISIBLE_DEVICES="" "$SP_PY" -B exp/confirmation.py audit --private /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/confirmation-run-20261108-a01 --quality-root /gpfs/users/jixinpeng/SpecDec/SpecPilot/logs/confirmation-evaluation-20261108-a01 --out /tmp/confirmation-replay-NEW.json'
```

不要再次运行finalize（只增不覆盖），不要手工查看私有题目/答案/逐题输出。
agent仅读公开`logs/confirmation-public-20261108-a02/`聚合汇总。
