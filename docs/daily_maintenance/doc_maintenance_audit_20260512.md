# 文档维护审计 2026-05-12

## 文档角色

- 角色：单次日常审计证据。
- 目的：保存一次计划文档维护 pass 的证据和决策。
- 允许更新：本审计日期检查过的文件、决策、无变更原因、陈旧候选和清理确认清单。
- 禁止更新：源码编辑、运行状态归属、稳定手册内容，以及超出审计证据范围的长期项目摘要。
- 更新节奏：本日期的计划日常审计创建或刷新时更新。
- 事实来源 / 相关文档：
  `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`.

- Project root: `G:/ALB_PROJECTS`
- Created at: `2026-05-12T09:03:10+08:00`
- Old-file minimum age: `1` days

## 计划维护说明

- This report is the scheduled daily documentation-maintenance pass for
  `G:/ALB_PROJECTS`; it is not an immediate update after every code/model
  change.
- Audit helper attempted:
  `C:/Users/73401/.codex/skills/maintain-project-docs/scripts/doc_maintenance_audit.py`.
- Helper result: not usable in this shell because `python` resolves to
  `C:/Users/73401/AppData/Local/Microsoft/WindowsApps/python.exe`, which exited
  without running the script. The pass used manual PowerShell scans instead.
- No source code, remote SSH, training, sampling, commits, deletes, archives,
  moves, or renames were performed by this pass.
- Stale keyword hits such as `old`, `TODO`, `deprecated`, `obsolete`, `旧`, and
  `过时` are treated as review candidates only.

## 已检查当前证据

- Role index read first:
  `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`.
- Git status checked in each child repository because `G:/ALB_PROJECTS` is a
  split workspace root, not a Git repository.
- Local process evidence checked only on this workstation. No remote status
  command was run.
- Local predecessor training PID `81380` from the prior live buffer was not
  present at the `2026-05-12T09:03:10+08:00` local check.
- Local queue PID `67356` was present, using
  `E:/Anaconda2023/envs/ALB/python.exe`.
- Queue status file:
  `SURROGATE_TRAIN/outputs/local_train_logs/queue_polar15_forcepolar_noaugment_sin_gelu_256_after_gelu512_20260512/queue_status.json`.
- Queue status at `2026-05-12T09:02:12+08:00`: `running_job`, current job
  `polar15_forcepolar_noaugment_gelu_256`, current PID `82848`.
- Current GELU 256 stdout tail reached epoch `3150/50000`, train loss
  `5.3256e-04`, test loss `4.9048e-03`, LR `0.0001`. Its stderr contained only
  the mixed-type CSV `DtypeWarning` already seen in related runs.
- Completed local polar29 `sqrt(abs(x))` GELU 512 model evidence:
  `metadata.json` and `validation_summary.json` written at
  `2026-05-12T07:46:15+08:00`, independent validation `n=15043`,
  `r2_mean=0.9851159260`.
- Completed local polar15 no-augmentation sin 256 model evidence:
  `metadata.json` and `validation_summary.json` written at
  `2026-05-12T08:43:00+08:00`, independent validation `n=15043`,
  `r2_mean=0.9433115947`.
- Current filtered-origin data directory:
  `SURROGATE_TRAIN/data/train_valid110000_filtered_ecc085_lr05_lam8_force3_origin1000_20260512`.
- Remote 100000-sample generation was not checked by SSH. Existing local
  monitor evidence remains ambiguous: the prior running snapshot had
  `7920/100000` valid samples, while the latest local monitor tail recorded
  `state: not_running`, `processes: 0`, and no `remote_time`.
- `ALB_MAIN/docs/daily_maintenance/latest_codex_daily_doc_maintenance_status.txt`
  still points at the 2026-05-11 scheduled launcher logs. It was read and left
  unchanged because this manually invoked scheduled pass did not produce
  scheduler final-log metadata.

## 已索引文档决策

| File | Daily decision |
| --- | --- |
| `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260512.md` | Created for this scheduled pass. |
| `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md` | Read first; no role-index update required. |
| `ALB_MAIN/docs/daily_maintenance/latest_codex_daily_doc_maintenance_status.txt` | Read; left unchanged because it points at scheduler-generated run logs. |
| `ALB_MAIN/docs/daily_summary_log.md` | Updated with a concise 2026-05-12 scheduled-pass note linking to this report. |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | Updated to resolve the local active-state conflict and record the clear local queue/current PID state. |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | Appended one 2026-05-12 durable entry for completed local polar models and queue handoff. |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | Read; no stable workflow-pointer or durable-lesson update was clear enough while the queue is still active and remote state is ambiguous. |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | Read; no read-order or source-of-truth update required. |
| `ALB_MAIN/docs/remote_workstation_connection.md` | Read; no stable remote-mechanics update required. |
| `ALB_MAIN/docs/file_classification.md` | Read; no ALB_MAIN classification update required. |
| `SURROGATE_TRAIN/docs/file_classification.md` | Read; no training artifact classification update required. |
| `ALB_MAIN/docs/alb_package_overview.md` | Read; no public package-boundary update required. |
| `ALB_MAIN/AGENTS.md` | Read; no agent-policy update required. |
| `SURROGATE_TRAIN/AGENTS.md` | Read; no local/remote launch-boundary update required. |
| `ARTIFACTS_ARCHIVE/docs/file_classification.md` | Read; no archive-policy update required. |
| `DATA_POSTPROCESS/docs/file_classification.md` | Read; no postprocess-policy update required. |
| `PARAM_SCAN/docs/file_classification.md` | Read; no parameter-scan policy update required. |
| `VALIDATION/docs/file_classification.md` | Read; no validation-policy update required. |
| `SPLIT_INDEX.md` | Read; no split membership or dependency-convention update required. |

## Git 状态快照

`G:/ALB_PROJECTS` itself is not a Git repository. Child repositories were dirty
before this pass; source-code modifications were left untouched.

### `ALB_MAIN`

```text
 M AGENTS.md
 M ALB/nn.py
 M docs/alb_package_overview.md
 M docs/daily_maintenance/daily_doc_update_index.md
 M docs/daily_maintenance/doc_maintenance_audit_20260511.md
 M docs/daily_summary_log.md
 M docs/file_classification.md
 M docs/remote_workstation_connection.md
```

### `SURROGATE_TRAIN`

```text
 M AGENTS.md
 M TODO.md
 M docs/albnn_training_brief.md
 M docs/albnn_training_info.md
 M docs/albnn_training_log.md
 M docs/current_runtime_status.md
 M docs/file_classification.md
 M run/heat_albnn_pipeline.py
 M run/train/train_albnn.py
?? data/
?? models/
```

### 其他 Split Repositories

```text
ARTIFACTS_ARCHIVE:  M docs/file_classification.md
DATA_POSTPROCESS:   M docs/file_classification.md
PARAM_SCAN:         M docs/file_classification.md
VALIDATION:         M docs/file_classification.md
```

## 陈旧术语复查候选

The keyword scan found review candidates, not automatic stale guidance:

- `SURROGATE_TRAIN/TODO.md` is intentionally a pending offline residual-expert
  validation checklist, not the active ALBNN workflow.
- `SURROGATE_TRAIN/docs/current_runtime_status.md` contains intentional
  non-active and stopped-run sections; the active-state conflict found today was
  corrected from local evidence.
- `ALB_MAIN/docs/remote_workstation_connection.md` and
  `SURROGATE_TRAIN/docs/albnn_training_log.md` contain `obsolete` Codex watcher
  notes as durable incident lessons.
- Split file-classification docs contain legacy review context that is
  explicitly superseded by their current split classifications.
- Older `ALB_MAIN/docs/daily_summary_log.md` and formula/project docs include
  historical Chinese entries and compatibility notes with `旧`/`过时` wording;
  they should be reviewed in context before compression or migration.

## 明日旧文件候选

The manual name-pattern scan found no non-generated source/doc candidates under
the scanned roots when excluding generated output directories. The following
generated maintenance evidence should be confirmed on the next daily pass before
any cleanup:

| Path | Reason | Suggested action |
| --- | --- | --- |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.err.log` | Generated scheduled-maintenance stderr log; large evidence file. | Confirm whether one-day scheduler-log retention applies. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.out.log` | Generated scheduled-maintenance stdout log. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.final.md` | Generated scheduled-maintenance final-message capture. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.err.log` | Generated scheduled-maintenance stderr/tool-output evidence. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.out.log` | Generated scheduled-maintenance stdout log. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.final.md` | Generated scheduled-maintenance final-message capture. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260512_090001.err.log` | Empty generated scheduled-maintenance stderr log. | Confirm whether it belongs to a scheduled run before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260512_090001.out.log` | Empty generated scheduled-maintenance stdout log. | Confirm whether it belongs to a scheduled run before cleanup. |

## 需要人工确认的项目

- Run a one-shot remote monitor or SSH status check before restarting
  `ALB_GenerateTrainValid100000CurrentAuto_20260511` or marking it
  complete/stopped.
- Confirm retention policy for generated maintenance logs, especially the empty
  2026-05-12 scheduler logs.
- After the active GELU 256 queue job completes, confirm whether the stable
  ALBNN brief should be updated for the polar15/polar29 workflow or whether
  those details should remain only in runtime/log docs.
- Review stale-term hits in context before changing historical notes,
  compatibility warnings, or legacy classifications.

## 复查清单

- Confirm whether stable project docs need updates.
- Confirm each old-file candidate before deleting or archiving.
- Keep secrets out of documentation.
- Preserve useful incident lessons when they prevent repeated errors.
