"""Controller sampling period and simulation step adjustment (ALB 0.4.6).

``control.control_period`` ``Ts`` makes an active PID/fuzzy-PID controller run
every ``m = Ts / h`` evaluations and hold its command in between, while the
rotor, valves, and films keep the shared step ``h``. A simulation whose step
does not divide ``Ts`` keeps ``Ts`` and uses ``h' = Ts / ceil(Ts / h)``
(``Ts`` when ``h > Ts``) with ``steps' = m * ceil(T / Ts)`` and warns once
(ADR-0009). Unset periods keep the 0.4.5 path and metadata unchanged.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import warnings

import numpy as np
import pytest

import ALB
from ALB.config import FuzzyPIDConfig, PIDConfig
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from tests._support.simulation_0_4_6 import (
    FUZZY_RULE_ROOT,
    NEW_METADATA_KEYS,
    TIME_STEP,
    ProtocolRotor,
    active_runtime,
    adjustment_warnings,
    fuzzy_config,
    inherited_pid_child,
    liquid_config,
    pid_config,
    pid_spec,
    recorded_warnings,
    ross_rotor,
    simulation_config,
)


H = TIME_STEP
# 7e-5 / 2e-5 = 3.5: m = ceil(3.5) = 4 and h' = 1.75e-5.
NON_INTEGER_PERIOD = 7.0e-5
ADJUSTED_STEP = NON_INTEGER_PERIOD / 4


# ---------------------------------------------------------------------------
# Step adjustment rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("control_period", "steps_per_period"),
    [
        (H, 1),
        # 6e-5 / 2e-5 = 2.9999999999999996: accepted by the 1e-9 tolerance.
        (6.0e-5, 3),
        (8.0e-5, 4),
        # 1e-4 / 2e-5 = 5.000000000000001.
        (1.0e-4, 5),
    ],
)
def test_integer_multiple_control_period_keeps_the_requested_grid(
    control_period: float,
    steps_per_period: int,
) -> None:
    rotor = ross_rotor()
    bearing = pid_config(control_period)
    with recorded_warnings() as caught:
        config = simulation_config(bearing, steps=20, rotor=rotor)

    assert adjustment_warnings(caught) == []
    assert config.time_step == H
    assert config.steps == 20
    assert config.rotor is rotor
    assert rotor.dt == H
    assert config.mounts[0].config is bearing
    assert config.time_step_adjustment is None
    assert [dict(item) for item in config.control_periods] == [
        {
            "mount": 0,
            "path": "mounts[0].config.control.control_period",
            "local_control_period": control_period,
            "control_period": control_period,
            "control_steps_per_period": steps_per_period,
        }
    ]


def test_non_integer_control_period_adjusts_step_and_warns_once() -> None:
    rotor = ross_rotor()
    bearing = pid_config(NON_INTEGER_PERIOD)
    with recorded_warnings() as caught:
        config = ALB.SimulationConfig(
            rotor=rotor,
            mounts=(ALB.BearingMount(bearing, 0),),
            time_step=H,
            steps=20,
        )

    adjusted = adjustment_warnings(caught)
    assert len(adjusted) == 1
    warning = adjusted[0].message
    assert isinstance(warning, ALB.TimeStepAdjustedWarning)
    assert isinstance(warning, UserWarning)
    # The warning points at the caller that built the configuration.
    assert Path(adjusted[0].filename).resolve() == Path(__file__).resolve()
    # T = 20 h = 4e-4 s = 5.71 Ts -> 6 periods of m = 4 steps.
    message = str(warning)
    for text in (
        repr(H),
        repr(NON_INTEGER_PERIOD),
        repr(ADJUSTED_STEP),
        "4 step(s) per control period",
        "24 steps instead of 20",
    ):
        assert text in message
    adjustment = warning.adjustment
    assert adjustment["requested_time_step"] == H
    assert adjustment["requested_steps"] == 20
    assert adjustment["requested_end_time"] == 20 * H
    assert adjustment["control_period"] == NON_INTEGER_PERIOD
    assert adjustment["time_step"] == ADJUSTED_STEP
    assert adjustment["control_steps_per_period"] == 4
    assert adjustment["steps"] == 24
    assert adjustment["end_time"] == 24 * ADJUSTED_STEP
    assert config.time_step_adjustment == adjustment
    with pytest.raises(TypeError):
        adjustment["steps"] = 1  # type: ignore[index]

    assert config.time_step == ADJUSTED_STEP
    assert config.steps == 24
    assert config.rotor is rotor
    assert rotor.dt == ADJUSTED_STEP
    for mount in config.mounts:
        assert mount.config.spec["time_step"] == ADJUSTED_STEP
        # The controller period is a property of the real controller.
        assert mount.config.spec["control"]["control_period"] == NON_INTEGER_PERIOD
    assert config.mounts[0].node == 0
    assert bearing.spec["time_step"] == H
    assert [item["control_steps_per_period"] for item in config.control_periods] == [4]
    assert config.control_periods[0]["control_period"] == NON_INTEGER_PERIOD


def test_effective_configuration_revalidates_without_another_adjustment() -> None:
    with recorded_warnings():
        adjusted = simulation_config(pid_config(NON_INTEGER_PERIOD), steps=20)

    with recorded_warnings() as caught:
        again = ALB.SimulationConfig(
            rotor=adjusted.rotor,
            mounts=adjusted.mounts,
            time_step=adjusted.time_step,
            steps=adjusted.steps,
            loads=adjusted.loads,
        )

    assert adjustment_warnings(caught) == []
    assert again.time_step == adjusted.time_step
    assert again.steps == adjusted.steps
    assert again.time_step_adjustment is None
    assert [item["control_steps_per_period"] for item in again.control_periods] == [4]
    # The rotor was retimed in place, so the requested step no longer matches.
    with pytest.raises(ALB.ConfigurationError, match=r"rotor\.dt"):
        simulation_config(
            pid_config(NON_INTEGER_PERIOD),
            steps=20,
            rotor=adjusted.rotor,
        )


@pytest.mark.parametrize(
    ("time_step", "control_period", "steps", "expected_steps"),
    [
        # h > Ts: h' = Ts; T = 6e-4 s is six whole periods.
        (1.5e-4, 1.0e-4, 4, 6),
        # h = 2 Ts (ratio 0.5 rounds to zero steps per period).
        (2.0e-4, 1.0e-4, 3, 6),
    ],
)
def test_step_larger_than_control_period_uses_one_step_per_period(
    time_step: float,
    control_period: float,
    steps: int,
    expected_steps: int,
) -> None:
    rotor = ross_rotor(time_step)
    with recorded_warnings() as caught:
        config = simulation_config(
            pid_config(control_period, time_step),
            steps=steps,
            time_step=time_step,
            rotor=rotor,
        )

    (warning,) = adjustment_warnings(caught)
    assert warning.message.adjustment["control_steps_per_period"] == 1
    assert config.time_step == control_period
    assert rotor.dt == control_period
    assert config.steps == expected_steps
    assert config.control_periods[0]["control_steps_per_period"] == 1


@pytest.mark.parametrize(
    ("time_step", "control_period", "steps"),
    [
        (3.0e-5, 1.0e-4, 10),  # T = 3 Ts exactly
        (3.0e-5, 1.0e-4, 11),  # T = 3.3 Ts -> rounded up to 4 Ts
        (H, NON_INTEGER_PERIOD, 20),  # T = 5.71 Ts -> 6 Ts
        (H, NON_INTEGER_PERIOD, 7),  # T = 2 Ts exactly (14 h' = 14e-5)
        (3.0e-5, 1.0e-4, 0),  # empty run stays empty
    ],
)
def test_adjusted_duration_is_kept_or_rounded_up_to_whole_periods(
    time_step: float,
    control_period: float,
    steps: int,
) -> None:
    with recorded_warnings() as caught:
        config = simulation_config(
            pid_config(control_period, time_step),
            steps=steps,
            time_step=time_step,
        )

    (warning,) = adjustment_warnings(caught)
    adjustment = warning.message.adjustment
    m = math.ceil(control_period / time_step)
    requested_end = steps * time_step
    end_time = config.steps * config.time_step

    assert adjustment["control_steps_per_period"] == m
    assert config.time_step == control_period / m
    assert config.time_step <= time_step
    assert config.steps % m == 0
    assert adjustment["end_time"] == end_time
    assert adjustment["requested_end_time"] == requested_end
    periods = requested_end / control_period
    if abs(periods - round(periods)) <= 1.0e-9:
        assert end_time == pytest.approx(requested_end, rel=1.0e-12, abs=0.0)
        assert config.steps == m * round(periods)
    else:
        assert end_time >= requested_end
        assert end_time - requested_end < control_period


# ---------------------------------------------------------------------------
# Sampled controller execution
# ---------------------------------------------------------------------------


def _assert_sample_times(controller: PID, period: float, count: int) -> None:
    times = np.asarray(controller.results["t"], dtype=float)
    np.testing.assert_allclose(
        times,
        np.arange(count) * period,
        rtol=1.0e-12,
        atol=1.0e-18,
    )


def test_staggered_controller_samples_every_m_steps_and_holds_valve_command() -> None:
    period, m, steps = 4 * H, 4, 18
    simulation = ALB.build_simulation(
        simulation_config(pid_config(period), steps=steps)
    )
    result = simulation.run()
    runtime = active_runtime(simulation)
    controller = runtime._controller

    assert result.time.shape == (steps + 1,)
    assert runtime.control_steps_per_period == m
    assert controller.dt == period
    assert controller.sample_period == period
    assert len(controller.results) == steps // m + 1
    _assert_sample_times(controller, period, steps // m + 1)
    assert len(runtime._servovalves) == 2
    for servovalve in runtime._servovalves:
        commands = np.asarray(servovalve.main_model.u, dtype=float).reshape(-1)
        assert commands.shape == (steps + 1,)
        held = commands[(np.arange(steps + 1) // m) * m]
        np.testing.assert_array_equal(commands, held)
        # The command really changes between periods (not trivially zero).
        assert len(np.unique(commands)) > 1


def test_ros2_controller_samples_every_m_steps() -> None:
    period, m, steps = 4 * H, 4, 10
    simulation = ALB.build_simulation(
        simulation_config(pid_config(period), steps=steps, integrator="ros2")
    )
    result = simulation.run()
    runtime = active_runtime(simulation)
    controller = runtime._controller

    assert result.time.shape == (steps + 1,)
    assert np.all(np.isfinite(result.rotor_displacement))
    assert controller.dt == period
    assert len(controller.results) == steps // m + 1
    _assert_sample_times(controller, period, steps // m + 1)
    diagnostics = simulation._coupling._ros2.diagnostics()
    assert diagnostics["control_steps_per_period"] == (m,)
    assert diagnostics["actuator_states"] > 0


def test_adjusted_run_uses_effective_grid_and_warns_only_at_configuration() -> None:
    with recorded_warnings() as caught:
        # T = 4 h = 8e-5 s -> 2 periods of 4 steps at h' = 1.75e-5 s.
        config = simulation_config(pid_config(NON_INTEGER_PERIOD), steps=4)
    assert len(adjustment_warnings(caught)) == 1

    with recorded_warnings() as caught:
        simulation = ALB.build_simulation(config)
        result = simulation.run()
    assert adjustment_warnings(caught) == []

    assert config.steps == 8
    np.testing.assert_allclose(
        result.time,
        np.arange(9) * ADJUSTED_STEP,
        rtol=1.0e-12,
        atol=0.0,
    )
    assert result.metadata["requested_steps"] == 9
    assert result.metadata["time_step"] == ADJUSTED_STEP
    assert result.metadata["time_step_adjustment"] == config.time_step_adjustment
    assert result.metadata["control_periods"] == config.control_periods
    assert result.metadata["integrator"] == "staggered"
    controller = active_runtime(simulation)._controller
    assert controller.dt == NON_INTEGER_PERIOD
    assert len(controller.results) == 3
    _assert_sample_times(controller, NON_INTEGER_PERIOD, 3)


# ---------------------------------------------------------------------------
# Controller laws
# ---------------------------------------------------------------------------


def _pid(control_period: float | None) -> PID:
    return PID(
        PIDConfig(
            dt=H,
            control_period=control_period,
            kp=1.0,
            ki=0.5,
            kd=0.01,
            freq=50.0,
            sensor_angles=np.asarray([45.0, 135.0]),
        )
    )


def test_pid_law_integrates_and_differentiates_over_control_period() -> None:
    period = 4 * H
    pid = _pid(period)
    assert pid.config.sample_period == period
    assert pid.dt == period
    assert pid.sample_period == period

    pid._reset_for_owner()
    pid.input(0.0, [0.2, -0.1])
    pid.evaluate()
    pid.input(period, [0.3, 0.1])
    pid.evaluate()
    first, second = pid.results.iloc[0], pid.results.iloc[1]
    error_1 = np.asarray(first["error"], dtype=float)
    error_2 = np.asarray(second["error"], dtype=float)

    assert np.all(error_1 != 0.0) and np.all(error_2 != error_1)
    np.testing.assert_allclose(
        first["ki_calc"], pid.ki_nodim * error_1 * period, rtol=1.0e-14
    )
    np.testing.assert_allclose(second["delta_error"], error_2 - error_1)
    np.testing.assert_allclose(
        second["kd_calc"],
        pid.kd_nodim * (error_2 - error_1) / period,
        rtol=1.0e-12,
    )
    np.testing.assert_allclose(
        second["ki_calc"],
        pid.ki_nodim * (error_1 + error_2) * period,
        rtol=1.0e-12,
    )


def _pid_outputs(pid: PID, errors: np.ndarray) -> np.ndarray:
    pid._reset_for_owner()
    outputs = []
    for index, error in enumerate(errors):
        pid.input(index * pid.dt, error)
        pid.evaluate()
        outputs.append(np.asarray(pid.output(), dtype=float))
    return np.vstack(outputs)


ERRORS = np.asarray(
    [[0.0, 0.0], [0.1, -0.05], [0.25, 0.1], [-0.2, 0.3], [0.05, -0.4]]
)


def test_unset_control_period_reproduces_the_step_based_pid() -> None:
    unset = _pid(None)
    assert unset.config.control_period is None
    assert unset.config.sample_period == H
    assert unset.dt == H

    np.testing.assert_array_equal(
        _pid_outputs(_pid(H), ERRORS),
        _pid_outputs(unset, ERRORS),
    )
    assert not np.array_equal(
        _pid_outputs(_pid(4 * H), ERRORS),
        _pid_outputs(unset, ERRORS),
    )


def _fuzzy(control_period: float | None) -> FuzzyPID:
    return FuzzyPID(
        FuzzyPIDConfig(
            dt=H,
            control_period=control_period,
            freq=5.0,
            rule_path=str(FUZZY_RULE_ROOT / "fuzzy_rules.csv"),
            sensor_angles=[45.0, 135.0],
        )
    )


def test_fuzzy_pid_uses_control_period_as_internal_step() -> None:
    period = 4 * H
    sampled = _fuzzy(period)
    unset = _fuzzy(None)

    assert sampled.dt == period
    assert sampled.config.control_period == period
    assert unset.dt == H
    assert unset.config.control_period is None
    np.testing.assert_array_equal(
        _pid_outputs(_fuzzy(H), ERRORS),
        _pid_outputs(unset, ERRORS),
    )
    assert not np.array_equal(
        _pid_outputs(sampled, ERRORS),
        _pid_outputs(unset, ERRORS),
    )


@pytest.mark.parametrize("value", [0.0, -1.0e-4, math.nan, math.inf, True])
@pytest.mark.parametrize("config_type", [PIDConfig, FuzzyPIDConfig])
def test_controller_configs_reject_invalid_control_period(
    config_type: type,
    value: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="control_period"):
        config_type(dt=H, control_period=value)


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["uncontrolled", "external_spool"])
def test_control_period_requires_pid_or_fuzzy_pid_mode(mode: str) -> None:
    spec = pid_spec(None)
    spec["control"] = {"mode": mode, "control_period": 4 * H}

    with pytest.raises(ALB.ConfigurationError, match="control_period"):
        ALB.BearingConfig(spec)


@pytest.mark.parametrize(
    "value",
    [0.0, -4.0e-5, math.nan, math.inf, -math.inf, True, "8e-5"],
)
def test_control_period_must_be_finite_and_positive(value: object) -> None:
    with pytest.raises(ALB.ConfigurationError, match="control_period"):
        ALB.BearingConfig(pid_spec(value))  # type: ignore[arg-type]


def test_standalone_bearing_requires_integer_period_ratio() -> None:
    with pytest.raises(ALB.ConfigurationError, match="control_period"):
        ALB.build_bearing(pid_config(NON_INTEGER_PERIOD))


def test_standalone_bearing_samples_controller_every_m_calculations() -> None:
    bearing = ALB.build_bearing(pid_config(4 * H))
    runtime = bearing._runtime

    assert runtime.control_steps_per_period == 4
    for index in range(9):
        bearing.calculate(
            displacement=(1.0e-7 * index, -2.0e-7 * index),
            time=index * H,
        )
    # Evaluations 0, 4, and 8 sample the controller.
    assert len(runtime._controller.results) == 3
    _assert_sample_times(runtime._controller, 4 * H, 3)


def test_unset_control_period_keeps_one_controller_step_per_evaluation() -> None:
    bearing = ALB.build_bearing(pid_config(None))
    assert bearing._runtime.control_steps_per_period == 1
    assert bearing._runtime._controller.dt == H


def test_requested_mount_step_mismatch_is_reported_before_adjustment() -> None:
    rotor = ross_rotor()
    # The bearing already uses the step an adjustment would choose.
    mismatched = pid_config(NON_INTEGER_PERIOD, ADJUSTED_STEP)

    with recorded_warnings() as caught:
        with pytest.raises(
            ALB.ConfigurationError,
            match=r"mounts\[0\]\.config\.time_step must equal",
        ):
            simulation_config(mismatched, steps=20, rotor=rotor)

    assert adjustment_warnings(caught) == []
    assert rotor.dt == H


def _two_pad_config(*control_periods: float) -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": [inherited_pid_child(period) for period in control_periods],
        }
    )


def test_several_control_periods_are_allowed_when_the_step_divides_all() -> None:
    with recorded_warnings() as caught:
        config = simulation_config(_two_pad_config(4 * H, 6 * H), steps=12)

    assert adjustment_warnings(caught) == []
    assert config.time_step == H
    assert config.steps == 12
    assert [
        (item["path"], item["control_steps_per_period"])
        for item in config.control_periods
    ] == [
        ("mounts[0].config.pads[0].control.control_period", 4),
        ("mounts[0].config.pads[1].control.control_period", 6),
    ]


def test_several_mounts_record_their_own_control_periods() -> None:
    config = ALB.SimulationConfig(
        rotor=ProtocolRotor(H),
        mounts=(
            ALB.BearingMount(pid_config(4 * H), 0),
            ALB.BearingMount(liquid_config(), 1),
            ALB.BearingMount(pid_config(2 * H), 2),
        ),
        time_step=H,
        steps=4,
    )

    assert [
        (item["mount"], item["control_steps_per_period"])
        for item in config.control_periods
    ] == [(0, 4), (2, 2)]


@pytest.mark.parametrize(
    "control_periods",
    [
        (NON_INTEGER_PERIOD, 9.0e-5),
        # One period divides h, the other needs an adjustment.
        (4 * H, NON_INTEGER_PERIOD),
    ],
)
def test_several_control_periods_needing_adjustment_are_rejected(
    control_periods: tuple[float, float],
) -> None:
    rotor = ross_rotor()
    with recorded_warnings() as caught:
        with pytest.raises(
            ALB.ConfigurationError,
            match="several different control periods",
        ):
            simulation_config(
                _two_pad_config(*control_periods),
                steps=20,
                rotor=rotor,
            )

    assert adjustment_warnings(caught) == []
    assert rotor.dt == H


def test_equal_non_integer_periods_share_one_adjustment() -> None:
    with recorded_warnings() as caught:
        config = simulation_config(
            _two_pad_config(NON_INTEGER_PERIOD, NON_INTEGER_PERIOD),
            steps=20,
        )

    assert len(adjustment_warnings(caught)) == 1
    assert config.time_step == ADJUSTED_STEP
    assert [
        item["control_steps_per_period"] for item in config.control_periods
    ] == [4, 4]


# ---------------------------------------------------------------------------
# Multi-pad children and rotor ownership
# ---------------------------------------------------------------------------


def test_inline_multi_pad_children_are_retimed() -> None:
    declared = pid_spec(NON_INTEGER_PERIOD)
    nested = {
        "family": "multi_pad",
        "pads": [liquid_config().to_dict()["spec"]],
    }
    parent = ALB.BearingConfig(
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": [declared, inherited_pid_child(NON_INTEGER_PERIOD), nested],
        }
    )
    with recorded_warnings() as caught:
        config = simulation_config(parent, steps=20)

    assert len(adjustment_warnings(caught)) == 1
    spec = config.mounts[0].config.spec
    pads = spec["pads"]
    assert spec["time_step"] == ADJUSTED_STEP
    # Declared steps are rewritten; inherited steps keep inheriting.
    assert pads[0]["time_step"] == ADJUSTED_STEP
    assert "time_step" not in pads[1]
    assert "time_step" not in pads[2]
    assert pads[2]["pads"][0]["time_step"] == ADJUSTED_STEP
    assert [pad["control"]["control_period"] for pad in pads[:2]] == [
        NON_INTEGER_PERIOD,
        NON_INTEGER_PERIOD,
    ]
    # The retimed tree is internally consistent and materializes.
    runtime = ALB.build_bearing(config.mounts[0].config)._runtime
    assert [
        child.control_steps_per_period for child in runtime._children[:2]
    ] == [4, 4]


def test_retimed_configuration_keeps_source_resources() -> None:
    with recorded_warnings():
        config = simulation_config(fuzzy_config(NON_INTEGER_PERIOD), steps=4)

    retimed = config.mounts[0].config
    assert retimed.resource_root == FUZZY_RULE_ROOT
    assert retimed.spec["time_step"] == ADJUSTED_STEP
    # The relative fuzzy rule file still resolves after retiming.
    runtime = ALB.build_bearing(retimed)._runtime
    assert runtime.control_steps_per_period == 4
    assert runtime._controller.dt == NON_INTEGER_PERIOD


def _write_document(path: Path, spec: dict[str, object]) -> None:
    path.write_text(
        json.dumps({"schema_version": "0.4.0", "kind": "bearing", "spec": spec}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("period_in_file_child", [True, False])
def test_file_referenced_multi_pad_child_cannot_be_retimed(
    tmp_path: Path,
    period_in_file_child: bool,
) -> None:
    if period_in_file_child:
        file_child = pid_spec(NON_INTEGER_PERIOD)
        pads: list[object] = ["child.json5"]
    else:
        file_child = liquid_config().to_dict()["spec"]
        pads = ["child.json5", inherited_pid_child(NON_INTEGER_PERIOD)]
    _write_document(tmp_path / "child.json5", file_child)
    _write_document(
        tmp_path / "parent.json5",
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": pads,
        },
    )
    parent = ALB.load_bearing_config(tmp_path / "parent.json5")
    rotor = ross_rotor()

    with recorded_warnings() as caught:
        with pytest.raises(
            ALB.ConfigurationError,
            match=r"mounts\[0\]\.config\.pads\[0\] is a file-referenced pad",
        ):
            simulation_config(parent, steps=20, rotor=rotor)

    assert adjustment_warnings(caught) == []
    assert rotor.dt == H


def test_file_referenced_child_with_dividing_period_is_accepted(
    tmp_path: Path,
) -> None:
    _write_document(tmp_path / "child.json5", pid_spec(4 * H))
    _write_document(
        tmp_path / "parent.json5",
        {
            "family": "multi_pad",
            "unit_system": "dimensional",
            "time_step": H,
            "node": 0,
            "pads": ["child.json5"],
        },
    )
    with recorded_warnings() as caught:
        config = simulation_config(
            ALB.load_bearing_config(tmp_path / "parent.json5"),
            steps=8,
        )

    assert adjustment_warnings(caught) == []
    assert [
        (item["path"], item["control_steps_per_period"])
        for item in config.control_periods
    ] == [("mounts[0].config.pads[0].control.control_period", 4)]


def test_rotor_without_retime_hook_rejects_required_adjustment() -> None:
    rotor = ProtocolRotor(H)
    with recorded_warnings() as caught:
        with pytest.raises(ALB.ConfigurationError, match="_retime_for_owner"):
            ALB.SimulationConfig(
                rotor=rotor,
                mounts=(ALB.BearingMount(pid_config(NON_INTEGER_PERIOD), 0),),
                time_step=H,
                steps=20,
            )

    assert adjustment_warnings(caught) == []
    assert rotor.dt == H
    # A dividing period needs no hook.
    config = ALB.SimulationConfig(
        rotor=rotor,
        mounts=(ALB.BearingMount(pid_config(4 * H), 0),),
        time_step=H,
        steps=20,
    )
    assert config.time_step_adjustment is None


class _FailingRetimeRotor(ProtocolRotor):
    def _retime_for_owner(self, dt: float) -> None:
        raise ValueError(f"cannot use dt={dt!r}")


class _IgnoringRetimeRotor(ProtocolRotor):
    def _retime_for_owner(self, dt: float) -> None:
        del dt


@pytest.mark.parametrize(
    ("rotor_type", "message"),
    [
        (_FailingRetimeRotor, "could not be retimed"),
        (_IgnoringRetimeRotor, r"rotor\.dt must equal the adjusted"),
    ],
)
def test_failed_rotor_retime_is_a_configuration_error_after_the_warning(
    rotor_type: type,
    message: str,
) -> None:
    """The adjustment is announced before the rotor is retimed.

    Warning first lets a caller escalate ``TimeStepAdjustedWarning`` to an
    error and reject the configuration before the rotor is mutated; a rotor
    that then fails to retime still yields ``ConfigurationError``.
    """

    with recorded_warnings() as caught:
        with pytest.raises(ALB.ConfigurationError, match=message):
            ALB.SimulationConfig(
                rotor=rotor_type(H),
                mounts=(ALB.BearingMount(pid_config(NON_INTEGER_PERIOD), 0),),
                time_step=H,
                steps=20,
            )

    assert len(adjustment_warnings(caught)) == 1


@pytest.mark.parametrize(
    ("bearing_factory", "kwargs", "error"),
    [
        (
            lambda: pid_config(NON_INTEGER_PERIOD),
            {"initial_rotor_state": np.zeros(3)},
            ALB.ConfigurationError,
        ),
        (
            lambda: pid_config(NON_INTEGER_PERIOD),
            {"dependencies": object()},
            TypeError,
        ),
        (
            # ROS2 rejects the thermal sibling after the step was planned.
            lambda: ALB.BearingConfig(
                {
                    "family": "multi_pad",
                    "unit_system": "dimensional",
                    "time_step": H,
                    "node": 0,
                    "pads": [
                        inherited_pid_child(NON_INTEGER_PERIOD),
                        liquid_config(
                            thermal={"transient_enabled": False}
                        ).to_dict()["spec"],
                    ],
                }
            ),
            {"integrator": "ros2"},
            ALB.ConfigurationError,
        ),
    ],
)
def test_rejected_configuration_never_retimes_the_rotor(
    bearing_factory,
    kwargs: dict[str, object],
    error: type[Exception],
) -> None:
    rotor = ross_rotor()
    with recorded_warnings() as caught:
        with pytest.raises(error):
            simulation_config(bearing_factory(), steps=20, rotor=rotor, **kwargs)

    assert adjustment_warnings(caught) == []
    assert rotor.dt == H


def test_warning_escalated_to_error_leaves_the_rotor_untouched() -> None:
    """The warning is emitted before the in-place retime of the rotor."""

    rotor = ross_rotor()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ALB.TimeStepAdjustedWarning)
        with pytest.raises(ALB.TimeStepAdjustedWarning):
            simulation_config(
                pid_config(NON_INTEGER_PERIOD),
                steps=20,
                rotor=rotor,
            )

    assert rotor.dt == H


# ---------------------------------------------------------------------------
# Default path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bearing_factory",
    [liquid_config, lambda: pid_config(None)],
    ids=["liquid_film", "active_pid_without_period"],
)
def test_default_path_metadata_has_no_new_keys(bearing_factory) -> None:
    with recorded_warnings() as caught:
        config = simulation_config(bearing_factory(), steps=3)
        result = ALB.build_simulation(config).run()

    assert adjustment_warnings(caught) == []
    assert config.control_periods == ()
    assert config.time_step_adjustment is None
    assert config.integrator == "staggered"
    assert NEW_METADATA_KEYS.isdisjoint(result.metadata)


def test_control_period_equal_to_step_reproduces_the_unset_path() -> None:
    results = {}
    for name, period in (("unset", None), ("one_step", H)):
        simulation = ALB.build_simulation(
            simulation_config(pid_config(period), steps=6)
        )
        results[name] = (simulation.run(), active_runtime(simulation))

    unset, unset_runtime = results["unset"]
    one_step, one_step_runtime = results["one_step"]
    for field in ("time", "rotor_displacement", "rotor_velocity", "bearing_force"):
        np.testing.assert_array_equal(getattr(one_step, field), getattr(unset, field))
    assert len(one_step_runtime._controller.results) == 7
    assert len(unset_runtime._controller.results) == 7
    # A configured period marks the run as non-default in the metadata.
    assert NEW_METADATA_KEYS.isdisjoint(unset.metadata)
    assert NEW_METADATA_KEYS <= set(one_step.metadata)
    assert one_step.metadata["control_periods"][0]["control_steps_per_period"] == 1


# ---------------------------------------------------------------------------
# Persistence and shared rotors
# ---------------------------------------------------------------------------


def test_control_period_result_metadata_round_trips_through_write(
    tmp_path: Path,
) -> None:
    """Nested frozen control-period metadata must be JSON serializable."""

    with recorded_warnings():
        config = simulation_config(
            pid_config(NON_INTEGER_PERIOD),
            steps=8,
            rotor=ross_rotor(),
        )
    result = ALB.build_simulation(config).run()

    result.write(tmp_path / "result")

    written = json.dumps(
        [dict(item) for item in result.metadata["control_periods"]]
    )
    assert "control_steps_per_period" in written
    assert any((tmp_path / "result").rglob("*.json"))


def test_shared_rotor_retimed_by_another_config_fails_at_build() -> None:
    rotor = ross_rotor()
    first = simulation_config(liquid_config(), steps=2, rotor=rotor)
    with recorded_warnings():
        simulation_config(pid_config(NON_INTEGER_PERIOD), steps=2, rotor=rotor)

    with pytest.raises(ALB.ConfigurationError, match="shared rotor"):
        ALB.build_simulation(first)
