# ALB_MAIN Agent Instructions

This file stores stable project-level instructions for coding agents working in
this repository.

## Environment

- Python: `E:/Anaconda2023/envs/ALB/python.exe`
- Shell: PowerShell 5.1
- In PowerShell commands, use `;` instead of `&&`.
- Repository root: this directory, `ALB_MAIN` inside `G:/ALB_PROJECTS`

## Code Conventions

- Do not modify source code unless one of these is true: the user explicitly
  asks for a code change, or the user's request cannot be fulfilled without a
  code change.
- For small or lightweight requests, prefer reusing existing scripts, CLIs,
  configs, and documented commands before adding new code.
- All code comments must be in English.
- New scripts must include at least brief comments for the main workflow,
  assumptions, and non-obvious steps.
- Package/module code must include complete, maintainable docstrings and
  comments for public APIs, important data contracts, and non-trivial logic.
- Use `miu`, not `u`, for viscosity.
- Use `lambda_value`, not bare `lambda`.
- Test files must wrap `plt.show()` in `if __name__ == '__main__':`.
- Prefer `rg` for searching files and text.

## Documentation Language

- Human-facing policy, overview, maintenance, audit, and operation documents
  should be written in Chinese. This includes files such as
  `docs/alb_package_overview.md`, `docs/daily_summary_log.md`,
  `docs/file_classification.md`, `docs/project_overview.md`,
  `docs/remote_workstation_connection.md`, `docs/run_index.md`, and similar
  maintained documents in sibling projects.
- Code comments, docstrings, inline implementation notes, CLI help text that is
  embedded in source code, and generated script comments must remain in English
  for encoding and tooling compatibility.
- When a maintained human-facing document is already partly English, future
  edits should move touched sections toward Chinese rather than adding more
  English policy text.

## ALB Package Orientation

Read `docs/alb_package_overview.md` before changing package modules or public
interfaces. The document summarizes the `ALB/` module map, top-level lazy
exports in `ALB/__init__.py`, and the main interface groups for system builders,
config dataclasses, bearing/film models, thermal/nondimensional helpers, ALBNN
surrogates, remote helpers, and task/result utilities.

When adding a public API, update both the module docstring/comments and the
package overview. Keep reusable numerical code in `ALB_MAIN/ALB`; sibling
projects such as `SURROGATE_TRAIN` should import it instead of duplicating ALB
package code.

## Documentation Role Boundary

Before maintaining project documents, read
`docs/daily_maintenance/daily_doc_update_index.md` first. It is the centralized
document-role index. Then read the target document's local `Document Role`
block and edit only content allowed by that role.

If the centralized index and the target document disagree, stop and report the
conflict before editing. Live runtime state belongs in
`../SURROGATE_TRAIN/docs/current_runtime_status.md`; daily durable ALBNN history
belongs in `../SURROGATE_TRAIN/docs/albnn_training_log.md`; stable remote
mechanics belong in `docs/remote_workstation_connection.md`.

## Run And Current Status Orientation

Use `docs/run_index.md` for workspace-wide run-number and path rules. Use the
owning project's current-status document as the first agent-facing locator for
active work before broad project searches. For SURROGATE_TRAIN, that file is
`../SURROGATE_TRAIN/docs/current_runtime_status.md`.

Keep active run blocks structured enough to locate config, outputs, relevant
log pointers, remote task names, latest progress, current issue, and next
action. Logs are not managed through a single global layout; detailed raw
evidence remains in artifacts and durable completed-run history belongs in the
appropriate chronological log.

## ALBNN / Thermal Sampling

Thermal ALBNN sampling and remote training details live in
`../SURROGATE_TRAIN/docs/albnn_training_brief.md`; detailed dated history lives
in `../SURROGATE_TRAIN/docs/albnn_training_log.md`. The current model uses 12
base inputs and outputs `fx, fy`; re-read the brief and the live
`SURROGATE_TRAIN/task/task_albnn_data.py` before making training claims.

## Remote Computer Connection

Remote workstation access is available by SSH over LAN or ZeroTier. Keep
detailed connection checks, paths, and long-job launch notes in
`docs/remote_workstation_connection.md`.

When launching remote ALBNN training, start monitoring by default. Prefer the
JSON queue wrapper because it supervises active jobs and syncs status/log tails
to its configured output paths; if a job is launched directly with the start
wrapper, start the corresponding queue monitor immediately.

Do not store passwords, private keys, recovery codes, or API keys in this file.
Store those in the OS credential manager, SSH agent, or another local secret
store instead.
