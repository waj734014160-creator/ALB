"""Freshness and metadata gates for the bearing configuration reference."""

from __future__ import annotations

from pathlib import Path

from ALB.api._config_fields import (
    BEARING_FIELD_GROUPS,
    DIMENSIONAL_FILM_FIELDS,
    GAS_FILM_FIELDS,
    GAS_FILM_OVERRIDE_FIELDS,
    GAS_ONLY_FILM_FIELDS,
    NONDIMENSIONAL_FILM_FIELDS,
    native_name_map,
)
from tools.docs._config_reference import field_surface, validate_groups
from tools.docs.generate_bearing_config_reference import (
    OUTPUT_PATH,
    build_reference,
)


def test_generated_bearing_config_reference_is_current() -> None:
    assert OUTPUT_PATH.read_text(encoding="utf-8") == build_reference()


def test_all_translated_film_fields_have_complete_metadata() -> None:
    for fields in (
        DIMENSIONAL_FILM_FIELDS,
        NONDIMENSIONAL_FILM_FIELDS,
        GAS_FILM_FIELDS,
    ):
        assert native_name_map(fields).keys() == fields.keys()
        for field in fields.values():
            assert field.native_name
            assert field.unit
            assert field.description


def test_all_bearing_field_groups_have_complete_source_metadata() -> None:
    validate_groups(BEARING_FIELD_GROUPS)
    surface = field_surface(BEARING_FIELD_GROUPS)

    assert len(surface) == 17
    assert sum(map(len, surface.values())) == 186
    for fields in surface.values():
        for field in fields.values():
            assert field["native_name"]
            assert field["unit"]
            assert field["description"]
            assert field["value_type"]
            assert field["required"] or field["has_default"] or field["default_description"]


def test_bearing_runtime_validation_consumes_canonical_field_groups() -> None:
    source = Path("ALB/api/config.py").read_text(encoding="utf-8")
    required_groups = {
        "ACTIVE_RESTRICTOR_FIELDS",
        "BEARING_DOCUMENT_FIELDS",
        "BEARING_SPEC_FIELDS",
        "CONTROL_FIELDS",
        "LIQUID_RESTRICTOR_FIELDS",
        "MODEL_PACKAGE_FIELDS",
        "PID_GAIN_FIELDS",
        "SECOND_ORDER_VALVE_FIELDS",
        "STATIC_VALVE_FIELDS",
        "SURROGATE_RUNTIME_FIELDS",
        "TANK_FIELDS",
        "TRANSFER_FUNCTION_VALVE_FIELDS",
        "TRANSFORM_FIELDS",
    }

    for group_name in required_groups:
        assert group_name in source


def test_generated_bearing_reference_explains_conditional_contracts() -> None:
    reference = OUTPUT_PATH.read_text(encoding="utf-8")

    assert "适用时必填" in reference
    assert "与公开字段同名" in reference
    assert "true for liquid_film; false for active_lubricated" in reference
    assert "film.supply_pressure for dimensional; 1.0 for nondimensional" in reference
    assert "flow_coefficient when provided; otherwise 1.0" in reference
    assert "50.0 for pid; 5.0 for fuzzy_pid" in reference


def test_gas_metadata_matches_public_configuration_constraints() -> None:
    texture = GAS_ONLY_FILM_FIELDS["texture_type"]
    assert texture.unit == "integer"
    assert texture.choices == (1, 2, 3)
    assert texture.default == 1
    assert GAS_ONLY_FILM_FIELDS["texture_start_theta_index"].constraint == ">= 1"
    assert GAS_ONLY_FILM_FIELDS["texture_start_axial_index"].constraint == ">= 1"
    assert GAS_FILM_OVERRIDE_FIELDS["continuous_boundary"].default is True
    assert GAS_FILM_OVERRIDE_FIELDS["continuous_boundary"].value_type == "boolean"
    assert GAS_FILM_OVERRIDE_FIELDS["ambient_pressure"].default == 1.0
    assert GAS_FILM_OVERRIDE_FIELDS["solver"].choices == ("skfem_newton",)
    assert DIMENSIONAL_FILM_FIELDS["mesh_type"].value_type == "string or null"
    assert DIMENSIONAL_FILM_FIELDS["element_order"].value_type == "integer or null"
    assert DIMENSIONAL_FILM_FIELDS["x_velocity"].value_type == "number or null"
