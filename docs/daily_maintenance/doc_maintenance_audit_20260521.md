# 文档维护审计 2026-05-21

## 文档角色

- 角色：单次日常审计证据。
- 目的：保存一次文档维护 pass 的检查证据、决策、无变更原因和后续复查项。
- 允许更新：本审计日期检查过的文件、决策、无变更原因、陈旧候选和清理确认清单。
- 禁止更新：源码编辑、运行状态归属、稳定手册内容，以及超出审计证据范围的长期项目摘要。
- 更新节奏：本日期的文档维护 pass 创建或刷新时更新。
- 事实来源 / 相关文档：
  `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`.

## 审计主题

本次为 PowerShell 默认 shell 迁移后的聚焦审计。目标是确认人类可读维护文档和规则文档中，本机默认环境已经统一为 PowerShell 7，且不再把 PowerShell 5.1 或 `powershell.exe` 写成默认入口。

## 审计范围

- `ALB_MAIN/AGENTS.md`
- `SURROGATE_TRAIN/AGENTS.md`
- `ALB_MAIN/docs/remote_workstation_connection.md`
- `ALB_MAIN/docs/alb_package_overview.md`
- `ALB_MAIN/docs/project_overview.md`
- `ALB_MAIN/docs/file_classification.md`
- `SURROGATE_TRAIN/docs/file_classification.md`
- `README.md` 和兄弟项目相关 `README.md`

排除范围：

- `docs/daily_maintenance/logs/` 中的历史 stdout/stderr 证据。
- `outputs/`、`models/`、`data/` 下的运行产物。
- 仅作为历史事故说明出现的旧 PowerShell 5.1 风险文字。

## 检查命令

```powershell
rg -n "PowerShell 5\.1|Shell：PowerShell|powershell\.exe|powershell -NoProfile|pwsh|PowerShell 7" G:/ALB_PROJECTS --glob '*.md' --glob 'README*' --glob 'AGENTS.md' --glob '!**/.git/**' --glob '!**/docs/daily_maintenance/logs/**' --glob '!**/outputs/**' --glob '!**/models/**' --glob '!**/data/**' --glob '!**/__pycache__/**'
```

## 审计结论

- `ALB_MAIN/AGENTS.md` 已明确本机默认 shell 为 PowerShell 7：`pwsh`，常用本机路径为 `C:/Program Files/PowerShell/7/pwsh.exe`。
- `ALB_MAIN/docs/remote_workstation_connection.md` 已把远程 encoded PowerShell 示例改为 `pwsh -NoLogo -NoProfile -EncodedCommand`。
- `ALB_MAIN/docs/alb_package_overview.md` 已记录 `ALB.remote` 默认使用 PowerShell 7，并通过 `ALB_POWERSHELL_EXE` 和 `ALB_POWERSHELL_TASK_EXE` 保留覆盖入口。
- `SURROGATE_TRAIN/AGENTS.md` 已要求本地训练不嵌套 PowerShell launcher；确需 PowerShell 时默认使用 PowerShell 7。
- 未发现稳定文档把 PowerShell 5.1 或 `powershell.exe` 作为当前默认入口。

## 保留项说明

- `ALB_MAIN/docs/remote_workstation_connection.md` 中仍保留“旧 PowerShell 5.1 在 `$ErrorActionPreference = 'Stop'` 与 `2>&1 | Tee-Object` 组合下的风险”说明。这是事故经验和兼容风险说明，不是默认环境声明，应保留。
- Markdown 代码块语言标记 `powershell` 仅用于语法高亮，不代表默认使用 Windows PowerShell 5.1。
- `ALB_MAIN/docs/project_overview.md` 和 `ALB_MAIN/docs/file_classification.md` 中的 “PowerShell” 是能力分类或工具类别描述，不需要改成具体版本。

## 后续复查项

- 新增远程 wrapper 或 Task Scheduler runner 时，优先复用 `ALB.remote.transport` 中的 PowerShell 命令构造，不要重新写死 `powershell.exe`。
- 若远程机器未将 PowerShell 7 加入 PATH，应通过 `ALB_POWERSHELL_EXE` 或 `ALB_POWERSHELL_TASK_EXE` 指向远程完整路径，而不是回退修改文档默认值。

## 远程工作站补充审计

2026-05-21 后续执行了两台远程计算工作站的 PowerShell 7 安装和验证：

- `desktop-1pvi7rp`：已安装 PowerShell `7.6.1`，标准路径为 `C:/Program Files/PowerShell/7/pwsh.exe`。
- `AMD64`：已安装 PowerShell `7.6.1`，标准路径为 `C:/Program Files/PowerShell/7/pwsh.exe`。
- 两台机器均通过 SSH `pwsh -NoLogo -NoProfile` 验证。
- 两台机器均通过 Task Scheduler smoke test，动作命令使用 `"C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File <runner>`，`LastTaskResult=0`。

配置结论：

- SSH encoded command 可以继续使用 `pwsh`。
- Task Scheduler runner 不应依赖 `pwsh.exe` 的 PATH 解析；默认使用标准绝对路径。
- `ALB.remote.transport` 已将 `ALB_POWERSHELL_TASK_EXE` 默认值调整为 `C:\Program Files\PowerShell\7\pwsh.exe`，并保留环境变量覆盖入口。
