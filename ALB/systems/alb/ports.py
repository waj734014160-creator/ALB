"""Strict bearing-port adapters shared by nonlinear and harmonic ALB models."""

from __future__ import annotations

from typing import Any

import numpy as np

from ALB.contracts import BearingInput, BearingOutput, UnitSystem
from ALB.core import EvaluatingBlock


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
