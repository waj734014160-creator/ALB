"""Typed rotor-coupled bearing bindings and owned runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    DirectSpoolBearingInput,
    ResultRecorderProtocol,
    SpoolCommandProviderProtocol,
    StepObserverProtocol,
    UnitSystem,
)
from ALB.physics.bearing.units import BearingUnitAdapter


@dataclass(frozen=True, slots=True)
class CoupledBearingBinding:
    """Bind one bearing runtime to a rotor node and optional boundary adapters."""

    bearing: BearingRuntimeProtocol[object]
    node_link: int
    unit_adapter: BearingUnitAdapter | None = None
    spool_provider: SpoolCommandProviderProtocol | None = None

    def __post_init__(self) -> None:
        if isinstance(self.node_link, bool) or not isinstance(self.node_link, int):
            raise TypeError("node_link must be an integer")
        if self.node_link < 0:
            raise ValueError("node_link must be nonnegative")
        input_type = getattr(self.bearing, "input_dto_type", None)
        if input_type not in (BearingInput, DirectSpoolBearingInput):
            raise TypeError("bearing must declare a supported input_dto_type")
        direct = input_type is DirectSpoolBearingInput
        if direct and self.spool_provider is None:
            raise ValueError("direct-spool bearing requires spool_provider")
        if not direct and self.spool_provider is not None:
            raise ValueError("ordinary bearing cannot carry spool_provider")
        bearing_unit = UnitSystem.coerce(self.bearing.unit_system)
        if self.unit_adapter is None:
            if bearing_unit is not UnitSystem.DIMENSIONAL:
                raise ValueError(
                    "nondimensional bearing requires an explicit unit_adapter"
                )
        else:
            scales = self.unit_adapter.scales
            if scales.rotor_unit is not UnitSystem.DIMENSIONAL:
                raise ValueError("rotor coupling domain must be dimensional")
            if scales.bearing_unit is not bearing_unit:
                raise ValueError("unit_adapter bearing_unit does not match bearing")


@dataclass(frozen=True, slots=True)
class CouplingRuntimeDependencies:
    """Post-commit dependencies owned by one top-level coupling runtime."""

    run_id: str
    recorder: ResultRecorderProtocol | None = None
    observers: tuple[StepObserverProtocol, ...] = ()
    record_failure_policy: Literal["return", "raise"] = "return"
    observer_failure_policy: Literal["isolate", "raise"] = "isolate"

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a nonempty string")
        object.__setattr__(self, "observers", tuple(self.observers))


__all__ = ["CoupledBearingBinding", "CouplingRuntimeDependencies"]
