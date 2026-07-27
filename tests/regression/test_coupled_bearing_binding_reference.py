"""Exact construction contracts for rotor-coupled bearing bindings."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ALB.contracts import (
    BearingInput,
    DirectSpoolBearingInput,
    UnitSystem,
)
from ALB.dynamics.bindings import CoupledBearingBinding


_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "refs/coupled_bearing_binding_reference_v1.json"
)


class _Runtime:
    node_link = 0
    lifecycle_state = object()
    convergence_status = object()

    def __init__(self, input_type: type[Any], unit: UnitSystem) -> None:
        self.input_dto_type = input_type
        self.unit_system = unit

    def input(self, dto: object) -> None:
        return None

    def evaluate(self) -> None:
        return None

    def output(self) -> None:
        return None

    def step(self, dto: object) -> None:
        return None

    def result_snapshot(self) -> None:
        return None

    def failure_snapshot(self) -> None:
        return None

    def diagnostic_snapshot(self) -> None:
        return None


class _Provider:
    def input(self, context: object, bearing_input: BearingInput) -> None:
        return None

    def evaluate(self) -> None:
        return None

    def output(self) -> None:
        return None


class _Adapter:
    def __init__(
        self,
        rotor_unit: UnitSystem,
        bearing_unit: UnitSystem,
    ) -> None:
        self.scales = SimpleNamespace(
            rotor_unit=rotor_unit,
            bearing_unit=bearing_unit,
        )

    def rotor_context_to_bearing(self, context: object) -> object:
        return context

    def rotor_input_to_bearing(self, value: object) -> object:
        return value

    def rotor_direct_spool_to_bearing(self, value: object) -> object:
        return value

    def bearing_output_to_rotor(self, value: object) -> object:
        return value


def _case(name: str) -> dict[str, object]:
    dimensional = _Runtime(BearingInput, UnitSystem.DIMENSIONAL)
    if name == "dimensional_ordinary":
        return {"bearing": dimensional, "node_link": 2}
    if name == "negative_node":
        return {"bearing": dimensional, "node_link": -1}
    if name == "direct_without_provider":
        return {
            "bearing": _Runtime(
                DirectSpoolBearingInput,
                UnitSystem.DIMENSIONAL,
            ),
            "node_link": 0,
        }
    if name == "nondimensional_without_adapter":
        return {
            "bearing": _Runtime(BearingInput, UnitSystem.NONDIMENSIONAL),
            "node_link": 0,
        }
    if name == "nondimensional_with_adapter":
        return {
            "bearing": _Runtime(BearingInput, UnitSystem.NONDIMENSIONAL),
            "node_link": 1,
            "unit_adapter": _Adapter(
                UnitSystem.DIMENSIONAL,
                UnitSystem.NONDIMENSIONAL,
            ),
        }
    if name == "ordinary_with_provider":
        return {
            "bearing": dimensional,
            "node_link": 0,
            "spool_provider": _Provider(),
        }
    raise AssertionError(f"unknown reference case: {name}")


def _capture(name: str) -> dict[str, object]:
    try:
        binding = CoupledBearingBinding(**_case(name))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        return {
            "name": name,
            "status": "error",
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    return {
        "name": name,
        "status": "accepted",
        "node_link": binding.node_link,
        "input_dto_type": binding.bearing.input_dto_type.__name__,
        "bearing_unit": UnitSystem.coerce(binding.bearing.unit_system).value,
        "has_unit_adapter": binding.unit_adapter is not None,
        "has_spool_provider": binding.spool_provider is not None,
    }


def test_coupled_bearing_binding_matches_pre_refactor_reference() -> None:
    reference = json.loads(_REFERENCE.read_text(encoding="utf-8"))
    actual = {
        "schema": reference["schema"],
        "cases": [_capture(case["name"]) for case in reference["cases"]],
    }

    assert actual == reference
