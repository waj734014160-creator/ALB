# coding: utf-8
"""Shared SSH, SCP, and PowerShell helpers for remote ALB tools."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any


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
        f"powershell -NoProfile -EncodedCommand {encoded}",
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

