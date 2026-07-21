"""Tests for configurable ALB LQG actuator-command limits."""

from types import SimpleNamespace

import numpy as np
import pytest

from ALB.config import LQGConfig
from ALB.control.lqg import ALBLQGController


def _attach_runtime_system(controller, raw_output):
    """Attach a minimal one-state runtime controller with a known output."""
    raw_output = np.asarray(raw_output, dtype=float).reshape(-1, 1)
    controller.active_ctrl_sys_d = SimpleNamespace(
        A=np.zeros((1, 1)),
        B=np.zeros((1, 1)),
        C=raw_output,
        D=np.zeros((raw_output.shape[0], 1)),
    )
    controller._init_runtime_state()
    controller.x_hat[:] = 1.0
    controller.t_prev = 0.0


def test_lqg_default_output_limits_are_minus_one_to_one():
    """Default LQG commands must be clipped and raw values must remain logged."""
    controller = ALBLQGController(SimpleNamespace(), dt=1.0e-3)
    _attach_runtime_system(controller, [2.0, -3.0])

    output = controller.output()
    history = controller.get_history(to_dataframe=False)

    np.testing.assert_allclose(output, [1.0, -1.0])
    np.testing.assert_allclose(history["u_raw"][0], [2.0, -3.0])
    np.testing.assert_allclose(history["u"][0], [1.0, -1.0])


def test_lqg_config_supports_per_channel_output_limits():
    """LQGConfig must support independent bounds for each actuator channel."""
    config = LQGConfig(
        dt=2.0e-3,
        freq=60.0,
        eso_enable=False,
        output_min=[-0.2, -0.4],
        output_max=[0.3, 0.5],
    )
    controller = ALBLQGController(SimpleNamespace(), config=config)
    _attach_runtime_system(controller, [2.0, -3.0])

    np.testing.assert_allclose(controller.output(), [0.3, -0.4])
    assert controller.dt == pytest.approx(2.0e-3)
    assert controller.freq == pytest.approx(60.0)
    assert controller.eso_enable is False


def test_empty_lqg_history_returns_a_typed_dataframe():
    controller = ALBLQGController(SimpleNamespace(), dt=1.0e-3)
    _attach_runtime_system(controller, [2.0, -3.0])

    history = controller.get_history(to_dataframe=True)

    assert history.empty
    assert list(history.columns) == [
        "t",
        "y_0",
        "u_raw_0",
        "u_raw_1",
        "u_0",
        "u_1",
        "x_hat_0",
    ]


@pytest.mark.parametrize(
    ("output_min", "output_max"),
    [
        (1.0, 1.0),
        ([0.0, -1.0], [-0.1, 1.0]),
        ([-1.0, -2.0], [1.0, 2.0, 3.0]),
    ],
)
def test_lqg_config_rejects_invalid_output_limits(output_min, output_max):
    """Invalid or incompatible LQG command bounds must fail at configuration."""
    with pytest.raises(ValueError):
        LQGConfig(output_min=output_min, output_max=output_max)
