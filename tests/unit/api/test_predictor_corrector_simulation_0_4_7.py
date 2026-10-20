"""Public predictor-corrector coupled simulations added in ALB 0.4.7.

``SimulationConfig(integrator="predictor_corrector")`` trials every bearing
from its committed state (probe or checkpoint/restore), iterates the
interface force without derivatives, and commits each bearing once per step.
These tests use the public API with real liquid-film (with and without a
transient thermal model), active PID, external-spool, and multi-pad bearings
on the small physical plant of the 0.4.6 tests: result contract and metadata,
agreement with the staggered path, topology and option validation, control
periods, file configuration, non-convergence, and the failure contract.
"""

from __future__ import annotations

import copy
import functools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import ALB
from ALB.dynamics import PredictorCorrectorOptions
from tests._support.dynamics.analytic_bearings import (
    LinearSpoolProvider,
    OpaqueLinearSpoolProvider,
)
from tests._support.simulation_0_4_6 import (
    NEW_METADATA_KEYS,
    TIME_STEP,
    ProtocolRotor,
    active_runtime,
    adjustment_warnings,
    inherited_pid_child,
    liquid_config,
    pid_config,
    recorded_warnings,
    ross_rotor,
    simulation_config,
)
from tools.reference.generate_coupling_staggered_pre_0_4_7_reference import (
    external_spool_spec,
    multi_pad_spec,
    thermal_liquid_spec,
)


H = TIME_STEP
PC = "predictor_corrector"
PC_METADATA_KEYS = frozenset(
    {"predictor_corrector_options", "predictor_corrector_diagnostics"}
)
DIAGNOSTIC_KEYS = frozenset(
    {
        "integrator",
        "steps",
        "trial_iterations",
        "trial_evaluations",
        "commits",
        "commit_evaluations",
        "iterations_per_step",
        "nonconverged_steps",
        "max_final_residual",
        "max_consistency_residual",
        "residual_ratio",
        "aitken_omega_range",
        "trial_modes",
        "spool_trials",
    }
)


@functools.cache
def _liquid_run(integrator: str, steps: int) -> ALB.SimulationResult:
    config = simulation_config(liquid_config(), steps=steps, integrator=integrator)
    return ALB.build_simulation(config).run()


def _config(spec: dict[str, Any], **kwargs: Any) -> ALB.BearingConfig:
    return ALB.BearingConfig(copy.deepcopy(spec), **kwargs)


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------


def test_liquid_film_run_keeps_the_result_contract_and_adds_diagnostics() -> None:
    staggered = _liquid_run("staggered", 30)
    result = _liquid_run(PC, 30)

    assert result.metadata["complete"] is True
    assert result.time.shape == staggered.time.shape
    for field in ("rotor_displacement", "rotor_velocity", "bearing_force"):
        assert getattr(result, field).shape == getattr(staggered, field).shape
    assert set(result.metadata) - set(staggered.metadata) == (
        NEW_METADATA_KEYS | PC_METADATA_KEYS
    )
    assert result.metadata["integrator"] == PC
    assert dict(result.metadata["predictor_corrector_options"]) == {
        **PredictorCorrectorOptions().to_dict(),
        "omega_bounds": (0.01, 1.5),
    }
    diagnostics = result.metadata["predictor_corrector_diagnostics"]
    assert set(diagnostics) == DIAGNOSTIC_KEYS
    assert diagnostics["steps"] == 30
    assert diagnostics["commits"] == 31
    assert diagnostics["nonconverged_steps"] == 0
    assert diagnostics["trial_modes"] == ("probe",)
    assert diagnostics["iterations_per_step"]["max"] <= 5


def test_default_and_ros2_runs_do_not_publish_predictor_corrector_metadata() -> None:
    assert not PC_METADATA_KEYS & set(_liquid_run("staggered", 3).metadata)
    assert not PC_METADATA_KEYS & set(_liquid_run("ros2", 3).metadata)


def test_predictor_corrector_agrees_with_fine_staggered_solution() -> None:
    end = 60 * H
    pc = _liquid_run(PC, 60)
    fine = ALB.build_simulation(
        simulation_config(
            liquid_config(H / 8),
            steps=480,
            time_step=H / 8,
            rotor=ross_rotor(H / 8),
        )
    ).run()
    coarse = _liquid_run("staggered", 60)
    reference = fine.rotor_displacement[-1]
    assert fine.time[-1] == pytest.approx(end)
    pc_error = np.linalg.norm(pc.rotor_displacement[-1] - reference)
    staggered_error = np.linalg.norm(coarse.rotor_displacement[-1] - reference)
    assert pc_error < staggered_error


def test_result_write_adds_only_predictor_corrector_metadata_files(
    tmp_path: Path,
) -> None:
    def files(root: Path) -> set[str]:
        return {
            item.relative_to(root).as_posix()
            for item in root.rglob("*")
            if item.is_file()
        }

    _liquid_run("staggered", 3).write(tmp_path / "default")
    _liquid_run(PC, 3).write(tmp_path / "pc")
    default, written = files(tmp_path / "default"), files(tmp_path / "pc")
    assert default < written
    added = {name.split("/")[1].removesuffix(".json") for name in written - default}
    assert added == NEW_METADATA_KEYS | PC_METADATA_KEYS
    assert "metadata/predictor_corrector_diagnostics/iterations_per_step/histogram.json" in written


# ---------------------------------------------------------------------------
# Stateful families
# ---------------------------------------------------------------------------


def test_small_transient_thermal_film_runs_with_checkpointed_trials() -> None:
    simulation = ALB.build_simulation(
        simulation_config(_config(thermal_liquid_spec(True)), steps=5, integrator=PC)
    )
    result = simulation.run()

    assert result.metadata["complete"] is True
    diagnostics = result.metadata["predictor_corrector_diagnostics"]
    assert set(diagnostics) == DIAGNOSTIC_KEYS
    assert diagnostics["trial_modes"] == ("checkpoint",)
    assert diagnostics["commits"] == 6
    assert diagnostics["nonconverged_steps"] == 0
    bearing = active_runtime(simulation)
    # Committed thermal memory reflects the committed step, not a trial.
    snapshot = bearing.result_snapshot()
    assert snapshot.metadata["time"] == pytest.approx(5 * H)
    np.testing.assert_array_equal(
        np.asarray(bearing._temperature_prev),
        np.asarray(snapshot.values["temperature"]),
    )
    np.testing.assert_array_equal(
        result.bearing_force[-1][0],
        np.asarray(snapshot.values["force"]),
    )


def test_active_pid_runs_controller_once_per_commit() -> None:
    simulation = ALB.build_simulation(
        simulation_config(pid_config(None), steps=8, integrator=PC)
    )
    result = simulation.run()
    runtime = active_runtime(simulation)
    diagnostics = result.metadata["predictor_corrector_diagnostics"]

    assert diagnostics["trial_modes"] == ("checkpoint",)
    assert diagnostics["trial_iterations"] > 8
    assert runtime._control_counter == 9
    assert len(runtime._controller.results) == 9


def test_control_period_adjustment_applies_to_predictor_corrector() -> None:
    control_period = 3.5 * H
    with recorded_warnings() as caught:
        config = simulation_config(
            pid_config(control_period),
            steps=8,
            integrator=PC,
        )
    assert len(adjustment_warnings(caught)) == 1
    assert config.integrator == PC
    simulation = ALB.build_simulation(config)
    result = simulation.run()
    runtime = active_runtime(simulation)
    steps_per_period = config.control_periods[0]["control_steps_per_period"]

    assert steps_per_period == 4
    assert result.metadata["time_step_adjustment"] is not None
    assert result.metadata["predictor_corrector_options"]["mode"] == "iterate"
    # The controller ran on commits 0, 4, 8, ... only.
    assert len(runtime._controller.results) == -(-(config.steps + 1) // 4)
    assert runtime._control_counter == config.steps + 1


def test_multi_pad_with_thermal_and_active_children_is_checkpointed() -> None:
    result = ALB.build_simulation(
        simulation_config(_config(multi_pad_spec()), steps=3, integrator=PC)
    ).run()
    diagnostics = result.metadata["predictor_corrector_diagnostics"]
    assert diagnostics["trial_modes"] == ("checkpoint",)
    assert result.metadata["complete"] is True


@pytest.mark.parametrize(
    ("provider_type", "spool_trials"),
    [
        (LinearSpoolProvider, "provider_checkpoint"),
        (OpaqueLinearSpoolProvider, "held_per_step"),
    ],
)
def test_external_spool_bearing_uses_its_provider(provider_type, spool_trials) -> None:
    provider = provider_type(gain=2.0e4)
    config = ALB.SimulationConfig(
        rotor=ross_rotor(),
        mounts=(
            ALB.BearingMount(
                _config(external_spool_spec()),
                0,
                spool_provider=provider,
            ),
        ),
        time_step=H,
        steps=4,
        integrator=PC,
    )
    result = ALB.build_simulation(config).run()
    diagnostics = result.metadata["predictor_corrector_diagnostics"]
    assert diagnostics["spool_trials"] == (spool_trials,)
    assert diagnostics["trial_modes"] == ("probe",)
    np.testing.assert_allclose(provider.samples, np.arange(5) * H)


# ---------------------------------------------------------------------------
# Topology and option validation
# ---------------------------------------------------------------------------


def test_external_spool_child_inside_multi_pad_is_rejected_with_its_path() -> None:
    child = external_spool_spec()
    for key in ("time_step", "node", "unit_system"):
        child.pop(key)
    multi_pad = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": [liquid_config().to_dict()["spec"], child],
        }
    )
    with pytest.raises(ALB.ConfigurationError, match="predictor_corrector") as caught:
        simulation_config(multi_pad, steps=2, integrator=PC)
    assert caught.match(r"mounts\[0\]\.config\.pads\[1\]")
    assert caught.match("integrator='staggered'")


def test_thermal_and_active_children_are_accepted_inside_multi_pad() -> None:
    multi_pad = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": [liquid_config().to_dict()["spec"], inherited_pid_child(None)],
        }
    )
    assert simulation_config(multi_pad, steps=2, integrator=PC).integrator == PC


def test_predictor_corrector_requires_rotor_owner_hooks() -> None:
    with pytest.raises(ALB.ConfigurationError, match="owner hooks"):
        ALB.SimulationConfig(
            rotor=ProtocolRotor(H),
            mounts=(ALB.BearingMount(liquid_config(), 0),),
            time_step=H,
            steps=2,
            integrator=PC,
        )


def test_options_are_accepted_only_with_the_predictor_corrector() -> None:
    with pytest.raises(ALB.ConfigurationError, match="integrator='predictor_corrector'"):
        simulation_config(
            liquid_config(),
            steps=2,
            predictor_corrector=PredictorCorrectorOptions(),
        )
    with pytest.raises(ALB.ConfigurationError, match="integrator='predictor_corrector'"):
        simulation_config(
            liquid_config(),
            steps=2,
            integrator="ros2",
            predictor_corrector=PredictorCorrectorOptions(),
        )
    with pytest.raises(TypeError, match="PredictorCorrectorOptions"):
        simulation_config(
            liquid_config(),
            steps=2,
            integrator=PC,
            predictor_corrector={"mode": "pece"},
        )
    config = simulation_config(
        liquid_config(),
        steps=2,
        integrator=PC,
        predictor_corrector=PredictorCorrectorOptions(mode="pece"),
    )
    assert config.predictor_corrector == PredictorCorrectorOptions(mode="pece")
    assert hash(config.predictor_corrector) == hash(PredictorCorrectorOptions(mode="pece"))


def test_unknown_integrator_lists_the_predictor_corrector() -> None:
    with pytest.raises(ALB.ConfigurationError, match="predictor_corrector"):
        simulation_config(liquid_config(), steps=2, integrator="rk4")


# ---------------------------------------------------------------------------
# Non-convergence and failures
# ---------------------------------------------------------------------------


def test_nonconvergence_warns_once_and_counts_steps() -> None:
    options = PredictorCorrectorOptions(rtol=0.0, atol=1.0e-12, max_iterations=1)
    simulation = ALB.build_simulation(
        simulation_config(
            liquid_config(),
            steps=4,
            integrator=PC,
            predictor_corrector=options,
        )
    )
    with recorded_warnings() as caught:
        result = simulation.run()
    issued = [item for item in caught if issubclass(item.category, ALB.CouplingIterationWarning)]
    assert len(issued) == 1
    assert issubclass(ALB.CouplingIterationWarning, UserWarning)
    assert not issubclass(ALB.CouplingIterationWarning, ALB.ALBError)
    diagnostics = result.metadata["predictor_corrector_diagnostics"]
    assert diagnostics["nonconverged_steps"] == 4
    assert diagnostics["max_final_residual"] > 0.0
    assert result.metadata["complete"] is True


def test_nonconvergence_raise_seals_a_simulation_failure() -> None:
    options = PredictorCorrectorOptions(
        rtol=0.0,
        atol=1.0e-12,
        max_iterations=1,
        on_nonconvergence="raise",
    )
    simulation = ALB.build_simulation(
        simulation_config(liquid_config(), steps=4, integrator=PC, predictor_corrector=options)
    )
    with pytest.raises(ALB.SimulationError) as caught:
        simulation.run()
    error = caught.value
    assert error.partial_result is not None
    assert error.partial_result.metadata["committed_steps"] == 1
    snapshot = error.failure_snapshot
    assert snapshot.metadata["failure_phase"] == "advance"
    assert snapshot.metadata["error_type"] == "CouplingIterationError"
    assert snapshot.metadata["integrator"] == PC
    coupling = snapshot.values["coupling_failure"]["metadata"]
    assert coupling["integrator"] == PC
    assert coupling["physical_step_committed"] is False
    diagnostics = snapshot.metadata["predictor_corrector_diagnostics"]
    assert diagnostics["steps"] == 0
    # The step that ended the run is counted as non-converged, and the
    # iteration statistics include it.
    assert diagnostics["nonconverged_steps"] == 1
    assert diagnostics["trial_iterations"] == 1
    assert tuple(diagnostics["iterations_per_step"]["histogram"]) == ((1, 1),)
    assert diagnostics["iterations_per_step"]["mean"] == 1.0


def test_trial_failure_restores_the_thermal_bearing_and_seals_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulation = ALB.build_simulation(
        simulation_config(_config(thermal_liquid_spec(True)), steps=4, integrator=PC)
    )
    bearing = active_runtime(simulation)
    original = type(bearing)._solve_thermal_raw
    calls: list[int] = []
    committed_temperatures: list[np.ndarray] = []

    def failing(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        # The first evaluation at t = 2h is a trial: trials precede commits.
        if self._pending_input.time == pytest.approx(2 * H) and not committed_temperatures:
            committed_temperatures.append(np.asarray(self._temperature_prev).copy())
            raise RuntimeError("injected thermal non-convergence")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(bearing), "_solve_thermal_raw", failing)
    with pytest.raises(ALB.SimulationError) as caught:
        simulation.run()

    assert caught.value.failure_snapshot.metadata["error_type"] == "CouplingTrialError"
    # The bearing was rolled back to its committed state before sealing.
    assert bearing.lifecycle_state is ALB.contracts.LifecycleState.READY
    np.testing.assert_array_equal(
        np.asarray(bearing._temperature_prev),
        committed_temperatures[0],
    )
    partial = caught.value.partial_result
    assert bearing.result_snapshot().metadata["time"] == pytest.approx(
        partial.time[-1]
    )


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


def test_time_grid_selects_the_predictor_corrector_with_options(
    tmp_path: Path,
    rotor_loads: list[dict[str, object]],
) -> None:
    config = ALB.load_simulation_config(
        _write_simulation(
            tmp_path,
            {
                "time_step": H,
                "steps": 3,
                "integrator": PC,
                "predictor_corrector": {
                    "mode": "iterate",
                    "relaxation": "iqn_ils",
                    "omega_bounds": [0.05, 1.2],
                    "max_iterations": 12,
                    "on_nonconvergence": "raise",
                },
            },
        )
    )
    assert len(rotor_loads) == 1
    assert config.integrator == PC
    assert config.predictor_corrector == PredictorCorrectorOptions(
        relaxation="iqn_ils",
        omega_bounds=(0.05, 1.2),
        max_iterations=12,
        on_nonconvergence="raise",
    )


def test_time_grid_predictor_corrector_defaults_to_none(
    tmp_path: Path,
    rotor_loads: list[dict[str, object]],
) -> None:
    config = ALB.load_simulation_config(
        _write_simulation(tmp_path, {"time_step": H, "steps": 3, "integrator": PC})
    )
    assert config.integrator == PC
    assert config.predictor_corrector is None


@pytest.mark.parametrize(
    ("time_grid", "message"),
    [
        ({"predictor_corrector": {"mode": "pece"}}, "requires integrator='predictor_corrector'"),
        (
            {"integrator": "ros2", "predictor_corrector": {}},
            "requires integrator='predictor_corrector'",
        ),
        ({"integrator": PC, "predictor_corrector": {"unknown": 1}}, "unknown"),
        ({"integrator": PC, "predictor_corrector": {"max_iterations": 0}}, "max_iterations"),
        ({"integrator": PC, "predictor_corrector": {"omega_bounds": [1.0]}}, "omega_bounds"),
        ({"integrator": PC, "predictor_corrector": {"relaxation": "anderson"}}, "relaxation"),
        ({"integrator": PC, "predictor_corrector": "aitken"}, "predictor_corrector"),
        ({"integrator": PC, "jacobian_refresh": 3}, "jacobian_refresh requires"),
    ],
)
def test_time_grid_predictor_corrector_is_validated_before_the_rotor_is_loaded(
    tmp_path: Path,
    rotor_loads: list[dict[str, object]],
    time_grid: dict[str, object],
    message: str,
) -> None:
    path = _write_simulation(tmp_path, {"time_step": H, "steps": 3, **time_grid})
    with pytest.raises(ALB.ConfigurationError, match=message):
        ALB.load_simulation_config(path)
    assert rotor_loads == []
