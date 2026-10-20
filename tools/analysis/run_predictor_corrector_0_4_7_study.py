"""Reproduce the ALB 0.4.7 predictor-corrector investigation numbers.

The study compares the staggered, ROS2, and predictor-corrector coupled
integrators on analytic plants and bearings (no trained surrogate package)
and measures the cost of checkpointed trials on small FEM film bearings. It
backs section 5 of ``docs/alb_0_4_7_predictor_corrector_report.md``:

* ``linear``: constant-coefficient bearing against the matrix-exponential
  solution (error, convergence ratio, evaluations per step);
* ``hardening``: stiffening bearing against a fine ROS2 solution;
* ``memory``: black-box bearing with stiffness memory (ROS2 not applicable);
* ``active``: black-box sampled active bearing with a first-order-hold
  (native) or zero-order-hold valve, ``m = 1`` and ``m > 1``;
* ``stiff``: strongly damped bearing (contraction factor above one) with
  every relaxation rule and PECE;
* ``film``: small FEM liquid film, contraction estimate and cost per step;
* ``thermal``: small transient thermal film (checkpointed trials), cost per
  step and iteration counts.

The analytic doubles come from ``tests/_support`` so the numbers match the
unit tests. Run from the repository root::

    python tools/analysis/run_predictor_corrector_0_4_7_study.py \
        --output .cache/tmp/predictor_corrector_0_4_7_study.json

Use ``--sections`` to run a subset. Wall-clock times depend on the machine
and are reported only as relative costs.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import time
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
from tests._support.dynamics.analytic_bearings import (  # noqa: E402
    AnalyticBearing,
    SinglePlant,
    hardening_law,
    linear_law,
)
from tests._support.dynamics.memory_bearings import (  # noqa: E402
    MemoryAnalyticBearing,
    SampledActiveAnalyticBearing,
)
from tests.unit.dynamics.test_ros2_coupling_0_4_6 import (  # noqa: E402
    STATIC_FORCE,
    UNBALANCE,
    _exact_linear_state,
)
from tools.reference.generate_coupling_default_path_0_4_6_reference import (  # noqa: E402
    LOADS,
    TIME_STEP,
    liquid_film_spec,
)
from tools.reference.generate_coupling_default_path_0_4_6_reference import (  # noqa: E402
    SinglePlant as PhysicalPlant,
)
from tools.reference.generate_coupling_staggered_pre_0_4_7_reference import (  # noqa: E402
    thermal_liquid_spec,
)


PC = "predictor_corrector"
SCHEMES: dict[str, tuple[str, PredictorCorrectorOptions | None]] = {
    "staggered": ("staggered", None),
    "ros2": ("ros2", None),
    "pc_iterate": (PC, PredictorCorrectorOptions()),
    "pc_pece": (PC, PredictorCorrectorOptions(mode="pece")),
}


def _run(
    bearing: Any,
    time_step: float,
    end_time: float,
    integrator: str,
    options: PredictorCorrectorOptions | None = None,
    unbalance: bool = True,
) -> _RotorBearingStepRuntime:
    """Run the analytic one-node plant with one bearing double."""

    steps = int(round(end_time / time_step))
    rotor = RossRotor(SinglePlant(), speed=1.0, dt=time_step)
    kwargs: dict[str, Any] = {"integrator": integrator}
    if options is not None:
        kwargs["predictor_corrector_options"] = options
    runtime = _RotorBearingStepRuntime(
        rotor,
        TimeIterDt(time_step, steps),
        CoupledBearingBinding(bearing, node_link=0),
        **kwargs,
    )
    runtime.add_static_force(STATIC_FORCE, 0)
    if unbalance:
        runtime.add_unbalance(node_link=0, **UNBALANCE)
    runtime._reset_for_owner()
    for index in range(1, steps + 1):
        runtime.advance(
            StepContext(index, time_step * index, time_step, UnitSystem.DIMENSIONAL)
        )
    return runtime


def _state(runtime: _RotorBearingStepRuntime) -> np.ndarray:
    return np.asarray(runtime.rotor.current_state(), dtype=float)


def _relative(state: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(state - reference) / np.linalg.norm(reference))


def _ratios(values: list[float]) -> list[float]:
    return [a / b for a, b in zip(values, values[1:])]


def _pc_summary(runtime: _RotorBearingStepRuntime) -> dict[str, Any] | None:
    integrator = getattr(runtime, "_pc", None)
    if integrator is None:
        return None
    diagnostics = integrator.diagnostics()
    return {
        "iterations_mean": diagnostics["iterations_per_step"]["mean"],
        "iterations_max": diagnostics["iterations_per_step"]["max"],
        "nonconverged_steps": diagnostics["nonconverged_steps"],
        "residual_ratio": diagnostics["residual_ratio"],
        "aitken_omega_range": diagnostics["aitken_omega_range"],
        "max_consistency_residual": diagnostics["max_consistency_residual"],
    }


def study_linear() -> dict[str, Any]:
    """Linear bearing: errors against the exact closed-loop solution."""

    steps = (1.25e-4, 6.25e-5, 3.125e-5)
    exact = _exact_linear_state(3.0e4, 40.0, 0.1, SinglePlant())
    result: dict[str, Any] = {"time_steps": steps}
    for name, (integrator, options) in SCHEMES.items():
        errors = []
        evaluations = None
        for time_step in steps:
            bearing = AnalyticBearing(linear_law(3.0e4, 40.0))
            runtime = _run(bearing, time_step, 0.1, integrator, options)
            errors.append(_relative(_state(runtime), exact))
            count = int(round(0.1 / time_step))
            # Lifecycle evaluations plus side-effect-free probes per step,
            # excluding the step-zero commit (and ROS2 Jacobian probes).
            probes = bearing.probes - (8 if integrator == "ros2" else 0)
            evaluations = (bearing.evaluations - 1 + probes) / count
        result[name] = {
            "errors": errors,
            "ratios": _ratios(errors),
            "evaluations_per_step": evaluations,
            "pc": _pc_summary(runtime),
        }
    return result


def study_hardening() -> dict[str, Any]:
    """Hardening bearing: errors against a fine ROS2 solution."""

    def bearing() -> AnalyticBearing:
        return AnalyticBearing(
            hardening_law(stiffness=3.0e4, damping=40.0, scale=6.0e-4, alpha=8.0)
        )

    reference = _state(_run(bearing(), 1.5625e-5, 0.1, "ros2"))
    steps = (2.5e-4, 1.25e-4, 6.25e-5)
    result: dict[str, Any] = {"time_steps": steps, "reference": "ros2 h=1.5625e-5"}
    for name, (integrator, options) in SCHEMES.items():
        states = [_state(_run(bearing(), h, 0.1, integrator, options)) for h in steps]
        differences = [float(np.linalg.norm(a - b)) for a, b in zip(states, states[1:])]
        errors = [_relative(state, reference) for state in states]
        result[name] = {
            "errors_vs_reference": errors,
            "self_convergence_ratio": differences[0] / differences[1],
        }
    return result


def study_memory() -> dict[str, Any]:
    """Black-box memory bearing: ROS2 rejects it; PC versus staggered."""

    def bearing() -> MemoryAnalyticBearing:
        return MemoryAnalyticBearing(
            stiffness=3.0e4, damping=40.0, scale=6.0e-4, alpha=2.0, tau=5.0e-3
        )

    reference = _state(_run(bearing(), 7.8125e-6, 0.1, PC))
    steps = (1.25e-4, 6.25e-5, 3.125e-5)
    result: dict[str, Any] = {"time_steps": steps, "reference": "pc_iterate h=7.8125e-6"}
    for name in ("staggered", "pc_iterate", "pc_pece"):
        integrator, options = SCHEMES[name]
        errors = []
        summary = None
        for time_step in steps:
            runtime = _run(bearing(), time_step, 0.1, integrator, options)
            errors.append(_relative(_state(runtime), reference))
            summary = _pc_summary(runtime)
        result[name] = {"errors": errors, "ratios": _ratios(errors), "pc": summary}
    try:
        _run(bearing(), 1.0e-3, 1.0e-3, "ros2")
        result["ros2"] = "accepted"
    except TypeError as exc:
        result["ros2"] = f"rejected: {exc}"
    return result


def study_active() -> dict[str, Any]:
    """Sampled active black box: FOH (native) versus ZOH valve, m = 1, 4."""

    control_period = 1.0e-3
    steps = (2.5e-4, 1.25e-4, 6.25e-5, 3.125e-5)
    result: dict[str, Any] = {"time_steps": steps, "control_period": control_period}
    for hold in ("first_order", "zero_order"):
        for label in ("m=1", "m>1"):
            for name in ("pc_iterate", "staggered"):
                integrator, options = SCHEMES[name]
                states = []
                for time_step in steps:
                    m = 1 if label == "m=1" else int(round(control_period / time_step))
                    bearing = SampledActiveAnalyticBearing(
                        stiffness=3.0e4,
                        damping=40.0,
                        spool_gain=200.0,
                        gain=500.0,
                        tau=5.0e-3,
                        control_steps=m,
                        valve_hold=hold,
                    )
                    states.append(_state(_run(bearing, time_step, 0.1, integrator, options)))
                differences = [
                    float(np.linalg.norm(a - b)) for a, b in zip(states, states[1:])
                ]
                result[f"{hold}/{label}/{name}"] = {
                    "differences": differences,
                    "ratios": _ratios(differences),
                }
    return result


def study_stiff() -> dict[str, Any]:
    """Strongly damped bearing: contraction above one at h = 1 ms."""

    time_step = 1.0e-3
    result: dict[str, Any] = {"time_step": time_step, "plant_mass": 2.0}
    for damping in (2.0e3, 8.0e3, 2.0e4):
        entry: dict[str, Any] = {
            "rho_estimate": damping * time_step / 4.0 + 3.0e4 * time_step**2 / 12.0,
        }
        reference = _state(
            _run(AnalyticBearing(linear_law(3.0e4, damping)), 1.0e-5, 0.05, "staggered")
        )
        variants = {
            "none": PredictorCorrectorOptions(relaxation="none"),
            "constant": PredictorCorrectorOptions(relaxation="constant"),
            "aitken": PredictorCorrectorOptions(relaxation="aitken"),
            "iqn_ils": PredictorCorrectorOptions(relaxation="iqn_ils"),
            "pece": PredictorCorrectorOptions(mode="pece"),
        }
        for name, options in variants.items():
            try:
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    runtime = _run(
                        AnalyticBearing(linear_law(3.0e4, damping)),
                        time_step,
                        0.05,
                        PC,
                        options,
                    )
                state = _state(runtime)
                entry[name] = {
                    "error_vs_fine_staggered": _relative(state, reference),
                    "pc": _pc_summary(runtime),
                }
            except Exception as exc:  # divergence is a recorded outcome
                entry[name] = {"failed": f"{type(exc).__name__}"}
        result[f"c={damping:g}"] = entry
    return result


def _physical_simulation(
    spec: dict[str, Any],
    steps: int,
    integrator: str,
    options: PredictorCorrectorOptions | None = None,
) -> tuple[ALB.SimulationResult, float]:
    rotor = RossRotor(PhysicalPlant(), speed=2.0 * np.pi * 50.0, dt=TIME_STEP)
    config = ALB.SimulationConfig(
        rotor=rotor,
        mounts=(ALB.BearingMount(ALB.BearingConfig(copy.deepcopy(spec)), 0),),
        time_step=TIME_STEP,
        steps=steps,
        loads=LOADS,
        integrator=integrator,
        predictor_corrector=options,
    )
    simulation = ALB.build_simulation(config)
    start = time.perf_counter()
    result = simulation.run()
    return result, time.perf_counter() - start


def _film_like(spec: dict[str, Any], steps: int) -> dict[str, Any]:
    entries: dict[str, Any] = {"steps": steps, "time_step": TIME_STEP}
    variants: dict[str, tuple[str, PredictorCorrectorOptions | None]] = {
        "staggered": ("staggered", None),
        "pc_iterate_aitken": (PC, PredictorCorrectorOptions()),
        "pc_iterate_none": (PC, PredictorCorrectorOptions(relaxation="none")),
        "pc_pece": (PC, PredictorCorrectorOptions(mode="pece")),
    }
    baseline = None
    for name, (integrator, options) in variants.items():
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result, seconds = _physical_simulation(spec, steps, integrator, options)
        per_step = seconds / (steps + 1)
        if baseline is None:
            baseline = per_step
        diagnostics = result.metadata.get("predictor_corrector_diagnostics")
        entries[name] = {
            "seconds_per_step": per_step,
            "cost_relative_to_staggered": per_step / baseline,
            "final_bearing_force": np.asarray(result.bearing_force[-1]).tolist(),
            "trials_per_step": (
                None if diagnostics is None else diagnostics["iterations_per_step"]["mean"]
            ),
            "iterations_max": (
                None if diagnostics is None else diagnostics["iterations_per_step"]["max"]
            ),
            "residual_ratio": (
                None if diagnostics is None else dict(diagnostics["residual_ratio"])
            ),
            "nonconverged_steps": (
                None if diagnostics is None else diagnostics["nonconverged_steps"]
            ),
            "max_consistency_residual": (
                None if diagnostics is None else diagnostics["max_consistency_residual"]
            ),
        }
    return entries


def study_film() -> dict[str, Any]:
    """Small FEM liquid film without thermal model (probe trials)."""

    return _film_like(liquid_film_spec(), 40)


def study_thermal() -> dict[str, Any]:
    """Small transient thermal film (checkpointed lifecycle trials)."""

    result = _film_like(thermal_liquid_spec(True), 10)
    result["note"] = (
        "every trial advances the transient thermal field once (backward "
        "Euler) from the committed state and is rolled back; the commit "
        "advances it once more"
    )
    return result


SECTIONS: dict[str, Callable[[], dict[str, Any]]] = {
    "linear": study_linear,
    "hardening": study_hardening,
    "memory": study_memory,
    "active": study_active,
    "stiff": study_stiff,
    "film": study_film,
    "thermal": study_thermal,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def main() -> int:
    """Run the selected sections and write one JSON summary."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / ".cache" / "tmp" / "predictor_corrector_0_4_7_study.json",
        help="JSON output path.",
    )
    parser.add_argument(
        "--sections",
        nargs="*",
        choices=tuple(SECTIONS),
        default=tuple(SECTIONS),
        help="Sections to run (default: all).",
    )
    args = parser.parse_args()
    payload: dict[str, Any] = {
        "alb": ALB.__version__,
        "numpy": np.__version__,
    }
    for name in args.sections:
        start = time.perf_counter()
        payload[name] = SECTIONS[name]()
        payload[name]["study_seconds"] = time.perf_counter() - start
        print(f"{name}: {payload[name]['study_seconds']:.1f} s", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
