# ALB_MAIN File Classification

## Document Role

- Role: ALB_MAIN file ownership and cleanup policy.
- Purpose: Classify ALB_MAIN file groups, ownership boundaries, artifact
  categories, and cleanup policy.
- Allowed updates: file categories, representative paths, retention/archive
  rules, cleanup risk notes, and ownership boundaries.
- Forbidden updates: live runtime state, model progress, latest metrics, and
  detailed run history.
- Update cadence: when major file groups, archive categories, or cleanup
  policies change.
- Source of truth / Related docs:
  `docs/daily_maintenance/daily_doc_update_index.md`.

本文档记录当前项目文件面向的主要需求、代表目录/文件、建议处理方式和风险点。
本阶段只建立分类清单和后续整理建议，不移动文件、不修改 import、不清理训练产物。

## Classification Principles

- Keep source layout unchanged. `ALB/` remains the stable Python package boundary.
- Preserve experiment evidence. `outputs/` is treated as an archive candidate by default, not a deletion target.
- Separate repeatable tests from exploratory work. Pytest files, diagnostics, notebooks, GUI tools, and artifacts should be labeled differently.
- Treat the current git state as live user work. Moves, deletions, or artifact
  cleanup must be a separate confirmed step.

## Demand Categories

| Demand type | Representative paths | Suggested action | Risk notes |
| --- | --- | --- | --- |
| Stable library code | `ALB/`, `pyproject.toml` | Keep in place and document module responsibilities. | Moving files would require import rewrites and broad tests. |
| Task and batch entrypoints | `task/`, `ALB/task.py` | Keep current entrypoints; later split reusable workflows from one-off scripts. | Some scripts use local absolute paths and copy task files to outputs. |
| Run scripts and experiments | `run/`, `run/validation/`, `run/JKW/` | Keep repeatable scripts; classify generated subdirectories as artifacts. | Some scripts are paper/demo specific and may write into `run/_*` directories. |
| Remote ALBNN tooling | `ALB/remote/`, `test/remote/`, `refs/remote_albnn_*_reference_v1.json` | Keep as the stable implementation and regression baseline for remote helpers. | Compatibility wrappers live in sibling `SURROGATE_TRAIN/run/remote/`; avoid restoring duplicate implementations there. |
| Run registration tooling | `scripts/run_registry.py`, `test/test_run_registry.py`, `docs/run_index.md`, `*/docs/run_registry.jsonl` | Keep reusable registry code as an `ALB_MAIN` repository script; keep append-only registration facts in each owning project's docs directory. | Do not parse Markdown as the registry source; do not backfill historical runs unless they are reviewed, reused, or archived. |
| Pytest and engineering validation | `test/*.py`, `test/bearing/`, `test/config/`, `test/thermal/` | Separate regression/unit/integration/validation/diagnostic purposes in documentation first. | `test/` also contains notebooks, GUI, logs, and figures, so pytest semantics are mixed. |
| Historical data processing and notebooks | `data_process/`, `learning_note/`, `test/**/*.ipynb` | Preserve as research history; later migrate to `notebooks/` or `experiments/notebooks/`. | Many notebooks may contain embedded output and hard-coded local paths. |
| Documentation and conventions | `docs/`, `AGENTS.md`, `README.md` | Keep and improve; use docs as the first layer of project organization. | Existing docs may have encoding issues and should be reviewed before reuse. |
| Training data, models, plots, logs | `outputs/`, `run/_*`, `test/**/_*`, `*.png`, `*.csv`, `*.json`, `*.pkl`, `*.pth` | Archive by experiment goal/date; do not delete by default. | Metadata, scalers, model weights, and CSV files can be needed for reproducibility. |
| IDE, cache, and temporary files | `.idea/`, `.vscode/`, `.pytest_cache/`, `__pycache__/`, `output.txt` | Mark as cleanup candidates after confirming they are not intentionally tracked. | Current git state is dirty; cleanup should happen only after a separate review. |

## ALB Module Map

`ALB/` should stay as the public package for now. The following map is a
documentation-only view of responsibilities. For the maintained package
orientation and public interface groups, read `docs/alb_package_overview.md`.

| Area | Files | Purpose |
| --- | --- | --- |
| Numerical foundation | `base.py`, `mesh.py`, `boundary.py`, `gauss.py`, `matrix/` | Base models, node/element management, mesh creation, boundary handling, matrix assembly, iterative solvers. |
| Film and bearing models | `film.py`, `bearing.py`, `orifice.py`, `gas.py` | Reynolds film solvers, hydrostatic and gas bearings, multi-pad assembly, orifice and supply flow models. |
| ALB system and control | `alb.py`, `controller.py`, `servovalve.py`, `lti.py` | ALB assembly, PID/fuzzy/LQG-related control, servo valve models, state-space utilities. |
| Thermal and nondimensional models | `thermal.py`, `nondim.py` | Thermal-hydrodynamic coupling, viscosity-temperature coupling, nondimensional scales and solver wrappers. |
| Rotor coupling | `rotor.py`, `orbit.py`, `couple.py` | ROSS rotor integration, orbit generation, rotor-bearing coupling, time response workflows. |
| Surrogate models | `nn.py` | ALBNN and thermal surrogate model definitions, feature augmentation, inference/training helpers. |
| Remote workstation tools | `remote/` | SSH, PowerShell, Task Scheduler, ALBNN launch/status/queue helpers used by sibling training workflows. |
| Utilities, config, and results | `tool.py`, `config.py`, `results.py`, `postprocess.py`, `logger.py` | Config objects, json5 readers, result trees, logging, plotting/postprocess helpers, assorted utilities. |

Notes:

- Do not rename `ALB/matrix/dynmaic.py` in this phase. The misspelling is part of existing imports and must be handled through a compatibility plan if changed later.
- `ALB/tool.py` and `ALB/config.py` are broad modules. They are good candidates for future gradual decomposition, but not for immediate movement.
- `ALB/task.py` and `task/*.py` overlap in workflow responsibilities. Future cleanup should define which APIs are reusable library workflows and which are command-line experiment entrypoints.

## Outputs And Artifacts

Experiment run outputs, run logs, queue status snapshots, and training configs
belong in sibling `SURROGATE_TRAIN` unless they are formal `ALB` package
regression fixtures. The workspace-global run rules live in
`ALB_MAIN/docs/run_index.md`, while append-only run facts live in each owning
project's `docs/run_registry.jsonl`. Future runs should use the
project-prefixed run ID and log-placement policy: configs under the owning
subproject, result artifacts under that subproject's `outputs`, runtime logs
under that subproject's `logs`, and short-term inactive archives under that
subproject's `outputs/archive`.

`outputs/` should be considered an archive candidate, not a cleanup target. Suggested labels:

| Artifact group | Representative paths | Suggested label |
| --- | --- | --- |
| Current thermal ALBNN data/model attempts | `outputs/albnn_data_lr_cq_*`, `outputs/albnn_model_lr_cq_*` | Archive as thermal ALBNN experiments, preserving `metadata.json`, CSV, scalers, model weights, and diagnostic plots. |
| Legacy or comparison ALBNN results | `outputs/albnn_model_r2_1000`, `outputs/albnn_validation_review`, `outputs/model2_*` | Archive as legacy/model-comparison evidence. Do not mix with current 12-column thermal ALBNN inputs. |
| Thermal MLP outputs | `outputs/thermal_mlp`, `outputs/thermal_mlp_data` | Archive as thermal force surrogate work. |
| Thermal diagnostics and comparisons | `outputs/thermal_kc_compare`, `outputs/thermal_force_time_term_compare`, `outputs/transient_thermal` | Archive as validation and diagnostic results. |
| Demo and paper figures | `run/_compare_orifice`, `run/_paper_textured_foil`, `run/_tilting_pad_demo`, `outputs/_gas_bearing_demo` | Preserve if referenced by docs, reports, or notebooks. |
| Smoke and tiny sample outputs | `outputs/albnn_smoke*`, `outputs/albnn_data_smoke*`, `outputs/albnn_data_parallel_smoke` | Cleanup candidates only after checking they are not used as quick regression fixtures. |
| Remote helper regression artifacts | `refs/remote_albnn_*_reference_v1.json`, `test/remote/` | Keep with `ALB.remote`; these files preserve CLI/wrapper behavior during refactors. |

Do not recommend deleting `.csv`, `.json`, `.pth`, or `.pkl` files without checking whether they are paired experiment assets.

## Test Directory Classification

The `test/` directory contains multiple kinds of work and should not be treated as a single pytest-only area.

| Test area | Representative paths | Suggested future home |
| --- | --- | --- |
| Unit/config tests | `test/config/test_config_validate.py`, `test/test_logging_dedup.py`, `test/tool/test_bearing_film_nastran_export.py` | `test/unit/` |
| Integration tests | `test/bearing/test_thermal_wrapper.py`, `test/bearing/test_tilting_pad_bearing.py`, `test/bearing/test_gas_bearing.py` | `test/integration/` |
| Regression/equivalence tests | `test/bearing/test_nodim_interfaces.py`, `test/bearing/test_nodim_alb_equivalence.py`, `test/test_nondim_thermal_field_case.py` | `test/regression/` |
| Engineering validation | `test/bearing/validation_runner.py`, `test/bearing/validation_reference_data.py`, `test/bearing/test_validation_smoke.py`, `test/bearing/test_validation_precision.py` | `test/validation/` |
| Diagnostics | `test/thermal/_thermal_*_diagnose.py` | `experiments/diagnostics/` or `test/diagnostics/` |
| Manual tools and notebooks | `test/gui_bearing.py`, `test/gomoku_game.py`, `test/**/*.ipynb`, `test/**/*.png`, `test/**/*.html`, `test/**/*.log` | `tools/manual/`, `notebooks/`, or `test/artifacts/` |

## Future Directory Suggestions

These are optional target structures for later phases. They are not implemented by this document.

| Target path | Intended content |
| --- | --- |
| `archive/YYYYMMDD_<experiment>/` | Preserved output bundles grouped by date and experiment purpose. |
| `notebooks/alb/`, `notebooks/control/`, `notebooks/ansys/`, `notebooks/symbolic/`, `notebooks/misc/` | Exploratory notebooks currently under `learning_note/`, `data_process/`, and `test/`. |
| `experiments/diagnostics/` | One-off diagnostic scripts that are useful but not formal pytest cases. |
| `ALB/remote/` | Stable LAN/remote helper APIs. Sibling `SURROGATE_TRAIN/run/remote/` should remain thin compatibility wrappers. |
| `tools/manual/` | GUI demos, manual visualization helpers, email/Nastran utilities, and non-test scripts. |
| `test/artifacts/` | Test-generated plots, logs, HTML, and reference output snapshots. |

## Implementation Guardrails

- Do not move source files in the same change that introduces the classification document.
- Do not modify `pyproject.toml`, package discovery, or public import paths during documentation-only cleanup.
- Do not delete training data, model weights, scalers, or metadata without a separate reproducibility review.
- Before any actual migration, capture a clean file inventory and run targeted tests for the affected area.
- Preserve local project conventions from `AGENTS.md`: English code comments, `miu` for viscosity, and `lambda_value` instead of bare `lambda` in Python code.
