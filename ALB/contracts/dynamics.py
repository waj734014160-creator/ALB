"""Rotor dynamics contracts."""

from typing import Protocol, runtime_checkable

from .block import AdvancingBlock
from .ports import RotorLoadInput, RotorState
from .types import UnitSystem


@runtime_checkable
class RotorProtocol(AdvancingBlock[RotorLoadInput, RotorState], Protocol):
    """Rotor role consumed by ``RsRotorBearingCouple``."""

    unit_system: UnitSystem
