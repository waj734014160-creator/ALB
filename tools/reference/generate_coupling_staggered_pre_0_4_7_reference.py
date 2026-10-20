"""Freeze the staggered coupling path of stateful bearing families before 0.4.7.

ALB 0.4.7 adds a predictor-corrector coupled integrator and a
checkpoint/restore contract implemented by stateful bearing runtimes (thermal
film wrappers, active bearings, multi-pad composites). The 0.4.6 references
(``coupling_default_path_0_4_6`` and ``ros2_control_period_0_4_6``) do not
cover these families on the default staggered path, so this generator freezes
them on the unmodified 0.4.6 source (``9432c06``) before any 0.4.7 change:

* a small dimensional liquid film with a transient and a steady thermal model;
* an active PID bearing whose pads carry a transient thermal model;
* a multi-pad composite with a liquid-film, an active PID, and a transient
  thermal liquid-film child;
* an external-spool active bearing (``ALBSV``) driven by a deterministic spool
  provider.

Every case runs the default staggered integrator through the public API and
captures the committed simulation arrays, the rotor state history, and the
numeric fields of the final bearing result snapshot. The regression test
rebuilds the same inputs and requires exact equality (ADR-0007, rule 5).
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Callable

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import ALB  # noqa: E402
from ALB.contracts import UnitSystem, ValveOutput  # noqa: E402
from ALB.dynamics.rotor import RossRotor  # noqa: E402
from tools.reference.generate_coupling_default_path_0_4_6_reference import (  # noqa: E402
    LOADS,
    PID_CONTROL,
    TIME_STEP,
    SinglePlant,
    active_spec,
    liquid_film_spec,
)


JSON_PATH = (
    REPOSITORY_ROOT / "refs" / "coupling_staggered_pre_0_4_7_reference_v1.json"
)
NPZ_PATH = (
    REPOSITORY_ROOT / "refs" / "coupling_staggered_pre_0_4_7_reference_v1.npz"
)
SOURCE_COMMIT = "9432c06"
SPEED = 2.0 * np.pi * 50.0
PROVIDER_GAIN = 2.0e4
PROVIDER_AMPLITUDE = 0.05
PROVIDER_FREQUENCY = 50.0


class ReferenceSpoolProvider:
    """Deterministic spool provider ``s = clip(-g x + a sin(2 pi f t))``.

    ``x`` is the rotor-domain journal displacement in m. The provider records
    every sampled time so the regression can check its call sequence.
    """

    def __init__(
        self,
        gain: float = PROVIDER_GAIN,
        amplitude: float = PROVIDER_AMPLITUDE,
        frequency: float = PROVIDER_FREQUENCY,
    ) -> None:
        self.gain = float(gain)
        self.amplitude = float(amplitude)
        self.frequency = float(frequency)
        self.samples: list[float] = []
        self._pending: Any = None
        self._output: ValveOutput | None = None

    def input(self, context: Any, bearing_input: Any) -> None:
        """Latch the global step context and the rotor-domain bearing state."""

        self._pending = (context, bearing_input)

    def evaluate(self) -> None:
        """Compute one normalized spool command for the latched state."""

        context, bearing_input = self._pending
        self.samples.append(float(context.time))
        spool = np.clip(
            -self.gain * np.asarray(bearing_input.displacement, dtype=float)
            + self.amplitude
            * np.sin(2.0 * np.pi * self.frequency * float(context.time)),
            -1.0,
            1.0,
        )
        self._output = ValveOutput(spool, context.time, UnitSystem.NONDIMENSIONAL)

    def output(self) -> ValveOutput:
        """Return the completed spool command."""

        assert self._output is not None
        return self._output


def _inline_child(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a multi-pad child that inherits step, node, and unit system."""

    child = copy.deepcopy(spec)
    for key in ("time_step", "node", "unit_system"):
        child.pop(key)
    return child


def thermal_liquid_spec(transient: bool) -> dict[str, Any]:
    """Return the small liquid film with a transient or steady thermal model."""

    spec = liquid_film_spec()
    spec["thermal"] = {"transient_enabled": bool(transient)}
    return spec


def thermal_active_spec() -> dict[str, Any]:
    """Return the small active PID bearing with transient thermal pads."""

    spec = active_spec(copy.deepcopy(PID_CONTROL))
    spec["thermal"] = {"transient_enabled": True}
    return spec


def multi_pad_spec() -> dict[str, Any]:
    """Return a multi-pad with liquid, active PID, and thermal children."""

    return {
        "family": "multi_pad",
        "unit_system": "dimensional",
        "time_step": TIME_STEP,
        "node": 0,
        "pads": [
            _inline_child(liquid_film_spec()),
            _inline_child(active_spec(copy.deepcopy(PID_CONTROL))),
            _inline_child(thermal_liquid_spec(True)),
        ],
    }


def external_spool_spec() -> dict[str, Any]:
    """Return the small active bearing driven by an external spool."""

    return active_spec({"mode": "external_spool"})


def _numeric_result_fields(bundle: Any) -> dict[str, np.ndarray]:
    """Return the finite numeric arrays of one bearing result snapshot."""

    fields: dict[str, np.ndarray] = {}
    for key in sorted(bundle.values):
        value = bundle.values[key]
        if isinstance(value, (bool, np.bool_)):
            continue
        try:
            array = np.asarray(value, dtype=float)
        except (TypeError, ValueError):
            continue
        fields[f"bearing_result.{key}"] = array
    return fields


def _simulation_case(
    spec: dict[str, Any],
    steps: int,
    *,
    provider: ReferenceSpoolProvider | None = None,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Run one staggered simulation and capture its committed arrays."""

    rotor = RossRotor(SinglePlant(), speed=SPEED, dt=TIME_STEP)
    simulation = ALB.build_simulation(
        ALB.SimulationConfig(
            rotor=rotor,
            mounts=(
                ALB.BearingMount(
                    ALB.BearingConfig(spec),
                    0,
                    spool_provider=provider,
                ),
            ),
            time_step=TIME_STEP,
            steps=steps,
            loads=LOADS,
        )
    )
    result = simulation.run()
    bearing = simulation._coupling.bindings[0].bearing
    arrays = {
        "time": np.asarray(result.time, dtype=float),
        "rotor_displacement": np.asarray(result.rotor_displacement, dtype=float),
        "rotor_velocity": np.asarray(result.rotor_velocity, dtype=float),
        "bearing_force": np.asarray(result.bearing_force, dtype=float),
        "rotor_state_history": np.asarray(rotor._xouts, dtype=float),
        "rotor_final_state": np.asarray(rotor.current_state(), dtype=float),
        **_numeric_result_fields(bearing.result_snapshot()),
    }
    if provider is not None:
        arrays["provider_samples"] = np.asarray(provider.samples, dtype=float)
    metadata = {
        "steps": steps,
        "time_step": TIME_STEP,
        "loads": list(LOADS),
        "bearing_spec": spec,
        "result_metadata": {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in result.metadata.items()
        },
        "converged": bool(result.convergence.converged),
    }
    return metadata, arrays


def run_thermal_transient_liquid_film() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Liquid film with a transient (backward-Euler) thermal model."""

    return _simulation_case(thermal_liquid_spec(True), 8)


def run_thermal_steady_liquid_film() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Liquid film with a steady thermal model."""

    return _simulation_case(thermal_liquid_spec(False), 8)


def run_active_pid_thermal_transient() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Active PID bearing whose four pads carry a transient thermal model."""

    return _simulation_case(thermal_active_spec(), 3)


def run_multi_pad_children() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Multi-pad composite with liquid, active PID, and thermal children."""

    return _simulation_case(multi_pad_spec(), 6)


def run_external_spool_provider() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """External-spool active bearing (ALBSV) driven by a spool provider."""

    metadata, arrays = _simulation_case(
        external_spool_spec(),
        12,
        provider=ReferenceSpoolProvider(),
    )
    metadata["provider"] = {
        "gain": PROVIDER_GAIN,
        "amplitude": PROVIDER_AMPLITUDE,
        "frequency": PROVIDER_FREQUENCY,
        "law": "clip(-gain * x + amplitude * sin(2 pi frequency t), -1, 1)",
    }
    return metadata, arrays


CASES: dict[str, Callable[[], tuple[dict[str, Any], dict[str, np.ndarray]]]] = {
    "thermal_transient_liquid_film": run_thermal_transient_liquid_film,
    "thermal_steady_liquid_film": run_thermal_steady_liquid_film,
    "active_pid_thermal_transient": run_active_pid_thermal_transient,
    "multi_pad_children": run_multi_pad_children,
    "external_spool_provider": run_external_spool_provider,
}


def capture_case(name: str) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Run one named case and prefix its arrays with the case name."""

    metadata, arrays = CASES[name]()
    return metadata, {f"{name}.{key}": value for key, value in arrays.items()}


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()


def build_reference() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Build the immutable reference payload from the unmodified source."""

    metadata_cases: dict[str, Any] = {}
    arrays: dict[str, np.ndarray] = {}
    for name in CASES:
        metadata, case_arrays = capture_case(name)
        metadata_cases[name] = {
            **metadata,
            "arrays": {
                key: {"shape": list(value.shape), "dtype": str(value.dtype)}
                for key, value in case_arrays.items()
            },
        }
        arrays.update(case_arrays)
    payload = {
        "schema": "alb.coupling-staggered-pre-0.4.7-reference.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": SOURCE_COMMIT,
        "generator_head": _git_head(),
        "purpose": (
            "Freeze the 0.4.6 staggered coupling path of thermal, active, "
            "multi-pad, and external-spool bearings before ALB 0.4.7 adds "
            "the predictor-corrector integrator and bearing checkpoints."
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "alb": ALB.__version__,
            "numpy": np.__version__,
            "scipy": _version("scipy"),
            "control": _version("control"),
            "slycot": _version("slycot"),
            "pandas": _version("pandas"),
            "ross-rotordynamics": _version("ross-rotordynamics"),
            "scikit-fem": _version("scikit-fem"),
            "scikit-fuzzy": _version("scikit-fuzzy"),
        },
        "time_step": TIME_STEP,
        "cases": metadata_cases,
        "comparison": {
            "arrays": "np.testing.assert_array_equal",
            "scope": (
                "exact equality in the recorded environment; other platforms "
                "may differ at floating-point round-off level"
            ),
        },
    }
    return payload, arrays


def main() -> int:
    """Write the pre-change JSON/NPZ reference pair exactly once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing reference pair intentionally.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=JSON_PATH,
        help="Output JSON path (defaults to refs/).",
    )
    parser.add_argument(
        "--npz",
        type=Path,
        default=NPZ_PATH,
        help="Output NPZ path (defaults to refs/).",
    )
    args = parser.parse_args()
    if not args.force and (args.json.exists() or args.npz.exists()):
        raise FileExistsError("reference exists; pass --force only intentionally")

    payload, arrays = build_reference()
    args.json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    np.savez(args.npz, **arrays)
    print(args.json)
    print(args.npz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
