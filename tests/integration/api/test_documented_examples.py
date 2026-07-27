"""Smoke tests for copyable public API configuration examples."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import ALB


EXAMPLE_ROOT = Path("docs/api/examples")
BEARING_EXAMPLES = tuple(sorted(EXAMPLE_ROOT.glob("*.json5")))


@pytest.mark.parametrize("path", BEARING_EXAMPLES, ids=lambda path: path.stem)
def test_documented_bearing_examples_use_public_facade(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "ALB_PROJECTS" not in text
    assert ":\\" not in text
    for legacy_key in ('"nx"', '"nz"', '"miu"', '"ps"'):
        assert legacy_key not in text

    config = ALB.load_bearing_config(path)
    bearing = ALB.build_bearing(config)
    result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)

    assert result.force.shape == (2,)
    assert np.all(np.isfinite(result.force))
