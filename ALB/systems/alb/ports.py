"""Strict bearing-port adapters shared by nonlinear and harmonic ALB models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    UnitSystem,
    ValveOutput,
)
from ALB.core import EvaluatingBlock


@dataclass(frozen=True, slots=True)
class DirectSpoolBearingInput:
    """Bearing state paired with an already-normalized valve spool state."""

    bearing: BearingInput
    spool: ValveOutput

    def __post_init__(self) -> None:
        if not isinstance(self.bearing, BearingInput):
            raise TypeError("bearing must be BearingInput")
        if not isinstance(self.spool, ValveOutput):
            raise TypeError("spool must be ValveOutput")
        if self.bearing.time != self.spool.time:
            raise ValueError("bearing and spool timestamps must match")
        if self.spool.unit_system is not UnitSystem.NONDIMENSIONAL:
            raise ValueError("direct spool state must be nondimensional")


class BearingBlock(EvaluatingBlock[BearingInput, BearingOutput]):
    """Adapt an ALB numerical implementation to the strict bearing port."""

    def __init__(self, implementation: Any) -> None:
        super().__init__()
        self.implementation = implementation
        self.unit_system = UnitSystem.coerce(implementation.unit_system)
        self.node_link = int(implementation.node_link)

    def _validate_input(self, dto: BearingInput) -> BearingInput:
        if not isinstance(dto, BearingInput):
            raise TypeError("bearing input must be BearingInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("bearing input unit_system does not match the block")
        return dto

    def evaluate(self) -> None:
        dto = self._require_input()
        self.implementation.input(dto.displacement, dto.velocity, dto.time)
        legacy_output = self.implementation.output()
        if not isinstance(legacy_output, dict) or "force" not in legacy_output:
            raise TypeError("bearing implementation must return a force mapping")
        self._publish_output(
            BearingOutput(legacy_output["force"], dto.time, self.unit_system)
        )


class DirectSpoolBearingBlock(
    EvaluatingBlock[DirectSpoolBearingInput, BearingOutput]
):
    """Adapt direct-spool ALBSV evaluation without adding valve dynamics."""

    def __init__(self, implementation: Any) -> None:
        super().__init__()
        self.implementation = implementation
        self.unit_system = UnitSystem.coerce(implementation.unit_system)
        node_link = implementation.node_link
        self.node_link = None if node_link is None else int(node_link)
        self._convergence_status = ConvergenceStatus.pending("input not evaluated")

    @property
    def convergence_status(self) -> ConvergenceStatus:
        """Return the cached local completion status without recomputing."""

        return self._convergence_status

    def input(self, dto: DirectSpoolBearingInput) -> None:
        """Latch a validated direct-spool sample and invalidate prior status."""

        super().input(dto)
        self._convergence_status = ConvergenceStatus.pending("input not evaluated")

    def _validate_input(
        self, dto: DirectSpoolBearingInput
    ) -> DirectSpoolBearingInput:
        if not isinstance(dto, DirectSpoolBearingInput):
            raise TypeError("direct spool input must be DirectSpoolBearingInput")
        if dto.bearing.unit_system is not self.unit_system:
            raise ValueError("bearing input unit_system does not match the block")
        return dto

    def evaluate(self) -> None:
        dto = self._require_input()
        nodim = self.unit_system is UnitSystem.NONDIMENSIONAL
        self.implementation.input(
            dto.bearing.displacement,
            dto.bearing.velocity,
            dto.bearing.time,
            sv=dto.spool.spool,
            nodim=nodim,
        )
        legacy_output = self.implementation.output(nodim=nodim)
        if not isinstance(legacy_output, dict) or "force" not in legacy_output:
            raise TypeError("bearing implementation must return a force mapping")
        converged = bool(self.implementation.calc_is_finished())
        self._convergence_status = (
            ConvergenceStatus(0.0, True, message="legacy calculation finished")
            if converged
            else ConvergenceStatus.pending("legacy calculation is incomplete")
        )
        self._publish_output(
            BearingOutput(
                legacy_output["force"], dto.bearing.time, self.unit_system
            )
        )


class HarmonicBearingBlock(BearingBlock):
    """Bearing block with formal K, C, and complex G_xv capabilities."""

    @property
    def K(self) -> np.ndarray:
        """Return the 2-by-2 harmonic stiffness matrix."""

        return np.asarray(self.implementation.K).copy()

    @property
    def C(self) -> np.ndarray:
        """Return the 2-by-2 harmonic damping matrix."""

        return np.asarray(self.implementation.C).copy()

    @property
    def G_xv(self) -> np.ndarray:
        """Return the complex 2-by-2 spool-force transfer matrix."""

        return np.asarray(self.implementation.G_xv).copy()
