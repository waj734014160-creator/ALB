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
is not the append-only registry of run events, not a live monitor log, and should
not duplicate raw evidence. Registration facts live in each owning project's
`docs/run_registry.jsonl`. Existing historical runs are not required to be
backfilled unless they are reviewed, reused, or archived.

## Run Number Policy

- Use one run number sequence per owning project.
- Format run numbers as a project prefix plus four digits, such as `S0001` or
  `A0001`.
- Do not use bare numeric directory names such as `0001`; they are too easy to
  confuse with dates, sample counts, or seeds.
- New run IDs should use:
  `<domain>_<purpose>_<size-or-key>_<date>_<project_run_no>`.
- A new launch config must record top-level `run_id`, and the task name, output
  directory, and log directory should include or clearly derive from the same
  `run_id`.
- The target policy is to also write `run_id` into generated metadata. Until the
  code supports that, the config plus the owning project's
  `docs/run_registry.jsonl` are the authoritative mapping.

Examples:

```text
fd_full_jacobian_20000_h1em03_20260517_S0001
queue_force3_gelu_minmax_p500_20260509_S0002
remote_helper_reference_v1_20260517_A0001
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
```

## Path Policy

New runs should prefer these path families inside the owning subproject:

```text
run/remote/configs/<run_id>.json
outputs/<domain>/<run_id>/
logs/remote/<run_id>/
logs/local_train/<run_id>/
logs/queue/<run_id>/
outputs/archive/<run_id>/
```

Use `logs/remote/<run_id>/` for remote runner/stdout/stderr logs and local
remote monitor logs. Use `outputs/<domain>/<run_id>/` for CSV, JSON metadata,
plots, summaries, and other result artifacts. Use `outputs/archive/<run_id>/`
only after the task is complete and the user confirms it is inactive or
obsolete.

## Registry Event Policy

Each owning project stores append-only events in:

```text
docs/run_registry.jsonl
```

Each event must include at least:

```text
event, timestamp, run_no, run_id, owner, domain, state, config, outputs, logs, archive, notes
```

`register` allocates a new project-local run number and appends the first event.
`update` appends state changes such as `running`, `completed`, `failed`, or
`archived` without rewriting previous events. `list` and `validate` read the
JSONL source directly; this Markdown file is not parsed as a registry table.

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
