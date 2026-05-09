# Documentation Maintenance Audit 2026-05-09

- Project root: `G:\ALB_PROJECTS`
- Created at: `2026-05-09T09:02:14`
- Old-file minimum age: `1` days

## Git Status

### `ALB_MAIN`

```text
M ALB/__init__.py
 M ALB/alb.py
 M ALB/bearing.py
 M ALB/config.py
 M ALB/film.py
 M ALB/gas.py
 M ALB/nn.py
 M ALB/thermal.py
?? ALB/damping.py
?? docs/daily_maintenance/
?? test/bearing/test_adaptive_damp_integration.py
?? test/config/test_adaptive_damp.py
```

### `ARTIFACTS_ARCHIVE`

```text
(no output)
```

### `DATA_POSTPROCESS`

```text
(no output)
```

### `PARAM_SCAN`

```text
(no output)
```

### `SURROGATE_TRAIN`

```text
M run/train_albnn.py
?? run/build_force20_total_dataset.py
?? run/ps1/run_train_force20_asinh_20260509.ps1
?? run/retry_invalid_adaptive_damp.py
```

### `VALIDATION`

```text
(no output)
```

## Documentation Entry Points

- `ALB_MAIN/AGENTS.md`
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
- `SURROGATE_TRAIN/docs/albnn_training_info.md`
- `SURROGATE_TRAIN/docs/file_classification.md`
- `SURROGATE_TRAIN/docs/PLAN.md`
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
- `ALB_MAIN/docs/pressure_temperature_consistency_review.md:33`: - 历史保留代码：`ViscosityFilmElem` 中仍留有基于 `h_eff` 的旧写法，但它不再作为设置项对外开放，不能作为当前实现依据。
- `ALB_MAIN/docs/project_overview.md:110`: - `NodimCSOrifice(position, cq0, cq1, cq2)`：CS 节流器无量纲核心类，旧 `CSOrifice` 仍保留量纲参数入口并继承它。
- `ALB_MAIN/docs/remote_workstation_connection.md:106`: inspect the old `RE_ALB_boundary_sample_20260508` task. It was obsolete and
- `ALB_MAIN/docs/thermal_model.md:485`: - 旧记号 $v_{x0}$ 只是代码变量名 `vx_ref` 的物理映射，其正确物理记号应统一为 $\Lambda_0$。
- `SURROGATE_TRAIN/docs/albnn_training_info.md:280`: - Do not run Codex CLI as an automatic watcher. The obsolete
- `SURROGATE_TRAIN/docs/PLAN.md:43`: - 先评估旧最佳模型：
- `SURROGATE_TRAIN/docs/PLAN.md:56`: - boundary validation MAE 或 RMSE 明显优于旧 base 模型
- `SURROGATE_TRAIN/docs/PLAN.md:86`: - 对比旧 base 模型和新模型的 base 域与 boundary 域残差。
- `SURROGATE_TRAIN/docs/PLAN.md:92`: - 旧最佳 base 模型作为 baseline，而不是继续训练被停止的 `48031` 模型。
- `SURROGATE_TRAIN/TODO.md:1`: # SURROGATE_TRAIN TODO

## Old File Candidates For Tomorrow

| Path | Age Days | Reason | Suggested Action |
|---|---:|---|---|
| `ARTIFACTS_ARCHIVE/test/couple/logs/film-5305.log` | 565 | old log-like file | confirm before delete/archive |

## Review Checklist

- Confirm whether stable project docs need updates.
- Confirm each old-file candidate before deleting or archiving.
- Keep secrets out of documentation.
- Preserve useful incident lessons when they prevent repeated errors.

## Codex Maintenance Review

- Maintenance type: scheduled daily documentation pass.
- Audit helper: ran successfully with `E:/Anaconda2023/envs/ALB/python.exe`. The default `python` command in this shell resolves to the Windows Store stub and did not run the helper.
- Stable docs updated in this pass: none. Existing split-workspace, remote-workstation, ALBNN training, and file-classification docs already contain the clear current facts found during this audit.
- Source code edited: none.
- Remote SSH, training, sampling, and long-running model work: not run.

## Current State Notes

- Workspace root `G:/ALB_PROJECTS` is a split workspace; each direct child project is its own git repository.
- Dirty repositories found:
  - `ALB_MAIN`: active ALB code changes, new `ALB/damping.py`, new adaptive damping tests, and this daily-maintenance report directory.
  - `SURROGATE_TRAIN`: active training/script changes including `run/train_albnn.py`, `run/build_force20_total_dataset.py`, `run/retry_invalid_adaptive_damp.py`, and `run/ps1/run_train_force20_asinh_20260509.ps1`.
- Clean repositories found: `ARTIFACTS_ARCHIVE`, `DATA_POSTPROCESS`, `PARAM_SCAN`, and `VALIDATION`.
- Current surrogate-training docs identify the active residual-expert stage as `ALB_TargetedResidualWaveThenTrain_20260510`, with runner `F:/GWJ/20260507-train/run_targeted_sampling_waves_then_train_20260510.ps1`.

## Old-File Candidates For Next-Day Confirmation

Treat these as review candidates only. No deletion, archive, move, or rename was performed.

| Path | Reason | Suggested next action |
|---|---|---|
| `ARTIFACTS_ARCHIVE/test/couple/logs/film-5305.log` | Very old log-like file, last modified in 2024. | Confirm whether it is reproducibility evidence; archive or delete only after human confirmation. |

Additional watch-list items:

- `ARTIFACTS_ARCHIVE/outputs/codex_cli_boundary_watch_20260508/*`: previous Codex CLI watcher evidence. It is documented as obsolete for future monitoring, but the files are recent archive evidence and were not added as delete candidates today.
- `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260509_090001.*.log`: zero-length scheduled-run logs from today. Keep for now; review tomorrow if repeated empty logs accumulate.

## Human Confirmation Needed

- Confirm whether `ARTIFACTS_ARCHIVE/test/couple/logs/film-5305.log` should be archived, retained, or deleted.
- Review whether the active untracked `ALB_MAIN/docs/daily_maintenance/` directory should be kept under version control.
- Confirm the intended status of `SURROGATE_TRAIN/run/ps1/run_train_force20_asinh_20260509.ps1` relative to the existing residual-expert remote runners before promoting it in stable docs.
