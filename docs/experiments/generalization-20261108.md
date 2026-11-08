# 作者 final 新数据泛化审计

日期：2026-11-08 UTC；用户已批准执行，阶段内自主安排。状态：准备，尚无新测量。
基准：e12537cd213c74b4d1dea2f1677a82ea8bf6ab12。

## 目标及不变边界

检查冻结的作者 final 是否对新请求仍有收益，而非只适配已测30条dev。
不修改 final/stock、46开关、controller裁判或门槛；不读取现有sealed，不晋升、不写ledger/memory。
本审计是额外的公开数据外部确认，不冒充论文原sealed或自主发现。
公开数据可能存在于预训练或作者其他实验中，不能声称作者绝对未见，更不能彻底排除reward hacking。

## 揭盲前协议

- 原五领域 gsm8k/math500/humaneval/mbpp/mt-bench 各20条新题（ID100），
  新五领域中文阅读问答/科学问答/摘要/JSON答案抽取/普通对话各20（OOD100）。
- 来源使用公开上游数据的固定revision和文件SHA；不读取样本决定选哪个数据源。
  优先官方仓库；下载/许可/结构不可用时仅在生成前更正来源并记录，不依据性能换数据。
- 排除作者全部100条dev：源ID、规范化问题完全一致或字符5-gram Jaccard>=0.8均排除；
  新集合内部同样去重。固定seed=261102501，按SHA排序确定性抽样。
- 每领域按输入token排序分短/长半区，各抽10；提前选各半区2条共4条/领域，组成固定40题长度面板。
  主集200题cap2048；面板额外cap256、4096，2048结果复用主集。自然EOS，thinking/turn0/greedy/top_k1。
  短/长是领域内相对分层，不保证绝对长上下文；只接受prompt<=8192token，不裁剪提示。
- 每个cap独立执行null-pre→stock/final→null-post，各两轮fresh双server/物理换卡；
  2条32cap短预热+该条件全集全尺度预热。时序、原始HTTP、GPU/CPU遥测均保存。
- 所有实际测速stock/final输出完整FP32 own-prefix forcing；每cap新AR用于δ与stock mismatch标定。
  总体及各领域分别判定；无首分歧则δ未标定、判证据不足，不套旧值。
- 两物理轮次是同一题cluster，跨cap也是同一题，不把重复当新样本。
  几何均值和双侧95%CI调用既有controller.stats，领域等权；null取前后所有端点最大偏离。
  既有paper-aligned-v1收益/forcing规则不变。逐领域区间为未校正探索性区间；
  不根据“有几个领域显著”声称所有领域总体成立，不作多重比较后的确认性结论。
- 除tok/s，报告stock延迟/final延迟、输出长度比、EOS/截断/失败、各轮和输入长度分层。
  “有收益”与“仍约2.2倍”分开：后者仅描述点估计/区间，不新增追绿门槛。
- 任务质量：数学最终答案规范化匹配（代理）；代码测试在Landlock+seccomp+资源限额独立进程；
  中文/科学问答及JSON抽取exact/F1，摘要ROUGE-L代理。MT/普通对话无可靠语义裁判，明确未评估；
  未结束thinking/空最终答案按未作答，不能以thinking中的答案充通过。任务分数不能代替forcing。
- 一次性盲审：执行器读取私有输入/原始输出；agent只看无题目、无答案、无逐题结果的汇总。
  私有数据位于忽略的logs专用目录，0700/0600，既有sealed完全不访问。
  同UID的约定隔离不是独立第三方保密证明。结果后若修改final，此集转dev，另取新确认集。
- 一次1节点×2 H100/256Gi任务，沿用已确认镜像和WeaverDev/qiji，最长8小时（16 GPU小时）；
  完整执行/科学通过分别记录；超时/缺项不自动扩预算、不重抽题。完整原始证据及失败持久保存。

## 先写验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p7_*.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[23567]*.py'
bash -n exp/generalization_remote.sh
git diff --check
git diff --exit-code e12537c -- controller patches assets/upstream
```

CPU反例先红后绿：全部100题排除/近重复/确定性抽样、输入分层与固定面板、独立cluster、
质量提取/错误代码/秘密读取/网络/子进程/无限循环被阻断、原始证据/缺轮/假换卡/缺预热拒绝。
实际任务后从原始产物独立重放两次，验原始HTTP/计时/forcing绑定、身份与SHA；
agent只读取聚合汇总。失败/证据不足不翻绿，结果不写晋升账本。

## 执行记录

尚未提交GPU。准备阶段a01/a02均在抽样前下载失败，原日志/下载保留：
HF TLS不可达，改官方GitHub固定revision；prm800k用Git LFS pointer核验内容；
OpenBookQA仓库无数据文件，改官方2018档案（SHA256
82368cf05df2e3b309c17d162e10b888b4d768fad6e171e0a041954c8553be46）。
Dolly官方GitHub不含数据且HF不可达，摘要/普通对话改官方Stanford Alpaca固定revision；
摘要参考为合成参考、ROUGE-L仅代理，对话为无额外输入的普通指令首轮，不声称多轮泛化。
上述变更均早于抽样和任何性能结果；未因测量表现换源。
最终revision、抽样SHA、源码pin、完整命令/UUID和结果待执行后追加。

### 已通过的提交前验收

- a03下载已全部成功，但CMRC官方文件采用list/context_text/query_text结构，与SQuAD不同；
  抽样活动在完成前停止，无任何性能结果。加schema红测试再修复adapter，a04复用逐文件SHA核验的原始源，
  不改seed，不重新选取表现好的题；全部准备失败日志保留。
- a04准备完成，200题/10领域各20，固定40题/领域4题；全部100条作者dev与集合内规范化/近重复校验通过，
  独立retokenize一致，源文件SHA全部通过；40/40代码参考解在隔离器内通过。
- 数据SHA256=`7c179e5d0f84fb87b0ebcdb78a70248f15c01e51d9668ee1b72da5cdcb514486`。
  私有输入`logs/generalization-data-20261108-a04/`；只读聚合准备/状态`logs/generalization-public-20261108-a04/`。
  原始下载版本/文件SHA见该公开状态目录`preparation.json`，包含9个公开来源、9个固定文件，
  该manifest SHA256=`b78a4ba47c446e8c5490b3d4c9372ab87fa8358d5bb28b1a7eb875e380f07eaa`。
  许可标签为来源仓库/数据发布说明索引，不以代码许可证替代数据条款；不在Git再分发原始题目/答案。
- 实际prompt为59–636 token；短/长仅为领域内相对分层，**不覆盖真正长上下文**。
  长度面板比较同40题，2048点复用主集对应题，不把不同题总体误当长度因果对照。
- 新旧136项CPU回归通过，包括真实HTTP合成集成、缺预热/假换卡/原始HTTP篡改被拒；
  代码隔离使用Landlock+seccomp只读openat/禁网络/禁子进程/限额，参考解和恶意反例均测试。
  同进程代码任务测试是功能代理，不是针对有意伪造测试完成标记的恶意代码的形式化正确性证明。
- controller、patches、作者配置/原dev文件未修改；原始产物不提交Git。
  CLI当前help四个调度参数可用，凭据仅验证结构；2 H100、最长8小时/16GPU小时预算，任务名查重待核对。
