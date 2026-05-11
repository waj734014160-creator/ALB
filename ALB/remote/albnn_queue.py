# coding: utf-8
"""Queue and supervise remote ALBNN training jobs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

from .albnn_start import DEFAULT_REMOTE_PYTHON
from .albnn_start import DEFAULT_WORK
from .common import parse_iso
from .defaults import DEFAULT_HOST
from .defaults import DEFAULT_KEY
from .defaults import DEFAULT_ROOT
from .defaults import DEFAULT_USER
from .albnn_status import latest_epoch
from .albnn_status import parse_json_text
from .albnn_status import parse_key_values
from .albnn_status import query_remote
from .transport import configure_stdio
from .transport import ps_quote
from .transport import remote_path
from .transport import run_remote_powershell


DEFAULT_CURRENT_TASK = "ALB_TrainForce5Sin10_20260509"
DEFAULT_CURRENT_MODEL = "force5_total_aug_v2_minmax_sin10_384_384_192_96_lr2em04"


def _default_project_root() -> Path:
    if sys.argv:
        script = Path(sys.argv[0]).resolve()
        if script.name == "remote_queue_albnn_activation_sweep.py":
            return script.parents[2]
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _default_project_root()


@dataclass(frozen=True)
class ActivationSpec:
    name: str
    lr: float
    patience: int
    sine_omega0: float | None = None


@dataclass(frozen=True)
class TransformSpec:
    label: str
    target_transform: str
    scaler: str
    model_token: str
    scale: float | None = None


@dataclass(frozen=True)
class ComboSpec:
    activation: ActivationSpec
    transform: TransformSpec
    architecture: str
    run_tag: str
    task_name: str
    runner: str
    model_name: str
    label: str | None = None
    input_noise_std: float = 0.0
    input_noise_copies: int = 0
    input_noise_seed: int | None = None
    input_noise_clip: bool = False

    @property
    def key(self) -> str:
        if self.label:
            return self.label
        return f"{self.activation.name}+{self.transform.label}"


ACTIVATIONS = [
    ActivationSpec("gelu", lr=0.0007, patience=2000),
    ActivationSpec("relu", lr=0.0007, patience=2000),
    ActivationSpec("silu", lr=0.0007, patience=2000),
    ActivationSpec("sin", lr=0.0002, patience=2000, sine_omega0=10.0),
]

TRANSFORMS = [
    TransformSpec("minmax", "none", "minmax", "minmax"),
    TransformSpec("asinh_minmax", "asinh", "minmax", "asinh5_minmax", scale=5.0),
    TransformSpec(
        "signed_log1p_minmax",
        "signed_log1p",
        "minmax",
        "signedlog1p5_minmax",
        scale=5.0,
    ),
]


def lr_token(lr: float) -> str:
    known = {
        0.0007: "lr7em04",
        0.0002: "lr2em04",
    }
    for value, token in known.items():
        if abs(lr - value) < 1e-12:
            return token
    text = f"{lr:.0e}".replace("-", "m").replace("+", "")
    return "lr" + text.replace("e", "e")


def architecture_token(architecture: str) -> str:
    values = [item.strip() for item in architecture.split(",") if item.strip()]
    if len(values) <= 2:
        return "_".join(values)
    return "_".join(values[1:-1])


def activation_token(activation: ActivationSpec) -> str:
    if activation.name == "sin":
        omega = int(activation.sine_omega0 or 10)
        return f"sin{omega}"
    return activation.name


def model_name_for(
    transform: TransformSpec,
    activation: ActivationSpec,
    architecture: str,
) -> str:
    arch = architecture_token(architecture)
    lr = lr_token(activation.lr)
    if transform.label == "minmax" and activation.name == "gelu":
        return f"force5_total_aug_v2_minmax_{arch}_{lr}"
    if transform.label == "minmax" and activation.name == "sin":
        return f"force5_total_aug_v2_minmax_{activation_token(activation)}_{arch}_{lr}"
    return (
        f"force5_total_aug_v2_{transform.model_token}_"
        f"{activation_token(activation)}_{arch}_{lr}"
    )


def task_name_for(transform: TransformSpec, activation: ActivationSpec, run_tag: str) -> str:
    return f"ALB_TrainForce5Sweep_{activation_token(activation)}_{transform.label}_{run_tag}"


def build_combos(args: argparse.Namespace) -> list[ComboSpec]:
    combos = []
    for transform in TRANSFORMS:
        for activation in ACTIVATIONS:
            model_name = model_name_for(transform, activation, args.architecture)
            task_name = task_name_for(transform, activation, args.run_tag)
            runner = remote_path(args.work, f"run_train_{model_name}.ps1")
            combos.append(
                ComboSpec(
                    activation=activation,
                    transform=transform,
                    architecture=args.architecture,
                    run_tag=args.run_tag,
                    task_name=task_name,
                    runner=runner,
                    model_name=model_name,
                )
            )
    return combos


def load_config(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError("Queue config must be a JSON object")
    jobs = config.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Queue config must contain a non-empty 'jobs' list")
    return config


def apply_config_defaults(args: argparse.Namespace, config: dict[str, Any] | None) -> None:
    if not config:
        return
    for key in (
        "poll_seconds",
        "tail",
        "ssh_timeout",
        "data_dir",
        "train_file",
        "validation_file",
        "architecture",
        "epochs",
        "batch_size",
        "test_size",
        "seed",
        "feature_set",
        "no_augment",
        "torch_threads",
        "target_transform_scale",
        "default_sine_omega0",
        "input_noise_std",
        "input_noise_copies",
        "input_noise_seed",
        "input_noise_clip",
        "run_tag",
    ):
        if key in config:
            setattr(args, key, config[key])

    log_sync = config.get("log_sync") or {}
    if "enabled" in log_sync:
        args.sync_logs = bool(log_sync["enabled"])
    if "local_dir" in log_sync:
        args.sync_dir = str(log_sync["local_dir"])
    if "tail" in log_sync:
        args.tail = int(log_sync["tail"])

    defaults = config.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("Queue config 'defaults' must be a JSON object")
    for key, value in defaults.items():
        if hasattr(args, key):
            setattr(args, key, value)


def build_config_combos(args: argparse.Namespace, config: dict[str, Any]) -> list[ComboSpec]:
    defaults = config.get("defaults") or {}
    combos = []
    for index, job in enumerate(config["jobs"], start=1):
        if not isinstance(job, dict):
            raise ValueError(f"Job {index} must be a JSON object")

        def value(name: str, fallback: Any = None) -> Any:
            if name in job:
                return job[name]
            if name in defaults:
                return defaults[name]
            return getattr(args, name, fallback)

        activation_name = str(value("activation", "gelu"))
        lr = float(value("lr", 0.0007))
        patience = int(value("patience", 2000))
        sine_omega0 = value("sine_omega0", None)
        activation = ActivationSpec(
            activation_name,
            lr=lr,
            patience=patience,
            sine_omega0=float(sine_omega0) if sine_omega0 is not None else None,
        )

        scaler = str(value("scaler", "minmax"))
        target_transform = str(value("target_transform", "none"))
        transform_label = str(
            value(
                "transform_label",
                "minmax" if target_transform == "none" and scaler == "minmax" else target_transform,
            )
        )
        transform_scale = value("target_transform_scale", None)
        transform = TransformSpec(
            transform_label,
            target_transform,
            scaler,
            str(value("model_token", transform_label)),
            scale=float(transform_scale)
            if target_transform != "none" and transform_scale is not None
            else None,
        )

        architecture = str(value("architecture", args.architecture))
        model_name = job.get("model_name")
        if not model_name:
            model_name = model_name_for(transform, activation, architecture)
        task_name = job.get("task_name")
        if not task_name:
            task_name = task_name_for(transform, activation, str(value("run_tag", args.run_tag)))
        runner = job.get("runner")
        if not runner:
            runner = remote_path(args.work, f"run_train_{model_name}.ps1")

        combos.append(
            ComboSpec(
                activation=activation,
                transform=transform,
                architecture=architecture,
                run_tag=str(value("run_tag", args.run_tag)),
                task_name=str(task_name),
                runner=str(runner),
                model_name=str(model_name),
                label=str(job.get("label") or f"job{index}_{activation_name}_{transform_label}"),
                input_noise_std=float(value("input_noise_std", args.input_noise_std)),
                input_noise_copies=int(value("input_noise_copies", args.input_noise_copies)),
                input_noise_seed=(
                    int(value("input_noise_seed"))
                    if value("input_noise_seed", None) is not None
                    else None
                ),
                input_noise_clip=bool(value("input_noise_clip", args.input_noise_clip)),
            )
        )
    return combos


def extract_json_value(text: str) -> Any:
    starts = [idx for idx in (text.find("["), text.find("{")) if idx >= 0]
    if not starts:
        return []
    return json.loads(text[min(starts) :])


def fetch_remote_models(args: argparse.Namespace) -> list[dict[str, Any]]:
    model_root = remote_path(args.root, "models")
    script = f"""
$modelRoot = {ps_quote(model_root)}
if (Test-Path $modelRoot) {{
  @(
    Get-ChildItem $modelRoot -Directory | ForEach-Object {{
      $metaPath = Join-Path $_.FullName 'metadata.json'
      $summaryPath = Join-Path $_.FullName 'validation_summary.json'
      $checkpointPath = Join-Path $_.FullName 'best_albnn.pth'
      $meta = $null
      if (Test-Path $metaPath) {{
        try {{ $meta = Get-Content $metaPath -Raw | ConvertFrom-Json }} catch {{ $meta = $null }}
      }}
      $activation = $null
      $omega = $null
      $targetTransform = $null
      $targetScale = $null
      $scaler = $null
      if ($meta -ne $null) {{
        $scaler = $meta.scaler
        if ($meta.activation -ne $null) {{
          $activation = $meta.activation.name
          $omega = $meta.activation.sine_omega0
        }}
        if ($meta.target_transform -ne $null) {{
          $targetTransform = $meta.target_transform.name
          $targetScale = $meta.target_transform.scale
        }}
      }}
      [PSCustomObject]@{{
        name = $_.Name
        full_name = $_.FullName
        has_validation = [bool](Test-Path $summaryPath)
        has_checkpoint = [bool](Test-Path $checkpointPath)
        scaler = $scaler
        activation = $activation
        sine_omega0 = $omega
        target_transform = $targetTransform
        target_transform_scale = $targetScale
        last_write_time = $_.LastWriteTime.ToString('o')
      }}
    }}
  ) | ConvertTo-Json -Depth 6
}} else {{
  @() | ConvertTo-Json
}}
"""
    result = run_remote_powershell(args, script)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to scan remote models, exit={result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    parsed = extract_json_value(result.stdout or "[]")
    if isinstance(parsed, dict):
        return [parsed]
    return list(parsed or [])


def model_index(models: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("name")): item for item in models}


def combo_status(
    combo: ComboSpec,
    models_by_name: dict[str, dict[str, Any]],
    args: argparse.Namespace,
) -> str:
    item = models_by_name.get(combo.model_name)
    if item is None:
        return "pending"
    if item.get("has_validation"):
        return "completed"
    if args.rerun_failed:
        return "rerun_incomplete"
    return "blocked_incomplete"


def query_args(args: argparse.Namespace, combo: ComboSpec) -> argparse.Namespace:
    return argparse.Namespace(
        host=args.host,
        user=args.user,
        key=args.key,
        root=args.root,
        task_name=combo.task_name,
        model_name=combo.model_name,
        tail=args.tail,
        ssh_timeout=args.ssh_timeout,
    )


def latest_logged_losses(stdout_lines: list[str]) -> dict[str, float | None]:
    train_loss = None
    test_loss = None
    for line in stdout_lines:
        match = re.search(
            r"epoch\s+\d+/\d+:\s+train=([0-9.eE+-]+),\s+test=([0-9.eE+-]+)",
            line,
        )
        if match:
            train_loss = float(match.group(1))
            test_loss = float(match.group(2))
    return {"train_loss": train_loss, "test_loss": test_loss}


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "job"


def sync_root(args: argparse.Namespace) -> Path:
    root = Path(args.sync_dir) if args.sync_dir else PROJECT_ROOT / "outputs" / "queue_logs" / "remote_sync"
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return root


def write_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def sync_logs(
    args: argparse.Namespace,
    combo: ComboSpec,
    data: dict[str, Any],
    status: dict[str, Any],
) -> None:
    if not args.sync_logs:
        return
    job_dir = sync_root(args) / safe_name(combo.model_name)
    job_dir.mkdir(parents=True, exist_ok=True)

    write_text(job_dir / "run_tail.log", data.get("run_log_tail") or [])
    write_text(job_dir / "stdout_tail.log", data.get("stdout_tail") or [])
    write_text(job_dir / "stderr_tail.log", data.get("stderr_tail") or [])

    if data.get("validation_summary_text"):
        (job_dir / "validation_summary.json").write_text(
            data["validation_summary_text"], encoding="utf-8"
        )
    if data.get("metadata_text"):
        (job_dir / "metadata.json").write_text(data["metadata_text"], encoding="utf-8")

    summary = status.get("summary") or {}
    snapshot = {
        "local_time": datetime.now().isoformat(timespec="seconds"),
        "remote_time": data.get("remote_time"),
        "label": combo.key,
        "task_name": combo.task_name,
        "model_name": combo.model_name,
        "state": status.get("state"),
        "epoch": status.get("latest"),
        "total_epoch": status.get("total"),
        "train_loss": status.get("train_loss"),
        "test_loss": status.get("test_loss"),
        "elapsed_min": status.get("elapsed_min"),
        "validation_r2_fx": summary.get("r2_fx"),
        "validation_r2_fy": summary.get("r2_fy"),
        "remote_stdout": data.get("stdout_path"),
        "remote_stderr": data.get("stderr_path"),
        "remote_run_log": data.get("run_log_path"),
    }
    (job_dir / "status.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with open(job_dir / "status.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def state_from_query(data: dict[str, Any]) -> dict[str, Any]:
    run_log_tail = data.get("run_log_tail") or []
    stdout_tail = data.get("stdout_tail") or []
    kv = parse_key_values(run_log_tail)
    summary = parse_json_text(data.get("validation_summary_text"))
    start_time = parse_iso(kv.get("START_TIME"))
    end_time = parse_iso(kv.get("END_TIME"))
    remote_time = parse_iso(data.get("remote_time"))
    stop_time = end_time or remote_time
    elapsed_min = None
    if start_time and stop_time:
        elapsed_min = max((stop_time - start_time).total_seconds() / 60.0, 0.0)

    latest, total, early_stop = latest_epoch(stdout_tail)
    losses = latest_logged_losses(stdout_tail)
    processes = data.get("processes") or []
    if isinstance(processes, dict):
        processes = [processes]
    exit_code = kv.get("EXIT_CODE")
    if summary and exit_code in (None, "0"):
        state = "completed"
    elif processes:
        state = "running"
    elif exit_code is not None:
        state = f"exited({exit_code})"
    else:
        state = "not_running"
    return {
        "state": state,
        "summary": summary,
        "exit_code": exit_code,
        "latest": latest,
        "total": total,
        "early_stop": early_stop,
        "elapsed_min": elapsed_min,
        **losses,
    }


def wait_for_combo(args: argparse.Namespace, combo: ComboSpec) -> bool:
    while True:
        data = query_remote(query_args(args, combo))
        status = state_from_query(data)
        sync_logs(args, combo, data, status)
        latest = status["latest"]
        total = status["total"]
        epoch_text = f"{latest}/{total}" if latest is not None and total else "n/a"
        elapsed = status["elapsed_min"]
        elapsed_text = f"{elapsed:.1f} min" if elapsed is not None else "n/a"
        train_loss = status["train_loss"]
        test_loss = status["test_loss"]
        train_loss_text = f"{train_loss:.4e}" if train_loss is not None else "n/a"
        test_loss_text = f"{test_loss:.4e}" if test_loss is not None else "n/a"
        r2_text = ""
        summary = status["summary"]
        if summary:
            r2_fx = summary.get("r2_fx")
            r2_fy = summary.get("r2_fy")
            if r2_fx is not None and r2_fy is not None:
                r2_text = f", validation_r2_fx={r2_fx:.6f}, validation_r2_fy={r2_fy:.6f}"
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"{combo.key}: {status['state']}, epoch={epoch_text}, "
            f"train_loss={train_loss_text}, test_loss={test_loss_text}, "
            f"elapsed={elapsed_text}{r2_text}",
            flush=True,
        )
        if status["state"] == "completed":
            return True
        if status["state"].startswith("exited("):
            return False
        if status["state"] == "not_running":
            return False
        time.sleep(args.poll_seconds)


def _legacy_start_script_from_argv() -> Path | None:
    if not sys.argv:
        return None
    script = Path(sys.argv[0]).resolve()
    if script.name != "remote_queue_albnn_activation_sweep.py":
        return None
    candidate = script.with_name("remote_start_albnn_train.py")
    if candidate.exists():
        return candidate
    return None


def _start_command_prefix() -> list[str]:
    script = _legacy_start_script_from_argv()
    if script is not None:
        return [sys.executable, str(script)]
    return [sys.executable, "-m", "ALB.remote.albnn_start"]


def launch_command(
    args: argparse.Namespace,
    combo: ComboSpec,
    allow_existing: bool,
) -> list[str]:
    cmd = _start_command_prefix() + [
        "--host",
        args.host,
        "--user",
        args.user,
        "--key",
        args.key,
        "--work",
        args.work,
        "--root",
        args.root,
        "--remote_python",
        args.remote_python,
        "--task_name",
        combo.task_name,
        "--runner",
        combo.runner,
        "--model_name",
        combo.model_name,
        "--data_dir",
        args.data_dir,
        "--train_file",
        args.train_file,
        "--validation_file",
        args.validation_file,
        "--architecture",
        combo.architecture,
        "--epochs",
        str(args.epochs),
        "--batch_size",
        str(args.batch_size),
        "--lr",
        str(combo.activation.lr),
        "--patience",
        str(combo.activation.patience),
        "--test_size",
        str(args.test_size),
        "--seed",
        str(args.seed),
        "--scaler",
        combo.transform.scaler,
        "--activation",
        combo.activation.name,
        "--sine_omega0",
        str(combo.activation.sine_omega0 or args.default_sine_omega0),
        "--target_transform",
        combo.transform.target_transform,
        "--target_transform_scale",
        str(combo.transform.scale or args.target_transform_scale),
        "--feature_set",
        args.feature_set,
        "--torch_threads",
        str(args.torch_threads),
    ]
    if args.no_augment:
        cmd.append("--no_augment")
    if combo.input_noise_std > 0.0 and combo.input_noise_copies > 0:
        noise_seed = (
            combo.input_noise_seed
            if combo.input_noise_seed is not None
            else args.input_noise_seed
        )
        if noise_seed is None:
            noise_seed = args.seed + 1009
        cmd.extend(
            [
                "--input_noise_std",
                str(combo.input_noise_std),
                "--input_noise_copies",
                str(combo.input_noise_copies),
                "--input_noise_seed",
                str(noise_seed),
            ]
        )
        if combo.input_noise_clip:
            cmd.append("--input_noise_clip")
    if allow_existing:
        cmd.append("--allow-existing-model-dir")
    if args.verbose_remote_output:
        cmd.append("--verbose-remote-output")
    return cmd


def launch_combo(args: argparse.Namespace, combo: ComboSpec, allow_existing: bool) -> bool:
    cmd = launch_command(args, combo, allow_existing)
    print(f"Launching {combo.key}: {combo.model_name}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        capture_output=True,
        env=env,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    return result.returncode == 0


def print_queue(
    args: argparse.Namespace,
    combos: list[ComboSpec],
    models: list[dict[str, Any]],
) -> None:
    by_name = model_index(models)
    title = "REMOTE ALBNN JSON QUEUE" if args.config else "REMOTE ALBNN ACTIVATION SWEEP QUEUE"
    print(title)
    for combo in combos:
        status = combo_status(combo, by_name, args)
        if combo.model_name == args.current_model_name and status != "completed":
            status = "current_running_or_pending"
        print(f"- {combo.key}: {status} -> {combo.model_name}")
        if status in {"pending", "rerun_incomplete"}:
            cmd = launch_command(args, combo, allow_existing=status == "rerun_incomplete")
            print("  " + subprocess.list2cmdline(cmd))


def run_queue(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    apply_config_defaults(args, config)
    combos = build_config_combos(args, config) if config else build_combos(args)
    models = fetch_remote_models(args)
    if args.dry_run:
        print_queue(args, combos, models)
        return 0

    if config:
        return run_combos(args, combos, models)

    current = next(
        (combo for combo in combos if combo.model_name == args.current_model_name),
        ComboSpec(
            ActivationSpec("sin", lr=0.0002, patience=2000, sine_omega0=10.0),
            TRANSFORMS[0],
            args.architecture,
            args.run_tag,
            args.current_task_name,
            remote_path(args.work, f"run_train_{args.current_model_name}.ps1"),
            args.current_model_name,
        ),
    )
    current = ComboSpec(
        current.activation,
        current.transform,
        current.architecture,
        current.run_tag,
        args.current_task_name,
        current.runner,
        current.model_name,
    )
    if not args.skip_current_wait:
        print(f"Waiting for current training: {current.model_name}", flush=True)
        if not wait_for_combo(args, current):
            print("Current training did not complete successfully; queue stopped.", file=sys.stderr)
            return 1

    return run_combos(args, combos, fetch_remote_models(args))


def run_combos(
    args: argparse.Namespace,
    combos: list[ComboSpec],
    models: list[dict[str, Any]],
) -> int:
    models = fetch_remote_models(args)
    by_name = model_index(models)
    for combo in combos:
        status = combo_status(combo, by_name, args)
        if status == "completed":
            print(f"Skipping completed {combo.key}: {combo.model_name}", flush=True)
            continue
        if status in {"blocked_incomplete", "rerun_incomplete"}:
            remote_status = state_from_query(query_remote(query_args(args, combo)))
            if remote_status["state"] == "running":
                print(
                    f"Resuming active {combo.key}: {combo.model_name}",
                    flush=True,
                )
                if not wait_for_combo(args, combo):
                    print(f"Training failed for {combo.key}.", file=sys.stderr)
                    if args.stop_on_failure:
                        return 4
                by_name = model_index(fetch_remote_models(args))
                continue
        if status == "blocked_incomplete":
            print(
                f"Blocked by incomplete existing model directory for {combo.key}: "
                f"{combo.model_name}. Use --rerun-failed to overwrite.",
                file=sys.stderr,
            )
            if args.stop_on_failure:
                return 2
            continue

        allow_existing = status == "rerun_incomplete"
        if not launch_combo(args, combo, allow_existing=allow_existing):
            print(f"Failed to launch {combo.key}.", file=sys.stderr)
            if args.stop_on_failure:
                return 3
            continue
        if not wait_for_combo(args, combo):
            print(f"Training failed for {combo.key}.", file=sys.stderr)
            if args.stop_on_failure:
                return 4
        by_name = model_index(fetch_remote_models(args))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queue and supervise remote ALBNN training jobs")
    parser.add_argument(
        "--config",
        default=None,
        help="Preferred JSON queue config. Put experiment parameters here instead of editing the script.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--work", default=DEFAULT_WORK)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--remote-python", dest="remote_python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--current-task-name", default=DEFAULT_CURRENT_TASK)
    parser.add_argument("--current-model-name", default=DEFAULT_CURRENT_MODEL)
    parser.add_argument("--data_dir", default="data/force5_total_20260509")
    parser.add_argument("--train_file", default="train80_converged_force_lt5.csv")
    parser.add_argument("--validation_file", default="validation20_converged_force_lt5.csv")
    parser.add_argument("--architecture", default="41,384,384,192,96,2")
    parser.add_argument("--epochs", type=int, default=30000)
    parser.add_argument("--batch_size", type=int, default=1024)
    parser.add_argument("--test_size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument("--feature_set", default="aug_v2")
    parser.add_argument("--no_augment", action="store_true")
    parser.add_argument("--torch_threads", type=int, default=0)
    parser.add_argument("--target_transform_scale", type=float, default=5.0)
    parser.add_argument("--default_sine_omega0", type=float, default=30.0)
    parser.add_argument("--input_noise_std", type=float, default=0.0)
    parser.add_argument("--input_noise_copies", type=int, default=0)
    parser.add_argument("--input_noise_seed", type=int, default=None)
    parser.add_argument("--input_noise_clip", action="store_true")
    parser.add_argument("--run-tag", default="20260509")
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--tail", type=int, default=120)
    parser.add_argument("--ssh-timeout", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rerun-failed", action="store_true")
    parser.add_argument("--skip-current-wait", action="store_true")
    parser.add_argument("--sync-dir", default=None)
    parser.add_argument("--no-sync-logs", action="store_false", dest="sync_logs")
    parser.add_argument("--verbose-remote-output", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true", dest="stop_on_failure")
    parser.add_argument("--continue-on-failure", action="store_false", dest="stop_on_failure")
    parser.set_defaults(stop_on_failure=True, sync_logs=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = build_parser().parse_args(argv)
    return run_queue(args)


if __name__ == "__main__":
    raise SystemExit(main())
