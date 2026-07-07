# 文档维护审计 2026-07-07

## 文档角色

- 角色：单次日常审计证据。
- 目的：记录本次项目文档审计的检查范围、结论、变更和未清理事项。
- 允许更新：本审计日期检查过的文件、决策、无变更原因、陈旧候选和清理确认清单。
- 禁止更新：源码编辑、运行状态归属、稳定手册内容，以及超出审计证据范围的长期项目摘要。
- 更新节奏：每次计划审计创建或刷新。
- 事实来源 / 相关文档：
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `AGENTS.md`,
  `docs/file_classification.md`,
  `docs/run_index.md`,
  `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md`。

## 审计目标

- 检查 `AGENTS.md` 是否存在可检索的项目文件管理、路径和命名约束。
- 检查文档角色、current-status、run 路径和论文任务路径是否存在可追踪引用。
- 将散落在当前状态文件中的论文图目录整理经验压缩为稳定规则。
- 不删除、不归档、不移动原始数据、日志、模型或图片产物。

## 已检查文件

| 文件 | 检查结果 |
| --- | --- |
| `AGENTS.md` | 已存在环境、编码、文档角色、run/current-status 和远程入口规则；缺少明确的文件/路径/命名约束，已补充。 |
| `docs/daily_maintenance/daily_doc_update_index.md` | 已存在文档角色和压缩规则；已补充 `AGENTS.md` 的文件/路径命名约束触发条件，并加入论文 current-status 证据入口。 |
| `docs/file_classification.md` | 已存在 ALB_MAIN 文件归属和清理策略；`PAPER_WORK` 完整规则已迁移到外部工作区 `AGENTS.md`，本文档只保留入口指针。 |
| `docs/run_index.md` | 已存在 ALB_PROJECTS run ID 和路径族；`PAPER_WORK` 论文任务外部路径族已迁移到外部工作区 `AGENTS.md`，本文档只保留入口指针。 |
| `docs/project_overview.md` | 入口和边界说明仍可用，无需本次修改。 |
| `docs/remote_workstation_connection.md` | 论文远程 wrapper 入口仍与当前路径一致，无需本次修改。 |
| `F:/BaiduSyncdisk/博士论文/PAPER_WORK/docs/current_task_status.md` | 当前论文任务路径整理已记录；该文件继续只作为短期状态缓冲区。 |

## 变更摘要

- `AGENTS.md` 新增 `文件、路径与命名约束`，明确文件管理的首查文档、论文 task/figure/run/remote 归属、`data*`/`datas*` 目录规则、`figures/` 规则和引用同步要求。
- `docs/file_classification.md` 保留 `PAPER_WORK/AGENTS.md` 入口指针，不再维护完整论文工作区目录规则。
- `docs/run_index.md` 保留 `PAPER_WORK/AGENTS.md` 入口指针，不再维护完整论文工作区路径族。
- `docs/daily_maintenance/daily_doc_update_index.md` 补充审计触发条件和论文 current-status 证据来源。

## 自查结论

| 检查项 | 结论 |
| --- | --- |
| `AGENTS.md` 是否有项目文档命名和管理约束 | 已补充。 |
| 是否能从项目文档找到数据、脚本、日志、图件归属 | 已能从 `AGENTS.md`、`file_classification.md`、`run_index.md` 追踪。 |
| 是否存在直接要求删除原始证据 | 未发现；规则继续要求删除/归档前单独确认。 |
| 是否把实时状态写进稳定文档 | 未写入实时进度；只沉淀路径族和归属规则。 |
| 是否压缩了当前状态中的临时经验 | 已将论文图目录整理经验压缩为稳定规则，不复制单次运行细节。 |

## 遗留风险

- `git status` 显示本仓库已有多处未提交修改和未跟踪文件，本次审计未尝试清理或解释这些源码/测试变更。
- 旧历史审计报告中仍可能含有英文正文或过时关键字；这些是历史证据，不在本次审计中重写。
- `PAPER_WORK` 不是本仓库目录，后续仍需要在具体绘图或计算任务结束时检查实际目录是否遵守本次规则。

## 补充迁移

- 已按人工要求将 `PAPER_WORK` 的脚本、远程配置、图目录、数据目录、图片审计、current-status 和证据保留规则迁移到 `F:/BaiduSyncdisk/博士论文/PAPER_WORK/AGENTS.md`。
- `ALB_MAIN/AGENTS.md`、`docs/file_classification.md`、`docs/run_index.md` 和 `docs/remote_workstation_connection.md` 不再维护完整 `PAPER_WORK` 目录规则，只保留外部工作区入口指针。
- `docs/daily_maintenance/daily_doc_update_index.md` 已加入 `PAPER_WORK/AGENTS.md` 作为条件性角色检查和证据来源。
