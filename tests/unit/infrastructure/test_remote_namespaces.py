"""Unit tests for the split generic and ALBNN remote namespaces."""

from __future__ import annotations

import argparse

from ALB.infrastructure.remote import job, monitor
from ALB.infrastructure.remote.transport import (
    RemoteConnection,
    encode_powershell,
    powershell_encoded_command,
    powershell_file_command,
    ps_quote,
    quote_executable,
    remote_path,
)
from ALB.surrogate.training.remote import queue, start, status


def test_transport_helpers_preserve_commands() -> None:
    assert ps_quote("a'b") == "'a''b'"
    assert remote_path("F:/root/", "/child/", r"leaf\\") == "F:/root/child/leaf"
    assert encode_powershell("Get-Date") == "RwBlAHQALQBEAGEAdABlAA=="
    assert powershell_encoded_command("abc", executable="pwsh") == (
        "pwsh -NoLogo -NoProfile -EncodedCommand abc"
    )
    assert powershell_file_command("F:/root/run.ps1", executable="pwsh.exe") == (
        'pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "F:/root/run.ps1"'
    )
    assert quote_executable(r"C:\Program Files\PowerShell\7\pwsh.exe") == (
        r'"C:\Program Files\PowerShell\7\pwsh.exe"'
    )


def test_remote_connection_uses_injected_arguments() -> None:
    args = argparse.Namespace(
        host="10.0.0.1",
        user=r"host\user",
        key="C:/key",
    )
    connection = RemoteConnection.from_args(args)
    assert connection.target == r"host\user@10.0.0.1"
    assert connection.connect_timeout == 10


def test_remote_namespace_ownership_is_explicit() -> None:
    assert job.__name__ == "ALB.infrastructure.remote.job"
    assert monitor.__name__ == "ALB.infrastructure.remote.monitor"
    assert start.__name__ == "ALB.surrogate.training.remote.start"
    assert status.__name__ == "ALB.surrogate.training.remote.status"
    assert queue.__name__ == "ALB.surrogate.training.remote.queue"


def test_albnn_queue_launches_new_start_module() -> None:
    assert queue._start_command_prefix() == [
        __import__("sys").executable,
        "-m",
        "ALB.surrogate.training.remote.start",
    ]
