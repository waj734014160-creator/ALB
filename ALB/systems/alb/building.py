"""Typed public builders that hide transitional bearing block adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, TypeAlias, cast

from ALB.config import (
    ALBConfig,
    ControlMode,
    CurrentConfig,
    NodimALBConfig,
)
from ALB.config.schema import (
    _current_config_envelope,
    materialize_current_config,
)
from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    DirectSpoolBearingRuntimeProtocol,
    LifecycleState,
)
from ALB.control.adapters import adapt_controller

from .factories import alb2, nodim_alb


class ControllerFactoryProtocol(Protocol):
    """Build one controller from its typed configuration object."""

    def __call__(self, config: object) -> object:
        """Return a controller implementation."""


class BearingComponentFactoryProtocol(Protocol):
    """Assemble one ALB implementation from a typed configuration."""

    def __call__(
        self,
        config: CurrentConfig,
        controller_factory: ControllerFactoryProtocol | None,
    ) -> object:
        """Return a fully wired ALB implementation."""


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
        implementation.init()
    return implementation


def _validated_config(
    config: CurrentConfig,
) -> tuple[CurrentConfig, ControlMode]:
    """Create the internal envelope and return its validated typed config."""

    if not isinstance(config, (ALBConfig, NodimALBConfig)):
        raise TypeError("config must be ALBConfig or NodimALBConfig")
    envelope = _current_config_envelope(config)
    return materialize_current_config(envelope), envelope.control_mode


def _build_implementation(
    validated_config: CurrentConfig,
    dependencies: BearingBuildDependencies | None,
) -> object:
    resolved = dependencies or BearingBuildDependencies()
    factory = resolved.component_factory or _default_component_factory
    implementation = factory(validated_config, resolved.controller_factory)
    if getattr(implementation, "lifecycle_state", None) is LifecycleState.NEW:
        initialize = getattr(implementation, "init", None)
        if not callable(initialize):
            raise TypeError(
                "component_factory returned an uninitialized runtime without init()"
            )
        initialize()
    return implementation


def build_alb(
    config: CurrentConfig,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> BearingRuntimeProtocol[BearingInput]:
    """Build an initialized controlled or uncontrolled runtime.

    The versioned configuration envelope is created and validated internally.
    """

    validated_config, control_mode = _validated_config(config)
    if control_mode is ControlMode.DIRECT_SPOOL:
        raise ValueError(
            "direct_spool configuration requires build_direct_spool_alb()"
        )
    implementation = _build_implementation(validated_config, dependencies)
    if not isinstance(implementation, BearingRuntimeProtocol):
        raise TypeError(
            "component_factory must return a BearingRuntimeProtocol runtime"
        )
    if implementation.lifecycle_state is not LifecycleState.READY:
        raise RuntimeError("component_factory must return a READY runtime")
    return cast(BearingRuntimeProtocol[BearingInput], implementation)


def build_direct_spool_alb(
    config: CurrentConfig,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> DirectSpoolBearingRuntimeProtocol:
    """Build an initialized runtime with explicit normalized spool input."""

    validated_config, control_mode = _validated_config(config)
    if control_mode is not ControlMode.DIRECT_SPOOL:
        raise ValueError(
            "build_direct_spool_alb() requires direct_spool control_mode"
        )
    implementation = _build_implementation(validated_config, dependencies)
    if not isinstance(implementation, DirectSpoolBearingRuntimeProtocol):
        raise TypeError(
            "component_factory must return a direct-spool bearing runtime"
        )
    if implementation.lifecycle_state is not LifecycleState.READY:
        raise RuntimeError("component_factory must return a READY runtime")
    return implementation


def build_typed_bearing(
    config: CurrentConfig,
    *,
    dependencies: BearingBuildDependencies | None = None,
) -> BuiltBearing:
    """Build one initialized discriminated runtime result."""

    envelope = _current_config_envelope(config)
    if envelope.control_mode is ControlMode.DIRECT_SPOOL:
        return BuiltDirectSpoolBearing(
            build_direct_spool_alb(config, dependencies=dependencies)
        )
    runtime = build_alb(config, dependencies=dependencies)
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
