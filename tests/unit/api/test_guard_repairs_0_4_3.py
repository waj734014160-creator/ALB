"""Focused boundary tests for the ALB 0.4.3 guard repairs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import ALB
from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    UnitSystem,
)
from ALB.surrogate.runtime import SurrogateBearingRuntime


class _MappingRotor:
    """Minimal rotor with a valid coupled state mapping."""

    lifecycle_state = LifecycleState.READY

    def __init__(
        self,
        dt: float,
        *,
        unit_system: UnitSystem = UnitSystem.DIMENSIONAL,
        output_value: object | None = None,
    ) -> None:
        self.dt = dt
        self.unit_system = unit_system
        self.reset_count = 0
        self._output_value = output_value

    def _reset_for_owner(self, initial_state=None) -> None:
        del initial_state
        self.reset_count += 1

    def input_force2node(
        self,
        time,
        force,
        node,
        initial_state=None,
        *,
        force0=None,
    ) -> None:
        del time, force, node, initial_state, force0

    def input_load(self, value) -> None:
        del value

    def advance(self) -> np.ndarray:
        return np.zeros(4)

    def current_state(self, node=None) -> object:
        return self.output(node)

    def output(self, node=None) -> object:
        if self._output_value is not None:
            return self._output_value
        count = 1 if node is None else len(np.atleast_1d(node))
        return {
            "uxy": np.zeros((count, 2), dtype=float),
            "uxyt": np.zeros((count, 2), dtype=float),
        }


class _DeterministicModel:
    """Small surrogate model used to test constructor validation."""

    def input(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def output(self, *, nodim: bool) -> np.ndarray:
        del nodim
        return np.zeros(2, dtype=float)


def _liquid_spec() -> dict[str, object]:
    return {
        "family": "liquid_film",
        "unit_system": "dimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": {},
        "restrictors": None,
        "thermal": None,
    }


def _liquid_config() -> ALB.BearingConfig:
    return ALB.BearingConfig(_liquid_spec())


def _simulation_config(rotor: _MappingRotor) -> ALB.SimulationConfig:
    return ALB.SimulationConfig(
        rotor=rotor,
        mounts=(ALB.BearingMount(_liquid_config(), 0),),
        time_step=1.0e-3,
        steps=1,
    )


def test_simulation_rejects_nondimensional_rotor_at_config_time() -> None:
    rotor = _MappingRotor(
        1.0e-3,
        unit_system=UnitSystem.NONDIMENSIONAL,
    )

    with pytest.raises(
        ALB.ConfigurationError,
        match="rotor.unit_system.*dimensional",
    ):
        _simulation_config(rotor)

    assert rotor.reset_count == 0


@pytest.mark.parametrize(
    ("output_value", "message"),
    [
        (np.zeros(4), "mapping"),
        ({"uxy": np.zeros((1, 2))}, "uxyt"),
        (
            {
                "uxy": np.zeros((1, 3)),
                "uxyt": np.zeros((1, 2)),
            },
            "shape",
        ),
        (
            {
                "uxy": np.array([[np.nan, 0.0]]),
                "uxyt": np.zeros((1, 2)),
            },
            "finite",
        ),
    ],
)
def test_simulation_rejects_invalid_rotor_output_before_reset(
    output_value: object,
    message: str,
) -> None:
    rotor = _MappingRotor(1.0e-3, output_value=output_value)

    with pytest.raises(ALB.ConfigurationError, match=message):
        _simulation_config(rotor)

    assert rotor.reset_count == 0


class _SubnormalEquilibriumRuntime:
    convergence_status = ConvergenceStatus(1.0, False)

    def __init__(self) -> None:
        self._input: BearingInput | None = None

    @staticmethod
    def _reset_for_owner() -> None:
        return None

    def input(self, value: BearingInput) -> None:
        self._input = value

    @staticmethod
    def evaluate_static() -> None:
        return None

    def output(self) -> BearingOutput:
        assert self._input is not None
        return BearingOutput(
            force=np.zeros(2),
            time=self._input.time,
            unit_system=UnitSystem.NONDIMENSIONAL,
        )


class _SubnormalEquilibriumBearing:
    config = SimpleNamespace(
        unit_system="nondimensional",
        control_mode="uncontrolled",
        family="liquid_film",
    )


def test_equilibrium_subnormal_load_is_not_perfectly_converged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subnormal = np.nextafter(0.0, 1.0)
    solver = ALB.EquilibriumSolver(
        _SubnormalEquilibriumBearing(),
        ALB.EquilibriumOptions(max_iterations=1, stall_patience=0),
    )
    monkeypatch.setattr(solver, "_new_runtime", _SubnormalEquilibriumRuntime)

    with pytest.raises(ALB.CalculationError) as caught:
        solver.solve(np.array([subnormal, 0.0]))

    assert caught.value.failure_snapshot is not None
    snapshot = caught.value.failure_snapshot
    assert snapshot.values["evaluation_relative_residual"][0] == 1.0
    assert snapshot.metadata["success"] is False


def test_equilibrium_stable_norm_keeps_normal_result_exact() -> None:
    from ALB.api.analysis import _stable_load_norm

    value = np.array([3.0, 4.0], dtype=float)
    assert _stable_load_norm(value) == float(np.linalg.norm(value))
    assert _stable_load_norm(np.array([1.0e308, 1.0e308])) == pytest.approx(
        np.hypot(1.0e308, 1.0e308),
        rel=0.0,
        abs=0.0,
    )


def test_json5_rejects_duplicate_object_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json5"
    path.write_text("{value: 1, value: 2}", encoding="utf-8")

    from ALB.api.config import _read_json5

    with pytest.raises(ALB.ConfigurationError, match="invalid JSON5"):
        _read_json5(path)


@pytest.mark.parametrize("time_step", ["0.001", True])
def test_bearing_config_rejects_coerced_time_step(time_step: object) -> None:
    spec = _liquid_spec()
    spec["time_step"] = time_step

    with pytest.raises(ALB.ConfigurationError, match="time_step.*real number"):
        ALB.BearingConfig(spec)


def _write_simulation_documents(
    root: Path,
    *,
    time_step: object = 1.0e-3,
    steps: object = 1,
    node: object = 0,
    downsample: object = 1,
) -> Path:
    bearing = root / "bearing.json5"
    bearing.write_text(
        json.dumps(
            {
                "schema_version": "0.4.0",
                "kind": "bearing",
                "spec": _liquid_spec(),
            }
        ),
        encoding="utf-8",
    )
    simulation = root / "simulation.json5"
    simulation.write_text(
        json.dumps(
            {
                "schema_version": "0.4.0",
                "kind": "simulation",
                "spec": {
                    "rotor": {
                        "model": "ross_excel",
                        "path": "unused.xlsx",
                        "frequency_hz": 10.0,
                    },
                    "time_grid": {
                        "time_step": time_step,
                        "steps": steps,
                    },
                    "mounts": [{"bearing": "bearing.json5", "node": node}],
                    "history": {
                        "mode": "memory",
                        "downsample": downsample,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return simulation


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("time_step", "0.001", "time_step.*real number"),
        ("time_step", True, "time_step.*real number"),
        ("steps", 1.9, "steps.*integer"),
        ("steps", True, "steps.*integer"),
        ("node", 0.9, "node.*integer"),
        ("node", True, "node.*integer"),
        ("downsample", 1.9, "downsample.*integer"),
        ("downsample", True, "downsample.*integer"),
    ],
)
def test_simulation_json_rejects_scalar_coercion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    values = {
        "time_step": 1.0e-3,
        "steps": 1,
        "node": 0,
        "downsample": 1,
    }
    values[field] = value
    path = _write_simulation_documents(tmp_path, **values)

    from ALB.dynamics import rotor as rotor_module

    monkeypatch.setattr(
        rotor_module,
        "rotor0",
        lambda **kwargs: _MappingRotor(float(kwargs["dt"])),
    )
    with pytest.raises(ALB.ConfigurationError, match=message):
        ALB.load_simulation_config(path)


def _surrogate_spec(spool: object) -> dict[str, object]:
    return {
        "family": "surrogate",
        "unit_system": "nondimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "model_package": {"path": "model", "use_augment": False},
        "runtime": {
            "spool_mode": "fixed",
            "spool": spool,
            "parameters": {},
        },
    }


@pytest.mark.parametrize("spool", ([1.01, 0.0], [0.0, -1.01]))
def test_surrogate_config_rejects_out_of_range_fixed_spool(
    tmp_path: Path,
    spool: object,
) -> None:
    with pytest.raises(ALB.ConfigurationError, match=r"within \[-1, 1\]"):
        ALB.BearingConfig(_surrogate_spec(spool), resource_root=tmp_path)


@pytest.mark.parametrize("spool", ([1.01, 0.0], [0.0, -1.01]))
def test_surrogate_runtime_rejects_out_of_range_fixed_spool(
    spool: object,
) -> None:
    with pytest.raises(ValueError, match=r"within \[-1, 1\]"):
        SurrogateBearingRuntime(
            _DeterministicModel(),
            unit_system=UnitSystem.NONDIMENSIONAL,
            node_link=0,
            external_spool=False,
            fixed_spool=spool,
        )


def test_surrogate_runtime_keeps_in_range_fixed_spool() -> None:
    runtime = SurrogateBearingRuntime(
        _DeterministicModel(),
        unit_system=UnitSystem.NONDIMENSIONAL,
        node_link=0,
        external_spool=False,
        fixed_spool=(1.0, -1.0),
    )
    runtime.input(
        BearingInput(
            displacement=np.zeros(2),
            velocity=np.zeros(2),
            time=0.0,
            unit_system=UnitSystem.NONDIMENSIONAL,
        )
    )
