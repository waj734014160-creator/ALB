"""Regression checks for the simple-rotor ALB LQG diagnostic case."""

import numpy as np

from tools.manual.control.LQG.simple_rotor_lqg_vibration import run_simple_rotor_case


def test_standard_lqg_reduces_noisy_resonant_vibration():
    """The current LQG runtime must materially attenuate the matched case."""
    result = run_simple_rotor_case()
    metrics = result.metrics

    assert all(np.isfinite(value) for value in metrics.values())
    assert metrics["rms_attenuation_fraction"] > 0.90
    assert (
        metrics["closed_loop_radial_peak_m"]
        < metrics["open_loop_radial_peak_m"]
    )
    assert metrics["maximum_absolute_control"] < result.config.control_limit
