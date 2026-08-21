# ALB_MAIN Claude Code 指令

本文件保存 Claude Code 在本仓库工作时需要遵守的稳定项目级指令。只保留跨会话稳定的约束；当前状态、远程路径和模型形状等易变事实保留在各自的状态文档或实现中。


## 环境与命令

- Python：`E:/Anaconda2023/envs/ALB/python.exe`。
- Windows、远程工作站或 Task Scheduler 流程需要 PowerShell 时，显式调用 PowerShell 7（`pwsh`）；服务环境优先使用 `C:/Program Files/PowerShell/7/pwsh.exe`。
- 有依赖关系的命令应在前一命令成功后才继续；仅在命令互相独立或目标 wrapper 明确要求时使用 `;`。
- 以当前活动 Git worktree 的仓库根目录为工作目标，不将主 checkout 的绝对路径作为固定写入目标。

## 代码约定

- 咨询、解释、审查、调查和方案请求默认只读。对“修复、实现、更新、重构、迁移、补充测试”等动作型请求，视为已授权在用户指定范围内修改；删除或覆盖重要资产、外部发布及其他高风险操作仍需单独确认。
- 对小型或轻量请求，优先复用现有脚本、CLI、配置和已记录命令，再考虑新增代码。
- 所有代码注释必须使用英文。
- 新脚本应以简短英文注释说明主流程、假设和非显然步骤；不要为显然代码添加注释。
- package/module 代码必须为 public API、重要数据契约和非平凡逻辑提供完整、可维护的 docstring 和注释。

## 编码策略

- 本项目所有文本文件默认使用 UTF-8 读取和写入，包括中文文档、Markdown、Python、TOML、JSON/JSON5、YAML、PowerShell 和 shell 脚本。
- 读取旧文件时，如果 UTF-8 解码失败，可以对明确的 legacy 文件临时 fallback 到 GBK/CP936，但必须在报告中说明；不要静默按 GBK/CP936 处理。
- fallback 读取的文件不要直接写回原编码；若需要修改，应先明确转换为 UTF-8，再按 UTF-8 写入。
- 机器消费的配置、命令、协议文本和长期规则优先使用 ASCII 标点；正常中文人类文档不受此限制。


## 文档语言

- 本仓库面向人类用户的规定、概览、维护、审计和操作手册类文档使用中文；进入兄弟项目后遵循该项目自己的指令文件。
- `docs/current_state.md` 是 ALB_MAIN 当前状况的首要入口，必须使用中文维护。
- 源码中的代码注释、docstring、实现说明、嵌入源码的 CLI help 文本和生成脚本注释保持英文。
- 维护类人类可读文档已部分使用英文时，把本次实际编辑的段落转向中文，不扩大到无关段落。

## ALB 包定位

- 修改 public API、包级导出、namespace 边界、跨模块架构或代码归属前，阅读 `docs/alb_package_overview.md`。局部私有实现修改只需确认不改变这些契约。
- 新增或改变 public API 时，同时更新模块 docstring/comment 和包概览。
- 可复用数值代码保留在 `ALB_MAIN/ALB`；`SURROGATE_TRAIN` 等兄弟项目应 import 这里的 ALB 包代码，不要复制。

## 文档角色边界

- 修改状态、维护、运行、归属、索引或操作手册类文档，或跨文档迁移事实前，阅读 `docs/daily_maintenance/daily_doc_update_index.md` 和目标文档本地的 `文档角色` 区块。普通源码配套文档的局部修正无需固定读取集中索引。
- 如果集中索引和目标文档的冲突影响本次修改，停止并报告冲突。
- ALB_MAIN 当前开发阶段、已确认基线、验证状态、风险和近期下一步属于 `docs/current_state.md`；SURROGATE_TRAIN 实时运行状态属于 `../SURROGATE_TRAIN/docs/current_runtime_status.md`；每日耐久 ALBNN 历史属于 `../SURROGATE_TRAIN/docs/albnn_training_log.md`；稳定远程机制属于 `docs/remote_workstation_connection.md`。
- `docs/current_state.md` 是可随当前事实重写的项目状态入口，不是完整历史日志。只在 ALB_MAIN 的开发阶段、工作重点、验证结论、风险或下一步发生实质变化时更新；旧状态压缩为结论，不持续堆叠时间线。不得把兄弟项目的训练 tick、远程 PID、loss、ETA 或论文任务进度写入其中。

## Run 与当前状态定位

- 涉及项目现状、发布、迁移、包重构、活跃 run、远程任务、ALBNN 训练或跨项目协作时，先读取拥有项目的 current-status 文档，再按其中的证据指针检查实际 Git、测试和代码状态。
- ALB_MAIN 使用 `docs/current_state.md`；SURROGATE_TRAIN 使用 `../SURROGATE_TRAIN/docs/current_runtime_status.md`；论文任务使用 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。
- 新建或编号 run 时读取 `docs/run_index.md`。活跃 run 区块应能定位 config、outputs、日志指针、远程任务名、最新进度、当前问题和下一步；详细原始证据保留在 artifacts 中，已完成 run 的耐久历史属于对应的时间顺序 log。

## 文件、路径与命名约束

- 判断资产归属、清理或归档策略时读取 `docs/file_classification.md`；判断当前阶段和基线时读取 `docs/current_state.md`；普通源码和测试编辑不需要读取全部管理文档。
- 新建、迁移或复制文件前，先检查目标任务已有命名方式和目录结构。除非用户明确要求重构目录，不要把数据、脚本、日志、note 和图件平铺混放在同一目录。
- `ALB_MAIN` 仓库只放稳定包代码、项目文档、回归参考、测试和工程验证资产。论文任务的计算脚本、任务日志和绘图数据默认不放入 `ALB_MAIN`。
- 进入 `F:/BaiduSyncdisk/博士论文/PAPER_WORK` 前先读取该工作区的 `AGENTS.md`。
- 清理或压缩文档时，只压缩叙事和过时状态；`.csv`、`.json`、`.log`、`.pth`、`.pkl` 等原始证据不因文档整理而删除，删除或归档必须另行确认。

## ALBNN 与远程操作

- 做 ALBNN 采样或训练判断前，读取 `../SURROGATE_TRAIN/docs/albnn_training_brief.md` 和 live 的 `../SURROGATE_TRAIN/task/task_albnn_data.py`；日期历史位于 `../SURROGATE_TRAIN/docs/albnn_training_log.md`。不要在本文件复制当前输入、输出或运行状态。
- 开展远程连接、长任务启动、queue/start/status 或 wrapper 操作前，阅读 `docs/remote_workstation_connection.md`，并以其中的当前机制和路径为准。
- 启动远程 ALBNN training 时默认同时启动 monitoring；优先采用当前远程操作文档指定的受监督 queue 流程。
- 不要把密码、私钥、恢复码或 API key 写入仓库、日志、命令参数或回复。使用 OS credential manager、SSH agent 或其他本地 secret store。
