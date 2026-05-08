# ALB_MAIN Agent Instructions

This file stores stable project-level instructions for coding agents working in
this repository.

## Environment

- Python: `E:/Anaconda2023/envs/ALB/python.exe`
- Shell: PowerShell 5.1
- In PowerShell commands, use `;` instead of `&&`.
- Repository root: this directory, `ALB_MAIN` inside `G:/ALB_PROJECTS`

## Code Conventions

- All code comments must be in English.
- Use `miu`, not `u`, for viscosity.
- Use `lambda_value`, not bare `lambda`.
- Test files must wrap `plt.show()` in `if __name__ == '__main__':`.
- Prefer `rg` for searching files and text.

## ALBNN / Thermal Sampling

Thermal ALBNN sampling and remote training details live in
`../SURROGATE_TRAIN/docs/albnn_training_info.md`. The current model uses 12
base inputs and outputs `fx, fy`; re-read that document and the live
`SURROGATE_TRAIN/task/task_albnn_data.py` before making training claims.

## Remote Computer Connection

Remote workstation access is available by SSH over LAN or ZeroTier. Keep
detailed connection checks, paths, and long-job launch notes in
`docs/remote_workstation_connection.md`.

Do not store passwords, private keys, recovery codes, or API keys in this file.
Store those in the OS credential manager, SSH agent, or another local secret
store instead.
