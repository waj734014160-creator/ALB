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

- Thermal ALBNN base input columns:
  `ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim, lr, cq0, cq1, cq2`
- Oil-film solver default `max_iter` is `120`.
- Avoid unstable tail-force sampling regions when generating general-purpose
  training data:
  - `lr < 0.30`
  - `lambda_value / lr > 10`
  - `ecc = sqrt(ex^2 + ey^2) > 0.88`
- Detailed mesh and tail-force analysis:
  see the G-drive result folder created on `2026-05-07` for
  `mesh_independence_120x80`.

## Remote Computer Connection

Remote workstation access is available by SSH over LAN or ZeroTier. Keep
detailed connection checks, paths, and long-job launch notes in
`docs/remote_workstation_connection.md`.

Do not store passwords, private keys, recovery codes, or API keys in this file.
Store those in the OS credential manager, SSH agent, or another local secret
store instead.
