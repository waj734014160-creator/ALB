from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import ALB.rotor as rotor_module
from ALB.control.lqg import ALBLQGController


def test_rotor0_converts_frequency_hz_to_ross_speed_rad_s(monkeypatch):
    """The default rotor factory must convert ALB Hz input for ROSS."""
    element_data = np.zeros((35, 7), dtype=float)
    element_data[:, 4] = 10.0
    element_data[:, 6] = 80.0
    monkeypatch.setattr(
        rotor_module.pd,
        "read_excel",
        lambda *args, **kwargs: pd.DataFrame(element_data),
    )
    monkeypatch.setattr(
        rotor_module.rs.Material,
        "save_material",
        lambda self: None,
    )

    captured = {}

    class CapturingRossRotor:
        def __init__(self, rotor, speed, dt, discrete=False):
            captured["rotor"] = rotor
            captured["speed"] = speed
            captured["dt"] = dt
            captured["discrete"] = discrete

    monkeypatch.setattr(rotor_module, "RossRotor", CapturingRossRotor)

    result = rotor_module.rotor0(dt=1e-3, freq=50.0, rotor_path="unused.xls")

    assert isinstance(result, CapturingRossRotor)
    assert captured["speed"] == pytest.approx(2.0 * np.pi * 50.0)
    assert captured["dt"] == pytest.approx(1e-3)


def test_lqg_builds_rotor_lti_with_angular_speed_rad_s():
    """LQG rotor synthesis must convert its public Hz frequency to rad/s."""

    class CapturingRotorModel:
        def __init__(self):
            self.speed = None

        def _lti(self, speed):
            self.speed = speed
            return "rotor-lti"

    rotor_model = CapturingRotorModel()
    rotor = SimpleNamespace(_rotor=rotor_model, _speed=2.0 * np.pi * 50.0)
    controller = ALBLQGController(rotor, dt=1e-3, freq=50.0, eso_enable=False)

    assert controller._rotor_lti() == "rotor-lti"
    assert rotor_model.speed == pytest.approx(2.0 * np.pi * 50.0)


def test_lqg_rejects_rotor_speed_that_does_not_match_frequency():
    """A mismatched rotor/controller operating speed must fail explicitly."""

    class RotorModel:
        def _lti(self, speed):
            return speed

    rotor = SimpleNamespace(_rotor=RotorModel(), _speed=50.0)
    controller = ALBLQGController(rotor, dt=1e-3, freq=50.0, eso_enable=False)

    with pytest.raises(ValueError, match="RossRotor speed does not match"):
        controller._rotor_lti()
