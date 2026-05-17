# 文档维护审计 2026-05-17

## 文档角色

- 角色：单次日常审计证据。
- 目的：保存一次文档维护 pass 的检查证据、仓库状态、陈旧候选和后续复查项。
- 允许更新：本审计日期检查过的文件、决策、无变更原因、陈旧候选和清理确认清单。
- 禁止更新：源码编辑、运行状态归属、稳定手册内容，以及超出审计证据范围的长期项目摘要。
- 更新节奏：本日期的文档维护 pass 创建或刷新时更新。
- 事实来源 / 相关文档：
  `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`.

## 审计参数

- Project root: `G:\ALB_PROJECTS`
- Created at: `2026-05-17T22:46:44`
- Old-file minimum age: `1` days

## Git 状态

### `ALB_MAIN`

```text
(no output)
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
 M docs/file_classification.md
 M docs/run_index.md
 M run/fd/evaluate_fd_perturbation_inputs.py
```

### `VALIDATION`

```text
M docs/file_classification.md
```

## 文档入口

- `ALB_MAIN/AGENTS.md`
- `ALB_MAIN/docs/alb_package_overview.md`
- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`
- `ALB_MAIN/docs/daily_summary_log.md`
- `ALB_MAIN/docs/file_classification.md`
- `ALB_MAIN/docs/formula/pressure_temperature_consistency_review.md`
- `ALB_MAIN/docs/formula/symbol_conventions.md`
- `ALB_MAIN/docs/formula/thermal_model.md`
- `ALB_MAIN/docs/project_overview.md`
- `ALB_MAIN/docs/remote_workstation_connection.md`
- `ALB_MAIN/docs/run_index.md`
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
- `SURROGATE_TRAIN/docs/run_index.md`
- `SURROGATE_TRAIN/README.md`
- `SURROGATE_TRAIN/TODO.md`
- `VALIDATION/AGENTS.md`
- `VALIDATION/docs/file_classification.md`
- `VALIDATION/README.md`

## 陈旧词命中

- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md:28`: - 若旧维护文档仍有英文正文，后续维护时应优先把被触及的段落改为中文，避免继续扩展英文规则正文。
- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md:41`: | `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_YYYYMMDD.md` | 单次日常审计证据 | 一次计划文档维护的检查证据。 | 已检查文件、决策、无变更原因、陈旧候选、清理确认清单。 | 源码编辑、运行状态归属、长期项目手册内容。 | 每次计划审计创建或刷新。 |
- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md:67`: - 检查被索引叙事文档是否触发压缩：过时经验、过时日志或长度过大。
- `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md:68`: - 压缩经验时，将其总结为耐久原则、注意事项、可复用检查或日期结论；有用经验被保存后，可以删除维护文档中的陈旧叙事。
- `ALB_MAIN/docs/daily_summary_log.md:13`: 本文档用于沉淀日常开发、验证和方案设计工作。后续记录按日期持续追加，不再分散到多个零散说明文件中。旧历史条目保留原样；若后续维护触及历史条目，应只做必要的事实性修正或压缩，避免重写证据链。
- `ALB_MAIN/docs/daily_summary_log.md:58`: - 约束热模型配置中 pressure_backend 仅允许 skfem 路线，旧 h_eff 分支保留为参考实现但不再作为用户可选项。
- `ALB_MAIN/docs/daily_summary_log.md:118`: - `delta_t_scale` 替代 `delta_t_mode` / `delta_t_char` 旧对，移除 `unit_system`。
- `ALB_MAIN/docs/daily_summary_log.md:122`: - `ThermalHydroBearing` 必须在每次 `input()` 改变膜几何后重建 `_thermal_grid`，否则能量方程使用过时的膜厚。
- `ALB_MAIN/docs/daily_summary_log.md:145`: - 部分历史脚本和 notebook 仍使用旧符号 `u`/`vx`，尚未全部迁移。
- `ALB_MAIN/docs/daily_summary_log.md:171`: - `FPBConfig.from_dict` 接受 `thermal_config` (ThermalConfig | dict) 或旧 `thermal_enabled`+`thermal` dict。
- `ALB_MAIN/docs/daily_summary_log.md:173`: - `NodimPadConfig.thermal_config` 镜像 `FPBConfig`（相同旧格式兼容）。
- `ALB_MAIN/docs/daily_summary_log.md:207`: - 部分历史脚本（`Run/`, `Task/` 子目录）仍使用旧 `u`/`vx` 符号，尚未迁移。
- `ALB_MAIN/docs/daily_summary_log.md:338`: - 维护 `G:/ALB_PROJECTS` split workspace 的稳定文档，压缩过时远程训练信息。
- `ALB_MAIN/docs/daily_summary_log.md:343`: - `ALB_MAIN/docs/file_classification.md`：补充 `ALB/remote/`、`test/remote/` 和 remote reference 文件分类，移除旧大小写目录迁移描述。
- `ALB_MAIN/docs/daily_summary_log.md:344`: - `SURROGATE_TRAIN/docs/file_classification.md`：从旧 `RE_ALB`/核心包分类改为训练项目专用分类。
- `ALB_MAIN/docs/daily_summary_log.md:347`: - `SURROGATE_TRAIN/TODO.md`：保留 pending 状态说明；`SURROGATE_TRAIN/docs/PLAN.md` 在当日仍作为 historical 计划检查，后续于 2026-05-10 确认删除。
- `ALB_MAIN/docs/daily_summary_log.md:364`: - 旧计划内容可通过审计报告和每日摘要保留证据链；`SURROGATE_TRAIN/docs/PLAN.md` 文件本身后续于 2026-05-10 确认删除。
- `ALB_MAIN/docs/daily_summary_log.md:372`: - 继续检查旧计划与实际训练状态是否还有冲突项。
- `ALB_MAIN/docs/daily_summary_log.md:379`: - ../SURROGATE_TRAIN/TODO.md
- `ALB_MAIN/docs/daily_summary_log.md:417`: - Stable docs changed: `SURROGATE_TRAIN/TODO.md` and
- `ALB_MAIN/docs/file_classification.md:34`: | 文档和约定 | `docs/`, `AGENTS.md`, `README.md` | 保留并持续改进；文档作为项目组织的第一层。 | 旧文档可能存在编码问题，复用前需要审查。 |
- `ALB_MAIN/docs/formula/pressure_temperature_consistency_review.md:33`: - 历史保留代码：`ViscosityFilmElem` 中仍留有基于 `h_eff` 的旧写法，但它不再作为设置项对外开放，不能作为当前实现依据。
- `ALB_MAIN/docs/formula/thermal_model.md:1036`: - 旧记号 $v_{x0}$ 只是代码变量名 `vx_ref` 的物理映射，其正确物理记号应统一为 $\Lambda_0$。
- `ALB_MAIN/docs/remote_workstation_connection.md:104`: 稳定实现维护在 `ALB.remote`：`job`、`albnn_queue`、`albnn_start`、`albnn_status`、`monitor` 和 `transport`。`SURROGATE_TRAIN/run/remote` 下的脚本是兼容入口，用于保持旧命令和 JSON queue config 可用。
- `ALB_MAIN/docs/remote_workstation_connection.md:183`: - 2026-05-08 旧 `codex_cli_boundary_watch_20260508.ps1` monitor 周期性运行 `codex exec` 来检查 `RE_ALB_boundary_sample_20260508`，会快速消耗 Codex 配额。未来远程监控必须使用直接 PowerShell/Python 状态脚本，除非用户明确要求一次性 Codex CLI review。
- `ALB_MAIN/docs/run_index.md:88`: `outputs/archive/<run_id>/` 只在任务完成且用户确认该运行已不活跃或已废弃后使用。对于 active、running、stopped、failed-but-not-archived 的运行，不要在活跃 locator 块中写入未来归档路径，除非归档已经真实存在。
- `ARTIFACTS_ARCHIVE/docs/file_classification.md:15`: | Logs and run evidence | `*.log`, `reports/logs/`, copied watcher logs | Treat as review candidates only after identifying the related run. | Empty or obsolete logs still need human confirmation before delete/archive. |
- `SURROGATE_TRAIN/docs/file_classification.md:33`: | 文档和状态 | `docs/current_runtime_status.md`, `../ALB_MAIN/docs/run_index.md`, `docs/run_index.md`, `docs/albnn_training_brief.md`, `docs/albnn_training_log.md`, `docs/albnn_training_info.md`, `TODO.md`, `README.md` | 活跃状态和路径定位只写入 `current_runtime_status.md`；工作区全局 run 规则由 `../ALB_MAIN/docs/run_index.md` 维护；`docs/run_index.md` 只保留指针；稳定工作流和经验写入 brief；日期历史写入 log；待验证项写入 TODO。 | 陈旧 run 状态或缺少路径映射会导致误重启、重复任务或归档不完整。 |
- `SURROGATE_TRAIN/docs/file_classification.md:82`: - 任务完成且用户确认 run 已非活跃或过时后，才做归档。
- `SURROGATE_TRAIN/docs/file_classification.md:101`: | JSON queue / generated tests | `outputs/queue_logs/generated_test_20260509.json` 和相关 queue logs | 作为启动/config 证据保留，除非后续 cleanup review 标记为过时。 |
- `SURROGATE_TRAIN/docs/file_classification.md:117`: | `TODO.md` | residual expert 待验证清单；不是活跃 ALBNN 工作流计划。 |
- `SURROGATE_TRAIN/docs/file_classification.md:122`: | `docs/albnn_training_log.md` | 长期每日模型指标、旧命令和事故历史。 |
- `SURROGATE_TRAIN/docs/file_classification.md:129`: - 不要移动活跃 run 目录或活跃 monitor 日志。run-ID-based config/output 命名先用于未来 run；旧非活跃产物只在任务完成和用户确认后迁移。
- `SURROGATE_TRAIN/docs/run_index.md:28`: 不要在本文分配 run 编号，也不要在本文维护活跃 run 状态。本文仅作为兼容入口保留，避免旧笔记或打开的标签页指向过时的第二事实来源。
- `SURROGATE_TRAIN/TODO.md:1`: # SURROGATE_TRAIN TODO

## 明日旧文件候选

| 路径 | 天数 | 原因 | 建议动作 |
|---|---:|---|---|
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.out.log` | 6 | old log-like file | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_090001.err.log` | 6 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/run/train/run_highforce_fromscratch_ablation_queue.py` | 5 | name matches `*scratch*` | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260512_090001.out.log` | 5 | old log-like file | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260512_090001.err.log` | 5 | old log-like file | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.out.log` | 5 | old log-like file | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260511_230401.err.log` | 5 | old log-like file | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260513_090001.out.log` | 4 | old log-like file | confirm before delete/archive |
| `ALB_MAIN/docs/daily_maintenance/logs/codex_daily_doc_maintenance_20260513_090001.err.log` | 4 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train142088_valid35523_l1lt3_noevsgate_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mserelfloorF001_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/farthest_point_feature_analysis/threshold_counts.csv` | 2 | name matches `*old*` | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train132109_valid33146_absfxfylt1p5_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mserelfloorF001_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/outlier_feature_analysis_abs_component_error_gt_0p05_0p10/threshold_counts.csv` | 2 | name matches `*old*` | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train132109_valid33146_absfxfylt1p5_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mserelfloorF001_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train132109_valid33146_absfxfylt1p5_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mserelfloorF001_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_selected_models_20260515/01_best_expert_fmax012_hybrid_scaler/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_selected_models_20260515/01_best_expert_fmax012_hybrid_scaler/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_selected_models_20260515/01_best_expert_fmax012_hybrid_scaler/kc_compare_logs/kc_amp10_cyc10_last_n20_dt002_c80_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_selected_models_20260515/01_best_expert_fmax012_hybrid_scaler/kc_compare_logs/kc_amp10_cyc10_last_n20_dt002_c80_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/12_least_needed_models_archive_20260515_1859/train261407_valid65352_fused326759_fmax012_expert2_adjblend080_polar18_forcepolar4e_mm11_huberraw02scale4_adamw_lr5em04_wd1em05_b5050_w15_noaug_h512_512_256_128_64_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/12_least_needed_models_archive_20260515_1859/train261407_valid65352_fused326759_fmax012_expert2_adjblend080_polar18_forcepolar4e_mm11_huberraw02scale4_adamw_lr5em04_wd1em05_b5050_w15_noaug_h512_512_256_128_64_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/12_least_needed_models_archive_20260515_1859/train261407_valid65352_fused326759_fmax012_expert2_adjblend080_asinh2id_huberraw02_adamw_lr5em04_wd1em05_noaug_h512_512_256_128_64_bs4096_p5000_val5_20260515/kc_compare_logs/kc_amp30_cyc3_last_n10_dt002_c80_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/12_least_needed_models_archive_20260515_1859/train261407_valid65352_fused326759_fmax012_expert2_adjblend080_asinh2id_huberraw02_adamw_lr5em04_wd1em05_noaug_h512_512_256_128_64_bs4096_p5000_val5_20260515/kc_compare_logs/kc_amp30_cyc3_last_n10_dt002_c80_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/12_least_needed_models_archive_20260515_1859/train261407_valid65352_fused326759_fmax012_expert2_adjblend080_asinh2id_huberraw02_adamw_lr5em04_wd1em05_noaug_h512_512_256_128_64_bs4096_p5000_val5_20260515/kc_compare_logs/kc_amp30_cyc10_last_n20_c80_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/12_least_needed_models_archive_20260515_1859/train261407_valid65352_fused326759_fmax012_expert2_adjblend080_asinh2id_huberraw02_adamw_lr5em04_wd1em05_noaug_h512_512_256_128_64_bs4096_p5000_val5_20260515/kc_compare_logs/kc_amp30_cyc10_last_n20_c80_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/11_failed_lorinput_logs_111911/train_stdout.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/_cleanup_candidates_20260515/11_failed_lorinput_logs_111911/train_stderr.log` | 2 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/data/raw419840_filtered_no_fmax_limit_lrgt0p5_lroverlrlt4_e085_v08_s10_20260515/l1_lt2_input_constraint_analysis_20260515/l1_lt2_evs_edotv_threshold_grid.csv` | 2 | name matches `*old*` | confirm before delete/archive |
| `SURROGATE_TRAIN/data/raw419840_filtered_no_fmax_limit_lrgt0p5_lroverlrlt4_e085_v08_s10_20260515/evs_geom_dot_joint_l1_analysis_20260515/evs_geom_abs_edotv_threshold_grid.csv` | 2 | name matches `*old*` | confirm before delete/archive |
| `SURROGATE_TRAIN/data/raw419840_filtered_no_fmax_limit_lrgt0p5_lroverlrlt4_e085_v08_s10_20260515/abs_edotv_analysis_20260515/abs_edotv_threshold_tradeoffs.csv` | 2 | name matches `*old*` | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_sinomega10_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_20260516_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_sinomega10_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_20260516_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_20260516_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_20260516_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_20260516_rerun_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/kc_compare_logs/kc_amp10_cyc3_last_n10_dt002_c80_20260516_rerun_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard3_of_4_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard3_of_4_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard2_of_4_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard2_of_4_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard1_of_4_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard1_of_4_stderr.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard0_of_4_stdout.log` | 1 | old log-like file | confirm before delete/archive |
| `SURROGATE_TRAIN/models/train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_p2500_plateau100_20260515/deployment_chain_abc_tests_20260516/test_H_jacobian_shard0_of_4_stderr.log` | 1 | old log-like file | confirm before delete/archive |

## 复查清单

- 确认稳定项目文档是否需要更新。
- 删除或归档前，逐项确认旧文件候选。
- 不要把 secrets 写入文档。
- 如果事故经验能避免重复问题，应保留其可复用结论。
