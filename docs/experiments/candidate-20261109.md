# 真实候选接入与 no-op 双卡烟测

日期：2026-11-09 UTC+08；基准 `dc1f2ef9c5bc193e59bd3c128a4563b9a145aacd`。
状态：用户已批准，先写验收再实现。执行日志保留 UTC。

## 目标和范围

新增独立 candidate 的身份、stock同源构建、启动开关、配对和评分接入，不修改controller。
第一版明确只支持一个启动参数option：`draft_tokens`，关闭时固定stock=8。
烟测中开启值也为8，是刻意无行为变化的接线检查，不算新机制或自主发现；
不声称已支持任意源码patch，也不把同token输出当作lossless证明。
candidate engine从stock复制并程序化校验canonical hash，不手工阅读作者引擎实现。
既有AR/stock/final入口保持原样；不碰eval/sealed、ledger或memory。

## 执行前验收命令

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p10_candidate
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p[2356789]*.py'
bash -n exp/candidate_remote.sh
git diff --check
git diff --exit-code dc1f2ef -- controller patches agents costmodel orchestrator assets/upstream
```

先红后绿：stock默认8、有效开关、spec/config/实际engine篡改拒绝、未知字段/非法类型拒绝、
构建不能覆盖已有目录、外链/断链/目录链拒绝且合法内部相对文件链接保留并计入hash、
环境污染清理、实际server参数错配拒绝；
CPU真实HTTP模拟验证fresh双server/物理换卡/原始HTTP捕获/完整请求和输出一致性。
评分复用NativeClient/FP32 stock scorer及controller的原始输出绑定校验，不能自写lossless规则。

## 远程 smoke 预声明

- 已确认镜像沿用 `harbor.local.clusters/bp/oss-sglang@sha256:6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`。
- WeaverDev / namespace qiji / 请求queue qiji，沿用已确认toleration；1节点×2H100、256Gi。
  禁RDMA/hostNetwork；bash/nproc=1。最多1小时，即2GPU小时，不因性能结果追加实验。
- 关闭、开启两种模式分别做两轮fresh双server并物理换卡；每suite1条，共5条已公开dev请求，
  64token cap，自然EOS；合计20pair/40臂行，不把两模式和物理重复当新独立样本。
- 两模式必须都与stock实际输出一致；这只是no-op/default回归，不是一般候选的正确性标准。
  计时数据由既有HttpPairBench产生，但本smoke不提供正式性能/晋升判定，不套历史noise/δ。
- 测速全部结束且GPU释放后，启动stock FP32 scorer，评分全部40条实际输出并核验自身prefix/
  原始生成绑定；不以短烟测估计δ或宣称rate/event门禁通过。
- 记录提交、启动、GPU/接口验收三个独立状态；退出前保存持久产物、清理两卡/端口。
  当前help→任务名查重→展示完整命令/2GPU→create一次→code200+精确UUID；不明先查重。
- 完成后CPU独立重放、SHA归档、更新README/HANDOFF/索引并推送私有origin。

## 执行与结果

- 17项新CPU/真实HTTP测试通过，167项历史回归通过。未修改controller、作者配置/引擎实现或三臂入口。
- 红测试保存于准备目录`red-tests.log`、`red-integration-tests.log`、`red-launch-tests.log`。
  首次实际stock契约因唯一合法内部相对`.clang-format`文件链接被过度拒绝，空`stock-contract.json`
  和`red-internal-symlink.log`保留；修复复制保留内链且canonical hash不变，`stock-contract-02.json`通过。
  只查看链接元数据和程序hash，未手工读作者实现。
- 实际历史server参数schema与新候选启动参数逐项一致，`launch-compatibility.json`无差异；
  这只是静态兼容性证据，不替代本次启动验收。
- 待补实际源码pin、任务UUID、验收和失败证据；本阶段不自动进入真实搜索或sealed。
