"""Exact regression contracts for surrogate-builder inference symmetry.

``refs/surrogate_c4_builder_reference_v1`` was frozen from the builder before
``model_package.symmetry`` existed. The bare forces it records must remain
reproducible (``symmetry: "none"`` and full-plane packages), and the new
``symmetry: "c4"`` path must equal the pre-existing ``ALBNNC4Canonical``
wrapper exactly at negative-quadrant points.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")

import ALB
from tools.reference.generate_surrogate_c4_builder_reference_v1 import (
    REAL_PARAMETERS,
    SYNTHETIC_PARAMETERS,
    build_synthetic_package,
    builder_forces,
    wrapper_forces,
)


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_JSON = ROOT / "refs/surrogate_c4_builder_reference_v1.json"
REFERENCE_NPZ = ROOT / "refs/surrogate_c4_builder_reference_v1.npz"
UNIT_SYSTEMS = (("nondimensional", "nondim"), ("dimensional", "dim"))


@pytest.fixture(scope="module")
def reference() -> tuple[dict[str, object], dict[str, np.ndarray]]:
    metadata = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    assert metadata["schema"] == "alb.surrogate-c4-builder-reference.v1"
    assert (
        hashlib.sha256(REFERENCE_NPZ.read_bytes()).hexdigest()
        == metadata["npz_sha256"]
    )
    with np.load(REFERENCE_NPZ) as data:
        arrays = {name: data[name] for name in data.files}
    for name, record in metadata["arrays"].items():
        assert list(arrays[name].shape) == record["shape"]
        assert str(arrays[name].dtype) == record["dtype"]
    return metadata, arrays


@pytest.fixture(scope="module")
def synthetic_packages(tmp_path_factory, reference):
    _, arrays = reference
    root = tmp_path_factory.mktemp("c4_reference_packages")
    return {
        "quadrant": build_synthetic_package(
            root / "quadrant" / "model", arrays, "synthetic_quadrant_fit_frame"
        ),
        "full": build_synthetic_package(
            root / "full" / "model", arrays, "synthetic_full_fit_frame"
        ),
    }


def _query(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {
        key: arrays[key]
        for key in ("query_eccentricity", "query_velocity_nondim", "query_spool")
    }


def test_reference_covers_negative_quadrants(reference) -> None:
    _, arrays = reference
    ecc = arrays["query_eccentricity"]
    assert np.count_nonzero(ecc[:, 1] < 0.0) >= 8
    assert np.any((ecc[:, 0] < 0.0) & (ecc[:, 1] >= 0.0))
    assert np.any((ecc[:, 0] < 0.0) & (ecc[:, 1] < 0.0))
    # The frozen C4 target genuinely differs from the bare network there.
    outside = (ecc[:, 0] < 0.0) | (ecc[:, 1] < 0.0)
    assert np.all(
        np.any(
            arrays["synthetic_quadrant_bare_builder_nondim"][outside]
            != arrays["synthetic_quadrant_c4_wrapper_nondim"][outside],
            axis=1,
        )
    )


@pytest.mark.parametrize(("unit_system", "tag"), UNIT_SYSTEMS)
@pytest.mark.parametrize("extra", [{}, {"symmetry": None}, {"symmetry": "none"}])
def test_full_plane_package_keeps_pre_change_builder_output(
    reference, synthetic_packages, unit_system, tag, extra
) -> None:
    _, arrays = reference
    forces = builder_forces(
        synthetic_packages["full"],
        _query(arrays),
        SYNTHETIC_PARAMETERS,
        unit_system=unit_system,
        model_package_extra=extra,
    )
    np.testing.assert_array_equal(forces, arrays[f"synthetic_full_bare_builder_{tag}"])


@pytest.mark.parametrize(("unit_system", "tag"), UNIT_SYSTEMS)
def test_explicit_none_reproduces_pre_change_quadrant_builder(
    reference, synthetic_packages, unit_system, tag
) -> None:
    _, arrays = reference
    forces = builder_forces(
        synthetic_packages["quadrant"],
        _query(arrays),
        SYNTHETIC_PARAMETERS,
        unit_system=unit_system,
        model_package_extra={"symmetry": "none"},
    )
    np.testing.assert_array_equal(
        forces, arrays[f"synthetic_quadrant_bare_builder_{tag}"]
    )


@pytest.mark.parametrize(("unit_system", "tag"), UNIT_SYSTEMS)
def test_c4_builder_matches_frozen_wrapper_reference(
    reference, synthetic_packages, unit_system, tag
) -> None:
    _, arrays = reference
    query = _query(arrays)
    forces = builder_forces(
        synthetic_packages["quadrant"],
        query,
        SYNTHETIC_PARAMETERS,
        unit_system=unit_system,
        model_package_extra={"symmetry": "c4"},
    )
    np.testing.assert_array_equal(
        forces, arrays[f"synthetic_quadrant_c4_wrapper_{tag}"]
    )
    np.testing.assert_array_equal(
        forces,
        wrapper_forces(
            synthetic_packages["quadrant"],
            query,
            SYNTHETIC_PARAMETERS,
            unit_system=unit_system,
        ),
    )


def test_undeclared_quadrant_package_requires_explicit_symmetry(
    synthetic_packages,
) -> None:
    config = ALB.BearingConfig(
        {
            "family": "surrogate",
            "unit_system": "nondimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "model_package": {"path": "model"},
            "runtime": {
                "spool_mode": "external",
                "parameters": dict(SYNTHETIC_PARAMETERS),
            },
        },
        resource_root=synthetic_packages["quadrant"].parent,
    )
    with pytest.raises(ALB.BuildError, match="fitted only on ex >= 0"):
        ALB.build_bearing(config)


def _real_package(metadata: dict[str, object], name: str) -> Path:
    record = metadata["cases"]["real_packages"]["packages"][name]
    if not record["available"]:
        pytest.skip(f"{name} package was unavailable when the reference was frozen")
    package = ROOT.parent / record["relative_path"]
    manifest = package / "manifest.json"
    if not manifest.is_file():
        pytest.skip(f"{name} package is not available: {package}")
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != record["manifest_sha256"]:
        pytest.skip(f"{name} package manifest differs from the frozen reference")
    return package


@pytest.mark.parametrize("name", ["m42", "m35"])
def test_real_quadrant_packages_resolve_symmetry_exactly(reference, name) -> None:
    metadata, arrays = reference
    package = _real_package(metadata, name)
    query = _query(arrays)
    np.testing.assert_array_equal(
        builder_forces(
            package,
            query,
            REAL_PARAMETERS,
            unit_system="dimensional",
            model_package_extra={"symmetry": "c4"},
        ),
        arrays[f"{name}_c4_wrapper_dim"],
    )
    np.testing.assert_array_equal(
        builder_forces(
            package,
            query,
            REAL_PARAMETERS,
            unit_system="dimensional",
            model_package_extra={"symmetry": "none"},
        ),
        arrays[f"{name}_bare_builder_dim"],
    )
    with pytest.raises(ALB.BuildError, match="fitted only on ex >= 0"):
        builder_forces(package, query, REAL_PARAMETERS, unit_system="dimensional")
