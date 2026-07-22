"""Validated coefficient contract and loaders for harmonic ALB runtimes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Mapping, TypeAlias, cast, overload

import numpy as np
import numpy.typing as npt

from ALB.contracts.numeric import FloatArray
from ALB.core.validation import finite_real_array


BUILTIN_COEFFICIENT_RESOURCE = "data/alb_harmonic_linear_gamma1_50hz.json"
ComplexArray: TypeAlias = npt.NDArray[np.complex128]


def finite_vector(name: str, value: Any) -> FloatArray:
    """Return a copied finite two-component float vector."""

    return finite_real_array(value, name, shape=(2,))


@overload
def _finite_matrix(
    name: str, value: Any, *, complex_values: Literal[False]
) -> FloatArray: ...


@overload
def _finite_matrix(
    name: str, value: Any, *, complex_values: Literal[True]
) -> ComplexArray: ...


def _finite_matrix(
    name: str, value: Any, *, complex_values: bool
) -> FloatArray | ComplexArray:
    """Return a copied finite 2 x 2 coefficient matrix."""

    if not complex_values:
        return finite_real_array(value, name, shape=(2, 2))
    matrix: ComplexArray = np.asarray(value, dtype=np.complex128)
    if matrix.shape != (2, 2):
        raise ValueError(f"{name} must have shape (2, 2)")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} must contain only finite values")
    return matrix.copy()


def positive_float(name: str, value: Any) -> float:
    """Return a finite positive scalar."""

    scalar = float(value)
    if not np.isfinite(scalar) or scalar <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return scalar


def _complex_matrix_from_payload(
    name: str, payload: Mapping[str, Any]
) -> ComplexArray:
    """Decode a complex matrix stored as separate real and imaginary arrays."""

    if not isinstance(payload, Mapping) or "real" not in payload or "imag" not in payload:
        raise ValueError(f"{name} must contain real and imag arrays")
    real = finite_real_array(payload["real"], f"{name}.real", shape=(2, 2))
    imag = finite_real_array(payload["imag"], f"{name}.imag", shape=(2, 2))
    return _finite_matrix(name, real + 1j * imag, complex_values=True)


@dataclass(frozen=True)
class ALBHarmonicCoefficients:
    r"""Dimensional local ALB coefficients at one strict harmonic base state.

    ``spool_transfer`` is the complex matrix
    :math:`G_{x_v}(\Omega_w)` in newtons per normalized spool displacement.
    The matrices are equation-derived inputs; this class only validates and
    stores them.
    """

    name: str
    static_force: FloatArray
    stiffness: FloatArray
    damping: FloatArray
    spool_transfer: ComplexArray
    equilibrium_position: FloatArray
    base_spool: FloatArray
    clearance_m: float
    shaft_frequency_hz: float
    whirl_ratio: float
    source: str = ""

    def __post_init__(self) -> None:
        """Normalize arrays and reject incomplete coefficient contracts."""

        if not str(self.name).strip():
            raise ValueError("name must be non-empty")
        object.__setattr__(
            self, "static_force", finite_vector("static_force", self.static_force)
        )
        object.__setattr__(
            self,
            "stiffness",
            _finite_matrix("stiffness", self.stiffness, complex_values=False),
        )
        object.__setattr__(
            self,
            "damping",
            _finite_matrix("damping", self.damping, complex_values=False),
        )
        object.__setattr__(
            self,
            "spool_transfer",
            _finite_matrix(
                "spool_transfer", self.spool_transfer, complex_values=True
            ),
        )
        object.__setattr__(
            self,
            "equilibrium_position",
            finite_vector("equilibrium_position", self.equilibrium_position),
        )
        object.__setattr__(
            self, "base_spool", finite_vector("base_spool", self.base_spool)
        )
        object.__setattr__(
            self, "clearance_m", positive_float("clearance_m", self.clearance_m)
        )
        object.__setattr__(
            self,
            "shaft_frequency_hz",
            positive_float("shaft_frequency_hz", self.shaft_frequency_hz),
        )
        whirl_ratio = float(self.whirl_ratio)
        if not np.isfinite(whirl_ratio) or whirl_ratio <= 0.0:
            raise ValueError("whirl_ratio must be finite and > 0")
        object.__setattr__(self, "whirl_ratio", whirl_ratio)
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "source", str(self.source))

    @property
    def whirl_frequency_hz(self) -> float:
        """Return the coefficient whirl frequency in hertz."""

        return self.whirl_ratio * self.shaft_frequency_hz

    @property
    def whirl_omega_rad_s(self) -> float:
        """Return the coefficient whirl angular frequency in radians per second."""

        return 2.0 * np.pi * self.whirl_frequency_hz

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ALBHarmonicCoefficients":
        """Load the stable ``alb.harmonic-linear.v1`` data contract."""

        if payload.get("schema") != "alb.harmonic-linear.v1":
            raise ValueError("Unsupported harmonic-linear coefficient schema")
        linearization = payload.get("linearization")
        if not isinstance(linearization, Mapping):
            raise ValueError("linearization must be an object")
        spool_transfer = _complex_matrix_from_payload(
            "G_xv_N_per_nondim",
            linearization["G_xv_N_per_nondim"],
        )
        return cls(
            name=str(payload["name"]),
            static_force=linearization["static_force_N"],
            stiffness=linearization["K_N_per_m"],
            damping=linearization["C_N_s_per_m"],
            spool_transfer=spool_transfer,
            equilibrium_position=linearization["equilibrium_position_m"],
            base_spool=linearization["base_spool_nondim"],
            clearance_m=linearization["clearance_m"],
            shaft_frequency_hz=linearization["shaft_frequency_hz"],
            whirl_ratio=linearization["whirl_ratio"],
            source=str(payload.get("coefficient_source", "")),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "ALBHarmonicCoefficients":
        """Load coefficients from a UTF-8 JSON file."""

        payload = cast(
            dict[str, Any], json.loads(Path(path).read_text(encoding="utf-8"))
        )
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible coefficient representation."""

        return {
            "name": self.name,
            "source": self.source,
            "static_force_N": self.static_force.tolist(),
            "K_N_per_m": self.stiffness.tolist(),
            "C_N_s_per_m": self.damping.tolist(),
            "G_xv_N_per_nondim": {
                "real": self.spool_transfer.real.tolist(),
                "imag": self.spool_transfer.imag.tolist(),
            },
            "equilibrium_position_m": self.equilibrium_position.tolist(),
            "base_spool_nondim": self.base_spool.tolist(),
            "clearance_m": self.clearance_m,
            "shaft_frequency_hz": self.shaft_frequency_hz,
            "whirl_ratio": self.whirl_ratio,
            "whirl_frequency_hz": self.whirl_frequency_hz,
        }


def load_builtin_payload() -> dict[str, Any]:
    """Load the packaged documented coefficient and runtime contract."""

    resource = resources.files("ALB.systems.alb").joinpath(
        BUILTIN_COEFFICIENT_RESOURCE
    )
    with resource.open("r", encoding="utf-8") as stream:
        return cast(dict[str, Any], json.load(stream))


def load_builtin_alb_harmonic_coefficients() -> ALBHarmonicCoefficients:
    """Return the packaged equation-derived 50 Hz, gamma=1 coefficient set."""

    return ALBHarmonicCoefficients.from_dict(load_builtin_payload())


__all__ = [
    "ALBHarmonicCoefficients",
    "BUILTIN_COEFFICIENT_RESOURCE",
    "finite_vector",
    "load_builtin_alb_harmonic_coefficients",
    "load_builtin_payload",
    "positive_float",
]
