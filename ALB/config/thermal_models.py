"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass, fields
from typing import Optional

import numpy as np

from ALB.core.numerics.damping import (
    AdaptiveDampConfig,
    normalize_adaptive_damp_config,
)
from .common_models import ConfigData

_THERMAL_ITER_METHODS = {"direct", "newton", "direct_then_newton"}

_THERMAL_MIU_UPDATE_METHODS = {"linear", "log"}

def _normalize_thermal_iter_method(value: str) -> str:
    """Return the canonical thermal nonlinear iteration method name."""
    method = str(value).lower()
    if method not in _THERMAL_ITER_METHODS:
        raise ValueError(
            "iter_method must be one of: 'direct', 'newton', 'direct_then_newton'"
        )
    return method

def _normalize_thermal_miu_update(value: str) -> str:
    """Return the canonical thermal viscosity update method name."""
    method = str(value).lower()
    if method not in _THERMAL_MIU_UPDATE_METHODS:
        raise ValueError("miu_update must be one of: 'linear', 'log'")
    return method

@dataclass
class ThermalConfig(ConfigData):
    """Configuration for thermo-hydrodynamic viscosity coupling.

    Stored on :class:`FPBConfig.thermal_config`; ``None`` disables the thermal
    coupling.  Both dimensional (``args_nodim=False``) and nondimensional
    (``args_nodim=True``) inputs are supported.
    """

    t_in: float = 40.0
    t_ref: Optional[float] = None
    miu0: Optional[float] = None
    beta: float = 0.03
    k_lub: float = 0.0
    """Three-dimensional lubricant conductivity in W/(m*K)."""
    cp_lub: float = 2000.0
    """Heat-capacity constant used under the incompressible cp approximately cv model."""
    flow_rate_factor: float = 1.0
    """Deprecated no-op retained for JSON compatibility; only 1.0 is valid."""
    max_delta_t: float = 80.0
    heat_partition: float = 0.9
    relax: float = 0.5
    tol: float = 1e-6
    max_iter: int = 60
    adaptive_damp: Optional[AdaptiveDampConfig] = None
    miu_min: float = 1e-4
    miu_max: float = 1.0
    coupling: str = "full"
    """Lowercase ``full`` uses nodal viscosity; ``half`` uses mean viscosity."""
    t_supply: Optional[float] = None
    """Orifice supply oil temperature; defaults to ``t_in``."""
    axial_side_bc: str = "inflow_fixed"
    """Axial-side BC: ``fixed`` (both fixed-T) | ``adiabatic`` | ``inflow_fixed``."""
    axial_side_t: Optional[float] = None
    """Axial-side fixed temperature; defaults to ``t_supply``."""
    supg: bool = True
    """Enable SUPG stabilization for advection-dominated regime."""
    pressure_backend: str = "skfem"
    """Retained for backward compatibility; only ``skfem`` is supported."""
    args_nodim: bool = False
    """Treat numeric inputs as already nondimensional when True."""
    delta_t_scale: Optional[float] = None
    """Fixed characteristic temperature rise."""
    beta_nondim: Optional[float] = None
    """Optional nondimensional beta input."""
    t_ref_nondim: Optional[float] = None
    """Optional nondimensional reference temperature input."""
    transient_enabled: bool = False
    """Enable rho*cp*h*dT/dt; currently supported only by direct iteration."""
    dt: Optional[float] = None
    """Transient time step, seconds."""
    iter_method: str = "direct"
    """Thermal nonlinear iteration method: direct, newton, or direct_then_newton."""
    thermal_newton_max_iter: int = 30
    """Maximum Newton iterations for one segregated thermal subsolve."""
    thermal_newton_tol: Optional[float] = None
    """Newton residual tolerance; defaults to ``tol`` when omitted."""
    thermal_newton_damp: float = 1.0
    """Initial damping factor for thermal Newton updates."""
    thermal_newton_min_damp: float = 1e-3
    """Smallest damping factor allowed by the Newton line search."""
    thermal_newton_line_search: bool = False
    """Enable residual-decreasing line search for thermal Newton updates."""
    miu_update: str = "linear"
    """Outer thermal viscosity update method: linear or log."""
    miu_update_max_ratio: Optional[float] = None
    """Optional per-step viscosity multiplier cap used by log updates."""
    heat_partition_steps: Optional[tuple] = None
    """Optional heat-partition continuation schedule ending at heat_partition."""

    def __post_init__(self):
        self.adaptive_damp = normalize_adaptive_damp_config(self.adaptive_damp)
        self.iter_method = _normalize_thermal_iter_method(self.iter_method)
        self.miu_update = _normalize_thermal_miu_update(self.miu_update)
        self.coupling = str(self.coupling).lower()
        if self.coupling not in {"full", "half"}:
            raise ValueError("coupling must be one of: 'full', 'half'")
        self.flow_rate_factor = float(self.flow_rate_factor)
        if not np.isclose(self.flow_rate_factor, 1.0, rtol=0.0, atol=0.0):
            raise ValueError(
                "flow_rate_factor is deprecated and has no effect; only 1.0 is allowed"
            )
        self.k_lub = float(self.k_lub)
        if not np.isfinite(self.k_lub) or self.k_lub < 0.0:
            raise ValueError("k_lub must be finite and >= 0")
        self.cp_lub = float(self.cp_lub)
        if not np.isfinite(self.cp_lub) or self.cp_lub <= 0.0:
            raise ValueError("cp_lub must be finite and > 0")
        if self.miu0 is not None:
            self.miu0 = float(self.miu0)
            if not np.isfinite(self.miu0) or self.miu0 <= 0.0:
                raise ValueError("miu0 must be finite and > 0 when provided")
        if self.transient_enabled and self.iter_method != "direct":
            raise ValueError(
                "Transient thermal solves currently require iter_method='direct'"
            )
        if self.thermal_newton_max_iter <= 0:
            raise ValueError("thermal_newton_max_iter must be > 0")
        if self.thermal_newton_tol is not None and self.thermal_newton_tol <= 0:
            raise ValueError("thermal_newton_tol must be > 0 when provided")
        if self.thermal_newton_damp <= 0:
            raise ValueError("thermal_newton_damp must be > 0")
        if self.thermal_newton_min_damp <= 0:
            raise ValueError("thermal_newton_min_damp must be > 0")
        if self.thermal_newton_min_damp > self.thermal_newton_damp:
            raise ValueError(
                "thermal_newton_min_damp must be <= thermal_newton_damp"
            )
        if self.miu_update_max_ratio is not None and self.miu_update_max_ratio <= 1.0:
            raise ValueError("miu_update_max_ratio must be > 1 when provided")
        if self.heat_partition_steps is not None:
            steps = tuple(float(value) for value in self.heat_partition_steps)
            if not steps:
                raise ValueError("heat_partition_steps must not be empty")
            if any(value <= 0.0 for value in steps):
                raise ValueError("heat_partition_steps values must be > 0")
            target = float(self.heat_partition)
            if not np.isclose(steps[-1], target):
                steps = steps + (target,)
            if any(value > target for value in steps):
                raise ValueError("heat_partition_steps values must be <= heat_partition")
            self.heat_partition_steps = steps
        if self.beta_nondim is None and self.t_ref_nondim is None:
            return
        if self.delta_t_scale is None or float(self.delta_t_scale) <= 0.0:
            raise ValueError("beta_nondim or t_ref_nondim requires delta_t_scale > 0")
        delta_t = float(self.delta_t_scale)
        t_supply = float(self.t_supply if self.t_supply is not None else self.t_in)
        if self.beta_nondim is not None:
            self.beta = float(self.beta_nondim) / delta_t
        if self.t_ref_nondim is not None:
            self.t_ref = t_supply + float(self.t_ref_nondim) * delta_t

    @classmethod
    def from_dict(cls, config_dict: Optional[dict]):
        if config_dict is None:
            return cls()
        config_dict = dict(config_dict)
        # Legacy alias: thermal_solver -> nodim flag
        if "thermal_solver" in config_dict and "nodim" not in config_dict:
            solver_name = str(config_dict["thermal_solver"]).lower()
            if solver_name == "dimensional":
                config_dict["nodim"] = False
            elif solver_name == "nondimensional":
                config_dict["nodim"] = True
            else:
                raise ValueError(
                    "thermal_solver must be one of: 'dimensional', 'nondimensional'"
                )
        if "args_nodim" not in config_dict and "nodim" in config_dict:
            config_dict["args_nodim"] = bool(config_dict["nodim"])
        # Legacy: delta_t_mode/delta_t_char described the explicit temperature
        # scale; new code should pass delta_t_scale.
        legacy_delta_t_mode = config_dict.get("delta_t_mode")
        if "delta_t_scale" not in config_dict and "delta_t_char" in config_dict:
            if legacy_delta_t_mode is None or str(legacy_delta_t_mode).lower() in {
                "fixed",
                "explicit",
                "manual",
            }:
                config_dict["delta_t_scale"] = config_dict["delta_t_char"]
        valid_fields = {item.name for item in fields(cls)}
        allowed_legacy_fields = {
            "thermal_solver",
            "nodim",
            "delta_t_mode",
            "delta_t_char",
        }
        unknown_fields = sorted(
            set(config_dict).difference(valid_fields, allowed_legacy_fields)
        )
        if unknown_fields:
            raise ValueError(
                "Unknown ThermalConfig field(s): " + ", ".join(unknown_fields)
            )
        args = {key: config_dict[key] for key in valid_fields if key in config_dict}
        return cls(**args)

def build_thermal_config(
    thermal_enabled: bool,
    thermal_data: Optional[dict] = None,
    *,
    dt: Optional[float] = None,
    transient_default: bool = False,
) -> Optional[ThermalConfig]:
    """Build a :class:`ThermalConfig` from a flat dict, or return ``None``.

    :param thermal_enabled: ``False`` short-circuits to ``None``.
    :param thermal_data: Optional dict whose keys match :class:`ThermalConfig` fields.
    :param dt: Optional time step for transient solves; fills in when missing.
    :param transient_default: Default for ``transient_enabled`` when not provided.
    """
    if not thermal_enabled:
        return None

    thermal_args = dict(thermal_data or {})
    if thermal_args.get("transient_enabled") is None:
        thermal_args["transient_enabled"] = transient_default
    if thermal_args.get("dt") is None and dt is not None:
        thermal_args["dt"] = dt
    return ThermalConfig.from_dict(thermal_args)

__all__ = ['ThermalConfig', 'build_thermal_config']
