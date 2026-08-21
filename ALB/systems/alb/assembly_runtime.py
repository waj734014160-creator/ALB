"""Internal typed assembly for dimensional and nondimensional active bearings."""

from __future__ import annotations

import copy

from ALB.config import (
    ALBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    SecondOrderServoConfig,
    StaticServoConfig,
    TransferFunctionServoConfig,
)
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.valve import (
    second_order_servovalve,
    static_sv,
    transfer_function_servovalve,
)
from ALB.physics.bearing.solver import _build_liquid_film_runtime
from ALB.physics.hydraulics.orifice import NodimCSOrifice
from ALB.physics.thermal.solver import (
    NodimThermalHydroBearing,
)

from ._dimensional_assembly import _DimensionalActiveAssembler
from .runtime import ALB, ALBSV, NodimALB, NodimALBSV
from .thermal_config import resolve_alb_thermal_config


_NODIM_PAD_MAIN_KEYS = {
    "lambda_value",
    "lr",
    "lx",
    "lz",
    "nx",
    "nz",
    "bias",
}


def _controller_from_config(config: NodimALBConfig):
    source = copy.deepcopy(config.controller_config)
    if source is None:
        return None
    source.dt = config.dt
    if isinstance(source, FuzzyPIDConfig):
        return FuzzyPID(source)
    return PID(source)


def _servovalves(config: NodimALBConfig):
    source = copy.deepcopy(config.servo_config)
    source.dt = config.dt
    if isinstance(source, SecondOrderServoConfig):
        return [
            second_order_servovalve(
                source.dt,
                source.natural_frequency_hz,
                source.damping_ratio,
                source.delay,
            )
            for _ in range(2)
        ]
    if isinstance(source, TransferFunctionServoConfig):
        return [
            transfer_function_servovalve(
                source.dt,
                source.numerator,
                source.denominator,
            )
            for _ in range(2)
        ]
    if isinstance(source, StaticServoConfig):
        return [static_sv(source.dt) for _ in range(2)]
    raise TypeError("unknown active-bearing servovalve configuration")


def _assemble_nondimensional(config: NodimALBConfig):
    pad = config.pad_config
    directions = ("up", "down", "right", "left")
    pads = {
        direction: _build_liquid_film_runtime(
            copy.deepcopy(pad),
            x0=float(x0),
        )
        for direction, x0 in zip(directions, pad.x0s)
    }
    orifice = config.orifice_config
    supply_x = NodimCSOrifice(
        position=orifice.position,
        cq0=orifice.cq0,
        cq1=orifice.cq1,
        cq2=orifice.cq2,
        ps=orifice.ps,
        p0=orifice.p0,
        q_leak=orifice.q_leak,
        flow_projection=orifice.flow_projection,
    )
    return_x = NodimCSOrifice(
        position=orifice.position,
        cq0=orifice.cq0,
        cq1=orifice.cq1,
        cq2=orifice.cq2,
        ps=orifice.p0,
        p0=orifice.ps,
        q_leak=orifice.q_leak,
        flow_projection=orifice.flow_projection,
    )
    orifices = {
        "soa_x": supply_x,
        "sob_x": return_x,
        "soa_y": copy.deepcopy(supply_x),
        "sob_y": copy.deepcopy(return_x),
    }
    servos = _servovalves(config)
    _DimensionalActiveAssembler._default_wiring(pads, servos, orifices)
    tank = config.tank_config
    for child in pads.values():
        child.set_thickness(
            method="add_tank",
            xrange=tank.xrange,
            zrange=tank.zrange,
            h_tank=tank.h_tank,
        )
    children = list(pads.values())
    thermal = resolve_alb_thermal_config(
        config,
        config.pad_config.thermal_config,
        args_nodim=True,
    )
    if thermal is not None:
        children = [
            NodimThermalHydroBearing(child, thermal)
            for child in children
        ]
    controller = _controller_from_config(config)
    if config.control_mode == "external_spool":
        return NodimALBSV(
            children,
            servos,
            controller=controller,
            alb_config=config,
        )
    return NodimALB(
        children,
        servos,
        controller=controller,
        alb_config=config,
    )


def assemble_active_runtime(config: ALBConfig | NodimALBConfig):
    """Assemble one already-ready active-bearing runtime."""

    if isinstance(config, ALBConfig):
        return _DimensionalActiveAssembler(copy.deepcopy(config)).build()
    if isinstance(config, NodimALBConfig):
        return _assemble_nondimensional(copy.deepcopy(config))
    raise TypeError("config must be ALBConfig or NodimALBConfig")


__all__ = ["assemble_active_runtime"]
