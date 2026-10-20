"""User-facing immutable rotor-bearing simulation API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import math
import os
import warnings
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from ALB.contracts import (
    BearingUnitAdapterProtocol,
    BearingRuntimeProtocol,
    ConvergenceStatus,
    ResultBundle,
    RotorProtocol,
    RunReceipt,
    SpoolCommandProviderProtocol,
    StepContext,
    UnitSystem,
    result_snapshot,
)
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.time import (
    control_steps_per_period,
    fit_time_step_to_control_period,
)
from ALB.core.validation import strict_nonnegative_integer
from ALB.contracts.dynamics import _validate_coupled_rotor_output
from ALB.dynamics.bindings import CouplingRuntimeDependencies
from ALB.dynamics.coupling_runtime import (
    PostCommitObserverError,
    PostCommitRecordingError,
)
from ALB.dynamics.ros2 import INTEGRATORS, Ros2Options

from ._config_fields import (
    GRAVITY_LOAD_FIELDS,
    SIMULATION_DOCUMENT_FIELDS,
    SIMULATION_HISTORY_FIELDS,
    SIMULATION_MOUNT_FIELDS,
    SIMULATION_ROTOR_FIELDS,
    SIMULATION_SPEC_FIELDS,
    SIMULATION_TIME_GRID_FIELDS,
    STATIC_LOAD_FIELDS,
    UNBALANCE_LOAD_FIELDS,
)
from .config import (
    SCHEMA_VERSION,
    BearingConfig,
    _freeze,
    _deep_merge,
    _finite_float,
    _positive_float,
    _read_json5,
    _reject_unknown,
    _require_integer,
    _require_mapping,
    _thaw,
    load_bearing_config,
)
from .errors import (
    ConfigurationError,
    SimulationError,
    TimeStepAdjustedWarning,
)
from .results import SimulationResult


def _normalize_load(value: Any, index: int) -> Mapping[str, Any]:
    """Validate and freeze one documented rotor-load declaration.

    Static loads require ``node`` and a finite two-component ``force``.
    Gravity accepts an optional finite ``acceleration``. Unbalance loads
    require ``node`` and accept ``phase``, ``t_max``, ``m``, ``freq``, ``e``,
    and ``no_step`` using the same names as the rotor excitation model.
    """

    path = f"loads[{index}]"
    load = _require_mapping(value, path)
    load_type = load.get("type")
    if load_type == "static":
        _reject_unknown(load, set(STATIC_LOAD_FIELDS), path)
        static_node = _require_integer(
            load.get("node"),
            f"{path}.node",
            minimum=0,
        )
        try:
            force = np.asarray(load.get("force"), dtype=float)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"{path}.force must contain two real values"
            ) from exc
        if force.shape != (2,) or not np.all(np.isfinite(force)):
            raise ConfigurationError(
                f"{path}.force must contain two finite values"
            )
        normalized: dict[str, Any] = {
            "type": "static",
            "node": static_node,
            "force": force,
        }
    elif load_type == "gravity":
        _reject_unknown(load, set(GRAVITY_LOAD_FIELDS), path)
        normalized = {
            "type": "gravity",
            "acceleration": _finite_float(
                load.get("acceleration", 9.80665),
                f"{path}.acceleration",
            ),
        }
    elif load_type == "unbalance":
        allowed = set(UNBALANCE_LOAD_FIELDS)
        _reject_unknown(load, allowed, path)
        raw_node = load.get("node")
        if isinstance(raw_node, Sequence) and not isinstance(
            raw_node,
            (str, bytes),
        ):
            unbalance_node: int | tuple[int, ...] = tuple(
                _require_integer(item, f"{path}.node[]", minimum=0)
                for item in raw_node
            )
            if not unbalance_node:
                raise ConfigurationError(
                    f"{path}.node must not be an empty sequence"
                )
        else:
            unbalance_node = _require_integer(
                raw_node,
                f"{path}.node",
                minimum=0,
            )
        no_step = load.get("no_step", False)
        if not isinstance(no_step, (bool, np.bool_)):
            raise ConfigurationError(f"{path}.no_step must be a bool")
        normalized = {
            "type": "unbalance",
            "node": unbalance_node,
            "phase": _finite_float(load.get("phase", 0.0), f"{path}.phase"),
            "t_max": _positive_float(
                load.get("t_max", 1.0),
                f"{path}.t_max",
            ),
            "m": _finite_float(load.get("m", 0.0), f"{path}.m"),
            "freq": _finite_float(load.get("freq", 0.0), f"{path}.freq"),
            "e": _finite_float(load.get("e", 0.0), f"{path}.e"),
            "no_step": bool(no_step),
        }
    else:
        raise ConfigurationError(
            f"{path}.type must be static, gravity, or unbalance"
        )
    return cast(Mapping[str, Any], _freeze(normalized))


@dataclass(frozen=True, slots=True)
class BearingMount:
    """Bind one immutable bearing configuration to a unique rotor node.

    ``node`` is the nonnegative rotor node used for displacement input and
    bearing-force feedback. Dimensional bearings normally need no adapter;
    a nondimensional bearing requires a ``BearingUnitAdapterProtocol`` that
    converts step context, kinematics, and force. Bearings using
    ``external_spool`` also require a ``SpoolCommandProviderProtocol``.
    """

    config: BearingConfig
    node: int
    unit_adapter: BearingUnitAdapterProtocol | None = None
    spool_provider: SpoolCommandProviderProtocol | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.config, BearingConfig):
            raise TypeError("config must be BearingConfig")
        strict_nonnegative_integer(self.node, "node")


@dataclass(frozen=True, slots=True)
class HistoryPolicy:
    """Select committed simulation fields, sampling, and storage.

    ``memory`` retains all selected samples, ``ring_buffer`` retains the latest
    ``capacity`` samples, and ``disk_stream`` writes selected samples below
    ``directory`` instead of returning their arrays in memory. ``downsample``
    keeps committed indices divisible by that positive integer, including the
    initial index zero. Available fields are ``rotor_displacement``,
    ``rotor_velocity``, and ``bearing_force``.
    """

    mode: Literal["memory", "ring_buffer", "disk_stream"] = "memory"
    fields: tuple[str, ...] = (
        "rotor_displacement",
        "rotor_velocity",
        "bearing_force",
    )
    downsample: int = 1
    capacity: int | None = None
    directory: Path | None = None

    def __post_init__(self) -> None:
        allowed = {
            "rotor_displacement",
            "rotor_velocity",
            "bearing_force",
        }
        fields = tuple(self.fields)
        unknown = sorted(set(fields) - allowed)
        if unknown or not fields:
            raise ValueError(f"history fields are invalid: {unknown}")
        if (
            isinstance(self.downsample, bool)
            or not isinstance(self.downsample, int)
            or self.downsample < 1
        ):
            raise ValueError("downsample must be a positive integer")
        if self.mode not in {"memory", "ring_buffer", "disk_stream"}:
            raise ValueError(
                "history mode must be memory, ring_buffer, or disk_stream"
            )
        if self.mode == "ring_buffer":
            if (
                self.capacity is None
                or isinstance(self.capacity, bool)
                or not isinstance(self.capacity, int)
                or self.capacity < 1
            ):
                raise ValueError(
                    "ring_buffer history requires a positive capacity"
                )
        elif self.capacity is not None:
            raise ValueError("capacity is accepted only by ring_buffer history")
        if self.mode == "disk_stream":
            if self.directory is None:
                raise ValueError("disk_stream history requires a directory")
            object.__setattr__(self, "directory", Path(self.directory).resolve())
        elif self.directory is not None:
            raise ValueError("directory is accepted only by disk_stream history")
        object.__setattr__(self, "fields", fields)


def _local_time_step(
    mount: BearingMount,
    index: int,
    time_step: float,
) -> float:
    """Return the bearing-local step produced for one global ``time_step``."""

    if mount.unit_adapter is None:
        return time_step
    try:
        local_context = mount.unit_adapter.rotor_context_to_bearing(
            StepContext(0, 0.0, time_step, UnitSystem.DIMENSIONAL)
        )
    except Exception as exc:
        raise ConfigurationError(
            f"mounts[{index}].unit_adapter could not convert "
            f"simulation time_step: {exc}"
        ) from exc
    if not isinstance(local_context, StepContext):
        raise ConfigurationError(
            f"mounts[{index}].unit_adapter must return StepContext"
        )
    if local_context.unit_system.value != mount.config.unit_system:
        raise ConfigurationError(
            f"mounts[{index}].unit_adapter local unit_system must "
            "match the bearing config"
        )
    local_step = float(local_context.dt)
    if not np.isfinite(local_step) or local_step <= 0.0:
        raise ConfigurationError(
            f"mounts[{index}].unit_adapter produced an invalid "
            "bearing-local time_step"
        )
    return local_step


def _validate_integrator(
    integrator: object,
    options: object,
) -> str:
    """Validate the integrator name and its optional ROS2 options."""

    if integrator not in INTEGRATORS:
        raise ConfigurationError(
            "integrator must be 'staggered' or 'ros2'"
        )
    if options is not None and not isinstance(options, Ros2Options):
        raise TypeError("ros2 must be Ros2Options or None")
    if options is not None and integrator != "ros2":
        raise ConfigurationError(
            "ros2 options are accepted only with integrator='ros2'"
        )
    return str(integrator)


def _validate_ros2_topology(
    rotor: RotorProtocol,
    mounts: Sequence[BearingMount],
) -> None:
    """Reject rotors and bearing families that ROS2 cannot integrate."""

    from .building import _ros2_support_issue

    hooks = (
        "_continuous_system",
        "_node_state_indices",
        "_node_force_vector",
        "_commit_integrated_state",
    )
    missing = [name for name in hooks if not callable(getattr(rotor, name, None))]
    if missing:
        raise ConfigurationError(
            "integrator='ros2' requires a rotor providing the owner hooks "
            f"{', '.join(hooks)} (missing {', '.join(missing)}), such as a "
            "continuous RossRotor"
        )
    continuous = getattr(rotor, "_continuous_system")
    try:
        continuous()
    except ValueError as exc:
        raise ConfigurationError(
            f"integrator='ros2' requires a continuous rotor model: {exc}"
        ) from exc
    for index, mount in enumerate(mounts):
        issue = _ros2_support_issue(mount.config, f"mounts[{index}].config")
        if issue is not None:
            raise ConfigurationError(
                f"integrator='ros2' cannot integrate this bearing: {issue}. "
                "Use integrator='staggered' for this topology."
            )


def _initial_rotor_state(rotor: RotorProtocol, value: Any) -> Any:
    """Validate an optional complete initial rotor state vector."""

    if value is None:
        return None
    try:
        state = np.array(value, dtype=float, copy=True)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            "initial_rotor_state must be a real vector"
        ) from exc
    current = np.asarray(rotor.current_state(), dtype=float).reshape(-1)
    if state.shape != current.shape:
        raise ConfigurationError(
            "initial_rotor_state must match the complete rotor state shape "
            f"{current.shape}; got {state.shape}"
        )
    if not np.all(np.isfinite(state)):
        raise ConfigurationError(
            "initial_rotor_state must contain finite values"
        )
    state.setflags(write=False)
    return state


def _adjustment_message(adjustment: Mapping[str, Any]) -> str:
    """Return the user-facing warning text for one step adjustment."""

    return (
        "simulation time_step "
        f"{adjustment['requested_time_step']!r} s is not an integer divisor "
        f"of control_period {adjustment['control_period']!r} s; using "
        f"time_step {adjustment['time_step']!r} s with "
        f"{adjustment['control_steps_per_period']} step(s) per control "
        f"period and {adjustment['steps']} steps instead of "
        f"{adjustment['requested_steps']} (end time "
        f"{adjustment['end_time']!r} s, requested "
        f"{adjustment['requested_end_time']!r} s)"
    )


def _plan_control_periods(
    rotor: RotorProtocol,
    mounts: tuple[BearingMount, ...],
    time_step: float,
    steps: int,
) -> tuple[
    tuple[BearingMount, ...],
    float,
    int,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
]:
    """Make every controller period an integer multiple of the global step.

    Controller periods ``Ts`` come from ``control.control_period`` in each
    mounted bearing tree and are converted to global time through the mount's
    unit adapter. Without periods, or when ``time_step`` already divides each
    ``Ts`` (``|r - round(r)| <= 1e-9 r``), nothing changes. Otherwise ``Ts`` is
    kept and the step becomes ``h' = Ts / ceil(Ts / h)`` (``Ts`` if ``h > Ts``);
    the step count is recomputed from the requested end time and rounded up to
    whole control periods. Every bearing config is rebuilt for ``h'``; the
    caller retimes the rotor in place after all validation has passed so all
    physical components share ``h'`` (ADR-0009).
    """

    from .building import _control_period_declarations, _retime_bearing_config

    declarations: list[dict[str, Any]] = []
    for index, mount in enumerate(mounts):
        local_step = _local_time_step(mount, index, time_step)
        time_scale = time_step / local_step
        for path, local_period in _control_period_declarations(
            mount.config,
            f"mounts[{index}].config",
        ):
            declarations.append(
                {
                    "mount": index,
                    "path": path,
                    "local_control_period": local_period,
                    "control_period": local_period * time_scale,
                }
            )
    if not declarations:
        return mounts, time_step, steps, (), None

    def describe(step: float) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            cast(
                Mapping[str, Any],
                _freeze(
                    {
                        **item,
                        "control_steps_per_period": control_steps_per_period(
                            item["control_period"],
                            step,
                        ),
                    }
                ),
            )
            for item in declarations
        )

    if all(
        control_steps_per_period(item["control_period"], time_step) is not None
        for item in declarations
    ):
        return mounts, time_step, steps, describe(time_step), None

    periods = [float(item["control_period"]) for item in declarations]
    reference_period = periods[0]
    if any(
        not math.isclose(period, reference_period, rel_tol=1.0e-9, abs_tol=0.0)
        for period in periods[1:]
    ):
        raise ConfigurationError(
            "time_step must divide every control_period exactly when "
            "several different control periods are configured; automatic "
            "time-step adjustment supports one control period "
            f"(found {sorted(set(periods))!r})"
        )
    adjusted_step, control_steps = fit_time_step_to_control_period(
        reference_period,
        time_step,
    )
    requested_end_time = steps * time_step
    periods_count = math.ceil(
        requested_end_time / reference_period - 1.0e-9
    )
    adjusted_steps = max(0, periods_count) * control_steps
    if not callable(getattr(rotor, "_retime_for_owner", None)):
        raise ConfigurationError(
            f"time_step {time_step!r} must be adjusted to {adjusted_step!r} "
            "to divide control_period, but the rotor does not provide "
            "_retime_for_owner(dt); choose time_step = control_period / m"
        )
    retimed: list[BearingMount] = []
    for index, mount in enumerate(mounts):
        retimed.append(
            BearingMount(
                _retime_bearing_config(
                    mount.config,
                    _local_time_step(mount, index, adjusted_step),
                    path=f"mounts[{index}].config",
                ),
                mount.node,
                unit_adapter=mount.unit_adapter,
                spool_provider=mount.spool_provider,
            )
        )
    adjustment = cast(
        Mapping[str, Any],
        _freeze(
            {
                "requested_time_step": time_step,
                "requested_steps": steps,
                "requested_end_time": requested_end_time,
                "control_period": reference_period,
                "time_step": adjusted_step,
                "control_steps_per_period": control_steps,
                "steps": adjusted_steps,
                "end_time": adjusted_steps * adjusted_step,
                "rule": (
                    "h' = Ts / ceil(Ts / h), or h' = Ts when h > Ts; "
                    "steps = m * ceil(T / Ts)"
                ),
            }
        ),
    )
    return (
        tuple(retimed),
        adjusted_step,
        adjusted_steps,
        describe(adjusted_step),
        adjustment,
    )


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Validate immutable inputs for one dimensional rotor simulation.

    ``rotor`` must satisfy ``ALB.contracts.RotorProtocol`` and its ``dt`` must
    equal ``time_step``. ``mounts`` contains at least one ``BearingMount`` with
    unique nodes. ``steps`` counts advances after the initial committed state,
    so memory history normally contains ``steps + 1`` samples.

    Each load is a mapping with one of these shapes (SI units):

    * ``{"type": "static", "node": int, "force": [Fx, Fy]}``;
    * ``{"type": "gravity", "acceleration": 9.80665}``;
    * ``{"type": "unbalance", "node": int | [int, ...], "phase": 0,
      "t_max": 1, "m": 0, "freq": 0, "e": 0, "no_step": False}``.

    Static and unbalance nodes are nonnegative. Load declarations are copied
    and frozen during construction. ``history`` controls returned or streamed
    fields. ``dependencies`` is an advanced runtime hook imported as
    ``ALB.dynamics.CouplingRuntimeDependencies``; ordinary simulations leave it
    as ``None``. The resulting ``RotorBearingSimulation`` is one-shot.

    Rotor time uses the global dimensional step. Each mounted bearing uses the
    step produced by its explicit unit adapter, and its entire materialized
    configuration tree must agree with that bearing-local value. Topology and
    load declarations are frozen; the supplied rotor, adapters, and optional
    runtime dependencies remain owner-managed runtime objects.
    """

    rotor: RotorProtocol
    mounts: tuple[BearingMount, ...]
    time_step: float
    steps: int
    loads: tuple[Mapping[str, Any], ...] = ()
    history: HistoryPolicy = HistoryPolicy()
    dependencies: CouplingRuntimeDependencies | None = None
    integrator: Literal["staggered", "ros2"] = "staggered"
    ros2: Ros2Options | None = None
    initial_rotor_state: Any = None
    control_periods: tuple[Mapping[str, Any], ...] = field(
        default=(),
        init=False,
        compare=False,
    )
    time_step_adjustment: Mapping[str, Any] | None = field(
        default=None,
        init=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.rotor, RotorProtocol):
            raise TypeError("rotor must satisfy RotorProtocol")
        mounts = tuple(self.mounts)
        if not mounts or any(not isinstance(item, BearingMount) for item in mounts):
            raise ValueError("mounts must contain at least one BearingMount")
        nodes = [item.node for item in mounts]
        if len(set(nodes)) != len(nodes):
            raise ValueError("bearing mount nodes must be unique")
        time_step = _positive_float(self.time_step, "time_step")
        try:
            normalized_rotor_time_step = _positive_float(
                self.rotor.dt,
                "rotor.dt",
            )
        except ConfigurationError as exc:
            raise ConfigurationError(
                "rotor.dt must be a finite positive number"
            ) from exc
        try:
            rotor_unit = UnitSystem.coerce(self.rotor.unit_system)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                "rotor.unit_system must be dimensional"
            ) from exc
        if rotor_unit is not UnitSystem.DIMENSIONAL:
            raise ConfigurationError(
                "rotor.unit_system must be dimensional for simulation"
            )
        if normalized_rotor_time_step != time_step:
            raise ConfigurationError(
                "rotor.dt must equal simulation time_step "
                f"{time_step!r}; got {normalized_rotor_time_step!r}"
            )
        integrator = _validate_integrator(self.integrator, self.ros2)
        steps = strict_nonnegative_integer(self.steps, "steps")
        from .building import _validate_runtime_time_steps

        rotor: RotorProtocol = self.rotor
        # The requested configuration must already share one step (ADR-0007
        # rule 8) before a controller period may adjust that step.
        for index, mount in enumerate(mounts):
            _validate_runtime_time_steps(
                mount.config,
                _local_time_step(mount, index, time_step),
                path=f"mounts[{index}].config",
                check_control_period=False,
            )
        (
            mounts,
            time_step,
            steps,
            control_periods,
            adjustment,
        ) = _plan_control_periods(rotor, mounts, time_step, steps)
        for index, mount in enumerate(mounts):
            _validate_runtime_time_steps(
                mount.config,
                _local_time_step(mount, index, time_step),
                path=f"mounts[{index}].config",
            )
        if integrator == "ros2":
            _validate_ros2_topology(rotor, mounts)
        initial_state = _initial_rotor_state(rotor, self.initial_rotor_state)
        try:
            _validate_coupled_rotor_output(
                rotor.output(nodes),
                len(nodes),
                label="rotor.output(nodes)",
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"rotor.output(nodes) is invalid: {exc}"
            ) from exc
        loads = tuple(
            _normalize_load(item, index)
            for index, item in enumerate(self.loads)
        )
        if not isinstance(self.history, HistoryPolicy):
            raise TypeError("history must be HistoryPolicy")
        if self.dependencies is not None and not isinstance(
            self.dependencies,
            CouplingRuntimeDependencies,
        ):
            raise TypeError(
                "dependencies must be CouplingRuntimeDependencies or None"
            )
        if adjustment is not None:
            # Retime last so a rejected configuration never mutates the rotor.
            try:
                rotor._retime_for_owner(time_step)  # type: ignore[attr-defined]
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(
                    f"rotor could not be retimed to time_step {time_step!r}: "
                    f"{exc}"
                ) from exc
            if float(rotor.dt) != time_step:
                raise ConfigurationError(
                    "rotor.dt must equal the adjusted simulation time_step "
                    f"{time_step!r}; got {rotor.dt!r}"
                )
        object.__setattr__(self, "rotor", rotor)
        object.__setattr__(self, "mounts", mounts)
        object.__setattr__(self, "time_step", time_step)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "loads", loads)
        object.__setattr__(self, "integrator", integrator)
        object.__setattr__(self, "control_periods", control_periods)
        object.__setattr__(self, "time_step_adjustment", adjustment)
        object.__setattr__(self, "initial_rotor_state", initial_state)
        if adjustment is not None:
            warnings.warn(
                TimeStepAdjustedWarning(
                    _adjustment_message(adjustment),
                    adjustment=adjustment,
                ),
                stacklevel=3,
            )


class RotorBearingSimulation:
    """Ready one-shot simulation with immutable topology.

    ``run()`` commits the initial state at time zero and then performs the
    configured number of advances. A second call raises ``RuntimeError``;
    construct a new simulation to repeat or change a run. Access
    ``latest_result`` only after successful completion.
    """

    __slots__ = ("_config", "_coupling", "_has_run", "_last_result")

    def __init__(self, config: SimulationConfig) -> None:
        if not isinstance(config, SimulationConfig):
            raise TypeError("config must be SimulationConfig")
        self._config = config
        self._coupling = self._build_coupling()
        self._has_run = False
        self._last_result: SimulationResult | None = None

    @property
    def config(self) -> SimulationConfig:
        """Return the immutable topology, loads, and history policy.

        Runtime-owned rotor, adapters, and dependencies remain the same objects;
        declarative mappings and sequences were copied and frozen at validation.
        """

        return self._config

    @property
    def latest_result(self) -> SimulationResult:
        """Return the latest complete or partial committed simulation history.

        A failed run may publish a partial result containing every safely retained
        committed step. Access before a successful or failed run raises.

        Raises
        ------
        RuntimeError
            If :meth:`run` has not produced any result boundary.
        """

        if self._last_result is None:
            raise RuntimeError("no simulation result is available")
        return self._last_result

    def _build_coupling(self) -> Any:
        from ALB.core.time import TimeIterDt
        from ALB.dynamics.bindings import CoupledBearingBinding
        from ALB.dynamics.coupling import _RotorBearingStepRuntime
        from .building import build_runtime

        bindings = []
        for mount in self._config.mounts:
            bindings.append(
                CoupledBearingBinding(
                    cast(
                        BearingRuntimeProtocol[Any],
                        build_runtime(mount.config),
                    ),
                    node_link=mount.node,
                    unit_adapter=mount.unit_adapter,
                    spool_provider=mount.spool_provider,
                )
            )
        kwargs: dict[str, object] = {}
        if self._config.dependencies is not None:
            kwargs["dependencies"] = self._config.dependencies
        if self._config.integrator != "staggered":
            kwargs["integrator"] = self._config.integrator
            kwargs["ros2_options"] = self._config.ros2
        if self._config.initial_rotor_state is not None:
            kwargs["initial_rotor_state"] = self._config.initial_rotor_state
        coupling = _RotorBearingStepRuntime(
            cast(Any, self._config.rotor),
            TimeIterDt(self._config.time_step, self._config.steps),
            *bindings,
            **kwargs,
        )
        for load in self._config.loads:
            load_type = load.get("type")
            if load_type == "static":
                coupling.add_static_force(  # type: ignore[no-untyped-call]
                    load["force"],
                    int(load["node"]),
                )
            elif load_type == "gravity":
                coupling.add_gravity(  # type: ignore[no-untyped-call]
                    float(load.get("acceleration", 9.80665))
                )
            elif load_type == "unbalance":
                values = dict(load)
                values.pop("type")
                if "node" in values:
                    values["node_link"] = values.pop("node")
                coupling.add_unbalance(**values)
            else:
                raise ConfigurationError(
                    "load type must be static, gravity, or unbalance"
                )
        return coupling

    def run(self) -> SimulationResult:
        """Run once and retain every policy-selected committed snapshot.

        A post-commit failure never repeats physics or advances another step.
        The raised ``SimulationError`` includes the committed output hidden by
        the exception plus independent physical, history, and post-commit
        completion diagnostics.
        """

        if self._has_run:
            raise SimulationError(
                "simulation instances are one-shot; build a new simulation "
                "for another run"
            )
        coupling = self._coupling
        policy = self._config.history
        snapshots: list[Any] = []
        retained_indices: set[int] = set()
        stream_records: list[dict[str, Any]] = []
        stream_root: Path | None = None
        committed_steps = 0
        last_snapshot: Any | None = None
        last_index = -1
        run_close_receipt: RunReceipt | None = None
        failure_phase = "setup"
        persistence_secondary_errors: list[dict[str, str]] = []

        if policy.mode == "disk_stream":
            assert policy.directory is not None
            stream_root = policy.directory
            if stream_root.exists() and any(stream_root.iterdir()):
                raise SimulationError(
                    f"history directory is not empty: {stream_root}"
                )
            stream_root.mkdir(parents=True, exist_ok=True)
        self._has_run = True

        def write_snapshot(
            snapshot: Any,
            index: int,
        ) -> dict[str, Any]:
            """Atomically persist one filtered snapshot in the stream root."""

            assert stream_root is not None
            file_name = f"step_{index:08d}.npz"
            target = stream_root / file_name
            temporary = stream_root / f".{file_name}.tmp.npz"
            payload: dict[str, Any] = {
                "time": np.asarray(
                    [float(snapshot.metadata["time"])],
                    dtype=float,
                )
            }
            for field in policy.fields:
                payload[field] = np.asarray(snapshot.values[field])
            try:
                with temporary.open("xb") as stream:
                    np.savez_compressed(stream, **payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(target)
            except BaseException:
                try:
                    temporary.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    persistence_secondary_errors.append(
                        {
                            "phase": "history_snapshot_cleanup",
                            "error_type": type(cleanup_error).__name__,
                            "message": sanitize_exception_message(
                                cleanup_error
                            ),
                        }
                    )
                raise
            return {
                "step_index": index,
                "time": float(snapshot.metadata["time"]),
                "file": file_name,
            }

        def retain(snapshot: Any, index: int, *, force: bool = False) -> None:
            if index in retained_indices:
                return
            if not force and index % policy.downsample != 0:
                return
            if stream_root is not None:
                record = write_snapshot(snapshot, index)
                stream_records.append(record)
                retained_indices.add(index)
                return
            snapshots.append(snapshot)
            retained_indices.add(index)
            if policy.mode == "ring_buffer":
                assert policy.capacity is not None
                while len(snapshots) > policy.capacity:
                    snapshots.pop(0)
                    retained_indices.discard(min(retained_indices))

        def finalize_stream(*, complete: bool) -> None:
            if stream_root is None:
                return
            manifest = {
                "schema": "alb.simulation-history.v0.4",
                "complete": complete,
                "committed_steps": committed_steps,
                "fields": list(policy.fields),
                "downsample": policy.downsample,
                "records": stream_records,
            }
            target = stream_root / "history.json"
            temporary = stream_root / ".history.json.tmp"
            try:
                with temporary.open(
                    "x",
                    encoding="utf-8",
                    newline="\n",
                ) as stream:
                    stream.write(
                        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(target)
            except BaseException:
                try:
                    temporary.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    persistence_secondary_errors.append(
                        {
                            "phase": "history_manifest_cleanup",
                            "error_type": type(cleanup_error).__name__,
                            "message": sanitize_exception_message(
                                cleanup_error
                            ),
                        }
                    )
                raise

        def coupling_diagnostics() -> tuple[dict[str, Any], dict[str, Any]]:
            """Return primitive coupling values and metadata without mutation."""

            try:
                diagnostic = coupling.diagnostic_snapshot()
            except Exception:
                return {}, {}
            return dict(diagnostic.values), dict(diagnostic.metadata)

        def reconcile_committed_output() -> None:
            """Publish a post-commit output that an exception hid from the loop."""

            nonlocal committed_steps, last_index, last_snapshot
            _, metadata = coupling_diagnostics()
            committed_index = metadata.get("committed_step_index")
            if (
                isinstance(committed_index, int)
                and committed_index > last_index
            ):
                current = coupling.output()
                last_snapshot = current
                last_index = committed_index
                committed_steps = committed_index + 1

        def close_run(*, allow_incomplete: bool) -> RunReceipt:
            """Close the low-level recorder run and return its actual receipt."""

            return cast(
                RunReceipt,
                coupling.end_run(allow_incomplete=allow_incomplete),
            )

        def build_failure_snapshot(
            error: BaseException,
            *,
            phase: str,
            partial: SimulationResult,
            secondary_errors: Sequence[Mapping[str, str]],
            history_complete: bool,
        ) -> ResultBundle:
            """Seal physical, recording, observer, and persistence diagnostics."""

            diagnostic_values, diagnostic_metadata = coupling_diagnostics()
            coupling_failure: ResultBundle | None = None
            get_coupling_failure = getattr(coupling, "failure_snapshot", None)
            if callable(get_coupling_failure):
                try:
                    candidate = get_coupling_failure()
                    if isinstance(candidate, ResultBundle):
                        coupling_failure = candidate
                except Exception:
                    coupling_failure = None
            values: dict[str, Any] = {
                "partial_time": partial.time,
                "observer_failures": diagnostic_values.get(
                    "observer_failures",
                    (),
                ),
            }
            if coupling_failure is not None:
                values["coupling_failure"] = {
                    "values": coupling_failure.values,
                    "metadata": coupling_failure.metadata,
                }
            if last_snapshot is not None:
                values["last_bearing_force"] = np.asarray(
                    last_snapshot.values["bearing_force"]
                )
                values["last_rotor_displacement"] = np.asarray(
                    last_snapshot.values["rotor_displacement"]
                )
                values["last_rotor_velocity"] = np.asarray(
                    last_snapshot.values["rotor_velocity"]
                )
            observer_failures = diagnostic_values.get("observer_failures", ())
            close_status = (
                None
                if (
                    run_close_receipt is None
                    or run_close_receipt.close_status is None
                )
                else run_close_receipt.close_status.value
            )
            close_pending_keys = (
                ()
                if run_close_receipt is None
                else tuple(
                    {
                        "run_id": key.run_id,
                        "step_index": key.step_index,
                    }
                    for key in run_close_receipt.pending_keys
                )
            )
            if phase in {"reset", "advance"}:
                failed_step_committed = bool(
                    getattr(error, "physical_step_committed", False)
                )
            else:
                failed_step_committed = last_snapshot is not None
            return result_snapshot(
                values,
                {
                    "schema": "alb.simulation-failure.v0.4.2",
                    "failure_phase": phase,
                    "error_type": type(error).__name__,
                    "message": sanitize_exception_message(error),
                    "physical_step_committed": failed_step_committed,
                    "committed_step_index": diagnostic_metadata.get(
                        "committed_step_index",
                        None if committed_steps == 0 else committed_steps - 1,
                    ),
                    "committed_steps": committed_steps,
                    "requested_steps": self._config.steps + 1,
                    "physical_complete": (
                        committed_steps == self._config.steps + 1
                    ),
                    "history_complete": history_complete,
                    "post_commit_complete": False,
                    "recording_status": diagnostic_metadata.get(
                        "recording_status"
                    ),
                    "pending_record_key": diagnostic_metadata.get(
                        "pending_record_key"
                    ),
                    "observer_failure_count": len(observer_failures),
                    "run_close_status": close_status,
                    "run_close_record_count": (
                        None
                        if run_close_receipt is None
                        else run_close_receipt.record_count
                    ),
                    "run_close_pending_keys": close_pending_keys,
                    "run_close_first_step_index": (
                        None
                        if run_close_receipt is None
                        else run_close_receipt.first_step_index
                    ),
                    "run_close_last_step_index": (
                        None
                        if run_close_receipt is None
                        else run_close_receipt.last_step_index
                    ),
                    "secondary_errors": tuple(secondary_errors),
                    "coupling_failure_available": (
                        coupling_failure is not None
                    ),
                    **self._time_metadata(),
                },
            )

        try:
            failure_phase = "reset"
            coupling._reset_for_owner()
            last_snapshot = coupling.output()
            last_index = 0
            committed_steps = 1
            failure_phase = "history_snapshot"
            retain(last_snapshot, last_index)
            for step_index in range(1, self._config.steps + 1):
                context = StepContext(
                    step_index,
                    self._config.time_step * step_index,
                    self._config.time_step,
                    UnitSystem.DIMENSIONAL,
                )
                failure_phase = "advance"
                last_snapshot = coupling.advance(context)
                last_index = step_index
                committed_steps += 1
                failure_phase = "history_snapshot"
                retain(last_snapshot, last_index)
            if last_snapshot is not None:
                failure_phase = "history_snapshot"
                retain(last_snapshot, last_index, force=True)
            failure_phase = "run_close"
            run_close_receipt = close_run(allow_incomplete=False)
            failure_phase = "history_manifest"
            finalize_stream(complete=True)
        except Exception as exc:
            secondary_errors = persistence_secondary_errors
            if isinstance(
                exc,
                (PostCommitRecordingError, PostCommitObserverError),
            ):
                try:
                    reconcile_committed_output()
                except Exception as reconcile_error:
                    secondary_errors.append(
                        {
                            "phase": "post_commit_reconcile",
                            "error_type": type(reconcile_error).__name__,
                            "message": sanitize_exception_message(
                                reconcile_error
                            ),
                        }
                    )
            history_complete = True
            if last_snapshot is not None:
                try:
                    retain(last_snapshot, last_index, force=True)
                except Exception as retain_error:
                    history_complete = False
                    secondary_errors.append(
                        {
                            "phase": "history_snapshot_retry",
                            "error_type": type(retain_error).__name__,
                            "message": sanitize_exception_message(retain_error),
                        }
                    )
            if run_close_receipt is None:
                try:
                    run_close_receipt = close_run(allow_incomplete=True)
                except Exception as close_error:
                    secondary_errors.append(
                        {
                            "phase": "run_close",
                            "error_type": type(close_error).__name__,
                            "message": sanitize_exception_message(close_error),
                        }
                    )
            try:
                finalize_stream(complete=False)
            except Exception as manifest_error:
                history_complete = False
                secondary_errors.append(
                    {
                        "phase": "history_manifest_retry",
                        "error_type": type(manifest_error).__name__,
                        "message": sanitize_exception_message(manifest_error),
                    }
                )
            physical_complete = committed_steps == self._config.steps + 1
            partial = self._to_result(
                snapshots,
                committed_steps=committed_steps,
                complete=physical_complete,
                history_complete=history_complete,
                post_commit_complete=False,
                stream_records=stream_records,
                stream_root=stream_root,
            )
            self._last_result = partial
            error = SimulationError(
                "rotor-bearing simulation failed: "
                f"{sanitize_exception_message(exc)}",
                partial_result=partial,
            )
            error.failure_snapshot = build_failure_snapshot(
                exc,
                phase=failure_phase,
                partial=partial,
                secondary_errors=secondary_errors,
                history_complete=history_complete,
            )
            raise error from exc
        result = self._to_result(
            snapshots,
            committed_steps=committed_steps,
            complete=True,
            history_complete=True,
            post_commit_complete=True,
            stream_records=stream_records,
            stream_root=stream_root,
        )
        self._last_result = result
        return result

    def _time_metadata(self) -> dict[str, Any]:
        """Return integrator, step, and control-period run metadata."""

        config = self._config
        if (
            config.integrator == "staggered"
            and not config.control_periods
            and config.initial_rotor_state is None
        ):
            # The 0.4.5 default path keeps its exact metadata contract.
            return {}
        return {
            "integrator": config.integrator,
            "time_step": config.time_step,
            "control_periods": config.control_periods,
            "time_step_adjustment": config.time_step_adjustment,
            "ros2_options": (
                None
                if config.integrator != "ros2"
                else _freeze(
                    (config.ros2 or Ros2Options()).to_dict()
                )
            ),
            "initial_rotor_state": (
                None
                if config.initial_rotor_state is None
                else "user-supplied"
            ),
        }

    def _to_result(
        self,
        snapshots: Sequence[Any],
        *,
        committed_steps: int,
        complete: bool,
        history_complete: bool,
        post_commit_complete: bool,
        stream_records: Sequence[Mapping[str, Any]],
        stream_root: Path | None,
    ) -> SimulationResult:
        policy = self._config.history
        if stream_root is None:
            time = np.asarray(
                [float(item.metadata["time"]) for item in snapshots],
                dtype=float,
            )
        else:
            time = np.asarray(
                [float(item["time"]) for item in stream_records],
                dtype=float,
            )

        def collect(field: str) -> np.ndarray[Any, np.dtype[np.float64]]:
            if field not in policy.fields or stream_root is not None:
                return np.empty((time.size, 0), dtype=float)
            return np.asarray([item.values[field] for item in snapshots])

        return SimulationResult(
            time=time,
            rotor_displacement=collect("rotor_displacement"),
            rotor_velocity=collect("rotor_velocity"),
            bearing_force=collect("bearing_force"),
            metadata={
                "complete": complete,
                "history_complete": history_complete,
                "post_commit_complete": post_commit_complete,
                "committed_steps": committed_steps,
                "requested_steps": self._config.steps + 1,
                "history_mode": policy.mode,
                "history_downsample": policy.downsample,
                "history_fields": policy.fields,
                "history_path": (
                    None if stream_root is None else str(stream_root)
                ),
                **self._time_metadata(),
            },
            convergence=ConvergenceStatus(
                residual=0.0,
                converged=complete,
                iterations=committed_steps,
                message=(
                    "all requested steps committed"
                    if complete
                    else "simulation stopped after the last committed step"
                ),
            ),
        )


def _load_simulation_document(
    path: Path,
    *,
    root: Path,
    stack: tuple[Path, ...],
    included: set[Path],
    top_level: bool,
) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError(
            f"include escapes the configuration root: {path}"
        ) from exc
    if resolved in stack:
        raise ConfigurationError("simulation configuration include cycle")
    if not top_level and resolved in included:
        raise ConfigurationError(f"duplicate configuration include: {resolved}")
    if not resolved.is_file():
        raise ConfigurationError(f"configuration file does not exist: {resolved}")
    payload = _read_json5(resolved)
    _reject_unknown(
        payload,
        set(SIMULATION_DOCUMENT_FIELDS),
        "document",
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ConfigurationError(f"schema_version must be {SCHEMA_VERSION!r}")
    expected = "simulation" if top_level else "simulation_profile"
    if payload.get("kind") != expected:
        raise ConfigurationError(f"document kind must be {expected!r}")
    if not top_level:
        included.add(resolved)
    raw_includes = payload.get("includes", [])
    if not isinstance(raw_includes, Sequence) or isinstance(
        raw_includes,
        (str, bytes),
    ):
        raise ConfigurationError("document.includes must be a list of paths")
    merged: dict[str, Any] = {}
    for raw in raw_includes:
        if not isinstance(raw, str) or not raw:
            raise ConfigurationError("configuration include must be a path")
        child = Path(raw)
        if child.is_absolute():
            raise ConfigurationError("configuration includes must be relative")
        merged = _deep_merge(
            merged,
            _load_simulation_document(
                resolved.parent / child,
                root=root,
                stack=(*stack, resolved),
                included=included,
                top_level=False,
            ),
        )
    return _deep_merge(
        merged,
        _require_mapping(payload.get("spec", {}), "document.spec"),
    )


def load_simulation_config(path: str | Path) -> SimulationConfig:
    """Load and materialize one strict UTF-8 ALB 0.4 simulation document.

    Parameters
    ----------
    path
        Top-level JSON5 file with ``schema_version='0.4.0'`` and
        ``kind='simulation'``. Relative ``simulation_profile`` includes, the
        ROSS Excel rotor, mounted bearing documents, and an optional disk-history
        directory must remain below the outer document directory.

    Returns
    -------
    SimulationConfig
        Fully validated immutable programmatic configuration containing a
        dimensional ``RossRotor``, bearing mounts, loads, and history policy.

    Raises
    ------
    ConfigurationError
        If the document/include graph, resource containment, fields, values,
        rotor, mounts, time grid, loads, or history policy is invalid.
    ImportError
        If JSON5, ROSS, or another required optional dependency is unavailable.
    FileNotFoundError
        If a declared rotor or bearing resource is absent in a downstream loader.

    Notes
    -----
    File configuration intentionally cannot serialize adapters, spool providers,
    recorders, or observers. Construct :class:`SimulationConfig` directly when
    those advanced runtime objects are required.
    """

    source = Path(path).resolve()
    spec = _load_simulation_document(
        source,
        root=source.parent,
        stack=(),
        included=set(),
        top_level=True,
    )
    _reject_unknown(
        spec,
        set(SIMULATION_SPEC_FIELDS),
        "spec",
    )
    rotor_spec = _require_mapping(spec.get("rotor"), "spec.rotor")
    _reject_unknown(
        rotor_spec,
        set(SIMULATION_ROTOR_FIELDS),
        "spec.rotor",
    )
    if rotor_spec.get("model") != "ross_excel":
        raise ConfigurationError("spec.rotor.model must be 'ross_excel'")
    raw_path = rotor_spec.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise ConfigurationError("spec.rotor.path must be a relative path")
    rotor_path = (source.parent / raw_path).resolve()
    try:
        rotor_path.relative_to(source.parent)
    except ValueError as exc:
        raise ConfigurationError(
            "rotor resource path escapes the outer document directory"
        ) from exc
    time_grid = _require_mapping(spec.get("time_grid"), "spec.time_grid")
    _reject_unknown(
        time_grid,
        set(SIMULATION_TIME_GRID_FIELDS),
        "spec.time_grid",
    )
    time_step = _positive_float(
        time_grid.get("time_step"),
        "spec.time_grid.time_step",
    )
    integrator = time_grid.get("integrator", "staggered")
    if integrator not in INTEGRATORS:
        raise ConfigurationError(
            "spec.time_grid.integrator must be 'staggered' or 'ros2'"
        )
    jacobian_refresh = time_grid.get("jacobian_refresh")
    ros2_options: Ros2Options | None = None
    if integrator == "ros2":
        if jacobian_refresh is not None and jacobian_refresh != "control_period":
            jacobian_refresh = _require_integer(
                jacobian_refresh,
                "spec.time_grid.jacobian_refresh",
                minimum=1,
            )
        ros2_options = Ros2Options(jacobian_refresh=jacobian_refresh)
    elif jacobian_refresh is not None:
        raise ConfigurationError(
            "spec.time_grid.jacobian_refresh requires integrator='ros2'"
        )
    from ALB.dynamics.rotor import rotor0

    rotor = rotor0(  # type: ignore[no-untyped-call]
        dt=time_step,
        freq=_finite_float(
            rotor_spec.get("frequency_hz"),
            "spec.rotor.frequency_hz",
        ),
        alpha=_finite_float(
            rotor_spec.get("alpha", 0.0),
            "spec.rotor.alpha",
        ),
        beta=_finite_float(
            rotor_spec.get("beta", 0.0),
            "spec.rotor.beta",
        ),
        rotor_path=str(rotor_path),
    )
    mounts_raw = spec.get("mounts")
    if not isinstance(mounts_raw, Sequence) or isinstance(
        mounts_raw,
        (str, bytes),
    ):
        raise ConfigurationError("spec.mounts must be a list")
    mounts = []
    for index, raw_mount in enumerate(mounts_raw):
        mount = _require_mapping(raw_mount, f"spec.mounts[{index}]")
        _reject_unknown(
            mount,
            set(SIMULATION_MOUNT_FIELDS),
            f"spec.mounts[{index}]",
        )
        bearing_path = mount.get("bearing")
        if not isinstance(bearing_path, str) or not bearing_path:
            raise ConfigurationError(
                f"spec.mounts[{index}].bearing must be a relative path"
            )
        mounts.append(
            BearingMount(
                load_bearing_config(source.parent / bearing_path),
                _require_integer(
                    mount.get("node"),
                    f"spec.mounts[{index}].node",
                    minimum=0,
                ),
            )
        )
    history_raw = _require_mapping(spec.get("history", {}), "spec.history")
    _reject_unknown(
        history_raw,
        set(SIMULATION_HISTORY_FIELDS),
        "spec.history",
    )
    raw_history_directory = history_raw.get("directory")
    history_directory: Path | None = None
    if raw_history_directory is not None:
        if (
            not isinstance(raw_history_directory, str)
            or not raw_history_directory
        ):
            raise ConfigurationError(
                "spec.history.directory must be a relative path"
            )
        history_directory = (source.parent / raw_history_directory).resolve()
        try:
            history_directory.relative_to(source.parent)
        except ValueError as exc:
            raise ConfigurationError(
                "history directory escapes the outer document directory"
            ) from exc
    history = HistoryPolicy(
        mode=history_raw.get("mode", "memory"),
        fields=tuple(
            history_raw.get(
                "fields",
                (
                    "rotor_displacement",
                    "rotor_velocity",
                    "bearing_force",
                ),
            )
        ),
        downsample=_require_integer(
            history_raw.get("downsample", 1),
            "spec.history.downsample",
            minimum=1,
        ),
        capacity=(
            None
            if history_raw.get("capacity") is None
            else _require_integer(
                history_raw.get("capacity"),
                "spec.history.capacity",
                minimum=1,
            )
        ),
        directory=history_directory,
    )
    loads_raw = spec.get("loads", [])
    if not isinstance(loads_raw, Sequence) or isinstance(
        loads_raw,
        (str, bytes),
    ):
        raise ConfigurationError("spec.loads must be a list")
    return SimulationConfig(
        rotor=rotor,
        mounts=tuple(mounts),
        time_step=time_step,
        steps=_require_integer(
            time_grid.get("steps"),
            "spec.time_grid.steps",
            minimum=0,
        ),
        loads=tuple(_thaw(load) for load in loads_raw),
        history=history,
        integrator=integrator,
        ros2=ros2_options,
    )


def build_simulation(config: SimulationConfig) -> RotorBearingSimulation:
    """Build a fresh one-shot simulation from immutable programmatic inputs.

    Parameters
    ----------
    config
        Validated :class:`SimulationConfig` owning rotor, mounts, fixed time grid,
        loads, history policy, and optional coupling dependencies.

    Returns
    -------
    RotorBearingSimulation
        Ready one-shot simulation; no physical step has run yet.

    Raises
    ------
    TypeError
        If ``config`` is not :class:`SimulationConfig`.
    ConfigurationError
        If runtime materialization detects an inconsistent bearing boundary.
    """

    return RotorBearingSimulation(config)


def simulation_from_file(path: str | Path) -> RotorBearingSimulation:
    """Load one strict simulation JSON5 document and build a fresh runtime.

    Parameters
    ----------
    path
        File accepted by :func:`load_simulation_config`.

    Returns
    -------
    RotorBearingSimulation
        Ready one-shot simulation constructed from the resolved resources.

    Raises
    ------
    ConfigurationError, ImportError, FileNotFoundError
        Propagated from configuration loading and optional resource construction.
    """

    return build_simulation(load_simulation_config(path))


__all__ = [
    "BearingMount",
    "HistoryPolicy",
    "RotorBearingSimulation",
    "SimulationConfig",
    "build_simulation",
    "load_simulation_config",
    "simulation_from_file",
]
