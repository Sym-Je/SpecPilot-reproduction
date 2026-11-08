# HANDOFF — 交接给新 session

> 本文件是**唯一的入口**。新 session 读这里，不要试图读旧对话。
> 最后更新：2026-11-08 UTC（200题泛化审计a02已启动，运行中；a01无测量失败保留，尚无新泛化结论）。

## 最新接续点：执行作者final外部数据泛化审计

- 新唯一阶段记录`docs/experiments/generalization-20261108.md`。用户已批准实际运行，阶段内自主；
  不修改final/stock/46开关/controller，不读取现有sealed，不写ledger/memory，不RSI。
- 200条新题：原5领域各20（ID100）＋中文QA/科学QA/摘要/JSON抽取/普通指令各20（OOD100）。
  排除作者全部100条dev与内部近重复，独立retokenize/源SHA及40代码参考解验收通过；
  固定40题长度面板额外256/4096cap，2048复用主集同题；自然EOS，不把跨cap/卡轮重复当新样本。
- 私有数据`logs/generalization-data-20261108-a04/`，dataset SHA256=
  `7c179e5d0f84fb87b0ebcdb78a70248f15c01e51d9668ee1b72da5cdcb514486`。
  **agent不得读取新题目/答案/逐题结果**；仅查看`logs/generalization-public-20261108-a04/`聚合状态/报告。
  同UID约定隔离不冒充第三方物理盲评。输入59–636 token，不宣称长上下文泛化；摘要参考为合成数据，
  对话无可靠语义裁判。若结果后改final，此集转dev，必须换确认集。
- 运行入口`exp/generalization_remote.sh <新私有输出> <dataset.json> <公开状态目录>`，
  复用既有controller计时/统计/forcing，exp仅新协议编排和代理质量；三cap各前null→候选→后null、各两轮fresh/物理换卡。
  全部测速结束后新AR/完整自身prefix FP32评分/任务质量；不套旧δ或旧noise。
- 新旧136项CPU测试通过；源冻结提交/最终NorthJob命令/UUID待登记。沿用用户已确认digest镜像、
  WeaverDev/qiji/实际proj-31/原toleration、单节点2 H100/256Gi，最长8小时（16GPU小时）。
  查重→展示完整命令/资源→create一次→code200+精确UUID，含糊先查不重提。
- 已提交一次：source pin=`c085f8bc069228c9dd156aac578f9d99ae6427f4`，
  UUID=`job-611d30b86458-20261108103155`，code200且精确名唯一；初始Pending。
  私有输出`logs/generalization-run-20261108-a01/`不要读取；只监控公开a04状态目录。
  不再次create，执行/科学验收仍待结果；生命周期落准备目录，最终更新以阶段记录为准。
- 准备失败a01/a02为数据源路径/下载，a03为CMRC schema；均无GPU提交/性能结果，原证据保留。
  目前尚未产生新泛化数字；30题dev通过记录见下，不借其替代新数据验收。
- 最新：GPU a01已Failed（node204，retryCount2，原日志和监控权限失败保留），未进入真实runner，
  **无性能测量、无模型server**。远程沙箱正例自检不通过，具体worker stderr当时未保留；
  不断言未经证实的内核根因。公开root日志0600也已诊断，只恢复公开文件可读，私有目录不开放。
- 修正执行位置：新a02远程只配对+FP32 forcing，代码题/质量固定移到本机已验证CPU隔离器，
  root本机9项隔离/编排合成测试通过、新旧137回归通过。新`--defer-quality`只记录质量待完成，不能当科学通过。
  a02公开状态`logs/generalization-public-20261108-a05/`，仍复用a04同一dataset SHA；不重抽样或改final/controller。
  远程完成后用`exp/generalization_local.py`（CUDA_VISIBLE_DEVICES=''，受控sudo读取root私有输出）
  完成质量和独立重放，只读公开汇总；新任务查重/源码pin/UUID见实验记录后续登记。
- a02已code200+精确UUID=`job-6b21065b7a0e-20261108104221`，node244，02:42:54 UTC容器启动，
  pin=`c39c7af0b244e2669bb307ec5684c4165f16d6f6`，公开events进入2048cap/null-pre/round1。
  **不要再次提交或修改运行代码**；前台monitor session13645，文件`logs/generalization-prep-20261108-a01/lifecycle-a02.*`。
  新纯合成探针确认为Landlock后ctypes库查找误走gcc/tempfile，非内核不支持；本机质量路径已验收。
  GPU脚本exit0且gpu-complete存在后，才运行本机质量、两次独立重放/证据SHA，再报告泛化结论。
  运行中只允许文档进度提交，不变更controller/exp/harness/assets；运行身份始终使用上述pin与source-a02.tar。

## 最新接续点：30请求正式dev联合验收通过

- 新入口`docs/experiments/dev-joint-20261108.md`；本阶段controller协议适配/证据联动获用户授权，
  默认legacy不变，不放宽判据。128项回归、旧P5重放/1347历史SHA与本活动独立重放通过。
- UUID=`job-e71c6069ec59-20261108081913`，node135，08:19:29–09:10:36 +08:00，51分7秒；
  Job=Completed/Pod=Succeeded、容器与脚本exit0。观测单Pod UID/Created1/Started1、容器restart0，
  Job retryCount字段未设置。原镜像/WeaverDev/qiji/实际queue=proj-31，2 H100/256Gi。
  source pin=`721b72c013aa6323837de30cba740c6eb55bf796`，运行中源码未变。
- 输出`logs/dev-joint-20261108-a01/`，准备/提交/生命周期`logs/dev-joint-prep-20261108-a01/`。
  固定每suite6条共30请求、2048cap自然EOS；null-pre → candidate → null-post，各两轮fresh/物理换卡，
  2条短预热＋全30条全尺度预热，实际原生生成证据计时后落盘；测得120条输出＋新AR30完整评分。
- final/stock=2.2214815927×，suite分层request-cluster95%CI [2.1585000041,2.2827307674]；
  两轮分别2.219895/2.223069。null-pre=1.00051887 [0.999775944,1.001327351]，
  null-post=1.00026564 [0.999435387,1.001086805]，两会话全部纳入noise=0.00132735095。
  current_campaign_usable=true，输出不同故收益门槛3%，95%收益下界115.85%，性能通过。
- 两轮独立δ=0.25；各轮stock198/25307=0.782392%、final187/24811=0.753698%，零大margin事件，
  rate/event均未触发，正确性均通过。新AR只标定δ，没有重测AR性能。
- joint_acceptance_passed=true，但promoted=false/ledger_eligible=false：作者产物不是自主发现。
  两次独立进程重放JSON字节相同，源码tar/独立retokenize请求/原始HTTP/评分/时序绑定均通过。
  测速后与评分后/最终两卡均0MiB/0%，端口释放；不能把Job Completed单独当科学通过。
- 本活动1223文件清单`logs/dev-joint-evidence-20261108-a01.sha256`，SHA256=
  `0ced7f2f3b760971ba9428ffb344e7da1a1bb974debfa715cd2320ce57c1d4f1`。
- 下一步先向用户报第6步sealed隔离/正式验证的目标与流程，获准后由controller/维护者落实。
  本阶段未读sealed、未做RSI、未写ledger/memory；不自动追加100请求或重复作者基线追数字。

## 已完成：第5步真实裁判回归（上一子阶段）

- 唯一新实验入口`docs/experiments/p5-real-controller-20261108.md`。用户授权本阶段controller改动，
  显式paper-aligned策略、真实FP32 scorer、δ与rate/event规则、runner/证据重放已交付；旧默认不变。
- 成功任务`job-93e052b78439-20261108074348`，node135，07:44:08–07:51:40 +08:00，
  Job=Completed/Pod=Succeeded，容器与脚本exit0；观测单Pod UID、Created/Started各1、容器restart0，
  Job retryCount字段未设置。2 H100/原镜像/WeaverDev/qiji/实际queue=proj-31，两卡清理0MiB/0%。
- 执行pin=`bfb5d6c39fc5cf435557f886e5eda99f7d4b3bdb`；输出`logs/p5-real-forcing-20261108-a02/`，
  源快照/提交/生命周期/独立重放脚本和结果在`logs/p5-real-controller-prep-20261108-a01/`。
  最终controller身份补强pin=`58f37d16f7f432ae1f2e50b34f8ec4dbdda63852`，两次离线重放JSON字节相同。
- 原20请求dev：14对首分歧标定δ=0.25；stock178/20250=0.879012%。健康stock、AR、分段续写、
  等价head均通过；故障475/18512、298大margin事件、rate/event双拒绝；作者final145/19295通过。
  故障实际post2048共8272 token；前200事件prefill审计解释0，另98未审计且按预定规则保留未解释。
- 等价控制5suite×64=320 token，真实checkpoint/FP32逆序8块；logit差最大7.629e-6，选择差异0。
  121项P2/P3/P5 unittest及shell/diff检查通过。全文件discover误导入旧8B独立GPU脚本因无torch失败，
  原失败保留，未修改或擅自运行该旧脚本。无完整Fig4任务精度区间、sealed或数学lossless结论。
- a01完整生成75条后，在head有限值整矩阵临时分配处OOM，原校准/输出不改；CPU分块验证修复后，
  a02按冻结249文件SHA清单复用全部真实生成并用fresh scorer全部重评分，明确不是单会话/性能配对。
  a01最终Failed/retryCount2和两次接口探针失败均保留，不把最终Pod restart0当全任务无重试。
- 新结果judge_ready=true，promoted=false/ledger_eligible=false；历史null重放noise=0.0022681713，
  current_campaign_usable=false，不能充当前正式校准。不自动进入sealed/RSI/写ledger。
- 1347文件证据清单`logs/p5-real-controller-evidence-20261108-a01.sha256`，SHA256=
  `050794539a3104f4fce85a56ba88704513a31438bf301e680847cd77df61c815`，包括所有失败和成功执行及源码快照。
- 下一步先向用户报正式dev扩围/当前null与候选联动的目标和主要流程，批准后再执行；
  不重跑已经完成的作者性能基线，不再为0.2%或覆盖1额外工程自检追绿。阶段验收后按授权推送私有origin。

### 以下为本阶段早期及上一阶段历史记录

- 最新用户已明确批准本阶段修改controller（仅校准与正确性验收），阶段内自主执行，不进入sealed/RSI/正式晋升。新入口记录`docs/experiments/p5-real-controller-20261108.md`。先红后绿的新旧105项CPU测试通过：显式paper-aligned-v1校准/候选readiness判定及native teacher-forced评分传输，legacy默认不变。准备短NorthJob接口探针，真实scorer/δ/注入/等价控制尚未验收；勿将接口测试当真实正确性通过。
- 本次记录：`docs/experiments/p5-acceptance-alignment-20261108.md`，依据用户PDF的§3.2/3.3/3.4/5.1；文档规则`paper-aligned-v1`见`docs/02-acceptance.md`。用户明确要求“对齐验收规则”，本次仅文档修订，不修改controller/运行代码，不提交GPU、不读sealed、不写ledger。
- 论文要求收益95%下界超过`1% + 2×实测stock-null噪声`，输出有分歧时约3%；H100 noise<0.1%是论文观测值。论文没有规定null CI全宽<0.2%或两独立会话均覆盖1，也没有规定CPU独占。上述额外自检降为诊断，不再以此阻塞研究主线或继续追绿；校准有效性、真实正确性及晋升下界仍必须验收。
- 历史precision/centered/stable字段、失败JSON和gate exit=1保持原值；本次不宣称旧实验新通过。controller尚未切换，不能由harness另设裁判绕过。正式noise估计量、跨会话选择、CI尾概率与候选同尺度协议需维护者先确认并接入；真实FP32-head scorer、stock mismatch/δ、故障注入/归约对照仍未完成。
- 下一步应先报真实裁判交付流程再获准执行；不重跑A1/A2/A3，不把CPU资源配置当唯一前置，不自动sealed/RSI。旧“先把CI压到0.2%/先等独占CPU”的接续计划已由本段替代。架构与论文数字复现仍分开报告。

## 第5步历史实验与权限记录（以下非当前执行计划）

- 最新完成CPU亲和性受控复验：`docs/experiments/p5-cpu-bound-null-20261107.md`，执行pin=`794219b`。UUID=`job-788af093f15c-20261108003647`，node131，16:37:05–17:22:20 UTC，Job=Completed/Pod=Succeeded，容器/脚本exit0、restart0，两会话两卡清理0 MiB/0%。会话1=1.0002672639、CI[0.9998000780,1.0007914498]、全宽0.0991372%，stable=true；会话2=0.9990706080、CI[0.9977318287,1.0003567337]、全宽0.2624905%，stable=false。均覆盖1且CPU绑定验收通过，但整体稳定性门禁exit1；不挑首会话、不合并平均、不再同配置追绿。
- CPU修正默认关闭，只在stable-null配合`--pin-cpus`；GPU固定scheduler主核2/50、各自8后台核，全部线程监控通过；不改controller/统计/门槛/引擎/时钟，不等于独占CPU。98项回归、独立复算两次JSON一致、历史校验通过。161文件清单`logs/p5-cpu-bound-null-evidence-20261107-a01.sha256`，SHA=`3b76e931a655ea915d97a1fae2e13766c8d1d87e46514a12a155573ac1f23a8d`。
- 此前资源诊断分支：真实Pod为Burstable、无CPU request/limit；当前NorthJob CLI无CPU预留/独占参数。第二会话约80.57%分层方差来自HumanEval，服务端也有延迟差；不能断言CPU是根因。一次预登记CPU修正已执行完，曾建议确认可用CPU隔离资源再做诊断；2026-11-08已取消其通用前置地位。不得擅自修改集群、升级CLI或手写Volcano提交，不盲重提。
- GitHub原credential helper指向已清理的`/tmp/handoff-gh/.../gh`；本轮push只在该进程使用`logs/p5-github-credential-helper.py`读取本人现有gh配置，未改全局配置、未把凭据写入Git/对话。后续push应注意此环境限制，不打印token。
- 稳定化a01已完成：`job-8f1d3b6bafa2-20261107233518`，node131，15:35:54–16:23:17 UTC，Job=Completed/Pod=Succeeded、容器/脚本exit0、无重启，两卡清理0 MiB/0%。会话1比值1.0020415084、CI[1.0011419394,1.0029587541]、全宽0.1816815%；会话2比值1.0018638161、CI[1.0010030732,1.0027354135]、全宽0.1732340%。两次precision=true但centered/stable=false；不平均掩盖，不盲重跑。141文件清单SHA=`7b99fcff66511193a200153c301600ae387a730766717d29db1335287477f1bb`。详见稳定化报告结果段；91项回归及独立复算通过。CPU迁移/亲和性是待受控验证假设，尚无因果结论；若继续本授权需先登记实质修正，不改controller或门槛。
- 最新用户已批准噪声稳定化大流程，明确流程内自主实现/调试/复验，无需中途请示；上一轮“只读、再复验需批准”是历史限制。高风险/额外权限仍须审批，不放宽门槛、不读取sealed、不设置共享GPU时钟。
- 正在冻结新协议代码：`docs/experiments/p5-stable-null-20261107.md`；固定完整20条/2048cap预热一遍，正式同20条，每会话预先4轮fresh双server/GPU×端口独立交叉，启动/提交顺序平衡并有线程屏障、HTTP实际时序、每2秒GPU/CPU监控。两独立会话均须全宽<0.2%；另加CI覆盖1的工程自检防窄但偏移，不冒充论文新增判据。20请求仍20独立cluster，不把4轮当80独立请求。
- 新旧91项测试通过、历史统计复算不变；入口 `exp/p5_remote_stable.sh <新目录> <A1目录>`，显式 --stable-null 启用，默认旧协议不变。a01于2026-11-07 23:35:18 +08:00唯一一次create code200，精确名查重解析UUID=`job-8f1d3b6bafa2-20261107233518`；原镜像/WeaverDev/qiji/实际proj-31/2 H100不变。现已结束，切勿重复create；真实forcing/注入不在本次噪声稳定化范围。
- 以下只读诊断是此前完成记录，本轮执行状态以最新协议记录为准。

- 最近用户只批准分析已有日志，本轮未提交GPU、未启停server、未改controller/exp/harness/gates或测量协议。下一次GPU复验须先报主要流程并获准，不能把此次“允许”当提交授权。
- 只读诊断 `docs/experiments/p5-noise-diagnosis-20261107.md`：8个server启动参数仅端口不同，输出/verify工作量一致且确实物理换卡。客户端残差通常约2ms，第二会话server时段仍有0.3273%偏差（客户端0.3333%），首会话server影子CI全宽仍约0.2635%，所以不能只换计时字段解决。
- 首条425-token/81-verify请求的双臂均时跨轮1.995–2.739s、跨度37.3%；其余19条的双臂均时跨度<1%。源代码预热是前两请求各最多32新token，结束后约0.5–0.8ms立即测速。支持优先检查启动稳态，但固定请求顺序混淆了样本与位置，不能断言预热是根因。
- 第一会话GPU1在36/40对更快，第二会话29/40，角色/端口/先发顺序/时间仍混杂。Pod没有显式CPU request/limit、numa_node=None；没有GPU频率/温度/功耗、实际CPU亲和性/运行负载、两臂发送时间等时序，不能甩锅“某张卡差”或认定CPU争用。第一会话gsm8k贡献约69.51%的分层bootstrap方差；前两请求的全局离散70.22%不等于贡献70%的CI方差（实际分层贡献34.61%）。
- 4个离线脚本在a02重放JSON一致，79测试、所有历史清单及运行实现未变验证均通过。最终26文件清单 `logs/p5-noise-diagnosis-evidence-20261107-a02.sha256`，清单SHA=0f42977b996332bfd6b86b5887bf7a58884b94c91f08b12275bbbe55b1e71512。脚本/输出在同名前缀a01/a02目录，完整SHA见报告，不覆盖旧测量。最终影子CI严格沿用原suite顺序/seed，客户端区间先逐字段复现，再换server时段；不要把初步排序suite的supplement端点当最终影子结果。
- 建议待批准后固定一次全尺度未计时预热并补状态/发起时序记录，再有限复验两会话；不删首请求，不把多个会话平均成通过，不改原20请求/2048cap/自然EOS/物理换卡/<0.2%要求。本轮止于日志诊断，真实FP32 scorer/注入/sealed/RSI均未推进。

- 用户在审计之后明确授权“允许修改”：范围为本阶段 controller 正确性/统计修复，不放宽判据，不读取 sealed，不进入 RSI。后续普通 agent 仍须遵守 controller 维护者边界，不能推定永久授权。
- 修复记录 `docs/experiments/p5-controller-repair-20261107.md`。空/长度/统计溢出/rate rule/输出分歧性能门槛已修；stock stock 显式展开 stock-a/stock-b，底层仍启动 stock。原 9 个合成反例全过，新旧 79 项测试通过，仍没有真实 lossless/晋升结论。
- 真实 null 已结束：`job-3c6565eedef3-20261107210140`，测量源 pin=dbebc6b88e97b893d7a0afd2a326a8ed37fd1bbc，2026-11-07 21:01:40 +08:00 code=200 后按精确名解析唯一 UUID。原镜像/WeaverDev/qiji/原 toleration、2 H100，node233；21:02:04启动、21:18:55结束，Job=Completed/Pod=Succeeded，容器/脚本exit=0、restart=0；两会话各两卡清理0 MiB/0%。输出 `logs/p5-stock-null-2048-20261107-a01/`，总80 pair/160臂行，但仅原20个不同请求。
- Session 1：比值0.9999525264、分层双侧95% CI [0.9986248088,1.0012594020]，全宽0.2634593%，noise=0.1375191%，precision_passed=false。Session 2：1.0033328725、CI [1.0026846326,1.0039834119]，全宽0.1298779%，noise=0.3983412%，precision_passed=true。整体精度门禁exit=1；两实例/卡位/会话输出一致不等于lossless。不能挑第二会话或跨会话平均掩盖失败，不重提追绿，不进入sealed/RSI。
- 下一步应先定位预热/稳态与角色时序偏差，登记稳定性协议；真实FP32-head scorer/stock mismatch/delta/注入及归约对照尚未完成。黑盒help已确认有 --enable-fp32-lm-head，但开关存在不是验收通过。权限阻塞已解除，当前是实测精度门禁未过。
- 78文件清单 `logs/p5-controller-repair-evidence-20261107.sha256`，清单SHA=170479f90a00a324865fe3430f9ab066906e19b213d52cdbef997fc9790f0c4d；完整源码快照在repair-a01/final-source.tar。95组SciPy核验、最后79测试、历史统计复算/清单均过。测量结束后仅澄清null reader CI字段标签，原始数据与判断未变，复验结果见independent-null-reaudit.json。详细报告记录具体路径与SHA。
- 以下审计条目是修复前历史，当前状态以本段与修复记录为准。

- 用户已批准开始第 5 步，但没有授权修改 `controller/`。先做只读 CPU 审计，无 NorthJob create、无 GPU 进程、无 sealed/作者实现访问、无 ledger 写入。
- 新入口 `exp/p5_readiness_audit.py --out <新JSON路径>`，只用合成 token / 内存 fixture 调用已有接口；exit=1 是未就绪证据，不是可放宽的正式门禁。
- 9 项检查全部未过：空请求/空 token 误报 lossless；少尾/多尾/整条缺失仍误过；4096 相同 token 自比 OverflowError；1000/1000 分歧 rate_flagged=False（event 此例仍拒绝）；合成输出不同的 2.5% 增益被 HTTP compare 标 promoted；stock stock 非执行计划被现有 CLI 拒绝。不是 9 个独立根因，也不是 27B 真实注入。
- scorer/margin/delta/实测 stock mismatch、真实注入及独立双 server null 尚无证据，不能绕过 controller 在 harness 另立正式裁判。审计工具 7 项测试、既有 P2/P3 50 项回归通过；不表示第 5 步通过。
- 记录与维护者交付清单：`docs/experiments/p5-readiness-20261107.md`；原始 `logs/p5-readiness-20261107-a01/`，复验另用 a02，不覆盖旧证据。继续需用户明确授权限定 controller 改动或维护者交付；不自动进入 sealed / RSI。
- a02 复验 9 项观察相同、exit=1；最终 57/57 测试通过，P2 a05/A1/A2/A3 历史证据和 controller 未改验证通过。新 12 文件清单 `logs/p5-readiness-evidence-20261107.sha256`，清单 SHA=5dc42cbdc0ba68dba02ccc2c3abfdce6955ea293c6b58a1d0a9af091ab1c3480；含完整审计代码/测试快照。阶段仍 blocked，不把“工具测试通过”写成“真实裁判通过”。

## 前一阶段：第 4 步作者 final 验证（不是 sealed Phase 4）

- 当前第 4 步已完成：A2 final/AR=8.7347197445× [8.0234899904,9.5599189918]；A3 **直接 final/stock=2.2218558884× [2.1380887617,2.2987528227]**，不是两次 AR 对照相除。两项实验均 20 原请求/2048 cap/自然 EOS、两轮 fresh server/物理换卡，各 40 pair/80 臂行、Job=Completed/Pod=Succeeded、容器/脚本 exit=0、GPU 清理 0 MiB/0%、50/50 回归及独立统计复算通过。源 pin=4d67c2f4acfa1b68df24ef3de5a8cf53819e1962，模型/镜像/调度参数未换。
- A3 唯一 UUID `job-4508734deeb3-20261107190750`，19:07:50 +08:00 code=200，19:08:14 启动、19:16:09 结束，node204，无重启；A2 已结束后才提交，最大同时占 2 GPU。输出 logs/p3-stock-final-2048-20261107-a01，38 文件清单 logs/p3-stock-final-evidence-20261107-a01.sha256，清单 SHA=bd5088cdd15862f2959cf7e327af7a4f8b04fdc76d12c051fbcf37bc6026bff6。A2 的 37 文件清单与 A1 历史清单均再次复核完整。
- 解释边界：AR/stock/final 平均实际长度为 999.0/1012.5/965.075 token；当前是作者产物 dev 子集验证，不是完整 dev（6 条/suite）/sealed、lossless 或自主发现。W12/tree/GDN 日志表明相关路径运行；缺字面 TLV 日志不等于未启用，但语义/计数仍需审计。长输出收益提高支持固定开销解释，不是同样本短/长输出严格因果证明。下一主线第 5 步真实正确性与噪声/晋升；先报计划获准，controller 仍仅维护者，不自动 sealed/RSI。

### 第 4 步准备与 A2 历史（以上述完成状态为准）
- A2 已完成：`job-674358f4a1a0-20261107183406`，final/AR=8.7347197445×，95% CI [8.0234899904,9.5599189918]；40 pair/80 臂行、请求绑定/树/46 开关/物理换卡/统计复算通过，Job=Completed、Pod=Succeeded、exit=0，两卡清理 0 MiB/0%。源 pin=4d67c2f4acfa1b68df24ef3de5a8cf53819e1962；输出 logs/p3-ar-final-2048-20261107-a01，37 文件清单 logs/p3-ar-final-evidence-20261107-a01.sha256，清单 SHA=cabf4e5079946bec3ce9e7f18e709c0a930428b63f069b332b919033061cf417。运行日志有 W12/tree/GDN 路径证据，未检出 TLV 字面日志，不宣称已审计 TLV 语义/lossless；其后 A3 已按计划完成，不重复任何 create。
- 当前完成：用户授权本阶段自主拆分、调试、测试及正常范围内重跑，小步骤不再等待回复；高风险及 skill 的查重/镜像/不明确提交保护仍有效。a04 首轮完成后因端口 TIME_WAIT 误报失败，已保留全部证据；只在探测 socket 增加 SO_REUSEADDR，真实 TCP 回归先红后绿，真实监听仍拒绝。最终 CPU 回归 26/26（17 编排 + 9 挂载/验收）通过；controller、sealed、账本、模型和镜像未改。
- a05 完成：2026-11-07 16:42:26 +08:00 code=200，唯一 UUID `job-ad27e2790ef7-20261107164226`；16:42:45 启动、16:47:09 结束，Job=Completed / Pod=Succeeded / container exit=0 / script exit=0，无容器重启。源 pin=`0bb2965474bc7b2872d59bc6f311c94ebf6b22b1`；原 5 请求/64 cap/两轮物理换卡全部通过，10 pair/20 臂行、请求哈希一致，两张 GPU 清理后均 0 MiB/0%。结果 `logs/p2-remote-smoke-20261107-a05`；33 个证据文件清单 `logs/p2-evidence-a05-20261107.sha256`，清单 SHA=231d9d7fcc24a526750d925eb2ad5a5321b4893f909789d09aa875fa0ad74e03。统计复算与持久 summary 完全相同，但这是短输出诊断，不是论文/正式性能或 lossless 结论。
- 当前主线已完成：AR/stock 20 请求、2048 cap、两轮 fresh server/GPU 互换，40 pair/80 臂行完整。stock/AR 几何平均 **3.8698909614×，95% CI [3.5570626359,4.2241726177]**，既有点估计判据 [3.555,4.345] 通过；两轮 3.8768596249× / 3.8629348241×，不能把差值当噪声地板。自然 EOS 保留，每臂 40 行中 30 stop/10 length，AR 平均 999.0、stock 1012.5 token，不能说每条生成满 2048。
- a01 唯一 UUID `job-3214d33ae356-20261107173128`；2026-11-07 17:31:28 +08:00 code=200，17:31:51 启动、17:50:33 结束，Job=Completed / Pod=Succeeded，容器/脚本 exit=0、restart_count=0。源 pin=`79fe81a61ffc38cc6a1352cbf0f25fe6668c280a`；原镜像、WeaverDev、namespace=qiji、请求 queue=qiji/实际 proj-31、toleration 均未换。输出 logs/p3-ar-stock-2048-20261107-a01，独立校验/统计复算一致、GPU 清理为两卡 0 MiB/0%，39/39 回归通过；38 文件清单 logs/p3-baseline-evidence-20261107-a01.sha256，清单 SHA=69f88e265d58e89ef86bc90878db3f61808bab2143fe578c2ac41f1be217c7b5。详细报告 docs/experiments/p3-ar-stock-2048-20261107.md。
- 当前第 4 步已获用户批准：先 A2 AR/final、再 A3 直接 stock/final，独立两次任务、各 2 H100，不并发占 4 卡；同 A1 原 20 请求/模型/采样、2048 cap、warmup=2、两轮 fresh server/物理换卡。新入口 exp/p3_remote_final.sh <ar|stock> <out> <A1 reference>，final 身份、A1 请求绑定及统计完整性由 harness/final_validation.py 校验；共享逻辑泛化后 A1 旧验收输出完全相同，新旧 50/50 回归通过。原镜像/WeaverDev/qiji/原 toleration 保持，不套用 A1 3.95 或 sealed 2.13 门槛；低收益也保留数据并排查，不进入 RSI/sealed。记录 docs/experiments/p3-final-2048-20261107.md；准备冻结源 pin 并先提交 specpilot-p3-ar-final-20261107-a01，后提交 specpilot-p3-stock-final-20261107-a01。

### 以下为准备及失败历史（当前状态以上述完成记录为准）
- 当前在原十步主线的第 2 步“配对测量远程验收”；镜像、CLI 和挂载是内部准备，不重新拆成研究大步骤。大步骤先报目标、流程与自检并等用户允许，内部小步骤自主安排。
- 用户已批准开始第 2 步，并明确同意使用下面固定 digest 的 oss-sglang 镜像。首次提交于 2026-11-07 06:46:44 UTC 被 HTTP 403 / code 40301 拒绝：账号 jixinpeng 不属于 default 项目。提交后按原名查询 total=0；无 code=200、无 job_uuid，未启动远程测量。需确认可用 `--project` 并获准重提，不要直接再次 create。运行记录见 `docs/experiments/p2-remote-smoke-20261107.md`。
- 用户随后明确指定 `--project infra-dev-weaver --k8s-namespace qiji --k8s-queue qiji --k8s-toleration key=task-type,operator=Equal,value=infra-dev-weaver,effect=NoSchedule` 并授权重提一次。已核对 CLI help、凭据格式与查重；新尝试名 `specpilot-p2-smoke-20261107-a02`，代码 pin 与镜像不变。2026-11-07 15:23:13 +08:00 返回 HTTP 400 / code 40005：项目 infra-dev-weaver 不存在；无 UUID，提交后 total=0。模板确认四项参数正确、无新增 nodeSelector；项目、namespace/queue、toleration 不能混同，toleration 不保证只调度该池。暂停，核实后端项目身份并取得新授权后才能再次提交。
- 用户要求只读排查后，已交叉核对 CLI/API 与两条本人 Kubernetes 任务：当前账号 jixinpeng、CLI 3.3.11、后端 10.1.2.7:31000 均无身份/环境覆盖异常。旧 infra-dev-weaver 任务在服务端为 project_exists=false / user_in_project=false；本人 WeaverDev 任务为 true / true，且现场注解、namespace/queue 与 API 一致。建议下一次仅改 `--project WeaverDev`，保留 qiji namespace/queue 和 infra-dev-weaver toleration，待用户授权再提交。只读诊断证据 `logs/p2-project-diagnosis-20261107.json`；不能据此称 GPU 配额、调度或镜像兼容通过，也不知道旧任务的创建路径或项目历史变更。本轮没有 create/update/delete。
- 用户随后批准修正项目重提。a03 名 `specpilot-p2-smoke-20261107-a03`，2026-11-07 15:54:59 +08:00 收到 code=200/data=None；精确查重唯一匹配 UUID `job-65f7d61d3d7f-20261107155459`，确认提交成功。进程 15:55:52 +08:00 已启动；持久日志显示 git dubious ownership，脚本 exit=128；最终 Job/Pod Failed（容器 exit=1）。未创建 runner 输出目录、未到 GPU 预检，无配对数据。请求 namespace/queue 为 qiji，服务端有效 queue 为 proj-31，不能隐瞒这一差别。未再次 create。下一次建议仅在任务命令的进程环境中设置 `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/gpfs/users/jixinpeng/SpecDec/SpecPilot`，不改全局配置、不信任通配路径；本机模拟 Git 归属不匹配验证 128→0，尚需新授权才能重提。记录见 docs/experiments/p2-remote-smoke-20261107.md。
- 可用 CLI 已找到：`/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/northjob`（3.3.11，参数与 skill 匹配，get 查询成功）；不再用缺 Kubernetes 依赖的 `/gpfs/envs/miniconda3/bin/northjob`，未升级 CLI。计划名 `specpilot-p2-smoke-20261107` 的查询 total=0；真正提交前重新查重。
- 已从本人现有任务核对镜像候选：`harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。仅证明在集群已有运行实例，不证明适配本实验；拟优先复用共享 `sp-sglang1520` 环境，不切换为镜像内未知引擎。
- 挂载已补最小适配：`exp/p2_northjob.py create ...` 在本进程调用原 CLI，仅在其生成的模板上追加 `share-readonly` / `models` 子路径到 `/gpfs/models` 的只读挂载；主挂载用 `jixinpeng-pvc` → 用户目录。不改已安装 CLI、不复制权重；真实模板离线验收通过。`RUN/` 已忽略，提交回执与日志保留在 `logs/`。
- 原编排测试 15/15，新增真实端口回归后 17/17；挂载与验收测试 9/9。stock/final 的 5 请求、64 cap、两轮烟测已在 a05 完成（10 pair / 20 臂行）。入口 `exp/p2_remote_smoke.sh`，1 节点 × 2 H100，256Gi，禁 RDMA 和 hostNetwork；只验收生命周期与落盘，不设论文收益门槛。代码 pin 比对 exp/harness/controller，允许后续只更新文档。
- 私有远端：`https://github.com/Sym-Je/SpecPilot-reproduction.git`（origin）。用户已授权每个大步骤结束后更新 README 进度、交接与相关代码，验收后阶段提交并推送；不上传大产物、凭据或 sealed 数据。
- 重新对齐论文/公开项目后的详细方案见 `docs/11-reproduction-plan.md`（草案，未授权修改 controller 或已有判据）。其中区分每 suite 4 条诊断、上游默认 6 条 dev 表格和后续 sealed；正式 CI 与真实 forcing 尚有维护者待办。
- `exp/p3_pair_run.py` 已实现 fresh 双 server、controller 逐请求配对、两轮物理 GPU UUID 互换、每轮一对 JSONL 和几何平均 CI；controller 未改。
- 验收：`PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s harness -p test_p3_pair_run.py` → 15/15；shell 语法和 `git diff --check` 通过。
- AR/stock 的 20 请求、2048 token、两轮执行已尝试，但在起 server 前被忙卡保护拒绝：GPU0/1 分别有 PID 59780/59781（各约 518 MiB，当前命名空间查不到进程名）。未杀进程，无实测数字。
- 用户已将后续执行统一到 NorthJob；不再等待本机两卡释放，也不继续扩建本机调度。按 northjob-submit skill 查重名并展示完整命令与资源，核对 code==200 且有 job_uuid；镜像已由用户确认，不得静默换镜像或重提不明确的提交。
- 远程按既有配对协议复用编排：先 AR/stock（20 请求、2048 token、两轮物理换卡，诊断区间 [3.555, 4.345]），通过后 AR/final，再直接 stock/final。相同 H100 不自动取消配对规则；远程环境与 GPU 生命周期尚未验证。
- Git 管理全流程的计划、任务、证据索引和决策，见 `docs/12-experiment-management.md`；每次实验使用 `docs/experiments/TEMPLATE.md` 建记录。原始产物外存并校验，不改 controller、不手写正式账本、不提前 RSI 或 sealed。
- 本机执行日志：`logs/p3-local-ar-stock-20261107.log`；因预检失败尚未创建对应运行目录。

## 一句话现状

RSI 的**制度层**在 mock 规模跑通（G2–G5）；**执行层**已打通到"三臂各起一次真 server、
跑同一请求集、落可审计 JSONL"（P0–P3，G6/G7/G8 全绿）。
**NorthJob 共尝试提交五次：前两次被拒，a03/a04 执行失败，a05 完整远程双卡烟测通过。** 论文正式数字一个都还没独立测出；本机烟测 stock/AR 3.74×
只作历史诊断，不代表正式配对尺子已经校准。

上述五次为 P2 历史；此后 A1 单独提交一次并完成，真实 20 请求配对诊断 stock/AR=3.8699× [3.5571,4.2242]，不能与论文完整 dev/sealed 协议混称。

## 接手前必做（5 分钟）

```bash
cd /gpfs/users/jixinpeng/SpecDec/SpecPilot
git log --oneline -5 && git status --short
cat AGENTS.md              # 铁律，不可协商
cat docs/06-gates.md       # 已通过的闸门与实际数字
cat docs/07-experiment.md  # 短期实验记录 + 5 个踩过的坑（必读）
ls harness/sglang/         # 启停脚本，环境约定全在 env.sh
cat docs/09-p3-harness-validation.md   # 三臂烟测实测数字与"为什么不能引用"
```

## 1. 任务边界

复现 *SpecPilot*（arXiv 2611.02501）的 **RSI 闭环**，引擎用 SGLang v0.5.20，硬件 H100 + Qwen3.8-27B + DFlash2。

**永远区分两件事**：
- **架构复现** = 闭环/测量/判据/账本/记忆是否正确
- **数字复现** = 能否独立测出 config 的 2.13× [2.07, 2.19]（sealed final vs stock）

在拿到实测前，任何"复现了论文"的说法都是错的。

## 2. 铁律（摘自 AGENTS.md）

1. 数字生产权归 `controller/`。agent 自报的加速比只是假设。
2. `eval/sealed/` 只由 controller 在 Phase 4 加载，agent 进程不得读。
3. 一切变更走 option，默认值必须复现 stock 行为。
4. 先写验收命令，再写实现。
5. 禁止：单卡串行 A/B 冒充配对测量；把"任务精度没掉"当 lossless 证据。
6. lossless 判据 = **token 级检查**（每个提交 token 都是 target 在该位置的自身选择），
   不是比文本。上游明说任何投机解码器（含 stock）输出都不与 AR 逐位相同。

## 3. 上游：只读边界

`/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main`（329 M，tarball 解压，**无 .git**，commit 78c42af）

**禁止读**：`python/`（剪枝 SGLang 实现）、`settings/*/files/`（final 机制实现）
**允许用**：`settings/*/config.json`、`research/bench/splits/`、`scripts/`、`research/dflash_lab/README.md`

上游**给了**：stock 引擎树、6 个 setting 的 final 覆盖层 + 46 个 `SPECPILOT_*` 开关、
bench/compare/score 脚本、dev split manifest（seed 20260928，5 数据集 × 20 条）。
上游**没给**（已全树关键词扫描确认，别再重新调研）：agent 主循环、cost model、ledger、
memory、candidate/campaign 管理、sealed 集、`ar` CLI。

## 4. 环境事实

| 项 | 值 |
|---|---|
| GPU | 2× H100 80GB HBM3，驱动 **535.154.05**（CUDA **12.2**） |
| 目标模型 | `/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B`（52 G）✅ |
| drafter | `/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2`（3.6 G）✅ |
| sglang 依赖环境 | `envs/sp-sglang1520`（sglang 0.5.20 / torch 2.13.0+cu130 / py3.12） |
| 引擎树 | 上游 `python/`，通过 `PYTHONPATH` 覆盖，**不 pip 安装** |
| 数据/缓存 | `/gpfs/users/jixinpeng/specpilot_data`（370 M） |
| 代理 | `http://10.51.6.1:6890`（外网必设） |
| git | 已修好：`~/.local/bin/git` → `envs/gitcli`（2.56.0）。备份 `git.bak-20261107` |
| NorthJob | `/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/northjob`（3.3.11；不用旧的 /gpfs/envs 版本） |
| 备选环境 | `envs/alice-sglang`（torch 2.9.1+cu128）—— 535 驱动上唯一原生可用的 torch，但**不含 sglang 0.5.20 依赖** |

**三个坑**（`harness/sglang/env.sh` 已针对它们写好）
1. torch 2.13+cu130 需 R580；535 要靠 NVIDIA **cuda-compat-13-0** 的 `libcuda.so.1`。
2. 全系统无 C 编译器。Triton JIT 会崩 `Failed to find C compiler`。
   解法：conda-forge `gcc_linux-64=13` 或 `nvidia-cuda-nvcc==13.0.*`。
3. 容器内 supervisord(PID 1) 会 reap 后台进程（exit 255）。长任务**前台跑**或走 NorthJob。
   `/tmp` 会被清空。

## 5. 卡点已解除：stock server 在真实权重上跑通（2026-11-07）

`logs/serve2.log`（stock 臂，block 8）：
```
Load weight end. elapsed=72.92s, type=Qwen3_5ForConditionalGeneration
Load weight end. elapsed=4.90s,  type=DFlash2DraftModel
Initialized DFLASH draft runner. attention_backend=fa3, block_size=8
KV Cache allocated: #tokens 108029
scheduler_e2e=219.34s  cuda_graph={prefill=39.73, target_verify=1.45, draft_decode=8.68}
The server is fired up and ready to roll!
```

此前崩在 `memory_pool.py:2114 _init_kv_copy_and_warmup` → triton JIT → 缺 C 编译器，
已由 `harness/sglang/env.sh` 的三件修补解决（conda gcc 14.4.0 / cuda-compat libcuda / CUDA_HOME）。

**第一条真实 greedy 请求已跑通**（`harness/sglang/probe_greedy.py`）：

```
[gsm8k-1182] 425 tok 2.70s 157.6 tok/s verify=81 tau=5.25
[gsm8k-211 ] 309 tok 1.54s 201.1 tok/s verify=46 tau=6.72
[gsm8k-877 ] 505 tok 2.50s 202.0 tok/s verify=79 tau=6.39
deterministic 3/3          → ACCEPT
```

- greedy 两次 output_ids 的 sha256 完全相同 → 逐 token 判据可以接到真引擎。
- τ 均值 6.12（论文 stock 4.65，不同请求集，不可直接比）。
- **这是烟测，不是测量**：单臂、无预热标定、无配对、无 GPU 互换。
  详见 `docs/07-experiment.md` 第二部分。

## 6. 起 server / 打请求

```bash
# 前台起（长任务必须前台，supervisord 会 reap 后台进程）
bash harness/sglang/serve.sh 2>&1 | tee logs/serve.log

# 另一终端：greedy 探针，自带确定性验收
source harness/sglang/env.sh
$SP_PY harness/sglang/probe_greedy.py --n 3 --repeats 2 --max-new-tokens 2048
```

`serve.sh` 已对齐上游 `research/scripts/launch.sh`：`--random-seed 0`、`--served-model-name`。

## 7. 之后的路线

- **P0（已完成）**：`docs/08-upstream-pin.md` — tarball sha256 `25e68b1b…602dd4`，
  规范化清单 `assets/upstream/MANIFEST.sha256`（3097 文件）sha256 `4bca3c10…81563f`；
  已核对 tarball 解包树与现有树逐字节一致（差异仅 .pyc）。
- **P1（已完成）**：`harness/build_engine.py` + `gates/g6_engine_build.py`（6/6）。
  stock `e5472c4f…652e3ff` / final `d406ba81…54f90a`，产物在
  `specpilot_data/work/engines/<setting>-{stock,final}`。`env.sh` 已改为优先用派生树，
  缓存按 `TREE_SHA[:16]` 分桶。验收：派生 stock 与上游树逐 token 一致（3/3）。
  坑：换 PYTHONPATH 会让 JIT 缓存失效，首次启动 `draft_decode` 图采集 8.7 s → 222.8 s。
- **P2（已完成）**：`controller/http_transport.py` + `gates/g7_http_transport.py`（5/5）。
  真实引擎的 options 是启动参数，所以配对变成"两个 server 各占一卡"；
  `HttpPairBench` 复用 `controller.stats`，统计不改。单卡顺序路径
  `SequentialPairBench` 直接 raise，**不许**冒充配对。验收含同 arm 确定性、
  噪声地板、`1%+2*noise` 下界判据注入测试。
- **P3（20 请求/2048-cap 的 A1/A2/A3 诊断已完成；下一步真实正确性与噪声/判据）**：链路提交 `ed8b571`，编排修复 `0bb2965`，A1 源 pin=79fe81a、A2/A3=4d67c2f；不是论文完整 dev/sealed 验收。
  `exp/p3_pair.sh <arm> <gpu> <port> <out.jsonl>` = 单臂执行单元（起 server → run_arm → 停）；
  `harness/sglang/gen_final_env.py` 从 config.json 派生 final 的 46 个 `SPECPILOT_*`（不手抄）；
  `gates/g8_pair_arms.py` = 配对前置条件 8 项，其中 **E2 要求三臂 `input_sha256` 逐条相同**。
  本机烟测（1 条/suite、256 tok、单卡顺序）：AR 43.6 / stock 162.9 / final 245.7 tok/s，
  stock/AR **3.74×**（论文 3.95×），τ 5.02→11.13（论文 4.65→13.08）。
  `final/stock` 只有 1.51×；**256-token 短序列摊不开固定开销**是待验证解释，不能排除覆盖层或配置生效问题。
  已经 NorthJob 双卡、每臂 fresh server，`P3_PER_SUITE=4 P3_MAX_NEW=2048`、两轮物理换卡，完成 AR/stock、AR/final 和直接 stock/final；实际结果见顶部与实验记录。
  后续正式 dev 扩围需先登记协议；P4/sealed 仍需 controller 真实判据与正确性/噪声就绪。原 image 与 WeaverDev 已验证，20 请求诊断完成，不得据此宣布正式 dev/sealed 完成。
  详见 `docs/09-p3-harness-validation.md`、`docs/11-reproduction-plan.md` 和 `docs/12-experiment-management.md`；`docs/10-p3-local-pairs.md` 保留执行单元说明，不再要求先跑本机。
- **P4（2 天，可与 P3 并行设计）**：建 `eval/sealed`（controller 侧抽样，agent 不可见）；
  `patches/` 先放 `noop`（必须 token-identical 到 stock）+ `block_8_16`。
  **必须新增门禁**：τ 计数口径一致性 —— final τ=13.08 是 *per exact-weight pass*
  （TLV 下可超 16 token draft block），stock τ=4.65 是 per verify step，**两个 τ 不同源**。
  用 τ 做奖励会把"换计数口径"当成"机制有效"。`run_arm.py` 已落 `tau_source` 字段
  （`per_verify_step` / `ar_no_verify`），final 的 TLV 口径仍是待办的第三个值。
  **lossless 判据**：paper 的 lossless 指"greedy 且每个 token 由 target 判定"，**不是**
  AR 与 stock 逐 token 相同（烟测仅 1/5 相同，第 3 个 token 就分叉，原因是采样路径不同 →
  BF16 GEMM 形状不同 → argmax 在近似并列处翻转）。跨路径的 lossless 只能靠
  **token forcing**（把 stock 的 token 序列喂回去，逐位检查 target argmax）来证明。
- **P5（长期）**：真 RSI。**不要追 W12**（69 KB CUDA kernel，短期做不到）。
  从简单机制族起：block size、tree shape、accept 阈值、attention backend、mem-fraction。

## 8. 仓库现状

`git log`: … e87db70 → 5a46dca → 3d14168(P0) → 76b642d(P1) → 39edfcb(P2) → ed8b571(P3)
（以 `git log --oneline` 为准）

**新门禁**：G6 引擎树可重现 6/6 · G7 传输层 5/5 · G8 配对前置 8/8
**派生树**：stock `e5472c4f…652e3ff` / final `d406ba81…54f90a`
**final env**：`/gpfs/users/jixinpeng/specpilot_data/work/env/h100_c1_qwen38-27b_dflash2-final.env`
（派生，勿手改；`gen_final_env.py --check` 可验）

**已通过验收（mock/TinyLM 规模）**
- `controller/measure.py` 双卡配对 + 互换 GPU + bootstrap CI
- `controller/ledger.py` append-only 哈希链（`ledger/rsi.jsonl` 8 条，chain OK）
- `controller/landlock.py` G3 9/9；`controller/token_force.py` G4 5/5
- `orchestrator/loop.py` G5 6/6；G2 故障续跑 6/6
- 噪声标定 3.11%，晋升阈值 = 1% + 2×噪声 = 7.21%

**已通过验收（真实 27B + DFlash2，本机 2×H100）**
- P0 stock server 跑通；P1 派生树 stock 与上游树逐 token 一致
- P3 三臂各起一次真 server 并跑完同一请求集（`docs/09`）

**空壳 / 未做**
- `eval/sealed` 空（`eval/dev` 已由 `assets/upstream/dev` 供给，5 suite × 20 条）；
  `memory/entries/rsi.json` 是 mock 结果
- `exp/run_e2e.sh` 用 TinyLM，不是真引擎
- **NorthJob 的 20 请求/2048-cap A1/A2/A3 已完成；论文完整 dev/sealed、真实 forcing/噪声/晋升仍未完成**
- `harness/make_traces.py`：自蒸馏语料生成，**WIP，不在主路径上**（DFlash2 已是训练好的 drafter，
  不需要自蒸馏）。保留但不要依赖。
- `harness/qwen_backend.py` / `qwen_spec.py`：自写前向，与 HF 数值一致（max diff 0.0），
  修好了 `is_causal` 在 `S>T` 时左上对齐的坑。**但不作为主引擎**（AR 35 tok/s，launch-bound
  会污染成本结构：让"加大 block"被高估、"省字节"显示零收益）。

## 9. 论文关键数字（用于对齐，不是结论）

`h100_c1_qwen38-27b_dflash2`：stock/AR 3.95×，final/AR 8.86×，
final/stock **2.13× `[2.07, 2.19]`**，τ 4.65 → 13.08。

> 基准取值只看 `assets/upstream/configs/h100_c1_qwen38-27b_dflash2/config.json` 的 `paper` 段
> （`sealed_final_vs_stock = 2.13x [2.07, 2.19]`）。上游 README 的 2.24× 来自 dev 表格的
> 8.86/3.95，与 sealed 的 2.13× 是不同请求协议，不应简单称为配置冲突。
> **sealed 目标以 config 为准**，dev/AR 对照单独报告，不在口径之间漂移。

成本拆解：ceiling 2.57× = τ 1.83 × overhead 1.01 × kernel 1.39。
单请求 27B：读权重占 23.61 ms 步时的 80%；GEMM 1 行 17.88 ms vs 64 行 18.58 ms（行数几乎免费）。

## 10. 工作方式

- 中文回答，直接不铺垫，单条回复别太长。
- 大输出落盘，`tail`/`grep`/限定行数回读。
- 跨轮状态外置到文件（`ledger/` 测量、`docs/` 决策、`AGENTS.md` 约定）。
- 所有 `exec_command` 需 `sandbox_permissions: require_escalated`。
- 每完成一步就跑一次验收命令。

## 11. NorthJob 提交规矩

提交前必须：① `northjob get --keyword <name>` 查重名；② 显示最终命令 + 资源摘要；
③ **image 显式确认**（`--k8s-images`）；④ 核对 `code == 200` 且 `data.job_uuid` 存在。
总 GPU > 32 且含推断项要二次确认。
