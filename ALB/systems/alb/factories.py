# coding: utf-8
import copy
from typing import TYPE_CHECKING, Iterable, Union

import numpy as np
import pandas as pd
from scipy import sparse as sp
from scipy.sparse import linalg as sl

from ALB.core.component import BaseCSystem, BaseSimpleModel
from ALB.core.events import Signal
from ALB.physics.bearing import four_pads_bearings, nodim_four_pads_bearings
from ALB.config import (
    ALBConfig,
    CsoArgs,
    FPBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    OrificeConfig,
    PIDConfig,
    ServoConfig,
    TankConfig,
    ThermalConfig,
    build_thermal_config,
)
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.adapters import adapt_controller
from ALB.control.blocks import run_controller_step, run_valve_step
from ALB.physics.hydraulics import CSOrifice, NodimCSOrifice
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.control.valve import moog_2nd_servovalve, moog_servovalve, static_sv
from ALB.physics.thermal import (
    NodimThermalHydroBearing,
    wrap_pad_collection_with_thermal,
)

if TYPE_CHECKING:
    from ALB.surrogate.inference import ALBNet

_NODIM_ALB_FORBIDDEN_PAD_KWARGS = {"miu", "c", "r", "l", "ps", "rho", "w", "w_rad"}
_NODIM_ALB_LEGACY_REQUIRED_KEYS = [
    "lambda_value",
    "lr",
    "lx",
    "lz",
    "position",
    "cq0",
    "cq1",
    "cq2",
]
_NODIM_ALB_PAD_MAIN_KEYS = {"lambda_value", "lr", "lx", "lz", "nx", "nz", "bias"}

from .builder import ALBBuilder
from .linear import ALBLinear, ALBLinearAgent, FakeOf
from .runtime import ALB, ALBSV, NodimALB, NodimALBSV
from .surrogate_runtime import ALBNNAgent

_NODIM_ALB_FORBIDDEN_PAD_KWARGS = {"miu", "c", "r", "l", "ps", "rho", "w", "w_rad"}
_NODIM_ALB_LEGACY_REQUIRED_KEYS = [
    "lambda_value", "lr", "lx", "lz", "position", "cq0", "cq1", "cq2",
]
_NODIM_ALB_PAD_MAIN_KEYS = {"lambda_value", "lr", "lx", "lz", "nx", "nz", "bias"}

def alb2(alb_config: ALBConfig) -> ALB:
    """
    Standard factory for ALB system (PID + Moog/Static based on config).
    """
    return ALBBuilder(alb_config).build()

def alb2_fuzzy(alb_config: ALBConfig) -> ALB:
    """
    Factory for ALB system with Fuzzy PID.
    """
    # Ensure the config is set to use Fuzzy Logic context if not already
    # This might be redundant if alb_config.controller_config is already FuzzyPIDConfig
    # but serves as a safeguard.
    if not isinstance(alb_config.controller_config, FuzzyPIDConfig):
        # If the user called alb2_fuzzy but passed a PIDConfig, we might need to handle it.
        # For now, we assume the config matches the intent.
        pass

    return ALBBuilder(alb_config).build()

def alb2_static(alb_config: ALBConfig) -> ALB:
    """
    Factory for ALB system with Static Servovalves.
    """
    # Force the servo type to static
    alb_config_copy = copy.deepcopy(alb_config)
    alb_config_copy.servo = "static"
    return ALBBuilder(alb_config_copy).build()

def _nodim_alb_config_from_legacy(args, kwargs, alb_config):
    """Build a NodimALBConfig from the pre-refactor flat nodim_alb arguments."""
    config = copy.deepcopy(alb_config) if alb_config is not None else NodimALBConfig()
    positional = dict(zip(_NODIM_ALB_LEGACY_REQUIRED_KEYS, args))
    if len(args) > len(_NODIM_ALB_LEGACY_REQUIRED_KEYS):
        raise TypeError("too many positional arguments for nodim_alb")

    for key in _NODIM_ALB_LEGACY_REQUIRED_KEYS[len(args) :]:
        if key not in kwargs:
            raise TypeError("nodim_alb legacy arguments are incomplete")
        positional[key] = kwargs.pop(key)

    dimensional_keys = _NODIM_ALB_FORBIDDEN_PAD_KWARGS.intersection(kwargs)
    if dimensional_keys:
        keys = ", ".join(sorted(dimensional_keys))
        raise ValueError(
            f"nodim_alb does not accept dimensional pad parameters: {keys}"
        )

    # Split the flat legacy signature into the nested pad/orifice config pieces.
    pad_args = {
        "lambda_value": positional["lambda_value"],
        "lr": positional["lr"],
        "lx": positional["lx"],
        "lz": positional["lz"],
        "nx": kwargs.pop("nx", config.pad_config.nx),
        "nz": kwargs.pop("nz", config.pad_config.nz),
        "bias": kwargs.pop("bias", config.pad_config.bias),
    }
    orifice_args = {
        "position": positional["position"],
        "cq0": positional["cq0"],
        "cq1": positional["cq1"],
        "cq2": positional["cq2"],
        "ps": kwargs.pop("orifice_ps", config.orifice_config.ps),
        "p0": kwargs.pop("orifice_p0", config.orifice_config.p0),
        "q_leak": kwargs.pop("q_leak", config.orifice_config.q_leak),
    }

    # Allow the remaining flat kwargs to override pad-level nondimensional options.
    pad_update_keys = set(config.pad_config.to_dict()) - {"x0s"}
    for key in list(kwargs):
        if key in pad_update_keys:
            pad_args[key] = kwargs.pop(key)
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected nodim_alb arguments: {unknown}")

    current_pad_args = config.pad_config.to_dict()
    current_pad_args.pop("x0s", None)
    config.pad_config = type(config.pad_config)(**{**current_pad_args, **pad_args})
    # Orifice config has no computed fields, so its dict can be reused directly.
    config.orifice_config = type(config.orifice_config)(
        **{**config.orifice_config.to_dict(), **orifice_args}
    )
    return config

def _coerce_nodim_alb_config(args, kwargs, alb_config):
    """Normalize all supported nodim_alb call styles to a NodimALBConfig."""
    if alb_config is not None and not isinstance(alb_config, NodimALBConfig):
        if (
            getattr(alb_config, "c", None) is not None
            or getattr(alb_config, "w", None) is not None
        ):
            raise ValueError(
                "nodim_alb does not accept dimensional ALBConfig.c/w scales"
            )
        raise TypeError("nodim_alb only accepts NodimALBConfig")

    if args and isinstance(args[0], NodimALBConfig):
        if alb_config is not None:
            raise TypeError("nodim_alb received NodimALBConfig twice")
        if len(args) > 1:
            raise TypeError("nodim_alb accepts only NodimALBConfig in config mode")
        if kwargs:
            unknown = ", ".join(sorted(kwargs))
            raise TypeError(f"unexpected nodim_alb arguments: {unknown}")
        return copy.deepcopy(args[0])

    if args or any(key in kwargs for key in _NODIM_ALB_LEGACY_REQUIRED_KEYS):
        return _nodim_alb_config_from_legacy(args, kwargs, alb_config)

    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected nodim_alb arguments: {unknown}")
    return copy.deepcopy(alb_config) if alb_config is not None else NodimALBConfig()

def _nodim_controller_from_config(alb_config, controller):
    """Create the controller instance used by the nondimensional ALB entry."""
    if controller is not None:
        return controller
    controller_config = copy.deepcopy(alb_config.controller_config)
    if controller_config is None:
        return None
    # Keep the controller time step aligned with the top-level ALB time step.
    if hasattr(controller_config, "dt"):
        controller_config.dt = alb_config.dt
    if isinstance(controller_config, FuzzyPIDConfig):
        return FuzzyPID(controller_config)
    return PID(controller_config)

def _nodim_thermal_config(alb_config, thermal_config):
    """Resolve the thermal config and force the nondimensional argument mode."""
    if thermal_config is None:
        thermal_config = getattr(alb_config, "thermal_config", None)
    if thermal_config is None:
        return None
    thermal_args = vars(thermal_config).copy()
    if thermal_args.get("dt") is None:
        thermal_args["dt"] = alb_config.dt
    if not thermal_args.get("transient_enabled"):
        thermal_args["transient_enabled"] = alb_config.servo != "static"
    # The nodim entry always drives the thermal wrapper with nondimensional states.
    thermal_args["args_nodim"] = True
    return ThermalConfig.from_dict(thermal_args)

def nodim_alb(
    *args,
    alb_config: NodimALBConfig = None,
    servo_config: ServoConfig = None,
    controller=None,
    thermal_config: ThermalConfig = None,
    **kwargs,
) -> ALB:
    """Assemble an ALB model from a NodimALBConfig."""
    alb_config = _coerce_nodim_alb_config(args, kwargs, alb_config)
    if (
        getattr(alb_config, "c", None) is not None
        or getattr(alb_config, "w", None) is not None
    ):
        raise ValueError("nodim_alb does not accept dimensional ALBConfig.c/w scales")

    if servo_config is None:
        servo_config = copy.deepcopy(alb_config.servo_config)
    servo_config.dt = alb_config.dt
    controller = _nodim_controller_from_config(alb_config, controller)

    pad_config = alb_config.pad_config
    pad_args = pad_config.to_dict()
    # nodim_four_pads_bearings takes the geometric core arguments explicitly and
    # the remaining nondimensional film options as keyword arguments.
    pad_kwargs = {
        key: value
        for key, value in pad_args.items()
        if key not in _NODIM_ALB_PAD_MAIN_KEYS and key != "x0s" and value is not None
    }
    scale_arg_map = {
        "scale_miu": "miu",
        "scale_c": "c",
        "scale_r": "r",
        "scale_l": "l",
        "scale_ps": "ps",
        "scale_rho": "rho",
        "scale_w": "w",
    }
    for scale_key, film_key in scale_arg_map.items():
        value = pad_kwargs.pop(scale_key, None)
        if value is not None:
            pad_kwargs[film_key] = value

    pads_dict = nodim_four_pads_bearings(
        lambda_value=pad_config.lambda_value,
        lr=pad_config.lr,
        lx=pad_config.lx,
        lz=pad_config.lz,
        nx=pad_config.nx,
        nz=pad_config.nz,
        bias=pad_config.bias,
        **pad_kwargs,
    )

    if alb_config.servo == "moog":
        servos = [
            moog_servovalve(
                servo_config.dt,
                servo_config.delay,
                servo_config.tw,
                servo_config.zeta,
                servo_config.tp3,
            )
            for _ in range(2)
        ]
    elif alb_config.servo == "moog_2nd":
        servos = [
            moog_2nd_servovalve(
                servo_config.dt,
                servo_config.delay,
                servo_config.tw,
                servo_config.zeta,
            )
            for _ in range(2)
        ]
    elif alb_config.servo == "static":
        servos = [static_sv(servo_config.dt) for _ in range(2)]
    else:
        raise ValueError("servo must be 'moog', 'moog_2nd', or 'static'")

    orifice_config = alb_config.orifice_config
    # X and Y branches share the same nondimensional slot model, while the
    # return-side branch is created by swapping supply and ambient pressures.
    soa_x = NodimCSOrifice(
        position=orifice_config.position,
        cq0=orifice_config.cq0,
        cq1=orifice_config.cq1,
        cq2=orifice_config.cq2,
        ps=orifice_config.ps,
        p0=orifice_config.p0,
        q_leak=orifice_config.q_leak,
    )
    sob_x = NodimCSOrifice(
        position=orifice_config.position,
        cq0=orifice_config.cq0,
        cq1=orifice_config.cq1,
        cq2=orifice_config.cq2,
        ps=orifice_config.p0,
        p0=orifice_config.ps,
        q_leak=orifice_config.q_leak,
    )
    orifices = {
        "soa_x": soa_x,
        "sob_x": sob_x,
        "soa_y": copy.deepcopy(soa_x),
        "sob_y": copy.deepcopy(sob_x),
    }

    # Reuse the standard hydraulic wiring so the nodim entry stays behaviorally
    # aligned with the dimensional ALB builder.
    ALBBuilder._default_wiring(pads_dict, servos, orifices)

    tank_config = getattr(alb_config, "tank_config", None)
    if tank_config is not None:
        for pad in pads_dict.values():
            pad.set_thickness(
                method="add_tank",
                xrange=tank_config.xrange,
                zrange=tank_config.zrange,
                h_tank=tank_config.h_tank,
            )

    pads = list(pads_dict.values())
    thermal_config = _nodim_thermal_config(alb_config, thermal_config)
    if thermal_config is not None:
        pads = [NodimThermalHydroBearing(pad, thermal_config) for pad in pads]

    alb_type = alb_config.alb
    if alb_type == "ALBSV":
        return NodimALBSV(pads, servos, controller=controller, alb_config=alb_config)
    if alb_type in {"ALB", None}:
        return NodimALB(pads, servos, controller=controller, alb_config=alb_config)
    raise ValueError(f"Unknown ALB type: {alb_type}")

def alb_no_controller(alb_config: ALBConfig) -> ALB:
    """
    Factory for ALB system without a controller.
    """
    builder = ALBBuilder(alb_config)
    # Explicitly remove controller config to prevent controller creation
    builder.set_controller_config(None)
    return builder.build()

def linear_alb(alb, uxy) -> ALB:
    """
    Create a linear model of an ALB system.
    This uses Moog servovalves and CSOrifices.
    :param alb: The original ALB object.
    :param uxy: The linearization position of the bearing.
    :return: A new ALB object representing the linearized system.
    """
    # establish the alb2 model and replace its pads and orifice model
    bearing = alb
    cb = copy.deepcopy(bearing)
    al = ALBLinear(bearing)
    lan = al.linearize(uxy)
    ala = ALBLinearAgent(**lan)
    # the ala model has the fake orifice model to get the xv from servo valve
    cb.servovalves[0].simple_models = [ala.of[0]]
    cb.servovalves[1].simple_models = [ala.of[1]]
    cb.pads = [ala]
    cb.signal.children = [pad.signal for pad in cb.pads]
    cb.init()
    return cb

def nn_agent(alb, albnet_config) -> ALB:
    """
    Create an ALB agent using a neural network.
    :param alb: The original ALB object.
    :param albnet_config: Configuration for the ALB neural network.
    :return: A new ALB object with the NN agent.
    """
    from ALB.surrogate.inference import alb_agent_nn

    alb = copy.deepcopy(alb)
    nn = alb_agent_nn(albnet_config)
    ala = ALBNNAgent(
        nn,
        agent=albnet_config.agent,
        unit_system=alb.unit_system,
        node_link=alb.node_link,
    )
    alb.servovalves[0].simple_models = [ala.of[0]]
    alb.servovalves[1].simple_models = [ala.of[1]]
    alb.pads = [ala]
    alb.signal.children = [pad.signal for pad in alb.pads]
    alb.init()
    return alb

__all__ = ['alb2', 'alb2_fuzzy', 'alb2_static', 'nodim_alb', 'alb_no_controller', 'linear_alb', 'nn_agent']
