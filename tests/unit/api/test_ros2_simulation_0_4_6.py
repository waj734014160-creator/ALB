"""Public ROS2 coupled-simulation options added in ALB 0.4.6.

``SimulationConfig(integrator="ros2")`` integrates the rotor and the bearing
forces synchronously with a two-stage Rosenbrock-W method. These tests use the
public API with real liquid-film, gas-film, and active bearings on a small
physical plant: result contract and agreement with the staggered path,
topology and option validation, sampled controllers, user initial states,
file configuration, and the failure contract.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import ALB
from ALB.dynamics import Ros2Options
from tests._support.simulation_0_4_6 import (
    NEW_METADATA_KEYS,
    TIME_STEP,
    ProtocolRotor,
    active_runtime,
    adjustment_warnings,
    fuzzy_config,
    inherited_pid_child,
    liquid_config,
    pid_config,
    recorded_warnings,
    ross_rotor,
    simulation_config,
)


H = TIME_STEP
END_TIME = 60 * H
RESULT_FIELDS = ("rotor_displacement", "rotor_velocity", "bearing_force")


def _relative_difference(actual: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(actual - reference) / np.linalg.norm(reference))


@functools.cache
def _liquid_run(integrator: str, time_step: float) -> ALB.SimulationResult:
    """Run the liquid-film plant up to ``END_TIME`` once per configuration."""

    steps = int(round(END_TIME / time_step))
    config = simulation_config(
        liquid_config(time_step),
        steps=steps,
        time_step=time_step,
        integrator=integrator,
    )
    return ALB.build_simulation(config).run()


# ---------------------------------------------------------------------------
# Result contract and accuracy
# ---------------------------------------------------------------------------


def test_ros2_liquid_film_run_keeps_the_staggered_result_contract() -> None:
    staggered = _liquid_run("staggered", H)
    ros2 = _liquid_run("ros2", H)

    np.testing.assert_array_equal(ros2.time, staggered.time)
    for field in RESULT_FIELDS:
        assert getattr(ros2, field).shape == getattr(staggered, field).shape
        assert np.all(np.isfinite(getattr(ros2, field)))
    assert ros2.convergence.converged
    assert ros2.metadata["complete"] is True
    assert ros2.metadata["committed_steps"] == 61
    assert ros2.metadata["integrator"] == "ros2"
    assert ros2.metadata["time_step"] == H
    assert ros2.metadata["ros2_options"] == Ros2Options().to_dict()
    assert ros2.metadata["control_periods"] == ()
    assert ros2.metadata["time_step_adjustment"] is None
    assert ros2.metadata["initial_rotor_state"] is None
    assert NEW_METADATA_KEYS.isdisjoint(staggered.metadata)


def test_ros2_agrees_with_staggered_and_converges_under_step_halving() -> None:
    final = {
        (integrator, time_step): (
            _liquid_run(integrator, time_step).rotor_displacement[-1]
        )
        for integrator in ("staggered", "ros2")
        for time_step in (H, H / 2)
    }

    # Both schemes describe the same physics on a short run.
    assert _relative_difference(final["ros2", H], final["staggered", H]) < 0.1
    ros2_change = _relative_difference(final["ros2", H], final["ros2", H / 2])
    staggered_change = _relative_difference(
        final["staggered", H], final["staggered", H / 2]
    )
    # Halving the step barely changes ROS2, and less than the lagged scheme.
    assert ros2_change < 1.0e-2
    assert ros2_change < staggered_change


def test_ros2_gas_film_runs() -> None:
    gas = ALB.BearingConfig(
        {
            "family": "gas_film",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "film": {
                "circumferential_elements": 5,
                "axial_elements": 3,
                "max_iterations": 5,
                "solver_tolerance": 1.0e-6,
                "eccentricity": 0.0,
            },
        }
    )
    results = {}
    diagnostics: dict[str, Any] = {}
    for integrator in ("staggered", "ros2"):
        simulation = ALB.build_simulation(
            simulation_config(gas, steps=10, integrator=integrator)
        )
        results[integrator] = simulation.run()
        if integrator == "ros2":
            diagnostics = simulation._coupling._ros2.diagnostics()

    ros2 = results["ros2"]
    assert ros2.metadata["integrator"] == "ros2"
    assert ros2.rotor_displacement.shape == (11, 1, 2)
    assert np.all(np.isfinite(ros2.bearing_force))
    assert np.linalg.norm(ros2.bearing_force[-1]) > 0.0
    assert _relative_difference(
        ros2.rotor_displacement[-1], results["staggered"].rotor_displacement[-1]
    ) < 0.2
    # Frozen Jacobian: one factorization, one committed f per step plus one
    # stage evaluation per step.
    assert diagnostics["w_factorizations"] == 1
    assert diagnostics["rhs_evaluations"] == 1 + 2 * 10
    assert diagnostics["actuator_states"] == 0


# ---------------------------------------------------------------------------
# Topology validation
# ---------------------------------------------------------------------------


def _thermal_liquid() -> ALB.BearingConfig:
    return liquid_config(thermal={"transient_enabled": False})


def _thermal_active() -> ALB.BearingConfig:
    spec = pid_config(None).to_dict()["spec"]
    spec["thermal"] = {"transient_enabled": False}
    return ALB.BearingConfig(spec)


def _multi_pad_with_thermal_child() -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": [
                liquid_config().to_dict()["spec"],
                _thermal_liquid().to_dict()["spec"],
            ],
        }
    )


@pytest.mark.parametrize(
    ("factory", "path"),
    [
        (_thermal_liquid, r"mounts\[0\]\.config uses a thermal model"),
        (_thermal_active, r"mounts\[0\]\.config uses a thermal model"),
        (
            _multi_pad_with_thermal_child,
            r"mounts\[0\]\.config\.pads\[1\] uses a thermal model",
        ),
    ],
    ids=["liquid_film", "active_lubricated", "multi_pad_child"],
)
def test_thermal_bearings_are_rejected_by_ros2_but_accepted_by_staggered(
    factory,
    path: str,
) -> None:
    rotor = ross_rotor()
    with pytest.raises(ALB.ConfigurationError, match="thermal") as caught:
        simulation_config(factory(), steps=2, rotor=rotor, integrator="ros2")
    assert caught.match(path)
    assert caught.match("integrator='staggered'")

    config = simulation_config(factory(), steps=2, rotor=rotor)
    assert config.integrator == "staggered"


def test_ros2_rejects_multi_pad_with_active_child_at_configuration() -> None:
    # MultiPad evaluates ROS2 stage forces through each child's probe_force;
    # an active child (controller and valve states) has none, so the topology
    # must be rejected at configuration instead of failing at reset.
    multi_pad = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": [
                liquid_config().to_dict()["spec"],
                inherited_pid_child(None),
            ],
        }
    )

    with pytest.raises(ALB.ConfigurationError, match="ros2") as caught:
        simulation_config(multi_pad, steps=2, integrator="ros2")
    assert caught.match(r"mounts\[0\]\.config\.pads\[1\]")

    config = simulation_config(multi_pad, steps=2)
    assert config.integrator == "staggered"


def test_ros2_requires_a_rotor_with_continuous_owner_hooks() -> None:
    with pytest.raises(ALB.ConfigurationError, match="owner hooks"):
        ALB.SimulationConfig(
            rotor=ProtocolRotor(H),
            mounts=(ALB.BearingMount(liquid_config(), 0),),
            time_step=H,
            steps=2,
            integrator="ros2",
        )


# ---------------------------------------------------------------------------
# Option validation
# ---------------------------------------------------------------------------


def test_ros2_options_require_the_ros2_integrator() -> None:
    with pytest.raises(ALB.ConfigurationError, match="integrator='ros2'"):
        simulation_config(liquid_config(), steps=2, ros2=Ros2Options())
    with pytest.raises(ALB.ConfigurationError, match="integrator='ros2'"):
        simulation_config(
            liquid_config(),
            steps=2,
            integrator="staggered",
            ros2=Ros2Options(jacobian_refresh=2),
        )


@pytest.mark.parametrize("integrator", ["rk4", "ROS2", "", None])
def test_unknown_integrator_is_a_configuration_error(integrator: object) -> None:
    with pytest.raises(ALB.ConfigurationError, match="integrator"):
        simulation_config(liquid_config(), steps=2, integrator=integrator)


def test_ros2_options_must_be_ros2_options() -> None:
    with pytest.raises(TypeError, match="Ros2Options"):
        simulation_config(
            liquid_config(),
            steps=2,
            integrator="ros2",
            ros2={"jacobian_refresh": 2},
        )


def test_jacobian_refresh_increases_w_factorizations() -> None:
    factorizations = {}
    for name, options in (
        ("frozen", None),
        ("every_2", Ros2Options(jacobian_refresh=2)),
    ):
        simulation = ALB.build_simulation(
            simulation_config(
                liquid_config(),
                steps=6,
                integrator="ros2",
                ros2=options,
            )
        )
        result = simulation.run()
        diagnostics = simulation._coupling._ros2.diagnostics()
        factorizations[name] = diagnostics["w_factorizations"]
        assert diagnostics["jacobian_evaluations"] == factorizations[name]
        assert result.metadata["ros2_options"]["jacobian_refresh"] == (
            None if options is None else 2
        )

    assert factorizations == {"frozen": 1, "every_2": 1 + 6 // 2}


# ---------------------------------------------------------------------------
# Sampled controllers under ROS2
# ---------------------------------------------------------------------------


def test_ros2_active_pid_samples_adjusted_control_period() -> None:
    period, adjusted_step = 7.0e-5, 7.0e-5 / 4
    with recorded_warnings() as caught:
        # T = 4 h = 8e-5 s -> 2 periods of m = 4 steps at h' = 1.75e-5 s.
        config = simulation_config(
            pid_config(period),
            steps=4,
            integrator="ros2",
            ros2=Ros2Options(jacobian_refresh="control_period"),
        )
    assert len(adjustment_warnings(caught)) == 1
    assert config.time_step == adjusted_step
    assert config.steps == 8

    simulation = ALB.build_simulation(config)
    result = simulation.run()
    controller = active_runtime(simulation)._controller
    diagnostics = simulation._coupling._ros2.diagnostics()

    np.testing.assert_allclose(result.time, np.arange(9) * adjusted_step, rtol=1.0e-12)
    assert np.all(np.isfinite(result.rotor_displacement))
    assert controller.dt == period
    assert len(controller.results) == 8 // 4 + 1
    np.testing.assert_allclose(
        np.asarray(controller.results["t"], dtype=float),
        np.arange(3) * period,
        rtol=1.0e-12,
    )
    assert diagnostics["control_steps_per_period"] == (4,)
    # The Jacobian is refreshed at the two controller samples after reset.
    assert diagnostics["w_factorizations"] == 1 + 2
    assert result.metadata["integrator"] == "ros2"
    assert result.metadata["time_step_adjustment"] == config.time_step_adjustment
    assert result.metadata["ros2_options"]["jacobian_refresh"] == "control_period"


def test_ros2_active_fuzzy_pid_runs_with_control_period() -> None:
    period, steps = 4 * H, 8
    simulation = ALB.build_simulation(
        simulation_config(fuzzy_config(period), steps=steps, integrator="ros2")
    )
    result = simulation.run()
    controller = active_runtime(simulation)._controller

    assert result.metadata["integrator"] == "ros2"
    assert result.rotor_displacement.shape == (steps + 1, 1, 2)
    assert np.all(np.isfinite(result.rotor_displacement))
    assert np.all(np.isfinite(result.bearing_force))
    assert controller.dt == period
    assert len(controller.results) == steps // 4 + 1


# ---------------------------------------------------------------------------
# Initial rotor state
# ---------------------------------------------------------------------------


def _initial_state() -> np.ndarray:
    # SinglePlant state [x, y, alpha, beta, vx, vy, valpha, vbeta].
    return np.asarray([1.0e-6, -2.0e-6, 0.0, 0.0, 1.0e-4, -3.0e-4, 0.0, 0.0])


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (np.zeros(7), "shape"),
        (np.zeros((2, 4)), "shape"),
        ([0.0] * 7 + [np.nan], "finite"),
        (["x"] * 8, "real vector"),
    ],
)
def test_initial_rotor_state_is_validated(value: object, message: str) -> None:
    with pytest.raises(ALB.ConfigurationError, match=message):
        simulation_config(liquid_config(), steps=2, initial_rotor_state=value)


@pytest.mark.parametrize("integrator", ["staggered", "ros2"])
def test_initial_rotor_state_is_the_committed_step_zero_state(
    integrator: str,
) -> None:
    supplied = _initial_state()
    config = simulation_config(
        liquid_config(),
        steps=3,
        integrator=integrator,
        initial_rotor_state=supplied,
    )
    supplied[:] = 0.0  # The configuration holds its own frozen copy.
    stored = config.initial_rotor_state
    assert not stored.flags.writeable
    np.testing.assert_array_equal(stored, _initial_state())

    result = ALB.build_simulation(config).run()

    np.testing.assert_array_equal(result.rotor_displacement[0, 0], [1.0e-6, -2.0e-6])
    np.testing.assert_array_equal(result.rotor_velocity[0, 0], [1.0e-4, -3.0e-4])
    assert np.linalg.norm(result.bearing_force[0]) > 0.0
    assert result.metadata["initial_rotor_state"] == "user-supplied"
    assert result.metadata["integrator"] == integrator
    assert result.metadata["control_periods"] == ()


# ---------------------------------------------------------------------------
# File configuration
# ---------------------------------------------------------------------------


def _write_simulation(tmp_path: Path, time_grid: dict[str, object]) -> Path:
    (tmp_path / "bearing.json5").write_text(
        json.dumps(liquid_config().to_dict()),
        encoding="utf-8",
    )
    document = {
        "schema_version": "0.4.0",
        "kind": "simulation",
        "spec": {
            "rotor": {
                "model": "ross_excel",
                "path": "resources/missing_rotor.xlsx",
                "frequency_hz": 50.0,
            },
            "time_grid": time_grid,
            "mounts": [{"bearing": "bearing.json5", "node": 0}],
            "loads": [],
        },
    }
    path = tmp_path / "simulation.json5"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.fixture
def rotor_loads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Replace the ROSS Excel loader with a recording plant factory."""

    calls: list[dict[str, object]] = []

    def fake_rotor0(**kwargs: object) -> object:
        calls.append(kwargs)
        return ross_rotor(float(kwargs["dt"]))  # type: ignore[arg-type]

    monkeypatch.setattr("ALB.dynamics.rotor.rotor0", fake_rotor0)
    return calls


@pytest.mark.parametrize(
    ("time_grid", "message"),
    [
        (
            {"integrator": "staggered", "jacobian_refresh": 3},
            "jacobian_refresh requires integrator='ros2'",
        ),
        (
            {"jacobian_refresh": "control_period"},
            "jacobian_refresh requires integrator='ros2'",
        ),
        ({"integrator": "rk4"}, "integrator must be"),
        ({"integrator": "ros2", "jacobian_refresh": 0}, "jacobian_refresh"),
        ({"integrator": "ros2", "jacobian_refresh": True}, "jacobian_refresh"),
        ({"integrator": "ros2", "jacobian_refresh": "always"}, "jacobian_refresh"),
    ],
)
def test_time_grid_integrator_is_validated_before_the_rotor_is_loaded(
    tmp_path: Path,
    rotor_loads: list[dict[str, object]],
    time_grid: dict[str, object],
    message: str,
) -> None:
    path = _write_simulation(
        tmp_path,
        {"time_step": H, "steps": 3, **time_grid},
    )

    with pytest.raises(ALB.ConfigurationError, match=message):
        ALB.load_simulation_config(path)
    assert rotor_loads == []


def test_invalid_time_grid_fails_before_reading_a_missing_rotor_file(
    tmp_path: Path,
) -> None:
    path = _write_simulation(
        tmp_path,
        {"time_step": H, "steps": 3, "integrator": "staggered", "jacobian_refresh": 3},
    )

    with pytest.raises(ALB.ConfigurationError, match="jacobian_refresh"):
        ALB.load_simulation_config(path)


@pytest.mark.parametrize("refresh", [3, "control_period", None])
def test_time_grid_selects_ros2_with_jacobian_refresh(
    tmp_path: Path,
    rotor_loads: list[dict[str, object]],
    refresh: object,
) -> None:
    time_grid: dict[str, object] = {"time_step": H, "steps": 3, "integrator": "ros2"}
    if refresh is not None:
        time_grid["jacobian_refresh"] = refresh

    config = ALB.load_simulation_config(_write_simulation(tmp_path, time_grid))

    assert len(rotor_loads) == 1
    assert config.integrator == "ros2"
    assert isinstance(config.ros2, Ros2Options)
    assert config.ros2.jacobian_refresh == refresh


def test_time_grid_defaults_to_the_staggered_integrator(
    tmp_path: Path,
    rotor_loads: list[dict[str, object]],
) -> None:
    config = ALB.load_simulation_config(
        _write_simulation(tmp_path, {"time_step": H, "steps": 3})
    )

    assert config.integrator == "staggered"
    assert config.ros2 is None


# ---------------------------------------------------------------------------
# Failure contract
# ---------------------------------------------------------------------------


def test_ros2_stage_failure_raises_simulation_error_with_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulation = ALB.build_simulation(
        simulation_config(liquid_config(), steps=6, integrator="ros2")
    )
    runtime = simulation._coupling.bindings[0].bearing
    original = runtime.probe_force
    stage_calls: list[float] = []

    def failing_probe(dto: Any) -> np.ndarray:
        # Reset-time Jacobian probes run at t = 0; stage probes run at t_j.
        if dto.time > 0.0:
            stage_calls.append(float(dto.time))
            if len(stage_calls) == 3:
                raise FloatingPointError("injected ROS2 stage failure")
        return original(dto)

    monkeypatch.setattr(runtime, "probe_force", failing_probe)

    with pytest.raises(ALB.SimulationError, match="simulation failed") as caught:
        simulation.run()

    error = caught.value
    assert type(error.__cause__).__name__ == "Ros2StageError"
    assert isinstance(error.__cause__.__cause__, FloatingPointError)
    np.testing.assert_allclose(stage_calls, [H, 2 * H, 3 * H], rtol=1.0e-12)

    partial = error.partial_result
    assert partial is not None
    assert simulation.latest_result is partial
    np.testing.assert_allclose(partial.time, [0.0, H, 2 * H], rtol=1.0e-12)
    assert partial.rotor_displacement.shape == (3, 1, 2)
    assert partial.metadata["complete"] is False
    assert partial.metadata["committed_steps"] == 3
    assert partial.metadata["requested_steps"] == 7
    assert partial.metadata["integrator"] == "ros2"

    snapshot = error.failure_snapshot
    assert snapshot is not None
    metadata = snapshot.metadata
    assert metadata["failure_phase"] == "advance"
    assert metadata["error_type"] == "Ros2StageError"
    assert metadata["committed_steps"] == partial.metadata["committed_steps"]
    assert metadata["committed_step_index"] == 2
    assert metadata["physical_step_committed"] is False
    assert metadata["physical_complete"] is False
    assert metadata["integrator"] == "ros2"
    coupling_failure = snapshot.values["coupling_failure"]["metadata"]
    assert coupling_failure["integrator"] == "ros2"
    assert coupling_failure["attempted_context"]["step_index"] == 3
    np.testing.assert_array_equal(
        snapshot.values["last_rotor_displacement"],
        partial.rotor_displacement[-1],
    )
