# 文档维护审计 2026-05-16

## 文档角色

- 角色：单次日常审计证据。
- 目的：保存一次文档维护 pass 的证据和决策。
- 允许更新：本审计日期检查过的文件、决策、无变更原因、陈旧候选和清理确认清单。
- 禁止更新：源码编辑、运行状态归属、稳定手册内容，以及超出审计证据范围的长期项目摘要。
- 更新节奏：本日期的文档维护 pass 创建或刷新时更新。
- 事实来源 / 相关文档：
  `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`.

- Project root: `G:/ALB_PROJECTS`
- Created at: `2026-05-16T23:56:52+08:00`
- Initial request: maintain long-term ALBNN logs, stable experience docs, and
  current status docs; remove outdated status/log/experience text; summarize
  candidates for future skill/manual solidification without applying those
  skill changes.
- Follow-up request on 2026-05-17: apply the confirmed skill/manual
  solidification candidates.

## 角色检查

- Read first: `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md`.
- Target role blocks checked:
  `SURROGATE_TRAIN/docs/current_runtime_status.md`,
  `SURROGATE_TRAIN/docs/albnn_training_brief.md`,
  `SURROGATE_TRAIN/docs/albnn_training_log.md`, and
  `SURROGATE_TRAIN/docs/albnn_training_info.md`.
- No role conflicts found.

## 已检查证据

- Git status was clean in both `ALB_MAIN` and `SURROGATE_TRAIN` before edits.
- FD h-review remote monitor evidence:
  `SURROGATE_TRAIN/outputs/fd_jacobian/h_review_500_20260516/local_remote_monitor_20260516_235458.log`.
- Latest one-shot remote monitor during this pass: `6400/12000` evaluated,
  `6400` valid, remote stderr empty except the start marker.
- Local monitor process `72520` was still running and writing the local monitor
  log.
- Current scaled-EVS model validation summaries were read from the ordinary MSE
  and sin-omega10 model directories.
- Prepared full FD candidate manifests were read from
  `SURROGATE_TRAIN/outputs/fd_jacobian/fd10000_candidates_20260516/`.

## 文档决策

| File | Decision |
| --- | --- |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | Rewritten as a short live snapshot. Removed stale active/completed local training sections and repeated old pointers that no longer belong in the live buffer. Kept only current FD h-review state, prepared full candidate state, next action, and non-active current artifact pointers. |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | Rewritten as stable current understanding. Removed old 2026-05-10/11 live remote pointers and stale preferred next steps. Added current scaled-EVS contract, current filtered dataset/model pointers, FD Jacobian workflow, and durable lessons. |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | Compressed long historical launch/status blocks into durable dated summaries. Preserved key metrics, contracts, incidents, and conclusions; removed repeated raw progress text and obsolete command dumps. Added 2026-05-16 FD Jacobian preparation summary. |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | Read; no update required because read order and source-of-truth pointers remain valid. |
| `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_20260516.md` | Created to record this pass and the candidate skill/manual updates. |

## 清理范围

- Deleted from maintained docs: stale live-state sections, repeated monitor
  ticks, old active PID blocks, obsolete preferred next steps, and long command
  dumps that had already been reduced to durable lessons.
- Not deleted: raw evidence files, generated CSVs, JSON manifests, model
  directories, monitor logs, checkpoints, or scalers.
- No source-code files, data files, model files, or skill files were modified by
  this documentation pass.

## 技能和手册固化

These candidates were confirmed by the user on 2026-05-17 and applied to the
listed skills/manual during the follow-up solidification pass.

1. `maintain-project-docs`
   - Add a stronger compression rule: when a live-status document contains
     multiple old `Active` or `Completed` sections, compress it back to one
     current snapshot plus pointers, and move durable conclusions to the
     chronological log or stable brief.
   - Add an explicit distinction between deleting stale maintained-doc text and
     deleting raw evidence artifacts. Raw `.csv`, `.json`, `.log`, `.pth`, and
     `.pkl` files should remain untouched unless the user explicitly requests
     artifact cleanup.

2. `alb-surrogate-remote-workflow`
   - Add the FD Jacobian supervision sequence as a reusable workflow: commit
     code/config first, generate stratified base manifests locally, run a
     small h-review remotely, analyze h stability locally, then launch full FD
     sampling only after the gate passes.
   - Add the monitor handoff pattern: for long remote sampling, start a local
     background monitor that writes a user-visible log, instead of keeping the
     active Codex turn in repeated sleep polling.

3. `train-alb-surrogate`
   - Add the scaled-EVS FD contract: finite-difference perturbations are applied
     only to base inputs `ex, ey, vx, vy`; derived scaled-EVS features must be
     recomputed by the scaler, not written as independent perturbation columns.
   - Add the first-pass FD loss rule: compare raw nondimensional force
     increments, do not divide by `delta`, and apply cross-term weighting only
     to `dFy/dex`, `dFx/dey`, `dFy/dvx`, and `dFx/dvy`.

4. `operate-remote-workstation`
   - Add a non-training AMD64 sampling reminder: use
     `G:/GWJ/envs/ALB/python.exe`, `pooln=60`, Task Scheduler through
     `remote_job.py`, and set single-threaded BLAS/OpenMP environment variables.

## 已更新固化目标

- `C:/Users/73401/.codex/skills/maintain-project-docs/SKILL.md`
- `C:/Users/73401/.codex/skills/alb-surrogate-remote-workflow/SKILL.md`
- `C:/Users/73401/.codex/skills/train-alb-surrogate/SKILL.md`
- `C:/Users/73401/.codex/skills/operate-remote-workstation/SKILL.md`
- `ALB_MAIN/docs/remote_workstation_connection.md`
