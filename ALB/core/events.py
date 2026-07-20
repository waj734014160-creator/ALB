"""Runtime event propagation primitives."""

from typing import Any, Iterable, List, Optional


class Signal:
    """Propagate lifecycle callbacks from a parent component to its children.

    Callback order is parent first and then children in attachment order.  A
    complete ``lead_loop`` sends a true event followed by a reset event, which
    preserves the historical ALB event behavior.
    """

    def __init__(
        self,
        default: bool = False,
        sys: Any = None,
        father: Optional["Signal"] = None,
        children: Optional[Iterable["Signal"]] = None,
    ) -> None:
        self.father = father
        self._children: List[Signal] = []
        self.children = [] if children is None else list(children)
        self.signal = default
        self.sys = sys

    @property
    def children(self) -> List["Signal"]:
        """Return attached child ports in propagation order."""

        return self._children

    @children.setter
    def children(self, children: Iterable["Signal"]) -> None:
        self._children = list(children)
        for child in self._children:
            child.father = self

    def add_child(self, child: "Signal") -> None:
        """Attach one child unless the same port is already attached."""

        if not any(existing is child for existing in self._children):
            self._children.append(child)
        child.father = self

    def lead(self, signal: Optional[bool] = None, attr: Optional[str] = None) -> bool:
        """Propagate one event value and optionally invoke a callback."""

        if signal is not None:
            self.signal = signal
        if self.father is not None:
            self.signal = self.father.signal
        if self.signal and attr is not None:
            if hasattr(self.sys, attr):
                getattr(self.sys, attr)()
            else:
                raise AttributeError("attr not in sys")
        for child in self.children:
            child.lead(self.signal, attr)
        return self.signal

    def lead_loop(self, attr: str) -> None:
        """Send one active event and then reset the full signal tree."""

        self.lead(True, attr)
        self.lead(False)
