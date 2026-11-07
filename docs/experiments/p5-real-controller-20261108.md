# 第5步：真实校准与token-forcing裁判

日期：2026-11-08（Asia/Shanghai）。状态：执行前登记。
基准`e6e55a6f4c3535c8f0515ee0654e95fb2d684b4f`。用户明确允许本阶段修改controller，
授权仅限校准与正确性验收；阶段内部自主调试，不自动sealed/RSI/正式晋升，不放宽正确性要求。

## 顺序与先验收契约

1. CPU契约先红再实现：版本化paper-aligned校准、完整teacher-forced分数解析、margin-aware判定；
   保留所有legacy默认行为，不改旧JSON/失败记录。无校准或真实分数时必须fail closed。
2. 先做一次NorthJob接口探针，原镜像/WeaverDev/qiji/原toleration，1节点×2 H100/256Gi。
   GPU0普通AR、GPU1 stock-tree FP32-head scorer；只检查公开接口、分数对齐、logit_bias和hidden states。
   这是正确性探针，不是性能测量，没有stock/final新加速比或晋升。
3. 接口验证后冻结完整正式dev正确性协议，在同一20个A1 dev请求上做fresh AR/stock生成及评分、
   stock首次偏离AR的δ标定、正常重复对照；4096-cap故障实验在满足长度条件的固定请求范围执行。
   不读取作者机制实现，不修改引擎文件，不使用sealed，也不重跑AR/stock/final性能基线。
4. 新旧CPU回归、真实判据、证据重放/校验、生命周期/清理分别验收，更新首页/交接并提交推送。

### 校准与性能策略（显式新API，旧API保持）

- 噪声使用匹配协议的stock null、suite等权request-cluster log bootstrap，固定10000次/seed0，
  使用双侧95%CI的保守下端作为性能下界，明确不是论文指定的具体bootstrap算法。
- noise=`max(abs(L-1),abs(U-1))`；对事先指定的全部独立null会话取最大值，不能挑低噪声会话。
  报告全宽/偏移，但不因0.2%或覆盖1单独拒绝；来源、请求、模型、GPU环境、轮次/采样协议须绑定。
- 新策略必须显式指定`paper-aligned-v1`，无完整匹配校准或真实正确性证据不得给出正式promoted。
  `LB(speedup)-1 > 0.01+2*noise`，输出分歧时还须>0.03。保留旧诊断，不追溯晋升历史结果。

### 真实评分与正确性

- 由controller调用stock引擎`--enable-fp32-lm-head`，对每条待测输出自身上下文做teacher forcing；
  保存原始HTTP请求/响应、server参数/源身份、每个token的argmax/自身log-prob、margin和prefix hash。
  输入和输出均须完整且非空，token/logprob位置必须能用单token前缀探针独立核对；缺失拒绝。
- δ来自本次stock与AR第一次不同处两token的log-prob差，向上取整到1/8；不抄论文0.72%或固定δ。
  缺少实际首次分歧证据时明确报告未能标定，不假装给出论文δ。
- rate rule采用候选mismatch率下界减stock上界>0.005；两边各用单侧97.5% Wilson界，
  是本地Bonferroni保守差值下界选择；需注明token-Bernoulli近似，不冒充论文披露的精确方法。
- event仅计margin>2δ的不匹配。解释必须绑定相同prefix的stock复现或prefill形状敏感性原始证据；
  不接受agent自填explained布尔。无法解释的事件与stock比较，使用有限stock样本的保守上界，
  不把stock零观测当成真实概率零；事件显著性与stock上界合并控制总α=0.05。
- 原token-list诊断仍不是真实forcing，新的正确性通过也不是性能晋升或lossless数学证明。

### 故障与等价控制的覆盖要求

- 真模型生成时原生logit_bias：新生成2048 token之后，对id%7==0的所有词表项加2。
  允许在2048边界拆成两次生成，但健康对照必须使用相同分段，明确与单次server内注入的区别。
  只有实际到达注入位置、发生偏置且有post-2048 token的请求算覆盖；自然EOS过早不能算注入成功。
  不ignore_eos、不编辑已经生成的token、不用随机假token冒充真实注入。
- 等价归约控制优先用同一真实hidden state、同一checkpoint FP32 LM head、不同分块累加顺序，
  检查head/argmax对齐并在真实生成/评分中应用；不将更换权重、降低精度或任意编辑输出称作等价归约。
- 健康stock/等价控制不得被误拒，故障必须由event rule拒绝；任务精度不能代替此验收。
  能力探针不足以宣称上述正式回归已通过，完整协议/覆盖规模在正式运行前继续冻结。

## 执行前验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
"$PY" -B -m unittest discover -s harness -p 'test_p5_scoring.py'
"$PY" -B -m unittest discover -s harness -p 'test_p5_paper_policy.py'
"$PY" -B -m unittest discover -s harness -p 'test_p[235]*.py'
bash -n exp/p5_serve.sh
git diff --check
```

真实探针入口`exp/p5_api_probe.py`，正式forcing/判定入口后续冻结；所有大输出落盘。
每次NorthJob提交前按skill核对help、凭据、路径、查重、展示完整命令/总GPU，create一次，
核对code=200和唯一UUID；镜像沿用用户已确认digest，不静默改镜像或不明确重提。

## 实施与结果

- 新评分/策略7项契约先红（缺模块），实现后新旧105项回归通过；旧98项仍过。
  中间mock漏HTTP status字段导致一次测试失败，补齐fixture后通过，未放宽解析契约。
- 普通公开API构造签名已离线核对，原生SamplingParams支持logit_bias，GenerateReqInput支持
  input logprob/top logprob/hidden states；只说明接口存在，不代表27B真实运行已通过。
- 短探针任务名`specpilot-p5-score-probe-20261108-a01`，查重、冻结与提交结果后续追加。
