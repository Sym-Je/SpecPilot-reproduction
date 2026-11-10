# H100 源码 option 自主研究（2026-11-10）

本阶段暂停，以下为历史准备/失败记录，不是当前待办。当前执行与结果以HANDOFF/PLANS及
`ceiling-20261110.md`为准；不恢复旧预算、预检或科学研究。

## 授权与目标

本阶段已获用户批准：累计16 H100 GPU小时、最长12小时、最多并发2卡，失败、排队和冷启动保守计入。
独立预算不结转旧阶段余额。镜像沿用已验证digest
`6e9415fcf90dbe66f14e994a7f7c51cb242db3805b1910ce7bd6d0b8e8db0798`；
项目WeaverDev，namespace/请求queue为qiji，沿用既有toleration和只读模型PVC。
不增加privileged、host网络或集群权限；不接管Ascend/DSH轨道。

目标是补齐现有startup option之后的源码机制执行能力：Master选方向，direction自己实现、实验、修复与停止。
主助手只维护通用工具，不代写优化、不指定VERIFY或作者final机制，不要求正收益。

## 先写验收，再实现

1. `python -B -m unittest harness.test_source_candidate`：严格文件路径/大小/哈希、CPU回执绑定、源码冻结、默认stock与篡改拒绝。
2. `python -B -m unittest harness.test_source_boundary`：真实无敏感文件探针，授权读取/缓存写入成功，保护文件读取/写入、源码写入、越权进程操作和额外设备访问拒绝；边界不可用则拒绝执行源码。
3. `python -B -m unittest discover -s harness -p 'test_p*.py'` 和 `python -B -m unittest harness.test_engine_research`：既有H100 CPU回归不退化；不改变原controller和判据。
4. GPU预检先于研究源码：核对实际H100、引擎版本、UID/文件/进程边界与默认路径，冻结当前可信入口。
5. 每个源码请求必须绑定direction的原生回包、当前CPU自检成功回执和文件SHA；实现只能进入独立stock副本。默认关闭直接选择原stock，不能执行候选源码后声称默认未变。
6. GPU请求经唯一可信broker：固定镜像/项目/挂载、持久预算预留、查重、展示完整命令与总GPU、单次create、code200与UUID独立核对；不确定不重提。
7. 真实研究固定同请求、两轮fresh server与GPU互换。诊断只用公开dev；有候选才交未修改的controller，不读取sealed、不自动晋升。
8. 原始退出码/失败日志交回direction；科学修复由direction完成，Master决定继续/停止。收尾分别报告通路/科学实验/正式验收是否完成。
9. 核对任务和角色终态、预算、保护目录零改动、原始证据SHA，更新README/PLANS/HANDOFF，公开审查后提交并推送。

## 能力与安全边界

首版仅接受有界Python文件替换，目标限定授权stock的`python/sglang/srt/`既有文件，不接受shell、构建脚本、启动器或作者final。
开关是可信层选择stock/冻结候选树；关闭时不导入候选代码。各候选独立身份，不开放integration。
源码server需要SGLang本身的子进程/IPC/JIT能力，不能直接复用禁止所有子进程的微实验沙箱。
必须先验证新的继承式内核文件边界和进程身份；不能用AST扫描、提示词或事后哈希代替运行时隔离。
具体可用范围以真实预检为准；若当前容器不能建立必要边界，则停止源码执行并明确记录阻塞。

## 最新接续

用户要求按完整多角色主线重新规划，暂不新增提交。9个预检均已终止，累计1996 GPU秒，未启动科学Master/direction。
第7次受限真实GPU运算及父进程环境保护通过；第8次完整server缺少系统MIME表读取，第9次加载权重后因ldconfig执行受限失败。
旧信号限制阻碍SGLang清理自身子进程；只对第9任务的身份匹配server进行清理，任务已终止。
当前工作树已补固定ldconfig/numactl工具和同UID自身子进程信号能力，跨UID仍由操作系统拒绝；**最新修复尚未复验**。
源码通路本身及科学目标均不能宣布完成。下一提案须包含多个direction、Integration组合、Kernel研究及独立dev验收；sealed不自动启动。

## 准备过程记录（历史checkpoint）

- 已核对起点`585b4d9`与干净工作树；已读交接/计划及NorthJob skill，当前CLI支持所需参数。
- 已确认本阶段资源与镜像/项目/挂载；尚无源码研究或性能结果。
- 源码冻结/默认stock/回执绑定及真实本机边界13项检查通过，303项既有CPU回归通过。
  18项engine检查首次遇到临时端口占用，未改旧测试，重新执行通过；失败日志保留。
- GPU预检按独立名称逐次提交，均先查重、核对code200与UUID；前四任务已结束，累计414 GPU秒。
  第一任务因nvidia-smi不支持minor_number查询失败，改为NVML；之后确认独立UID及文件/进程/设备拒绝探针生效，但CUDA初始化报304。
- 第四次受信诊断明确：UID-only与seccomp-only可执行真实GPU矩阵乘；文件边界单独开启时失败。
  扩展系统只读目录、仅改变设备选择格式不是正式安全通路；任何诊断放宽都不用于运行研究源码。
- 第五次预检正定位具体被拒绝路径；主助手维护的C访问诊断钩子只用于受信探针，不进入科学计时。
  后续源版本单独冻结，不声称早先运行热加载了加固；旧startup研究不算本阶段源码发现。
