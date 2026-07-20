"""Strict lifecycle tests for 0.2 computational blocks."""

import pytest

from ALB.core import EvaluatingBlock


class _DoubleBlock(EvaluatingBlock[int, int]):
    def _validate_input(self, dto: int) -> int:
        if not isinstance(dto, int):
            raise TypeError("input must be an integer")
        return dto

    def evaluate(self) -> None:
        self._publish_output(self._require_input() * 2)


def test_output_is_read_only_and_requires_fresh_computation():
    block = _DoubleBlock()
    with pytest.raises(RuntimeError, match="unavailable"):
        block.output()

    block.input(3)
    with pytest.raises(RuntimeError, match="unavailable"):
        block.output()

    block.evaluate()
    assert block.output() == 6
    assert block.output() == 6

    block.input(4)
    with pytest.raises(RuntimeError, match="unavailable"):
        block.output()


def test_step_composes_local_lifecycle_without_time_commit():
    block = _DoubleBlock()
    assert block.step(5) == 10
    assert block.output() == 10


def test_computation_requires_latched_input():
    block = _DoubleBlock()
    with pytest.raises(RuntimeError, match="input must be latched"):
        block.evaluate()
