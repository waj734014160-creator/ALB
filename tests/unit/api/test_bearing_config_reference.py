"""Freshness and metadata gates for the bearing configuration reference."""

from __future__ import annotations

from ALB.api._config_fields import (
    DIMENSIONAL_FILM_FIELDS,
    GAS_FILM_FIELDS,
    GAS_ONLY_FILM_FIELDS,
    NONDIMENSIONAL_FILM_FIELDS,
    native_name_map,
)
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


def test_gas_metadata_matches_public_configuration_constraints() -> None:
    texture = GAS_ONLY_FILM_FIELDS["texture_type"]
    assert texture.unit == "integer"
    assert texture.choices == (1, 2, 3)
    assert texture.default == 1
    assert GAS_ONLY_FILM_FIELDS["texture_start_theta_index"].constraint == ">= 1"
    assert GAS_ONLY_FILM_FIELDS["texture_start_axial_index"].constraint == ">= 1"
