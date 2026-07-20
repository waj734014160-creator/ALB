"""Capture the pre-refactor pytest node inventory and migration destinations.

Run this script before adding any 0.2.0 tests.  It records every collected
node so later test moves cannot silently drop coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "refs"
    / "full_repo_refactor_v1"
    / "test_node_migration_map.json"
)


def _git_head() -> str:
    """Return the commit whose test collection is being captured."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _collect_nodeids() -> tuple[list[str], str, str]:
    """Collect node ids without creating pytest cache artifacts."""

    command = [
        sys.executable,
        "-m",
        "pytest",
        "test",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode not in (0, 5):
        raise RuntimeError(
            "pytest collection failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    nodeids = sorted(
        {
            line.strip().replace("\\", "/")
            for line in result.stdout.splitlines()
            if "::" in line and not line.lstrip().startswith("<")
        }
    )
    return nodeids, result.stdout, result.stderr


def _target_category(source_path: str) -> tuple[str, str]:
    """Return the planned test class and a short migration rationale."""

    path = source_path.lower()
    name = Path(path).name
    if (
        "reference" in name
        or "equivalence" in name
        or "nodim_thermal_field" in name
        or "thermal_kc_compare" in name
        or "thermal_force_time_term_compare" in name
        or "harmonic_linear" in name
    ):
        return "regression", "Exact or numerical behavior baseline."
    if (
        "validation" in path
        or "gas_bearing" in name
        or "tilting_pad" in name
        or "thermal_wrapper.py" in path
        or "coe_boundary_fullpad" in name
    ):
        return "validation", "Engineering or physical validation coverage."
    if (
        "/remote/" in path
        or "adaptive_damp_integration" in name
        or "alb_gui_tool" in name
        or "train_packaging" in name
        or "train_wrapper" in name
        or "task.py" in name
    ):
        return "integration", "Cross-module or optional-system behavior."
    return "unit", "Deterministic module-level behavior."


def _is_manual_plot_node(nodeid: str) -> bool:
    """Identify collected nodes whose only durable purpose is plot generation."""

    return nodeid.endswith(
        (
            "::TestALBThermal::test_alb_thermal_plots",
            "::TestThermalHydroBearing::test_comparison_plot",
            "::TestThermalHydroBearing::test_orifice_plots",
        )
    )


def _writes_artifacts(nodeid: str) -> bool:
    """Mark legacy nodes that write images or other repository artifacts."""

    tokens = (
        "test_gas_bearing_solver_produces_physical_pressure",
        "test_textured_foil_bearing_matches_paper_trend",
        "test_alb_thermal_plots",
        "test_comparison_plot",
        "test_orifice_plots",
        "test_window_dynamic_result_updates_text_and_plots",
        "test_window_static_result_updates_text_and_plots",
    )
    return any(token in nodeid for token in tokens)


def _required_extra(source_path: str) -> str:
    """Return the planned optional-dependency group for a test path."""

    path = source_path.lower()
    if "/remote/" in path:
        return "remote"
    if "/train/" in path or "albnn" in path:
        return "surrogate"
    if "/control/" in path or "rotor" in path:
        return "control"
    if "gui" in path:
        return "gui"
    if any(token in path for token in ("thermal", "gas_bearing", "skfem")):
        return "thermal"
    return "core"


def _reference_artifacts(source_path: str) -> list[str]:
    """Return reference files that protect a baseline test family."""

    path = source_path.lower()
    refs = []
    if "interface_contract_reference" in path:
        refs.extend(
            [
                "refs/interface_contract_reference_v1.json",
                "refs/interface_contract_reference_v1.npz",
            ]
        )
    if "servo_config_reference" in path:
        refs.extend(
            [
                "refs/servo_config_reference_v1.json",
                "refs/servo_config_reference_v1.npz",
            ]
        )
    if "time_grid_config" in path:
        refs.append("refs/task_time_config_reference_v1.json")
    if "thermal_segregated_newton" in path:
        refs.extend(
            [
                "refs/thermal_segregated_newton_reference_v1.json",
                "refs/thermal_segregated_newton_reference_v1.npz",
            ]
        )
    if "thermal_reference_snapshot" in path:
        refs.extend(
            [
                "refs/thermal_small_model_reference_v1.json",
                "refs/thermal_small_model_reference_v1.npz",
            ]
        )
    if "/remote/" in path:
        refs.append("refs/full_repo_refactor_v1/remote_persistence.npz")
    if "/train/" in path:
        refs.extend(
            [
                "refs/alb_train_reference_v1.json",
                "refs/alb_train_reference_v1.npz",
            ]
        )
    return refs


def _mapping(nodeid: str) -> dict[str, object]:
    """Build one explicit old-to-new node mapping entry."""

    source_path, *suffix = nodeid.split("::")
    category, rationale = _target_category(source_path)
    relative = source_path.removeprefix("test/")
    target_path = f"tests/{category}/{relative}"
    target_nodeid = "::".join([target_path, *suffix])
    disposition = "validation" if category == "validation" else "migrate"
    replacement_nodeids = [target_nodeid]
    manual_companion = None
    if _is_manual_plot_node(nodeid):
        category = "manual"
        disposition = "manual"
        target_path = f"tools/manual/legacy_tests/{relative}"
        target_nodeid = None
        replacement_nodeids = []
        rationale = "Plot-only node becomes an explicit manual visualization tool."
    elif (
        "test_gas_bearing_solver_produces_physical_pressure" in nodeid
        or "test_textured_foil_bearing_matches_paper_trend" in nodeid
    ):
        manual_companion = "tools/manual/gas/render_gas_bearing_pressure.py"
        rationale += " Plot writing is split into a manual companion."
    return {
        "baseline_nodeid": nodeid,
        "source_path": source_path,
        "target_category": category,
        "target_path": target_path,
        "target_nodeid": target_nodeid,
        "replacement_nodeids": replacement_nodeids,
        "manual_companion": manual_companion,
        "disposition": disposition,
        "status": "planned",
        "rationale": rationale,
        "reference_artifacts": _reference_artifacts(source_path),
        "array_keys": [],
        "required_extra": _required_extra(source_path),
        "writes_artifacts": _writes_artifacts(nodeid),
        "verification_status": "pending",
        "verification_commit": None,
    }


def _non_collected_python_files(collected_paths: set[str]) -> list[dict[str, str]]:
    """Inventory tracked legacy Python helpers and scripts with no pytest node."""

    result = subprocess.run(
        ["git", "ls-files", "test/*.py", "test/**/*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    files = sorted(
        path.replace("\\", "/")
        for path in result.stdout.splitlines()
        if path.strip() and path.replace("\\", "/") not in collected_paths
    )
    inventory = []
    for source_path in files:
        name = Path(source_path).name.lower()
        if name.startswith("_thermal_") or "diagnos" in name:
            target = f"tools/diagnostics/{source_path.removeprefix('test/')}"
            kind = "diagnostic"
        elif name in {"_split_imports.py", "validation_reference_data.py", "validation_runner.py"}:
            target = f"tests/_support/{source_path.removeprefix('test/')}"
            kind = "test_support"
        else:
            target = f"tools/manual/{source_path.removeprefix('test/')}"
            kind = "manual"
        inventory.append(
            {
                "source_path": source_path,
                "target_path": target,
                "disposition": kind,
                "status": "planned",
                "rationale": "Tracked Python file produced no baseline pytest node.",
            }
        )
    return inventory


def capture(output: Path, expected_count: int) -> Path:
    """Write the immutable baseline node map, refusing overwrite or drift."""

    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing inventory: {output}")
    nodeids, stdout, stderr = _collect_nodeids()
    if len(nodeids) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} collected nodes, found {len(nodeids)}.\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    digest = hashlib.sha256("\n".join(nodeids).encode("utf-8")).hexdigest()
    collected_paths = {nodeid.split("::", 1)[0] for nodeid in nodeids}
    payload = {
        "schema": "alb.test-node-migration-map.v1",
        "baseline_commit": _git_head(),
        "collection_command": (
            f"{sys.executable} -m pytest test --collect-only -q "
            "-p no:cacheprovider"
        ),
        "python": sys.version.split()[0],
        "pytest": importlib.metadata.version("pytest"),
        "node_count": len(nodeids),
        "nodeids_sha256": digest,
        "policy": (
            "Immutable baseline inventory and initial plan. Every baseline node "
            "must migrate to tests/ or receive an explicit manual/validation "
            "disposition and rationale. Final actual mappings are recorded in "
            "docs/migrations/0.2.0_test_map.json without overwriting this file."
        ),
        "mappings": [_mapping(nodeid) for nodeid in nodeids],
        "non_collected_python_files": _non_collected_python_files(collected_paths),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    """Run the command-line capture workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-count", type=int, default=242)
    args = parser.parse_args()
    print(capture(args.output.resolve(), args.expected_count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
