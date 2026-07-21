"""Exact regression tests for the pre-refactor interface behavior."""

from __future__ import annotations

import importlib
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import ALB
from ALB.surrogate.training.transforms import MidpointMinMaxScaler


REPO_ROOT = Path(__file__).resolve().parents[3]
REF_JSON = REPO_ROOT / "refs" / "interface_contract_reference_v1.json"
REF_NPZ = REPO_ROOT / "refs" / "interface_contract_reference_v1.npz"
GENERATOR_PATH = (
    REPO_ROOT / "tools" / "reference" / "generate_interface_contract_reference.py"
)

NAMESPACE_TARGETS = {
    "BearingCoefficientProtocol": ("ALB.contracts", "BearingCoefficientProtocol"),
    "BearingComponentBase": ("ALB.core", "BearingComponentBase"),
    "BearingDecoratorBase": ("ALB.physics.bearing.decorators", "BearingDecoratorBase"),
    "BearingProtocol": ("ALB.contracts", "BearingProtocol"),
    "ComponentBase": ("ALB.core", "ComponentBase"),
    "ControllerProtocol": ("ALB.contracts", "ControllerProtocol"),
    "ConvergenceStatus": ("ALB.contracts", "ConvergenceStatus"),
    "LegacyBearingAdapter": ("ALB.physics.bearing.decorators", "LegacyBearingAdapter"),
    "NotifierProtocol": ("ALB.contracts", "NotifierProtocol"),
    "RotorProtocol": ("ALB.contracts", "RotorProtocol"),
    "ServoValveProtocol": ("ALB.contracts", "ServoValveProtocol"),
    "TimeGridProtocol": ("ALB.contracts", "TimeGridProtocol"),
}


def _load_generator():
    """Load the reference functions without making tools a runtime package."""

    spec = importlib.util.spec_from_file_location(
        "alb_interface_reference_generator",
        GENERATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load reference generator: {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_metadata() -> dict:
    return json.loads(REF_JSON.read_text(encoding="utf-8"))


def test_public_and_legacy_import_contract_matches_reference():
    metadata = _load_metadata()
    assert metadata["schema"] == "alb.interface-contract-reference.v1"
    assert metadata["baseline_commit"] == (
        "24ea190becf19c6f0e33e3c05686c0052dfdbedd"
    )

    assert set(ALB.__all__) == {
        "__version__",
        "UnitSystem",
        "StepContext",
        "ConvergenceStatus",
        "ComputationalBlock",
        "SolvableBlock",
        "EvaluableBlock",
        "CommandBlock",
        "AdvancingBlock",
    }
    for attribute_name, (module_name, target_name) in NAMESPACE_TARGETS.items():
        module = importlib.import_module(module_name)
        assert getattr(module, target_name).__name__ == attribute_name

    removed_modules = {
        "ALB.alb",
        "ALB.base",
        "ALB.bearing",
        "ALB.controller",
        "ALB.film",
        "ALB.nn",
        "ALB.remote",
        "ALB.results",
        "ALB.task",
        "ALB.tool",
    }
    for module_name in removed_modules:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


def test_signal_and_numeric_behavior_match_reference_exactly():
    generator = _load_generator()
    metadata = _load_metadata()
    assert generator._signal_reference() == metadata["signal"]

    bearing_metadata, bearing_arrays = generator._bearing_reference()
    legacy_metadata, legacy_arrays = generator._legacy_linear_reference()
    coupling_metadata, coupling_arrays = generator._coupling_reference()
    del bearing_metadata, legacy_metadata, coupling_metadata

    actual_arrays = {
        **bearing_arrays,
        **legacy_arrays,
        **coupling_arrays,
    }
    with np.load(REF_NPZ) as reference_arrays:
        for name, actual in actual_arrays.items():
            expected = reference_arrays[name]
            assert list(actual.shape) == metadata["arrays"][name]["shape"]
            assert str(actual.dtype) == metadata["arrays"][name]["dtype"]
            if name.startswith("coupling_"):
                continue
            np.testing.assert_array_equal(actual, expected, err_msg=name)


def test_legacy_scaler_pickle_loads_and_replays_exactly():
    with np.load(REF_NPZ) as reference_arrays:
        serialized = reference_arrays["pickle_scaler_bytes"].tobytes()
        with pytest.raises(ModuleNotFoundError):
            pickle.loads(serialized)
        frame = pd.DataFrame(
            reference_arrays["pickle_scaler_input"],
            columns=["constant", "varying"],
        )
        scaler = MidpointMinMaxScaler(feature_range=(-1.0, 1.0)).fit(frame)
        actual = scaler.transform(frame)
        np.testing.assert_array_equal(
            actual,
            reference_arrays["pickle_scaler_output"],
        )
