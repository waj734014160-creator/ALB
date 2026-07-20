# coding: utf-8
"""Config-driven launch, monitor, and queue helpers for remote Windows jobs.

The public contract is a JSON object with optional ``profile`` and ``uploads``
sections plus one of ``job``, ``monitor``, or ``queue`` depending on the CLI
subcommand.  The module intentionally keeps the transport primitive small:
files are uploaded with SCP, long jobs are owned by Windows Task Scheduler, and
status is delegated to :mod:`ALB.infrastructure.remote.monitor`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

from . import monitor
from .defaults import DEFAULT_HOST
from .defaults import DEFAULT_KEY
from .defaults import DEFAULT_USER
from .transport import configure_stdio
from .transport import powershell_file_command
from .transport import ps_quote
from .transport import remote_path
from .transport import run_remote_powershell
from .transport import run_scp


INTERNAL_CONFIG_DIR = "_config_dir"
RUNNING_TASK_RESULT = monitor.RUNNING_TASK_RESULT


class RemoteJobError(RuntimeError):
    """Raised when a generic remote job config cannot be executed safely."""


@dataclass(frozen=True)
class JobSpec:
    """Resolved remote job settings used to generate and schedule a runner."""

    task_name: str
    work: str
    runner: str
    command: list[str]
    stdout: str
    stderr: str
    runner_log: str
    env: dict[str, str]
    disable_after_run: bool = True
    execution_time_limit: str | None = None
    verbose_remote_output: bool = False


@dataclass(frozen=True)
class UploadSpec:
    """One local-to-remote file copy requested by a job config."""

    local_path: Path
    remote_path: str


@dataclass(frozen=True)
class ConditionResult:
    """Outcome of one queue wait condition evaluation."""

    satisfied: bool
    failed: bool
    message: str


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON remote-job config and remember its directory for uploads."""
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise RemoteJobError("Remote job config must be a JSON object")
    config[INTERNAL_CONFIG_DIR] = str(config_path.parent)
    return config


def profile_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return connection and default path values with package defaults applied."""
    profile = dict(config.get("profile") or {})
    return {
        "host": profile.get("host", DEFAULT_HOST),
        "user": profile.get("user", DEFAULT_USER),
        "key": profile.get("key", DEFAULT_KEY),
        "connect_timeout": int(profile.get("connect_timeout", 10)),
        "ssh_timeout": int(profile.get("ssh_timeout", 30)),
        "work": profile.get("work"),
        "root": profile.get("root"),
        "remote_python": profile.get("remote_python"),
    }


def connection_args(config: dict[str, Any]) -> argparse.Namespace:
    """Build the Namespace shape expected by transport and monitor helpers."""
    profile = profile_config(config)
    return argparse.Namespace(
        host=profile["host"],
        user=profile["user"],
        key=profile["key"],
        connect_timeout=profile["connect_timeout"],
        ssh_timeout=profile["ssh_timeout"],
    )


def _context(config: dict[str, Any]) -> dict[str, str]:
    profile = profile_config(config)
    return {
        key: str(value)
        for key, value in profile.items()
        if value is not None
    }


def expand_value(value: Any, context: dict[str, str]) -> Any:
    """Expand ``${name}`` placeholders in strings, lists, and dictionaries."""
    if isinstance(value, str):
        result = value
        for key, replacement in context.items():
            result = result.replace("${" + key + "}", replacement)
        return result
    if isinstance(value, list):
        return [expand_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: expand_value(item, context) for key, item in value.items()}
    return value


def is_remote_absolute(path: str) -> bool:
    """Return whether ``path`` is already absolute for the remote host."""
    return bool(re.match(r"^[A-Za-z]:[\\/]", path)) or path.startswith("/")


def normalize_remote_path(path: str, base: str | None = None) -> str:
    """Normalize slashes and optionally resolve a relative remote path."""
    normalized = str(path).replace("\\", "/")
    if base and not is_remote_absolute(normalized):
        return remote_path(base, normalized)
    return normalized


def safe_name(text: str) -> str:
    """Return a filesystem-safe token for generated runner and log paths."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "remote_job"


def _required_remote_base(profile: dict[str, Any], key: str) -> str:
    value = profile.get(key)
    if not value:
        raise RemoteJobError(f"profile.{key} is required for this job config")
    return str(value)


def build_job_spec(config: dict[str, Any]) -> JobSpec:
    """Resolve the ``job`` section into concrete command, log, and task paths."""
    profile = profile_config(config)
    work = normalize_remote_path(_required_remote_base(profile, "work"))
    log_root = normalize_remote_path(str(profile.get("root") or work))
    job = dict(config.get("job") or {})
    if not job:
        raise RemoteJobError("Config must contain a 'job' section")

    context = _context(config)
    job = expand_value(job, context)
    task_name = str(job.get("task_name") or "").strip()
    if not task_name:
        raise RemoteJobError("job.task_name is required")

    command = job.get("command") or job.get("argv")
    if not isinstance(command, list) or not command:
        raise RemoteJobError("job.command must be a non-empty list")
    command = [str(item) for item in command]

    token = safe_name(task_name)
    log_dir = remote_path(log_root, "reports", "logs")
    runner = normalize_remote_path(
        str(job.get("runner") or f"run_{token}.ps1"),
        work,
    )
    stdout = normalize_remote_path(
        str(job.get("stdout") or remote_path(log_dir, f"{token}.stdout.log")),
        log_root,
    )
    stderr = normalize_remote_path(
        str(job.get("stderr") or remote_path(log_dir, f"{token}.stderr.log")),
        log_root,
    )
    runner_log = normalize_remote_path(
        str(job.get("runner_log") or remote_path(log_dir, f"{token}.runner.log")),
        log_root,
    )
    env = {str(key): str(value) for key, value in (job.get("env") or {}).items()}
    return JobSpec(
        task_name=task_name,
        work=work,
        runner=runner,
        command=command,
        stdout=stdout,
        stderr=stderr,
        runner_log=runner_log,
        env=env,
        disable_after_run=bool(job.get("disable_after_run", True)),
        execution_time_limit=job.get("execution_time_limit"),
        verbose_remote_output=bool(job.get("verbose_remote_output", False)),
    )


def powershell_array(items: list[str]) -> str:
    """Render a PowerShell array literal with safe single-quoted strings."""
    lines = ["@("]
    for index, item in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        lines.append(f"    {ps_quote(item)}{suffix}")
    lines.append(")")
    return "\n".join(lines)


def _parent_dir(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else path


def build_runner_content(spec: JobSpec) -> str:
    """Generate the stable remote PowerShell runner for one scheduled job."""
    env_lines = []
    for key, value in sorted(spec.env.items()):
        env_lines.append(f"$env:{key} = {ps_quote(value)}")
    env_block = "\n".join(env_lines)
    return f"""# Generated by ALB.infrastructure.remote.job. Edit the JSON config, not this runner.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$work = {ps_quote(spec.work)}
$taskName = {ps_quote(spec.task_name)}
$stdout = {ps_quote(spec.stdout)}
$stderr = {ps_quote(spec.stderr)}
$runnerLog = {ps_quote(spec.runner_log)}
{env_block}

$dirs = @(
    (Split-Path -Parent $stdout),
    (Split-Path -Parent $stderr),
    (Split-Path -Parent $runnerLog)
)
New-Item -ItemType Directory -Force -Path $dirs | Out-Null
Set-Location $work

$cmd = {powershell_array(spec.command)}
$program = $cmd[0]
$arguments = @()
if ($cmd.Count -gt 1) {{
    $arguments = $cmd[1..($cmd.Count - 1)]
}}

"START_TIME=$(Get-Date -Format o)" | Set-Content -Path $runnerLog -Encoding UTF8
"TASK=$taskName" | Add-Content -Path $runnerLog -Encoding UTF8
"WORK=$work" | Add-Content -Path $runnerLog -Encoding UTF8
"COMMAND=$($cmd -join ' ')" | Add-Content -Path $runnerLog -Encoding UTF8
"STDOUT=$stdout" | Add-Content -Path $runnerLog -Encoding UTF8
"STDERR=$stderr" | Add-Content -Path $runnerLog -Encoding UTF8
"START_TIME=$(Get-Date -Format o)" | Set-Content -Path $stdout -Encoding UTF8
"START_TIME=$(Get-Date -Format o)" | Set-Content -Path $stderr -Encoding UTF8

$commandInfo = $null
if (-not (Test-Path -LiteralPath $program -PathType Leaf)) {{
    $commandInfo = Get-Command $program -ErrorAction SilentlyContinue
}}
$programAvailable = (Test-Path -LiteralPath $program -PathType Leaf) -or ($null -ne $commandInfo)
$exit = 0
if (-not $programAvailable) {{
    $exit = 127
    "RUNNER_ERROR=Program not found: $program" | Add-Content -Path $runnerLog -Encoding UTF8
    "RUNNER_ERROR=Program not found: $program" | Add-Content -Path $stderr -Encoding UTF8
}} else {{
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {{
        & $program @arguments >> $stdout 2>> $stderr
        if ($null -eq $LASTEXITCODE) {{
            $exit = 0
        }} else {{
            $exit = [int]$LASTEXITCODE
        }}
    }} finally {{
        $ErrorActionPreference = $previousErrorActionPreference
    }}
}}

"END_TIME=$(Get-Date -Format o)" | Add-Content -Path $runnerLog -Encoding UTF8
"EXIT_CODE=$exit" | Add-Content -Path $runnerLog -Encoding UTF8
"END_TIME=$(Get-Date -Format o)" | Add-Content -Path $stdout -Encoding UTF8
"EXIT_CODE=$exit" | Add-Content -Path $stdout -Encoding UTF8
exit $exit
"""


def expand_uploads(config: dict[str, Any]) -> list[UploadSpec]:
    """Resolve ``uploads`` entries into local paths and remote destinations."""
    uploads = config.get("uploads") or []
    if not isinstance(uploads, list):
        raise RemoteJobError("uploads must be a list")
    context = _context(config)
    base_dir = Path(config.get(INTERNAL_CONFIG_DIR, "."))
    resolved = []
    for index, item in enumerate(uploads, start=1):
        if not isinstance(item, dict):
            raise RemoteJobError(f"uploads[{index}] must be an object")
        expanded = expand_value(item, context)
        local = expanded.get("local")
        remote = expanded.get("remote")
        if not local or not remote:
            raise RemoteJobError(f"uploads[{index}] needs local and remote paths")
        local_path = Path(str(local))
        if not local_path.is_absolute():
            local_path = (base_dir / local_path).resolve()
        resolved.append(
            UploadSpec(
                local_path=local_path,
                remote_path=normalize_remote_path(str(remote)),
            )
        )
    return resolved


def build_prepare_script(spec: JobSpec, uploads: list[UploadSpec]) -> str:
    """Build a remote script that creates all upload, runner, and log dirs."""
    dirs = {
        _parent_dir(spec.runner),
        _parent_dir(spec.stdout),
        _parent_dir(spec.stderr),
        _parent_dir(spec.runner_log),
    }
    dirs.update(_parent_dir(upload.remote_path) for upload in uploads)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$ProgressPreference = 'SilentlyContinue'",
        "$dirs = " + powershell_array(sorted(dirs)),
        "New-Item -ItemType Directory -Force -Path $dirs | Out-Null",
    ]
    return "\n".join(lines) + "\n"


def build_launch_script(spec: JobSpec) -> str:
    """Build the remote Task Scheduler create/run script for ``spec``."""
    disable_after_run = "$true" if spec.disable_after_run else "$false"
    verbose_remote_output = "$true" if spec.verbose_remote_output else "$false"
    task_run = powershell_file_command(spec.runner)
    limit_block = ""
    if spec.execution_time_limit:
        limit_block = f"""
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
$task.Settings.ExecutionTimeLimit = {ps_quote(spec.execution_time_limit)}
Set-ScheduledTask -TaskName $taskName -Settings $task.Settings | Out-Null
"""
    return f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskName = {ps_quote(spec.task_name)}
$runner = {ps_quote(spec.runner)}
$taskRun = {ps_quote(task_run)}
$disableAfterRun = {disable_after_run}
$verboseRemoteOutput = {verbose_remote_output}
if (-not (Test-Path -LiteralPath $runner)) {{
    throw "Runner was not uploaded: $runner"
}}
$createOutput = schtasks /Create /TN $taskName /SC ONCE /ST 23:59 /TR $taskRun /F 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{
    throw "schtasks create failed with exit $LASTEXITCODE`n$createOutput"
}}
{limit_block}$runOutput = schtasks /Run /TN $taskName 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{
    throw "schtasks run failed with exit $LASTEXITCODE`n$runOutput"
}}
Start-Sleep -Seconds 3
if ($disableAfterRun) {{
    $disableOutput = schtasks /Change /TN $taskName /DISABLE 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {{
        throw "schtasks disable failed with exit $LASTEXITCODE`n$disableOutput"
    }}
}} else {{
    $disableOutput = ""
}}
$queryOutput = schtasks /Query /TN $taskName /V /FO LIST 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{
    throw "schtasks query failed with exit $LASTEXITCODE`n$queryOutput"
}}
if ($verboseRemoteOutput) {{
    "REMOTE_SCHTASKS_CREATE_OUTPUT"
    $createOutput
    "REMOTE_SCHTASKS_RUN_OUTPUT"
    $runOutput
    if ($disableAfterRun) {{
        "REMOTE_SCHTASKS_DISABLE_OUTPUT"
        $disableOutput
    }}
    "REMOTE_SCHTASKS_QUERY_OUTPUT"
    $queryOutput
}}
"""


def _print_result(result: subprocess.CompletedProcess) -> None:
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )


def launch_config(config: dict[str, Any], *, dry_run: bool = False) -> int:
    """Upload configured files, upload the generated runner, and start a task."""
    spec = build_job_spec(config)
    uploads = expand_uploads(config)
    prepare_script = build_prepare_script(spec, uploads)
    runner_content = build_runner_content(spec)
    launch_script = build_launch_script(spec)

    if dry_run:
        print("REMOTE_JOB_DRY_RUN")
        print("---REMOTE-PREPARE---")
        print(prepare_script, end="")
        print("---UPLOADS---")
        for upload in uploads:
            print(f"{upload.local_path} -> {upload.remote_path}")
        print("---REMOTE-RUNNER---")
        print(runner_content, end="")
        print("---REMOTE-LAUNCH---")
        print(launch_script, end="")
        return 0

    args = connection_args(config)
    prepare_result = run_remote_powershell(args, prepare_script, timeout=args.ssh_timeout)
    _print_result(prepare_result)
    if prepare_result.returncode != 0:
        return prepare_result.returncode

    for upload in uploads:
        if not upload.local_path.exists():
            raise RemoteJobError(f"Upload source does not exist: {upload.local_path}")
        scp_result = run_scp(args, upload.local_path, upload.remote_path)
        _print_result(scp_result)
        if scp_result.returncode != 0:
            return scp_result.returncode

    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as f:
        temp_path = Path(f.name)
        f.write(runner_content)
    try:
        runner_upload = run_scp(args, temp_path, spec.runner)
    finally:
        temp_path.unlink(missing_ok=True)
    _print_result(runner_upload)
    if runner_upload.returncode != 0:
        return runner_upload.returncode

    launch_result = run_remote_powershell(args, launch_script, timeout=args.ssh_timeout)
    _print_result(launch_result)
    if launch_result.returncode != 0:
        return launch_result.returncode

    print("REMOTE_JOB_LAUNCH")
    print(f"task_name={spec.task_name}")
    print(f"runner={spec.runner}")
    print(f"runner_log={spec.runner_log}")
    print(f"stdout={spec.stdout}")
    print(f"stderr={spec.stderr}")
    return 0


def _logs_from_config(logs: Any) -> list[str]:
    if not logs:
        return []
    if isinstance(logs, dict):
        return [f"{name}={path}" for name, path in logs.items()]
    result = []
    for item in logs:
        if isinstance(item, dict):
            result.append(f"{item.get('name', 'log')}={item['path']}")
        else:
            result.append(str(item))
    return result


def monitor_args(config: dict[str, Any]) -> argparse.Namespace:
    """Build monitor arguments from config with job-log defaults."""
    profile = profile_config(config)
    job_spec = build_job_spec(config) if config.get("job") else None
    monitor_cfg = expand_value(dict(config.get("monitor") or {}), _context(config))
    logs = _logs_from_config(monitor_cfg.get("logs") or monitor_cfg.get("log"))
    if not logs and job_spec:
        logs = [
            f"runner={job_spec.runner_log}",
            f"stdout={job_spec.stdout}",
            f"stderr={job_spec.stderr}",
        ]
    task_name = monitor_cfg.get("task_name") or (job_spec.task_name if job_spec else None)
    return argparse.Namespace(
        host=profile["host"],
        user=profile["user"],
        key=profile["key"],
        connect_timeout=profile["connect_timeout"],
        ssh_timeout=int(monitor_cfg.get("ssh_timeout", profile["ssh_timeout"])),
        task_name=task_name,
        pid=monitor_cfg.get("pid"),
        process_match=monitor_cfg.get("process_match"),
        metadata=monitor_cfg.get("metadata"),
        csv=monitor_cfg.get("csv"),
        log=logs,
        tail=int(monitor_cfg.get("tail", 20)),
    )


def monitor_config(
    config: dict[str, Any],
    *,
    json_output: bool = False,
    watch: bool | None = None,
    poll_seconds: int | None = None,
) -> int:
    """Query or watch a remote job using the shared monitor implementation."""
    monitor_cfg = config.get("monitor") or {}
    should_watch = bool(monitor_cfg.get("watch", False)) if watch is None else watch
    seconds = int(poll_seconds or monitor_cfg.get("poll_seconds", 60))
    keep_terminal = bool(monitor_cfg.get("keep_watching_terminal", False))
    args = monitor_args(config)
    while True:
        snapshot = monitor.query_job(args)
        if json_output:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        else:
            print(monitor.summarize(snapshot), flush=True)
        if not should_watch:
            return 0
        if not keep_terminal and snapshot.get("state") != "running":
            return 0
        time.sleep(max(seconds, 1))


def parse_exit_code(text: str | list[str] | None) -> int | None:
    """Parse the latest ``EXIT_CODE=<int>`` value from runner-log content."""
    if text is None:
        return None
    lines = text if isinstance(text, list) else str(text).splitlines()
    for line in reversed(lines):
        match = re.match(r"\s*EXIT_CODE\s*=\s*(-?\d+)\s*$", str(line))
        if match:
            return int(match.group(1))
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def evaluate_condition(
    config: dict[str, Any],
    condition: dict[str, Any],
    *,
    previous: JobSpec | None = None,
) -> ConditionResult:
    """Evaluate one queue wait condition against the remote host."""
    condition = expand_value(condition, _context(config))
    kind = str(condition.get("type") or "runner_success")
    args = connection_args(config)

    if kind in {"file", "file_exists"}:
        path = normalize_remote_path(str(condition["path"]))
        info = monitor.query_file_info(args, path)
        min_bytes = int(condition.get("min_bytes", 0))
        ok = bool(info.get("exists")) and int(info.get("length") or 0) >= min_bytes
        detail = f"file_exists {path} bytes={info.get('length')}"
        return ConditionResult(ok, False, detail)

    if kind in {"pid_exit", "pid_exited"}:
        pid = condition.get("pid")
        if pid is None:
            pid = (config.get("monitor") or {}).get("pid")
        if pid is None:
            raise RemoteJobError("pid_exit condition needs a pid")
        pid_args = argparse.Namespace(**vars(args), pid=int(pid))
        alive = monitor.query_pid_process(pid_args)
        return ConditionResult(alive is None, False, f"pid_exit {pid}")

    if kind in {"process_exit", "process_exited"}:
        process_match = condition.get("process_match")
        if process_match is None:
            process_match = (config.get("monitor") or {}).get("process_match")
        if not process_match:
            raise RemoteJobError("process_exit condition needs process_match")
        proc_args = argparse.Namespace(**vars(args), process_match=process_match)
        processes = monitor.query_processes(proc_args)
        return ConditionResult(not processes, False, f"process_exit {process_match}")

    if kind == "task_success":
        task_name = condition.get("task_name")
        if task_name is None:
            task_name = build_job_spec(config).task_name
        task_args = argparse.Namespace(**vars(args), task_name=task_name)
        task = monitor.query_task(task_args) or {}
        if task.get("exists") is False:
            return ConditionResult(False, True, f"task_success {task_name} missing")
        last_result = _int_or_none(task.get("last_task_result"))
        state = str(task.get("state", "")).lower()
        if state == "running" or last_result is None or last_result == RUNNING_TASK_RESULT:
            return ConditionResult(False, False, f"task_success {task_name} pending")
        ok = int(last_result or 1) == 0
        return ConditionResult(ok, not ok, f"task_success {task_name} result={last_result}")

    if kind in {"runner_success", "job_success", "previous_success"}:
        path = condition.get("path")
        if path is None and kind == "previous_success" and previous:
            path = previous.runner_log
        if path is None:
            path = build_job_spec(config).runner_log
        lines = monitor.query_text_tail(args, normalize_remote_path(str(path)), 40)
        exit_code = parse_exit_code(lines)
        if exit_code is None:
            return ConditionResult(False, False, f"runner_success {path} pending")
        ok = exit_code == 0
        return ConditionResult(ok, not ok, f"runner_success {path} exit={exit_code}")

    raise RemoteJobError(f"Unknown queue condition type: {kind}")


def wait_for_conditions(
    config: dict[str, Any],
    conditions: list[dict[str, Any]],
    *,
    poll_seconds: int,
    previous: JobSpec | None = None,
    label: str = "wait",
) -> bool:
    """Poll until every condition is satisfied or one condition fails."""
    while True:
        results = [
            evaluate_condition(config, condition, previous=previous)
            for condition in conditions
        ]
        summary = "; ".join(result.message for result in results)
        print(f"{label}: {summary}", flush=True)
        if any(result.failed for result in results):
            return False
        if all(result.satisfied for result in results):
            return True
        time.sleep(max(int(poll_seconds), 1))


def wait_for_launched_job(config: dict[str, Any], *, poll_seconds: int) -> bool:
    """Wait for a launched job to finish successfully by runner log or task."""
    spec = build_job_spec(config)
    args = connection_args(config)
    runner_condition = {"type": "runner_success", "path": spec.runner_log}
    while True:
        runner = evaluate_condition(config, runner_condition)
        if runner.satisfied:
            print(f"{spec.task_name}: {runner.message}", flush=True)
            return True
        if runner.failed:
            print(f"{spec.task_name}: {runner.message}", flush=True)
            return False

        task_args = argparse.Namespace(**vars(args), task_name=spec.task_name)
        task = monitor.query_task(task_args) or {}
        state = str(task.get("state", "")).lower()
        last_result = _int_or_none(task.get("last_task_result"))
        if state != "running" and last_result not in (None, RUNNING_TASK_RESULT):
            ok = int(last_result) == 0
            print(f"{spec.task_name}: task_result={last_result}", flush=True)
            return ok

        print(f"{spec.task_name}: running or waiting for runner log", flush=True)
        time.sleep(max(int(poll_seconds), 1))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge queue job overrides without mutating the base config."""
    merged = dict(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def queue_item_config(base_config: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Resolve one queue item against root-level profile and upload defaults."""
    config = {
        INTERNAL_CONFIG_DIR: base_config.get(INTERNAL_CONFIG_DIR, "."),
        "profile": base_config.get("profile", {}),
        "uploads": base_config.get("uploads", []),
    }
    for key in ("run_id", "owner", "job", "monitor"):
        if key in base_config:
            config[key] = base_config[key]
    merged = deep_merge(config, item)
    if "uploads" in item and base_config.get("uploads"):
        merged["uploads"] = list(base_config.get("uploads") or []) + list(item.get("uploads") or [])
    return merged


def queue_config(config: dict[str, Any], *, dry_run: bool = False) -> int:
    """Run a sequential conditional queue from the ``queue.jobs`` config list."""
    queue = config.get("queue") or {}
    jobs = queue.get("jobs") or []
    if not isinstance(jobs, list) or not jobs:
        raise RemoteJobError("queue.jobs must be a non-empty list")
    poll_seconds = int(queue.get("poll_seconds", 60))
    stop_on_failure = bool(queue.get("stop_on_failure", True))
    previous_spec: JobSpec | None = None

    for index, item in enumerate(jobs, start=1):
        if not isinstance(item, dict):
            raise RemoteJobError(f"queue.jobs[{index}] must be an object")
        job_config = queue_item_config(config, item)
        spec = build_job_spec(job_config)
        label = str(item.get("label") or spec.task_name)
        conditions = item.get("wait_for")
        if isinstance(conditions, dict):
            conditions = [conditions]
        if conditions is None and previous_spec is not None:
            conditions = [{"type": "previous_success", "path": previous_spec.runner_log}]
        if dry_run:
            print(f"QUEUE_JOB {index}: {label} task={spec.task_name}")
            if conditions:
                print(f"  wait_for={json.dumps(conditions, ensure_ascii=False)}")
            print(f"  runner={spec.runner}")
            previous_spec = spec
            continue

        if conditions:
            if not wait_for_conditions(
                job_config,
                list(conditions),
                poll_seconds=poll_seconds,
                previous=previous_spec,
                label=f"{label} wait",
            ):
                print(f"Queue stopped before {label}: wait condition failed")
                return 2 if stop_on_failure else 0

        launch_code = launch_config(job_config)
        if launch_code != 0:
            print(f"Queue launch failed for {label}: exit={launch_code}")
            return launch_code if stop_on_failure else 0
        if not wait_for_launched_job(job_config, poll_seconds=poll_seconds):
            print(f"Queue job failed: {label}")
            return 4 if stop_on_failure else 0
        previous_spec = spec
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for ``python -m ALB.infrastructure.remote.job``."""
    parser = argparse.ArgumentParser(description="Generic ALB remote job toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch = subparsers.add_parser("launch", help="Upload and start one job")
    launch.add_argument("--config", required=True)
    launch.add_argument("--dry-run", action="store_true")

    monitor_parser = subparsers.add_parser("monitor", help="Monitor one job")
    monitor_parser.add_argument("--config", required=True)
    monitor_parser.add_argument("--json", action="store_true")
    monitor_parser.add_argument("--watch", action="store_true")
    monitor_parser.add_argument("--poll-seconds", type=int, default=None)

    queue_parser = subparsers.add_parser("queue", help="Run a conditional queue")
    queue_parser.add_argument("--config", required=True)
    queue_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for generic remote launch, monitor, and queue actions."""
    configure_stdio()
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "launch":
            return launch_config(config, dry_run=args.dry_run)
        if args.command == "monitor":
            return monitor_config(
                config,
                json_output=args.json,
                watch=args.watch or None,
                poll_seconds=args.poll_seconds,
            )
        if args.command == "queue":
            return queue_config(config, dry_run=args.dry_run)
    except RemoteJobError as exc:
        print(f"REMOTE_JOB_ERROR: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
