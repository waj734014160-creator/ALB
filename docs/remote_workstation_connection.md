# Remote Workstation Connection

This document stores stable, non-secret connection facts and the verified
workflow for the remote workstation.

## Endpoint

- Hostname: `desktop-1pvi7rp`
- LAN IP: `192.168.3.90`
- ZeroTier IP: `10.182.216.22`
- Username: `desktop-1pvi7rp\workstationg`
- Local SSH key: `C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519`
- Remote work directory: `F:/GWJ/20260507-train`
- Remote output directory: `F:/GWJ/20260507-train/outputs`
- Verified ports over ZeroTier: `SSH 22`, `SMB 445`, `RPC 135`
- Not open over ZeroTier at last check: `WinRM 5985`, `RDP 3389`

## Connection Checks

Use the ZeroTier IP first when not on the same LAN:

```powershell
Test-Connection -ComputerName 10.182.216.22 -Count 2 -Quiet
Test-NetConnection -ComputerName 10.182.216.22 -Port 22
ssh-keyscan -T 8 -p 22 10.182.216.22
```

Confirm the host identity:

```powershell
ssh -i C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519 desktop-1pvi7rp\workstationg@10.182.216.22 hostname
ssh -i C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519 desktop-1pvi7rp\workstationg@10.182.216.22 whoami
```

Expected results:

```text
DESKTOP-1PVI7RP
desktop-1pvi7rp\workstationg
```

## Remote PowerShell

The remote SSH default shell behaves like `cmd`, so direct PowerShell pipelines
can be split incorrectly. For multi-step PowerShell checks, send an encoded
PowerShell command from the local machine.

Pattern:

```powershell
$remoteScript = @'
Get-ChildItem F:/GWJ/20260507-train/outputs
'@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remoteScript))
ssh -i C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519 desktop-1pvi7rp\workstationg@10.182.216.22 "powershell -NoProfile -EncodedCommand $encoded"
```

## Long Jobs

Do not rely on `Start-Process` launched inside an SSH session for long training
jobs. In testing, the child process did not survive SSH session teardown.

Persistent training workflow:

1. Write a `.ps1` runner under `F:/GWJ/20260507-train`.
2. Launch it with Windows Task Scheduler.
3. Monitor task state with `schtasks /Query`.
4. Monitor logs under `F:/GWJ/20260507-train/outputs/.../reports/logs`.

Example task name from the boundary-augmented ALBNN run:

```text
ALB_BoundaryAugTrain_20260508
```

## PowerShell Runner Notes

PowerShell 5.1 can turn native program `stderr` into a terminating error when
`$ErrorActionPreference = 'Stop'` is combined with `2>&1 | Tee-Object`. This can
make Task Scheduler report `LAST_RESULT=1` even when the Python process only
printed a solver warning. Avoid this pattern for long ALB sampling/training
runners.

Preferred patterns:

- Let Task Scheduler own the long-running top-level runner.
- Do not launch long work with `Start-Process` directly from an SSH session.
- Do not use `codex exec` or another Codex CLI agent in a timed watcher for
  remote status checks. It consumes Codex quota each cycle and should be
  reserved for explicit one-shot human-requested analysis.
- If a scheduled controller needs child processes, redirect stdout and stderr
  to separate files and check child exit codes explicitly.
- Do not depend on `Tee-Object` for native long-running Python logs.
- Count CSV rows with a line iterator such as `switch -File`, not
  `Get-Content -ReadCount ... | Measure-Object -Line`, because chunked reads can
  undercount rows.

Incident note from `2026-05-08`: the targeted residual sampling shards initially
used 15 concurrent scheduled tasks with `2>&1 | Tee-Object`. Many shard tasks
reported `LAST_RESULT=1` after solver messages such as `iter of filmsystem is
max`. The replacement runner uses a scheduled wave controller with lower
concurrency and explicit log files.

Quota incident note from `2026-05-08`: the legacy
`codex_cli_boundary_watch_20260508.ps1` monitor ran `codex exec` periodically to
inspect the old `RE_ALB_boundary_sample_20260508` task. It was obsolete and
could rapidly consume Codex quota. Future remote monitoring must use direct
PowerShell/Python status scripts unless the user explicitly requests a one-time
Codex CLI review.

## Path Finding

Local doc path:

```text
G:/ALB_PROJECTS/ALB_MAIN/docs/remote_workstation_connection.md
```

From `G:/ALB_PROJECTS`, find this document with:

```powershell
rg --files | rg "remote_workstation_connection.md"
```

Find remote training logs:

```powershell
$remoteScript = @'
Get-ChildItem F:/GWJ/20260507-train/outputs -Recurse -File -Filter *.log |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 30 FullName,LastWriteTime,Length
'@
```

Do not store passwords, private keys, recovery codes, API keys, or one-time
tokens in this file.
