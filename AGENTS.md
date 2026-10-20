# ALB_MAIN 代理指令

## 环境与路径

以当前活动 Git worktree 的仓库根目录为工作目标。

| 项目 | 路径 |
| --- | --- |
| Python | `E:/Anaconda2023/envs/ALB/python.exe` |
| PowerShell 7 | `C:/Program Files/PowerShell/7/pwsh.exe` |
| 包代码 | `ALB/` |
| 测试 | `tests/` |
| 工具 | `tools/` |
| 行为参考 | `refs/` |
| 项目记录 | `docs/current_state.md` |
| 包概览与架构 | `docs/alb_package_overview.md`、`docs/interface_architecture.md` |
| API 说明与生成入口 | `docs/api/README.md` |
| 文件与运行路径说明 | `docs/file_classification.md`、`docs/run_index.md` |
| 文档路径索引 | `docs/daily_maintenance/daily_doc_update_index.md` |
| 远程操作说明 | `docs/remote_workstation_connection.md` |
| 训练项目运行记录 | `../SURROGATE_TRAIN/docs/current_runtime_status.md` |
| ALBNN 训练说明与历史记录 | `../SURROGATE_TRAIN/docs/albnn_training_brief.md`、`../SURROGATE_TRAIN/docs/albnn_training_log.md` |
| ALBNN 数据任务入口 | `../SURROGATE_TRAIN/task/task_albnn_data.py` |
| 论文工作区与约束 | `F:/BaiduSyncdisk/博士论文/PAPER_WORK/`、该目录的 `AGENTS.md` |
| 论文任务记录 | `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md` |

## 任务与文件约束

- 咨询、解释、扫描、审查和方案请求默认只读。动作型请求授权完成指定范围内的必要修改。
- 已有明确授权不重复确认。未涵盖的破坏性删除、重要资产覆盖、外部发布或权限变化，先说明范围并确认。
- 仿真参数的含义、单位或取值不明确时，直接询问用户，确认后再执行依赖这些参数的计算；已有明确约定的参数不重复确认。
- 保留与任务无关的用户改动，不使用 `git reset --hard` 处理混合工作树。
- 在文件所属项目落地修改。兄弟项目 import 本包，不复制 `ALB/` 实现；论文计算脚本、日志、绘图数据和图件放在论文工作区。
- 新建或迁移文件沿用目标任务的命名与目录结构。小型任务优先复用已有脚本、CLI、配置和命令。
- 原始 CSV、JSON、日志、模型、pickle、图件与冻结参考不因文档精简而删除或归档；资产操作按明确授权执行。
- 递归清理前解析并核验绝对目标路径处于指定范围。

## 代码、编码与验证约束

- Windows、远程工作站或 Task Scheduler 流程需要 PowerShell 时使用 PowerShell 7 (`pwsh`)。
- 有依赖关系的命令仅在前一步成功后继续；兼容旧 shell 时检查退出码。`;` 只表示顺序执行，不作为成功条件。
- 源码注释、docstring、实现说明、嵌入源码的 CLI help 和生成脚本注释使用英文。注释说明主流程、假设和非显然步骤。
- public API、重要数据契约和非平凡逻辑保留可维护的 docstring 与注释。
- 文本按 UTF-8 读取，写入 UTF-8 无 BOM。明确的 legacy 文件需要 GBK/CP936 fallback 时报告使用情况，修改前明确转换编码，不静默写回旧编码。
- 机器消费的配置、命令和协议文本优先使用 ASCII 标点；人类说明默认使用中文，正常中文正文可使用中文标点。
- 验证范围随实际改动确定。数值或行为修改遵循已确认的参考与验收要求；文档检查不代替数值验证。
- 历史测试结果标明适用版本或提交，机器报告记录真实执行结果。
- 公开接口变化时修正实际受影响的说明和引用。

## ALBNN 与远程操作约束

- ALBNN 输入输出形状以当前数据、配置和实现为准。
- 远程端点、任务名和 wrapper 路径以实际配置为准。
- 远程 ALBNN training 默认同时启动 monitoring，优先复用现有受监督 queue 流程。
- 活跃 run 保留可定位的配置、输出、日志和远程任务名。
- 密码、私钥、恢复码和 API key 不写入仓库、日志、命令参数或回复；使用 OS credential manager、SSH agent 或本地 secret store。
