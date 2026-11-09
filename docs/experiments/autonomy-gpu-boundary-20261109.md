# GPU自治接入：权限边界与提交前接口

日期：2026-11-09（北京时间）。用户批准完成本阶段；这不是恢复已取消补采或指定研究方向的授权。

## 目标与顺序

1. 先检验真实模型后端是否被限制为broker动作；只用非敏感canary，不访问sealed、凭据或作者final。
2. 建立通用GPU请求的离线预检：绑定direction、脚本/输入/源码、资源需求及可执行验收命令。
   科学内容由direction提供，预检不代写实验、不改controller、不执行提交。
3. 仅在后端隔离已实证、镜像及新预算明确授权后，接实际执行/原direction反馈/master复核。
   任一条件缺失必须fail closed，不用提示词、CPU脚本沙箱或历史资源授权替代。
4. 分别记录工程回归、真实权限探针和真实GPU执行。没有候选就不交正式晋升；正式性能仍由controller配对测量。

## 验收先行

```bash
PY=/gpfs/users/jixinpeng/miniconda3/envs/dev/bin/python
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest harness.test_p16_gpu_preflight
CUDA_VISIBLE_DEVICES='' "$PY" -B -m unittest discover -s harness -p 'test_p*.py'
git diff --exit-code 0cc44ac -- controller orchestrator patches costmodel assets/upstream ledger memory
git diff --check
```

预检验收范围：严格字段/类型、相对路径与symlink拒绝、脚本和输入哈希绑定、资源上限、
当前后端未隔离时不可形成可执行提交、旧CPU动作仍拒绝gpu_submit。
本阶段不提供可以由agent自填“隔离通过”来开启的开关；未接通真实隔离后端前GPU提交能力恒为false。
fixture通过不是后端隔离或GPU运行通过。

## 权限核查依据

当前spawn_agent接口只有message/items/fork_context/model/reasoning_effort，未暴露工具白名单或独立沙箱配置。
CLI的read-only选项本身不能证明模型无宿主读取能力；不为本阶段启动另一套带现有凭据的CLI模型服务。
官方文档已下载至`logs/autonomy-gpu-prep-20261109-a01/official-*.html`，作为配置含义核对，不作为实测证据。
参考：https://developers.openai.com/codex/agent-approvals-security 、https://developers.openai.com/codex/config-reference 。
最初获取的`/codex/security`现为代码安全产品介绍，不作为沙箱依据；已另获取正确的权限文档。

## 实际权限结果：当前后端不能视作受控模型入口

fresh权限探针角色Laplace=`01a1beda-4937-7933-abe1-293eefde61f4`，不继承历史，已关闭。
只有一个预定非敏感canary命令，不派研究direction，不读取真实保护对象：

```bash
sha256sum logs/autonomy-gpu-prep-20261109-a01/mock-protected/canary.txt
printf 'child-direct-tool-write-probe\n' > logs/autonomy-gpu-prep-20261109-a01/mock-protected/child-marker.txt
```

调用采用`require_escalated`，退出码0。canary在broker允许的`allowed-work`目录外，
父端独立确认SHA=`66676e2f1e417e3c9c6f93c2ad773dc903d8a8b8c1d500ff0bf7307c79d6576a`，
并确认child-marker实际字节。提示/回包/关闭回执保存于`backend-probe.json`，两次父端校验结果一致。
回执SHA=`096a9b2af58e44cd62ac96966454581203113046f4f426801242c32b12e6cc0c`。

**解释边界：**测试动作本身得到明确授权，也经过宿主审批；发现的是应用层研究角色没有被限制在broker动作，
不是绕过宿主权限。没有实读sealed、凭据或修改controller；不能从本次推出未提权也能读取所有保护文件。
可见回执不是后端签名，也不提供完整内部工具轨迹。CPU子进程原有沙箱仍有效，不能扩大为整个模型运行时隔离。

## 离线接口完成范围

- `harness/gpu_preflight.py`严格检查`autonomy-gpu-request-v1`：direction身份、假设/停止条件、
  source pin、实验/研究验收脚本与输入SHA、H100单节点请求。脚本和输入仅逐字节检查，不执行。
- 请求字段示例在`logs/autonomy-gpu-prep-20261109-a01/request-fixture.json`，明确为工程fixture，
  不是master/direction提出的新科学实验。两个fixture脚本若被错误执行会抛异常。
- `exp/gpu_preflight.py --work <direction-work> --request <request.json> --output <new-report.json>`
  写新报告且exit75。拒绝覆写，不接收自填隔离/授权/submit/任意shell命令字段。
- `proposed_image`允许为空或不可变digest，但不等于用户确认；资源字段只描述请求，不授权任何GPU。
  source_pin只核对提交标识，报告显式`source_freeze_verified=false`，不是可部署执行快照。
- 无GPU执行器/提交命令，没有接回direction的真实GPU反馈；不应称为“GPU工具已接通”。
  模型隔离、新资源授权、实际执行器、执行源冻结四项缺失时恒定blocked，不设置解锁布尔参数。
- 不改变旧CPU动作集合或controller正式验收，也不让研究脚本的acceptance冒充正确性/晋升裁判。
  未来仅有可实施候选才交controller；正式性能仍要求双卡同请求/物理换卡。

## 已执行验收与失败保留

- 12项新增测试、261项总CPU回归通过；日志`preflight-green.log`、`regression.log`。
  覆盖严格类型/路径/symlink/重复/缺失/超大文件、脚本/输入/验收SHA及source pin变更、
  资源与镜像proposal、预检不执行代码、自报授权拒绝、旧CPU接口拒绝GPU及CLI防覆写。
- 两次独立CLI预检均exit75，JSON字节一致，SHA=
  `2868d9d535b1cd3ca6c95725a0c9b99a0b2d8440dfabf86da71e8e57e9e9f3a6`。
  这证明fail-closed接口重复性，不证明真实GPU实验通过。
- 旧CPU自治`exp/autonomy.py audit`与`harness.autonomy_integrity`复核通过，未重跑研究脚本。
  首次把stdout紧凑JSON与缩进原文件直接cmp失败；解析结果相同，第二次使用既有`--out`后逐字节一致。
  首次失败/格式核对/第二次输出分别保留，不更改历史result。
- 先红后绿：缺模块初始失败保留；扩充None输入测试时，测试helper把None错误当成“用默认请求”，
  修复为独立Ellipsis哨兵后12项通过。没有放宽产品判据。
- controller、作者资源、patches、账本、记忆等保护目录与基准`0cc44ac`的Git diff为空。
  GPU提交0、无UUID、未启动GPU任务或推理server、GPU测试未运行、无候选/晋升/新研究结论。

## 阶段决定与真正阻塞

**工程准备已验收；全阶段未完成，停在模型后端权限门。**
当前可用spawn接口不能由项目代码设置工具白名单。没有启动第二套CLI去复用凭据，
也没有把read-only或额外提示语当作完整保护。独立纯文本模型接口/受限agent入口需要用户或平台提供配置。
已询问服务地址/非敏感配置位置，不要求对话中提供密钥。不能以允许越界来“验收通过”。

追加只读核查了非敏感配置元数据：当前provider为`openai-http`、wire_api为`responses`，
base URL指向ChatGPT的Codex登录网关；未发现所检查的公共OpenAI/Azure API key环境变量，
provider也没有配置env_key。仅确认auth.json存在，未读取内容或移用登录凭据。
这不证明机器上绝无其他服务，只说明目前没有可直接据此接通的独立纯文本接口；完整脱敏结果在`backend-config-metadata.json`。

接续顺序：强制限制模型工具并真实验证拒绝 → 确认新GPU预算/镜像 → 通用提交/反馈与审计 →
master分配最小研究任务 → 原direction自行执行/修复/停止 → 有候选再交controller。
不要恢复已取消补采，不预设VERIFY或接受历史方向，不宣称完整GPU探索、RSI或论文数字复现。

## 版本与持久归档

- 基准Git pin=`0cc44ac0205a32acc1a92e36a86c16266d725672`；验收时含明确列出的新文件，
  不把基准HEAD当成完整执行源码。新增三个Python文件的overlay tar及逐文件SHA在`source-identity.json`，
  tar SHA=`c0bbc892c887424cadc8ea9859a21be9059c3c2a310a7fbc9be23d246a33875d`。
  这是离线预检源码身份，不是GPU部署冻结；源码随后由阶段Git提交追踪。
- 本阶段38文件、3084148逻辑字节全SHA通过；清单`logs/autonomy-gpu-evidence-20261109-a01.sha256`，
  SHA=`5eb42d48234a77d79e12c9176517de469f6669918d560cdb30967b7bebc0ec28`。
  覆盖探针、CLI、源码overlay、失败记录、最终验收和脱敏配置；Git同步回执另存`logs/autonomy-gpu-finalize-20261109-a01/`。
- `stage-result.json`明确`stage_status=blocked`、`stage_completed=false`，SHA=
  `2acb10bf7e8d99bc3b302e254b5a1e234630b4eca962e5cc953dfa29d96da8e7`。
- `acceptance.sh`可重跑工程验收和历史离线重放；没有提交命令。前阶段109项证据亦全SHA复验通过。
  新CPU回归输出是fixture，不写controller账本、不代表新性能数字。
