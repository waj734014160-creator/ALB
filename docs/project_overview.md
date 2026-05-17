# ALB_MAIN 项目概览

## 文档角色

- 角色：ALB_MAIN 项目入口概览。
- 目的：给人类用户和代理提供项目边界、主要目录、首读文档和常用验证入口。
- 允许更新：项目职责、目录职责、首读文档、稳定验证入口和跨项目边界说明。
- 禁止更新：实时运行状态、详细实验日志、模型指标流水、原始日志正文和源码实现细节。
- 更新节奏：项目拆分、目录职责、首读文档或稳定工作流入口变化时更新。
- 事实来源 / 相关文档：
  `AGENTS.md`,
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `docs/alb_package_overview.md`,
  `docs/file_classification.md`,
  `docs/run_index.md`。

## 项目定位

`ALB_MAIN` 是 `G:/ALB_PROJECTS` split workspace 中的稳定 ALB 包项目。它负责保存可复用的 ALB 数值模型、轴承/油膜/热耦合/无量纲接口、ALBNN 相关基础接口、远程 helper 和工程验证基线。

训练数据、模型产物、远程队列状态和活跃运行状态不放在本项目内维护；这些内容由兄弟项目 `SURROGATE_TRAIN` 负责。`ALB_MAIN` 只维护稳定库代码、公共接口、文档规则和必要的回归/验证资产。

## 主要目录

| 路径 | 职责 |
| --- | --- |
| `ALB/` | 稳定 Python 包边界，包含求解器、轴承模型、热模型、无量纲接口、代理模型接口和远程 helper。 |
| `docs/` | 项目说明、包概览、文件分类、run 规则、远程手册和维护审计文档。 |
| `refs/` | 行为参考和回归基线，特别是远程 helper 相关 reference。 |
| `scripts/` | 项目维护脚本。新增脚本必须遵守英文代码注释规则。 |
| `test/` | pytest、工程验证、诊断脚本和部分历史手动工具；具体分类见 `docs/file_classification.md`。 |
| `pyproject.toml` | 包元数据和构建配置。 |
| `AGENTS.md` | 代理在本仓库工作的稳定规则入口。 |

## 首读顺序

1. `AGENTS.md`：确认环境、代码约定、文档边界和远程操作边界。
2. `docs/daily_maintenance/daily_doc_update_index.md`：维护文档前先读，用于确认目标文档角色。
3. `docs/alb_package_overview.md`：修改 `ALB/` 包模块或公共接口前先读。
4. `docs/file_classification.md`：整理文件、判断归档/清理风险时先读。
5. `docs/run_index.md`：需要 run 编号、路径或 current-status 边界时先读。
6. `docs/remote_workstation_connection.md`：需要远程连接、Task Scheduler、SSH、runner 或 monitor 规则时先读。

与 ALBNN 训练相关的活跃状态和历史，应转向：

- `../SURROGATE_TRAIN/docs/current_runtime_status.md`：当前活跃 run、进度、日志路径和下一步。
- `../SURROGATE_TRAIN/docs/albnn_training_brief.md`：稳定训练工作流和当前模型/数据契约。
- `../SURROGATE_TRAIN/docs/albnn_training_log.md`：完成事件、事故原因、最终指标和耐久结论。

## 核心能力

- Reynolds 油膜、静压轴承、气体轴承和节流孔模型。
- 热-流体耦合、黏温关系、无量纲接口和有量纲/无量纲包装。
- ALB 系统装配、控制器、伺服阀和转子/轴承耦合相关工具。
- ALBNN/热代理模型基础接口和特征辅助函数。
- 远程 Windows 工作站 helper：SSH、PowerShell、Task Scheduler、队列/监控抽象。
- 结果树、配置对象、日志、绘图和后处理辅助工具。

更细的模块说明以 `docs/alb_package_overview.md` 为准。

## 开发和验证入口

默认 Python：

```powershell
E:/Anaconda2023/envs/ALB/python.exe
```

常用轻量验证：

```powershell
E:/Anaconda2023/envs/ALB/python.exe -m pytest --collect-only
E:/Anaconda2023/envs/ALB/python.exe -m pytest test/bearing/test_thermal_wrapper.py -v
E:/Anaconda2023/envs/ALB/python.exe -m pytest test/bearing/test_nodim_interfaces.py -v
```

修改公共 API、无量纲接口、热模型或远程 helper 时，应根据影响面选择更聚焦的测试。若验证命令耗时过长，先使用 import smoke 或 `pytest --collect-only` 缩小问题。

## 文档语言规则

- 面向人类用户阅读的规定类、概览类、维护类、审计类和操作手册类文档使用中文。
- 源码中的代码注释、docstring、实现说明、嵌入代码的 CLI help 和生成脚本注释使用英文，以兼容不同编码方式和工具链。
- 文档中保留路径、命令、模块名、类名、函数名、参数名和错误文本的英文原文。

## 边界提醒

- 不在 `ALB_MAIN` 内维护实时训练进度；实时状态属于 `SURROGATE_TRAIN/docs/current_runtime_status.md`。
- 不把日志集中搬到统一目录；日志作为原始证据留在负责工具写入的位置，稳定文档只保留指针和结论。
- 不把历史产物按文件名直接删除；清理前先按 `docs/file_classification.md` 分类，再做单独确认。
- 不在兄弟项目复制 `ALB/` 包代码；兄弟项目应导入 `ALB_MAIN` 的稳定包能力。
