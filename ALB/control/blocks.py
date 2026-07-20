"""Strict 0.2 computational blocks for controller and valve implementations."""

from __future__ import annotations

from typing import Any

from ALB.contracts import (
    ControlInput,
    ControlOutput,
    UnitSystem,
    ValveInput,
    ValveOutput,
)
from ALB.core import CommandComputingBlock, EvaluatingBlock


class ControllerBlock(CommandComputingBlock[ControlInput, ControlOutput]):
    """Adapt a numerical control law to the strict command port lifecycle."""

    def __init__(self, controller: Any, unit_system: UnitSystem | str) -> None:
        super().__init__()
        self.controller = controller
        self.unit_system = UnitSystem.coerce(unit_system)

    def _validate_input(self, dto: ControlInput) -> ControlInput:
        if not isinstance(dto, ControlInput):
            raise TypeError("controller input must be ControlInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("controller input unit_system does not match the block")
        return dto

    def compute_command(self) -> None:
        dto = self._require_input()
        self.controller.input(dto.time, dto.error)
        command = self.controller.output()
        self._publish_output(
            ControlOutput(command, dto.time, self.unit_system)
        )


class ValveBlock(EvaluatingBlock[ValveInput, ValveOutput]):
    """Adapt a servovalve model to the strict evaluation port lifecycle."""

    def __init__(self, valve: Any, unit_system: UnitSystem | str) -> None:
        super().__init__()
        self.valve = valve
        self.unit_system = UnitSystem.coerce(unit_system)

    def _validate_input(self, dto: ValveInput) -> ValveInput:
        if not isinstance(dto, ValveInput):
            raise TypeError("valve input must be ValveInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("valve input unit_system does not match the block")
        return dto

    def evaluate(self) -> None:
        dto = self._require_input()
        self.valve.input(dto.time, dto.command)
        spool = self.valve.output()
        self._publish_output(ValveOutput(spool, dto.time, self.unit_system))
