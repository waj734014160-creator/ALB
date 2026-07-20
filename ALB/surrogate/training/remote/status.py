# coding: utf-8
"""Query ALBNN remote training jobs started through Task Scheduler."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from ALB.infrastructure.remote import monitor
from ALB.infrastructure.remote.common import extract_json
from ALB.infrastructure.remote.common import parse_iso
from ALB.infrastructure.remote.defaults import DEFAULT_HOST
from ALB.infrastructure.remote.defaults import DEFAULT_KEY
from ALB.infrastructure.remote.defaults import DEFAULT_MODEL
from ALB.infrastructure.remote.defaults import DEFAULT_ROOT
from ALB.infrastructure.remote.defaults import DEFAULT_TASK
from ALB.infrastructure.remote.defaults import DEFAULT_USER
from ALB.infrastructure.remote.transport import configure_stdio
from ALB.infrastructure.remote.transport import remote_path
from ALB.infrastructure.remote.transport import run_remote_powershell


def remote_stdout(args: argparse.Namespace, script: str, *, required: bool = False) -> str:
    result = run_remote_powershell(args, script, timeout=args.ssh_timeout)
    if result.returncode != 0 and required:
        raise RuntimeError(
            f"Remote command failed with exit {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout or ""


def parse_json_text(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_key_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def latest_epoch(stdout_lines: list[str]) -> tuple[int | None, int | None, bool]:
    latest = None
    total = None
    early_stop = False
    for line in stdout_lines:
        match = re.search(r"epoch\s+(\d+)/(\d+)", line)
        if match:
            latest = int(match.group(1))
            total = int(match.group(2))
        if "early stop at epoch" in line:
            early_stop = True
            match = re.search(r"early stop at epoch\s+(\d+)", line)
            if match:
                latest = int(match.group(1))
    return latest, total, early_stop


def parse_json_output(text: str) -> Any:
    try:
        return extract_json(text)
    except Exception:
        return None


def split_lines(text: str) -> list[str]:
    return [
        line.rstrip("\r")
        for line in text.splitlines()
        if not line.startswith("#< CLIXML")
    ]


def query_remote(args: argparse.Namespace) -> dict[str, Any]:
    model_dir = remote_path(args.root, "models", args.model_name)
    log_dir = remote_path(args.root, "reports", "logs")
    run_log = remote_path(log_dir, f"train_{args.model_name}.log")
    stdout = remote_path(log_dir, f"train_{args.model_name}.stdout.log")
    stderr = remote_path(log_dir, f"train_{args.model_name}.stderr.log")
    summary = remote_path(model_dir, "validation_summary.json")
    metadata = remote_path(model_dir, "metadata.json")

    process_args = argparse.Namespace(**vars(args), process_match=args.model_name)
    task_snapshot = monitor.query_task(args)
    summary_text = monitor.query_file_text(args, summary).strip()
    metadata_text = monitor.query_file_text(args, metadata).strip()

    return {
        "remote_time": monitor.query_remote_time(args),
        "task_name": args.task_name,
        "model_name": args.model_name,
        "model_dir": model_dir,
        "task_text": json.dumps(task_snapshot, ensure_ascii=False),
        "task": task_snapshot,
        "processes": monitor.query_processes(process_args),
        "run_log_path": run_log,
        "stdout_path": stdout,
        "stderr_path": stderr,
        "run_log_tail": monitor.query_text_tail(args, run_log, int(args.tail)),
        "stdout_tail": monitor.query_text_tail(args, stdout, int(args.tail)),
        "stderr_tail": monitor.query_text_tail(args, stderr, int(args.tail)),
        "validation_summary_text": summary_text or None,
        "metadata_text": metadata_text or None,
        "model_files": monitor.query_directory_files(args, model_dir),
    }


def summarize(data: dict[str, Any]) -> str:
    run_log_tail = data.get("run_log_tail") or []
    stdout_tail = data.get("stdout_tail") or []
    stderr_tail = data.get("stderr_tail") or []
    kv = parse_key_values(run_log_tail)
    summary = parse_json_text(data.get("validation_summary_text"))
    metadata = parse_json_text(data.get("metadata_text"))

    start_time = parse_iso(kv.get("START_TIME"))
    end_time = parse_iso(kv.get("END_TIME"))
    remote_time = parse_iso(data.get("remote_time"))
    stop_time = end_time or remote_time
    elapsed_min = None
    if start_time and stop_time:
        elapsed_min = max((stop_time - start_time).total_seconds() / 60.0, 0.0)

    latest, total, early_stop = latest_epoch(stdout_tail)
    processes = data.get("processes") or []
    if isinstance(processes, dict):
        processes = [processes]
    exit_code = kv.get("EXIT_CODE")
    if summary and exit_code == "0":
        state = "completed"
    elif processes:
        state = "running"
    elif exit_code is not None:
        state = f"exited({exit_code})"
    else:
        state = "not running or not started"

    lines = [
        f"task: {data.get('task_name')}",
        f"model: {data.get('model_name')}",
        f"state: {state}",
        f"model_dir: {data.get('model_dir')}",
    ]
    if elapsed_min is not None:
        lines.append(f"elapsed_min: {elapsed_min:.1f}")
    if latest is not None:
        suffix = f"/{total}" if total is not None else ""
        lines.append(f"latest_epoch: {latest}{suffix}")
        if elapsed_min and elapsed_min > 0:
            lines.append(f"avg_epoch_per_min: {latest / elapsed_min:.2f}")
    if early_stop:
        lines.append("early_stop: true")
    if processes:
        pid_list = ", ".join(str(item.get("ProcessId")) for item in processes)
        lines.append(f"python_pids: {pid_list}")
    if metadata:
        lines.append(f"scaler: {metadata.get('scaler')}")
        activation = metadata.get("activation") or {}
        if activation:
            name = activation.get("name")
            omega = activation.get("sine_omega0")
            suffix = f"(omega0={omega})" if omega is not None else ""
            lines.append(f"activation: {name}{suffix}")
        target_transform = metadata.get("target_transform") or {}
        transform_name = target_transform.get("name")
        transform_scale = target_transform.get("scale")
        transform_suffix = (
            f"(scale={transform_scale})"
            if transform_scale is not None and transform_name != "none"
            else ""
        )
        lines.append(f"target_transform: {transform_name}{transform_suffix}")
    if summary:
        lines.extend(
            [
                f"validation_n: {summary.get('n')}",
                f"validation_r2_fx: {summary.get('r2_fx'):.6f}",
                f"validation_r2_fy: {summary.get('r2_fy'):.6f}",
                f"validation_mae_fx: {summary.get('mae_fx'):.6f}",
                f"validation_mae_fy: {summary.get('mae_fy'):.6f}",
                f"validation_rmse_fx: {summary.get('rmse_fx'):.6f}",
                f"validation_rmse_fy: {summary.get('rmse_fy'):.6f}",
                f"median_relative_norm_error: {summary.get('median_relative_norm_error'):.6f}",
            ]
        )
    if stderr_tail:
        last_stderr = [line for line in stderr_tail if str(line).strip()]
        if last_stderr:
            lines.append("stderr_tail:")
            lines.extend(f"  {line}" for line in last_stderr[-8:])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query remote ALBNN training status")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--task_name", default=DEFAULT_TASK)
    parser.add_argument("--model_name", default=DEFAULT_MODEL)
    parser.add_argument("--tail", type=int, default=120)
    parser.add_argument("--ssh-timeout", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="Print raw parsed JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = build_parser().parse_args(argv)
    data = query_remote(args)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(summarize(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
