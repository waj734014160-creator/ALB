"""User-facing immutable rotor-bearing simulation API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from ALB.contracts import (
    BearingUnitAdapterProtocol,
    BearingRuntimeProtocol,
    ConvergenceStatus,
    RotorProtocol,
    SpoolCommandProviderProtocol,
    StepContext,
    UnitSystem,
)

from .config import (
    SCHEMA_VERSION,
    BearingConfig,
    _deep_merge,
    _read_json5,
    _reject_unknown,
    _require_mapping,
    _thaw,
    load_bearing_config,
)
from .errors import ConfigurationError, SimulationError
from .results import SimulationResult


def _validate_bearing_time_step(
    config: BearingConfig,
    expected: float,
    *,
    path: str,
    active_paths: frozenset[Path] = frozenset(),
) -> None:
    """Require one normalized step across a mount and all nested pads."""

    actual = float(config.spec["time_step"])
    if actual != expected:
        raise ConfigurationError(
            f"{path}.time_step must equal simulation time_step "
            f"{expected!r}; got {actual!r}"
        )
    try:
        if config.family == "active_lubricated":
            from .building import _active_config

            _active_config(config)
        elif (
            config.family == "liquid_film"
            and config.spec.get("thermal") is not None
        ):
            from .building import _thermal_config

            _thermal_config(config)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"{path} has inconsistent materialized time steps: {exc}"
        ) from exc
    if config.family != "multi_pad":
        return
    pads = config.spec["pads"]
    assert isinstance(pads, tuple)
    for index, item in enumerate(pads):
        child_path = f"{path}.pads[{index}]"
        if isinstance(item, str):
            if config.resource_root is None:
                raise ConfigurationError(
                    f"{child_path} requires a source document resource root"
                )
            source = (config.resource_root / item).resolve()
            if source in active_paths:
                raise ConfigurationError(
                    f"{child_path} creates a recursive multi_pad reference"
                )
            child = load_bearing_config(source)
            child_active_paths = active_paths | {source}
        else:
            child_spec = _thaw(item)
            child_spec.setdefault("time_step", actual)
            child_spec.setdefault("node", config.spec.get("node"))
            child_spec.setdefault("unit_system", config.unit_system)
            child = BearingConfig(
                child_spec,
                resource_root=config.resource_root,
            )
            child_active_paths = active_paths
        _validate_bearing_time_step(
            child,
            expected,
            path=child_path,
            active_paths=child_active_paths,
        )


@dataclass(frozen=True, slots=True)
class BearingMount:
    """Bind one immutable bearing config to a rotor node."""

    config: BearingConfig
    node: int
    unit_adapter: BearingUnitAdapterProtocol | None = None
    spool_provider: SpoolCommandProviderProtocol | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.config, BearingConfig):
            raise TypeError("config must be BearingConfig")
        if isinstance(self.node, bool) or not isinstance(self.node, int):
            raise TypeError("node must be an integer")
        if self.node < 0:
            raise ValueError("node must be nonnegative")


@dataclass(frozen=True, slots=True)
class HistoryPolicy:
    """Optional committed-history retention policy."""

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


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Validated immutable inputs for one rotor-bearing simulation."""

    rotor: RotorProtocol
    mounts: tuple[BearingMount, ...]
    time_step: float
    steps: int
    loads: tuple[Mapping[str, Any], ...] = ()
    history: HistoryPolicy = HistoryPolicy()
    dependencies: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rotor, RotorProtocol):
            raise TypeError("rotor must satisfy RotorProtocol")
        mounts = tuple(self.mounts)
        if not mounts or any(not isinstance(item, BearingMount) for item in mounts):
            raise ValueError("mounts must contain at least one BearingMount")
        nodes = [item.node for item in mounts]
        if len(set(nodes)) != len(nodes):
            raise ValueError("bearing mount nodes must be unique")
        time_step = float(self.time_step)
        if not np.isfinite(time_step) or time_step <= 0.0:
            raise ValueError("time_step must be finite and > 0")
        rotor_time_step = getattr(self.rotor, "dt", None)
        if rotor_time_step is None:
            raise ConfigurationError(
                "rotor.dt is required to verify simulation time_step"
            )
        try:
            normalized_rotor_time_step = float(rotor_time_step)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                "rotor.dt must be a finite positive number"
            ) from exc
        if (
            not np.isfinite(normalized_rotor_time_step)
            or normalized_rotor_time_step <= 0.0
        ):
            raise ConfigurationError(
                "rotor.dt must be a finite positive number"
            )
        if normalized_rotor_time_step != time_step:
            raise ConfigurationError(
                "rotor.dt must equal simulation time_step "
                f"{time_step!r}; got {normalized_rotor_time_step!r}"
            )
        for index, mount in enumerate(mounts):
            _validate_bearing_time_step(
                mount.config,
                time_step,
                path=f"mounts[{index}].config",
            )
        if isinstance(self.steps, bool) or not isinstance(self.steps, int):
            raise TypeError("steps must be an integer")
        if self.steps < 0:
            raise ValueError("steps must be nonnegative")
        loads = tuple(_require_mapping(item, "loads[]") for item in self.loads)
        if not isinstance(self.history, HistoryPolicy):
            raise TypeError("history must be HistoryPolicy")
        object.__setattr__(self, "mounts", mounts)
        object.__setattr__(self, "time_step", time_step)
        object.__setattr__(self, "loads", loads)


class RotorBearingSimulation:
    """Ready one-shot simulation with immutable topology."""

    __slots__ = ("_config", "_last_result")

    def __init__(self, config: SimulationConfig) -> None:
        if not isinstance(config, SimulationConfig):
            raise TypeError("config must be SimulationConfig")
        self._config = config
        self._last_result: SimulationResult | None = None

    @property
    def config(self) -> SimulationConfig:
        """Return immutable simulation inputs."""

        return self._config

    @property
    def latest_result(self) -> SimulationResult:
        """Return the latest complete or partial committed history."""

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
        """Run all requested steps and retain only committed snapshots."""

        coupling = self._build_coupling()
        policy = self._config.history
        snapshots: list[Any] = []
        retained_indices: set[int] = set()
        stream_records: list[dict[str, Any]] = []
        stream_root: Path | None = None
        committed_steps = 0
        last_snapshot: Any | None = None
        last_index = -1

        if policy.mode == "disk_stream":
            assert policy.directory is not None
            stream_root = policy.directory
            if stream_root.exists() and any(stream_root.iterdir()):
                raise SimulationError(
                    f"history directory is not empty: {stream_root}"
                )
            stream_root.mkdir(parents=True, exist_ok=True)

        def retain(snapshot: Any, index: int, *, force: bool = False) -> None:
            if index in retained_indices:
                return
            if not force and index % policy.downsample != 0:
                return
            retained_indices.add(index)
            if stream_root is not None:
                file_name = f"step_{index:08d}.npz"
                payload: dict[str, Any] = {
                    "time": np.asarray(
                        [float(snapshot.metadata["time"])],
                        dtype=float,
                    )
                }
                for field in policy.fields:
                    payload[field] = np.asarray(snapshot.values[field])
                np.savez_compressed(stream_root / file_name, **payload)
                stream_records.append(
                    {
                        "step_index": index,
                        "time": float(snapshot.metadata["time"]),
                        "file": file_name,
                    }
                )
                return
            snapshots.append(snapshot)
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
            (stream_root / "history.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        try:
            coupling._reset_for_owner()
            last_snapshot = coupling.output()
            last_index = 0
            committed_steps = 1
            retain(last_snapshot, last_index)
            for step_index in range(1, self._config.steps + 1):
                context = StepContext(
                    step_index,
                    self._config.time_step * step_index,
                    self._config.time_step,
                    UnitSystem.DIMENSIONAL,
                )
                last_snapshot = coupling.advance(context)
                last_index = step_index
                committed_steps += 1
                retain(last_snapshot, last_index)
        except BaseException as exc:
            if last_snapshot is not None:
                retain(last_snapshot, last_index, force=True)
            finalize_stream(complete=False)
            partial = self._to_result(
                snapshots,
                committed_steps=committed_steps,
                complete=False,
                stream_records=stream_records,
                stream_root=stream_root,
            )
            self._last_result = partial
            error = SimulationError(
                f"rotor-bearing simulation failed: {exc}",
                partial_result=partial,
            )
            get_failure = getattr(coupling, "failure_snapshot", None)
            if callable(get_failure):
                try:
                    error.failure_snapshot = get_failure()
                except Exception:
                    pass
            raise error from exc
        if last_snapshot is not None:
            retain(last_snapshot, last_index, force=True)
        finalize_stream(complete=True)
        result = self._to_result(
            snapshots,
            committed_steps=committed_steps,
            complete=True,
            stream_records=stream_records,
            stream_root=stream_root,
        )
        self._last_result = result
        return result

    def _to_result(
        self,
        snapshots: Sequence[Any],
        *,
        committed_steps: int,
        complete: bool,
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
                "committed_steps": committed_steps,
                "requested_steps": self._config.steps + 1,
                "history_mode": policy.mode,
                "history_downsample": policy.downsample,
                "history_fields": policy.fields,
                "history_path": (
                    None if stream_root is None else str(stream_root)
                ),
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
        {"schema_version", "kind", "includes", "spec"},
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
    """Load and build one strict 0.4 simulation document."""

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
        {"rotor", "time_grid", "mounts", "loads", "history"},
        "spec",
    )
    rotor_spec = _require_mapping(spec.get("rotor"), "spec.rotor")
    _reject_unknown(
        rotor_spec,
        {"model", "path", "frequency_hz", "alpha", "beta"},
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
    _reject_unknown(time_grid, {"time_step", "steps"}, "spec.time_grid")
    time_step = float(cast(Any, time_grid.get("time_step")))
    from ALB.dynamics.rotor import rotor0

    rotor = rotor0(  # type: ignore[no-untyped-call]
        dt=time_step,
        freq=float(cast(Any, rotor_spec.get("frequency_hz"))),
        alpha=float(rotor_spec.get("alpha", 0.0)),
        beta=float(rotor_spec.get("beta", 0.0)),
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
        _reject_unknown(mount, {"bearing", "node"}, f"spec.mounts[{index}]")
        bearing_path = mount.get("bearing")
        if not isinstance(bearing_path, str) or not bearing_path:
            raise ConfigurationError(
                f"spec.mounts[{index}].bearing must be a relative path"
            )
        mounts.append(
            BearingMount(
                load_bearing_config(source.parent / bearing_path),
                int(mount["node"]),
            )
        )
    history_raw = _require_mapping(spec.get("history", {}), "spec.history")
    _reject_unknown(
        history_raw,
        {"mode", "fields", "downsample", "capacity", "directory"},
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
        downsample=int(history_raw.get("downsample", 1)),
        capacity=history_raw.get("capacity"),
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
        steps=int(cast(Any, time_grid.get("steps"))),
        loads=tuple(_thaw(load) for load in loads_raw),
        history=history,
    )


def build_simulation(config: SimulationConfig) -> RotorBearingSimulation:
    """Build a ready simulation from immutable programmatic inputs."""

    return RotorBearingSimulation(config)


def simulation_from_file(path: str | Path) -> RotorBearingSimulation:
    """Load one strict JSON5 simulation and build it."""

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
