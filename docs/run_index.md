# ALB_PROJECTS Run Index

## Document Role

- Role: ALB_PROJECTS global run rules and placement index.
- Purpose: Define project-prefixed run number policy, run ID format, canonical
  path families, and current-status ownership.
- Allowed updates: run-number policy, project prefix mappings, run ID format,
  canonical path pointers, archive pointers, and short notes needed to find the
  current status document.
- Forbidden updates: raw logs, detailed progress tails, full metric reports,
  cleanup actions, and destructive archive decisions.
- Update cadence: when run-number policy, project prefixes, current-status
  ownership, path families, or archive pointer policy changes.
- Source of truth / Related docs:
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `docs/file_classification.md`,
  `../SURROGATE_TRAIN/docs/file_classification.md`, and
  `../SURROGATE_TRAIN/docs/current_runtime_status.md`.

This file is the workspace-global human-readable rule index for future runs. It
is not a live monitor log and should not duplicate raw evidence. Current active
run state, paths, progress, and next action belong in the owning project's
structured current-status document, currently
`../SURROGATE_TRAIN/docs/current_runtime_status.md` for SURROGATE_TRAIN work.

## Run Number Policy

- Use one run number sequence per owning project.
- Format run numbers as a project prefix plus four digits, such as `S0001` or
  `A0001`.
- Do not use bare numeric directory names such as `0001`; they are too easy to
  confuse with dates, sample counts, or seeds.
- New run IDs should put the project-local run number first:
  `<project_run_no>_<domain>_<purpose>_<size-or-key>_<date>`.
- A new launch config should record top-level `run_id`, and the task name, output
  directory, and log directory should include or clearly derive from the same
  `run_id`.
- The target policy is to also write `run_id` into generated metadata. Until the
  code supports that everywhere, the config plus the structured current-status
  entry are the active mapping.

Examples:

```text
S0001_fd_full_jacobian_20000_h1em03_20260517
S0002_queue_force3_gelu_minmax_p500_20260509
A0001_remote_helper_reference_v1_20260517
```

## Project Prefixes

| Prefix | Project | Allocation policy |
| --- | --- | --- |
| `A` | `ALB_MAIN` | Stable package helper runs, references, and package-owned evidence. |
| `S` | `SURROGATE_TRAIN` | ALBNN sampling, training, model testing, queue configs, and experiment outputs. |
| `P` | `PARAM_SCAN` | Parameter-scan jobs and generated evidence bundles. |
| `D` | `DATA_POSTPROCESS` | Postprocess jobs that produce durable generated outputs. |
| `V` | `VALIDATION` | Formal validation runs and selected validation outputs. |
| `X` | `ARTIFACTS_ARCHIVE` | Archive-owned bundles only; do not allocate new experiment runs here by default. |

Allocate the next number from the owning project's current-status document and
recent config/output names. Keep allocation notes in current status while the
run is active.

## Current Status Policy

The current-status document is the first place an agent should inspect before
launching, resuming, monitoring, or archiving active work:

```text
../SURROGATE_TRAIN/docs/current_runtime_status.md
```

For each active run, keep a stable structured block with:

```text
run_no, run_id, state, config, output root, remote root, task name, monitor command,
latest check, progress, evidence paths, current issue, next action
```

This current-status block replaces the former separate JSONL locator file. It may be
rewritten as facts change; detailed raw logs and completed-run history still
belong in raw artifacts or the appropriate chronological log.

## Path Policy

New runs should prefer these path families inside the owning subproject:

```text
run/remote/configs/<run_id>.json
outputs/<domain>/<run_id>/
logs/remote/<run_id>/
logs/local_train/<run_id>/
logs/queue/<run_id>/
outputs/archive/<run_id>/   # only after confirmed archive
```

Use `logs/remote/<run_id>/` for remote runner/stdout/stderr logs and local
remote monitor logs. Use `outputs/<domain>/<run_id>/` for CSV, JSON metadata,
plots, summaries, and other result artifacts. Use `outputs/archive/<run_id>/`
only after the task is complete and the user confirms it is inactive or
obsolete. For active, running, stopped, or failed-but-not-archived runs, keep
archive pointers out of the active locator block unless an archive actually
exists.

## Project Ownership

- `SURROGATE_TRAIN` owns ALBNN sampling, training, model testing, queue configs,
  runtime logs, and experiment outputs.
- `ALB_MAIN` owns reusable package code, stable remote helper code, package
  regression references, global docs, and this run index.
- Other subprojects should use their assigned project prefix when they create
  long-running jobs, generated evidence bundles, or archived runs.
