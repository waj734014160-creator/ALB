"""Public and typed configuration tests for supply-flow projection."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ALB.api import BearingConfig, build_bearing
from ALB.api.building import _active_config
from ALB.api.errors import ConfigurationError
from ALB.config import NodimALBConfig, NodimOrificeConfig, OrificeConfig
from ALB.physics.hydraulics.orifice import FilmPointAttachment


ROOT = Path(__file__).resolve().parents[3]
LEGACY_REFERENCE = ROOT / "refs" / "mesh_independence_legacy_reference_v1.json"


def _dimensional_spec() -> dict:
    metadata = json.loads(LEGACY_REFERENCE.read_text(encoding="utf-8"))
    return deepcopy(metadata["derived_spec"])


def _nondimensional_spec() -> dict:
    return {
        "family": "active_lubricated",
        "unit_system": "nondimensional",
        "time_step": 1.0e-3,
        "node": 1,
        "film": {
            "bearing_number": 1.0,
            "reference_bearing_number": 1.0,
            "length_ratio": 1.5,
            "arc_angle_deg": 80.0,
            "axial_length_ratio": 2.0,
            "circumferential_elements": 10,
            "axial_elements": 5,
            "continuous_boundary": False,
            "scale_viscosity": 0.0195,
            "scale_clearance": 1.2e-4,
            "scale_radius": 0.04,
            "scale_length": 0.06,
            "scale_pressure": 7.0e6,
            "scale_density": 872.0,
            "scale_speed_rpm": 3000.0,
        },
        "restrictors": {
            "positions": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "base_flow_coefficient": 1.0,
            "spool_flow_coefficient": 1.0,
            "pressure_flow_coefficient": 0.0,
            "supply_pressure": 1.0,
            "tank_pressure": 0.0,
        },
        "tank": {},
        "valve": {"model": "static"},
        "control": {"mode": "external_spool"},
        "transforms": {},
        "thermal": None,
    }


def test_typed_orifice_configs_default_to_nearest_node() -> None:
    assert OrificeConfig().flow_projection == "nearest_node"
    assert NodimOrificeConfig().flow_projection == "nearest_node"


def test_explicit_mesh_does_not_change_default_projection() -> None:
    spec = _dimensional_spec()
    spec["film"]["mesh_type"] = "quadrilateral"
    spec["film"]["element_order"] = 2
    bearing = build_bearing(BearingConfig(spec))
    owner = bearing._runtime._pads[0].bearing
    orifice = owner.simple_models[0]
    nodes = orifice._get_node(owner.main_model)

    assert orifice.flow_projection == "nearest_node"
    assert not any(isinstance(node, FilmPointAttachment) for node in nodes)


@pytest.mark.parametrize("mode", ["nearest_node", "element_shape"])
@pytest.mark.parametrize(
    ("spec_factory", "resolved_type"),
    [
        (_dimensional_spec, OrificeConfig),
        (_nondimensional_spec, NodimOrificeConfig),
    ],
)
def test_projection_mode_passes_through_public_and_typed_configs(
    mode, spec_factory, resolved_type
) -> None:
    spec = spec_factory()
    spec["restrictors"]["flow_projection"] = mode
    public = BearingConfig(spec)
    resolved = _active_config(public)

    assert isinstance(resolved.orifice_config, resolved_type)
    assert resolved.orifice_config.flow_projection == mode

    bearing = build_bearing(public)
    pad = bearing._runtime._pads[0]
    owner = getattr(pad, "bearing", pad)
    orifice = owner.simple_models[0]
    assert orifice.flow_projection == mode


def test_nondimensional_orifice_from_dict_preserves_projection() -> None:
    config = NodimOrificeConfig.from_dict({"flow_projection": "element_shape"})
    assert config.flow_projection == "element_shape"
    resolved = NodimALBConfig(orifice_config=config)
    assert resolved.orifice_config.flow_projection == "element_shape"


@pytest.mark.parametrize("config_type", [OrificeConfig, NodimOrificeConfig])
def test_typed_orifice_config_rejects_invalid_projection(config_type) -> None:
    with pytest.raises(ValueError, match="flow_projection"):
        config_type(flow_projection="cell_average")


def test_public_active_config_rejects_invalid_projection() -> None:
    spec = _dimensional_spec()
    spec["restrictors"]["flow_projection"] = "cell_average"
    with pytest.raises(ConfigurationError, match="flow_projection"):
        BearingConfig(spec)


def test_liquid_film_rejects_active_projection_field() -> None:
    spec = {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": {},
        "restrictors": {"flow_projection": "element_shape"},
        "thermal": None,
    }
    with pytest.raises(ConfigurationError, match="flow_projection"):
        BearingConfig(spec)
