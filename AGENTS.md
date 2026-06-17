# ALB_MAIN 代理指令

本文件保存 coding agent 在本仓库工作时需要遵守的稳定项目级指令。

## 环境

- Python：`E:/Anaconda2023/envs/ALB/python.exe`
- Shell：PowerShell 7（`pwsh`，本机路径通常为 `C:/Program Files/PowerShell/7/pwsh.exe`）。
- PowerShell 命令默认面向 PowerShell 7；跨旧 runner、远程 `cmd` 包装或 Task Scheduler 命令时仍优先使用 `;` 保持兼容，除非确认调用环境支持 `&&`。
- 仓库根目录：当前目录，即 `G:/ALB_PROJECTS` 下的 `ALB_MAIN`。

## 代码约定

- 不要修改源码，除非满足以下任一条件：用户明确要求代码变更，或用户请求不修改代码就无法完成。
- 对小型或轻量请求，优先复用现有脚本、CLI、配置和已记录命令，再考虑新增代码。
- 所有代码注释必须使用英文。
- 新脚本至少要包含简短英文注释，说明主流程、假设和不明显步骤。
- package/module 代码必须为 public API、重要数据契约和非平凡逻辑提供完整、可维护的 docstring 和注释。
- 黏度变量使用 `miu`，不要使用 `u`。
- 使用 `lambda_value`，不要使用裸 `lambda`。
- 测试文件中的 `plt.show()` 必须包在 `if __name__ == '__main__':` 下。
- 搜索文件和文本时优先使用 `rg`。

## 编码策略

- 本项目所有文本文件默认使用 UTF-8 读取和写入，包括中文文档、Markdown、Python、TOML、JSON/JSON5、YAML、PowerShell 和 shell 脚本。
- 读取旧文件时，如果 UTF-8 解码失败，可以对明确的 legacy 文件临时 fallback 到 GBK/CP936，但必须在报告中说明；不要静默按 GBK/CP936 处理。
- fallback 读取的文件不要直接写回原编码；若需要修改，应先明确转换为 UTF-8，再按 UTF-8 写入。
- agent 面向机器或长期规则的输出尽量使用 ASCII 标点，避免智能引号、特殊破折号等易被 Windows 编码链路污染的字符。

## Agent 调度

- 除非用户明确给定 agent 数量，否则执行任务时最多创建两个子 agent。
- 小型修复、单文件审查、简单测试排错优先由主 agent 直接完成；需要并行审计时，默认使用一到两个子 agent 后由主 agent 复核和集成。
- 新对话涉及当前项目状态或长任务状态时，可以用 1 个 explorer 做只读状态摘要。
- 大规模重构、跨文件影响分析、文档/历史检索时，可以用 1-2 个 explorer 并行分工。
- 简单任务不启用子 agent。
- explorer 输出只作为压缩后的导航层，关键事实在执行前由主 agent 抽查验证。
- 启用子 agent 时按任务复杂度选择模型：轻量、边界清晰、可快速验证的代码检查或小修复使用 `GPT-5.3-Codex-Spark`；中等复杂度的多文件审计、局部重构、常规训练/远程流程诊断使用 `GPT-5.4`；高风险或高复杂度任务，如核心训练框架重构、远程长任务控制面修改、数值/物理一致性审计、跨项目集成和最终仲裁，使用 `GPT-5.5`。
- 主 agent 在派发任务前应明确子 agent 的范围、预期输出和是否允许改文件；除非用户指定模型，否则优先按上一条规则选择，不为简单任务默认升级到更高模型。

## 文档语言

- 面向人类用户阅读的规定类、概览类、维护类、审计类和操作手册类文档应使用中文。包括但不限于 `docs/alb_package_overview.md`、`docs/daily_summary_log.md`、`docs/file_classification.md`、`docs/project_overview.md`、`docs/remote_workstation_connection.md`、`docs/run_index.md`，以及兄弟项目中的同类维护文档。
- 源码中的代码注释、docstring、实现说明、嵌入源码的 CLI help 文本和生成脚本注释必须保持英文，以兼容编码和工具链。
- 当维护类人类可读文档已经部分使用英文时，后续编辑应把被触及段落转向中文，而不是继续增加英文规则正文。

## ALB 包定位

修改 package module 或 public interface 前，先阅读 `docs/alb_package_overview.md`。该文档总结 `ALB/` 模块图、`ALB/__init__.py` 中的顶层 lazy exports，以及系统构建器、配置 dataclass、轴承/油膜模型、热/无量纲 helper、ALBNN surrogate、远程 helper、task/result 工具等主要接口组。

新增 public API 时，同时更新模块 docstring/comment 和包概览。可复用数值代码应保留在 `ALB_MAIN/ALB`；`SURROGATE_TRAIN` 等兄弟项目应 import 这里的 ALB 包代码，不要复制。

## 文档角色边界

维护项目文档前，先阅读 `docs/daily_maintenance/daily_doc_update_index.md`。它是集中式文档角色索引。然后阅读目标文档本地的 `文档角色` 区块，只编辑该角色允许的内容。

如果集中索引和目标文档冲突，停止并报告冲突。实时运行状态属于 `../SURROGATE_TRAIN/docs/current_runtime_status.md`；每日耐久 ALBNN 历史属于 `../SURROGATE_TRAIN/docs/albnn_training_log.md`；稳定远程机制属于 `docs/remote_workstation_connection.md`。

## Run 与当前状态定位

使用 `docs/run_index.md` 获取工作区级 run 编号和路径规则。广泛搜索项目文件前，先使用拥有项目的 current-status 文档作为 agent 面向活跃工作的首要定位入口。对 SURROGATE_TRAIN 来说，该文件是 `../SURROGATE_TRAIN/docs/current_runtime_status.md`。对论文任务和 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/task` 下的活跃计算来说，该文件是 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/task/docs/current_task_status.md`。

活跃 run 区块应保持足够结构化，能够定位 config、outputs、相关日志指针、远程任务名、最新进度、当前问题和下一步。日志不通过单一全局布局统一管理；详细原始证据保留在 artifacts 中，已完成 run 的耐久历史属于对应的时间顺序 log。

## ALBNN / 热采样

热 ALBNN 采样和远程训练细节位于 `../SURROGATE_TRAIN/docs/albnn_training_brief.md`；详细日期历史位于 `../SURROGATE_TRAIN/docs/albnn_training_log.md`。当前模型使用 12 个 base inputs，输出 `fx, fy`；做训练相关判断前，重新阅读 brief 和 live 的 `SURROGATE_TRAIN/task/task_albnn_data.py`。

## 远程计算机连接

远程工作站可通过 LAN 或 ZeroTier 上的 SSH 访问。详细连接检查、路径和长任务启动说明维护在 `docs/remote_workstation_connection.md`。

论文远程计算脚本和配置的当前入口位于 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/run/remote`；通用 ALB 远程实现仍维护在 `ALB.remote` 和 `docs/remote_workstation_connection.md` 所述兼容 wrapper 中。

启动远程 ALBNN training 时，默认启动 monitoring。优先使用 JSON queue wrapper，因为它会监督活跃任务，并把 status/log tails 同步到配置的输出路径；如果直接用 start wrapper 启动任务，应立即启动对应 queue monitor。
两台远程计算工作站默认使用 PowerShell 7，且 `C:/Program Files/PowerShell/7` 已加入 Machine/User PATH。SSH encoded command 和交互短命令可调用 `pwsh`；Task Scheduler runner 默认优先使用 `C:/Program Files/PowerShell/7/pwsh.exe` 绝对路径，以避免服务环境或 WindowsApps alias 差异。

不要把密码、私钥、恢复码或 API key 写入本文件。它们应存放在 OS credential manager、SSH agent 或其他本地 secret store 中。
