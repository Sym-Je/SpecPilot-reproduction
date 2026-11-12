# 原生Master独立方案评估

## 目标与授权

用户批准：让原生Master独立获取信息、比较验证长度、送验token/tree、kernel和端到端开销，
提出值得最小实验验证的方案。不指定链16、best-first或VERIFY为答案，不要求制造正结果。
本阶段只使用已有开发侧证据、公开调研和CPU分析，0GPU，不派Direction，不恢复旧实验或继承旧余额。

Master继承主助手实际权限；两类禁区仅prompt约束，沿用`agents/master_native.md`。
不给旧agent研究过程/方案，不提供作者final实现，不读取sealed、凭据或Ascend实验。
主助手负责资料来源、事后核对和发布，不替Master选择科学答案或实现优化。

## 先行验收与流程

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_master_native
$PY -B -m harness.master_native prepare --directory logs/master-native-study-20261112-a01
$PY -B -m harness.master_native check --directory logs/master-native-study-20261112-a01
```

1. 保存既有工作树与保护文件身份，建立有SHA来源的stock、profile、接受统计/上界、匹配计时和BBuf资料索引。
2. 新原生线程、不继承旧对话；Master自行阅读源码/文献、调用分析工具和编写CPU实验，不由主助手提供候选答案。
3. 比较四类机会，提交至少两项具体候选并排序；每项说明实际路径、依据、条件净收益/新增成本、正确性风险及最小证伪实验。
4. 收益估计必须对应同一工作量/分母；profile kernel累计时间不得直接当关键路径占比，接受上界不得写成已测提速。
5. 主助手独立复核所引用证据、公式和执行可行性。发现缺口交回同一Master自行修订，不代写科学方案。
6. 至少形成一个证据充分、修改路径明确、可执行验证的提案；若信息不足，明确哪些结论未建立，不硬凑赢家。
7. 事后对比controller/账本/列明规则并复核可得轨迹；归档实际研究产物，公开同步脱敏摘要和下一步。

## 判据边界

此阶段评价研究提案的质量，不认证候选正确性、实际收益、sealed、晋升或完整RSI。
不证明未读取禁区；仅prompt约束的科学隔离局限须保留。新增GPU采集需求另行明确资源方案，不能直接执行。

## Master实际完成的研究

原生Master从新线程自主读stock、获取公开文献、运行BBuf profiler/compute，编写并执行CPU分析。
维护者没有交付旧agent方案、指定科学答案或替它实现候选。原始报告、脚本、失败/修复和来源在阶段research目录。

- 分析10份stock trace，复算5290条有效接受路径；排除20个未提交in-flight步骤和18个不完整尾部。
- 单链Bellman选择自行实现，并用150个小例穷举核对；该自检只证明代理目标求解器，不证明概率标定或lossless。
- 主动发现BBuf启发式FP8/MoE标签与真实BF16/dense形状不符；未把工具标签当事实。
- 自行处理依赖、计数口径、路径和网页获取失败，区分工具错误、实现问题与假设被否定。

### 六项候选及取舍

| 排序 | 方案 | Master依据与边界 |
|---|---|---|
| K1 | 小M BF16 MLP gate/up投影专化 | 首选。真实M8/K5120/N34816形状及调用点明确，交叠少；先比较完整gate/up+SwiGLU算子对，不先改整套server。 |
| T1 | 有预算的draft tree | 次选。复用公开tree机制和既有条件回放；必须先验祖先/Conv/GDN/KV状态正确性，不能忽略hybrid状态成本。 |
| L1 | 先标定长度成本，再考虑动态长度 | 默认8不是运行上限证明；现有七层后续不能预测更深接受率，clipping也不等于真实短block。 |
| Q1 | 最大化预计前缀接受量的单链Bellman选择 | 本轮CPU实验T=1仅约+0.564%条件进度，T=2约-0.802%；新增成本与泛化均未知，降级。 |
| S1 | 跨draft/verify/accept的稳定graph岛 | 需要先证明因果enqueue间隙；不把profile空洞或请求级残差当每步可省开销。 |
| N1 | GDN输出归一化融合 | 累计work看似显著，但约93.64%的norm interval与其他kernel交叠，否定“全额节省work”的论据，不否定所有融合。 |

### 首选K1具体指什么

在stock的`Qwen2MoeMLP.forward`共享实现及`_bf16_gemm_dispatch_impl`接入默认stock的形状开关，
只针对BF16、TP1、M8/K5120/N34816评估Hopper小M调度/tile/K-split策略；该类名不意味着目标模型是MoE。
可选融合SiLU*up必须保留原BF16中间舍入边界，不混入量化或修改采样策略。

对应kernel家族累计work约22.742秒，占本批累计kernel work约30.31%，但**不是30%可获得的端到端收益**。
每次356.5MB权重、约123.72微秒，在假设3.35TB/s读权重模型下仅约14%局部时间空间；实际带宽/cache未知。
每次节省2/5/10微秒、按名义69次调用全额转移时，每步仅约省0.138/0.345/0.690毫秒，再扣新增成本。
这些是敏感性情景，不是实测提速或完整ceiling。

最小下一实验由Direction/Kernel角色设计执行：先比较真实stride的完整算子对、数值中间结果及warm graph依赖链，
再看完整step是否转移；只有候选存活才走既有controller验收。完整算子对无净收益、收益不转移或正确性失败即停止。
本轮未实现kernel、未提交GPU任务，不能宣称K1已有效。

## 独立复核与发布

维护者在独立副本重放CPU脚本，复核来源SHA、接受量聚合、shape/byte成本与原始trace区间；原生研究产物冻结不改。
首次复核使用不同Python版本，在严格逐值对比时发现约1e-14的work_fraction差异；失败原样保留，改用原解释器重放，未改科学判据。
最终数值复核、保护文件比较、归档与GitHub身份以本阶段独立review/postcheck/publication回执为准，不以模型自检代替独立复核。

最终6个CPU重放命令全部成功，6份科学分析输出在同一CPython3.10.12下逐值完全一致；原始research文件SHA未变。
另用独立分组重算5290行条件接受量、检查权重byte/时间模型，并用端点扫描独立核对首trace热点交叠。
53个外部来源文件及7份成功获取的公开资料内容SHA核对通过；首次跨版本复核失败保留，不将其改写成成功。
保护文件事后摘要未变，4项postcheck回归通过，原生Master已关闭。本阶段研究提案目标达成，只有最小证伪实验的依据成立。

公开仅同步本摘要与进度，不发布原始请求、trace、角色私有上下文或第三方源码。
本轮达成的是有依据的研究提案；真实性能、正确性、推广能力和完整RSI仍未在本阶段完成。
