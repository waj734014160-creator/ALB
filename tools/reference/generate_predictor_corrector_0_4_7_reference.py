"""Freeze the new ALB 0.4.7 predictor-corrector coupling behavior.

Unlike ``generate_coupling_staggered_pre_0_4_7_reference.py`` (frozen on the
unmodified 0.4.6 source), this reference is generated from the finished 0.4.7
implementation. It pins the new algorithm so later refactors cannot change it
silently (ADR-0007 rules 5 and 6, ADR-0010):

* the dimensional liquid film (probe trials) with the default iteration and
  with PECE;
* a small liquid film with a transient thermal model (checkpointed trials);
* an active PID bearing with an adjusted control period (checkpointed trials,
  controller once per commit);
* an external-spool active bearing whose spool provider has no checkpoint
  support (spool held per step);
* the black-box memory bearing and the hardening bearing with IQN-ILS on the
  coupling runtime.

The analytic memory bearing is the test double of
``tests/_support/dynamics/memory_bearings.py``; this generator imports it so
the regression also protects the double that the unit tests rely on.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Callable
import warnings

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import ALB  # noqa: E402
from ALB.contracts import StepContext, UnitSystem  # noqa: E402
from ALB.core.time import TimeIterDt  # noqa: E402
from ALB.dynamics.bindings import CoupledBearingBinding  # noqa: E402
from ALB.dynamics.coupling import _RotorBearingStepRuntime  # noqa: E402
from ALB.dynamics.predictor_corrector import PredictorCorrectorOptions  # noqa: E402
from ALB.dynamics.rotor import RossRotor  # noqa: E402
from tests._support.dynamics.memory_bearings import MemoryAnalyticBearing  # noqa: E402
from tools.reference.generate_coupling_default_path_0_4_6_reference import (  # noqa: E402
    LOADS,
    PID_CONTROL,
    TIME_STEP,
    SinglePlant,
    _version,
    active_spec,
    liquid_film_spec,
)
from tools.reference.generate_coupling_staggered_pre_0_4_7_reference import (  # noqa: E402
    ReferenceSpoolProvider,
    external_spool_spec,
    thermal_liquid_spec,
)
from tools.reference.generate_ros2_control_period_0_4_6_reference import (  # noqa: E402
    _AnalyticPlant,
    _HardeningBearing,
    _plain,
)


JSON_PATH = (
    REPOSITORY_ROOT / "refs" / "predictor_corrector_0_4_7_reference_v1.json"
)
NPZ_PATH = (
    REPOSITORY_ROOT / "refs" / "predictor_corrector_0_4_7_reference_v1.npz"
)
PC = "predictor_corrector"
SPEED = 2.0 * np.pi * 50.0


def _simulate(
    spec: dict[str, Any],
    steps: int,
    options: PredictorCorrectorOptions | None = None,
    *,
    time_step: float = TIME_STEP,
    provider: Any = None,
) -> tuple[dict[str, Any], dict[str, np.ndarray], Any]:
    """Run one public predictor-corrector simulation and capture arrays."""

    rotor = RossRotor(SinglePlant(), speed=SPEED, dt=time_step)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = ALB.SimulationConfig(
            rotor=rotor,
            mounts=(
                ALB.BearingMount(
                    ALB.BearingConfig(spec),
                    0,
                    spool_provider=provider,
                ),
            ),
            time_step=time_step,
            steps=steps,
            loads=LOADS,
            integrator=PC,
            predictor_corrector=options,
        )
        simulation = ALB.build_simulation(config)
        result = simulation.run()
    arrays = {
        "time": np.asarray(result.time, dtype=float),
        "rotor_displacement": np.asarray(result.rotor_displacement, dtype=float),
        "rotor_velocity": np.asarray(result.rotor_velocity, dtype=float),
        "bearing_force": np.asarray(result.bearing_force, dtype=float),
        "rotor_final_state": np.asarray(rotor.current_state(), dtype=float),
    }
    metadata = {
        "bearing_spec": spec,
        "result_metadata": _plain(dict(result.metadata)),
        "warnings": [
            {"category": item.category.__name__, "message": str(item.message)}
            for item in caught
        ],
    }
    return metadata, arrays, simulation


def run_liquid_film_iterate() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Liquid film, default options (Aitken iteration, probe trials)."""

    metadata, arrays, _ = _simulate(liquid_film_spec(), 40)
    return metadata, arrays


def run_liquid_film_pece() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Liquid film with one trial and one commit per step."""

    metadata, arrays, _ = _simulate(
        liquid_film_spec(),
        40,
        PredictorCorrectorOptions(mode="pece"),
    )
    return metadata, arrays


def run_thermal_transient() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Small transient thermal film with checkpointed lifecycle trials."""

    metadata, arrays, simulation = _simulate(thermal_liquid_spec(True), 6)
    bearing = simulation._coupling.bindings[0].bearing
    arrays["final_temperature"] = np.asarray(bearing._temperature_prev, dtype=float)
    return metadata, arrays


def run_active_pid_control_period() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Active PID with an adjusted control period (m = 4) and IQN-ILS."""

    spec = active_spec(dict(PID_CONTROL, control_period=3.5 * TIME_STEP))
    metadata, arrays, simulation = _simulate(
        spec,
        12,
        PredictorCorrectorOptions(relaxation="iqn_ils"),
    )
    controller = simulation._coupling.bindings[0].bearing._controller
    arrays["controller_times"] = np.asarray(controller.results["t"], dtype=float)
    arrays["controller_outputs"] = np.vstack(
        [np.asarray(item, dtype=float) for item in controller.results["output"]]
    )
    return metadata, arrays


def run_external_spool_held() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """External-spool bearing whose provider is held over each step."""

    provider = ReferenceSpoolProvider()
    metadata, arrays, _ = _simulate(
        external_spool_spec(),
        10,
        provider=provider,
    )
    arrays["provider_samples"] = np.asarray(provider.samples, dtype=float)
    return metadata, arrays


def _analytic(
    bearing: Any,
    options: PredictorCorrectorOptions,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    time_step = 2.5e-4
    steps = 400
    rotor = RossRotor(_AnalyticPlant(), speed=1.0, dt=time_step)
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(time_step, steps),
        CoupledBearingBinding(bearing, node_link=0),
        integrator=PC,
        predictor_corrector_options=options,
    )
    runtime.add_static_force(np.array([3.0, -20.0]), 0)
    runtime.add_unbalance(node_link=0, phase=0.3, m=2.0e-3, freq=12.0, e=1.0e-2)
    runtime._reset_for_owner()
    forces = [np.asarray(runtime.output().values["bearing_force"], dtype=float)]
    for index in range(1, steps + 1):
        snapshot = runtime.advance(
            StepContext(index, time_step * index, time_step, UnitSystem.DIMENSIONAL)
        )
        forces.append(np.asarray(snapshot.values["bearing_force"], dtype=float))
    arrays = {
        "rotor_state_history": np.asarray(rotor._xouts, dtype=float),
        "bearing_force": np.asarray(forces, dtype=float),
    }
    return {"diagnostics": _plain(runtime._pc.diagnostics())}, arrays


def run_memory_analytic() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Black-box stiffness-memory bearing with checkpointed trials."""

    bearing = MemoryAnalyticBearing(
        stiffness=3.0e4, damping=40.0, scale=6.0e-4, alpha=2.0, tau=5.0e-3
    )
    metadata, arrays = _analytic(bearing, PredictorCorrectorOptions())
    arrays["memory_history"] = np.asarray(bearing.history, dtype=float)
    return metadata, arrays


def run_hardening_iqn_ils() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Hardening analytic bearing (probe trials) with IQN-ILS."""

    return _analytic(
        _HardeningBearing(),
        PredictorCorrectorOptions(relaxation="iqn_ils"),
    )


CASES: dict[str, Callable[[], tuple[dict[str, Any], dict[str, np.ndarray]]]] = {
    "liquid_film_iterate": run_liquid_film_iterate,
    "liquid_film_pece": run_liquid_film_pece,
    "thermal_transient": run_thermal_transient,
    "active_pid_control_period": run_active_pid_control_period,
    "external_spool_held": run_external_spool_held,
    "memory_analytic": run_memory_analytic,
    "hardening_iqn_ils": run_hardening_iqn_ils,
}


def capture_case(name: str) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Run one named case and prefix its arrays with the case name."""

    metadata, arrays = CASES[name]()
    return metadata, {f"{name}.{key}": value for key, value in arrays.items()}


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()


def build_reference() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Build the reference payload from the finished 0.4.7 implementation."""

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
        "schema": "alb.predictor-corrector-0.4.7-reference.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _git_head(),
        "purpose": (
            "Freeze the new ALB 0.4.7 predictor-corrector coupling behavior "
            "(probe and checkpointed trials, PECE, Aitken and IQN-ILS, "
            "control periods, held spool providers)."
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
            "metadata": "exact equality of the JSON case metadata",
            "scope": (
                "exact equality in the recorded environment; other platforms "
                "may differ at floating-point round-off level"
            ),
        },
    }
    return payload, arrays


def main() -> int:
    """Write the new-behavior JSON/NPZ reference pair exactly once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing reference pair intentionally.",
    )
    parser.add_argument("--json", type=Path, default=JSON_PATH, help="Output JSON path.")
    parser.add_argument("--npz", type=Path, default=NPZ_PATH, help="Output NPZ path.")
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
