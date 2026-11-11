# 作者公开原题的干扰前缀长度实验

用户批准执行；新资源8 H100 GPU小时／最长12小时／最多2卡，失败/冷启动计入，不结转旧余额。
镜像digest、WeaverDev/qiji、既有只读模型PVC、toleration和priority3已重新确认。
这是冻结作者产物的控制实验，不是自主研究、sealed、论文数字复现或晋升。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest harness.test_prefix_context harness.test_long_context harness.test_p3_pair_run harness.test_sampling_protocol
bash -n exp/long_context_remote.sh
git diff --check
```

验收反例：原题或回答模板改变、原始对照与作者token不一致、前缀重复凑长度、缺题/缺轮/假换卡、
输入截断、原始HTTP与输出/计时不一致均拒绝。旧长文原始证据用更新的通用入口重算，必须保持结果相同。
参考代码先在既有CPU隔离器通过；生成代码只在本机同一隔离器评估，不在GPU容器执行。

## 冻结协议

- 固定五套公开dev各前2题，共10题，不按结果选题。原题文本和采样模板保持作者原样，greedy/top_k1、thinking开启。
- 同10题执行original对照，以及完整输入精确2048/8192/32768/65536 token；输出cap2048、自然EOS。
  每题按自身ID SHA确定一篇公开Gutenberg小说，所有长度都从同一文档起点截取增长的真实前缀，
  不重复字符/段落。前缀与原题以固定分隔符隔开，不额外加入“忽略干扰”提示或重写原题。
- 复用上阶段双卡stock/final计时、两轮fresh/物理换卡、各条件32-token预热和既有controller forcing。
  只改变输入；不调N、不改作者代码、不采profile，不读其他研究角色上下文或私有题。
- TPS含prefill与HTTP，不称纯decode；每题两轮聚类、每suite等权、10000次bootstrap/seed0。
  各suite只有2题，CI仅作探索性描述；不能据此证明全域泛化或正式质量非劣。
- 数学答案作规范化/boxed数值代理，代码使用公开测试及通过的参考实现控制；未结束thinking记未作答。
  MT-Bench无独立语义裁判，只报告是否作答，不编造语义分数。任务分数与token forcing分别报告。
- 无本机δ标定、容量不足、缺证据均为unknown，不套旧δ或放宽规则，不写ledger/memory。

唯一阶段目录`logs/prefix-context-20261111-a01/`。提交前查重并显示完整命令/总GPU，提交后分别核code200、
UUID、启动、Job优先级及最终结果。其他工作区既有dirty和其他阶段预算不动，原始文本/请求/输出不发布Git。

## 执行记录

- 39项指定CPU检查通过，旧长文协议结果重算完全一致；10原题token与suffix独立复核通过。
  原始长度为68–259 token；4份公开代码参考解在既有CPU隔离器通过。
- 基准`e2d4fa2`，实际源码归档SHA256=`13a9efaf293ba948f11ae0cf4bf93851f09baee4b51d2b6958fc9b6cbfa8a482`。
- 单次create返回code200，UUID`job-f6a47ae23f69-20261111132726`；2 H100、7200秒，
  实际Job.spec.priorityClassName=higher-priority-job、queue=proj-31。提交不等于科学通过。
- 前台监督TTY40558，最终命令`logs/prefix-context-20261111-a01/final-command.txt`；不重复提交。

## 结果

同10道原题、原始模板不变，5条件×2轮，共100pair/200臂输出；输入长度含完整模板。

| 条件 | stock输出TPS | final输出TPS | final/stock | 双侧95%CI |
|---|---:|---:|---:|---|
| original，68–259 token | 193.887 | 422.554 | 2.179× | [2.111, 2.250] |
| 2048 token | 185.106 | 375.465 | 2.028× | [2.001, 2.057] |
| 8192 token | 154.003 | 299.470 | 1.945× | [1.772, 2.134] |
| 32768 token | 110.461 | 161.521 | 1.462× | [1.400, 1.527] |
| 65536 token | 77.613 | 90.307 | 1.164× | [1.096, 1.235] |

输出TPS为完整请求输出token数/墙钟时间，包含prefill和HTTP，不是纯decode；
各suite先对每题两轮log比求平均，再几何平均/等权聚合，bootstrap 10000次/seed0。
每suite仅2题，CI是固定样本/固定前缀的探索性描述，不覆盖所有干扰文本、任务或硬件。

### 逐suite及反例

| suite | original | 2K | 8K | 32K | 64K |
|---|---:|---:|---:|---:|---:|
| GSM8K | 1.913 | 1.941 | 1.594 | 1.211 | 1.040 |
| MATH500 | 2.344 | 1.952 | 1.699 | 1.439 | 1.232 |
| HumanEval | 2.303 | 2.068 | 1.899 | 1.385 | 1.203 |
| MBPP | 2.140 | 2.117 | 2.840 | 1.841 | 1.275 |
| MT-Bench | 2.225 | 2.070 | 1.903 | 1.504 | 1.085 |

逐题不是全部提速：64K的`mt-bench-63`两轮聚合吞吐比0.8709×；其余条件无逐题聚合吞吐比小于1。
该题两臂平均输出1226/709 token，stock/final延迟比为1.506×，因此不能把吞吐下降说成请求延迟变长。
全样本不同条件的stock/final平均输出分别为1174.90/1144.15、1063.40/1126.10、1379.50/1244.00、
1262.90/1231.30、1272.10/1186.40 token，已保存触顶/EOS信息，不把不同长度输出的指标混同。

### 正确性与质量分别报告

- 所有200份实际测速输出、241695 token均绑定自身前缀，由既有FP32-head scorer及controller forcing评估。
  5条件×2轮rate/event判据全部通过，无大margin事件；不是逐token相等或数学上的lossless证明。
- 公开答案/代码质量代理独立在本机CPU执行两次，回执完全一致。每条件两臂原始代理分数均为4/8，
  GSM8K与HumanEval各2题通过，MATH500与MBPP代理未通过；部分输出因2048上限未完成回答。
  MT-Bench两题无独立语义裁判，不报语义正确率。物理重复轮不是新增独立题。
- **已发现代理盲点：**MATH500一题的数学下标格式被既有数值归一器误读，
  等价记号可能被计作不匹配。证据在`quality-limitations.json`；原始分数保留，不事后改分或修改controller。
  因此4/8不能当真实准确率，更不能以相同分数证明质量完全不变或非劣；本阶段没有完成全面语义质量验证。

### 独立验收和资源

- audit两次、独立工程复核两次、质量评估两次均一致；100组HTTP实际重叠，最大启动偏差4.34ms。
  原题与冻结公开dev逐字核对，预热/完整长度/原始HTTP/双卡换卡/实际启动参数/forcing谱系均通过。
  stock/final整树SHA重算与冻结身份一致；本次未修改作者实现、controller或阈值。
- 本机及冻结公开源码副本39项指定CPU回归通过，旧长文结果重算不变，4份代码参考解隔离测试通过。
- 唯一任务Completed/exit0，无重启；北京时间2026-11-11 13:27:26创建、14:26:28结束。
  从创建至结束保守计7084 GPU秒=1.96778 H100 GPU小时；本阶段活动GPU为0，不结转余额。

**结论：**固定原题、增加真实无关背景后，本次样本整体收益保留到64K，但由约2.18×收窄至1.16×；
并非每题吞吐都提升。它支持“固定原任务的长度干扰下仍有总体收益”，不能代替真实长文理解、
未见任务泛化、语义质量非劣、sealed或完整RSI；没有profile，不能据趋势断定具体瓶颈原因。

## 归档与公开同步

- 892文件、693662807逻辑字节，完整SHA扫描两次通过；
  清单`logs/prefix-context-evidence-20261111-a01.sha256`，
  SHA256=`88425f45d9af3e2574dc41b8d6f75a865fa59b76fd1b32301eb223761a2e567f`。
- 归档回执`logs/prefix-context-archive-20261111-a01.json`；提交/推送身份见独立
  `logs/prefix-context-publication-20261111-a01.json`，不把发布回执纳入自引用清单。
- 公开仅本项目执行器、合成测试和聚合报告，不发布真实请求/输出、小说原文、原始日志、模型或源码归档。
  不修改或混入其他Master阶段和旧ceiling变更；controller/eval/ledger/patches/memory无本阶段修改。
