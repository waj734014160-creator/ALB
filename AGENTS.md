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

The following LAN / ZeroTier connection information is safe to keep here when it
does not include passwords, private keys, or one-time tokens.

- Connection method: `SSH or SMB/RPC on LAN or ZeroTier; WinRM and RDP are not currently open over ZeroTier`
- Hostname: `desktop-1pvi7rp`
- LAN IP: `192.168.3.90`
- ZeroTier IP: `10.182.216.22`
- Port: `SSH 22; SMB 445; RPC 135`
- Username: `desktop-1pvi7rp\workstationg`
- Local SSH key: `C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519`
- Work directory on remote host: `F:/GWJ/20260507-train`
- Shared data directory: `F:/GWJ/20260507-train/outputs`
- GPU / compute notes: `NVIDIA T600, 4 GB VRAM, driver 528.95, CUDA 12.0`
- Startup command notes: `F:/GWJ/20260507-train/run_full_ascii.ps1 starts the thermal ALBNN pipeline`

Do not store passwords, private keys, recovery codes, or API keys in this file.
Store those in the OS credential manager, SSH agent, or another local secret
store instead.
