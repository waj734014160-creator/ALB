"""Adversarial API tests for the ALB 0.4.2 review repairs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ALB
from ALB.contracts import (
    ConvergenceStatus,
    LifecycleState,
    RotorProtocol,
    UnitSystem,
)
from ALB.physics.bearing.units import BearingScaleSet, BearingUnitAdapter


class _LinearWhirlRuntime:
    """Return a deterministic two-axis linear bearing force."""

    unit_system = UnitSystem.DIMENSIONAL

    def calculate(
        self,
        *,
        displacement: object,
        velocity: object,
        time: float,
        spool: object = None,
    ) -> SimpleNamespace:
        del time, spool
        coordinate = np.asarray(displacement, dtype=float)
        speed = np.asarray(velocity, dtype=float)
        stiffness = np.array([[8.0, 1.0], [-2.0, 5.0]])
        damping = np.array([[0.8, -0.1], [0.2, 0.6]])
        return SimpleNamespace(
            force=-(stiffness @ coordinate + damping @ speed),
            convergence=ConvergenceStatus(0.0, True, iterations=1),
        )


class _CountingWhirlBearing:
    """Count isolated runtimes so pre-solve rejection is observable."""

    config = SimpleNamespace(unit_system="dimensional")

    def __init__(self) -> None:
        self.fresh_count = 0

    def _fresh(self) -> _LinearWhirlRuntime:
        self.fresh_count += 1
        return _LinearWhirlRuntime()


class _Rotor:
    """Minimal rotor satisfying the public runtime protocol."""

    unit_system = UnitSystem.DIMENSIONAL
    lifecycle_state = LifecycleState.READY

    def __init__(self, dt: float) -> None:
        self.dt = dt

    def _reset_for_owner(self, initial_state=None) -> None:
        del initial_state

    def input_force2node(
        self,
        time,
        force,
        node,
        initial_state=None,
        *,
        force0=None,
    ) -> None:
        del time, force, node, initial_state, force0

    def input_load(self, value) -> None:
        del value

    def advance(self) -> np.ndarray:
        return np.zeros(4)

    def current_state(self, node=None) -> np.ndarray:
        del node
        return np.zeros(4)

    def output(self, node=None) -> np.ndarray:
        del node
        return np.zeros(4)


class _RotorWithoutDt:
    """Match the old protocol while intentionally omitting dt."""

    unit_system = UnitSystem.DIMENSIONAL
    lifecycle_state = LifecycleState.READY

    def _reset_for_owner(self, initial_state=None) -> None:
        del initial_state

    def input_force2node(
        self,
        time,
        force,
        node,
        initial_state=None,
        *,
        force0=None,
    ) -> None:
        del time, force, node, initial_state, force0

    def input_load(self, value) -> None:
        del value

    def advance(self) -> np.ndarray:
        return np.zeros(4)

    def current_state(self, node=None) -> np.ndarray:
        del node
        return np.zeros(4)

    def output(self, node=None) -> np.ndarray:
        del node
        return np.zeros(4)


def _trajectory(
    *,
    semi_axes: tuple[float, float] = (2.0e-4, 7.0e-5),
) -> ALB.EllipseTrajectory:
    return ALB.EllipseTrajectory(
        center=(0.0, 0.0),
        semi_axes=semi_axes,
        orientation_rad=0.2,
    )


def _liquid_spec(
    time_step: float,
    *,
    unit_system: str = "dimensional",
) -> dict[str, object]:
    return {
        "family": "liquid_film",
        "unit_system": unit_system,
        "time_step": time_step,
        "node": 0,
        "film": {},
        "restrictors": None,
        "thermal": None,
    }


def _adapter() -> BearingUnitAdapter:
    return BearingUnitAdapter(
        BearingScaleSet(
            rotor_unit=UnitSystem.DIMENSIONAL,
            bearing_unit=UnitSystem.NONDIMENSIONAL,
            Sx=2.0e-5,
            St=2.0e-4,
            Sv=0.1,
            Sf=2500.0,
            Sp=5.0e6,
            scale_id="review-test",
            pressure_scale_source="unit test",
            velocity_definition_id="Sx/St",
            residual_definition_id="bearing-local",
            provenance="unit test",
        )
    )


@pytest.mark.parametrize(
    ("time", "message"),
    [
        (np.array([0.0]), "at least two"),
        (np.array([0.0, 0.01, 0.021, 0.03]), "uniform"),
        (np.array([0.0, 0.01, 0.01]), "strictly increasing"),
        (np.array([0.0, np.nan]), "finite"),
    ],
)
def test_dynamic_coefficients_reject_invalid_grid_before_runtime(
    time: np.ndarray,
    message: str,
) -> None:
    bearing = _CountingWhirlBearing()

    with pytest.raises(ValueError, match=message):
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(),
            time,
            frequency_hz=10.0,
        )

    assert bearing.fresh_count == 0


@pytest.mark.parametrize(
    ("time", "frequency_hz", "message"),
    [
        (np.arange(32) * 1.0e-3, 10.0, "FFT bin"),
        (np.arange(100) * 1.0e-3, 12.0, "FFT bin"),
        (np.arange(100) * 1.0e-3, 600.0, "Nyquist"),
    ],
)
def test_dynamic_coefficients_reject_unrepresented_frequency_before_runtime(
    time: np.ndarray,
    frequency_hz: float,
    message: str,
) -> None:
    bearing = _CountingWhirlBearing()

    with pytest.raises(ALB.CalculationError, match=message) as caught:
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(),
            time,
            frequency_hz=frequency_hz,
        )

    assert bearing.fresh_count == 0
    assert caught.value.failure_snapshot is not None
    assert caught.value.failure_snapshot.metadata["requested_frequency_hz"] == (
        frequency_hz
    )


def test_dynamic_coefficients_reject_ill_conditioned_displacement_matrix() -> None:
    bearing = _CountingWhirlBearing()

    with pytest.raises(ALB.CalculationError, match="ill-conditioned") as caught:
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(semi_axes=(1.0e-4, 1.0e-13)),
            np.arange(100) * 1.0e-3,
            frequency_hz=10.0,
        )

    assert bearing.fresh_count == 2
    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["displacement_condition_number"] > (
        1.0 / np.sqrt(np.finfo(float).eps)
    )
    assert set(snapshot.values) >= {
        "forward_displacement",
        "forward_force",
        "reverse_displacement",
        "reverse_force",
        "displacement_matrix_real",
        "displacement_matrix_imag",
    }


def test_dynamic_coefficients_reject_rank_deficient_matrix_before_inversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bearing = _CountingWhirlBearing()

    def unexpected_inversion(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("rank-deficient matrices must not be inverted")

    monkeypatch.setattr(
        "ALB.dynamics.identification.recognize_kc",
        unexpected_inversion,
    )
    with pytest.raises(ALB.CalculationError, match="ill-conditioned") as caught:
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(semi_axes=(1.0e-4, 1.0e-200)),
            np.arange(100) * 1.0e-3,
            frequency_hz=10.0,
        )

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["displacement_rank"] < 2


@pytest.mark.parametrize("frequency_hz", [0.0, -1.0, np.nan, np.inf])
def test_dynamic_coefficients_reject_invalid_frequency_before_runtime(
    frequency_hz: float,
) -> None:
    bearing = _CountingWhirlBearing()

    with pytest.raises(ValueError, match="finite and > 0"):
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(),
            np.arange(100) * 1.0e-3,
            frequency_hz=frequency_hz,
        )

    assert bearing.fresh_count == 0


def test_dynamic_coefficients_reject_complex_time_before_runtime() -> None:
    bearing = _CountingWhirlBearing()

    with pytest.raises(TypeError, match="time_grid must be real"):
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(),
            np.arange(100, dtype=float) * 1.0e-3 + 1.0j,
            frequency_hz=10.0,
        )

    assert bearing.fresh_count == 0


def test_dynamic_coefficients_wraps_matrix_diagnostic_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bearing = _CountingWhirlBearing()

    def fail_svd(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(np.linalg, "matrix_rank", fail_svd)
    with pytest.raises(
        ALB.CalculationError,
        match="matrix diagnostics failed",
    ) as caught:
        ALB.BearingAnalysis(bearing).dynamic_coefficients(
            _trajectory(),
            np.arange(100) * 1.0e-3,
            frequency_hz=10.0,
        )

    snapshot = caught.value.failure_snapshot
    assert snapshot is not None
    assert snapshot.metadata["failure_phase"] == "matrix_diagnostics"
    assert snapshot.metadata["exception_type"] == "LinAlgError"
    assert set(snapshot.values) >= {
        "forward_displacement",
        "forward_force",
        "reverse_displacement",
        "reverse_force",
        "displacement_matrix_real",
        "displacement_matrix_imag",
    }


def test_zero_load_equilibrium_is_rejected_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = ALB.BearingConfig(_liquid_spec(1.0e-3))
    analysis = ALB.build_bearing(config).analysis

    def unexpected_runtime() -> object:
        raise AssertionError("zero load must be rejected before runtime creation")

    monkeypatch.setattr(analysis, "_new_runtime", unexpected_runtime)
    with pytest.raises(ValueError, match="nonzero load"):
        analysis.find_equilibrium(
            load=(0.0, 0.0),
            initial_displacement=(0.0, 0.0),
        )


def test_only_exact_zero_load_uses_the_pre_runtime_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = ALB.BearingConfig(_liquid_spec(1.0e-3))
    analysis = ALB.build_bearing(config).analysis

    class _ExpectedRuntimeCreation(RuntimeError):
        """Mark that a nonzero load reached runtime creation."""

    def expected_runtime() -> object:
        raise _ExpectedRuntimeCreation

    monkeypatch.setattr(analysis, "_new_runtime", expected_runtime)
    with pytest.raises(_ExpectedRuntimeCreation):
        analysis.find_equilibrium(
            load=(np.nextafter(0.0, 1.0), 0.0),
            initial_displacement=(0.0, 0.0),
        )


def test_unit_adapter_uses_bearing_local_time_step() -> None:
    config = ALB.BearingConfig(
        _liquid_spec(5.0, unit_system="nondimensional")
    )

    simulation = ALB.SimulationConfig(
        rotor=_Rotor(1.0e-3),
        mounts=(ALB.BearingMount(config, 0, unit_adapter=_adapter()),),
        time_step=1.0e-3,
        steps=1,
    )

    assert simulation.mounts[0].config.spec["time_step"] == 5.0


def test_unit_adapter_rejects_global_dt_used_as_local_dt() -> None:
    config = ALB.BearingConfig(
        _liquid_spec(1.0e-3, unit_system="nondimensional")
    )

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"mounts\[0\]\.config\.time_step.*bearing-local",
    ):
        ALB.SimulationConfig(
            rotor=_Rotor(1.0e-3),
            mounts=(ALB.BearingMount(config, 0, unit_adapter=_adapter()),),
            time_step=1.0e-3,
            steps=1,
        )


def test_standalone_multi_pad_rejects_explicit_child_dt_mismatch() -> None:
    config = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "pads": [
                _liquid_spec(1.0e-3),
                _liquid_spec(2.0e-3),
            ],
        }
    )

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"config\.pads\[1\]\.time_step",
    ):
        ALB.build_bearing(config)


def test_standalone_nested_multi_pad_rejects_grandchild_dt_mismatch() -> None:
    config = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "pads": [
                {
                    "family": "multi_pad",
                    "pads": [_liquid_spec(2.0e-3)],
                }
            ],
        }
    )

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"config\.pads\[0\]\.pads\[0\]\.time_step",
    ):
        ALB.build_bearing(config)


def test_file_referenced_multi_pad_rejects_child_dt_before_build(
    tmp_path: Path,
) -> None:
    child = {
        "schema_version": "0.4.0",
        "kind": "bearing",
        "spec": _liquid_spec(2.0e-3),
    }
    parent = {
        "schema_version": "0.4.0",
        "kind": "bearing",
        "spec": {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "pads": ["child.json5"],
        },
    }
    (tmp_path / "child.json5").write_text(
        json.dumps(child),
        encoding="utf-8",
    )
    parent_path = tmp_path / "parent.json5"
    parent_path.write_text(json.dumps(parent), encoding="utf-8")

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"config\.pads\[0\]\.time_step",
    ):
        ALB.bearing_from_file(parent_path)


def test_rotor_protocol_declares_required_dt() -> None:
    assert isinstance(_Rotor(1.0e-3), RotorProtocol)
    assert not isinstance(_RotorWithoutDt(), RotorProtocol)


def test_third_party_rotor_without_dt_fails_during_configuration() -> None:
    with pytest.raises(TypeError, match="RotorProtocol"):
        ALB.SimulationConfig(
            rotor=_RotorWithoutDt(),  # type: ignore[arg-type]
            mounts=(
                ALB.BearingMount(
                    ALB.BearingConfig(_liquid_spec(1.0e-3)),
                    0,
                ),
            ),
            time_step=1.0e-3,
            steps=1,
        )
