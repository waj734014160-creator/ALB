"""Typed rotor-coupled bearing bindings and owned runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ALB.contracts import (
    BearingRuntimeProtocol,
    BearingUnitAdapterProtocol,
    ResultRecorderProtocol,
    SpoolCommandProviderProtocol,
    StepObserverProtocol,
)
from ._validation import validate_coupled_bearing_boundary


@dataclass(frozen=True, slots=True)
class CoupledBearingBinding:
    """Bind one bearing runtime to a valid rotor-coupling boundary.

    Construction rejects incompatible node, input-port, spool, and unit
    topology before the time-stepping runtime is created.
    """

    bearing: BearingRuntimeProtocol[object]
    node_link: int
    unit_adapter: BearingUnitAdapterProtocol | None = None
    spool_provider: SpoolCommandProviderProtocol | None = None

    def __post_init__(self) -> None:
        validate_coupled_bearing_boundary(
            bearing=self.bearing,
            node_link=self.node_link,
            unit_adapter=self.unit_adapter,
            spool_provider=self.spool_provider,
        )


@dataclass(frozen=True, slots=True)
class CouplingRuntimeDependencies:
    """Post-commit dependencies owned by one top-level coupling runtime."""

    run_id: str
    recorder: ResultRecorderProtocol | None = None
    observers: tuple[StepObserverProtocol, ...] = ()
    record_failure_policy: Literal["return", "raise"] = "return"
    observer_failure_policy: Literal["isolate", "raise"] = "isolate"

    def __post_init__(self) -> None:
        from ALB.contracts.recording import validate_run_id

        validate_run_id(self.run_id)
        if self.recorder is not None and not isinstance(
            self.recorder,
            ResultRecorderProtocol,
        ):
            raise TypeError("recorder must satisfy ResultRecorderProtocol")
        observers = tuple(self.observers)
        if any(
            not isinstance(observer, StepObserverProtocol)
            for observer in observers
        ):
            raise TypeError("all observers must satisfy StepObserverProtocol")
        if self.record_failure_policy not in {"return", "raise"}:
            raise ValueError(
                "record_failure_policy must be 'return' or 'raise'"
            )
        if self.observer_failure_policy not in {"isolate", "raise"}:
            raise ValueError(
                "observer_failure_policy must be 'isolate' or 'raise'"
            )
        object.__setattr__(self, "observers", observers)


__all__ = ["CoupledBearingBinding", "CouplingRuntimeDependencies"]
