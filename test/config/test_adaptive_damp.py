import math

from ALB.config import HydConfig, NodimPadConfig, ThermalConfig
from ALB.damping import AdaptiveDampConfig, AdaptiveDampController


def test_disabled_controller_keeps_initial_value():
    controller = AdaptiveDampController(0.5, AdaptiveDampConfig(enabled=False))

    controller.update(1.0)
    controller.update(2.0)
    controller.update(math.inf)

    assert controller.value == 0.5
    assert controller.history == []


def test_controller_shrinks_on_worse_or_nonfinite_error():
    config = AdaptiveDampConfig(enabled=True, min_value=0.1, shrink_factor=0.5)
    controller = AdaptiveDampController(0.8, config)

    controller.update(1.0)
    assert controller.value == 0.8

    controller.update(1.2)
    assert controller.value == 0.4

    controller.update(math.inf)
    assert controller.value == 0.2

    controller.update(math.nan)
    assert controller.value == 0.1


def test_controller_grows_after_repeated_improvement_and_clamps_to_max():
    config = AdaptiveDampConfig(
        enabled=True,
        min_value=0.05,
        max_value=0.3,
        growth_factor=2.0,
        improve_ratio=0.9,
        improve_patience=2,
    )
    controller = AdaptiveDampController(0.2, config)

    controller.update(1.0)
    controller.update(0.8)
    assert controller.value == 0.2

    controller.update(0.6)
    assert controller.value == 0.3


def test_controller_does_not_raise_value_above_small_initial_damp():
    config = AdaptiveDampConfig(enabled=True, min_value=0.02, shrink_factor=0.5)
    controller = AdaptiveDampController(0.01, config)

    controller.update(1.0)
    controller.update(1.2)

    assert controller.value == 0.01


def test_adaptive_damp_config_parses_from_model_configs():
    hyd = HydConfig.from_dict({"adaptive_damp": {"enabled": True}})
    thermal = ThermalConfig.from_dict({"adaptive_damp": {"enabled": True}})
    nodim = NodimPadConfig.from_dict({"adaptive_damp": {"enabled": True}})

    assert hyd.adaptive_damp.enabled
    assert thermal.adaptive_damp.enabled
    assert nodim.adaptive_damp.enabled


def test_adaptive_damp_config_accepts_dataclass_instances():
    config = AdaptiveDampConfig(enabled=True, min_value=0.03)

    hyd = HydConfig(adaptive_damp=config)
    thermal = ThermalConfig(adaptive_damp=config)
    nodim = NodimPadConfig(adaptive_damp=config)

    assert hyd.adaptive_damp.min_value == 0.03
    assert thermal.adaptive_damp.min_value == 0.03
    assert nodim.adaptive_damp.min_value == 0.03
