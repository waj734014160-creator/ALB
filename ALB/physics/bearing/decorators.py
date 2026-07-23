"""Compatibility adapters for standard bearing integration."""

import inspect
from typing import Any, Literal, Optional
import warnings

from ALB.contracts import (
    BearingInput,
    BearingOutput,
    ConvergenceStatus,
    LifecycleState,
    ResultBundle,
    UnitSystem,
    result_snapshot,
)
from ALB.core.component import BearingComponentBase
from ALB.core.lifecycle import RuntimeLifecycle
from ALB.core.diagnostics import sanitize_exception_message
from ALB.core.validation import get_unit_system
from ALB.core.validation import validate_bearing_output


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

    def evaluate(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate explicit evaluation, with a bridge for legacy wrapped bearings."""

        method = getattr(self.bearing, "evaluate", None)
        if method is not None:
            return method(*args, **kwargs)
        return self.bearing.output(*args, **kwargs)

    def step(self, *args: Any, **kwargs: Any) -> Any:
        """Compose legacy input, explicit evaluation, and read-only output."""

        self.input(*args, **kwargs)
        self.evaluate()
        return self.output()

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


class LegacyBearingAdapter:
    """Isolate a calculating-output bearing behind the strict 0.3 runtime.

    This compatibility adapter is deprecated for removal no earlier than
    0.4.0. New in-repository bearings must implement the native lifecycle.
    """

    input_dto_type = BearingInput

    def __init__(
        self,
        bearing: Any,
        *,
        node_link: Optional[int] = None,
        unit_system: str = "dimensional",
        input_style: Literal["keywords", "positional"] | None = None,
    ) -> None:
        warnings.warn(
            "LegacyBearingAdapter is a 0.3.x migration surface",
            DeprecationWarning,
            stacklevel=2,
        )
        wrapped_unit_system = get_unit_system(bearing)
        if wrapped_unit_system != unit_system:
            raise TypeError("legacy adapter cannot relabel an explicit unit system")
        self.bearing = bearing
        self.node_link = (
            int(node_link)
            if node_link is not None
            else getattr(bearing, "node_link", None)
        )
        self.unit_system = UnitSystem.coerce(unit_system)
        self._lifecycle = RuntimeLifecycle(
            type(self).__name__, input_label="bearing input"
        )
        self._input: BearingInput | None = None
        self._output: BearingOutput | None = None
        self._result: ResultBundle | None = None
        self._failure: ResultBundle | None = None
        self._input_style = self._resolve_input_style(
            self.bearing.input,
            input_style,
        )

    @staticmethod
    def _resolve_input_style(
        method: Any,
        declared: Literal["keywords", "positional"] | None,
    ) -> Literal["keywords", "positional"]:
        """Resolve the legacy call shape before any mutable input call."""

        if declared is not None:
            if declared not in {"keywords", "positional"}:
                raise ValueError("input_style must be 'keywords' or 'positional'")
            return declared
        try:
            call_signature = inspect.signature(method)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "legacy input signature is not inspectable; provide input_style"
            ) from exc
        marker = object()
        try:
            call_signature.bind(uxy=marker, uxyt=marker, t=marker)
        except TypeError:
            try:
                call_signature.bind(marker, marker, marker)
            except TypeError as exc:
                raise TypeError(
                    "legacy bearing input must accept uxy, uxyt, and t"
                ) from exc
            return "positional"
        return "keywords"

    @property
    def lifecycle_state(self) -> LifecycleState:
        return self._lifecycle.state

    @property
    def convergence_status(self) -> ConvergenceStatus:
        finished = getattr(self.bearing, "calc_is_finished", None)
        if callable(finished) and not bool(finished()):
            return ConvergenceStatus.pending("legacy calculation is incomplete")
        return ConvergenceStatus(0.0, True, message="legacy calculation finished")

    def init(self) -> None:
        self._lifecycle.fail()
        try:
            self.bearing.init()
            self._input = None
            self._output = None
            self._result = None
            self._failure = None
        except BaseException as exc:
            self._failure = result_snapshot(
                {},
                {
                    "phase": "init",
                    "error_type": type(exc).__name__,
                    "message": sanitize_exception_message(exc),
                },
            )
            raise
        self._lifecycle.reset()

    def input(self, dto: BearingInput) -> None:
        self._lifecycle.require_input_slot()
        if not isinstance(dto, BearingInput):
            raise TypeError("legacy bearing input must be BearingInput")
        if dto.unit_system is not self.unit_system:
            raise ValueError("bearing input unit_system does not match adapter")
        self._input = dto
        self._output = None
        self._result = None
        self._lifecycle.latch()

    def evaluate(self) -> None:
        dto = self._input
        try:
            with self._lifecycle.evaluation():
                assert dto is not None
                if self._input_style == "keywords":
                    self.bearing.input(
                        uxy=dto.displacement,
                        uxyt=dto.velocity,
                        t=dto.time,
                    )
                else:
                    self.bearing.input(
                        dto.displacement,
                        dto.velocity,
                        dto.time,
                    )
                force = validate_bearing_output(self.bearing.output())
                self._output = BearingOutput(force, dto.time, self.unit_system)
                self._result = result_snapshot(
                    {"force": self._output.force},
                    {
                        "time": dto.time,
                        "unit_system": self.unit_system.value,
                        "compatibility_adapter": type(self).__name__,
                    },
                )
        except BaseException as exc:
            self._output = None
            self._result = None
            self._failure = result_snapshot(
                {},
                {
                    "phase": "evaluate",
                    "error_type": type(exc).__name__,
                    "message": sanitize_exception_message(exc),
                },
            )
            raise

    def output(self) -> BearingOutput:
        self._lifecycle.require_output()
        assert self._output is not None
        return self._output

    def step(self, dto: BearingInput) -> BearingOutput:
        self.input(dto)
        self.evaluate()
        return self.output()

    def result_snapshot(self) -> ResultBundle:
        self._lifecycle.require_output()
        assert self._result is not None
        return self._result

    def failure_snapshot(self) -> ResultBundle:
        if self._failure is None:
            raise RuntimeError("no legacy bearing failure snapshot is available")
        return self._failure

    def diagnostic_snapshot(self) -> ResultBundle:
        if self._failure is not None:
            return self._failure
        return self.result_snapshot()
