# Documentation Role And Daily Update Index

## Document Role

- Role: Centralized document role index and daily audit index.
- Purpose: Define maintained-document roles, allowed updates, forbidden updates,
  update cadence, and daily audit triggers.
- Allowed updates: document-role entries, daily audit rules, evidence-source
  pointers, and role-boundary corrections.
- Forbidden updates: realtime runtime state, detailed run history, source-code
  changes, raw evidence dumps, and cleanup actions.
- Update cadence: when maintained document roles, entry points, or audit rules
  change.
- Source of truth / Related docs: each indexed document's local
  `Document Role` block.

This is the centralized role index for maintained project documents. Every
documentation-maintenance pass must read this file first, then read the target
document's own `Document Role` block before editing it.

## Role Index Rule

- A maintained document may be edited only for the role listed here and in its
  own `Document Role` block.
- If this index and the target document disagree, stop and report the conflict
  before editing.
- If a requested update belongs to a different role, write it to the correct
  document or produce a migration recommendation.
- Documents not listed here are not routine maintenance targets. Add an index
  entry and a local `Document Role` block before maintaining them.
- This index does not grant permission to delete, move, archive, launch jobs,
  edit source code, or rewrite raw evidence.

## Core Document Roles

| File | Role | Brief description | Allowed updates | Forbidden updates | Cadence / trigger |
| --- | --- | --- | --- | --- | --- |
| `ALB_MAIN/docs/daily_maintenance/daily_doc_update_index.md` | Centralized document role index and daily audit index | The source of truth for maintained-document roles and audit triggers. | Document-role entries, daily audit rules, evidence-source pointers, role-boundary corrections. | Realtime runtime state, detailed run history, source-code changes, raw evidence dumps, cleanup actions. | When maintained document roles, entry points, or audit rules change. |
| `SURROGATE_TRAIN/docs/current_runtime_status.md` | Short-term memory / live status buffer | The only realtime state for active training, sampling, queue, and monitor work. | Active task names, PIDs, latest loss/progress/ETA, active log paths, check commands, next action. | Durable lessons, full incident writeups, historical narrative, stable manuals. | Update after status checks, launches, syncs, stops, or monitor runs. |
| `SURROGATE_TRAIN/docs/albnn_training_log.md` | Long-term memory / chronological log | Daily durable ALBNN history after the "sleep" pass. | At most one dated daily entry with completed events, key metrics, incident root causes, reproducible commands, final conclusions. | Realtime ticks, latest loss polling, live PIDs, active ETAs, repeated monitor snapshots. | Daily maintenance only by default, or explicit user request for immediate durable logging. |
| `SURROGATE_TRAIN/docs/albnn_training_brief.md` | Stable current understanding | First-read stable ALBNN workflow state. | Current recommended workflow, canonical data/model pointers, input/output contracts, sampling settings, durable lessons. | Live PIDs, latest loss, ETAs, log tails, transient monitor output, daily audit minutiae. | Only when workflow structure, canonical paths, sampling settings, or durable lessons change. |
| `SURROGATE_TRAIN/docs/albnn_training_info.md` | Reading index | Short entry point for ALBNN docs. | Read order, role-index pointer, source-of-truth pointer. | Runtime status, metrics, history, operational details. | Rare; update when entry-point docs or read order changes. |
| `ALB_MAIN/docs/run_index.md` | ALB_PROJECTS global run rules and placement index | Human-readable policy for project-prefixed run numbers, run ID format, per-project JSONL registry sources, and canonical config/output/log pointers. | Run-number policy, project prefix mappings, registry source pointers, canonical path pointers, and archive pointer policy. | Raw logs, detailed progress tails, model metrics better owned by run outputs, append-only registry event facts, and cleanup actions. | When run-registration policy, project prefixes, registry source locations, path families, or archive pointer policy changes. |
| `ALB_MAIN/docs/remote_workstation_connection.md` | Stable remote-operation manual | Reusable remote connection, Task Scheduler, SSH, runner, and monitor mechanics. | Connection facts, stable command patterns, wrapper ownership, reusable remote-operation lessons. | Current task progress, PIDs, latest loss, active ETAs, per-run metrics. | When remote mechanics, paths, wrappers, or credential-handling guidance changes. |
| `ALB_MAIN/docs/file_classification.md` | ALB_MAIN file ownership and cleanup policy | File groups, ownership boundaries, archive/delete policy. | File categories, representative paths, retention/archive rules, cleanup risk notes. | Live runtime state, model progress, detailed run history. | When major file groups, archive categories, or cleanup policies change. |
| `SURROGATE_TRAIN/docs/file_classification.md` | SURROGATE_TRAIN file ownership and cleanup policy | Training repo file groups, evidence categories, and cleanup policy. | Training data/model/log/script categories, ownership boundaries, archive/delete rules. | Live progress, latest metrics, detailed chronological history. | When training outputs, scripts, models, monitor logs, or cleanup policy changes. |
| `ALB_MAIN/docs/daily_summary_log.md` | Project-level daily maintenance summary | Concise daily record of documentation maintenance and stable project changes. | Daily maintenance summaries, cleanup confirmations, stable doc/code organization decisions. | Realtime job state, raw log dumps, detailed ALBNN metrics better owned by `albnn_training_log.md`. | Daily maintenance pass or explicit project-summary request. |
| `ALB_MAIN/docs/daily_maintenance/doc_maintenance_audit_YYYYMMDD.md` | Daily audit evidence | Evidence from one scheduled documentation-maintenance pass. | Files checked, decisions, no-change reasons, stale candidates, cleanup confirmation lists. | Source edits, runtime state ownership, long-term project manuals. | Created/refreshed by each scheduled daily audit. |
| `ALB_MAIN/docs/alb_package_overview.md` | Stable package orientation | ALB package module map and public interface groups. | Public API/module ownership changes and package-boundary notes. | Experiment runtime state, daily maintenance history. | When public APIs, module ownership, or package boundaries change. |
| `ALB_MAIN/docs/formula/thermal_model.md` | Stable formula and implementation reference | Formula-level explanation of the thermal-pressure model, discretization, and implementation mapping. | Governing equations, nondimensional forms, FEM discretization, boundary-condition explanations, and code-to-formula mapping. | Realtime runtime state, per-run metrics, task PIDs, and raw logs. | When thermal-pressure equations, discretization, or implementation mapping changes. |

## Conditional Workspace Role Checks

| File | Role | Check trigger |
| --- | --- | --- |
| `ALB_MAIN/AGENTS.md` | Stable agent policy | Agent policy, source-change boundary, package orientation, or remote-operation rule changes. |
| `SURROGATE_TRAIN/AGENTS.md` | Stable training-project agent policy | Local/remote launch boundary, documentation frequency, training-source ownership, or document-role policy changes. |
| `ARTIFACTS_ARCHIVE/docs/file_classification.md` | Archive file ownership policy | Archive structure or retention policy changes. |
| `DATA_POSTPROCESS/docs/file_classification.md` | Postprocess file ownership policy | Postprocess/notebook categories change. |
| `PARAM_SCAN/docs/file_classification.md` | Parameter-scan file ownership policy | Parameter-scan task or artifact categories change. |
| `VALIDATION/docs/file_classification.md` | Validation file ownership policy | Validation/test artifact categories change. |
| `SPLIT_INDEX.md` | Split workspace index | Project membership or dependency convention changes. |
| `SURROGATE_TRAIN/docs/run_index.md` | Pointer to global run rules and local registry | Only when the canonical global run-index location or local registry path changes. |

## Daily Audit Rule

- The daily audit must read every required file in the core role table that
  exists.
- If a listed file needs a content change, update it only within its role.
- If a listed file does not need a content change, record that no-change
  decision in the day's `doc_maintenance_audit_YYYYMMDD.md`.
- Check indexed narrative documents for compression triggers: outdated
  experience, outdated logs, or excessive length.
- Compress experience by summarizing durable lessons. Remove outdated narrative
  logs from maintained docs after useful lessons are preserved.
- Preserve incident cases, root-cause notes, final metrics, and reference
  workflows that remain useful for future diagnosis or reproduction.

## Evidence Sources To Inspect

These are raw evidence sources, not maintained narrative documents. The daily
audit may summarize them into the correct role-owned document.

| Evidence source | Use |
| --- | --- |
| `SURROGATE_TRAIN/models/*/metadata.json` | Completed model configuration and metrics. |
| `SURROGATE_TRAIN/models/*/validation_summary.json` | Independent validation metrics. |
| `SURROGATE_TRAIN/models/*/manual_termination.json` | Manual-stop evidence. |
| `SURROGATE_TRAIN/outputs/local_train_logs/` | Local training stdout/stderr and launch metadata. |
| `SURROGATE_TRAIN/outputs/remote_monitor_logs/` | Remote sampling monitor status. |
| `SURROGATE_TRAIN/outputs/queue_logs/` | Remote training queue status and synced tails. |
| `SURROGATE_TRAIN/logs/` | Preferred future location for run logs, local monitors, remote stdout/stderr mirrors, and queue log streams. |
| `ALB_MAIN/docs/run_index.md` | Human-readable workspace-global run-number and run-path policy. |
| `*/docs/run_registry.jsonl` | Per-project append-only run-registration event source for registered future runs. |
| `ALB_MAIN/docs/daily_maintenance/latest_codex_daily_doc_maintenance_status.txt` | Machine-readable pointer to the latest scheduled maintenance pass; generated by the audit workflow and not a maintained narrative document. |
| `ALB_MAIN/docs/daily_maintenance/logs/` | Scheduled maintenance stdout/stderr/final-message evidence. |
