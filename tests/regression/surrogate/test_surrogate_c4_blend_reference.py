"""Frozen M0042 public-builder forces with default C4 boundary blending."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")

from tools.reference.generate_surrogate_c4_builder_reference_v1 import builder_forces

ROOT = Path(__file__).resolve().parents[3]
STEM = ROOT / "refs/surrogate_c4_builder_reference_v2"


@pytest.fixture(scope="module")
def reference():
    metadata = json.loads(STEM.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["schema"] == "alb.surrogate-c4-builder-reference.v2"
    assert metadata["blend_ratio"] == 0.15
    assert hashlib.sha256(STEM.with_suffix(".npz").read_bytes()).hexdigest() == metadata["npz_sha256"]
    with np.load(STEM.with_suffix(".npz")) as data:
        arrays = {name: data[name] for name in data.files}
    for name, record in metadata["arrays"].items():
        assert list(arrays[name].shape) == record["shape"]
        assert str(arrays[name].dtype) == record["dtype"]
    return metadata, arrays


def test_blend_reference_covers_bands_at_all_four_half_axes(reference):
    _, arrays = reference
    e = arrays["query_eccentricity"]
    theta = np.mod(np.arctan2(e[:, 1], e[:, 0]), 2 * np.pi)
    b = np.rint(theta / (np.pi / 2)).astype(int) % 4
    phi = (theta - b * np.pi / 2 + np.pi) % (2 * np.pi) - np.pi
    for axis in range(4):
        assert np.any((b == axis) & (phi < 0) & (np.abs(phi) < 0.15 * (np.pi / 2)))
        assert np.any((b == axis) & (phi > 0) & (np.abs(phi) < 0.15 * (np.pi / 2)))
        assert np.any((b == axis) & (np.abs(phi) > 0.15 * (np.pi / 2)))


@pytest.mark.parametrize(("units", "tag"), [("nondimensional", "nondim"), ("dimensional", "dim")])
def test_default_builder_matches_frozen_m42_blend(reference, units, tag):
    metadata, arrays = reference
    record = metadata["package"]
    if not record["available"]:
        pytest.skip("M0042 package was unavailable when reference was frozen")
    package = ROOT.parent / record["relative_path"]
    manifest = package / "manifest.json"
    if not manifest.is_file():
        pytest.skip(f"M0042 package is not available: {package}")
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != record["manifest_sha256"]:
        pytest.skip("M0042 manifest differs from the frozen reference")
    query = {key: arrays[key] for key in
             ("query_eccentricity", "query_velocity_nondim", "query_spool")}
    force = builder_forces(package, query, metadata["parameters"], unit_system=units,
                           model_package_extra={"symmetry": "c4"})
    np.testing.assert_array_equal(force, arrays[f"m42_c4_blend_builder_{tag}"])
