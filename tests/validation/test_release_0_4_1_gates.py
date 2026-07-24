"""Release-level gates for the ALB 0.4.1 numerical patch."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import ALB
from ALB.api.config import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_numerical_reference_is_the_frozen_93dd63d_contract() -> None:
    metadata_path = (
        ROOT / "refs/alb_0_4_1_numerical_contract_v1.json"
    )
    arrays_path = ROOT / "refs/alb_0_4_1_numerical_contract_v1.npz"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["baseline_commit"] == (
        "93dd63d12817b6952245cf60311139eb52ee5668"
    )
    assert _sha256(metadata_path) == (
        "8f603ec1382b93ffbd65a118be00c5b764f573fadc22b9488caa1e4dbe0ef54d"
    )
    assert _sha256(arrays_path) == (
        "78440877f4816b1286979659c3615f7ff22001299d54932613db1e4c516e02d7"
    )


def test_patch_manifest_and_test_map_are_contiguous_and_aligned() -> None:
    manifest = json.loads(
        (
            ROOT
            / "tools/validation/release_feature_manifest_0_4_1.json"
        ).read_text(encoding="utf-8")
    )
    test_map = json.loads(
        (
            ROOT / "docs/migrations/0.4.1_test_map.json"
        ).read_text(encoding="utf-8")
    )
    feature_ids = [item["id"] for item in manifest["features"]]
    mapped_ids = [item["id"] for item in test_map["features"]]

    assert manifest["release"] == "0.4.1"
    assert feature_ids == [
        f"V4P-{index:02d}"
        for index in range(1, len(feature_ids) + 1)
    ]
    assert mapped_ids == feature_ids
    assert all(item["required_nodeids"] for item in manifest["features"])


def test_0_4_0_release_evidence_remains_content_unchanged() -> None:
    expected = {
        "tools/validation/release_feature_manifest_0_4.json": (
            "9a2adb08c6ff4c51a7285e5acff43c04810f07d7c9fac1e1f68a529def2cc8ce"
        ),
        "docs/migrations/0.4.0_test_map.json": (
            "72099b6400597d289617dfbfc63a296a826c5ce8faa9c4b7d207f652a6277ab7"
        ),
        "docs/migrations/0.4.0_release_acceptance.json": (
            "7e6988d7afd284c53e66844e394ca03392d38b0ee4f26fe2ec8df49a96ad4e67"
        ),
    }

    for relative_path, digest in expected.items():
        assert _normalized_text_sha256(ROOT / relative_path) == digest


def test_package_version_changes_without_configuration_schema_migration() -> None:
    assert ALB.__version__ == "0.4.2"
    assert SCHEMA_VERSION == "0.4.0"
