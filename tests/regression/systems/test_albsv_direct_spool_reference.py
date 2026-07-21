"""Exact regression for the ALBSV direct-spool 0.2 adapter."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ALB.config.system import NodimALBConfig
from ALB.contracts import BearingInput, ValveOutput
from ALB.systems.alb import DirectSpoolBearingBlock, DirectSpoolBearingInput
from ALB.systems.alb.assembly import nodim_alb


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs" / "albsv_direct_spool_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs" / "albsv_direct_spool_reference_v1.npz"


@pytest.mark.parametrize("case_id", ["zero", "nonzero", "reversed"])
def test_direct_spool_adapter_replays_frozen_numerics_exactly(case_id):
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    config = NodimALBConfig.from_dict(metadata["config"])
    model = nodim_alb(config, thermal_config=config.thermal_config)
    model.init()
    bearing_data = metadata["bearing_input"]
    spool = metadata["spool_cases"][case_id]
    block = DirectSpoolBearingBlock(model)
    dto = DirectSpoolBearingInput(
        BearingInput(
            bearing_data["displacement"],
            bearing_data["velocity"],
            bearing_data["time"],
            "nondimensional",
        ),
        ValveOutput(spool, bearing_data["time"], "nondimensional"),
    )

    result = block.step(dto)
    thermal = [pad._last_thermal for pad in model.pads]
    actual = {
        "input.displacement": dto.bearing.displacement,
        "input.velocity": dto.bearing.velocity,
        "input.spool": dto.spool.spool,
        "output.force": result.force,
        "output.servovalve_spool": np.asarray(
            [servovalve.xv for servovalve in model.servovalves], dtype=float
        ),
        "thermal.t_eff": np.asarray(
            [item["t_eff"] for item in thermal], dtype=float
        ),
        "thermal.viscosity": np.asarray(
            [item["viscosity"] for item in thermal], dtype=float
        ),
        "thermal.iterations": np.asarray(
            [item["iterations"] for item in thermal], dtype=np.int64
        ),
        "thermal.viscosity_fields": np.vstack(
            [np.asarray(item["viscosity_field"], dtype=float) for item in thermal]
        ),
    }
    with np.load(REFERENCE_NPZ, allow_pickle=False) as frozen:
        for name, value in actual.items():
            np.testing.assert_array_equal(value, frozen[f"{case_id}.{name}"])

    expected_status = metadata["status"][case_id]
    assert block.convergence_status.converged is True
    assert bool(model.calc_is_finished()) is True
    assert [bool(item["converged"]) for item in thermal] == expected_status[
        "thermal_converged_by_pad"
    ]


@pytest.mark.parametrize("case_id", ["zero", "nonzero", "reversed"])
def test_direct_spool_completion_snapshot_and_status_are_read_only(case_id):
    reference_json = ROOT / "refs" / "albsv_convergence_state_reference_v2.json"
    reference_npz = ROOT / "refs" / "albsv_convergence_state_reference_v2.npz"
    metadata = json.loads(reference_json.read_text(encoding="utf-8"))
    source = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    config = NodimALBConfig.from_dict(source["config"])
    model = nodim_alb(config, thermal_config=config.thermal_config)
    model.init()
    bearing_data = source["bearing_input"]
    block = DirectSpoolBearingBlock(model)
    result = block.step(
        DirectSpoolBearingInput(
            BearingInput(
                bearing_data["displacement"],
                bearing_data["velocity"],
                bearing_data["time"],
                "nondimensional",
            ),
            ValveOutput(
                source["spool_cases"][case_id],
                bearing_data["time"],
                "nondimensional",
            ),
        )
    )
    pressure = np.vstack(
        [
            np.asarray(pad.bearing.main_model.latest_result, dtype=float).copy()
            for pad in model.pads
        ]
    )
    histories_before = [
        list(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads
    ]

    assert model.calc_is_finished() is True
    assert model.calc_is_finished() is True
    histories_after = [
        list(pad.bearing.main_model.adaptive_damp_history) for pad in model.pads
    ]

    with np.load(reference_npz, allow_pickle=False) as frozen:
        np.testing.assert_array_equal(result.force, frozen[f"{case_id}.force"])
        np.testing.assert_array_equal(
            pressure, frozen[f"{case_id}.pressure_at_completion"]
        )
    assert histories_after == histories_before
    assert metadata["cases"][case_id]["expected_status_after_fix"] is True
