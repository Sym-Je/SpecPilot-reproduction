# 冻结作者 final 的长上下文小样本检查

用户批准简化实验及新预算：8 H100 GPU小时／12小时／最多2卡，失败与冷启动计入。
沿用已确认镜像digest、WeaverDev/qiji、只读模型PVC、toleration及priority3；提交后核实际优先级。
不扫描N、不拆机制、不采profile、不运行研究agent，不读取旧私有题或sealed，不写晋升账本。

## 先行验收

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest harness.test_long_context harness.test_p3_pair_run harness.test_sampling_protocol
bash -n exp/long_context_remote.sh
git diff --check
```

反例：输入长度不足/重复请求/缺轮/未换卡/原始HTTP与计时结果不一致/输入被截断/改动源码或数据均拒绝。
验收前不提交GPU。运行结束独立重算两次，核终态、GPU费用、清理及原始产物SHA。

## 协议

- 3篇公开英文长篇小说（Gutenberg Moby Dick、War and Peace、Middlemarch），下载冻结SHA，
  不按性能选样；不重复文本凑长度。每篇取相同起点的逐渐增长前缀，问题固定为概括当前叙事。
  公共来源不代表作者或训练模型从未见过，结论仅适用于本次小说摘要负载。
- 实际输入含模板严格为2048/8192/32768/65536/131072 token，每档3请求，输出上限2048，
  greedy/top_k1、自然EOS、thinking开启。完整记录输入、输出长度与结束原因。
- 既有stock/final引擎与配置不改。两轮fresh server并互换物理GPU；每档先用首篇32-token预热，
  再对3篇正式测量；未就绪/容量不足/OOM保存原始证据，不能用截断后的短输入冒充该档。
- 复用controller HTTP计时与stats：主指标为输出token数/完整请求墙钟时间，包含prefill、decode及HTTP，
  不是纯decode TPS。输出不同则另列长度比、延迟比，不将二者等同；每请求两轮聚类后bootstrap。
  3篇样本的双侧95%CI仅作探索性描述，不是全域泛化或论文sealed数字复现。
- 测速后使用既有stock FP32-head scorer、AR生成和controller forcing规则检查实际输出。
  每长度/每轮独立标定；无首次分歧则δ未标定，容量不足或缺证据记unknown，不能拷贝旧δ或放宽规则。
  两轮逐token相等另报，但不代替forcing或lossless证明。
- 完整ceiling、各机制消融和最优N不是本阶段目标。原始文档/请求/输出仅保留logs，不发布到Git。

## 执行

阶段目录与唯一预算：`logs/long-context-20261111-a01/`。
代码身份、最终命令、任务UUID、验收、结果及公开同步回执在执行后追加。

- 32项指定CPU检查通过；三文档SHA和15条精确长度请求冻结，未复用旧私有题。
- 首任务`sp-longctx-20261111-a01`提交一次，code200，UUID`job-2c7803a11bbb-20261111122955`。
  源码基准`6f31e9f`，归档SHA`cafbe7fd6512e48f99f7dc49ed8b4d7011353e353b99426468b9a9cd37cd39c7`。
  实际Volcano queue=proj-31、Job.spec.priorityClassName=higher-priority-job、2 H100、7200秒。
  Pod自身priorityClassName为空；不把Job级调度优先级冒充Pod已设置同字段。
  提交、Running、模型就绪、计时与终态分别核对；前台监督TTY94560已正常退出，不再接续或重复提交。
  完整命令在阶段目录`final-command.txt`。

## 结果：2K–64K有收益，128K不可配对比较

| 输入token数 | stock输出TPS | final输出TPS | final/stock及双侧95%CI |
|---|---:|---:|---|
| 2048 | 136.976 | 294.151 | 2.147× [1.953, 2.336] |
| 8192 | 121.490 | 220.860 | 1.818× [1.731, 1.957] |
| 32768 | 99.988 | 153.335 | 1.534× [1.423, 1.677] |
| 65536 | 82.864 | 109.337 | 1.319× [1.280, 1.343] |
| 131072 | 不支持 | 仅32-token预检通过 | 无配对加速比或正确性结论 |

TPS为各档6个测量的几何平均，包含prefill和HTTP，不是纯decode速率。
每档3篇、每篇2轮，共24pair/48臂输出；请求cluster内先合并轮次，bootstrap 10000次、seed0。
每轮速度比：2K 2.15010/2.14483；8K 1.81835/1.81751；32K 1.52856/1.53854；64K 1.31169/1.32730。
2K stock/final平均输出1671.33/1722.67 token，分别4/6触顶，故TPS比不直接当延迟比；
其余三档两臂均实际2048 token、6/6触顶，结果仅覆盖该输出上限。

128K两轮stock原始HTTP400均明确：输入131072超过允许的113767 token。
没有OOM证据，不开启auto-truncate、不改启动配置来追求成功；final两轮同输入32-token预检均成功，
但未独立执行128K/2048-token正式生成，不能据此宣称该档吞吐/正确性或完整泛化已验证。

### 正确性和独立复核

- 所有48份测速输出、共94092个token绑定自身前缀，沿既有stock FP32-head controller forcing检查。
  4个长度×2轮全部通过rate/event规则，δ为实测0.125/0.125/0.25/0.125；无大margin事件。
  24个pair并非逐token相等；“检查通过”不是文本质量评估、逐位一致或数学上的lossless证明。
- 两次独立进程audit字节一致，与remote/result.json一致；另两次独立工程复核绑定预热原始响应、
  准确输入长度、实际启动参数、完整轮次/物理换卡、计时重算和forcing输出谱系。
  24组HTTP实际重叠，最大启动偏差4.38ms；引擎全树SHA重算与冻结stock/final一致。
- 32项指定CPU回归复跑通过，shell语法及diff检查通过；不宣称仓库全量或Ascend测试通过。
- 唯一任务Completed/exit0、无重启；北京时间2026-11-11 12:29:55创建、13:00:49结束。
  从创建至结束保守计3708 GPU秒=1.03 H100 GPU小时，0活动GPU，不结转余额。

**结论：**这3篇公开英文小说摘要负载上，冻结final在2K–64K仍有统计可见收益，但收益随上下文增长收窄；
不是“所有长上下文任务都泛化”，也没有验证论文长上下文收益或128K完整生成。
本次未做profile，不能据趋势断定Attention/GDN/接受长度等具体原因；不做参数适配或优化发现声明。
原始产物仅留阶段logs，归档及公开同步身份另以独立回执为准。

### 归档与发布索引

- 305个文件、235778452逻辑字节，完整SHA扫描两次通过。
- 清单`logs/long-context-evidence-20261111-a01.sha256`，
  SHA256=`75979015938cdae3dc70c12f407eb74aa364e44d48fbb11647f2ac1e052d44d6`；
  归档回执`logs/long-context-archive-20261111-a01.json`。发布回执不纳入自引用清单。
- 公开仅本项目执行器、合成测试和汇总文档；不发布小说原文、真实请求/输出、模型、原始日志或源码归档。
  保留旧ceiling未提交改动，不混入此阶段提交；controller/patches/eval/ledger/memory无改动。
- 最终公开审查与GitHub身份见`logs/long-context-publication-20261111-a01.json`，
  未取得该成功回执前，不将本地提交等同于远端同步完成。
- 发布副本首次CPU验收缺少`agents`源码依赖而失败；补齐同一基准提交的公开依赖后32项通过，
  原失败日志保留。这是发布测试副本准备问题，未改运行源码或重跑GPU。
