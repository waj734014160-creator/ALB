"""Compatibility adapters for standard bearing integration."""

from typing import Any, Optional

from ALB.core.component import BearingComponentBase
from ALB.core.validation import get_unit_system


class BearingDecoratorBase(BearingComponentBase):
    """Delegate the standard bearing contract to a wrapped bearing.

    Decorators that add thermal, diagnostic, or filtering behavior can inherit
    this class and override only the operations they actually modify.
    """

    unit_system = "dimensional"

    def __init__(self, bearing: Any) -> None:
        if bearing is None:
            raise TypeError("bearing must not be None")
        super().__init__()
        self.bearing = bearing
        self.node_link = getattr(bearing, "node_link", None)
        wrapped_unit_system = get_unit_system(bearing)
        declared_unit_system = get_unit_system(self)
        if wrapped_unit_system != declared_unit_system:
            raise TypeError("bearing decorator and wrapped bearing unit systems differ")
        self.unit_system = declared_unit_system
        self.signal.children = [bearing.signal]

    @property
    def results(self) -> Any:
        return getattr(self.bearing, "results")

    def init(self, *args: Any, **kwargs: Any) -> Any:
        return self.bearing.init(*args, **kwargs)

    def input(self, *args: Any, **kwargs: Any) -> Any:
        return self.bearing.input(*args, **kwargs)

    def output(self, *args: Any, **kwargs: Any) -> Any:
        output = self.bearing.output(*args, **kwargs)
        self.validate_output(output)
        return output

    def calc_error(self, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.bearing, "calc_error", None)
        return 0.0 if method is None else method(*args, **kwargs)

    def calc_is_finished(self, *args: Any, **kwargs: Any) -> bool:
        method = getattr(self.bearing, "calc_is_finished", None)
        return True if method is None else bool(method(*args, **kwargs))

    def save(
        self,
        tofile: bool = True,
        path: Optional[str] = None,
        name: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return self.bearing.save(
            *args,
            tofile=tofile,
            path=path,
            name=name,
            **kwargs,
        )


class LegacyBearingAdapter(BearingDecoratorBase):
    """Attach explicit node and unit metadata to an older bearing object."""

    def __init__(
        self,
        bearing: Any,
        *,
        node_link: Optional[int] = None,
        unit_system: str = "dimensional",
    ) -> None:
        wrapped_unit_system = get_unit_system(bearing)
        if wrapped_unit_system != unit_system:
            raise TypeError("legacy adapter cannot relabel an explicit unit system")
        super().__init__(bearing)
        if node_link is not None:
            self.node_link = int(node_link)
        self.unit_system = unit_system
        get_unit_system(self)
