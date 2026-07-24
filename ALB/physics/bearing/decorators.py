"""Shared construction support for native bearing decorators."""

from typing import Any

from ALB.core.validation import get_unit_system


class BearingDecoratorBase:
    """Validate the unit boundary for one native bearing decorator."""

    unit_system = "dimensional"

    def __init__(self, bearing: Any) -> None:
        if bearing is None:
            raise TypeError("bearing must not be None")
        self.bearing = bearing
        self.node_link = getattr(bearing, "node_link", None)
        wrapped_unit_system = get_unit_system(bearing)
        declared_unit_system = get_unit_system(self)
        if wrapped_unit_system != declared_unit_system:
            raise TypeError("bearing decorator and wrapped bearing unit systems differ")
        self.unit_system = declared_unit_system
