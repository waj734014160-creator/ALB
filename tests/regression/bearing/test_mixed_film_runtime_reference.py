"""Exact numerical replay of the mixed-film runtime baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ALB.config import HydConfig, HybridOrificeConfig, NodimPadConfig
from ALB.contracts import BearingInput
from ALB.physics.bearing.solver import (
    _DimensionalMixedFilmRuntime,
    _NondimensionalMixedFilmRuntime,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "mixed_film_composition_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "mixed_film_composition_reference_v1.npz"


def _load_reference() -> tuple[dict[str, Any], Any]:
    payload = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    assert payload["schema"] == "alb.mixed-film-composition-reference.v1"
    assert hashlib.sha256(REFERENCE_NPZ.read_bytes()).hexdigest() == payload[
        "npz_sha256"
    ]
    return payload, np.load(REFERENCE_NPZ, allow_pickle=False)


def _build_runtime(name: str, case: dict[str, Any]) -> Any:
    if name == "nondimensional":
        return _NondimensionalMixedFilmRuntime(
            NodimPadConfig(**case["config"]),
            x0=case["x0"],
        )
    orifices = (
        None
        if case["orifices"] is None
        else HybridOrificeConfig(**case["orifices"])
    )
    return _DimensionalMixedFilmRuntime(
        HydConfig(**case["config"]),
        orifices=orifices,
    )


@pytest.mark.parametrize(
    "name",
    ["dimensional", "dimensional_hybrid", "nondimensional"],
)
def test_mixed_film_runtime_preserves_frozen_numerical_behavior(
    name: str,
) -> None:
    payload, arrays = _load_reference()
    case = payload["cases"][name]
    dto_data = case["dto"]
    runtime = _build_runtime(name, case)
    output = runtime.step(
        BearingInput(
            displacement=dto_data["displacement"],
            velocity=dto_data["velocity"],
            time=dto_data["time"],
            unit_system=dto_data["unit_system"],
        )
    )
    expected = case["outputs"]

    np.testing.assert_array_equal(output.force, arrays[expected["force_array"]])
    np.testing.assert_array_equal(
        runtime.main_model.latest_result,
        arrays[expected["pressure_array"]],
    )
    assert runtime.result_snapshot().values["friction"] == expected["friction"]
    assert runtime.lifecycle_state.value == expected["lifecycle_state"]
    assert runtime.convergence_status.converged is expected["converged"]
    assert runtime.convergence_status.iterations == expected["iterations"]
    assert runtime.final_iter == expected["final_iter"]
    metadata = runtime.result_snapshot().metadata
    assert {
        key: metadata[key] for key in expected["result_metadata"]
    } == expected["result_metadata"]
    assert (
        dict(runtime.diagnostic_snapshot().metadata)
        == expected["diagnostic_metadata"]
    )
