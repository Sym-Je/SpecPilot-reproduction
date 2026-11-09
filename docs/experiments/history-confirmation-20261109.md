# 接受历史方向：独立证据可用性核查

日期：2026-11-09（北京时间）。基准`2ff1c4966fa6ed76be4109f96f19a138d90a0b84`。
用户批准：先核查已有独立dev计数记录，固定规则后CPU确认，交agent评估；无合格记录则报告最小采集方案。
本阶段不提交GPU、不实现候选、不改controller、不读取sealed/作者final实现/原题或生成内容。

## 预登记与停止条件

先核对持久归档校验索引及已公开匿名计数，不递归打开私有请求/输出。
只将有来源绑定、完整有序接受数量、两轮一致且未参与上一轮诊断的独立请求列为候选；
同轨迹重放、复制文件、GPU重复和暖机都不是新请求。文件存在本身不证明独立性或采集完整。
权限拒绝和索引未覆盖的范围显式保留，不把找不到推断为全仓库绝无数据。

若有合格记录，沿用T001固定的一步预测、整请求留一、首目标排除、训练专属均值/中位数及同suite常数，
逐请求等权报告；suite无训练数据显式回退。先冻结请求清单，不按预测好坏挑题或调参。
按上一轮agent设想，至少gsm8k/HumanEval各2个独立确认请求；不足则不启动确认性计算。
“每个请求均优于适用常数”仅作该固定规则的保守筛选，不是论文晋升门槛或普适策略否定判据。
已有3个诊断请求不重新包装成独立确认；不构造总体CI、加速比、净收益或泛化声明。

没有合格记录时，输出`insufficient_independent_records`，预测误差/净收益保持null，
只把核查证据交agent判定待测，并提出下一阶段最小采集范围、预算与验收；本阶段不采集。
终止方向仅核旧runtime/公开产物是否有入队及可靠终止信息与原生时间关联；顺序不是因果延迟。

## 先写验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
# inventory.py仅读校验目录清单和指定匿名计数，不打开私有内容。
CUDA_VISIBLE_DEVICES='' "$PY" -B logs/history-confirmation-20261109-a01/inventory.py
CUDA_VISIBLE_DEVICES='' "$PY" -B logs/history-confirmation-20261109-a01/inventory.py --check
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p13_observations harness.test_p13_exploration
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
git diff --exit-code 2ff1c49 -- controller orchestrator patches costmodel assets/upstream ledger memory agents exp harness
git diff --check
```

独立进程重放核查输出，测试复制文件不产生新请求、诊断数据不进入确认、缺数据不伪造MAE。
原始索引/计数/规则及实际agent输入输出绑定SHA；agent的等待结论不是优化发现。
若索引权限受限，只允许受控程序读取校验索引元数据，不手工读取受限题目/轨迹。

## 实际核查结果

- 核对22份历史归档SHA索引、35030个去重产物路径；只读取索引元数据和已公开匿名计数。
  原始私有流、题目、输出和token ID未打开；不是递归检查整个磁盘，也不涵盖未索引或未知格式的数据。
- 可识别的计数导出共3份，SHA均为
  `2e20499a50d739d0492ebffbf9e0635b21b738566c25cfd280c54b3f6c46a84a`，实际都是原3个诊断请求。
  两个observer JSONL来自原活动的两轮重复，没有新增候选流。副本/重复不增加独立请求数。
- 首次索引解析将合法`RUN/`任务YAML元数据错误拒绝，失败日志保留；仅读元数据的白名单修正后通过。
  普通权限初检还漏读1份受限索引，结果明确为`incomplete_catalog_access`；随后由受控程序仅读该类索引，
  22份全部覆盖，无权限漏项。没有打开YAML/私有流内容，不能以补齐索引宣称复验了所有原始产物。
- stock观测事件有发出`time_ns`，但没有任务入队/可靠终止信息可用时刻及无扰动关键路径。
  不能从这些时间戳推算终止取消收益，也不为终止方向另开采集。
- 清点输出`logs/history-confirmation-20261109-a01/inventory.json`，SHA=
  `969ae8c079400274501da0c152e61f69f32f238fa72a7dec53cb84f59f231ef4`；两个独立CLI重放字节一致。
  原规则在`protocol-frozen.md`保存，SHA=`124cdb17168ee22b114cbffc0c6a31109bbd5720e2094ef4d5e455a214849359`。

## 真实agent复核

继续原a02 master `01a1be6f-7dc6-7bc1-b02f-1aa5691d1688`，没有换agent追求通过。
仅给inline清点摘要；原agent没有重新读取文件，结论依据外部broker证据，不冒充独立文件检查。
实际resume/send/completion/close回执、精确输入与原始响应均保存于本阶段日志目录。
响应SHA=`1f9d77728195da021f4c434607b76231cd5941e828c7f070e3d6e5697e10036e`（含存档末尾换行）。

agent决定为`needs_independent_collection`：缺独立记录，不是固定规则已证伪。
`independent_confirmation_run=false`、`confirmation_mae=null`、`end_to_end_gain=null`、`implementation_ready=false`。
没有重算旧3题当新验证；没有独立预测数字、总体泛化、加速、lossless、实现或晋升结论。
继承默认模型，精确模型ID和token用量仍不可得；客户端回执不是后端签名或物理隔离证明。角色已关闭。

## 最小采集建议（未执行、待下一阶段批准）

1. 在授权dev池中排除原3题、输入重复及别名；按固定哈希排序取GSM8K/HumanEval各2个新请求。
   broker事先冻结清单、顺序、seed与有效性处理；不手工看题、不按预测表现/接受率/长度选题。
2. 沿用stock/block8/greedy/2048cap/自然EOS和已验收默认关闭只读观测副本，记录完整提交接受链。
   原题/token级重放数据仍由受控程序私有保管，模型只接收匿名计数与聚合；原生输出绑定和线性重放必须通过。
3. agent原建议一轮最省资源，但与现有`history_screen`强制两轮一致的契约不符。
   broker建议两次fresh server采集全部4题，两轮合并为4个独立样本；不为省资源修改现有验收器。
   两轮不一致/链缺失则保留缺口、停止确认，不靠删异常或补跑挑绿。
4. 仅采stock计数不比较方案性能，建议1张H100、总上限30 GPU分钟，含两次启动/预热/采集；
   这是待批停止预算，不是耗时保证。**不是单卡串行A/B，不报告配对性能或写ledger**。
   任何未来性能判断仍必须走controller双卡配对/换卡。本次没有提交NorthJob。
5. 仅用4新请求沿用T001留一/训练专属基线，逐请求与等权报告；不混入旧3题拟合基线，不调参。
   最多支持初步筛选；规则未通过则停止该固定规则路线，不外推为所有历史策略无效。
   即使通过，也不能直接实现预算策略或宣称净收益；仍缺预算映射、完整生成及开销证据。

落地采集需新的外围runner/受控导出适配：当前入口固定选旧3题，不能直接换标签复用，也不能放宽两轮契约。
这些实现、执行版本冻结和NorthJob参数核对均留待下一阶段授权；不改controller/eval或既有观测机制。

## 验收与当前决策

14项定向与224项CPU回归通过，清点两独立重放、实际agent输入/回执/响应绑定通过；
清点编辑、伪造确认MAE、编辑prompt三类工程完整性故障均拒绝。不是论文token-forcing验收。
完整验收入口`logs/history-confirmation-20261109-a01/acceptance.sh`。
日志中的stock/final速率来自CPU测试fixture，不是本阶段GPU性能测量。
新增32个归档文件/121237逻辑字节全部SHA通过；清单`logs/history-confirmation-20261109-a01.sha256`，
清单SHA=`407ee5796497a3d3d66fb850ce31ee23d205def388467cb85eccfef9d9107443`，
摘要`logs/history-confirmation-20261109-a01.summary.json`，复核日志`logs/history-confirmation-verification-20261109-a01.log`。
清点程序SHA=`9d128b9b9061b0684f76617d0a0f6b58fea592cc9e9dbf4d25ccf446c2bd9d6b`；
本地审计程序/回执/失败与成功日志一起入清单持久保存，Git记录协议、运行基准与证据身份。
本阶段只新增协议/报告及ignored审计产物；运行源码和所有保护目录不变，0GPU、无运行模型角色。

**决策：可用性核查已完成，独立确认因缺合格记录尚未执行。** 下一阶段须先批准最小采集方案，不自动继续。
