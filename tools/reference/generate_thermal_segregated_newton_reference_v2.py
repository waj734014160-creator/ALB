"""Generate the corrected, self-contained thermal Newton v2 reference.

The v1 snapshot intentionally remains immutable.  This generator corrects the
local nondimensional Reynolds bearing-number construction and embeds the
three S0011 diagnostic inputs plus their effective ALB configuration so the
regression no longer depends on live PAPER_WORK or SURROGATE_TRAIN files.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ALB.config import ALBConfig, HydConfig, ThermalConfig
from ALB.infrastructure.config_io import read_json5_with_shared
from ALB.physics.bearing import HydrostaticBearing, NodimHydrostaticBearing
from ALB.physics.thermal import (
    FilmNondimScales,
    NodimThermalHydroBearing,
    ThermalHydroBearing,
)
from ALB.systems.alb import alb2


V1_JSON = ROOT / "refs" / "thermal_segregated_newton_reference_v1.json"
DEFAULT_OUTPUT_JSON = (
    ROOT / "refs" / "thermal_segregated_newton_reference_v2.json"
)
DEFAULT_OUTPUT_NPZ = ROOT / "refs" / "thermal_segregated_newton_reference_v2.npz"
DEFAULT_PAPER_CONFIG = Path(
    "F:/BaiduSyncdisk/博士论文/PAPER_WORK/task/PAPER/config/alb12.json5"
)
DEFAULT_S0011_CSV = (
    ROOT.parent
    / "SURROGATE_TRAIN"
    / "outputs"
    / "alb_data2"
    / "S0011_alb_data2_exey0to0p9_200000_seed20260607_20260607"
    / "alb_data2_results_n200000_seed20260607.csv"
)
DEFAULT_S0011_METADATA = DEFAULT_S0011_CSV.with_name(
    "alb_data2_results_n200000_seed20260607_metadata.json"
)


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    """Return the source commit used to generate the reference."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _build_nondim_pad(config: HydConfig) -> NodimHydrostaticBearing:
    """Build a pad with the production 1.5 Reynolds bearing-number scale."""
    scales = FilmNondimScales.from_dimensional(
        w=config.w,
        miu=config.miu,
        c=config.c,
        r=config.r,
        l=config.l,
        ps=config.ps,
        rho=config.rho,
        vf=config.vf,
    )
    return NodimHydrostaticBearing(
        lambda_value=scales.lambda_value,
        lr=scales.lr,
        x0=config.x0,
        lx=config.lx,
        lz=config.lz,
        nx=config.nx,
        nz=config.nz,
        e=config.e,
        angle=config.angle_rad,
        coe=config.coe,
        p_set=config.p_set,
        reynold=config.reynold,
        max_iter=config.max_iter,
        error_set=config.error_set,
        damp=config.damp,
        miu=config.miu,
        c=config.c,
        r=config.r,
        l=config.l,
        ps=config.ps,
        rho=config.rho,
        w=config.w,
    )


def _run_dimensional(case: dict[str, Any]) -> dict[str, np.ndarray]:
    """Run the dimensional local fixed-point case."""
    config = HydConfig.from_dict(case["hyd_config"])
    thermal_config = ThermalConfig.from_dict(case["thermal_config"])
    model = ThermalHydroBearing(HydrostaticBearing(config), thermal_config)
    model.init()
    model.input(
        np.asarray(case["input"]["uxy"], dtype=float),
        np.asarray(case["input"]["uxyt"], dtype=float),
    )
    output = model.output(calc=True, nodim=True)
    return {
        "dim_small_fixed_point.force": np.asarray(output["force"], dtype=np.float64),
        "dim_small_fixed_point.friction": np.asarray(
            [output["friction"]], dtype=np.float64
        ),
        "dim_small_fixed_point.pressure_field": np.asarray(
            output["pressure_field"], dtype=np.float64
        ),
        "dim_small_fixed_point.temperature_field": np.asarray(
            output["temperature_field"], dtype=np.float64
        ),
        "dim_small_fixed_point.temperature_film": np.asarray(
            output["temperature_film"], dtype=np.float64
        ),
        "dim_small_fixed_point.viscosity_field": np.asarray(
            output["viscosity_field"], dtype=np.float64
        ),
        "dim_small_fixed_point.thermal_iterations": np.asarray(
            [output["thermal_iterations"]], dtype=np.int64
        ),
        "dim_small_fixed_point.thermal_converged": np.asarray(
            [bool(output["thermal_converged"])], dtype=np.bool_
        ),
    }


def _run_nondimensional(case: dict[str, Any]) -> dict[str, np.ndarray]:
    """Run the local nondimensional case with the corrected scale."""
    config = HydConfig.from_dict(case["hyd_config"])
    thermal_config = ThermalConfig.from_dict(case["thermal_config"])
    model = NodimThermalHydroBearing(_build_nondim_pad(config), thermal_config)
    model.init()
    model.input(
        np.asarray(case["input"]["uxy"], dtype=float),
        np.asarray(case["input"]["uxyt"], dtype=float),
    )
    output = model.output(calc=True, nodim=True)
    return {
        "nondim_small_fixed_point.force": np.asarray(
            output["force"], dtype=np.float64
        ),
        "nondim_small_fixed_point.temperature_nondim": np.asarray(
            output["temperature_nondim"], dtype=np.float64
        ),
        "nondim_small_fixed_point.temperature_field": np.asarray(
            output["temperature_field"], dtype=np.float64
        ),
        "nondim_small_fixed_point.viscosity_field_grid": np.asarray(
            output["viscosity_field_grid"], dtype=np.float64
        ),
        "nondim_small_fixed_point.beta_nondim": np.asarray(
            [output["beta_nondim"]], dtype=np.float64
        ),
        "nondim_small_fixed_point.thermal_iterations": np.asarray(
            [output["thermal_iterations"]], dtype=np.int64
        ),
        "nondim_small_fixed_point.thermal_converged": np.asarray(
            [bool(output["thermal_converged"])], dtype=np.bool_
        ),
    }


def _pad_summaries(model: Any) -> list[dict[str, Any]]:
    """Collect deterministic per-pad convergence and field summaries."""
    summaries = []
    for pad in model.pads:
        state = pad.thermal_state
        temperature = np.asarray(pad.post_process.temperature_field, dtype=float)
        viscosity = np.asarray(pad.post_process.viscosity_field, dtype=float)
        summaries.append(
            {
                "pad": len(summaries),
                "thermal_converged": bool(state.get("converged", False)),
                "thermal_iterations": int(state.get("iterations", 0)),
                "t_eff": float(np.nanmean(temperature)),
                "viscosity": float(np.nanmean(viscosity)),
                "temperature_min": float(np.nanmin(temperature)),
                "temperature_mean": float(np.nanmean(temperature)),
                "temperature_max": float(np.nanmax(temperature)),
                "viscosity_min": float(np.nanmin(viscosity)),
                "viscosity_mean": float(np.nanmean(viscosity)),
                "viscosity_max": float(np.nanmax(viscosity)),
            }
        )
    return summaries


def _effective_s0011_config(path: Path) -> dict[str, Any]:
    """Resolve and freeze the effective S0011 diagnostic configuration."""
    config = read_json5_with_shared(str(path))
    thermal = config.setdefault("thermal", {})
    thermal["iter_method"] = "direct"
    thermal["supg"] = True
    thermal["miu_min"] = 1e-4
    thermal["max_delta_t"] = 80.0
    thermal["miu_update"] = "linear"
    thermal.pop("miu_update_max_ratio", None)
    thermal.pop("heat_partition_steps", None)
    return config


def _run_s0011(
    case: dict[str, Any], base_config: dict[str, Any]
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Run the embedded S0011 inputs without reading the external CSV."""
    force_scale = float(case["derived"]["force_scale"])
    arrays: dict[str, np.ndarray] = {}
    records: list[dict[str, Any]] = []
    for source_record in case["records"]:
        record = copy.deepcopy(source_record)
        sample = record["input"]
        config = copy.deepcopy(base_config)
        config["freq"] = float(sample["freq"])
        config["alb"] = "ALBSV"
        config["servo"] = "static"
        config["switch"] = False
        model = alb2(ALBConfig.from_dict(config))
        model.init()
        model.input(
            uxy=np.asarray([sample["ex"], sample["ey"]], dtype=float),
            uxyt=np.asarray([sample["vx"], sample["vy"]], dtype=float),
            t=0.0,
            sv=np.asarray([sample["sx"], sample["sy"]], dtype=float),
            nodim=True,
        )
        captured_warnings: list[warnings.WarningMessage]
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings(
            record=True
        ) as captured_warnings:
            warnings.simplefilter("always")
            output = model.output(nodim=False)
        force_dim = np.asarray(output["force"], dtype=np.float64)
        force = force_dim / force_scale
        pad_summaries = _pad_summaries(model)
        sample_id = int(record["sample_id"])
        prefix = f"s0011_diagnostic_fixed_point.sample_{sample_id}"
        arrays[f"{prefix}.force"] = force
        arrays[f"{prefix}.force_dim"] = force_dim
        arrays[f"{prefix}.thermal_iterations_by_pad"] = np.asarray(
            [item["thermal_iterations"] for item in pad_summaries], dtype=np.int64
        )
        arrays[f"{prefix}.thermal_converged_by_pad"] = np.asarray(
            [item["thermal_converged"] for item in pad_summaries], dtype=np.bool_
        )
        arrays[f"{prefix}.temperature_summary"] = np.asarray(
            [
                [
                    item["temperature_min"],
                    item["temperature_mean"],
                    item["temperature_max"],
                ]
                for item in pad_summaries
            ],
            dtype=np.float64,
        )
        arrays[f"{prefix}.viscosity_summary"] = np.asarray(
            [
                [
                    item["viscosity_min"],
                    item["viscosity_mean"],
                    item["viscosity_max"],
                ]
                for item in pad_summaries
            ],
            dtype=np.float64,
        )
        record.update(
            {
                "force": force.tolist(),
                "force_dim": force_dim.tolist(),
                "force_norm": float(np.linalg.norm(force)),
                "hydro_converged": bool(output.get("hydro_converged", True)),
                "thermal_converged": bool(
                    all(item["thermal_converged"] for item in pad_summaries)
                ),
                "thermal_iterations": int(
                    max(item["thermal_iterations"] for item in pad_summaries)
                ),
                "pad_thermal_flags": [
                    item["thermal_converged"] for item in pad_summaries
                ],
                "pad_summaries": pad_summaries,
                "warning_count": len(captured_warnings),
                "warning_summary": [str(item.message) for item in captured_warnings],
            }
        )
        records.append(record)
    return arrays, records


def _update_case_summaries(
    metadata: dict[str, Any], arrays: dict[str, np.ndarray]
) -> None:
    """Synchronize compact JSON summaries with the generated arrays."""
    dim_summary = metadata["cases"]["dim_small_fixed_point"]["summary"]
    dim_summary.update(
        {
            "force": arrays["dim_small_fixed_point.force"].tolist(),
            "friction": float(arrays["dim_small_fixed_point.friction"][0]),
            "thermal_iterations": int(
                arrays["dim_small_fixed_point.thermal_iterations"][0]
            ),
            "thermal_converged": bool(
                arrays["dim_small_fixed_point.thermal_converged"][0]
            ),
        }
    )
    nondim_summary = metadata["cases"]["nondim_small_fixed_point"]["summary"]
    nondim_summary.update(
        {
            "force": arrays["nondim_small_fixed_point.force"].tolist(),
            "beta_nondim": float(
                arrays["nondim_small_fixed_point.beta_nondim"][0]
            ),
            "thermal_iterations": int(
                arrays["nondim_small_fixed_point.thermal_iterations"][0]
            ),
            "thermal_converged": bool(
                arrays["nondim_small_fixed_point.thermal_converged"][0]
            ),
        }
    )


def generate(
    output_json: Path,
    output_npz: Path,
    paper_config: Path,
    s0011_csv: Path,
    s0011_metadata: Path,
) -> None:
    """Generate both v2 files while refusing to overwrite prior evidence."""
    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite existing reference: {output}")
    share_config = paper_config.with_name("share.json5")
    for source in (V1_JSON, paper_config, share_config, s0011_csv, s0011_metadata):
        if not source.exists():
            raise FileNotFoundError(source)

    started = time.perf_counter()
    v1 = json.loads(V1_JSON.read_text(encoding="utf-8"))
    s0011_v1 = v1["cases"]["s0011_diagnostic_fixed_point"]
    source_metadata = json.loads(s0011_metadata.read_text(encoding="utf-8"))
    config_sha256 = _sha256(paper_config)
    replay_share_sha256 = _sha256(share_config)
    csv_sha256 = _sha256(s0011_csv)
    if config_sha256 != s0011_v1["config_sha256"]:
        raise RuntimeError("The relocated S0011 config no longer matches the v1 source")
    if csv_sha256 != s0011_v1["csv_sha256"]:
        raise RuntimeError("The S0011 CSV no longer matches the v1 source")
    historical_share_sha256 = source_metadata["config_hashes"]["share_json5"]

    metadata = copy.deepcopy(v1)
    metadata.update(
        {
            "reference_name": "thermal_segregated_newton_reference_v2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_before_test_fix": True,
            "baseline_commit": _git_head(),
            "corrective_scope": {
                "nondim_lambda": (
                    "Use 1.5 * miu * omega * l**2 / (ps * c**2), matching "
                    "FilmNondimScales and film_args_trans."
                ),
                "s0011": (
                    "Reuse the hash-matched historical inputs with the current "
                    "PAPER_WORK shared config, then embed the effective config for "
                    "self-contained tests. This is a current-code replay, not an "
                    "exact reconstruction of the missing historical share.json5."
                ),
            },
            "source_reference": V1_JSON.relative_to(ROOT).as_posix(),
            "random_seed": None,
        }
    )
    metadata.pop("created_before_solver_change", None)

    dim_case = metadata["cases"]["dim_small_fixed_point"]
    nondim_case = metadata["cases"]["nondim_small_fixed_point"]
    arrays = _run_dimensional(dim_case)
    arrays.update(_run_nondimensional(nondim_case))

    base_config = _effective_s0011_config(paper_config)
    s0011_arrays, s0011_records = _run_s0011(s0011_v1, base_config)
    arrays.update(s0011_arrays)
    s0011_case = metadata["cases"]["s0011_diagnostic_fixed_point"]
    s0011_case.update(
        {
            "config_path": paper_config.as_posix(),
            "csv_path": s0011_csv.relative_to(ROOT.parent).as_posix(),
            "config_sha256": config_sha256,
            "csv_sha256": csv_sha256,
            "config_provenance": {
                "historical_alb12_sha256": source_metadata["config_hashes"][
                    "alb12_json5"
                ],
                "replay_alb12_sha256": config_sha256,
                "historical_share_sha256": historical_share_sha256,
                "replay_share_sha256": replay_share_sha256,
                "historical_share_available": (
                    historical_share_sha256 == replay_share_sha256
                ),
                "policy": (
                    "The historical share.json5 is unavailable. The v2 arrays freeze "
                    "the embedded current effective config and must not be described "
                    "as an exact replay of the original S0011 configuration."
                ),
            },
            "effective_base_config": base_config,
            "records": s0011_records,
        }
    )
    _update_case_summaries(metadata, arrays)
    metadata["array_names"] = {
        name: list(array.shape) for name, array in arrays.items()
    }
    metadata["elapsed_s"] = time.perf_counter() - started

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    np.savez(output_npz, **arrays)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_npz}")


def main() -> None:
    """Parse CLI arguments and generate the v2 reference bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_OUTPUT_NPZ)
    parser.add_argument("--paper-config", type=Path, default=DEFAULT_PAPER_CONFIG)
    parser.add_argument("--s0011-csv", type=Path, default=DEFAULT_S0011_CSV)
    parser.add_argument(
        "--s0011-metadata", type=Path, default=DEFAULT_S0011_METADATA
    )
    args = parser.parse_args()
    generate(
        args.output_json,
        args.output_npz,
        args.paper_config,
        args.s0011_csv,
        args.s0011_metadata,
    )


if __name__ == "__main__":
    main()
