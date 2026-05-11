# Daily Documentation Update Index

This index defines the files that the scheduled daily documentation audit must
check and update when needed. Realtime progress belongs in
`SURROGATE_TRAIN/docs/current_runtime_status.md`; durable daily summaries,
completed events, and key metrics are folded into the lower-churn documents
listed here.

## Audit Rule

- The daily audit must read every file in this index that exists.
- If a listed file needs a content change, update it during the daily pass.
- If a listed file does not need a content change, record that no-change
  decision in the day's `doc_maintenance_audit_YYYYMMDD.md`.
- Check indexed narrative documents for compression triggers: outdated
  experience, outdated logs, or excessive length.
- Compress experience by summarizing durable lessons. Remove outdated narrative
  logs from maintained docs after useful lessons are preserved.
- Preserve incident cases, root-cause notes, final metrics, and reference
  workflows that remain useful for future diagnosis or reproduction.
- Do not use this index as permission to delete, move, archive, launch jobs, or
  edit source code.

## Required Daily Audit Files

| File | Daily action | Update trigger |
| --- | --- | --- |
| `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_YYYYMMDD.md` | Create or refresh for the scheduled pass. | Every scheduled daily audit. |
| `ALB_MAIN/docs/daily_maintenance/latest_codex_daily_doc_maintenance_status.txt` | Refresh scheduler status pointer. | Every scheduled daily audit. |
| `ALB_MAIN/docs/daily_summary_log.md` | Append one concise daily documentation-maintenance summary. | Completed daily maintenance work, cleanup confirmations, stable doc changes, or key audit findings. |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | Verify and update active long-job state. | Active training, sampling, queue monitor, or remote job exists. |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | Append at most one dated daily ALBNN entry. | Completed runs, incidents, model metrics, manual stops, launches worth preserving, or durable decisions since the previous daily pass. |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | Update only stable current-workflow pointers and lessons. | Active workflow stage, canonical data/model path, sampling settings, or durable lesson changes. |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | Keep the first-read ALBNN doc order current. | Entry-point docs or read order changes. |

## Conditional Audit Files

| File | Daily action | Update trigger |
| --- | --- | --- |
| `ALB_MAIN/AGENTS.md` | Check for stale project-level rules. | Agent policy, source-change boundary, package orientation, or remote-operation rule changes. |
| `SURROGATE_TRAIN/AGENTS.md` | Check for stale training-project rules. | Local/remote launch boundary, documentation frequency, or training-source ownership changes. |
| `ALB_MAIN/docs/remote_workstation_connection.md` | Check remote mechanics and path references. | SSH, Task Scheduler, remote runner, monitor, or credential-handling mechanics change. |
| `ALB_MAIN/docs/alb_package_overview.md` | Check package orientation. | Public API, module ownership, or package-boundary changes. |
| `ALB_MAIN/docs/file_classification.md` | Check classification and cleanup categories. | New major file groups, archive categories, or cleanup policies appear. |
| `SURROGATE_TRAIN/docs/file_classification.md` | Check training file classifications. | New training outputs, scripts, monitor logs, models, or cleanup policy changes appear. |
| `ARTIFACTS_ARCHIVE/docs/file_classification.md` | Check archive ownership notes. | Archive structure or retention policy changes. |
| `DATA_POSTPROCESS/docs/file_classification.md` | Check postprocess ownership notes. | Postprocess/notebook categories change. |
| `PARAM_SCAN/docs/file_classification.md` | Check parameter-scan ownership notes. | Parameter-scan task or artifact categories change. |
| `VALIDATION/docs/file_classification.md` | Check validation ownership notes. | Validation/test artifact categories change. |
| `SPLIT_INDEX.md` | Check split workspace entry points. | Project membership or dependency convention changes. |

## Evidence Sources To Inspect

These are not narrative docs and should not be edited unless a separate task
requires it. The daily audit may summarize them into the files above.

| Evidence source | Use |
| --- | --- |
| `SURROGATE_TRAIN/models/*/metadata.json` | Completed model configuration and metrics. |
| `SURROGATE_TRAIN/models/*/validation_summary.json` | Independent validation metrics. |
| `SURROGATE_TRAIN/models/*/manual_termination.json` | Manual-stop evidence. |
| `SURROGATE_TRAIN/outputs/local_train_logs/` | Local training stdout/stderr and launch metadata. |
| `SURROGATE_TRAIN/outputs/remote_monitor_logs/` | Remote sampling monitor status. |
| `SURROGATE_TRAIN/outputs/queue_logs/` | Remote training queue status and synced tails. |
| `ALB_MAIN/docs/daily_maintenance/logs/` | Scheduled maintenance stdout/stderr/final-message evidence. |
