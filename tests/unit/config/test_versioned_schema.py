"""Contract tests for versioned current configuration and one-way migration."""

from __future__ import annotations

from copy import deepcopy

import pytest

from ALB.config import (
    ALBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    current_config_envelope,
    load_current_config,
    migrate_legacy_alb_config,
)


@pytest.mark.parametrize(
    "config",
    [
        ALBConfig(controller_config=None),
        ALBConfig(controller_config=FuzzyPIDConfig(error_range=[-2.0, 2.0, 0.02])),
        NodimALBConfig(),
    ],
)
def test_current_schema_round_trip_preserves_model_and_controller_type(config):
    envelope = current_config_envelope(config)
    restored = load_current_config(envelope.to_dict())

    assert type(restored) is type(config)
    assert type(restored.controller_config) is type(config.controller_config)
    assert restored.to_dict()["controller"] == config.to_dict()["controller"]
    if isinstance(config.controller_config, FuzzyPIDConfig):
        assert restored.controller_config.error_range == [-2.0, 2.0, 0.02]
    assert restored.alb == config.alb
    assert restored.servo == config.servo


def test_current_loader_rejects_unversioned_flat_payload():
    with pytest.raises((TypeError, ValueError), match="config"):
        load_current_config({"kp": 1.0, "servo": "moog_2nd"})


def test_legacy_migration_is_non_mutating_and_one_way():
    legacy = {"kp": 0.4, "ki": 0.0, "kd": 0.1, "servo": "moog_2nd"}
    original = deepcopy(legacy)

    envelope, report = migrate_legacy_alb_config(legacy)

    assert legacy == original
    assert report.source_schema == "legacy-flat"
    assert report.target_schema == "0.2.0"
    assert load_current_config(envelope.to_dict()).controller_config.kp == 0.4
    with pytest.raises(ValueError, match="one-way"):
        migrate_legacy_alb_config(envelope.to_dict())


def test_current_schema_rejects_unknown_envelope_fields():
    payload = current_config_envelope(ALBConfig()).to_dict()
    payload["legacy_override"] = True
    with pytest.raises(ValueError, match="unknown"):
        load_current_config(payload)
