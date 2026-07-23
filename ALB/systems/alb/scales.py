"""Derive explicit bearing scale sets from validated ALB configurations."""

from __future__ import annotations

import hashlib
import json
import math

from ALB.config import NodimALBConfig
from ALB.contracts import UnitSystem
from ALB.physics.bearing.units import BearingScaleSet


def bearing_scale_set_from_config(
    config: NodimALBConfig,
    *,
    rotor_unit: UnitSystem | str = UnitSystem.DIMENSIONAL,
    scale_id: str | None = None,
) -> BearingScaleSet:
    """Build a complete scale boundary from explicit nondimensional settings.

    ``scale_l`` and ``scale_w`` are optional in legacy numerical models, but
    they are mandatory here because force and time cannot otherwise be
    converted without guessing.
    """

    if not isinstance(config, NodimALBConfig):
        raise TypeError("config must be NodimALBConfig")
    pad = config.pad_config
    if pad.scale_l is None:
        raise ValueError("pad_config.scale_l is required for unit conversion")
    if pad.scale_w is None:
        raise ValueError("pad_config.scale_w is required for unit conversion")
    angular_speed = float(pad.scale_w) / 60.0 * 2.0 * math.pi
    if angular_speed <= 0.0 or pad.vf <= 0.0:
        raise ValueError("pad_config.scale_w and vf must be positive")
    Sx = float(pad.scale_c)
    St = 1.0 / (float(pad.vf) * angular_speed)
    Sv = Sx / St
    Sp = float(pad.scale_ps)
    Sf = Sp * float(pad.scale_l) * float(pad.scale_r) / 2.0
    identity_payload = {
        "Sx": Sx,
        "St": St,
        "Sv": Sv,
        "Sf": Sf,
        "Sp": Sp,
        "velocity_definition_id": "journal_surface_time.v1",
        "residual_definition_id": "film.relative_pressure_change.v1",
    }
    resolved_scale_id = scale_id or (
        "nodim-pad-"
        + hashlib.sha256(
            json.dumps(
                identity_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()[:16]
    )
    return BearingScaleSet(
        rotor_unit=UnitSystem.coerce(rotor_unit),
        bearing_unit=UnitSystem.NONDIMENSIONAL,
        Sx=Sx,
        St=St,
        Sv=Sv,
        Sf=Sf,
        Sp=Sp,
        scale_id=resolved_scale_id,
        pressure_scale_source="NodimPadConfig.scale_ps",
        velocity_definition_id="journal_surface_time.v1",
        residual_definition_id="film.relative_pressure_change.v1",
        provenance="NodimPadConfig explicit scale_* fields",
    )


__all__ = ["bearing_scale_set_from_config"]
