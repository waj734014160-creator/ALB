# coding: utf-8
import copy
from typing import Iterable, Union

import numpy as np
import pandas as pd
from scipy import sparse as sp
from scipy.sparse import linalg as sl

from ALB.core.component import BaseCSystem, BaseSimpleModel
from ALB.physics.bearing.solver import (
    four_pads_bearings,
    nodim_four_pads_bearings,
)
from ALB.config import (
    ALBConfig,
    CsoArgs,
    FPBConfig,
    FuzzyPIDConfig,
    NodimALBConfig,
    OrificeConfig,
    PIDConfig,
    SecondOrderServoConfig,
    StaticServoConfig,
    TankConfig,
    TransferFunctionServoConfig,
)
from ALB.control.fuzzy import FuzzyPID
from ALB.control.pid import PID
from ALB.control.blocks import run_controller_step, run_valve_step
from ALB.physics.hydraulics.orifice import CSOrifice, NodimCSOrifice
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode
from ALB.control.valve import (
    second_order_servovalve,
    static_sv,
    transfer_function_servovalve,
)
from ALB.physics.thermal.solver import (
    NodimThermalHydroBearing,
    wrap_pad_collection_with_thermal,
)

_NODIM_ALB_FORBIDDEN_PAD_KWARGS = {"miu", "c", "r", "l", "ps", "rho", "w", "w_rad"}
_NODIM_ALB_PAD_MAIN_KEYS = {"lambda_value", "lr", "lx", "lz", "nx", "nz", "bias"}

from .runtime import ALB, ALBSV
from .thermal_config import resolve_alb_thermal_config

class _DimensionalActiveAssembler:
    """
    Builder class for constructing an ALB (Active Lubricated Bearing) system.
    Refactored from ALBCreator to provide a robust, type-safe, and fluent interface.
    """

    def __init__(self, alb_config: ALBConfig = None):
        """
        Initialize the builder. If alb_config is provided, it populates the sub-configs automatically.
        """
        self.alb_config = alb_config

        # Sub-configurations (can be overridden manually)
        self.pad_config: Union[FPBConfig, None] = (
            alb_config.pad_config if alb_config else None
        )
        self.servo_config: Union[
            SecondOrderServoConfig,
            StaticServoConfig,
            TransferFunctionServoConfig,
            None,
        ] = (
            alb_config.servo_config if alb_config else None
        )
        self.orifice_config: Union[OrificeConfig, None] = (
            alb_config.orifice_config if alb_config else None
        )
        self.tank_config: Union[TankConfig, None] = (
            alb_config.tank_config if alb_config else None
        )
        self.controller_config: Union[PIDConfig, FuzzyPIDConfig, None] = (
            alb_config.controller_config if alb_config else None
        )

        # Internal components storage
        self._pads = []
        self._servovalves = []
        self._static_svs = []
        self._controller = None
        self._orifices = {}  # stores soa_x, sob_x, etc.

        self.wiring_strategy = None

    # -------------------------- Configuration Steps --------------------------

    def set_pads_config(self, config: FPBConfig):
        self.pad_config = config
        return self

    def set_servo_config(
        self,
        config: Union[
            SecondOrderServoConfig,
            StaticServoConfig,
            TransferFunctionServoConfig,
        ],
    ):
        self.servo_config = config
        return self

    def set_orifice_config(self, config: OrificeConfig):
        self.orifice_config = config
        return self

    def set_tank_config(self, config: TankConfig):
        self.tank_config = config
        return self

    def set_controller_config(self, config: Union[PIDConfig, FuzzyPIDConfig]):
        self.controller_config = config
        return self

    def set_wiring_strategy(self, strategy_func):
        """
        Set a custom wiring strategy for pads, servos, and orifices.
        Expected signature: (pads, servos, orifices) -> None.
        """
        self.wiring_strategy = strategy_func
        return self

    def _create_pads(self):
        if not self.pad_config:
            raise ValueError("Pad configuration is missing.")
        return four_pads_bearings(self.pad_config)

    def _create_servos(self):
        if not self.servo_config:
            raise ValueError("Servo configuration is missing.")

        # Create Dynamic Servos (for control)
        if isinstance(self.servo_config, SecondOrderServoConfig):
            sv_x = second_order_servovalve(
                self.servo_config.dt,
                self.servo_config.natural_frequency_hz,
                self.servo_config.damping_ratio,
                self.servo_config.delay,
            )
            sv_y = second_order_servovalve(
                self.servo_config.dt,
                self.servo_config.natural_frequency_hz,
                self.servo_config.damping_ratio,
                self.servo_config.delay,
            )
        elif isinstance(self.servo_config, TransferFunctionServoConfig):
            sv_x = transfer_function_servovalve(
                self.servo_config.dt,
                self.servo_config.numerator,
                self.servo_config.denominator,
            )
            sv_y = transfer_function_servovalve(
                self.servo_config.dt,
                self.servo_config.numerator,
                self.servo_config.denominator,
            )
        elif isinstance(self.servo_config, StaticServoConfig):
            sv_x = static_sv(self.servo_config.dt)
            sv_y = static_sv(self.servo_config.dt)
        else:
            raise TypeError("Unknown servovalve configuration type")

        # Create Static Servos (for static equilibrium calculation)
        # Note: ALB class expects static_sv to be available implicitly or created internally,
        # but creating them here ensures consistency.
        # Logic matches original ALBCreator._static_servo
        ssv_x = static_sv(self.servo_config.dt)
        ssv_y = static_sv(self.servo_config.dt)

        return [sv_x, sv_y], [ssv_x, ssv_y]

    def _create_orifices(self):
        if not self.orifice_config:
            raise ValueError("Orifice configuration is missing.")

        ps = self.orifice_config.ps
        p0 = self.orifice_config.p0
        position = self.orifice_config.position
        csorifice_args = CsoArgs(
            d=self.orifice_config.diameter,
            l=self.orifice_config.length,
            w=self.orifice_config.valve_area,
            cd=self.orifice_config.discharge_coefficient,
            cq1_nondim=self.orifice_config.cq1_nondim,
        )

        soa_x = CSOrifice(
            ps=ps,
            p0=p0,
            cso_args=csorifice_args,
            position=position,
            flow_projection=self.orifice_config.flow_projection,
        )
        sob_x = CSOrifice(
            ps=p0,
            p0=ps,
            cso_args=csorifice_args,
            position=position,
            flow_projection=self.orifice_config.flow_projection,
        )
        soa_y = copy.deepcopy(soa_x)
        sob_y = copy.deepcopy(sob_x)

        return {"soa_x": soa_x, "sob_x": sob_x, "soa_y": soa_y, "sob_y": sob_y}

    def _create_controller(self):
        if not self.controller_config:
            # Return None or a dummy controller if allowed
            return None

        if isinstance(self.controller_config, FuzzyPIDConfig):
            # Original code copied args before creation, keeping that behavior
            fargs = copy.copy(self.controller_config)
            return FuzzyPID(fargs)
        elif isinstance(self.controller_config, PIDConfig):
            return PID(self.controller_config)
        else:
            raise TypeError(
                f"Unknown controller config type: {type(self.controller_config)}"
            )

    def _create_thermal_config(self):
        """Resolve the pad-level thermal config and apply ALB-level defaults."""
        thermal_config = getattr(self.pad_config, "thermal_config", None)
        return resolve_alb_thermal_config(
            self.alb_config,
            thermal_config,
            args_nodim=False,
        )

    # -------------------------- Wiring / Assembly --------------------------

    def _apply_tank_settings(self, bearings: dict):
        if self.tank_config:
            for bearing in bearings.values():
                bearing.set_thickness(
                    method="add_tank",
                    xrange=self.tank_config.xrange,
                    zrange=self.tank_config.zrange,
                    h_tank=self.tank_config.h_tank,
                )
        return bearings

    def _couple_components(self, pads, servos, orifices):
        if hasattr(self, "wiring_strategy") and self.wiring_strategy:
            self.wiring_strategy(pads, servos, orifices)
        else:
            self._default_wiring(pads, servos, orifices)

    @staticmethod
    def _default_wiring(pads_dict, servos, orifices):
        sv_x, sv_y = servos

        # Couple Orifice to Servo
        sv_x.add_simple_model([orifices["soa_x"], orifices["sob_x"]])
        sv_y.add_simple_model([orifices["soa_y"], orifices["sob_y"]])

        # Couple Orifice to Bearing Pads
        pads_dict["up"].add_simple_model(orifices["soa_y"])
        pads_dict["down"].add_simple_model(orifices["sob_y"])
        pads_dict["right"].add_simple_model(orifices["soa_x"])
        pads_dict["left"].add_simple_model(orifices["sob_x"])

        return pads_dict

    # -------------------------- Main Build Method --------------------------

    def build(self) -> ALB:
        """
        Constructs the ALB system based on the current configuration.
        """
        if not self.alb_config:
            raise ValueError("ALBConfig is required to build the final system.")

        # 1. Create Components
        pads_dict = self._create_pads()
        servos, static_servos = self._create_servos()
        orifices = self._create_orifices()
        controller = self._create_controller()

        # 2. Wire Components (Hydraulic connections)
        self._couple_components(pads_dict, servos, orifices)

        # 3. Apply Tank Settings (Geometry modification)
        self._apply_tank_settings(pads_dict)

        # 4. Instantiate ALB (System Assembly)
        pads_list = wrap_pad_collection_with_thermal(
            list(pads_dict.values()), self._create_thermal_config()
        )

        # Determine ALB Class type
        if self.alb_config.control_mode == "external_spool":
            alb_system = ALBSV(
                pads_list, servos, controller=controller, alb_config=self.alb_config
            )
        else:
            alb_system = ALB(
                pads_list, servos, controller=controller, alb_config=self.alb_config
            )

        # Inject the static servos created earlier (optional, but maintains consistency with original logic)
        # The ALB class creates its own static_sv internally in _create_static_sv,
        # but if we wanted to enforce the ones we built:
        # alb_system.static_sv = static_servos

        return alb_system

__all__ = ["_DimensionalActiveAssembler"]
