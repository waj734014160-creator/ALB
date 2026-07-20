"""Non-destructive migration tests for ALBNN artifact packages."""

import pytest

from ALB.surrogate.migration import migrate_legacy_model_package
from ALB.surrogate.package import load_albnn_package, open_model_package


def test_legacy_artifacts_are_copied_and_sources_remain_unchanged(tmp_path):
    model = tmp_path / "legacy.pth"
    input_scaler = tmp_path / "legacy_x.pkl"
    output_scaler = tmp_path / "legacy_y.pkl"
    model.write_bytes(b"model-checkpoint")
    input_scaler.write_bytes(b"input-pickle")
    output_scaler.write_bytes(b"output-pickle")

    destination = tmp_path / "package"
    migrate_legacy_model_package(model, input_scaler, output_scaler, destination)
    package = open_model_package(destination)

    assert model.read_bytes() == b"model-checkpoint"
    assert input_scaler.read_bytes() == b"input-pickle"
    assert output_scaler.read_bytes() == b"output-pickle"
    assert package.model.read_bytes() == b"model-checkpoint"
    with pytest.raises(PermissionError, match="trust_pickle"):
        load_albnn_package(destination)


def test_model_package_migration_refuses_overwrite(tmp_path):
    artifacts = []
    for name in ("model.pth", "x.pkl", "y.pkl"):
        path = tmp_path / name
        path.write_bytes(name.encode("ascii"))
        artifacts.append(path)
    destination = tmp_path / "package"
    migrate_legacy_model_package(*artifacts, destination)
    with pytest.raises(FileExistsError):
        migrate_legacy_model_package(*artifacts, destination)
