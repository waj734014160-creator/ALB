# coding: utf-8
"""Reusable one-shot and polling monitor for remote Windows ALB jobs."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
import time
from typing import Any

from .common import extract_json
from .common import parse_iso
from .defaults import DEFAULT_HOST
from .defaults import DEFAULT_KEY
from .defaults import DEFAULT_USER
from .transport import configure_stdio
from .transport import ps_quote
from .transport import run_remote_powershell


RUNNING_TASK_RESULT = 267009


def remote_stdout(args: argparse.Namespace, script: str, *, required: bool = False) -> str:
    result = run_remote_powershell(args, script, timeout=args.ssh_timeout)
    if result.returncode != 0 and required:
        raise RuntimeError(
            f"Remote monitor command failed with exit {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout or ""


def parse_json_output(text: str | None) -> Any:
    if not text:
        return None
    try:
        return extract_json(text)
    except Exception:
        return None


def split_lines(text: str | None) -> list[str]:
    if not text:
        return []
    cleaned = text.replace("\x00", "")
    return [
        line.rstrip("\r")
        for line in cleaned.splitlines()
        if line.strip() and not line.startswith("#< CLIXML")
    ]


def ps_common() -> str:
    return (
        "$ProgressPreference='SilentlyContinue';"
        "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false;"
        "$OutputEncoding=New-Object System.Text.UTF8Encoding $false;"
    )


def query_remote_time(args: argparse.Namespace) -> str | None:
    text = remote_stdout(args, ps_common() + "(Get-Date).ToString('o')")
    lines = split_lines(text)
    return lines[0].strip() if lines else None


def query_task(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.task_name:
        return None
    task_name = ps_quote(args.task_name)
    script = (
        ps_common()
        + f"""
$taskName = {task_name}
try {{
  $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
  $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction Stop
  [PSCustomObject]@{{
    exists = $true
    name = $taskName
    state = $task.State.ToString()
    enabled = $task.Settings.Enabled
    execution_time_limit = $task.Settings.ExecutionTimeLimit
    last_run_time = $info.LastRunTime.ToString('o')
    next_run_time = $info.NextRunTime.ToString('o')
    last_task_result = $info.LastTaskResult
  }} | ConvertTo-Json -Compress
}} catch {{
  [PSCustomObject]@{{
    exists = $false
    name = $taskName
    error = $_.Exception.Message
  }} | ConvertTo-Json -Compress
}}
"""
    )
    return parse_json_output(remote_stdout(args, script))


def query_processes(args: argparse.Namespace) -> list[dict[str, Any]]:
    if not args.process_match:
        return []
    process_match = ps_quote(args.process_match)
    script = (
        ps_common()
        + f"""
$needle = {process_match}
@(
  Get-CimInstance Win32_Process |
  Where-Object {{ $_.CommandLine -and $_.CommandLine -like "*$needle*" }} |
  Select-Object ProcessId, ParentProcessId, Name,
    @{{Name='CreationDate';Expression={{ try {{ $_.CreationDate.ToString('o') }} catch {{ [string]$_.CreationDate }} }}}},
    CommandLine
) | ConvertTo-Json -Depth 4 -Compress
"""
    )
    parsed = parse_json_output(remote_stdout(args, script))
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    return list(parsed)


def query_pid_process(args: argparse.Namespace) -> dict[str, Any] | None:
    """Return one remote process snapshot for ``args.pid`` if it is alive."""
    pid = getattr(args, "pid", None)
    if pid in (None, ""):
        return None
    script = (
        ps_common()
        + f"""
$pidValue = {int(pid)}
Get-CimInstance Win32_Process -Filter "ProcessId = $pidValue" |
  Select-Object ProcessId, ParentProcessId, Name,
    @{{Name='CreationDate';Expression={{ try {{ $_.CreationDate.ToString('o') }} catch {{ [string]$_.CreationDate }} }}}},
    CommandLine |
  ConvertTo-Json -Depth 4 -Compress
"""
    )
    parsed = parse_json_output(remote_stdout(args, script))
    return parsed if isinstance(parsed, dict) else None


def query_file_info(args: argparse.Namespace, path: str) -> dict[str, Any]:
    remote_path = ps_quote(path)
    script = (
        ps_common()
        + f"""
$path = {remote_path}
if (Test-Path -LiteralPath $path) {{
  $item = Get-Item -LiteralPath $path
  [PSCustomObject]@{{
    exists = $true
    path = $path
    length = $item.Length
    last_write_time = $item.LastWriteTime.ToString('o')
  }} | ConvertTo-Json -Compress
}} else {{
  [PSCustomObject]@{{
    exists = $false
    path = $path
  }} | ConvertTo-Json -Compress
}}
"""
    )
    return parse_json_output(remote_stdout(args, script)) or {"exists": False, "path": path}


def query_json_file(args: argparse.Namespace, path: str) -> dict[str, Any] | None:
    remote_path = ps_quote(path)
    script = (
        ps_common()
        + f"if (Test-Path -LiteralPath {remote_path}) "
        + f"{{ [System.IO.File]::ReadAllText({remote_path}) }}"
    )
    text = remote_stdout(args, script).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def query_file_text(args: argparse.Namespace, path: str) -> str:
    remote_path = ps_quote(path)
    script = (
        ps_common()
        + f"if (Test-Path -LiteralPath {remote_path}) "
        + f"{{ [System.IO.File]::ReadAllText({remote_path}) }}"
    )
    return remote_stdout(args, script)


def query_text_tail(args: argparse.Namespace, path: str, tail: int) -> list[str]:
    remote_path = ps_quote(path)
    script = (
        ps_common()
        + f"if (Test-Path -LiteralPath {remote_path}) "
        + "{ Get-Content -LiteralPath "
        + remote_path
        + f" -Tail {int(tail)} | ForEach-Object {{ ([string]$_) -replace [char]0,'' }} }}"
    )
    return split_lines(remote_stdout(args, script))


def query_directory_files(args: argparse.Namespace, path: str) -> list[dict[str, Any]]:
    remote_path = ps_quote(path)
    script = (
        ps_common()
        + f"""
$path = {remote_path}
if (Test-Path -LiteralPath $path) {{
  @(
    Get-ChildItem -LiteralPath $path |
    Sort-Object LastWriteTime -Descending |
    Select-Object Name, Length,
      @{{Name='LastWriteTime';Expression={{ $_.LastWriteTime.ToString('o') }}}}
  ) | ConvertTo-Json -Depth 4 -Compress
}} else {{
  @() | ConvertTo-Json -Compress
}}
"""
    )
    parsed = parse_json_output(remote_stdout(args, script))
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    return list(parsed)


def parse_named_path(text: str) -> tuple[str, str]:
    if "=" not in text:
        return "log", text
    name, path = text.split("=", 1)
    return name.strip() or "log", path.strip()


def progress_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None

    prepared_input_mode = (
        metadata.get("mode") == "evaluate_prepared_inputs"
        or (
            metadata.get("input_rows") is not None
            and metadata.get("target_valid_samples") is None
        )
    )
    target = metadata.get("target_valid_samples", metadata.get("n_samples"))
    completion_basis = "valid"
    if prepared_input_mode:
        target = metadata.get("input_rows")
        completion_basis = "attempted"
    valid = metadata.get("valid_samples", metadata.get("valid_count"))
    attempted = metadata.get(
        "attempted_samples",
        metadata.get("attempted_count", metadata.get("attempted_rows")),
    )
    invalid = metadata.get("invalid_samples")
    elapsed = metadata.get("elapsed_s", metadata.get("elapsed_seconds"))
    progress_value = attempted if completion_basis == "attempted" else valid

    progress: dict[str, Any] = {
        "target": target,
        "valid": valid,
        "attempted": attempted,
        "invalid": invalid,
        "elapsed_s": elapsed,
        "valid_rate": metadata.get("valid_rate"),
        "completion_basis": completion_basis,
    }
    if progress["valid_rate"] is None and valid is not None and attempted:
        progress["valid_rate"] = float(valid) / float(attempted)
    if target is not None and progress_value is not None:
        progress["remaining"] = max(float(target) - float(progress_value), 0.0)
    if progress_value is not None and elapsed:
        progress["progress_per_s"] = float(progress_value) / float(elapsed)
    if valid is not None and elapsed:
        progress["valid_per_s"] = float(valid) / float(elapsed)
    if progress.get("remaining") is not None and progress.get("progress_per_s"):
        progress["eta_s"] = progress["remaining"] / progress["progress_per_s"]
    return progress


def solver_settings_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    settings = metadata.get("fixed_nondim_parameters") or metadata.get("solver_config")
    if not isinstance(settings, dict):
        return None
    thermal = settings.get("thermal") or {}
    return {
        "damp": settings.get("damp"),
        "max_iter": settings.get("max_iter"),
        "thermal_max_iter": thermal.get("max_iter"),
        "solver_retry_policy": settings.get("solver_retry_policy")
        or settings.get("retry_policy"),
    }


def state_from_snapshot(snapshot: dict[str, Any]) -> str:
    task = snapshot.get("task") or {}
    pid_process = snapshot.get("pid_process")
    processes = snapshot.get("processes") or []
    progress = snapshot.get("progress") or {}
    target = progress.get("target")
    valid = progress.get("valid")
    attempted = progress.get("attempted")
    basis = progress.get("completion_basis", "valid")
    if (
        basis == "attempted"
        and target is not None
        and attempted is not None
        and float(attempted) >= float(target)
    ):
        return "completed"
    if target is not None and valid is not None and float(valid) >= float(target):
        return "completed"
    if str(task.get("state", "")).lower() == "running":
        return "running"
    if pid_process:
        return "running"
    if processes:
        return "running"
    if task.get("exists"):
        last_result = task.get("last_task_result")
        if last_result is not None and int(last_result) != RUNNING_TASK_RESULT:
            return f"task_{str(task.get('state', 'unknown')).lower()}({last_result})"
        return f"task_{str(task.get('state', 'unknown')).lower()}"
    return "not_running"


def query_job(args: argparse.Namespace) -> dict[str, Any]:
    metadata = query_json_file(args, args.metadata) if args.metadata else None
    logs = {}
    for log_arg in args.log or []:
        name, path = parse_named_path(log_arg)
        logs[name] = {
            "path": path,
            "info": query_file_info(args, path),
            "tail": query_text_tail(args, path, args.tail),
        }

    snapshot: dict[str, Any] = {
        "remote_time": query_remote_time(args),
        "task": query_task(args),
        "pid": getattr(args, "pid", None),
        "pid_process": query_pid_process(args),
        "process_match": args.process_match,
        "processes": query_processes(args),
        "metadata_path": args.metadata,
        "metadata_info": query_file_info(args, args.metadata) if args.metadata else None,
        "metadata": metadata,
        "progress": progress_from_metadata(metadata),
        "solver_settings": solver_settings_from_metadata(metadata),
        "csv_path": args.csv,
        "csv_info": query_file_info(args, args.csv) if args.csv else None,
        "logs": logs,
    }
    snapshot["state"] = state_from_snapshot(snapshot)
    return snapshot


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    seconds = max(float(seconds), 0.0)
    return str(timedelta(seconds=int(round(seconds))))


def summarize(snapshot: dict[str, Any]) -> str:
    lines = [
        f"remote_time: {snapshot.get('remote_time')}",
        f"state: {snapshot.get('state')}",
    ]
    task = snapshot.get("task") or {}
    if task:
        lines.append(
            "task: "
            f"{task.get('name')} state={task.get('state')} "
            f"enabled={task.get('enabled')} last_result={task.get('last_task_result')}"
        )
    processes = snapshot.get("processes") or []
    pid_process = snapshot.get("pid_process")
    if pid_process:
        lines.append(f"pid: {pid_process.get('ProcessId')} alive")
    elif snapshot.get("pid") is not None:
        lines.append(f"pid: {snapshot.get('pid')} not found")
    if processes:
        pids = ", ".join(str(item.get("ProcessId")) for item in processes)
        lines.append(f"processes: {len(processes)} pid={pids}")
    else:
        lines.append("processes: 0")

    progress = snapshot.get("progress") or {}
    if progress:
        valid = progress.get("valid")
        target = progress.get("target")
        attempted = progress.get("attempted")
        rate = progress.get("valid_rate")
        speed = progress.get("valid_per_s")
        eta_s = progress.get("eta_s")
        lines.append(f"progress: {valid}/{target} valid, attempted={attempted}")
        if rate is not None:
            lines.append(f"valid_rate: {float(rate):.4f}")
        if speed is not None:
            lines.append(f"valid_per_s: {float(speed):.4f}")
        if eta_s is not None:
            lines.append(f"eta: {format_duration(float(eta_s))}")
            remote_time = parse_iso(snapshot.get("remote_time"))
            if remote_time is not None:
                finish = remote_time + timedelta(seconds=float(eta_s))
                lines.append(f"eta_finish_remote_time: {finish.isoformat(timespec='seconds')}")

    settings = snapshot.get("solver_settings") or {}
    if settings:
        lines.append(
            "solver: "
            f"damp={settings.get('damp')} "
            f"max_iter={settings.get('max_iter')} "
            f"thermal_max_iter={settings.get('thermal_max_iter')}"
        )

    for key in ("metadata_info", "csv_info"):
        info = snapshot.get(key) or {}
        if info.get("exists"):
            lines.append(
                f"{key}: {info.get('path')} "
                f"bytes={info.get('length')} write={info.get('last_write_time')}"
            )

    logs = snapshot.get("logs") or {}
    for name, item in logs.items():
        info = item.get("info") or {}
        if info.get("exists"):
            lines.append(
                f"log[{name}]: {info.get('path')} "
                f"bytes={info.get('length')} write={info.get('last_write_time')}"
            )
        tail = [line for line in item.get("tail", []) if str(line).strip()]
        if tail:
            lines.append(f"log[{name}]_tail:")
            lines.extend(f"  {line}" for line in tail[-8:])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor a remote Windows ALB job")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--ssh-timeout", type=int, default=30)
    parser.add_argument("--task-name", default=None)
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--process-match", default=None)
    parser.add_argument("--metadata", default=None)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--tail", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print raw JSON snapshot")
    parser.add_argument("--watch", action="store_true", help="Poll until stopped or terminal")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument(
        "--keep-watching-terminal",
        action="store_true",
        help="Keep polling after completed/exited/not-running states",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = build_parser().parse_args(argv)
    while True:
        snapshot = query_job(args)
        if args.json:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        else:
            print(summarize(snapshot), flush=True)
        if not args.watch:
            return 0
        if (
            not args.keep_watching_terminal
            and snapshot.get("state") != "running"
        ):
            return 0
        time.sleep(max(int(args.poll_seconds), 1))


if __name__ == "__main__":
    raise SystemExit(main())
