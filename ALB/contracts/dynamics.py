"""Rotor dynamics contracts."""

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np

from .model import PersistableProtocol, SignalProtocol


@runtime_checkable
class RotorProtocol(PersistableProtocol, Protocol):
    """Rotor role consumed by ``RsRotorBearingCouple``."""

    signal: SignalProtocol

    def init(self, *args: Any, **kwargs: Any) -> Any:
        """Reset rotor state."""

    def output(self, node_links: Sequence[int]) -> Mapping[str, np.ndarray]:
        """Return ``uxy`` and ``uxyt`` arrays at selected nodes."""

    def input_force2node(
        self,
        t: float,
        force: np.ndarray,
        node_links: Sequence[int],
        force0: np.ndarray,
    ) -> Any:
        """Advance the rotor using current and previous nodal force arrays."""
