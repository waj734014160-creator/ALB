"""Contract tests for the strict 0.3 configuration envelope."""

from __future__ import annotations

from copy import deepcopy
import json

import numpy as np
import pytest

from ALB.config import (
    ALBConfig,
    ControlMode,
    FuzzyPIDConfig,
    NodimALBConfig,
    ThermalConfig,
    current_config_envelope,
    load_current_config,
    load_current_envelope,
    migrate_legacy_alb_config,
)


@pytest.mark.parametrize(
    "config",
    [
        ALBConfig(controller_config=None),
        ALBConfig(
            controller_config=FuzzyPIDConfig(
                error_range=[-2.0, 2.0, 0.02]
            )
        ),
        NodimALBConfig(),
        NodimALBConfig(
            alb="ALBSV",
            controller_config=None,
        ),
        NodimALBConfig(
            pad_config=NodimALBConfig().pad_config.__class__(
                thermal_config=ThermalConfig(
                    args_nodim=True,
                    beta_nondim=0.03,
                    delta_t_scale=1.0,
                )
            )
        ),
    ],
)
def test_current_schema_round_trip_preserves_type_mode_and_values(config):
    envelope = current_config_envelope(config)
    payload = envelope.to_dict()
    json.dumps(payload)
    restored = load_current_config(payload)

    assert type(restored) is type(config)
    assert type(restored.controller_config) is type(config.controller_config)
    assert restored.to_dict()["controller"] == config.to_dict()["controller"]
    assert np.array_equal(restored.gxy, config.gxy)
    assert np.array_equal(restored.gxyt, config.gxyt)
    assert restored.alb == config.alb
    assert restored.servo == config.servo
    assert load_current_envelope(payload).control_mode is envelope.control_mode


def test_current_loader_rejects_unversioned_and_old_envelopes():
    with pytest.raises((TypeError, ValueError), match="config"):
        load_current_config({"kp": 1.0, "servo": "moog_2nd"})
    with pytest.raises(ValueError, match="0.3.0"):
        load_current_envelope(
            {
                "schema_version": "0.2.0",
                "kind": "alb",
                "unit_system": "dimensional",
                "control_mode": "controlled",
                "config": {},
            }
        )


def test_legacy_migration_is_non_mutating_one_way_and_auditable():
    legacy = {"kp": 0.4, "ki": 0.0, "kd": 0.1, "servo": "moog_2nd"}
    original = deepcopy(legacy)

    envelope, report = migrate_legacy_alb_config(legacy)

    assert legacy == original
    assert report.source_schema == "legacy-flat"
    assert report.target_schema == "0.3.0"
    assert report.control_mode == "controlled"
    assert len(report.source_sha256) == 64
    assert load_current_config(envelope.to_dict()).controller_config.kp == 0.4
    with pytest.raises(ValueError, match="one-way"):
        migrate_legacy_alb_config(envelope.to_dict())


def test_current_schema_rejects_unknown_envelope_and_nested_fields():
    payload = current_config_envelope(ALBConfig()).to_dict()
    payload["legacy_override"] = True
    with pytest.raises(ValueError, match="unknown"):
        load_current_envelope(payload)

    payload = current_config_envelope(ALBConfig()).to_dict()
    payload["config"]["pad_config"]["unknown_current_field"] = 1
    with pytest.raises(ValueError, match="unknown pad_config"):
        load_current_envelope(payload)


@pytest.mark.parametrize(
    ("mode", "alb", "controller"),
    [
        (ControlMode.DIRECT_SPOOL, "ALB", "none"),
        (ControlMode.NONE, "ALBSV", "none"),
        (ControlMode.CONTROLLED, "ALB", "none"),
    ],
)
def test_control_mode_conflicts_fail_instead_of_guessing(mode, alb, controller):
    config = ALBConfig(
        alb=alb,
        controller_config=None,
    )
    payload = current_config_envelope(
        ALBConfig(controller_config=None),
        control_mode=ControlMode.NONE,
    ).to_dict()
    payload["control_mode"] = mode.value
    payload["config"]["alb"] = alb
    payload["config"]["controller"] = controller
    payload["config"]["controller_config"] = None

    with pytest.raises(ValueError, match="control_mode|controlled"):
        load_current_envelope(payload)


def test_gain_matrices_reject_complex_nonfinite_and_wrong_shapes():
    with pytest.raises(TypeError, match="gxy"):
        ALBConfig(gxy=np.asarray([[1.0 + 1.0j, 0.0], [0.0, 1.0]]))
    with pytest.raises(ValueError, match="gxyt"):
        NodimALBConfig(gxyt=np.asarray([[np.inf, 0.0], [0.0, 1.0]]))
    with pytest.raises(ValueError, match="shape"):
        ALBConfig(gxy=np.eye(3))


def test_current_envelope_is_recursively_immutable_and_revalidates_materialization():
    envelope = current_config_envelope(ALBConfig())

    with pytest.raises(TypeError):
        envelope.config["pad_config"]["n_pad"] = 99
    with pytest.raises(TypeError):
        envelope.config["controller_config"]["kp"] = 99.0
    with pytest.raises((TypeError, ValueError)):
        envelope.config["gxy"][0][0] = 99.0

    mutable = envelope.to_dict()["config"]
    mutable["pad_config"]["unknown_after_validation"] = True
    object.__setattr__(envelope, "config", mutable)
    from ALB.config import materialize_current_config

    with pytest.raises(ValueError, match="unknown pad_config"):
        materialize_current_config(envelope)
