# 2026-06-17 文档维护审计

## 审计范围

- 工作区：`G:/ALB_PROJECTS`
- 目标项目：`ALB_MAIN`、`SURROGATE_TRAIN`
- 触发请求：清理两个项目维护文档中的过时信息，并在完成后执行 git 操作。
- 排除边界：`F:/BaiduSyncdisk/博士论文/PAPER_WORK` 不纳入本次 git 提交；论文任务实时状态继续归属其自己的 current-status 文档。
- 审计脚本：已运行
  `C:/Users/73401/.codex/skills/maintain-project-docs/scripts/doc_maintenance_audit.py`
  生成初稿；初稿命中大量 `.pytest_tmp_review` 历史快照，已在人工报告中压缩。

## 已读取的角色入口

- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`
- `ALB_MAIN/docs/project_overview.md`
- `ALB_MAIN/docs/file_classification.md`
- `ALB_MAIN/docs/run_index.md`
- `ALB_MAIN/docs/remote_workstation_connection.md`
- `SURROGATE_TRAIN/docs/current_runtime_status.md`
- `SURROGATE_TRAIN/docs/albnn_training_brief.md`
- `SURROGATE_TRAIN/docs/albnn_training_log.md`
- `SURROGATE_TRAIN/docs/albnn_training_info.md`
- `SURROGATE_TRAIN/docs/file_classification.md`
- `SURROGATE_TRAIN/docs/run_index.md`

集中索引与上述目标文档的本地角色区块未发现冲突。

## Git 状态摘要

审计开始前两个目标项目均已有未提交改动。

- `ALB_MAIN`：存在源码、测试和文档改动；本次只处理文档，不回退源码/测试。
- `SURROGATE_TRAIN`：存在文档、分析脚本、notebook 和大量未跟踪 run config/script；本次只处理已索引文档。
- 其它子项目：`PARAM_SCAN` 有配置改动；本次未处理。

## 过时信息处理

### 已清理

- `SURROGATE_TRAIN/docs/current_runtime_status.md`
  - 移除旧 M0031-M0035、S0011、S0010、S0009、M0024-M0030、S0008 等已完成运行的长篇历史区块。
  - 写入 2026-06-17 no-active 审计状态：旧本地 PID 均不在运行；M0031-M0035 均已有 `metadata.json`、`validation_summary.json` 和 `best_albnn.pth`。
  - 明确本次未 SSH 远程轮询；论文任务活跃状态不写入此文件。
- `SURROGATE_TRAIN/docs/albnn_training_log.md`
  - 增加 2026-06-17 runtime buffer compression audit。
  - 沉淀 M0031-M0035 validation summary 指标和 packaged artifact 完整性。
- `SURROGATE_TRAIN/docs/albnn_training_brief.md`
  - 将 `Current S0003 200k Resample Workflow` 调整为已完成采样 workflow pattern。
  - 更新 `Preferred Next Steps`，移除等待旧 FD/S0003 活跃任务完成的过时动作。
- `ALB_MAIN/docs/daily_summary_log.md`
  - 记录本次交互式文档审计、角色边界和不删除/不归档原则。

### 保留为稳定说明

- `ALB_MAIN/docs/remote_workstation_connection.md`
  - 保留 `PAPER_WORK/run/remote` 作为论文远程任务本地入口的稳定说明。
  - 不写入论文任务实时 PID、ETA 或最新进度。
- `ALB_MAIN/docs/project_overview.md`、`ALB_MAIN/docs/file_classification.md`、`ALB_MAIN/docs/run_index.md`
  - 仍准确描述 split workspace、current-status 归属和路径规则，本次无内容变更。
- `SURROGATE_TRAIN/docs/albnn_training_info.md`、`SURROGATE_TRAIN/docs/file_classification.md`、`SURROGATE_TRAIN/docs/run_index.md`
  - 仍只作为入口/分类/指针文档，本次无内容变更。

## 清理候选

本次未删除、移动或归档任何文件。以下候选仅供后续单独确认：

- `ALB_MAIN/.pytest_tmp_review/`：审计脚本将其历史快照识别为文档入口；它更像临时 review 证据，不应混入稳定文档审计。
- `ALB_MAIN/_daily_alas_tmp/AlasAutomation/start-alas-automation.log`：旧本地自动化日志候选，需确认是否仍用于 ALAS 启动诊断。
- `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_*`、`codex_daily_doc_maintenance_20260512_*`、`codex_daily_doc_maintenance_20260513_*`：旧计划维护日志候选，删除前需确认是否仍需保留审计证据链。
- `SURROGATE_TRAIN/models/**/train_stdout.log`、`train_stderr.log`、`kc_compare_logs/*.log`：模型/验证原始证据，默认随模型保留，不应只因文件名或年龄删除。
- `SURROGATE_TRAIN/data/**/old40w_*`：名称含 old，但仍可能是训练数据来源证据；删除前必须复查引用关系。

## 验证

- 已用 `Get-Process` 核对旧 live buffer PID：`204592`、`80516`、`194756`、`205312`、`200452`、`125608`、`170524`、`148592`、`150704`、`170560` 均未运行。
- 已检查 M0031-M0035 模型目录：`metadata.json`、`validation_summary.json`、`best_albnn.pth` 均存在。
- 已检查 `outputs/queue_logs/`、`outputs/remote_monitor_logs/`、`outputs/local_train_logs/` 最近写入时间；未发现比 2026-06-09 更新的 `SURROGATE_TRAIN` 训练/queue 证据。
- 已复核目标文档角色边界；没有把实时任务状态写入稳定手册。

## 本次未做

- 未修改源码。
- 未启动训练、采样、远程任务或 SSH monitor。
- 未删除、移动、归档旧文件。
- 未对 `F:/BaiduSyncdisk/博士论文/PAPER_WORK` 执行 git 操作。
