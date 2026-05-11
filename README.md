# ALB_MAIN

Main project copy for the stable ALB package, source-code tests, and project documentation.

Contains:
- `ALB/`: core package code.
- `test/`: Python test/debug files and lightweight configs only.
- `docs/`: project documentation and file classification.
- Packaging metadata: `pyproject.toml`, `README.md`, `AGENTS.md`.

Key docs:
- `docs/alb_package_overview.md`: first-read map of `ALB/` modules and public
  interface groups.
- `docs/remote_workstation_connection.md`: stable remote workstation connection
  and long-job operation notes.
- `docs/file_classification.md`: repository file ownership and cleanup
  guardrails.

Excluded intentionally: `.env`, `.git`, IDE folders, caches, notebooks, model outputs, and generated artifacts.
