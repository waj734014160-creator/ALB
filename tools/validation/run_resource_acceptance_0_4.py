"""Measure bounded ALB 0.4 facade runtime and Python peak memory."""

from __future__ import annotations

import gc
import json
import time
import tracemalloc
from types import SimpleNamespace
from typing import Any, Callable, cast

import numpy as np

import ALB
from ALB.contracts import RotorProtocol
from ALB.dynamics.rotor import RossRotor


MAX_CASE_SECONDS = 10.0
MAX_CASE_PEAK_BYTES = 512 * 1024 * 1024


def _bearing_config(family: str) -> ALB.BearingConfig:
    """Return one small deterministic facade benchmark configuration."""

    spec: dict[str, Any] = {
        "family": family,
        "unit_system": "dimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": {
            "circumferential_elements": 5,
            "axial_elements": 3,
            "max_iterations": 5,
            "solver_tolerance": 1.0e-6,
            "eccentricity": 0.0,
        },
    }
    if family == "liquid_film":
        spec["restrictors"] = None
        spec["thermal"] = None
    return ALB.BearingConfig(spec)


class _ResourceRotorPlant:
    """Minimal deterministic rotor plant for coupling resource measurement."""

    ndof = 4
    number_dof = 4

    def _lti(self, speed: float) -> SimpleNamespace:
        del speed
        states = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(states),
            B=np.vstack((np.eye(self.ndof), 0.25 * np.eye(self.ndof))),
            C=np.eye(states),
            D=np.zeros((states, self.ndof)),
        )


def _measure(name: str, action: Callable[[], object]) -> dict[str, Any]:
    """Measure one warmed action and enforce explicit absolute budgets."""

    action()
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = action()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if elapsed > MAX_CASE_SECONDS:
        raise RuntimeError(
            f"{name} exceeded runtime budget: {elapsed:.6f}s"
        )
    if peak > MAX_CASE_PEAK_BYTES:
        raise RuntimeError(f"{name} exceeded peak memory budget: {peak}")
    return {
        "case": name,
        "elapsed_seconds": elapsed,
        "peak_memory_bytes": peak,
        "max_seconds": MAX_CASE_SECONDS,
        "max_peak_memory_bytes": MAX_CASE_PEAK_BYTES,
        "result_type": type(result).__name__,
        "status": "passed",
    }


def run_resource_acceptance() -> dict[str, Any]:
    """Run representative liquid, gas, and coupled facade measurements."""

    liquid_config = _bearing_config("liquid_film")
    gas_config = _bearing_config("gas_film")

    def liquid() -> ALB.BearingResult:
        return ALB.build_bearing(liquid_config).calculate(
            displacement=(0.0, 0.0),
            time=0.0,
        )

    def gas() -> ALB.BearingResult:
        return ALB.build_bearing(gas_config).calculate(
            displacement=(0.0, 0.0),
            time=0.0,
        )

    def simulation() -> ALB.SimulationResult:
        rotor = RossRotor(_ResourceRotorPlant(), speed=1.0, dt=1.0e-3)
        config = ALB.SimulationConfig(
            rotor=cast(RotorProtocol, rotor),
            mounts=(ALB.BearingMount(liquid_config, 0),),
            time_step=1.0e-3,
            steps=1,
        )
        return ALB.build_simulation(config).run()

    results = [
        _measure("liquid_film_facade", liquid),
        _measure("gas_film_facade", gas),
        _measure("rotor_bearing_simulation", simulation),
    ]
    return {
        "schema": "alb.resource-acceptance.v0.4",
        "status": "passed",
        "cases": results,
    }


def main() -> int:
    """Print machine-readable evidence without mutating the candidate tree."""

    print(json.dumps(run_resource_acceptance(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
