"""End-to-end current config file to initialized bearing runtime tests."""

from __future__ import annotations

import json

from ALB.config import ControlMode, NodimALBConfig
from ALB.config.schema import _current_config_envelope
from ALB.contracts import BearingInput, DirectSpoolBearingInput, ValveOutput
from ALB.systems.alb import (
    BuiltDirectSpoolBearing,
    BuiltUncontrolledBearing,
)
from ALB.workflows import build_alb_from_file


def _config(mode: ControlMode) -> NodimALBConfig:
    return NodimALBConfig.from_dict(
        {
            "alb": "ALBSV" if mode is ControlMode.DIRECT_SPOOL else "ALB",
            "controller": "none",
            "controller_config": None,
            "servo": "static",
            "switch": False,
            "node_link": 2,
            "nx": 15,
            "nz": 7,
            "lx": 80.0,
            "lz": 2.0,
            "lambda_value": 1.2,
            "lr": 1.0,
            "position": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "cq0": 6.0557,
            "cq1": 0.02313,
            "cq2": 0.002173,
            "ps": 1.0,
            "p0": 0.0,
        }
    )


def test_current_standard_file_build_init_and_step(tmp_path):
    envelope = _current_config_envelope(
        _config(ControlMode.NONE),
        control_mode=ControlMode.NONE,
    )
    path = tmp_path / "alb-none.json5"
    path.write_text(json.dumps(envelope.to_dict()), encoding="utf-8")

    built = build_alb_from_file(path)
    assert built.runtime.lifecycle_state.value == "ready"
    output = built.runtime.step(
        BearingInput(
            [0.1, -0.2],
            [0.03, -0.04],
            0.0,
            "nondimensional",
        )
    )

    assert isinstance(built, BuiltUncontrolledBearing)
    assert built.control_mode is ControlMode.NONE
    assert output.force.shape == (2,)


def test_current_direct_spool_file_build_init_and_step(tmp_path):
    envelope = _current_config_envelope(
        _config(ControlMode.DIRECT_SPOOL),
        control_mode=ControlMode.DIRECT_SPOOL,
    )
    path = tmp_path / "alb-direct.json5"
    path.write_text(json.dumps(envelope.to_dict()), encoding="utf-8")

    built = build_alb_from_file(path)
    assert built.runtime.lifecycle_state.value == "ready"
    output = built.runtime.step(
        DirectSpoolBearingInput(
            BearingInput(
                [0.1, -0.2],
                [0.03, -0.04],
                0.0,
                "nondimensional",
            ),
            ValveOutput([0.2, -0.3], 0.0, "nondimensional"),
        )
    )

    assert isinstance(built, BuiltDirectSpoolBearing)
    assert built.control_mode is ControlMode.DIRECT_SPOOL
    assert output.force.shape == (2,)


def test_file_builder_rejects_legacy_with_migration_command(tmp_path):
    path = tmp_path / "legacy.json5"
    path.write_text("{kp: 0.3, alb: 'ALB'}", encoding="utf-8")

    try:
        build_alb_from_file(path)
    except ValueError as exc:
        assert "alb-migrate-config" in str(exc)
    else:
        raise AssertionError("legacy files must not be parsed by the runtime builder")
