"""Shared ALB thermal-configuration materialization."""

from __future__ import annotations

import warnings

from ALB.config import (
    StaticServoConfig,
    ThermalConfig,
    TransferFunctionServoConfig,
)


def resolve_alb_thermal_config(
    alb_config,
    thermal_config: ThermalConfig | None,
    *,
    args_nodim: bool,
) -> ThermalConfig | None:
    """Return one final thermal config without overriding user mode choices.

    The servo and thermal transient switches describe different physical
    subsystems. Mismatched static/dynamic choices remain valid but emit one
    warning per build so users can verify that the mixed-fidelity model is
    intentional.
    """

    if thermal_config is None:
        return None
    if not isinstance(thermal_config, ThermalConfig):
        raise TypeError("thermal_config must be ThermalConfig or None")

    thermal_args = vars(thermal_config).copy()
    if thermal_args.get("dt") is None:
        thermal_args["dt"] = alb_config.dt
    thermal_args["args_nodim"] = args_nodim
    resolved = ThermalConfig.from_dict(thermal_args)

    static_servo = (
        isinstance(alb_config.servo_config, StaticServoConfig)
        or (
            isinstance(alb_config.servo_config, TransferFunctionServoConfig)
            and alb_config.servo_config.is_static
        )
    )
    if static_servo and resolved.transient_enabled:
        warnings.warn(
            "static servo dynamics are paired with transient thermal dynamics",
            RuntimeWarning,
            stacklevel=3,
        )
    elif not static_servo and not resolved.transient_enabled:
        warnings.warn(
            "dynamic servo dynamics are paired with steady thermal dynamics",
            RuntimeWarning,
            stacklevel=3,
        )
    return resolved


__all__ = ["resolve_alb_thermal_config"]
