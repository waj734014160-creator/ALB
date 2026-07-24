"""Failure-atomic simulation and disk-stream tests for ALB 0.4.2."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import ALB
from ALB.api import simulation as simulation_module
from ALB.contracts import (
    RecordingRecovered,
    RunReceipt,
    StepCompleted,
)
from ALB.dynamics.bindings import CouplingRuntimeDependencies
from ALB.dynamics.rotor import RossRotor
from ALB.infrastructure.recording import InMemoryResultRecorder


class _NodeRotorPlant:
    """Small deterministic rotor plant for public simulation failures."""

    ndof = 4
    number_dof = 4

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        state_count = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(state_count),
            B=np.vstack((np.eye(self.ndof), 0.25 * np.eye(self.ndof))),
            C=np.eye(state_count),
            D=np.zeros((state_count, self.ndof)),
        )


class _TrackingRecorder(InMemoryResultRecorder):
    """Record close receipts and optionally fail one physical step."""

    def __init__(self, fail_step: int | None = None) -> None:
        super().__init__()
        self.fail_step = fail_step
        self.attempts: list[int] = []
        self.close_receipt: RunReceipt | None = None
        self.close_attempts: list[bool] = []

    def record(self, context, bundle):
        self.attempts.append(context.step_index)
        if context.step_index == self.fail_step:
            raise OSError(f"record failure at step {context.step_index}")
        return super().record(context, bundle)

    def end_run(
        self,
        run_id: str,
        *,
        allow_incomplete: bool = False,
    ) -> RunReceipt:
        self.close_attempts.append(allow_incomplete)
        self.close_receipt = super().end_run(
            run_id,
            allow_incomplete=allow_incomplete,
        )
        return self.close_receipt


class _FailingCloseRecorder(_TrackingRecorder):
    """Keep the primary record error when recorder close also fails."""

    def end_run(
        self,
        run_id: str,
        *,
        allow_incomplete: bool = False,
    ) -> RunReceipt:
        del run_id, allow_incomplete
        raise OSError("secondary close failure")


class _FailingObserver:
    """Raise after one selected committed step."""

    def __init__(self, fail_step: int) -> None:
        self.fail_step = fail_step
        self.completed: list[int] = []
        self.recovered: list[int] = []

    def on_step_completed(self, event: StepCompleted) -> None:
        self.completed.append(event.context.step_index)
        if event.context.step_index == self.fail_step:
            raise RuntimeError(
                f"observer failure at step {event.context.step_index}"
            )

    def on_recording_recovered(self, event: RecordingRecovered) -> None:
        self.recovered.append(event.key.step_index)


def _liquid_config() -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {
                "circumferential_elements": 5,
                "axial_elements": 3,
                "max_iterations": 5,
                "solver_tolerance": 1.0e-6,
                "eccentricity": 0.0,
            },
            "restrictors": None,
            "thermal": None,
        }
    )


def _simulation(
    *,
    steps: int = 2,
    dependencies: CouplingRuntimeDependencies | None = None,
    history: ALB.HistoryPolicy = ALB.HistoryPolicy(),
) -> ALB.RotorBearingSimulation:
    return ALB.build_simulation(
        ALB.SimulationConfig(
            rotor=RossRotor(_NodeRotorPlant(), speed=1.0, dt=1.0e-3),
            mounts=(ALB.BearingMount(_liquid_config(), 0),),
            time_step=1.0e-3,
            steps=steps,
            dependencies=dependencies,
            history=history,
        )
    )


@pytest.mark.parametrize("fail_step", [0, 1, 2])
def test_post_commit_record_failure_keeps_committed_step_in_partial_result(
    fail_step: int,
) -> None:
    recorder = _TrackingRecorder(fail_step)
    dependencies = CouplingRuntimeDependencies(
        f"record-failure-{fail_step}",
        recorder=recorder,
        record_failure_policy="raise",
    )

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(dependencies=dependencies).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    expected = np.arange(fail_step + 1, dtype=float) * 1.0e-3
    np.testing.assert_array_equal(partial.time, expected)
    assert partial.metadata["committed_steps"] == fail_step + 1
    assert partial.metadata["post_commit_complete"] is False
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["physical_step_committed"] is True
    assert snapshot.metadata["committed_step_index"] == fail_step
    assert snapshot.metadata["recording_status"] == "pending"
    assert recorder.attempts == list(range(fail_step + 1))
    assert recorder.close_receipt is not None
    assert recorder.close_receipt.close_status.value == "incomplete"
    assert recorder.close_attempts == [True]
    assert partial.metadata["complete"] is (fail_step == 2)


def test_strict_observer_failure_keeps_step_one_without_repeating_physics() -> None:
    observer = _FailingObserver(1)
    dependencies = CouplingRuntimeDependencies(
        "observer-failure-1",
        observers=(observer,),
        observer_failure_policy="raise",
    )

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(dependencies=dependencies).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [0.0, 1.0e-3])
    assert partial.metadata["committed_steps"] == 2
    assert observer.completed == [0, 1]
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["committed_step_index"] == 1
    assert snapshot.metadata["observer_failure_count"] == 1


def test_strict_observer_failure_at_step_zero_keeps_initial_commit() -> None:
    observer = _FailingObserver(0)
    dependencies = CouplingRuntimeDependencies(
        "observer-failure-0",
        observers=(observer,),
        observer_failure_policy="raise",
    )

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(dependencies=dependencies).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [0.0])
    assert observer.completed == [0]
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["physical_step_committed"] is True
    assert snapshot.metadata["committed_step_index"] == 0


def test_secondary_recorder_close_failure_does_not_replace_primary_error() -> None:
    recorder = _FailingCloseRecorder(fail_step=0)
    dependencies = CouplingRuntimeDependencies(
        "record-and-close-failure",
        recorder=recorder,
        record_failure_policy="raise",
    )

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(dependencies=dependencies).run()

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["error_type"] == "PostCommitRecordingError"
    secondary = snapshot.metadata["secondary_errors"]
    assert len(secondary) == 1
    assert secondary[0]["phase"] == "run_close"
    assert secondary[0]["error_type"] == "OSError"


def test_successful_simulation_closes_recorder_run() -> None:
    recorder = _TrackingRecorder()
    dependencies = CouplingRuntimeDependencies(
        "successful-recorder-run",
        recorder=recorder,
    )

    result = _simulation(steps=1, dependencies=dependencies).run()

    assert result.metadata["post_commit_complete"] is True
    assert recorder.close_receipt is not None
    assert recorder.close_receipt.close_status.value == "complete"
    assert recorder.close_receipt.record_count == 2
    assert recorder.close_attempts == [False]


def test_simulation_instance_cannot_replay_after_success() -> None:
    recorder = _TrackingRecorder()
    dependencies = CouplingRuntimeDependencies(
        "one-shot-success",
        recorder=recorder,
    )
    simulation = _simulation(steps=1, dependencies=dependencies)

    first = simulation.run()
    with pytest.raises(ALB.SimulationError, match="one-shot"):
        simulation.run()

    assert simulation.latest_result is first
    assert recorder.attempts == [0, 1]
    assert recorder.close_attempts == [False]


def test_simulation_instance_cannot_replay_after_failure() -> None:
    recorder = _TrackingRecorder(fail_step=1)
    dependencies = CouplingRuntimeDependencies(
        "one-shot-failure",
        recorder=recorder,
        record_failure_policy="raise",
    )
    simulation = _simulation(steps=2, dependencies=dependencies)

    with pytest.raises(ALB.SimulationError):
        simulation.run()
    with pytest.raises(ALB.SimulationError, match="one-shot"):
        simulation.run()

    assert recorder.attempts == [0, 1]
    assert recorder.close_attempts == [True]


def test_precommit_failure_preserves_coupling_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_advance(self: RossRotor) -> np.ndarray:
        del self
        nonlocal calls
        calls += 1
        raise ArithmeticError("rotor propagation failure")

    monkeypatch.setattr(RossRotor, "advance", fail_advance)
    simulation = _simulation(steps=2)

    with pytest.raises(ALB.SimulationError) as caught:
        simulation.run()

    assert calls == 1
    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [0.0])
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["physical_step_committed"] is False
    assert snapshot.metadata["committed_step_index"] == 0
    assert snapshot.metadata["coupling_failure_available"] is True
    coupling_failure = snapshot.values["coupling_failure"]
    assert coupling_failure["metadata"]["phase"] == "advance"
    assert coupling_failure["metadata"]["physical_step_committed"] is False


def _stream_policy(path: Path) -> ALB.HistoryPolicy:
    return ALB.HistoryPolicy(
        mode="disk_stream",
        fields=("bearing_force",),
        directory=path,
    )


def _assert_no_temporary_files(path: Path) -> None:
    assert not [
        item
        for item in path.iterdir()
        if ".tmp" in item.name or item.name.startswith(".")
    ]


def test_snapshot_write_failure_retries_without_publishing_early(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = simulation_module.np.savez_compressed
    calls = 0

    def fail_once(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("snapshot write failure")
        original(*args, **kwargs)

    monkeypatch.setattr(simulation_module.np, "savez_compressed", fail_once)
    root = tmp_path / "stream"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(steps=1, history=_stream_policy(root)).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [0.0])
    assert (root / "step_00000000.npz").is_file()
    _assert_no_temporary_files(root)


def test_snapshot_replace_failure_retries_without_publishing_early(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = Path.replace
    calls = 0

    def fail_once(source: Path, target: Path) -> Path:
        nonlocal calls
        if "step_00000000" in target.name:
            calls += 1
            if calls == 1:
                raise OSError("snapshot replace failure")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", fail_once)
    root = tmp_path / "stream"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(steps=1, history=_stream_policy(root)).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [0.0])
    assert (root / "step_00000000.npz").is_file()
    _assert_no_temporary_files(root)


@pytest.mark.parametrize("failure", ["write", "replace"])
def test_persistent_snapshot_failure_is_wrapped_without_false_retention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    if failure == "write":
        def fail_write(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            raise OSError("persistent snapshot write failure")

        monkeypatch.setattr(
            simulation_module.np,
            "savez_compressed",
            fail_write,
        )
    else:
        original_replace = Path.replace

        def fail_replace(source: Path, target: Path) -> Path:
            if target.suffix == ".npz":
                raise OSError("persistent snapshot replace failure")
            return original_replace(source, target)

        monkeypatch.setattr(Path, "replace", fail_replace)
    root = tmp_path / f"stream-{failure}"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(steps=1, history=_stream_policy(root)).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [])
    assert partial.metadata["history_complete"] is False
    assert not list(root.glob("step_*.npz"))
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["failure_phase"] == "history_snapshot"
    _assert_no_temporary_files(root)


def test_snapshot_cleanup_failure_does_not_replace_primary_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_write(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise PermissionError("primary snapshot failure")

    original_unlink = Path.unlink

    def fail_cleanup(path: Path, *args: Any, **kwargs: Any) -> None:
        if ".tmp" in path.name:
            raise OSError("secondary cleanup failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(simulation_module.np, "savez_compressed", fail_write)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    root = tmp_path / "stream"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(steps=1, history=_stream_policy(root)).run()

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["error_type"] == "PermissionError"
    secondary = snapshot.metadata["secondary_errors"]
    assert any(
        item["phase"] == "history_snapshot_cleanup"
        and item["error_type"] == "OSError"
        for item in secondary
    )


def test_manifest_write_failure_is_wrapped_and_incomplete_manifest_is_saved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = Path.open
    calls = 0

    def fail_once(path: Path, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        if "history.json" in path.name:
            calls += 1
            if calls == 1:
                raise OSError("manifest write failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_once)
    root = tmp_path / "stream"

    recorder = _TrackingRecorder()
    dependencies = CouplingRuntimeDependencies(
        "manifest-failure",
        recorder=recorder,
    )
    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(
            steps=1,
            history=_stream_policy(root),
            dependencies=dependencies,
        ).run()

    assert isinstance(caught.value.partial_result, ALB.SimulationResult)
    assert caught.value.failure_snapshot is not None
    assert caught.value.failure_snapshot.metadata["failure_phase"] == (
        "history_manifest"
    )
    manifest = (root / "history.json").read_text(encoding="utf-8")
    assert '"complete": false' in manifest
    assert recorder.close_attempts == [False]
    _assert_no_temporary_files(root)


def test_manifest_replace_failure_is_wrapped_and_retried_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = Path.replace
    calls = 0

    def fail_once(source: Path, target: Path) -> Path:
        nonlocal calls
        if target.name == "history.json":
            calls += 1
            if calls == 1:
                raise OSError("manifest replace failure")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", fail_once)
    root = tmp_path / "stream"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(steps=1, history=_stream_policy(root)).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    assert partial.metadata["complete"] is True
    assert partial.metadata["history_complete"] is True
    assert '"complete": false' in (root / "history.json").read_text(
        encoding="utf-8"
    )
    _assert_no_temporary_files(root)


def test_persistent_manifest_failure_is_wrapped_and_cleans_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = Path.open

    def fail_manifest(path: Path, *args: Any, **kwargs: Any) -> Any:
        if "history.json" in path.name:
            raise OSError("persistent manifest failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_manifest)
    root = tmp_path / "stream"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(steps=1, history=_stream_policy(root)).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    assert partial.metadata["complete"] is True
    assert partial.metadata["history_complete"] is False
    assert not (root / "history.json").exists()
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["failure_phase"] == "history_manifest"
    assert len(snapshot.metadata["secondary_errors"]) == 1
    _assert_no_temporary_files(root)


def test_disk_stream_force_retains_the_final_committed_step(
    tmp_path: Path,
) -> None:
    root = tmp_path / "stream"
    policy = ALB.HistoryPolicy(
        mode="disk_stream",
        fields=("bearing_force",),
        downsample=2,
        directory=root,
    )

    result = _simulation(steps=1, history=policy).run()

    np.testing.assert_array_equal(result.time, [0.0, 1.0e-3])
    assert sorted(path.name for path in root.glob("step_*.npz")) == [
        "step_00000000.npz",
        "step_00000001.npz",
    ]


def test_disk_stream_includes_final_post_commit_failure(
    tmp_path: Path,
) -> None:
    recorder = _TrackingRecorder(fail_step=2)
    dependencies = CouplingRuntimeDependencies(
        "disk-final-record-failure",
        recorder=recorder,
        record_failure_policy="raise",
    )
    root = tmp_path / "stream"

    with pytest.raises(ALB.SimulationError) as caught:
        _simulation(
            steps=2,
            dependencies=dependencies,
            history=_stream_policy(root),
        ).run()

    partial = caught.value.partial_result
    assert isinstance(partial, ALB.SimulationResult)
    np.testing.assert_array_equal(partial.time, [0.0, 1.0e-3, 2.0e-3])
    assert partial.metadata["complete"] is True
    assert partial.metadata["history_complete"] is True
    assert partial.metadata["post_commit_complete"] is False
    assert recorder.attempts == [0, 1, 2]
    assert recorder.close_attempts == [True]
    assert sorted(path.name for path in root.glob("step_*.npz")) == [
        "step_00000000.npz",
        "step_00000001.npz",
        "step_00000002.npz",
    ]
    assert '"complete": false' in (root / "history.json").read_text(
        encoding="utf-8"
    )
