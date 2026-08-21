"""Freshness gate for the generated ALB root public API reference."""

from __future__ import annotations

import inspect
import json

import ALB
from tools.docs._source_contracts import render_docstring_details
from tools.docs.generate_public_api_reference import (
    NOTES_PATH,
    OUTPUT_PATH,
    _kind,
    _public_members,
    _source_location,
    build_reference,
)


def test_generated_public_api_reference_is_current() -> None:
    expected = build_reference()
    actual = OUTPUT_PATH.read_text(encoding="utf-8")

    assert actual == expected, (
        "public API reference is stale; run "
        "tools/docs/generate_public_api_reference.py"
    )


def test_generated_reference_embeds_source_docstrings_and_locations() -> None:
    reference = OUTPUT_PATH.read_text(encoding="utf-8")

    for name in ALB.__all__:
        value = getattr(ALB, name)
        if _kind(value) != "constant":
            docstring = inspect.getdoc(value) or ""
            assert len([line for line in docstring.splitlines() if line.strip()]) >= 2
            assert render_docstring_details(docstring) in reference
        source, line = _source_location(value)
        source_text = source if line is None else f"{source}:{line}"
        assert f"`{source_text}`" in reference

        if not inspect.isclass(value):
            continue
        for member_name, member in _public_members(value).items():
            target = member.fget if isinstance(member, property) else member
            assert target is not None
            docstring = inspect.getdoc(target) or ""
            assert len([line for line in docstring.splitlines() if line.strip()]) >= 2
            assert render_docstring_details(docstring) in reference
            member_source, member_line = _source_location(target)
            member_source_text = (
                member_source
                if member_line is None
                else f"{member_source}:{member_line}"
            )
            assert f"`{member_source_text}`" in reference
            assert f"`{name}.{member_name}" in reference


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
