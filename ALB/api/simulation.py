"""User-facing immutable rotor-bearing simulation API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
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
from ALB.dynamics.coupling_runtime import (
    PostCommitObserverError,
    PostCommitRecordingError,
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
    """Validated immutable inputs for one rotor-bearing simulation.

    Rotor time uses the global dimensional step. Each mounted bearing uses the
    step produced by its explicit unit adapter, and its entire materialized
    configuration tree must agree with that bearing-local value.
    """

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
        try:
            normalized_rotor_time_step = float(self.rotor.dt)
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
        from .building import _validate_runtime_time_steps

        for index, mount in enumerate(mounts):
            expected_local_step = time_step
            if mount.unit_adapter is not None:
                try:
                    local_context = (
                        mount.unit_adapter.rotor_context_to_bearing(
                            StepContext(
                                0,
                                0.0,
                                time_step,
                                UnitSystem.DIMENSIONAL,
                            )
                        )
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
                expected_local_step = float(local_context.dt)
                if (
                    not np.isfinite(expected_local_step)
                    or expected_local_step <= 0.0
                ):
                    raise ConfigurationError(
                        f"mounts[{index}].unit_adapter produced an invalid "
                        "bearing-local time_step"
                    )
            _validate_runtime_time_steps(
                mount.config,
                expected_local_step,
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

    __slots__ = ("_config", "_has_run", "_last_result")

    def __init__(self, config: SimulationConfig) -> None:
        if not isinstance(config, SimulationConfig):
            raise TypeError("config must be SimulationConfig")
        self._config = config
        self._has_run = False
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
        self._has_run = True
        coupling = self._build_coupling()
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
        except BaseException as exc:
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
