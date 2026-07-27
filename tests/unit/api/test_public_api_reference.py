"""Freshness gate for the generated ALB root public API reference."""

from __future__ import annotations

import inspect
import json

import ALB
from tools.docs.generate_public_api_reference import (
    NOTES_PATH,
    OUTPUT_PATH,
    build_reference,
)


def test_generated_public_api_reference_is_current() -> None:
    expected = build_reference()
    actual = OUTPUT_PATH.read_text(encoding="utf-8")

    assert actual == expected, (
        "public API reference is stale; run "
        "tools/docs/generate_public_api_reference.py"
    )


def test_mapping_heavy_public_types_remain_self_documenting() -> None:
    required_fragments = {
        ALB.BearingConfig: (
            "liquid_film",
            "resource_root",
            "docs/api/bearing_config_reference.md",
        ),
        ALB.SimulationConfig: (
            '"type": "static"',
            '"type": "unbalance"',
            "steps + 1",
            "CouplingRuntimeDependencies",
        ),
        ALB.EquilibriumOptions: (
            "relative_tolerance",
            "jacobian_step",
            "fallback_stiffness",
        ),
    }

    for public_type, fragments in required_fragments.items():
        docstring = inspect.getdoc(public_type) or ""
        assert len(docstring.splitlines()) >= 5
        for fragment in fragments:
            assert fragment in docstring


def test_dynamic_coefficient_exception_metadata_matches_public_contract() -> None:
    metadata = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    raises = metadata["symbols"]["BearingAnalysis"]["members"][
        "dynamic_coefficients"
    ]["raises"]

    assert [item["type"] for item in raises] == [
        "ValueError",
        "CalculationError",
    ]
    assert "failure_snapshot" in raises[1]["when"]
