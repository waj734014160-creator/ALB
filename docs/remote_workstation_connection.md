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

The preferred local wrappers are:

```powershell
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_queue_albnn_activation_sweep.py --config ../SURROGATE_TRAIN/run/remote/configs/<queue>.json
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_start_albnn_train.py
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_query_albnn_status.py
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_monitor_job.py --task-name <task> --process-match <needle>
```

The stable implementation is maintained in `ALB.remote`:
`albnn_queue`, `albnn_start`, `albnn_status`, `monitor`, and `transport`. The
`SURROGATE_TRAIN/run/remote` scripts are compatibility entry points so existing
commands and JSON queue configs continue to work.

The start wrapper generates a temporary local PowerShell runner, uploads it with
`scp`, starts a Task Scheduler job, and disables the one-shot schedule after the
manual start to prevent a duplicate later run. The ALBNN status wrapper now
delegates its Task Scheduler, process, file, and log checks to
`ALB.remote.monitor`, which uses several short SSH commands instead of one large
encoded PowerShell command so it is not sensitive to command-line length
limits.

Default future launch behavior: remote ALBNN training should also start local
monitoring. Prefer the JSON queue wrapper for launches because it resumes active
jobs, polls status, and syncs `status.json`, `status.jsonl`, and log tails under
`../SURROGATE_TRAIN/outputs/queue_logs`. If a job is launched directly with the
start wrapper, start the matching queue monitor immediately.

Training launch preflight: the remote start wrapper checks that both configured
training CSVs exist and are non-empty before it creates a Task Scheduler run.
For generation-to-training watchers, still gate queue launch on split success,
train/validation CSV presence, split summary presence, nonzero row counts, and
zero train/validation input overlap. Do not start a training queue only because
generation metadata reached the requested attempted row count.

For non-training long jobs such as sample generation, use the generic monitor
wrapper instead of ad-hoc SSH status snippets. It queries Task Scheduler,
matching processes, metadata progress, CSV/log file timestamps, and ETA through
short PowerShell commands.

Generic one-shot monitor pattern for a remote generation task:

```powershell
E:/Anaconda2023/envs/ALB/python.exe ../SURROGATE_TRAIN/run/remote/remote_monitor_job.py `
  --task-name <task-name> `
  --process-match <stable-commandline-needle> `
  --metadata <remote-metadata-json> `
  --csv <remote-output-csv> `
  --log stdout=<remote-stdout-log> `
  --log stderr=<remote-stderr-log>
```

## ALBNN Job Pointers

Current ALBNN data, model, task, and sampling lessons live in
`../SURROGATE_TRAIN/docs/albnn_training_brief.md`; detailed dated history lives
in `../SURROGATE_TRAIN/docs/albnn_training_log.md`. Keep this connection
document focused on stable remote-operation mechanics and only record short
pointers that help operators find the active job.

Active remote ALBNN workflow pointers:

- Live progress buffer:
  `../SURROGATE_TRAIN/docs/current_runtime_status.md`.
- First-read ALBNN workflow brief:
  `../SURROGATE_TRAIN/docs/albnn_training_brief.md`.

Do not keep active task names, PIDs, ETAs, queue roots, or current model names
in this stable connection manual. Put live state in `current_runtime_status.md`
and dated run history in `albnn_training_log.md`.

Older completed or stopped ALBNN runs should stay in the surrogate-training
document unless they introduce a reusable remote-operation lesson.

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
- Keep remote launcher logs structured and English-only by default. Native
  Windows tools such as `schtasks.exe` may emit localized text over SSH; mixed
  PowerShell CLIXML, UTF-8, and CP936/GBK output can produce replacement
  characters and has caused local Python `UnicodeEncodeError` during queue
  launches. Capture native command output for exit-code checks, but do not print
  it in normal logs; expose raw output only behind an explicit verbose/debug
  flag.
- For Python wrappers that may print remote output on Windows, configure
  `stdout` and `stderr` as UTF-8 with replacement handling, and set
  `PYTHONIOENCODING=utf-8` when one wrapper launches another.
- If a scheduled controller needs child processes, redirect stdout and stderr
  to separate files and check child exit codes explicitly.
- For long watcher/controller tasks, set Task Scheduler `ExecutionTimeLimit`
  explicitly to at least the runner deadline. The default can be `PT72H`, which
  may stop a healthy watcher before a multi-day dependency chain completes.
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
