"""Exact regression tests for the pre-refactor interface behavior."""

from __future__ import annotations

import importlib
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np

import ALB


REPO_ROOT = Path(__file__).resolve().parents[2]
REF_JSON = REPO_ROOT / "refs" / "interface_contract_reference_v1.json"
REF_NPZ = REPO_ROOT / "refs" / "interface_contract_reference_v1.npz"
GENERATOR_PATH = (
    REPO_ROOT / "tools" / "reference" / "generate_interface_contract_reference.py"
)


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

    export_map = ALB.__dict__["_EXPORTS"]
    assert sorted(export_map) == metadata["public_exports"]
    actual_targets = {
        name: {"module": export_map[name][0], "attribute": export_map[name][1]}
        for name in sorted(export_map)
    }
    assert actual_targets == metadata["public_export_targets"]
    assert sorted(ALB.__all__) == metadata["legacy___all__"]
    assert metadata["known_export_drift"] == [
        "FilmNondimScales",
        "build_thermal_config",
    ]

    for module_name, attribute_names in metadata["legacy_import_surface"].items():
        module = importlib.import_module(module_name)
        for attribute_name in attribute_names:
            assert hasattr(module, attribute_name), f"{module_name}.{attribute_name}"


def test_signal_and_numeric_behavior_match_reference_exactly():
    generator = _load_generator()
    metadata = _load_metadata()
    assert generator._signal_reference() == metadata["signal"]

    bearing_metadata, bearing_arrays = generator._bearing_reference()
    legacy_metadata, legacy_arrays = generator._legacy_linear_reference()
    coupling_metadata, coupling_arrays = generator._coupling_reference()
    pickle_metadata, pickle_arrays = generator._pickle_reference()
    assert bearing_metadata == metadata["bearing"]
    assert legacy_metadata == metadata["legacy_linear"]
    assert coupling_metadata == metadata["coupling"]
    assert pickle_metadata == metadata["pickle"]

    actual_arrays = {
        **bearing_arrays,
        **legacy_arrays,
        **coupling_arrays,
        **pickle_arrays,
    }
    with np.load(REF_NPZ) as reference_arrays:
        assert set(actual_arrays) == set(reference_arrays.files)
        for name, actual in actual_arrays.items():
            expected = reference_arrays[name]
            assert list(actual.shape) == metadata["arrays"][name]["shape"]
            assert str(actual.dtype) == metadata["arrays"][name]["dtype"]
            np.testing.assert_array_equal(actual, expected, err_msg=name)


def test_legacy_scaler_pickle_loads_and_replays_exactly():
    with np.load(REF_NPZ) as reference_arrays:
        serialized = reference_arrays["pickle_scaler_bytes"].tobytes()
        scaler = pickle.loads(serialized)
        actual = scaler.transform(reference_arrays["pickle_scaler_input"])
        np.testing.assert_array_equal(
            actual,
            reference_arrays["pickle_scaler_output"],
        )
