# Master外部知识访问：故障定位与最小修复

## 授权与目标

用户批准排查Master公开检索/阅读失败。只诊断并修复可信broker通路，不替Master调研优化方案，
不恢复旧研究，不新增GPU，不读final/sealed，不改controller/验收规则/账本。
阶段目录`logs/public-knowledge-access-20261111-a01/`；保留既有旧ceiling等dirty，不混入提交。

## 先行验收与流程

1. 重放旧三次`network_unavailable`回执，分层检查目标DNS、代理配置、TCP/CONNECT、TLS及响应解析。
   只记录安全的阶段/异常类别/errno，不输出代理地址、凭据、环境全量或原始异常字符串。
2. 定位具体失败后先加失败回归，再做最小修复；不关闭TLS、不移除域名/公网IP/重定向约束，
   不开放任意网络或给研究角色增加宿主工具。
3. 真实执行现有`MasterAccess`公开检索/阅读，核对非空内容、来源/SHA/原始回执及独立离线审计。
   如果需要角色级证明，只启动有界工具连通性探针，不冒充自主研究或新优化发现。
4. 定向回归与公开源码副本验收，保存失败与成功记录，更新主页/计划/交接，审查后提交推送。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
$PY -B -m unittest harness.test_research_knowledge harness.test_master_autonomy \
  harness.test_master_autonomy_audit harness.test_master_decisions
```

标准：真实可访问文本且可审计才算对应入口通过；接口存在、mock通过、空搜索或错误页都不算。
网页读取与搜索分别验收；一种成功不能掩盖另一种失败。联网成功不代表研究能力、正确性或性能收益。

## 根因：正文已读完，却再次操作关闭的socket

旧Master的1次Bing搜索、2次Triton文档/GitHub raw读取都返回network_unavailable。
本阶段重现：三个目标DNS均返回公网地址，已有代理配置有效；经代理实际收到GitHub raw/Triton文档
HTTP 200，以及Bing的302跳转。不是这些请求被角色策略禁止，也不是已证实的DNS/代理不可达。

具体异常出在`https_get`的正文循环：响应带Content-Length，`HTTPResponse.read1`读完最后一块时
自动关闭响应文件及对应连接。循环尚有字节预算，下一轮又对原TLS socket调用`settimeout`，触发
`OSError(errno=9)`，最终被安全错误包装统一转成network_unavailable。正文成功读取也被丢弃。
分层探针、异常帧和响应状态分别在layer-probe、exception-frames、response-state记录中。
直接连接诊断另有超时，不能据此保证绕过代理可用；生产访问仍沿用既有可信代理。

最小修复只有正文循环增加`not response.isclosed()`条件，不再在已到EOF后操作socket。
未关闭证书校验、未改代理、域名/公网IP/重定向/凭据/字节与时间上限；不增加任意联网能力。

## 验收结果

1. 先增加Content-Length=0、小正文和多块正文回归，正长度两个case在旧实现稳定复现errno9。
   修复后通过；已有一个HTTPResponse mock补齐isclosed=False以符合实际接口，没有改科学验收规则。
2. 从真实MasterAccess分别重试原三种访问：搜索获得2条授权结果，Triton文档提取1923字节，
   GitHub raw读取21812字节；均为completed，正文非空，原始回执独立离线审计通过。
3. 另启动一个新的受限Master做**维护者指定的连通性探针**，不恢复旧研究：1原生回合、5工具动作、
   3次CPU额度计费、0脚本执行、0GPU。它亲自发出搜索和两次读取，并如实报告回执/SHA；
   搜索2条/718字节，正文1923/21812字节，与可信结果逐项核对。
4. `probe_audit.py`两次独立运行一致，核对原生工具/答复、请求身份、非空内容/来源、预算和同父
   birth/wait/关闭记录；2个进程exit0。证据在native、native-result、native-closure及probe-audit文件。
5. 243项指定CPU回归通过，不代表仓库全量。角色自身inputs/config/canary持久化到role-context，
   不复制auth/整个home；原生绝对路径不改，临时目录清理后须显式按归档恢复。

本阶段证明三种指定请求的受控访问可用，不保证所有网页/搜索长期可用，也不证明Master已经完成
自主知识调研、产生好方案或完成RSI。既有五阶段研究/BBuf接入不因该网络修复自动升级为完成。

复验（仅离线，不重启原生角色或GPU）：

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
PYTHONPATH=$PWD $PY -B logs/public-knowledge-access-20261111-a01/probe_audit.py
$PY -B -m unittest harness.test_master_decisions harness.test_skill_rsi_audit \
  harness.test_profile_autonomy_audit harness.test_master_autonomy_audit harness.test_master_proposal \
  harness.test_master_autonomy harness.test_research_paging harness.test_research_knowledge \
  harness.test_engine_research harness.test_research_shutdown harness.test_skill_rsi_continue \
  harness.test_master_recovery harness.test_skill_rsi_pipeline
```

## 下一步（另行审核）

让Master实际使用已经修通的工具，自主提出问题、获取并比较公开知识，然后交Direction设计/执行
最便宜的有效实验。不是维护者代查资料后喂答案，不重开旧缩块支线，不先造大型知识库。
外部知识只算有来源的参考，未通过规定验收不能写入可信memory；GPU仍须新资源授权。

## 封存与发布

243项指定CPU检查在工作区和排除旧dirty的公开源码副本均通过；44份非本阶段旧dirty的SHA保持。
公开只提交六份本阶段摘要/源码/测试，不提交原始网页回执、角色轨迹、配置、鉴权或其他旧实验改动。
61文件/731154字节双次全SHA封存，索引`logs/public-knowledge-access-20261111-a01.sha256`，
SHA-256为`d4c66a23471ded50ba8d88892123d5507048497ecfbece0ecd30c12d29f8aa93`。
封存目录不再写入；最终提交/远端身份在独立的`logs/public-knowledge-access-20261111-a01-publication.json`，
以该回执确认同步完成，不修改旧失败证据或既有预算。
