"""Release-level gates for the ALB 0.4.2 review repair patch."""

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


def test_repair_reference_is_the_frozen_v0_4_1_candidate_contract() -> None:
    metadata_path = ROOT / "refs/alb_0_4_2_repair_contract_v1.json"
    arrays_path = ROOT / "refs/alb_0_4_2_repair_contract_v1.npz"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["baseline_commit"] == (
        "a26435e2eb7652d6d64af2194865dd3cf05db61d"
    )
    assert _normalized_text_sha256(metadata_path) == (
        "793146471424f63ff07df230ea7adad2e620da26c82bd17d5d5cd5760fd51991"
    )
    assert _sha256(arrays_path) == (
        "72eb8e591b27b40be0098ebc55d8c373c00159902b7a362e04b33fe86355e52b"
    )


def test_patch_manifest_and_test_map_are_contiguous_and_aligned() -> None:
    manifest = json.loads(
        (
            ROOT
            / "tools/validation/release_feature_manifest_0_4_2.json"
        ).read_text(encoding="utf-8")
    )
    test_map = json.loads(
        (ROOT / "docs/migrations/0.4.2_test_map.json").read_text(
            encoding="utf-8"
        )
    )
    feature_ids = [item["id"] for item in manifest["features"]]
    mapped_ids = [item["id"] for item in test_map["features"]]

    assert manifest["release"] == "0.4.2"
    assert feature_ids == [
        f"V4P2-{index:02d}"
        for index in range(1, len(feature_ids) + 1)
    ]
    assert mapped_ids == feature_ids
    assert all(item["required_nodeids"] for item in manifest["features"])


def test_historical_release_evidence_remains_content_unchanged() -> None:
    normalized = {
        "tools/validation/release_feature_manifest_0_4.json": (
            "9a2adb08c6ff4c51a7285e5acff43c04810f07d7c9fac1e1f68a529def2cc8ce"
        ),
        "docs/migrations/0.4.0_test_map.json": (
            "72099b6400597d289617dfbfc63a296a826c5ce8faa9c4b7d207f652a6277ab7"
        ),
        "docs/migrations/0.4.0_release_acceptance.json": (
            "7e6988d7afd284c53e66844e394ca03392d38b0ee4f26fe2ec8df49a96ad4e67"
        ),
        "tools/validation/release_feature_manifest_0_4_1.json": (
            "289b733fc7d70f66e40f5b04c06b31599d5b97e4e004d615a2614d9f14cc3505"
        ),
        "docs/migrations/0.4.1_test_map.json": (
            "ffd16cc75933b8b59ee927976bd5c9ae3ecfa16d14ff9603daf1aeb9a053e758"
        ),
        "docs/migrations/0.4.1_release_acceptance.json": (
            "2d09acbdacf7b08971a7e91fcf727f0102f8dc7fce25925f546fa88785b36b18"
        ),
        "refs/alb_0_4_1_numerical_contract_v1.json": (
            "2128d95cc7d4ca417850fc72a855ef50fbccaf5de6fc8b1031c52905e449721d"
        ),
    }
    binary = {
        "refs/alb_0_4_1_numerical_contract_v1.npz": (
            "78440877f4816b1286979659c3615f7ff22001299d54932613db1e4c516e02d7"
        )
    }

    for relative_path, digest in normalized.items():
        assert _normalized_text_sha256(ROOT / relative_path) == digest
    for relative_path, digest in binary.items():
        assert _sha256(ROOT / relative_path) == digest


def test_package_version_changes_without_schema_migration() -> None:
    assert ALB.__version__ == "0.4.3"
    assert SCHEMA_VERSION == "0.4.0"


def test_quickstart_uses_a_coherent_ten_hertz_grid() -> None:
    quickstart = (ROOT / "docs/alb_albnn_quickstart.md").read_text(
        encoding="utf-8"
    )

    assert "time = np.arange(100) * 1.0e-3" in quickstart
    assert "frequency_hz=10.0" in quickstart
