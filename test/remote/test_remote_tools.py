# coding: utf-8

import contextlib
import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

from ALB.remote import albnn_start
from ALB.remote import albnn_queue
from ALB.remote import albnn_status
from ALB.remote import monitor
from ALB.remote.transport import RemoteConnection
from ALB.remote.transport import encode_powershell
from ALB.remote.transport import ps_quote
from ALB.remote.transport import remote_path


ROOT = Path(__file__).resolve().parents[2]
SURROGATE_ROOT = ROOT.parent / "SURROGATE_TRAIN"
REMOTE_DIR = SURROGATE_ROOT / "run" / "remote"
REFS = ROOT / "refs"


def load_ref(name):
    return json.loads((REFS / name).read_text(encoding="utf-8"))


def test_transport_helpers():
    assert ps_quote("a'b") == "'a''b'"
    assert remote_path("F:/root/", "/child/", r"leaf\\") == "F:/root/child/leaf"
    assert encode_powershell("Get-Date") == "RwBlAHQALQBEAGEAdABlAA=="

    class Args:
        host = "10.0.0.1"
        user = r"host\user"
        key = "C:/key"

    connection = RemoteConnection.from_args(Args)
    assert connection.target == r"host\user@10.0.0.1"
    assert connection.connect_timeout == 10


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


def test_compat_wrappers_help():
    wrappers = [
        "remote_start_albnn_train.py",
        "remote_query_albnn_status.py",
        "remote_queue_albnn_activation_sweep.py",
        "remote_monitor_job.py",
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
