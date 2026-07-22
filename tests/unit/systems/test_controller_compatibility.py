"""Compatibility tests for ALB controller lifecycle integration points."""

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.config import ALBConfig, Moog2ndServoConfig
from ALB.control.controllers import ALBLQGController, RCConfig, RepetitiveController
from ALB.core import Signal
from ALB.systems.alb.assembly import ALB, ALBSV, NodimALB, NodimALBSV
from ALB.systems.alb.harmonic import ALBHarmonicCoefficients, ALBHarmonicLinear


class _LegacyController:
    """Historical controller whose output method owns calculation."""

    def __init__(self) -> None:
        self.init()

    def init(self) -> None:
        self.error = np.zeros(2, dtype=float)
        self.time = 0.0
        self.output_calls = 0

    def input(self, time, error) -> None:
        self.time = float(time)
        self.error = np.asarray(error, dtype=float).reshape(2)

    def output(self) -> np.ndarray:
        self.output_calls += 1
        return self.error + self.time


class _ReadOnlyValve:
    """Small valve that exposes the command supplied by the harmonic path."""

    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.simple_models = []
        self.command = 0.0
        self.input_calls = 0
        self.commands = []

    def init(self) -> None:
        self.command = 0.0
        self.input_calls = 0
        self.commands = []

    def input(self, time, command) -> None:
        del time
        self.command = float(command)
        self.input_calls += 1
        self.commands.append(self.command)

    def output(self) -> float:
        return self.command

    def finish_signal(self) -> None:
        return None


class _ReadOnlyPad:
    """Small deterministic pad for the public ALB lifecycle tests."""

    def __init__(self) -> None:
        self.signal = Signal(sys=self)
        self.main_model = SimpleNamespace(args={"c": 1.0, "w": 60.0, "vf": 1.0})
        self.position = np.zeros(2, dtype=float)

    def init(self) -> None:
        self.position = np.zeros(2, dtype=float)

    def input(self, *, t, uxy, uxyt, nodim=False) -> None:
        del t, uxyt, nodim
        self.position = np.asarray(uxy, dtype=float).reshape(2)

    def output(self, *, nodim=False) -> dict[str, object]:
        del nodim
        return {"force": self.position.copy(), "friction": 0.0}

    def finish_signal(self) -> None:
        return None


class _FactoryLegacyController:
    """Legacy controller without init support, intended for factory injection."""

    def input(self, time, error) -> None:
        del time
        self.error = np.asarray(error, dtype=float).reshape(2)

    def output(self) -> np.ndarray:
        return 0.25 * self.error


class _ReinitializationFailureController(_FactoryLegacyController):
    """Resettable controller that fails once at a selected reinit phase."""

    def __init__(self, failure_point: str) -> None:
        self.failure_point = failure_point
        self.init_calls = 0
        self.fail_during_output = False

    def init(self) -> None:
        self.init_calls += 1
        if self.failure_point == "controller-init" and self.init_calls == 2:
            raise RuntimeError("controller reset failed")
        self.fail_during_output = (
            self.failure_point == "warm-up" and self.init_calls == 2
        )

    def output(self) -> np.ndarray:
        if self.fail_during_output:
            self.fail_during_output = False
            raise RuntimeError("controller warm-up failed")
        return super().output()


class _RuntimeFailureController(_FactoryLegacyController):
    """Controller double that mutates once before a runtime output failure."""

    def __init__(
        self,
        output_size: int | None = None,
        output_value: float = 0.0,
    ) -> None:
        self.output_size = output_size
        self.output_value = float(output_value)
        self.output_calls = 0

    def output(self) -> np.ndarray:
        self.output_calls += 1
        if self.output_size is None:
            raise RuntimeError("controller runtime failed")
        return np.full(self.output_size, self.output_value, dtype=float)


class _FailingValve(_ReadOnlyValve):
    """Valve double that fails after latching its command."""

    def input(self, time, command) -> None:
        super().input(time, command)
        raise RuntimeError("second valve failed")


class _NonfiniteValve(_ReadOnlyValve):
    """Valve double that returns a non-finite scalar after accepting input."""

    def output(self) -> float:
        return float("inf")


def _lqg_controller() -> ALBLQGController:
    controller = ALBLQGController(SimpleNamespace(), dt=0.01, eso_enable=False)
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.asarray([[0.8]], dtype=float),
        B=np.asarray([[0.2, -0.1]], dtype=float),
        C=np.asarray([[2.0], [-3.0]], dtype=float),
        D=np.zeros((2, 2), dtype=float),
    )
    controller._init_runtime_state()
    return controller


def _repetitive_controller() -> RepetitiveController:
    return RepetitiveController(
        RCConfig(
            dt=0.01,
            freq=10.0,
            k_rc=np.asarray([0.4, -0.2]),
            q_filter=0.95,
            m_lead=1,
        )
    )


def _harmonic_lqg_controller() -> ALBLQGController:
    controller = ALBLQGController(
        SimpleNamespace(), dt=0.001, freq=50.0, eso_enable=False
    )
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.asarray([[0.8]], dtype=float),
        B=np.asarray([[0.2, -0.1]], dtype=float),
        C=np.asarray([[2.0], [-3.0]], dtype=float),
        D=np.zeros((2, 2), dtype=float),
    )
    controller._init_runtime_state()
    return controller


def _harmonic_repetitive_controller() -> RepetitiveController:
    return RepetitiveController(
        RCConfig(
            dt=0.001,
            freq=50.0,
            k_rc=np.asarray([0.4, -0.2]),
            q_filter=0.95,
            m_lead=1,
        )
    )


def _zero_base_coefficients() -> ALBHarmonicCoefficients:
    return ALBHarmonicCoefficients(
        name="controller-injection-test",
        static_force=np.asarray([10.0, -20.0]),
        stiffness=np.asarray([[2.0e5, 1.0e4], [-3.0e4, 1.5e5]]),
        damping=np.asarray([[25.0, 2.0], [-4.0, 18.0]]),
        spool_transfer=np.asarray(
            [[100.0 + 20.0j, -10.0j], [5.0j, 80.0 - 15.0j]]
        ),
        equilibrium_position=np.zeros(2),
        base_spool=np.zeros(2),
        clearance_m=1.0e-4,
        shaft_frequency_hz=50.0,
        whirl_ratio=1.0,
        source="unit-test",
    )


@pytest.mark.parametrize(
    "factory",
    [_LegacyController, _lqg_controller, _repetitive_controller],
    ids=["legacy", "lqg", "repetitive"],
)
def test_alb_control_process_accepts_strict_and_legacy_controllers(factory):
    controller = factory()
    alb = object.__new__(ALB)
    alb._gxy = np.eye(2)
    alb._gxyt = np.zeros((2, 2))
    alb.controller = controller

    command = ALB._control_process(
        alb,
        np.asarray([0.2, -0.3]),
        np.asarray([0.0, 0.0]),
        0.0,
    )

    assert np.asarray(command).shape == (2,)
    if isinstance(controller, _LegacyController):
        assert controller.output_calls == 1


@pytest.mark.parametrize(
    "factory",
    [_LegacyController, _lqg_controller, _repetitive_controller],
    ids=["legacy", "lqg", "repetitive"],
)
def test_harmonic_control_path_accepts_strict_and_legacy_controllers(factory):
    controller = factory()
    bearing = object.__new__(ALBHarmonicLinear)
    bearing.controller = controller
    bearing.coefficients = SimpleNamespace(clearance_m=2.0)
    bearing.servovalves = [_ReadOnlyValve(), _ReadOnlyValve()]

    ALBHarmonicLinear._advance_control(
        bearing,
        time_s=0.0,
        uxy=np.asarray([0.4, -0.6]),
    )

    assert bearing.spool_command.shape == (2,)
    np.testing.assert_array_equal(bearing.spool, bearing.spool_command)
    assert [valve.input_calls for valve in bearing.servovalves] == [1, 1]
    if isinstance(controller, _LegacyController):
        assert controller.output_calls == 1


@pytest.mark.parametrize("controller_kind", ["legacy", "lqg", "repetitive"])
def test_harmonic_public_lifecycle_supports_injected_controllers(controller_kind):
    controller = None
    controller_factory = None
    if controller_kind == "legacy":
        controller_factory = _FactoryLegacyController
    elif controller_kind == "lqg":
        controller = _harmonic_lqg_controller()
    else:
        controller = _harmonic_repetitive_controller()

    bearing = ALBHarmonicLinear(
        _zero_base_coefficients(),
        node_link=3,
        servo_config=Moog2ndServoConfig(dt=0.001),
        controller=controller,
        controller_factory=controller_factory,
        warmup_steps=24,
    )
    first_controller = bearing.controller

    def run_trajectory() -> np.ndarray:
        rows = []
        for step in range(24):
            phase = 2.0 * np.pi * step / 20.0
            position = 1.0e-6 * np.asarray([np.cos(phase), np.sin(phase)])
            velocity = 1.0e-3 * np.asarray([-np.sin(phase), np.cos(phase)])
            bearing.input(position, velocity, step * bearing.dt)
            output = bearing.output()
            rows.append(
                np.hstack(
                    (output["spool_command"], output["spool"], output["force"])
                )
            )
        return np.asarray(rows, dtype=float)

    first = run_trajectory()
    bearing.init()
    second_controller = bearing.controller
    second = run_trajectory()

    np.testing.assert_array_equal(second, first)
    if controller_kind == "legacy":
        assert second_controller is not first_controller
    else:
        assert second_controller is first_controller


@pytest.mark.parametrize(
    "failure_point", ["factory", "controller-init", "warm-up"]
)
def test_failed_harmonic_reinitialization_invalidates_runtime(
    failure_point, tmp_path
):
    """Failed reset must block every public state consumer until recovery."""

    controller = None
    controller_factory = None
    if failure_point == "factory":
        factory_calls = 0

        def controller_factory():
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 2:
                raise RuntimeError("controller factory failed")
            return _FactoryLegacyController()

    else:
        controller = _ReinitializationFailureController(failure_point)

    bearing = ALBHarmonicLinear(
        _zero_base_coefficients(),
        node_link=3,
        servo_config=Moog2ndServoConfig(dt=0.001),
        controller=controller,
        controller_factory=controller_factory,
        warmup_steps=24,
    )
    bearing.input(np.asarray([1.0e-6, -2.0e-6]), np.zeros(2), 0.0)
    bearing.output()
    assert len(bearing.results) == 1

    with pytest.raises(RuntimeError, match="failed"):
        bearing.init()

    assert bearing._valid is False
    assert bearing._has_input is False
    invalid_operations = (
        bearing.output,
        lambda: bearing.input(np.zeros(2), np.zeros(2), 0.0),
        lambda: bearing.results,
        lambda: bearing.save(tofile=False, path=tmp_path),
        lambda: bearing.xv,
        lambda: bearing.t,
    )
    for operation in invalid_operations:
        with pytest.raises(RuntimeError, match="runtime is invalid"):
            operation()

    assert bearing.init() is True
    bearing.input(np.zeros(2), np.zeros(2), 0.0)
    assert bearing.output()["force"].shape == (2,)


@pytest.mark.parametrize(
    "failure_point",
    [
        "controller",
        "command-shape",
        "controller-nonfinite",
        "second-valve",
        "valve-nonfinite",
    ],
)
def test_harmonic_runtime_failure_invalidates_partial_step(failure_point):
    """A partial controller/valve advance cannot be observed or retried."""

    bearing = ALBHarmonicLinear(
        _zero_base_coefficients(),
        node_link=3,
        servo_config=Moog2ndServoConfig(dt=0.001),
        controller_factory=_FactoryLegacyController,
        warmup_steps=24,
    )
    first_valve = None
    if failure_point == "controller":
        bearing.controller = _RuntimeFailureController()
    elif failure_point == "command-shape":
        bearing.controller = _RuntimeFailureController(output_size=3)
    elif failure_point == "controller-nonfinite":
        bearing.controller = _RuntimeFailureController(
            output_size=2,
            output_value=float("nan"),
        )
    else:
        first_valve = _ReadOnlyValve()
        second_valve = (
            _FailingValve()
            if failure_point == "second-valve"
            else _NonfiniteValve()
        )
        bearing.servovalves = [first_valve, second_valve]

    with pytest.raises(
        (RuntimeError, ValueError, FloatingPointError),
        match="failed|exactly|finite",
    ):
        bearing.input(np.asarray([1.0e-6, -2.0e-6]), np.zeros(2), 0.0)

    assert bearing._valid is False
    assert bearing._has_input is False
    if first_valve is not None:
        assert first_valve.input_calls == 1
    for operation in (
        lambda: bearing.input(np.zeros(2), np.zeros(2), 0.0),
        bearing.output,
        lambda: bearing.results,
    ):
        with pytest.raises(RuntimeError, match="runtime is invalid"):
            operation()

    assert bearing.init() is True
    bearing.input(np.zeros(2), np.zeros(2), 0.0)
    assert bearing.output()["force"].shape == (2,)


def test_harmonic_output_overflow_invalidates_runtime():
    """Finite inputs that overflow force evaluation cannot be committed."""

    bearing = ALBHarmonicLinear(
        _zero_base_coefficients(),
        node_link=3,
        servo_config=Moog2ndServoConfig(dt=0.001),
        controller_factory=_FactoryLegacyController,
        warmup_steps=24,
    )
    bearing.controller = _RuntimeFailureController(output_size=2)
    bearing.input(np.asarray([1.0e303, 0.0]), np.zeros(2), 0.0)

    with pytest.raises(FloatingPointError, match="overflow|finite"):
        bearing.output()

    assert bearing._valid is False
    assert bearing._has_input is False
    with pytest.raises(RuntimeError, match="runtime is invalid"):
        bearing.results

    assert bearing.init() is True
    bearing.input(np.zeros(2), np.zeros(2), 0.0)
    assert bearing.output()["force"].shape == (2,)


def test_harmonic_output_failure_invalidates_partial_result(monkeypatch):
    """A result-recording failure also invalidates the advanced runtime."""

    bearing = ALBHarmonicLinear(
        _zero_base_coefficients(),
        node_link=3,
        servo_config=Moog2ndServoConfig(dt=0.001),
        controller_factory=_FactoryLegacyController,
        warmup_steps=24,
    )
    bearing.input(np.asarray([1.0e-6, -2.0e-6]), np.zeros(2), 0.0)

    def fail_recording(name):
        del name
        raise RuntimeError("result recording failed")

    monkeypatch.setattr(bearing.signal, "lead_loop", fail_recording)
    with pytest.raises(RuntimeError, match="result recording failed"):
        bearing.output()

    assert bearing._valid is False
    assert bearing._has_input is False
    with pytest.raises(RuntimeError, match="runtime is invalid"):
        bearing.output()


def test_public_alb_subclass_defaults_are_fresh_per_instance():
    """Omitted mutable configs must not be shared between public instances."""

    for model_type in (ALBSV, NodimALB, NodimALBSV):
        first = model_type(
            [_ReadOnlyPad()], [_ReadOnlyValve(), _ReadOnlyValve()]
        )
        second = model_type(
            [_ReadOnlyPad()], [_ReadOnlyValve(), _ReadOnlyValve()]
        )
        first.gxy[0, 0] = 9.0
        first.gxyt[0, 0] = 8.0
        np.testing.assert_array_equal(second.gxy, np.eye(2))
        np.testing.assert_array_equal(second.gxyt, np.zeros((2, 2)))


def _make_alb(*, switch: bool, controller):
    valves = [_ReadOnlyValve(), _ReadOnlyValve()]
    config = ALBConfig(
        controller_config=None,
        switch=switch,
        c=1.0,
        w=60.0,
        gxy=np.eye(2),
        gxyt=np.zeros((2, 2)),
    )
    model = ALB([_ReadOnlyPad()], valves, controller=controller, alb_config=config)
    model.init()
    return model, valves


def test_switch_false_stays_disabled_for_nonnegative_times():
    controller = _LegacyController()
    model, valves = _make_alb(switch=False, controller=controller)

    for time in (0.0, 0.01, 1.0):
        model.input(np.asarray([0.4, -0.2]), np.zeros(2), time)
        model.output()

    np.testing.assert_array_equal(
        np.column_stack([valve.commands for valve in valves]), np.zeros((3, 2))
    )
    assert controller.output_calls == 0


def test_missing_controller_produces_zero_command():
    model, valves = _make_alb(switch=True, controller=None)

    model.input(np.asarray([0.4, -0.2]), np.zeros(2), 0.0)
    model.output()

    np.testing.assert_array_equal([valve.command for valve in valves], [0.0, 0.0])


def test_timed_start_is_recomputed_after_reinitialization():
    controller = _LegacyController()
    model, valves = _make_alb(switch=True, controller=controller)
    model.turn_on_at(0.01)

    model.input(np.asarray([0.4, -0.2]), np.zeros(2), 0.0)
    model.output()
    model.input(np.asarray([0.4, -0.2]), np.zeros(2), 0.01)
    model.output()
    assert np.any(np.asarray([valve.commands for valve in valves])[:, 1] != 0.0)

    model.init()
    model.input(np.asarray([0.4, -0.2]), np.zeros(2), 0.0)
    model.output()

    np.testing.assert_array_equal([valve.command for valve in valves], [0.0, 0.0])
    assert controller.output_calls == 0
