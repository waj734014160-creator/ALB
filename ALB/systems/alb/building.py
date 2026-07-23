"""Typed public builders that hide transitional bearing block adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, TypeAlias, cast

from ALB.config import (
    ALBConfig,
    ALBConfigEnvelope,
    ControlMode,
    CurrentConfig,
    NodimALBConfig,
    materialize_current_config,
)
from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    DirectSpoolBearingRuntimeProtocol,
)
from ALB.control.adapters import adapt_controller

from .factories import alb2, nodim_alb


class ControllerFactoryProtocol(Protocol):
    """Build one controller from its typed configuration object."""

    def __call__(self, config: object) -> object:
        """Return a controller implementation."""


class BearingComponentFactoryProtocol(Protocol):
    """Assemble one legacy ALB implementation from a typed configuration."""

    def __call__(
        self,
        config: CurrentConfig,
        controller_factory: ControllerFactoryProtocol | None,
    ) -> object:
        """Return a fully wired but uninitialized ALB implementation."""


@dataclass(frozen=True, slots=True)
class BearingBuildDependencies:
    """Build-time factories only.

    Spool providers belong to coupling bindings, recorders and observers belong
    to coupling runtime dependencies, and artifact writers belong to workflow
    output dependencies.
    """

    component_factory: BearingComponentFactoryProtocol | None = None
    controller_factory: ControllerFactoryProtocol | None = None


@dataclass(frozen=True, slots=True)
class BuiltControlledBearing:
    """Discriminated file-build result for closed-loop control."""

    runtime: BearingRuntimeProtocol[BearingInput]
    control_mode: Literal[ControlMode.CONTROLLED] = field(
        default=ControlMode.CONTROLLED,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class BuiltUncontrolledBearing:
    """Discriminated file-build result for a zero-command bearing."""

    runtime: BearingRuntimeProtocol[BearingInput]
    control_mode: Literal[ControlMode.NONE] = field(
        default=ControlMode.NONE,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class BuiltDirectSpoolBearing:
    """Discriminated file-build result for external normalized spool input."""

    runtime: DirectSpoolBearingRuntimeProtocol
    control_mode: Literal[ControlMode.DIRECT_SPOOL] = field(
        default=ControlMode.DIRECT_SPOOL,
        init=False,
    )


BuiltBearing: TypeAlias = (
    BuiltControlledBearing
    | BuiltUncontrolledBearing
    | BuiltDirectSpoolBearing
)


def _default_component_factory(
    config: CurrentConfig,
    controller_factory: ControllerFactoryProtocol | None,
) -> object:
    """Reuse the frozen 0.2 assembly path while public builders stabilize."""

    if isinstance(config, ALBConfig):
        implementation = alb2(config)
    elif isinstance(config, NodimALBConfig):
        implementation = nodim_alb(config)
    else:
        raise TypeError("config must be ALBConfig or NodimALBConfig")
    if controller_factory is not None and config.controller_config is not None:
        implementation.controller = adapt_controller(
            controller_factory(config.controller_config)
        )
    return implementation


def _build_implementation(
    envelope: ALBConfigEnvelope,
    dependencies: BearingBuildDependencies | None,
) -> object:
    if not isinstance(envelope, ALBConfigEnvelope):
        raise TypeError("envelope must be ALBConfigEnvelope")
    resolved = dependencies or BearingBuildDependencies()
    factory = resolved.component_factory or _default_component_factory
    config = materialize_current_config(envelope)
    return factory(config, resolved.controller_factory)


def build_alb(
    envelope: ALBConfigEnvelope,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> BearingRuntimeProtocol[BearingInput]:
    """Build a controlled or uncontrolled runtime from a current envelope."""

    if envelope.control_mode is ControlMode.DIRECT_SPOOL:
        raise ValueError(
            "direct_spool configuration requires build_direct_spool_alb()"
        )
    implementation = _build_implementation(envelope, dependencies)
    if not isinstance(implementation, BearingRuntimeProtocol):
        raise TypeError(
            "component_factory must return a BearingRuntimeProtocol runtime"
        )
    return cast(BearingRuntimeProtocol[BearingInput], implementation)


def build_direct_spool_alb(
    envelope: ALBConfigEnvelope,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> DirectSpoolBearingRuntimeProtocol:
    """Build a runtime whose input explicitly includes normalized spool state."""

    if envelope.control_mode is not ControlMode.DIRECT_SPOOL:
        raise ValueError(
            "build_direct_spool_alb() requires direct_spool control_mode"
        )
    implementation = _build_implementation(envelope, dependencies)
    if not isinstance(implementation, DirectSpoolBearingRuntimeProtocol):
        raise TypeError(
            "component_factory must return a direct-spool bearing runtime"
        )
    return cast(DirectSpoolBearingRuntimeProtocol, implementation)


def build_typed_bearing(
    envelope: ALBConfigEnvelope,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> BuiltBearing:
    """Build one discriminated runtime result for file-oriented workflows."""

    if envelope.control_mode is ControlMode.DIRECT_SPOOL:
        return BuiltDirectSpoolBearing(
            build_direct_spool_alb(envelope, dependencies=dependencies)
        )
    runtime = build_alb(envelope, dependencies=dependencies)
    if envelope.control_mode is ControlMode.NONE:
        return BuiltUncontrolledBearing(runtime)
    return BuiltControlledBearing(runtime)


__all__ = [
    "BearingBuildDependencies",
    "BearingComponentFactoryProtocol",
    "BuiltBearing",
    "BuiltControlledBearing",
    "BuiltDirectSpoolBearing",
    "BuiltUncontrolledBearing",
    "ControllerFactoryProtocol",
    "build_alb",
    "build_direct_spool_alb",
    "build_typed_bearing",
]
