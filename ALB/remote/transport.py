# coding: utf-8
"""Shared SSH, SCP, and PowerShell helpers for remote ALB tools."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_POWERSHELL_EXE = os.environ.get("ALB_POWERSHELL_EXE", "pwsh")
DEFAULT_POWERSHELL_TASK_EXE = os.environ.get(
    "ALB_POWERSHELL_TASK_EXE",
    r"C:\Program Files\PowerShell\7\pwsh.exe",
)


@dataclass(frozen=True)
class RemoteConnection:
    host: str
    user: str
    key: str
    connect_timeout: int = 10

    @classmethod
    def from_args(cls, args: Any) -> "RemoteConnection":
        if isinstance(args, cls):
            return args
        return cls(
            host=args.host,
            user=args.user,
            key=args.key,
            connect_timeout=int(getattr(args, "connect_timeout", 10)),
        )

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def remote_path(*parts: str) -> str:
    path = parts[0].rstrip("/\\")
    for part in parts[1:]:
        path += "/" + part.strip("/\\")
    return path


def encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def quote_executable(executable: str) -> str:
    """Quote a command executable when Windows command parsing requires it."""
    if not executable:
        return executable
    if executable[0] in ("'", '"'):
        return executable
    if any(char.isspace() for char in executable):
        return f'"{executable}"'
    return executable


def powershell_encoded_command(
    encoded_script: str,
    *,
    executable: str = DEFAULT_POWERSHELL_EXE,
) -> str:
    """Return the remote command line for an encoded PowerShell script."""
    return f"{quote_executable(executable)} -NoLogo -NoProfile -EncodedCommand {encoded_script}"


def powershell_file_command(
    script_path: str,
    *,
    executable: str = DEFAULT_POWERSHELL_TASK_EXE,
) -> str:
    """Return the Task Scheduler command line for a PowerShell runner file."""
    return (
        f'{quote_executable(executable)} -NoLogo -NoProfile -ExecutionPolicy Bypass '
        f'-File "{script_path}"'
    )


def run_remote_powershell(
    connection: RemoteConnection | Any,
    script: str,
    *,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    remote = RemoteConnection.from_args(connection)
    encoded = encode_powershell(script)
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={remote.connect_timeout}",
        "-i",
        remote.key,
        remote.target,
        powershell_encoded_command(encoded),
    ]
    try:
        return subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        if timeout is None:
            raise
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nremote command timed out after {timeout}s"
        return subprocess.CompletedProcess(cmd, 124, stdout=stdout, stderr=stderr)


def run_scp(
    connection: RemoteConnection | Any,
    local_path: Path,
    remote_path_value: str,
) -> subprocess.CompletedProcess:
    remote = RemoteConnection.from_args(connection)
    target = f"{remote.target}:{remote_path_value}"
    cmd = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={remote.connect_timeout}",
        "-i",
        remote.key,
        str(local_path),
        target,
    ]
    return subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        capture_output=True,
    )
