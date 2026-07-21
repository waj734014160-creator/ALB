"""Non-destructive migration tests for ALBNN artifact packages."""

import pickle
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ALB.surrogate.inference import IdentityTargetScaler, SelectiveMinMaxScaler
from ALB.surrogate.migration import migrate_legacy_model_package
from ALB.surrogate.package import load_albnn_package, open_model_package


def _write_legacy_alb_nn_pickle(path, current_object) -> None:
    legacy_module = ModuleType("ALB.nn")
    legacy_type = type(type(current_object).__name__, (), {})
    legacy_type.__module__ = "ALB.nn"
    setattr(legacy_module, legacy_type.__name__, legacy_type)
    legacy_object = legacy_type()
    legacy_object.__dict__.update(current_object.__dict__)
    previous = sys.modules.get("ALB.nn")
    sys.modules["ALB.nn"] = legacy_module
    try:
        with path.open("wb") as stream:
            pickle.dump(legacy_object, stream, protocol=pickle.HIGHEST_PROTOCOL)
    finally:
        if previous is None:
            sys.modules.pop("ALB.nn", None)
        else:
            sys.modules["ALB.nn"] = previous


def _legacy_artifacts(tmp_path):
    model = tmp_path / "legacy.pth"
    input_scaler = tmp_path / "legacy_x.pkl"
    output_scaler = tmp_path / "legacy_y.pkl"
    model.write_bytes(b"model-checkpoint")
    x = pd.DataFrame([[0.0, 2.0], [4.0, 6.0]], columns=["ex", "ey"])
    y = pd.DataFrame([[1.0, -2.0], [3.0, 4.0]], columns=["fx", "fy"])
    current_input = SelectiveMinMaxScaler().fit(x)
    current_output = IdentityTargetScaler().fit(y)
    _write_legacy_alb_nn_pickle(input_scaler, current_input)
    _write_legacy_alb_nn_pickle(output_scaler, current_output)
    return (model, input_scaler, output_scaler), current_input, current_output, x, y


def test_legacy_scalers_are_rewritten_and_sources_remain_unchanged(tmp_path):
    artifacts, current_input, current_output, x, y = _legacy_artifacts(tmp_path)
    model, input_scaler, output_scaler = artifacts
    source_bytes = (
        model.read_bytes(),
        input_scaler.read_bytes(),
        output_scaler.read_bytes(),
    )

    destination = tmp_path / "package"
    migrate_legacy_model_package(
        model,
        input_scaler,
        output_scaler,
        destination,
        trust_legacy_pickle=True,
    )
    package = open_model_package(destination)

    assert (
        model.read_bytes(),
        input_scaler.read_bytes(),
        output_scaler.read_bytes(),
    ) == source_bytes
    assert package.model.read_bytes() == b"model-checkpoint"
    assert b"ALB.nn" not in package.input_scaler.read_bytes()
    assert b"ALB.nn" not in package.output_scaler.read_bytes()
    with package.input_scaler.open("rb") as stream:
        migrated_input = pickle.load(stream)
    with package.output_scaler.open("rb") as stream:
        migrated_output = pickle.load(stream)
    np.testing.assert_array_equal(
        migrated_input.transform(x), current_input.transform(x)
    )
    np.testing.assert_array_equal(
        migrated_input.inverse_transform(current_input.transform(x)),
        current_input.inverse_transform(current_input.transform(x)),
    )
    np.testing.assert_array_equal(
        migrated_output.transform(y), current_output.transform(y)
    )
    np.testing.assert_array_equal(
        migrated_output.inverse_transform(y), current_output.inverse_transform(y)
    )
    with pytest.raises(PermissionError, match="trust_pickle"):
        load_albnn_package(destination)


def test_model_package_migration_requires_explicit_pickle_trust(tmp_path):
    artifacts, *_ = _legacy_artifacts(tmp_path)
    destination = tmp_path / "package"
    with pytest.raises(PermissionError, match="trust_legacy_pickle"):
        migrate_legacy_model_package(*artifacts, destination)
    assert not destination.exists()


def test_model_package_migration_refuses_overwrite(tmp_path):
    artifacts, *_ = _legacy_artifacts(tmp_path)
    destination = tmp_path / "package"
    migrate_legacy_model_package(
        *artifacts, destination, trust_legacy_pickle=True
    )
    with pytest.raises(FileExistsError):
        migrate_legacy_model_package(
            *artifacts, destination, trust_legacy_pickle=True
        )


def test_package_loader_merges_runtime_config_and_owns_artifact_paths(
    tmp_path, monkeypatch
):
    artifacts, *_ = _legacy_artifacts(tmp_path)
    destination = tmp_path / "package"
    migrate_legacy_model_package(
        *artifacts, destination, trust_legacy_pickle=True
    )
    captured = {}

    def fake_albnn(config, *, use_augment=None):
        captured["config"] = config
        captured["use_augment"] = use_augment
        return "loaded"

    import ALB.surrogate.inference as inference

    monkeypatch.setattr(inference, "albnn", fake_albnn)
    result = load_albnn_package(
        destination,
        trust_pickle=True,
        use_augment=False,
        runtime_config=SimpleNamespace(
            ps=7.0,
            model="ignored.pth",
            scaler_X="ignored.pkl",
        ),
    )

    assert result == "loaded"
    assert captured["config"].ps == 7.0
    assert captured["config"].model == str((destination / "model.pt").resolve())
    assert captured["config"].scaler_X == str(
        (destination / "input_scaler.pkl").resolve()
    )
    assert captured["use_augment"] is False
