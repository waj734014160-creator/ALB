"""Regression tests for immutable refs except explicitly superseded results."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tests._support.dynamics.coupling_v4 import (
    assert_corrected_coupling_reference_exact,
)
from tools.reference.generate_full_repo_refactor_references import (
    DOMAIN_ORDER,
    EXPECTED_BASELINE_COMMIT,
    collect_cases,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "refs" / "full_repo_refactor_v1"
REFERENCE_SCHEMA = "alb.full-repo-refactor-reference.v1"
REFERENCE_SEED = 20260720


def _array_digest(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).view(np.uint8)).hexdigest()


def _assert_metadata(domain, expected, actual):
    expected_metadata = {
        key: value
        for key, value in expected.items()
        if key not in {"schema", "domain", "baseline_commit", "seed", "arrays"}
    }
    actual_metadata = deepcopy(actual)
    if actual_metadata.get("seed") == expected["seed"] and "seed" not in expected_metadata:
        actual_metadata.pop("seed")

    if domain == "dynamics_coupling":
        assert expected_metadata.pop("legacy_output_advances_state") is True
        assert actual_metadata.pop("legacy_output_advances_state") is False
    if domain == "remote_persistence":
        expected_remote = expected_metadata.pop("remote")
        actual_remote = actual_metadata.pop("remote")
        assert actual_remote["runner_content"].replace(
            "ALB.infrastructure.remote.job", "ALB.remote.job"
        ) == expected_remote["runner_content"]
        actual_remote = dict(actual_remote)
        expected_remote = dict(expected_remote)
        actual_remote.pop("runner_content")
        expected_remote.pop("runner_content")
        assert actual_remote == expected_remote

    assert actual_metadata == expected_metadata


@pytest.fixture(scope="session")
def replayed_cases():
    """Recompute all deterministic cases once for the test session."""

    return collect_cases()


@pytest.mark.parametrize("domain", DOMAIN_ORDER)
def test_domain_arrays_match_reference_exactly(domain, replayed_cases):
    """Preserve v1 or require an exact corrected reference when superseded."""

    metadata = json.loads(
        (REFERENCE_DIR / f"{domain}.json").read_text(encoding="utf-8")
    )
    with np.load(REFERENCE_DIR / f"{domain}.npz") as reference:
        actual = replayed_cases[domain].arrays
        assert metadata["schema"] == REFERENCE_SCHEMA
        assert metadata["domain"] == domain
        assert metadata["baseline_commit"] == EXPECTED_BASELINE_COMMIT
        assert metadata["seed"] == REFERENCE_SEED
        _assert_metadata(domain, metadata, replayed_cases[domain].metadata)
        protected_keys = set(reference.files)
        if domain == "dynamics_coupling":
            protected_keys.remove("coupling_bearing_results")
        assert set(actual) == protected_keys
        assert protected_keys.issubset(metadata["arrays"])
        for key in sorted(protected_keys):
            actual_array = np.asarray(actual[key])
            reference_array = np.asarray(reference[key])
            assert list(actual_array.shape) == metadata["arrays"][key]["shape"]
            assert str(actual_array.dtype) == metadata["arrays"][key]["dtype"]
            assert _array_digest(reference_array) == metadata["arrays"][key]["sha256"]
            if domain not in {"hydraulics_orifice", "dynamics_coupling"}:
                assert _array_digest(actual_array) == metadata["arrays"][key]["sha256"]
                np.testing.assert_array_equal(
                    actual_array,
                    reference_array,
                    err_msg=f"{domain}:{key}",
                )
        if domain == "dynamics_coupling":
            assert_corrected_coupling_reference_exact()


def test_baseline_test_node_inventory_is_complete_and_unique():
    """The immutable pre-refactor inventory must retain all 242 node ids."""

    payload = json.loads(
        (REFERENCE_DIR / "test_node_migration_map.json").read_text(
            encoding="utf-8"
        )
    )
    mappings = payload["mappings"]
    nodeids = [mapping["baseline_nodeid"] for mapping in mappings]
    assert payload["baseline_commit"] == EXPECTED_BASELINE_COMMIT
    assert payload["node_count"] == 242
    assert len(mappings) == len(nodeids) == len(set(nodeids)) == 242
    assert all(mapping["rationale"] for mapping in mappings)
    assert all(
        mapping["disposition"] in {"migrate", "manual", "validation"}
        for mapping in mappings
    )
