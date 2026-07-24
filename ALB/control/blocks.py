"""Strict computational blocks for controller and valve implementations."""

from __future__ import annotations

from typing import Any

from ALB.contracts import (
    ControlInput,
    ControlOutput,
    ControllerProtocol,
    ServoValveProtocol,
    UnitSystem,
    ValveInput,
    ValveOutput,
)
from ALB.core import CommandComputingBlock, EvaluatingBlock
def run_controller_step(controller: Any, time: float, error: Any) -> Any:
    """Run one native controller step."""

    if not isinstance(controller, ControllerProtocol):
        raise TypeError("controller must satisfy ControllerProtocol")
    controller.input(time, error)
    controller.evaluate()
    return controller.output()


def run_valve_step(valve: Any, time: float, command: Any) -> Any:
    """Run one native valve step."""

    if not isinstance(valve, ServoValveProtocol):
        raise TypeError("valve must satisfy ServoValveProtocol")
    valve.input(time, command)
    valve.evaluate()
    return valve.output()


class ControllerBlock(CommandComputingBlock[ControlInput, ControlOutput]):
    """Adapt a numerical control law to the strict command port lifecycle."""

    def __init__(self, controller: Any, unit_system: UnitSystem | str) -> None:
        super().__init__()
        self._controller = controller
        self.unit_system = UnitSystem.coerce(unit_system)

    def _validate_input(self, dto: ControlInput) -> ControlInput:
        if not isinstance(dto, ControlInput):
            raise TypeError("controller input must be ControlInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("controller input unit_system does not match the block")
        return dto

    def compute_command(self) -> None:
        dto = self._require_input()
        command = run_controller_step(self._controller, dto.time, dto.error)
        self._publish_output(
            ControlOutput(command, dto.time, self.unit_system)
        )


class ValveBlock(EvaluatingBlock[ValveInput, ValveOutput]):
    """Adapt a servovalve model to the strict evaluation port lifecycle."""

    def __init__(self, valve: Any, unit_system: UnitSystem | str) -> None:
        super().__init__()
        self._valve = valve
        self.unit_system = UnitSystem.coerce(unit_system)

    def _validate_input(self, dto: ValveInput) -> ValveInput:
        if not isinstance(dto, ValveInput):
            raise TypeError("valve input must be ValveInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("valve input unit_system does not match the block")
        return dto

    def evaluate(self) -> None:
        dto = self._require_input()
        spool = run_valve_step(self._valve, dto.time, dto.command)
        self._publish_output(ValveOutput(spool, dto.time, self.unit_system))
