# 公开仓库发布审查与同步

日期：2026-11-09。用户确认origin是本人主动改为public，并批准公开发布审查、更新记录及推送。
不修改仓库可见性，不启动GPU或模型研究，不改变controller/验收规则/账本。

## 目标与范围

解除此前“仅授权私有同步”的历史阻塞，将本地`60a601b`及本阶段文档更新安全同步至既有仓库。
用户随后明确仓库已转入组织`china-qijizhifeng`，当前目标为
`https://github.com/china-qijizhifeng/SpecPilot-reproduction.git`。
审查范围是远端main基准之后的全部待发布提交及最终暂存内容，不只看最终差异，避免漏掉中间提交中的泄露。
已在远端的历史不是本次全量安全审计对象；不宣称整个公开仓库无任何隐私/许可风险。
审查不读取sealed或任何实际凭据，扫描只读Git对象；原始证据与日志仍留本地持久存储。
推送认证沿用既有Git credential helper，仅在Git子进程内使用，不输出凭据、不更改全局认证配置。

## 验收先行

执行环境：`/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python`。
本阶段输出：`logs/public-sync-20261109-a01/`，审查脚本也存该目录，不增加产品框架。

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
OUT=logs/public-sync-20261109-a01
BASE=2e069e6c0148f440e79e68643300813119ea0c48
"$PY" -B "$OUT/review_publication.py" --base "$BASE" --head HEAD --out "$OUT/review-before.json"
# 更新文档并暂存后，检查所有待发布历史和最终暂存树
"$PY" -B "$OUT/review_publication.py" --base "$BASE" --head HEAD --index --out "$OUT/review-staged.json"
"$PY" -B "$OUT/document_checks.py"
git diff --check
git diff --cached --check
git diff --exit-code "$BASE" -- controller orchestrator patches costmodel assets/upstream eval ledger memory
# 文档检查：本地链接有效、四条铁律保留、当前授权和下一GPU阶段待批准状态一致
# 提交后重跑相同审查，推送后要求 git rev-parse HEAD == git ls-remote origin refs/heads/main
```

自动审查的工程fixture必须检出虚构token/私钥/认证URL/受限路径/二进制等反例，并允许普通路径/哈希/凭据字段名。
不打印可能的敏感值；只记文件、行号、类别。自动规则不能证明绝无泄露，须配合逐文件人工审查。
本机没有现成gitleaks/trufflehog/detect-secrets命令，本次不安装或下载新工具。

## 发布规则与许可检查

- 不提交sealed、真实请求/输出、模型数据、运行日志、profile、源快照归档或凭据文件。
- 检查常见密钥/私钥/认证URL和硬编码口令模式；发现真实高风险信息时停止推送。
  若风险存在于待发布的旧提交，后续删除不等于清除历史，不擅自重写历史或强制推送。
- 逐文件确认新增实现与测试为本项目代码，没有本次新增的第三方模型/数据/作者final覆盖层或其他vendor代码。
  导入现有依赖不等于重新分发它们；本次不新增许可证或宣称完成全仓库许可审计。
- 本地安装路径、非敏感canary身份、任务索引与SHA是环境/审计元数据，不是认证材料。
  新增探针含不带认证的RFC1918代理地址及本地用户名/路径；本次保留用于说明真实执行环境，
  不宣称已隐藏全部基础设施元信息，也不发布实际配置/认证文件内容。
- 每次同步核对精确origin、远端基准及发布集合；按用户确认将旧origin更新为组织地址，
  不创建分支、不改变可见性、不强推。

## 停止条件

发现高风险敏感信息、未获许可的第三方内容、非预期文件/远端变更、验收失败即停止推送并保留证据。
网络返回不明确先核对远端commit，不能把push命令返回当作唯一成功证据。
公开授权只解决发布权限，不授权下一阶段GPU接入、资源预算或实验。

## 结果与接续

本次重新运行278项harness CPU回归全部通过（33.797秒），没有修改或重跑模型/GPU研究。
真实探针独立审计与原结果字节一致；旧588文件SHA清单全量复验通过，原失败/阻塞回执不改写。
发布规则的16项合成正反例自检通过；初次待发布提交`60a601b`的14个文件版本未触发高风险规则。
逐文件审查未发现本次新增的模型数据、原始请求/输出、凭据文件或第三方vendor代码。
本次产品代码与`60a601b`完全相同，新增审查脚本及原始验收产物仅留被忽略的logs目录。

最终暂存树和提交后的全部待发布历史还须分别通过相同审查；推送只走正常fast-forward，
推送后核对本地HEAD、组织origin/main及GitHub API的main commit一致。
最终同步回执为`logs/public-sync-20261109-git-sync.json`，在提交/推送后生成，不放入自引用清单。
若同步未通过，回执必须如实记录，不以本地验收通过替代同步成功。

同步后的下一主线仍为审核`docs/experiments/codex-gpu-autonomy-proposal-20261109.md`，
由Master分方向、direction自主实验、controller独立验收；本阶段不启动该流程。

### 组织转移核对

初次对GitHub响应的full_name做旧名称相等检查失败，保留为本次预检失败，不把它当网络/模型失败。
后续用户确认组织转移，且已独立核实：旧API地址正式重定向到`/repositories/1449067162`，
组织API返回同一numeric ID/node ID，两Git地址main均为基准`2e069e6c0148f440e79e68643300813119ea0c48`。
因此更新本地origin至用户给定组织地址，不是向另一个同名仓库盲目推送。
核对证据为`logs/public-sync-20261109-a01/redirect-identity.json`，不更改服务端可见性。

### 归档与最终版本核对

- 发布准备证据13文件、43,819逻辑字节；清单`logs/public-sync-evidence-20261109-a01.sha256`，
  SHA256=`dd1d64ac6a807287403502d27b6f7569a724fa58a68fa6b6e1d03da40200af7a`，全部校验通过。
  包含审查脚本、16项fixture自检、预检失败说明、身份/权限预检、CPU回归、旧探针审计和暂存预审结果。
- 暂存预审覆盖原14文件版本与本次7份文档版本，共21个版本，无高风险规则命中；
  文档检查9份文件、66个本地链接，四条铁律、产品代码及保护路径均未改。
- 为避免自引用，清单不含本节补写后的最终提交审查和Git同步回执；
  最终提交审查另存`logs/public-sync-final-review-20261109.json`，其SHA由最终同步回执绑定。
- 正式push前必须重审最终提交的所有待发布历史，push后核对Git和GitHub API的main身份。
  认证dry-run已成功，使用原有helper的单进程配置，不读取/打印明文凭据给审查脚本或对话。
- 本阶段GPU提交0、新模型研究轮0；下一GPU阶段仍待用户批准。
- 提交前曾遇到一次GitHub TLS unexpected EOF，尚未到达commit/push；第一次只读重查即恢复，main仍为原基准。
  保留`logs/public-sync-network-check-20261109.json`，未关闭TLS校验、未改全局网络配置或盲目重推。
