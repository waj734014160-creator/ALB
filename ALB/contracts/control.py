"""Controller and servovalve contracts."""

from typing import Protocol, runtime_checkable

from .block import CommandBlock, EvaluableBlock
from .ports import ControlInput, ControlOutput, ValveInput, ValveOutput
from .types import UnitSystem


@runtime_checkable
class ControllerProtocol(CommandBlock[ControlInput, ControlOutput], Protocol):
    """Controller role independent of its control law."""

    unit_system: UnitSystem


@runtime_checkable
class ServoValveProtocol(EvaluableBlock[ValveInput, ValveOutput], Protocol):
    """Servovalve dynamic role."""

    unit_system: UnitSystem
