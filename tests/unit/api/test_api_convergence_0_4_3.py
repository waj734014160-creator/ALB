"""User-boundary tests for the simplified ALB 0.4.3 facade."""

from __future__ import annotations

import numpy as np
import pytest

import ALB
from ALB.contracts import LifecycleState, UnitSystem


class _Rotor:
    """Minimal dimensional rotor used to validate simulation declarations."""

    unit_system = UnitSystem.DIMENSIONAL
    lifecycle_state = LifecycleState.READY
    dt = 1.0e-3

    def _reset_for_owner(self, initial_state=None) -> None:
        del initial_state

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

    def current_state(self, node=None) -> np.ndarray:
        del node
        return np.zeros(4)

    def output(self, node=None) -> object:
        count = 1 if node is None else len(np.atleast_1d(node))
        return {
            "uxy": np.zeros((count, 2)),
            "uxyt": np.zeros((count, 2)),
        }


def _liquid_config() -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {
                "circumferential_elements": 5,
                "axial_elements": 3,
                "max_iterations": 5,
            },
            "restrictors": None,
            "thermal": None,
        }
    )


def test_invalid_supply_pressure_is_rejected_before_runtime_build() -> None:
    spec = _liquid_config().to_dict()["spec"]
    spec["film"]["supply_pressure"] = -1.0

    with pytest.raises(
        ALB.ConfigurationError,
        match=r"spec\.film\.supply_pressure",
    ):
        ALB.BearingConfig(spec)


def test_simulation_loads_are_validated_and_deeply_frozen() -> None:
    source = {"type": "static", "node": 0, "force": [1.0, -2.0]}
    config = ALB.SimulationConfig(
        rotor=_Rotor(),
        mounts=(ALB.BearingMount(_liquid_config(), 0),),
        time_step=1.0e-3,
        steps=0,
        loads=(source,),
    )
    source["force"][0] = 99.0

    np.testing.assert_array_equal(config.loads[0]["force"], [1.0, -2.0])
    with pytest.raises(TypeError):
        config.loads[0]["node"] = 1
    with pytest.raises(ValueError):
        config.loads[0]["force"][0] = 3.0


@pytest.mark.parametrize(
    "load",
    [
        {"type": "static", "node": 0},
        {"type": "gravity", "acceleration": float("nan")},
        {"type": "unbalance", "node": -1},
        {"type": "unknown"},
    ],
)
def test_invalid_loads_fail_at_simulation_config(load: object) -> None:
    with pytest.raises(ALB.ConfigurationError):
        ALB.SimulationConfig(
            rotor=_Rotor(),
            mounts=(ALB.BearingMount(_liquid_config(), 0),),
            time_step=1.0e-3,
            steps=0,
            loads=(load,),
        )


def test_analysis_constructors_reject_invalid_public_inputs() -> None:
    bearing = ALB.build_bearing(_liquid_config())

    with pytest.raises(TypeError, match="bearing must be Bearing or"):
        ALB.BearingAnalysis(None)
    with pytest.raises(TypeError, match="bearing must be Bearing or"):
        ALB.EquilibriumSolver(None)
    with pytest.raises(TypeError, match="options must be EquilibriumOptions"):
        ALB.EquilibriumSolver(bearing, options=object())


@pytest.mark.parametrize(
    ("film_override", "message"),
    [
        ({"solver": "newton"}, r"spec\.film\.solver"),
        ({"texture_type": "groove"}, r"spec\.film\.texture_type"),
        ({"texture_type": 4}, r"spec\.film\.texture_type"),
        (
            {"texture_start_theta_index": 0},
            r"spec\.film\.texture_start_theta_index",
        ),
        (
            {"texture_start_axial_index": 0},
            r"spec\.film\.texture_start_axial_index",
        ),
    ],
)
def test_gas_specific_constraints_fail_at_config_boundary(
    film_override: dict[str, object],
    message: str,
) -> None:
    spec = {
        "family": "gas_film",
        "unit_system": "dimensional",
        "time_step": 1.0e-3,
        "node": 0,
        "film": film_override,
    }

    with pytest.raises(ALB.ConfigurationError, match=message):
        ALB.BearingConfig(spec)


def test_bearing_does_not_wrap_keyboard_interrupt() -> None:
    class _InterruptedRuntime:
        def step(self, dto):
            del dto
            raise KeyboardInterrupt

    bearing = ALB.build_bearing(_liquid_config())
    bearing._runtime = _InterruptedRuntime()

    with pytest.raises(KeyboardInterrupt):
        bearing.calculate(displacement=(0.0, 0.0), time=0.0)


def test_simulation_does_not_wrap_keyboard_interrupt() -> None:
    class _InterruptedCoupling:
        def _reset_for_owner(self):
            raise KeyboardInterrupt

    simulation = ALB.build_simulation(
        ALB.SimulationConfig(
            rotor=_Rotor(),
            mounts=(ALB.BearingMount(_liquid_config(), 0),),
            time_step=1.0e-3,
            steps=0,
        )
    )
    simulation._coupling = _InterruptedCoupling()

    with pytest.raises(KeyboardInterrupt):
        simulation.run()
