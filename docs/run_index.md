# ALB_PROJECTS Run Index

## Document Role

- Role: ALB_PROJECTS global run rules and placement index.
- Purpose: Define project-prefixed run number policy, run ID format, canonical
  path families, and the per-project JSONL registry source locations.
- Allowed updates: run-number policy, project prefix mappings, run ID format,
  registry source pointers, canonical path pointers, archive pointers, and short
  notes needed to find registered runs.
- Forbidden updates: raw logs, detailed progress tails, full metric reports,
  cleanup actions, and destructive archive decisions.
- Update cadence: when run-registration policy, project prefixes, registry
  source locations, path families, or archive pointer policy changes.
- Source of truth / Related docs:
  `docs/daily_maintenance/daily_doc_update_index.md`,
  `docs/file_classification.md`,
  `../SURROGATE_TRAIN/docs/file_classification.md`, and
  `../SURROGATE_TRAIN/docs/current_runtime_status.md`.

This file is the workspace-global human-readable rule index for future runs. It
is not the registry content itself, not a live monitor log, and should
not duplicate raw evidence. Registration facts live in each owning project's
`docs/run_registry.jsonl`. That JSONL registry is an agent-facing run locator
index: it is optimized for quickly finding a run's config, outputs, logs,
archive pointer, and coarse state without scanning the whole project. It should
not store detailed metrics, old event history, or replace raw evidence. Existing
historical runs are not required to be backfilled unless they are reviewed,
reused, or archived.

## Run Number Policy

- Use one run number sequence per owning project.
- Format run numbers as a project prefix plus four digits, such as `S0001` or
  `A0001`.
- Do not use bare numeric directory names such as `0001`; they are too easy to
  confuse with dates, sample counts, or seeds.
- New run IDs should put the project-local run number first:
  `<project_run_no>_<domain>_<purpose>_<size-or-key>_<date>`.
- A new launch config must record top-level `run_id`, and the task name, output
  directory, and log directory should include or clearly derive from the same
  `run_id`.
- The target policy is to also write `run_id` into generated metadata. Until the
  code supports that, the config plus the owning project's
  `docs/run_registry.jsonl` are the authoritative mapping.

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

Use `scripts/run_registry.py` to allocate the next number inside the owning
project.
The registry file is created on first registration:

```powershell
python scripts/run_registry.py register --project-root ../SURROGATE_TRAIN --domain fd_jacobian --purpose full_jacobian --size-or-key 20000_h1em03 --date 20260517
python scripts/run_registry.py paths --project-root ../SURROGATE_TRAIN --run-no S0001
```

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
the registry event's `archive` value as `null`.

The registry is a path locator, not a log manager. Registration should record
only the smallest useful locator set: `run_no`, `run_id`, `owner`, `domain`,
`state`, `config`, `outputs`, nullable `logs`, nullable `archive`, timestamp,
and short notes. Keep `logs` as `null` unless a coarse log-root pointer is
needed to locate the run. Detailed log tails, PIDs, progress, and ETA belong in
`../SURROGATE_TRAIN/docs/current_runtime_status.md` or raw log artifacts, not in
registry events.

## Registry Event Policy

Each owning project stores the current locator records in:

```text
docs/run_registry.jsonl
```

Each record must include at least:

```text
run_no, run_id, event, timestamp, owner, domain, state, config, outputs, logs, archive, notes
```

`register` allocates a new project-local run number and writes the first locator
record. `update` replaces the current record for that run with state changes
such as `running`, `completed`, `failed`, or `archived`; detailed change history
belongs in runtime/status docs or raw evidence, not in this registry. `list` and
`validate` read the JSONL source directly; this Markdown file is not parsed as a
registry table.
The `archive` field is a nullable archive pointer: use `null` until an archive
actually exists or has been confirmed as the intended staging location.
Use `scripts/run_registry.py paths --project-root <project> --run-no <run_no>`
to retrieve the current project file paths for a registered run number.

New launch paths that use `remote_job.py launch` or `remote_job.py queue` must
validate that the config's top-level `run_id` exists in the owning project's
registry before starting work. Registration failure should block the launch.
Monitoring existing jobs may still use historical configs that were created
before this policy.

## Project Ownership

- `SURROGATE_TRAIN` owns ALBNN sampling, training, model testing, queue configs,
  runtime logs, and experiment outputs.
- `ALB_MAIN` owns reusable package code, stable remote helper code, package
  regression references, global docs, and this run index.
- Other subprojects should use their assigned project prefix when they create
  long-running jobs, generated evidence bundles, or archived runs.
