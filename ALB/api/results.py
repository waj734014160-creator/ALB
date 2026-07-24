"""Immutable result objects for the ALB 0.4 user API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, cast

import numpy as np
import numpy.typing as npt

from ALB.contracts import (
    ArtifactManifest,
    ConvergenceStatus,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.infrastructure.persistence import DirectoryArtifactWriter


FloatArray = npt.NDArray[np.float64]


def _readonly_array(value: object, *, shape: tuple[int, ...] | None = None) -> FloatArray:
    if np.iscomplexobj(cast(Any, value)):
        raise TypeError("result arrays must be real")
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise TypeError("result arrays must be numeric") from exc
    if shape is not None and array.shape != shape:
        raise ValueError(f"result array must have shape {shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError("result arrays must contain only finite values")
    result = array.copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True, slots=True)
class BearingResult:
    """One completed two-axis bearing calculation."""

    force: FloatArray
    time: float
    unit_system: UnitSystem
    convergence: ConvergenceStatus
    details: ResultBundle

    def __post_init__(self) -> None:
        object.__setattr__(self, "force", _readonly_array(self.force, shape=(2,)))
        object.__setattr__(self, "time", float(self.time))
        object.__setattr__(self, "unit_system", UnitSystem.coerce(self.unit_system))
        if not isinstance(self.convergence, ConvergenceStatus):
            raise TypeError("convergence must be ConvergenceStatus")
        if not isinstance(self.details, ResultBundle):
            raise TypeError("details must be ResultBundle")

    @property
    def fx(self) -> float:
        """Return the x-axis force."""

        return float(self.force[0])

    @property
    def fy(self) -> float:
        """Return the y-axis force."""

        return float(self.force[1])

    @property
    def diagnostics(self) -> Mapping[str, Any]:
        """Return immutable diagnostic metadata."""

        return self.details.metadata

    def as_bundle(self) -> ResultBundle:
        """Return the complete persistable result bundle."""

        return result_snapshot(
            {
                "force": self.force,
                "details": dict(self.details.values),
            },
            {
                **dict(self.details.metadata),
                "schema": "alb.bearing-result.v0.4",
                "time": self.time,
                "unit_system": self.unit_system.value,
                "converged": self.convergence.converged,
                "residual": self.convergence.residual,
                "iterations": self.convergence.iterations,
                "message": self.convergence.message,
            },
        )

    def write(self, path: str | Path) -> ArtifactManifest:
        """Persist this result to a new directory."""

        return DirectoryArtifactWriter().write(self.as_bundle(), Path(path))


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Generic immutable result returned by a bound analysis service."""

    values: Mapping[str, Any]
    metadata: Mapping[str, Any]
    convergence: ConvergenceStatus = ConvergenceStatus(
        residual=0.0,
        converged=True,
    )

    def __post_init__(self) -> None:
        bundle = result_snapshot(self.values, self.metadata)
        object.__setattr__(self, "values", bundle.values)
        object.__setattr__(self, "metadata", bundle.metadata)
        if not isinstance(self.convergence, ConvergenceStatus):
            raise TypeError("convergence must be ConvergenceStatus")

    @property
    def diagnostics(self) -> Mapping[str, Any]:
        """Return immutable analysis diagnostics."""

        return self.metadata

    def as_bundle(self) -> ResultBundle:
        """Return the persistable analysis bundle."""

        return result_snapshot(
            dict(self.values),
            {
                **dict(self.metadata),
                "converged": self.convergence.converged,
                "residual": self.convergence.residual,
                "iterations": self.convergence.iterations,
                "message": self.convergence.message,
            },
        )

    def write(self, path: str | Path) -> ArtifactManifest:
        """Persist this analysis to a new directory."""

        return DirectoryArtifactWriter().write(self.as_bundle(), Path(path))


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Complete committed history from one rotor-bearing simulation."""

    time: FloatArray
    rotor_displacement: FloatArray
    rotor_velocity: FloatArray
    bearing_force: FloatArray
    metadata: Mapping[str, Any]
    convergence: ConvergenceStatus = ConvergenceStatus(
        residual=0.0,
        converged=True,
    )

    def __post_init__(self) -> None:
        time = _readonly_array(self.time)
        if time.ndim != 1:
            raise ValueError("time must be one-dimensional")
        displacement = _readonly_array(self.rotor_displacement)
        velocity = _readonly_array(self.rotor_velocity)
        force = _readonly_array(self.bearing_force)
        if displacement.shape != velocity.shape:
            raise ValueError("rotor displacement and velocity shapes must match")
        if displacement.shape[0] != time.shape[0]:
            raise ValueError("rotor history length must match time")
        if force.shape[0] != time.shape[0]:
            raise ValueError("bearing force history length must match time")
        object.__setattr__(self, "time", time)
        object.__setattr__(self, "rotor_displacement", displacement)
        object.__setattr__(self, "rotor_velocity", velocity)
        object.__setattr__(self, "bearing_force", force)
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )
        if not isinstance(self.convergence, ConvergenceStatus):
            raise TypeError("convergence must be ConvergenceStatus")

    @property
    def diagnostics(self) -> Mapping[str, Any]:
        """Return immutable simulation diagnostics."""

        return self.metadata

    def as_bundle(self) -> ResultBundle:
        """Return the complete persistable simulation bundle."""

        return result_snapshot(
            {
                "time": self.time,
                "rotor_displacement": self.rotor_displacement,
                "rotor_velocity": self.rotor_velocity,
                "bearing_force": self.bearing_force,
            },
            {
                **dict(self.metadata),
                "schema": "alb.simulation-result.v0.4",
                "converged": self.convergence.converged,
                "residual": self.convergence.residual,
                "iterations": self.convergence.iterations,
                "message": self.convergence.message,
            },
        )

    def write(self, path: str | Path) -> ArtifactManifest:
        """Persist this simulation to a new directory."""

        return DirectoryArtifactWriter().write(self.as_bundle(), Path(path))


__all__ = ["AnalysisResult", "BearingResult", "SimulationResult"]
