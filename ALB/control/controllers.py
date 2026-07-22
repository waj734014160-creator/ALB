"""Deprecated flat controller imports; use domain modules instead."""

from .fuzzy import FuzzyPID, default_rules
from .lqg import ALBLQGController, BearingContent
from .pid import PID
from .reduction_core import (
    alpha_shift,
    alpha_unshift,
    balanced_truncation,
    balreal,
    compute_modal_info,
    modal_truncation_by_damping,
    modal_truncation_by_dominance,
    modal_truncation_by_frequency,
    modal_truncation_by_index,
    print_modal_table,
)
from .repetitive import RCConfig, RepetitiveController


def test_lqg(eso=True, dt=1e-3, freq=50, alpha=1e-3, beta=2e-3):
    """Build the historical two-bearing LQG diagnostic controller."""

    import numpy as np

    from ALB.dynamics.rotor import rotor0
    from .valve import moog_servovalve

    rotor = rotor0(dt, freq, alpha=alpha, beta=beta)
    valve1 = moog_servovalve(dt=0.001)
    valve2 = moog_servovalve(dt=0.001)
    controller = ALBLQGController(rotor, dt=dt, freq=freq, eso_enable=eso)
    controller.add_bearing(
        valve1,
        np.array([[1e6, 0], [0, 1e6]]),
        np.array([[1e3, 0], [0, 1e3]]),
        np.array([0.5, 0.5]),
        act_node=12,
        sensor_node=12,
    )
    controller.add_bearing(
        valve2,
        np.array([[1.2e6, 0], [0, 1.2e6]]),
        np.array([[1.1e3, 0], [0, 1.1e3]]),
        np.array([0.4, 0.4]),
        act_node=24,
        sensor_node=24,
    )
    controller.add_unbalance_node(18)
    return controller

__all__ = [
    "ALBLQGController",
    "BearingContent",
    "FuzzyPID",
    "PID",
    "RCConfig",
    "RepetitiveController",
    "alpha_shift",
    "alpha_unshift",
    "balanced_truncation",
    "balreal",
    "compute_modal_info",
    "default_rules",
    "modal_truncation_by_damping",
    "modal_truncation_by_dominance",
    "modal_truncation_by_frequency",
    "modal_truncation_by_index",
    "print_modal_table",
    "test_lqg",
]
