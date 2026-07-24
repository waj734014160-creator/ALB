"""Run detached, reproducible ALB 0.4 source and wheel acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence
import uuid
import zipfile

from tools.validation.release_source_identity import (
    materialize_candidate_source,
)


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path("E:/Anaconda2023/envs/ALB/python.exe")
VERSION = "0.4.0"
FEATURE_MANIFEST = ROOT / "tools/validation/release_feature_manifest_0_4.json"
FEATURE_ID_PREFIX = "V4-"
REPORT_SCHEMA = "alb.release-acceptance.v0.4"
RUN_SLUG = "alb_0_4"
PAPER_ROOT = Path("F:/BaiduSyncdisk/博士论文/PAPER_WORK")
SURROGATE_ROOT = ROOT.parent / "SURROGATE_TRAIN"
FORBIDDEN_MEMBERS = {
    "ALB/config/legacy.py",
    "ALB/config/migration.py",
    "ALB/control/adapters.py",
    "ALB/infrastructure/legacy_signal.py",
    "ALB/surrogate/migration.py",
    "ALB/systems/alb/builder.py",
    "ALB/systems/alb/factories.py",
    "ALB/systems/alb/runtime_adapter.py",
}
FORBIDDEN_SOURCE_TOKENS: tuple[str, ...] = (
    "class Signal",
    "lead_loop",
    "LegacyBearingAdapter",
    "LegacyControllerAdapter",
    "LegacySignalAdapter",
    "LegacyBearingRuntimeAdapter",
    "trust_pickle",
    "trust-pickle",
)


def _run(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    evidence = {
        "command": [str(item) for item in command],
        "cwd": str(cwd),
        "returncode": result.returncode,
        "duration_s": time.perf_counter() - started,
        "stdout_tail": result.stdout.splitlines()[-80:],
        "stderr_tail": result.stderr.splitlines()[-80:],
    }
    if result.returncode != 0:
        raise RuntimeError(json.dumps(evidence, indent=2, ensure_ascii=False))
    return evidence


def _output(command: Sequence[str | Path], *, cwd: Path) -> str:
    result = subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _feature_nodeids() -> list[str]:
    payload = json.loads(FEATURE_MANIFEST.read_text(encoding="utf-8"))
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("0.4 feature manifest is empty")
    expected = [
        f"{FEATURE_ID_PREFIX}{index:02d}"
        for index in range(1, len(features) + 1)
    ]
    actual = [item.get("id") for item in features]
    if actual != expected:
        raise ValueError("0.4 feature IDs must be contiguous and ordered")
    nodeids = sorted(
        {
            str(nodeid)
            for item in features
            for nodeid in item.get("required_nodeids", [])
        }
    )
    if not nodeids:
        raise ValueError("0.4 feature manifest has no required nodeids")
    return nodeids


def _build_wheel(
    candidate: Path,
    destination: Path,
    *,
    source_date_epoch: str,
) -> tuple[Path, dict[str, Any]]:
    destination.mkdir(parents=True)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = source_date_epoch
    env["PYTHONHASHSEED"] = "0"
    evidence = _run(
        [
            PYTHON,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            destination,
        ],
        cwd=candidate,
        env=env,
    )
    wheels = list(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel, found {wheels}")
    return wheels[0], evidence


def _inspect_wheel(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.namelist())
        forbidden_members = sorted(FORBIDDEN_MEMBERS.intersection(members))
        tool_members = [item for item in members if item.startswith("tools/")]
        token_hits: list[str] = []
        for member in members:
            if not member.startswith("ALB/") or not member.endswith(".py"):
                continue
            text = archive.read(member).decode("utf-8")
            for token in FORBIDDEN_SOURCE_TOKENS:
                if token in text:
                    token_hits.append(f"{member}: {token}")
    if forbidden_members or tool_members or token_hits:
        raise RuntimeError(
            f"wheel legacy-zero gate failed: "
            f"{forbidden_members=}, {tool_members=}, {token_hits=}"
        )
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "member_count": len(members),
        "forbidden_members": forbidden_members,
        "tool_members": tool_members,
        "forbidden_token_hits": token_hits,
    }


def _isolated_smoke(
    wheel: Path,
    runtime: Path,
) -> list[dict[str, Any]]:
    venv = runtime / "venv"
    _run(
        [PYTHON, "-m", "venv", "--system-site-packages", venv],
        cwd=runtime,
    )
    python = venv / "Scripts/python.exe"
    pip = venv / "Scripts/pip.exe"
    install = _run(
        [pip, "install", "--no-deps", "--force-reinstall", wheel],
        cwd=runtime,
    )
    smoke_code = """
import ALB
assert ALB.__version__ == "__ALB_VERSION__"
assert not hasattr(ALB, "Signal")
cfg = ALB.BearingConfig({
    "family": "liquid_film",
    "unit_system": "dimensional",
    "time_step": 0.001,
    "node": 0,
    "film": {
        "circumferential_elements": 5,
        "axial_elements": 3,
        "max_iterations": 3,
    },
    "restrictors": None,
    "thermal": None,
})
bearing = ALB.build_bearing(cfg)
assert not hasattr(bearing, "init")
assert bearing.calculate(displacement=(0.0, 0.0), time=0.0).force.shape == (2,)
print(ALB.__file__)
""".replace("__ALB_VERSION__", VERSION)
    core = _run([python, "-c", smoke_code], cwd=runtime)
    paper_code = f"""
import ALB
cfg = ALB.load_bearing_config(
    r"{PAPER_ROOT / 'task/PAPER/config/alb12.json5'}"
)
assert cfg.family == "active_lubricated"
assert cfg.control_mode == "pid"
print(cfg.spec["time_step"])
"""
    paper = _run([python, "-c", paper_code], cwd=runtime)
    surrogate_code = f"""
import json
from pathlib import Path
import ALB
root = Path(r"{SURROGATE_ROOT}")
ref = json.loads((root / "refs/alb_0_4_consumer_reference_v1.json").read_text(encoding="utf-8"))
assert ref["schema"] == "surrogate-train.alb-0.4-consumer-reference.v1"
site_packages = Path(r"{venv / 'Lib/site-packages'}").resolve()
assert Path(ALB.__file__).resolve().is_relative_to(site_packages)
print(ALB.__version__)
"""
    surrogate = _run([python, "-c", surrogate_code], cwd=runtime)
    training_cli = _run(
        [
            python,
            SURROGATE_ROOT / "run/train/train_albnn.py",
            "--help",
        ],
        cwd=runtime,
    )
    remote_cli = _run(
        [
            python,
            "-m",
            "ALB.surrogate.training.remote.status",
            "--help",
        ],
        cwd=runtime,
    )
    return [install, core, paper, surrogate, training_cli, remote_cli]


def run_acceptance(
    candidate_ref: str,
    *,
    publish: bool,
) -> dict[str, Any]:
    candidate_sha = _output(
        ["git", "rev-parse", f"{candidate_ref}^{{commit}}"],
        cwd=ROOT,
    )
    short_sha = candidate_sha[:12]
    runtime = (
        ROOT
        / "outputs/release_acceptance"
        / f"{RUN_SLUG}_{short_sha}_{uuid.uuid4().hex[:8]}"
    )
    worktree = (
        ROOT.parent
        / f"_{RUN_SLUG}_candidate_{short_sha}_{uuid.uuid4().hex[:6]}"
    )
    runtime.mkdir(parents=True)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "release": VERSION,
        "candidate_commit": candidate_sha,
        "runtime": str(runtime),
        "status": "running",
        "phases": {},
    }
    report_path = runtime / "report.json"
    try:
        _run(
            ["git", "worktree", "add", "--detach", worktree, candidate_sha],
            cwd=ROOT,
        )
        status = _output(["git", "status", "--porcelain"], cwd=worktree)
        if status:
            raise RuntimeError("detached candidate worktree is not clean")
        source1 = runtime / "source1"
        source2 = runtime / "source2"
        source_evidence = materialize_candidate_source(
            ROOT,
            candidate_sha,
            source1,
        )
        second_source_evidence = materialize_candidate_source(
            ROOT,
            candidate_sha,
            source2,
        )
        if source_evidence != second_source_evidence:
            raise RuntimeError("canonical candidate source evidence changed")
        epoch = str(source_evidence["source_date_epoch"])
        build1, build1_evidence = _build_wheel(
            source1,
            runtime / "build1",
            source_date_epoch=epoch,
        )
        build2, build2_evidence = _build_wheel(
            source2,
            runtime / "build2",
            source_date_epoch=epoch,
        )
        first = _inspect_wheel(build1)
        second = _inspect_wheel(build2)
        if first["sha256"] != second["sha256"]:
            raise RuntimeError("consecutive wheel builds are not reproducible")
        report["phases"]["wheel"] = {
            "builds": [build1_evidence, build2_evidence],
            "source": source_evidence,
            "first": first,
            "second": second,
            "reproducible": True,
        }
        report["phases"]["pytest"] = _run(
            [PYTHON, "-m", "pytest", "-q"],
            cwd=worktree,
        )
        report["phases"]["required_nodeids"] = _run(
            [PYTHON, "-m", "pytest", "-q", *_feature_nodeids()],
            cwd=worktree,
        )
        report["phases"]["mypy"] = _run(
            [
                PYTHON,
                "tools/validation/run_layered_mypy.py",
                "--mypy-target",
                ROOT / "outputs/.devtools",
                "--cache-root",
                runtime / "mypy_cache",
            ],
            cwd=worktree,
        )
        report["phases"]["resources"] = _run(
            [
                PYTHON,
                "-m",
                "tools.validation.run_resource_acceptance_0_4",
            ],
            cwd=worktree,
        )
        report["phases"]["isolated_smoke"] = _isolated_smoke(
            build1,
            runtime,
        )
        if publish:
            destination = ROOT / "dist" / build1.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(build1, destination)
            if _sha256(destination) != first["sha256"]:
                raise RuntimeError("published wheel digest changed")
            report["published_wheel"] = str(destination)
        report["status"] = "passed"
        return report
    finally:
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if worktree.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=ROOT,
                check=False,
                capture_output=True,
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Run detached, reproducible ALB {VERSION} source and wheel "
            "acceptance."
        )
    )
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--publish", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run_acceptance(args.candidate, publish=args.publish)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
