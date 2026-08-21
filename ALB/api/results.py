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
    """One completed two-axis bearing calculation.

    ``force`` is always a two-component array in the selected unit system.
    Detailed scalar and field outputs are available through the named
    properties below. ``details`` remains available for family-specific data
    such as per-pad or thermal outputs.
    """

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
        """Return the x-axis force component as a Python float.

        Dimensional results use N; nondimensional results use the configured
        bearing force scale.
        """

        return float(self.force[0])

    @property
    def fy(self) -> float:
        """Return the y-axis force component as a Python float.

        Dimensional results use N; nondimensional results use the configured
        bearing force scale.
        """

        return float(self.force[1])

    @property
    def diagnostics(self) -> Mapping[str, Any]:
        """Return immutable family and convergence diagnostic metadata.

        Keys beyond the documented schema are family-specific diagnostics rather
        than a root-API compatibility promise.
        """

        return self.details.metadata

    @property
    def friction(self) -> float | None:
        """Return the total friction force when the bearing reports it.

        Dimensional results use N. Nondimensional results use the family force
        scale. Families that do not publish aggregate friction return ``None``.
        """

        value = self.details.values.get("friction")
        return None if value is None else float(value)

    @property
    def pressure(self) -> FloatArray | None:
        """Return the immutable pressure field for a single film.

        Dimensional results use Pa. Nondimensional results contain ``p / ps``.
        Multi-pad results expose per-pad arrays through
        ``details.values["pad_pressure"]`` because one aggregate pressure field
        would not have a physical meaning.
        """

        value = self.details.values.get("pressure")
        return None if value is None else cast(FloatArray, value)

    @property
    def film_thickness(self) -> FloatArray | None:
        """Return the immutable film-thickness field for a single film.

        Dimensional results use m. Nondimensional results contain ``h / c``.
        Multi-pad results expose per-pad arrays through
        ``details.values["pad_film_thickness"]``.
        """

        value = self.details.values.get("film_thickness")
        return None if value is None else cast(FloatArray, value)

    def as_bundle(self) -> ResultBundle:
        """Return a complete immutable bundle for persistence or transport.

        The bundle contains the force and family-specific detail values plus
        schema, time, unit-system, and convergence metadata. Nested arrays and
        mappings are read-only snapshots.
        """

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
        """Persist the complete result to a new artifact directory.

        Parameters
        ----------
        path
            Destination directory, which must not contain an existing artifact.

        Returns
        -------
        ArtifactManifest
            Written files, digests, and schema metadata.
        """

        return DirectoryArtifactWriter().write(self.as_bundle(), Path(path))


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Immutable values and diagnostics from one bound analysis operation.

    ``values`` is operation-specific: orbit tracing exposes ``time``,
    ``displacement``, ``velocity``, and ``force``; dynamic identification adds
    stiffness/damping coefficient arrays and forward/reverse responses;
    equilibrium exposes the solved displacement and force balance; harmonic
    linearization exposes stiffness, damping, and operating-point diagnostics.
    Treat additional family-specific keys as diagnostic rather than a root-API
    compatibility promise. Arrays and nested mappings are read-only.
    """

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
        """Return immutable operation-specific analysis diagnostics.

        The mapping includes a schema identifier and the physical/numerical
        context needed to interpret ``values``.
        """

        return self.metadata

    def as_bundle(self) -> ResultBundle:
        """Return a persistable immutable analysis bundle.

        Operation values are copied with metadata augmented by convergence,
        residual, iteration-count, and message fields.
        """

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
        """Persist this analysis snapshot to a new artifact directory.

        Parameters
        ----------
        path
            Destination directory passed to ``DirectoryArtifactWriter``.

        Returns
        -------
        ArtifactManifest
            Written files and their integrity metadata.
        """

        return DirectoryArtifactWriter().write(self.as_bundle(), Path(path))


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Immutable committed history from one rotor-bearing simulation.

    The first axis of every retained array matches ``time``. Displacement and
    velocity normally have shape ``(samples, rotor_dofs)`` and bearing force
    has shape ``(samples, mount_count, 2)``. A field excluded by
    ``HistoryPolicy.fields`` is represented by an empty trailing dimension;
    ring-buffer and downsampling policies may reduce ``samples``. Disk-streamed
    fields are empty in memory and ``metadata['history_path']`` identifies the
    persisted history.
    """

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
        """Return immutable simulation completion and history diagnostics.

        Metadata records committed/requested steps, physical/history/post-commit
        completion, history policy, and an optional disk-stream path.
        """

        return self.metadata

    def as_bundle(self) -> ResultBundle:
        """Return the complete committed in-memory history as a result bundle.

        The bundle contains time, rotor displacement/velocity, and bearing force
        arrays plus the simulation schema and convergence metadata. Disk-streamed
        fields remain empty in memory and are identified by metadata.
        """

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
        """Persist the in-memory simulation result to a new artifact directory.

        Parameters
        ----------
        path
            Destination directory passed to ``DirectoryArtifactWriter``.

        Returns
        -------
        ArtifactManifest
            Written arrays, metadata, and integrity digests.
        """

        return DirectoryArtifactWriter().write(self.as_bundle(), Path(path))


__all__ = ["AnalysisResult", "BearingResult", "SimulationResult"]
