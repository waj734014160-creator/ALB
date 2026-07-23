"""Explicit dimensional boundaries for bearing runtime ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from ALB.contracts.numeric import finite_real_array, finite_real_scalar
from ALB.contracts.ports import (
    BearingInput,
    BearingOutput,
    DirectSpoolBearingInput,
    ValveOutput,
)
from ALB.contracts.types import StepContext, UnitSystem


AppliedTransform = Literal["rotor_to_bearing", "bearing_to_rotor"]


def _positive_scale(value: Any, name: str) -> float:
    result = finite_real_scalar(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _required_text(value: str, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be nonempty")
    return result


def _context_descriptor(context: StepContext) -> dict[str, object]:
    return {
        "step_index": context.step_index,
        "time": context.time,
        "dt": context.dt,
        "unit_system": context.unit_system.value,
    }


@dataclass(frozen=True, slots=True)
class BearingScaleSet:
    """Validated scales shared by one rotor-to-bearing unit boundary.

    Each scale is defined as the dimensional value represented by one
    nondimensional unit.  ``rotor_unit`` and ``bearing_unit`` identify the two
    runtime domains; they do not change the mathematical scale definition.
    """

    rotor_unit: UnitSystem
    bearing_unit: UnitSystem
    Sx: float
    St: float
    Sv: float
    Sf: float
    Sp: float
    scale_id: str
    pressure_scale_source: str
    velocity_definition_id: str
    residual_definition_id: str
    provenance: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rotor_unit", UnitSystem.coerce(self.rotor_unit))
        object.__setattr__(
            self, "bearing_unit", UnitSystem.coerce(self.bearing_unit)
        )
        for name in ("Sx", "St", "Sv", "Sf", "Sp"):
            object.__setattr__(
                self,
                name,
                _positive_scale(getattr(self, name), name),
            )
        expected_velocity = self.Sx / self.St
        if not np.isclose(
            self.Sv,
            expected_velocity,
            rtol=1.0e-12,
            atol=np.finfo(float).eps * max(1.0, abs(expected_velocity)),
        ):
            raise ValueError("Sv must equal Sx / St")
        for name in (
            "scale_id",
            "pressure_scale_source",
            "velocity_definition_id",
            "residual_definition_id",
            "provenance",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), name),
            )

    def descriptor(
        self,
        *,
        applied_transform: AppliedTransform,
        global_context: StepContext,
        bearing_local_context: StepContext,
    ) -> dict[str, object]:
        """Return digest-safe primitive metadata for one applied conversion."""

        if applied_transform == "rotor_to_bearing":
            source_unit = self.rotor_unit
            target_unit = self.bearing_unit
        elif applied_transform == "bearing_to_rotor":
            source_unit = self.bearing_unit
            target_unit = self.rotor_unit
        else:
            raise ValueError(
                "applied_transform must be 'rotor_to_bearing' or "
                "'bearing_to_rotor'"
            )
        return {
            "schema": "alb.bearing-scale-set.v1",
            "scale_id": self.scale_id,
            "source_unit": source_unit.value,
            "target_unit": target_unit.value,
            "scale_definition": "dimensional_per_nondimensional",
            "applied_transform": applied_transform,
            "Sx": self.Sx,
            "St": self.St,
            "Sv": self.Sv,
            "Sf": self.Sf,
            "Sp": self.Sp,
            "pressure_scale_source": self.pressure_scale_source,
            "velocity_definition_id": self.velocity_definition_id,
            "residual_definition_id": self.residual_definition_id,
            "provenance": self.provenance,
            "global_context": _context_descriptor(global_context),
            "bearing_local_context": _context_descriptor(
                bearing_local_context
            ),
        }


class BearingUnitAdapter:
    """Convert bearing DTOs through the canonical dimensional domain."""

    def __init__(self, scales: BearingScaleSet) -> None:
        if not isinstance(scales, BearingScaleSet):
            raise TypeError("scales must be BearingScaleSet")
        self.scales = scales

    @staticmethod
    def _convert(
        value: Any,
        scale: float,
        source: UnitSystem,
        target: UnitSystem,
        name: str,
    ) -> np.ndarray:
        array = finite_real_array(value, name)
        dimensional = (
            array * scale
            if source is UnitSystem.NONDIMENSIONAL
            else array
        )
        converted = (
            dimensional / scale
            if target is UnitSystem.NONDIMENSIONAL
            else dimensional
        )
        converted.setflags(write=False)
        return converted

    @staticmethod
    def _convert_scalar(
        value: Any,
        scale: float,
        source: UnitSystem,
        target: UnitSystem,
        name: str,
    ) -> float:
        scalar = finite_real_scalar(value, name)
        dimensional = (
            scalar * scale
            if source is UnitSystem.NONDIMENSIONAL
            else scalar
        )
        return (
            dimensional / scale
            if target is UnitSystem.NONDIMENSIONAL
            else dimensional
        )

    def rotor_context_to_bearing(self, context: StepContext) -> StepContext:
        """Create the bearing-local context without committing it globally."""

        if context.unit_system is not self.scales.rotor_unit:
            raise ValueError("global context unit does not match rotor_unit")
        return StepContext(
            step_index=context.step_index,
            time=self._convert_scalar(
                context.time,
                self.scales.St,
                self.scales.rotor_unit,
                self.scales.bearing_unit,
                "time",
            ),
            dt=self._convert_scalar(
                context.dt,
                self.scales.St,
                self.scales.rotor_unit,
                self.scales.bearing_unit,
                "dt",
            ),
            unit_system=self.scales.bearing_unit,
        )

    def rotor_input_to_bearing(self, value: BearingInput) -> BearingInput:
        """Convert rotor displacement, velocity, and time independently."""

        if value.unit_system is not self.scales.rotor_unit:
            raise ValueError("bearing input unit does not match rotor_unit")
        return BearingInput(
            displacement=self._convert(
                value.displacement,
                self.scales.Sx,
                self.scales.rotor_unit,
                self.scales.bearing_unit,
                "displacement",
            ),
            velocity=self._convert(
                value.velocity,
                self.scales.Sv,
                self.scales.rotor_unit,
                self.scales.bearing_unit,
                "velocity",
            ),
            time=self._convert_scalar(
                value.time,
                self.scales.St,
                self.scales.rotor_unit,
                self.scales.bearing_unit,
                "time",
            ),
            unit_system=self.scales.bearing_unit,
        )

    def rotor_direct_spool_to_bearing(
        self,
        value: DirectSpoolBearingInput,
    ) -> DirectSpoolBearingInput:
        """Convert state/time while preserving normalized spool values."""

        bearing = self.rotor_input_to_bearing(value.bearing)
        return DirectSpoolBearingInput(
            bearing=bearing,
            spool=ValveOutput(
                spool=value.spool.spool,
                time=bearing.time,
                unit_system=UnitSystem.NONDIMENSIONAL,
            ),
        )

    def bearing_output_to_rotor(self, value: BearingOutput) -> BearingOutput:
        """Convert bearing force and timestamp back to the rotor domain."""

        if value.unit_system is not self.scales.bearing_unit:
            raise ValueError("bearing output unit does not match bearing_unit")
        return BearingOutput(
            force=self._convert(
                value.force,
                self.scales.Sf,
                self.scales.bearing_unit,
                self.scales.rotor_unit,
                "force",
            ),
            time=self._convert_scalar(
                value.time,
                self.scales.St,
                self.scales.bearing_unit,
                self.scales.rotor_unit,
                "time",
            ),
            unit_system=self.scales.rotor_unit,
        )

    def pressure(
        self,
        value: Any,
        *,
        source: UnitSystem,
        target: UnitSystem,
    ) -> np.ndarray:
        """Convert pressure explicitly without reusing a force scale."""

        source_unit = UnitSystem.coerce(source)
        target_unit = UnitSystem.coerce(target)
        return self._convert(
            value,
            self.scales.Sp,
            source_unit,
            target_unit,
            "pressure",
        )


__all__ = [
    "AppliedTransform",
    "BearingScaleSet",
    "BearingUnitAdapter",
]
