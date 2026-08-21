"""Freshness and metadata gates for the simulation configuration reference."""

from __future__ import annotations

from pathlib import Path

from ALB.api._config_fields import (
    SIMULATION_FIELD_GROUPS,
    SIMULATION_HISTORY_FIELDS,
    SIMULATION_ROTOR_FIELDS,
)
from tools.docs._config_reference import field_surface, validate_groups
from tools.docs.generate_simulation_config_reference import OUTPUT_PATH, build_reference


def test_generated_simulation_config_reference_is_current() -> None:
    assert OUTPUT_PATH.read_text(encoding="utf-8") == build_reference()


def test_all_simulation_field_groups_have_complete_source_metadata() -> None:
    validate_groups(SIMULATION_FIELD_GROUPS)
    surface = field_surface(SIMULATION_FIELD_GROUPS)

    assert len(surface) == 9
    assert sum(map(len, surface.values())) == 36
    for fields in surface.values():
        for field in fields.values():
            assert field["native_name"]
            assert field["unit"]
            assert field["description"]
            assert field["value_type"]
            assert field["required"] or field["has_default"] or field["default_description"]


def test_simulation_loader_consumes_canonical_field_groups() -> None:
    source = Path("ALB/api/simulation.py").read_text(encoding="utf-8")

    for group_name in (
        "GRAVITY_LOAD_FIELDS",
        "SIMULATION_DOCUMENT_FIELDS",
        "SIMULATION_HISTORY_FIELDS",
        "SIMULATION_MOUNT_FIELDS",
        "SIMULATION_ROTOR_FIELDS",
        "SIMULATION_SPEC_FIELDS",
        "SIMULATION_TIME_GRID_FIELDS",
        "STATIC_LOAD_FIELDS",
        "UNBALANCE_LOAD_FIELDS",
    ):
        assert group_name in source


def test_simulation_reference_exposes_resources_history_and_contract_mapping() -> None:
    reference = OUTPUT_PATH.read_text(encoding="utf-8")

    assert "ross_excel" in SIMULATION_ROTOR_FIELDS["model"].choices
    assert SIMULATION_HISTORY_FIELDS["mode"].choices == (
        "memory",
        "ring_buffer",
        "disk_stream",
    )
    assert "steps + 1" in reference
    assert "resources/rotor.xlsx" in reference
    assert "与公开字段同名" in reference
    assert "源码合同摘要：`sha256:" in reference
    assert "SimulationError" in reference
