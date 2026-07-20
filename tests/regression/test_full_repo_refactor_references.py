"""Exact regression tests for the immutable full-repository refactor refs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tools.reference.generate_full_repo_refactor_references import (
    DOMAIN_ORDER,
    EXPECTED_BASELINE_COMMIT,
    collect_cases,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "refs" / "full_repo_refactor_v1"


@pytest.fixture(scope="session")
def replayed_cases():
    """Recompute all deterministic cases once for the test session."""

    return collect_cases()


@pytest.mark.parametrize("domain", DOMAIN_ORDER)
def test_domain_arrays_match_reference_exactly(domain, replayed_cases):
    """Every frozen array must preserve dtype, shape, and every bit."""

    metadata = json.loads(
        (REFERENCE_DIR / f"{domain}.json").read_text(encoding="utf-8")
    )
    with np.load(REFERENCE_DIR / f"{domain}.npz") as reference:
        actual = replayed_cases[domain].arrays
        assert metadata["baseline_commit"] == EXPECTED_BASELINE_COMMIT
        assert set(actual) == set(reference.files) == set(metadata["arrays"])
        for key in reference.files:
            actual_array = np.asarray(actual[key])
            assert list(actual_array.shape) == metadata["arrays"][key]["shape"]
            assert str(actual_array.dtype) == metadata["arrays"][key]["dtype"]
            np.testing.assert_array_equal(
                actual_array,
                reference[key],
                err_msg=f"{domain}:{key}",
            )


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
