"""Validation for rotor-coupling topology assembled before runtime creation."""

from __future__ import annotations

from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    BearingUnitAdapterProtocol,
    DirectSpoolBearingInput,
    SpoolCommandProviderProtocol,
    UnitSystem,
)
from ALB.core.validation import (
    require_protocol,
    strict_nonnegative_integer,
)


def validate_coupled_bearing_boundary(
    *,
    bearing: BearingRuntimeProtocol[object],
    node_link: object,
    unit_adapter: BearingUnitAdapterProtocol | None,
    spool_provider: SpoolCommandProviderProtocol | None,
) -> None:
    """Reject an invalid bearing, spool, node, or unit coupling topology."""

    require_protocol(
        bearing,
        BearingRuntimeProtocol,
        "bearing",
    )
    strict_nonnegative_integer(node_link, "node_link")

    input_type = bearing.input_dto_type
    if input_type not in (BearingInput, DirectSpoolBearingInput):
        raise TypeError("bearing must declare a supported input_dto_type")
    direct_spool = input_type is DirectSpoolBearingInput
    if direct_spool:
        if spool_provider is None:
            raise ValueError("direct-spool bearing requires spool_provider")
        require_protocol(
            spool_provider,
            SpoolCommandProviderProtocol,
            "spool_provider",
        )
    elif spool_provider is not None:
        raise ValueError("ordinary bearing cannot carry spool_provider")

    bearing_unit = UnitSystem.coerce(bearing.unit_system)
    if unit_adapter is None:
        if bearing_unit is not UnitSystem.DIMENSIONAL:
            raise ValueError(
                "nondimensional bearing requires an explicit unit_adapter"
            )
        return

    require_protocol(
        unit_adapter,
        BearingUnitAdapterProtocol,
        "unit_adapter",
    )
    scales = unit_adapter.scales
    if scales.rotor_unit is not UnitSystem.DIMENSIONAL:
        raise ValueError("rotor coupling domain must be dimensional")
    if scales.bearing_unit is not bearing_unit:
        raise ValueError("unit_adapter bearing_unit does not match bearing")


__all__ = ["validate_coupled_bearing_boundary"]
