# coding: utf-8
"""Start a persistent ALBNN training job on the remote workstation."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path, PureWindowsPath

from ALB.infrastructure.remote.transport import configure_stdio
from ALB.infrastructure.remote.transport import powershell_file_command
from ALB.infrastructure.remote.transport import ps_quote
from ALB.infrastructure.remote.transport import remote_path
from ALB.infrastructure.remote.transport import run_remote_powershell
from ALB.infrastructure.remote.transport import run_scp


DEFAULT_HOST = "10.182.216.22"
DEFAULT_USER = r"desktop-1pvi7rp\workstationg"
DEFAULT_KEY = "C:/Users/73401/.ssh/re_alb_desktop_1pvi7rp_ed25519"
DEFAULT_WORK = "F:/GWJ/20260507-train"
DEFAULT_ROOT = (
    "F:/GWJ/20260507-train/outputs/"
    "heat_albnn_79x39_thermal60_filtered_40000"
)
DEFAULT_REMOTE_PYTHON = "F:/GWJ/ALB/python.exe"
DEFAULT_MODEL = "force5_total_aug_v2_minmax_384_384_192_96_lr7em04"
DEFAULT_TASK = "ALB_TrainForce5Minmax_20260509"
DEFAULT_RUNNER = "F:/GWJ/20260507-train/run_train_force5_minmax_20260509.ps1"


def build_training_cmd(
    args: argparse.Namespace,
    train_data: str,
    validation_data: str,
    model_dir: str,
) -> list[str]:
    cmd = [
        "-u",
        "run/train_albnn.py",
        "--data",
        train_data,
        "--validation_data",
        validation_data,
        "--output_dir",
        model_dir,
        "--architecture",
        args.architecture,
        "--epochs",
        str(args.epochs),
        "--batch_size",
        str(args.batch_size),
        "--lr",
        str(args.lr),
        "--patience",
        str(args.patience),
        "--test_size",
        str(args.test_size),
        "--seed",
        str(args.seed),
        "--scaler",
        args.scaler,
        "--activation",
        args.activation,
        "--sine_omega0",
        str(args.sine_omega0),
        "--target_transform",
        args.target_transform,
        "--feature_set",
        args.feature_set,
        "--torch_threads",
        str(args.torch_threads),
    ]
    if args.no_augment:
        cmd.append("--no_augment")
    if args.target_transform != "none":
        cmd.extend(["--target_transform_scale", str(args.target_transform_scale)])
    if args.force_weight_max != 1.0 or args.force_weight_threshold > 0.0:
        cmd.extend(
            [
                "--force_weight_threshold",
                str(args.force_weight_threshold),
                "--force_weight_max",
                str(args.force_weight_max),
                "--force_weight_power",
                str(args.force_weight_power),
            ]
        )
    if args.input_noise_std > 0.0 and args.input_noise_copies > 0:
        cmd.extend(
            [
                "--input_noise_std",
                str(args.input_noise_std),
                "--input_noise_copies",
                str(args.input_noise_copies),
                "--input_noise_seed",
                str(args.input_noise_seed),
            ]
        )
        if args.input_noise_clip:
            cmd.append("--input_noise_clip")
    return cmd


def powershell_array(items: list[str]) -> str:
    lines = ["@("]
    for idx, item in enumerate(items):
        suffix = "," if idx < len(items) - 1 else ""
        lines.append(f"    {ps_quote(item)}{suffix}")
    lines.append(")")
    return "\n".join(lines)


def build_runner_content(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    data_dir = remote_path(args.root, args.data_dir)
    train_data = remote_path(data_dir, args.train_file)
    validation_data = remote_path(data_dir, args.validation_file)
    model_dir = remote_path(args.root, "models", args.model_name)
    log_dir = remote_path(args.root, "reports", "logs")
    run_log = remote_path(log_dir, f"train_{args.model_name}.log")
    stdout = remote_path(log_dir, f"train_{args.model_name}.stdout.log")
    stderr = remote_path(log_dir, f"train_{args.model_name}.stderr.log")
    train_cmd = build_training_cmd(args, train_data, validation_data, model_dir)
    target_transform_log = (
        f"{args.target_transform}(scale={args.target_transform_scale})"
        if args.target_transform != "none"
        else "none"
    )
    noise_log_lines = ""
    if args.input_noise_std > 0.0 and args.input_noise_copies > 0:
        noise_log_lines = (
            f'"INPUT_NOISE_STD={args.input_noise_std}" | Add-Content -Path $log -Encoding UTF8\n'
            f'"INPUT_NOISE_COPIES={args.input_noise_copies}" | Add-Content -Path $log -Encoding UTF8\n'
            f'"INPUT_NOISE_SEED={args.input_noise_seed}" | Add-Content -Path $log -Encoding UTF8\n'
            f'"INPUT_NOISE_CLIP={args.input_noise_clip}" | Add-Content -Path $log -Encoding UTF8\n'
        )

    runner = f"""$work = {ps_quote(args.work)}
$root = {ps_quote(args.root)}
$python = {ps_quote(args.remote_python)}
$modelName = {ps_quote(args.model_name)}
$modelDir = {ps_quote(model_dir)}
$logDir = {ps_quote(log_dir)}
$log = {ps_quote(run_log)}
$stdout = {ps_quote(stdout)}
$stderr = {ps_quote(stderr)}
$trainData = {ps_quote(train_data)}
$validationData = {ps_quote(validation_data)}

New-Item -ItemType Directory -Force -Path $logDir, $modelDir | Out-Null
Set-Location $work

$cmd = {powershell_array(train_cmd)}

"START_TIME=$(Get-Date -Format o)" | Set-Content -Path $log -Encoding UTF8
"MODEL_DIR=$modelDir" | Add-Content -Path $log -Encoding UTF8
"DATA=$trainData" | Add-Content -Path $log -Encoding UTF8
"VALIDATION=$validationData" | Add-Content -Path $log -Encoding UTF8
"SCALER={args.scaler}" | Add-Content -Path $log -Encoding UTF8
"ACTIVATION={args.activation}" | Add-Content -Path $log -Encoding UTF8
"SINE_OMEGA0={args.sine_omega0}" | Add-Content -Path $log -Encoding UTF8
"TARGET_TRANSFORM={target_transform_log}" | Add-Content -Path $log -Encoding UTF8
"NO_AUGMENT={args.no_augment}" | Add-Content -Path $log -Encoding UTF8
{noise_log_lines}"COMMAND=$python $($cmd -join ' ')" | Add-Content -Path $log -Encoding UTF8

& $python @cmd > $stdout 2> $stderr
$exit = $LASTEXITCODE

"END_TIME=$(Get-Date -Format o)" | Add-Content -Path $log -Encoding UTF8
"EXIT_CODE=$exit" | Add-Content -Path $log -Encoding UTF8
"STDOUT=$stdout" | Add-Content -Path $log -Encoding UTF8
"STDERR=$stderr" | Add-Content -Path $log -Encoding UTF8

exit $exit
"""
    paths = {
        "data_dir": data_dir,
        "train_data": train_data,
        "validation_data": validation_data,
        "model_dir": model_dir,
        "log_dir": log_dir,
        "run_log": run_log,
        "stdout": stdout,
        "stderr": stderr,
    }
    return runner, paths


def build_model_dir_check_script(
    args: argparse.Namespace,
    paths: dict[str, str],
) -> str:
    """Build the remote preflight that must pass before scheduling training."""
    allow_existing = "$true" if args.allow_existing_model_dir else "$false"
    return f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$modelDir = {ps_quote(paths["model_dir"])}
$trainData = {ps_quote(paths["train_data"])}
$validationData = {ps_quote(paths["validation_data"])}
$allowExisting = {allow_existing}
# Fail before Task Scheduler creation if the split artifacts are missing.
foreach ($dataPath in @($trainData, $validationData)) {{
    if (-not (Test-Path $dataPath)) {{
        throw "Training data file is missing: $dataPath"
    }}
    $dataItem = Get-Item $dataPath
    if ($dataItem.Length -le 0) {{
        throw "Training data file is empty: $dataPath"
    }}
}}
# Reuse incomplete model directories only when the queue explicitly asks for it.
if ((Test-Path $modelDir) -and (-not $allowExisting)) {{
    $existing = @(Get-ChildItem $modelDir -Force -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {{
        throw "Model directory already has files: $modelDir. Pass --allow-existing-model-dir to reuse it."
    }}
}}
"""


def build_launch_script(args: argparse.Namespace) -> str:
    disable_after_run = "$true" if args.disable_after_run else "$false"
    verbose_remote_output = "$true" if args.verbose_remote_output else "$false"
    task_run = powershell_file_command(args.runner)
    script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskName = {ps_quote(args.task_name)}
$runner = {ps_quote(args.runner)}
$disableAfterRun = {disable_after_run}
$verboseRemoteOutput = {verbose_remote_output}
$taskRun = {ps_quote(task_run)}
if (-not (Test-Path $runner)) {{
    throw "Runner was not uploaded: $runner"
}}
$createOutput = schtasks /Create /TN $taskName /SC ONCE /ST 23:59 /TR $taskRun /F 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{
    throw "schtasks create failed with exit $LASTEXITCODE`n$createOutput"
}}
$runOutput = schtasks /Run /TN $taskName 2>&1 | Out-String
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
    return script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start remote ALBNN training")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--work", default=DEFAULT_WORK)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--remote_python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--task_name", default=DEFAULT_TASK)
    parser.add_argument("--runner", default=DEFAULT_RUNNER)
    parser.add_argument("--model_name", default=DEFAULT_MODEL)
    parser.add_argument("--data_dir", default="data/force5_total_20260509")
    parser.add_argument("--train_file", default="train80_converged_force_lt5.csv")
    parser.add_argument("--validation_file", default="validation20_converged_force_lt5.csv")
    parser.add_argument("--architecture", default="41,384,384,192,96,2")
    parser.add_argument("--epochs", type=int, default=30000)
    parser.add_argument("--batch_size", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=0.0007)
    parser.add_argument("--patience", type=int, default=2000)
    parser.add_argument("--test_size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument(
        "--scaler",
        choices=["minmax", "standard", "cq2_sig_log_minmax", "cq2_sig_log_minmax01"],
        default="minmax",
    )
    parser.add_argument("--activation", choices=["gelu", "relu", "silu", "sin"], default="gelu")
    parser.add_argument("--sine_omega0", type=float, default=30.0)
    parser.add_argument(
        "--target_transform",
        choices=["none", "asinh", "signed_log1p"],
        default="none",
    )
    parser.add_argument("--target_transform_scale", type=float, default=5.0)
    parser.add_argument("--feature_set", default="aug_v2")
    parser.add_argument("--no_augment", action="store_true")
    parser.add_argument("--torch_threads", type=int, default=0)
    parser.add_argument("--force_weight_threshold", type=float, default=0.0)
    parser.add_argument("--force_weight_max", type=float, default=1.0)
    parser.add_argument("--force_weight_power", type=float, default=1.0)
    parser.add_argument("--input_noise_std", type=float, default=0.0)
    parser.add_argument("--input_noise_copies", type=int, default=0)
    parser.add_argument("--input_noise_seed", type=int, default=None)
    parser.add_argument("--input_noise_clip", action="store_true")
    parser.add_argument("--allow-existing-model-dir", action="store_true")
    parser.add_argument("--no-disable-after-run", action="store_false", dest="disable_after_run")
    parser.set_defaults(disable_after_run=True)
    parser.add_argument(
        "--verbose-remote-output",
        action="store_true",
        help="Print raw remote schtasks output for debugging. Default keeps logs structured.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = build_parser().parse_args(argv)
    if args.input_noise_seed is None:
        args.input_noise_seed = args.seed + 1009
    args.runner = str(PureWindowsPath(args.runner)).replace("\\", "/")
    runner_content, paths = build_runner_content(args)
    check_script = build_model_dir_check_script(args, paths)
    launch_script = build_launch_script(args)
    if args.dry_run:
        print(runner_content)
        print("---REMOTE-CHECK---")
        print(check_script)
        print("---REMOTE-LAUNCH---")
        print(launch_script)
        return 0

    check_result = run_remote_powershell(args, check_script)
    if check_result.stdout:
        print(check_result.stdout)
    if check_result.stderr:
        print(check_result.stderr)
    if check_result.returncode != 0:
        return check_result.returncode

    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as f:
        temp_path = Path(f.name)
        f.write(runner_content)
    try:
        scp_result = run_scp(args, temp_path, args.runner)
    finally:
        temp_path.unlink(missing_ok=True)
    if scp_result.stdout:
        print(scp_result.stdout)
    if scp_result.stderr:
        print(scp_result.stderr)
    if scp_result.returncode != 0:
        return scp_result.returncode

    launch_result = run_remote_powershell(args, launch_script)
    if launch_result.stdout:
        print(launch_result.stdout)
    if launch_result.stderr:
        print(launch_result.stderr)
    if launch_result.returncode != 0:
        return launch_result.returncode

    print("REMOTE_TRAINING_LAUNCH")
    print(f"task_name={args.task_name}")
    print(f"runner={args.runner}")
    print(f"model_dir={paths['model_dir']}")
    print(f"stdout={paths['stdout']}")
    print(f"stderr={paths['stderr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
