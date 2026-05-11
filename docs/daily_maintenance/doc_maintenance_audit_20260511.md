# Documentation Maintenance Audit 2026-05-11

- Project root: `G:\ALB_PROJECTS`
- Created at: `2026-05-11T23:05:28`
- Old-file minimum age: `1` days

## Scheduled Pass Notes

- This report is the scheduled daily documentation-maintenance pass for
  `G:/ALB_PROJECTS`; it is not an immediate update after every code/model
  change.
- Audit helper used:
  `C:/Users/73401/.codex/skills/maintain-project-docs/scripts/doc_maintenance_audit.py`.
- Helper interpreter:
  `E:/Anaconda2023/envs/ALB/python.exe`.
- No source code, remote SSH, training, sampling, commits, deletes, archives,
  moves, or renames were performed by this pass.
- Stable documentation changed only where stale active-status wording was clear:
  `SURROGATE_TRAIN/TODO.md` and
  `SURROGATE_TRAIN/docs/file_classification.md` no longer describe the old
  force3 queue as the active workflow.
- Stale keyword hits such as `old`, `TODO`, `deprecated`, `旧`, and `过时` are
  treated as review candidates only.

## Current Evidence Checked

- Active workflow source of truth:
  `SURROGATE_TRAIN/docs/current_runtime_status.md`.
- Current ALBNN brief:
  `SURROGATE_TRAIN/docs/albnn_training_brief.md`.
- Local 28-input `sqrt28` training was checked locally only: Python PID `73756`
  still matched the active model command, `stderr.log` was empty, and
  `loss_history.csv` had advanced to epoch `1450`.
- Remote 100000-sample generation was not checked by SSH. Local monitor log
  evidence showed running snapshots through remote time
  `2026-05-11T22:51:02+08:00` at `7920/100000` valid samples, followed by a
  later ambiguous local monitor snapshot with `remote_time: None`,
  `state: not_running`, and `processes: 0`. This ambiguity is recorded for
  review instead of changing stable remote docs.
- The helper found no non-generated old-file candidates under scanned
  source/docs paths. Daily-maintenance scheduler logs are listed separately
  below as next-day confirmation candidates.

## Indexed Document Decisions

| File | Daily decision |
| --- | --- |
| `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260511.md` | Refreshed for this scheduled pass. |
| `ALB_MAIN/docs/daily_maintenance/latest_codex_daily_doc_maintenance_status.txt` | Refreshed to point at this pass/report. |
| `ALB_MAIN/docs/daily_summary_log.md` | Updated with a concise 2026-05-11 scheduled-pass note linking to this report. |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | Read; not changed because the local training progress was a live tick and the remote monitor state was ambiguous. |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | Read; no new completed run or durable incident was clear enough to append. |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | Read; no stable workflow-pointer change required. |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | Read; no entry-point order change required. |
| `ALB_MAIN/AGENTS.md` | Read; no policy/path update required. |
| `SURROGATE_TRAIN/AGENTS.md` | Read; no launch-boundary update required. |
| `ALB_MAIN/docs/remote_workstation_connection.md` | Read; no stable remote-mechanics update required. |
| `ALB_MAIN/docs/alb_package_overview.md` | Read; no package-boundary update required. |
| `ALB_MAIN/docs/file_classification.md` | Read; no classification update required. |
| `SURROGATE_TRAIN/docs/file_classification.md` | Updated to make force3 artifacts historical evidence, not active workflow guidance. |
| `ARTIFACTS_ARCHIVE/docs/file_classification.md` | Read; no archive-policy update required. |
| `DATA_POSTPROCESS/docs/file_classification.md` | Read; no postprocess-policy update required. |
| `PARAM_SCAN/docs/file_classification.md` | Read; no parameter-scan policy update required. |
| `VALIDATION/docs/file_classification.md` | Read; no validation-policy update required. |
| `SPLIT_INDEX.md` | Read; no split membership or dependency-convention update required. |

## Git Status

### `ALB_MAIN`

```text
M AGENTS.md
 M ALB/config.py
 M ALB/nn.py
 M README.md
 D docs/daily_maintenance/doc_maintenance_audit_20260509.md
 M docs/daily_summary_log.md
 M docs/file_classification.md
 M docs/remote_workstation_connection.md
?? ALB/remote/
?? docs/alb_package_overview.md
?? docs/daily_maintenance/daily_doc_update_index.md
?? docs/daily_maintenance/doc_maintenance_audit_20260511.md
?? refs/remote_albnn_queue_config_reference_v1.json
?? refs/remote_albnn_start_dry_run_reference_v1.json
?? refs/remote_albnn_status_summary_reference_v1.json
?? refs/remote_monitor_snapshot_reference_v1.json
?? test/remote/
?? test/test_albnn_input_compat.py
```

### `ARTIFACTS_ARCHIVE`

```text
M docs/file_classification.md
```

### `DATA_POSTPROCESS`

```text
M docs/file_classification.md
```

### `PARAM_SCAN`

```text
M docs/file_classification.md
```

### `SURROGATE_TRAIN`

```text
M AGENTS.md
 M README.md
 M TODO.md
 D docs/PLAN.md
 M docs/albnn_training_info.md
 M docs/file_classification.md
 D run/build_boundary_curriculum.py
 D run/build_force20_total_dataset.py
 D run/evaluate_albnn_domains.py
 D run/evaluate_albnn_residual_domains.py
 D run/generate_targeted_boundary_samples.py
 M run/heat_albnn_pipeline.py
 D run/merge_targeted_boundary_shards.py
 M run/remote/remote_query_albnn_status.py
 M run/remote/remote_start_albnn_train.py
 D run/train_alb_agent.py
 D run/train_albnn.py
 D run/train_albnn_residual_expert.py
 D run/train_thermal_mlp.py
 M task/task_albnn_data.py
?? data/
?? docs/albnn_training_brief.md
?? docs/albnn_training_log.md
?? docs/current_runtime_status.md
?? models/
?? run/analysis/
?? run/evaluate_albnn_input_samples.py
?? run/prepare_albnn_110k_input_samples.py
?? run/prepare_polar_ecc_filter_dataset.py
?? run/ps1/run_generate_train_valid100000_current_auto_damp070_iter40_20260511.ps1
?? run/ps1/run_generate_train_valid110000_current_ps7focus_auto_damp070_iter40_20260510.ps1
?? run/ps1/run_generate_train_valid40000_expansion_auto_seed_damp070_iter40_20260510.ps1
?? run/ps1/run_train_valid110000_base12_cq2siglog01_gelu_512_512_256_128_noise002x1_local_20260511.ps1
?? run/ps1/run_train_valid110000_base12_cq2siglog01_gelu_noise002x1_local_20260511.ps1
?? run/ps1/run_train_valid110000_base12_cq2siglog_gelu_noise002x1_local_20260511.ps1
?? run/ps1/run_train_valid40000_polar_ecc030_080_standard_gelu_20260511.ps1
?? run/ps1/watch_110k_generation_then_train_queue_20260510.ps1
?? run/ps1/watch_trainvalid40000_two_trainings_then_generate_expansion_20260510.ps1
?? run/remote/configs/
?? run/remote/remote_monitor_job.py
?? run/remote/remote_queue_albnn_activation_sweep.py
?? run/repair_albnn_output_csv_columns.py
?? run/split_albnn_train_validation.py
?? run/train/
```

### `VALIDATION`

```text
M docs/file_classification.md
```

## Documentation Entry Points

- `ALB_MAIN/AGENTS.md`
- `ALB_MAIN/docs/alb_package_overview.md`
- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`
- `ALB_MAIN/docs/daily_summary_log.md`
- `ALB_MAIN/docs/file_classification.md`
- `ALB_MAIN/docs/pressure_temperature_consistency_review.md`
- `ALB_MAIN/docs/project_overview.md`
- `ALB_MAIN/docs/remote_workstation_connection.md`
- `ALB_MAIN/docs/symbol_conventions.md`
- `ALB_MAIN/docs/thermal_model.md`
- `ALB_MAIN/README.md`
- `ARTIFACTS_ARCHIVE/AGENTS.md`
- `ARTIFACTS_ARCHIVE/docs/file_classification.md`
- `ARTIFACTS_ARCHIVE/README.md`
- `DATA_POSTPROCESS/AGENTS.md`
- `DATA_POSTPROCESS/docs/file_classification.md`
- `DATA_POSTPROCESS/README.md`
- `PARAM_SCAN/AGENTS.md`
- `PARAM_SCAN/docs/file_classification.md`
- `PARAM_SCAN/README.md`
- `SPLIT_INDEX.md`
- `SURROGATE_TRAIN/AGENTS.md`
- `SURROGATE_TRAIN/docs/albnn_training_brief.md`
- `SURROGATE_TRAIN/docs/albnn_training_info.md`
- `SURROGATE_TRAIN/docs/albnn_training_log.md`
- `SURROGATE_TRAIN/docs/current_runtime_status.md`
- `SURROGATE_TRAIN/docs/file_classification.md`
- `SURROGATE_TRAIN/README.md`
- `SURROGATE_TRAIN/TODO.md`
- `VALIDATION/AGENTS.md`
- `VALIDATION/docs/file_classification.md`
- `VALIDATION/README.md`

## Stale-Term Hits

- `ALB_MAIN/docs/daily_summary_log.md:48`: - 约束热模型配置中 pressure_backend 仅允许 skfem 路线，旧 h_eff 分支保留为参考实现但不再作为用户可选项。
- `ALB_MAIN/docs/daily_summary_log.md:108`: - `delta_t_scale` 替代 `delta_t_mode` / `delta_t_char` 旧对，移除 `unit_system`。
- `ALB_MAIN/docs/daily_summary_log.md:112`: - `ThermalHydroBearing` 必须在每次 `input()` 改变膜几何后重建 `_thermal_grid`，否则能量方程使用过时的膜厚。
- `ALB_MAIN/docs/daily_summary_log.md:135`: - 部分历史脚本和 notebook 仍使用旧符号 `u`/`vx`，尚未全部迁移。
- `ALB_MAIN/docs/daily_summary_log.md:161`: - `FPBConfig.from_dict` 接受 `thermal_config` (ThermalConfig | dict) 或旧 `thermal_enabled`+`thermal` dict。
- `ALB_MAIN/docs/daily_summary_log.md:163`: - `NodimPadConfig.thermal_config` 镜像 `FPBConfig`（相同旧格式兼容）。
- `ALB_MAIN/docs/daily_summary_log.md:197`: - 部分历史脚本（`Run/`, `Task/` 子目录）仍使用旧 `u`/`vx` 符号，尚未迁移。
- `ALB_MAIN/docs/daily_summary_log.md:328`: - 维护 `G:/ALB_PROJECTS` split workspace 的稳定文档，压缩过时远程训练信息。
- `ALB_MAIN/docs/daily_summary_log.md:333`: - `ALB_MAIN/docs/file_classification.md`：补充 `ALB/remote/`、`test/remote/` 和 remote reference 文件分类，移除旧大小写目录迁移描述。
- `ALB_MAIN/docs/daily_summary_log.md:334`: - `SURROGATE_TRAIN/docs/file_classification.md`：从旧 `RE_ALB`/核心包分类改为训练项目专用分类。
- `ALB_MAIN/docs/daily_summary_log.md:337`: - `SURROGATE_TRAIN/TODO.md`：保留 pending 状态说明；`SURROGATE_TRAIN/docs/PLAN.md` 在当日仍作为 historical 计划检查，后续于 2026-05-10 确认删除。
- `ALB_MAIN/docs/daily_summary_log.md:354`: - 旧计划内容可通过审计报告和每日摘要保留证据链；`SURROGATE_TRAIN/docs/PLAN.md` 文件本身后续于 2026-05-10 确认删除。
- `ALB_MAIN/docs/daily_summary_log.md:362`: - 继续检查旧计划与实际训练状态是否还有冲突项。
- `ALB_MAIN/docs/daily_summary_log.md:369`: - ../SURROGATE_TRAIN/TODO.md
- `ALB_MAIN/docs/pressure_temperature_consistency_review.md:33`: - 历史保留代码：`ViscosityFilmElem` 中仍留有基于 `h_eff` 的旧写法，但它不再作为设置项对外开放，不能作为当前实现依据。
- `ALB_MAIN/docs/project_overview.md:110`: - `NodimCSOrifice(position, cq0, cq1, cq2)`：CS 节流器无量纲核心类，旧 `CSOrifice` 仍保留量纲参数入口并继承它。
- `ALB_MAIN/docs/remote_workstation_connection.md:187`: inspect the old `RE_ALB_boundary_sample_20260508` task. It was obsolete and
- `ALB_MAIN/docs/thermal_model.md:485`: - 旧记号 $v_{x0}$ 只是代码变量名 `vx_ref` 的物理映射，其正确物理记号应统一为 $\Lambda_0$。
- `ARTIFACTS_ARCHIVE/docs/file_classification.md:15`: | Logs and run evidence | `*.log`, `reports/logs/`, copied watcher logs | Treat as review candidates only after identifying the related run. | Empty or obsolete logs still need human confirmation before delete/archive. |
- `SURROGATE_TRAIN/docs/albnn_training_log.md:599`: - Do not run Codex CLI as an automatic watcher. The obsolete
- `SURROGATE_TRAIN/docs/file_classification.md:29`: | Documentation and status | `docs/albnn_training_brief.md`, `docs/albnn_training_log.md`, `docs/albnn_training_info.md`, `TODO.md`, `README.md` | Keep current training status and lessons in `albnn_training_brief.md`; keep chronological details in `albnn_training_log.md`; keep pending validation checks in `TODO.md`. | Stale run state can cause accidental restarts or duplicate tasks. |
- `SURROGATE_TRAIN/docs/file_classification.md:41`: | JSON queue/generated tests | `outputs/queue_logs/generated_test_20260509.json` and related queue logs | Keep as launch/config evidence unless a later cleanup review marks them obsolete. |
- `SURROGATE_TRAIN/TODO.md:1`: # SURROGATE_TRAIN TODO

## Old File Candidates For Tomorrow

The audit helper found no non-generated old-file candidates under scanned
source/docs paths. The following generated maintenance evidence should be
confirmed on the next daily pass before any cleanup:

| Path | Reason | Suggested action |
| --- | --- | --- |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.err.log` | Same-day scheduled-maintenance stderr log; large generated evidence file. | Confirm whether one-day scheduler-log retention applies after the 2026-05-12 pass. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.out.log` | Same-day scheduled-maintenance stdout log. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.final.md` | Same-day scheduled-maintenance final-message capture. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.err.log` | Current-pass generated stderr/tool-output evidence. | Confirm retention before cleanup. |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.out.log` | Current-pass generated stdout log, currently empty. | Confirm retention before cleanup. |

## Human Confirmation Items

- Review the ambiguous local monitor tail for
  `ALB_GenerateTrainValid100000CurrentAuto_20260511`: the latest local log tail
  says `state: not_running` with `remote_time: None`, but the preceding checked
  snapshots were running. No remote check was run during this pass.
- Confirm whether the preexisting git deletion
  `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260509.md` should
  remain deleted or be restored as historical evidence.
- Review keyword hits in context. Several hits are intentional historical notes
  or compatibility warnings, not automatic stale-doc judgments.

## Review Checklist

- Confirm whether stable project docs need updates.
- Confirm each old-file candidate before deleting or archiving.
- Keep secrets out of documentation.
- Preserve useful incident lessons when they prevent repeated errors.
