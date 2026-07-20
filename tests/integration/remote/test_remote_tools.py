# coding: utf-8

import contextlib
import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ALB.infrastructure.remote import job as remote_job
from ALB.infrastructure.remote import monitor
from ALB.infrastructure.remote.transport import RemoteConnection
from ALB.infrastructure.remote.transport import encode_powershell
from ALB.infrastructure.remote.transport import powershell_encoded_command
from ALB.infrastructure.remote.transport import powershell_file_command
from ALB.infrastructure.remote.transport import ps_quote
from ALB.infrastructure.remote.transport import quote_executable
from ALB.infrastructure.remote.transport import remote_path
from ALB.surrogate.training.remote import queue as albnn_queue
from ALB.surrogate.training.remote import start as albnn_start
from ALB.surrogate.training.remote import status as albnn_status


ROOT = Path(__file__).resolve().parents[3]
SURROGATE_ROOT = ROOT.parent / "SURROGATE_TRAIN"
REMOTE_DIR = SURROGATE_ROOT / "run" / "remote"
REFS = ROOT / "refs"


def load_ref(name):
    return json.loads((REFS / name).read_text(encoding="utf-8"))


def test_transport_helpers():
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
    assert powershell_file_command("F:/root/run.ps1") == (
        r'"C:\Program Files\PowerShell\7\pwsh.exe" '
        '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "F:/root/run.ps1"'
    )

    class Args:
        host = "10.0.0.1"
        user = r"host\user"
        key = "C:/key"

    connection = RemoteConnection.from_args(Args)
    assert connection.target == r"host\user@10.0.0.1"
    assert connection.connect_timeout == 10


@pytest.mark.skip(
    reason="read-only SURROGATE_TRAIN wrapper still imports the removed ALB 0.1 remote namespace"
)
def test_start_wrapper_dry_run_matches_reference():
    ref = load_ref("remote_albnn_start_dry_run_reference_v1.json")
    result = subprocess.run(
        [sys.executable, str(REMOTE_DIR / "remote_start_albnn_train.py"), "--dry-run"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert result.returncode == ref["returncode"]
    assert result.stdout == ref["stdout"]
    assert result.stderr == ref["stderr"]


def test_start_preflight_checks_training_data_files():
    # Guard against the 2026-05-11 failure mode: the launcher must fail before
    # scheduling a remote task when split CSVs are missing or empty.
    args = argparse.Namespace(allow_existing_model_dir=False)
    script = albnn_start.build_model_dir_check_script(
        args,
        {
            "model_dir": "F:/root/models/example",
            "train_data": "F:/root/data/train.csv",
            "validation_data": "F:/root/data/validation.csv",
        },
    )
    assert "$trainData = 'F:/root/data/train.csv'" in script
    assert "$validationData = 'F:/root/data/validation.csv'" in script
    assert "Training data file is missing: $dataPath" in script
    assert "Training data file is empty: $dataPath" in script


def test_status_summary_matches_reference():
    ref = load_ref("remote_albnn_status_summary_reference_v1.json")
    assert albnn_status.summarize(ref["input"]) == ref["summary"]
    assert albnn_status.latest_epoch(ref["input"]["stdout_tail"]) == (180, 30000, True)
    assert albnn_status.parse_iso("2026-05-09T12:30:00.1234567+08:00").isoformat() == (
        "2026-05-09T12:30:00.123456+08:00"
    )


def test_monitor_summary_matches_reference():
    ref = load_ref("remote_monitor_snapshot_reference_v1.json")
    assert monitor.summarize(ref["snapshot"]) == ref["summary"]

    progress = monitor.progress_from_metadata(
        {
            "target_valid_samples": 40000,
            "valid_samples": 2129,
            "attempted_samples": 2560,
            "elapsed_s": 1105.8947785999917,
        }
    )
    assert progress["remaining"] == 37871.0
    assert progress["valid_rate"] == 2129 / 2560
    assert monitor.state_from_snapshot(ref["snapshot"]) == "running"

    prepared_progress = monitor.progress_from_metadata(
        {
            "mode": "evaluate_prepared_inputs",
            "input_rows": 200000,
            "attempted_rows": 200000,
            "valid_samples": 198000,
            "invalid_samples": 2000,
            "elapsed_s": 1000.0,
        }
    )
    assert prepared_progress["completion_basis"] == "attempted"
    assert prepared_progress["target"] == 200000
    assert prepared_progress["remaining"] == 0.0
    assert monitor.state_from_snapshot({"progress": prepared_progress}) == "completed"


def generic_job_config(tmp_path):
    run_id = "S0001_remote_generic_test_1_20260517"
    return {
        remote_job.INTERNAL_CONFIG_DIR: str(tmp_path),
        "run_id": run_id,
        "owner": "SURROGATE_TRAIN",
        "profile": {
            "host": "10.0.0.1",
            "user": r"host\user",
            "key": "C:/key",
            "work": "F:/work",
            "root": "F:/work/outputs",
            "remote_python": "F:/env/python.exe",
        },
        "uploads": [
            {
                "local": "script.py",
                "remote": "${work}/run/script.py",
            }
        ],
        "job": {
            "task_name": "ALB_GenericTest",
            "runner": "${work}/run_generic_test.ps1",
            "command": ["${remote_python}", "-u", "run/script.py", "--flag"],
            "env": {"PYTHONUNBUFFERED": "1"},
            "stdout": "${root}/reports/logs/generic.stdout.log",
            "stderr": "${root}/reports/logs/generic.stderr.log",
            "runner_log": "${root}/reports/logs/generic.runner.log",
            "execution_time_limit": "PT2H",
        },
    }


def test_generic_job_config_builds_stable_runner(tmp_path):
    config = generic_job_config(tmp_path)
    spec = remote_job.build_job_spec(config)
    assert spec.task_name == "ALB_GenericTest"
    assert spec.command == ["F:/env/python.exe", "-u", "run/script.py", "--flag"]
    assert spec.runner == "F:/work/run_generic_test.ps1"

    runner = remote_job.build_runner_content(spec)
    assert "START_TIME=$(Get-Date -Format o)" in runner
    assert '"TASK=$taskName"' in runner
    assert '"COMMAND=$($cmd -join \' \')"' in runner
    assert '"STDOUT=$stdout"' in runner
    assert '"STDERR=$stderr"' in runner
    assert '"EXIT_CODE=$exit"' in runner
    assert "Program not found: $program" in runner
    assert "$exit = 127" in runner
    assert ">> $stdout 2>> $stderr" in runner


def test_generic_job_launch_uploads_before_scheduling(monkeypatch, tmp_path):
    (tmp_path / "script.py").write_text("print('hello')\n", encoding="utf-8")
    config = generic_job_config(tmp_path)
    calls = []

    def fake_remote(args, script, timeout=None):
        calls.append(("remote", script))
        return subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr="")

    def fake_scp(args, local_path, remote_path_value):
        calls.append(("scp", str(local_path), remote_path_value))
        return subprocess.CompletedProcess(["scp"], 0, stdout="", stderr="")

    monkeypatch.setattr(remote_job, "run_remote_powershell", fake_remote)
    monkeypatch.setattr(remote_job, "run_scp", fake_scp)

    assert remote_job.launch_config(config) == 0
    assert [call[0] for call in calls] == ["remote", "scp", "scp", "remote"]
    assert calls[1][2] == "F:/work/run/script.py"
    assert calls[2][2] == "F:/work/run_generic_test.ps1"
    assert "New-Item -ItemType Directory" in calls[0][1]
    assert "schtasks /Create" in calls[3][1]
    assert "schtasks /Run" in calls[3][1]


def test_generic_job_cli_launch_dry_run_and_monitor_json(monkeypatch, tmp_path, capsys):
    (tmp_path / "script.py").write_text("print('hello')\n", encoding="utf-8")
    config = generic_job_config(tmp_path)
    config_path = tmp_path / "generic_job.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert remote_job.main(["launch", "--config", str(config_path), "--dry-run"]) == 0
    launch_out = capsys.readouterr().out
    assert "REMOTE_JOB_DRY_RUN" in launch_out
    assert "---REMOTE-RUNNER---" in launch_out

    monkeypatch.setattr(
        remote_job.monitor,
        "query_job",
        lambda args: {"remote_time": "2026-05-12T00:00:00+08:00", "state": "not_running"},
    )
    assert remote_job.main(["monitor", "--config", str(config_path), "--json"]) == 0
    monitor_out = capsys.readouterr().out
    assert '"state": "not_running"' in monitor_out


def test_generic_job_cli_launch_dry_run_uses_config_only(tmp_path, capsys):
    (tmp_path / "script.py").write_text("print('hello')\n", encoding="utf-8")
    config = generic_job_config(tmp_path)
    config_path = tmp_path / "generic_job.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert remote_job.main(["launch", "--config", str(config_path), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "REMOTE_JOB_DRY_RUN" in output


def test_generic_queue_dry_run_inherits_run_id(tmp_path, capsys):
    config = generic_job_config(tmp_path)
    config["queue"] = {"jobs": [{"label": "registered_generic"}]}

    assert remote_job.queue_config(config, dry_run=True) == 0
    output = capsys.readouterr().out
    assert "QUEUE_JOB 1: registered_generic task=ALB_GenericTest" in output


def test_generic_queue_conditions(monkeypatch, tmp_path):
    config = generic_job_config(tmp_path)

    def fake_file_info(args, path):
        return {"exists": True, "path": path, "length": 12}

    def fake_pid_process(args):
        return None

    def fake_processes(args):
        return []

    def fake_tail(args, path, tail):
        return ["START_TIME=2026-05-12T00:00:00+08:00", "EXIT_CODE=0"]

    monkeypatch.setattr(remote_job.monitor, "query_file_info", fake_file_info)
    monkeypatch.setattr(remote_job.monitor, "query_pid_process", fake_pid_process)
    monkeypatch.setattr(remote_job.monitor, "query_processes", fake_processes)
    monkeypatch.setattr(remote_job.monitor, "query_text_tail", fake_tail)

    assert remote_job.evaluate_condition(
        config, {"type": "file_exists", "path": "${root}/done.txt", "min_bytes": 1}
    ).satisfied
    assert remote_job.evaluate_condition(config, {"type": "pid_exit", "pid": 1234}).satisfied
    assert remote_job.evaluate_condition(
        config, {"type": "process_exit", "process_match": "run/script.py"}
    ).satisfied
    assert remote_job.evaluate_condition(config, {"type": "runner_success"}).satisfied

    monkeypatch.setattr(
        remote_job.monitor,
        "query_text_tail",
        lambda args, path, tail: ["EXIT_CODE=7"],
    )
    failed = remote_job.evaluate_condition(config, {"type": "runner_success"})
    assert failed.failed
    assert not failed.satisfied


def test_status_query_uses_monitor_helpers(monkeypatch):
    calls = []

    args = argparse.Namespace(
        root="F:/root",
        task_name="ALB_TrainExample",
        model_name="example_model",
        tail=3,
        ssh_timeout=5,
    )

    def fake_query_remote_time(args):
        calls.append(("remote_time", args.task_name))
        return "2026-05-10T12:00:00+08:00"

    def fake_query_task(args):
        calls.append(("task", args.task_name))
        return {"exists": True, "name": args.task_name, "state": "Running"}

    def fake_query_processes(args):
        calls.append(("processes", args.process_match))
        return [{"ProcessId": 1234}]

    def fake_query_text_tail(args, path, tail):
        calls.append(("tail", path, tail))
        if path.endswith(".log") and ".stdout." not in path and ".stderr." not in path:
            return ["START_TIME=2026-05-10T11:00:00+08:00"]
        if ".stdout." in path:
            return ["epoch 7/50: train=1.0e-3, test=2.0e-3"]
        return ["warning"]

    def fake_query_file_text(args, path):
        calls.append(("file_text", path))
        if path.endswith("validation_summary.json"):
            return '{"n": 10, "r2_fx": 0.9, "r2_fy": 0.8}'
        if path.endswith("metadata.json"):
            return '{"scaler": "minmax"}'
        return ""

    def fake_query_directory_files(args, path):
        calls.append(("files", path))
        return [{"Name": "metadata.json"}]

    monkeypatch.setattr(albnn_status.monitor, "query_remote_time", fake_query_remote_time)
    monkeypatch.setattr(albnn_status.monitor, "query_task", fake_query_task)
    monkeypatch.setattr(albnn_status.monitor, "query_processes", fake_query_processes)
    monkeypatch.setattr(albnn_status.monitor, "query_text_tail", fake_query_text_tail)
    monkeypatch.setattr(albnn_status.monitor, "query_file_text", fake_query_file_text)
    monkeypatch.setattr(albnn_status.monitor, "query_directory_files", fake_query_directory_files)

    data = albnn_status.query_remote(args)
    assert data["remote_time"] == "2026-05-10T12:00:00+08:00"
    assert data["task"] == {"exists": True, "name": "ALB_TrainExample", "state": "Running"}
    assert data["processes"] == [{"ProcessId": 1234}]
    assert data["run_log_tail"] == ["START_TIME=2026-05-10T11:00:00+08:00"]
    assert data["stdout_tail"] == ["epoch 7/50: train=1.0e-3, test=2.0e-3"]
    assert data["stderr_tail"] == ["warning"]
    assert data["validation_summary_text"] == '{"n": 10, "r2_fx": 0.9, "r2_fy": 0.8}'
    assert data["metadata_text"] == '{"scaler": "minmax"}'
    assert ("processes", "example_model") in calls


def test_queue_config_and_launch_command_match_reference(monkeypatch):
    ref = load_ref("remote_albnn_queue_config_reference_v1.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [str(REMOTE_DIR / "remote_queue_albnn_activation_sweep.py")],
    )

    args = albnn_queue.build_parser().parse_args(
        ["--config", ref["config_path"], "--dry-run"]
    )
    config = albnn_queue.load_config(args.config)
    albnn_queue.apply_config_defaults(args, config)
    combos = albnn_queue.build_config_combos(args, config)

    actual = []
    for combo in combos:
        actual.append(
            {
                "key": combo.key,
                "task_name": combo.task_name,
                "runner": combo.runner,
                "model_name": combo.model_name,
                "architecture": combo.architecture,
                "activation": combo.activation.__dict__,
                "transform": combo.transform.__dict__,
                "launch_command": albnn_queue.launch_command(
                    args, combo, allow_existing=False
                ),
            }
        )
    assert actual == ref["combos"]

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        albnn_queue.print_queue(args, combos, [])
    assert out.getvalue() == ref["print_queue_output"]


@pytest.mark.skip(
    reason="read-only SURROGATE_TRAIN wrappers require the 0.2 import-map migration"
)
def test_compat_wrappers_help():
    wrappers = [
        "remote_start_albnn_train.py",
        "remote_query_albnn_status.py",
        "remote_queue_albnn_activation_sweep.py",
        "remote_monitor_job.py",
        "remote_job.py",
    ]
    for wrapper in wrappers:
        result = subprocess.run(
            [sys.executable, str(REMOTE_DIR / wrapper), "--help"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout
