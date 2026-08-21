"""Smoke tests for copyable public API configuration examples."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import json5
import numpy as np
import pytest

import ALB


EXAMPLE_ROOT = Path("docs/api/examples")
BEARING_EXAMPLES = tuple(sorted(EXAMPLE_ROOT.glob("*.json5")))
TEMPLATE_EXAMPLES = tuple(sorted((EXAMPLE_ROOT / "templates").glob("*.json5")))


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


def _assert_relative_placeholder(value: str) -> None:
    path = PurePosixPath(value.replace("\\", "/"))
    assert not path.is_absolute()
    assert ".." not in path.parts
    assert ":" not in value


@pytest.mark.parametrize("path", TEMPLATE_EXAMPLES, ids=lambda path: path.stem)
def test_resource_templates_are_valid_json5_with_contained_placeholders(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")
    document = json5.loads(text)

    assert document["schema_version"] == "0.4.0"
    assert document["includes"] == []
    assert "ALB_PROJECTS" not in text
    assert ":\\" not in text

    if document["kind"] == "bearing":
        assert document["spec"]["family"] == "surrogate"
        _assert_relative_placeholder(document["spec"]["model_package"]["path"])
        assert document["spec"]["runtime"]["spool_mode"] == "fixed"
    else:
        assert document["kind"] == "simulation"
        assert document["spec"]["rotor"]["model"] == "ross_excel"
        _assert_relative_placeholder(document["spec"]["rotor"]["path"])
        for mount in document["spec"]["mounts"]:
            _assert_relative_placeholder(mount["bearing"])
        assert document["spec"]["history"]["mode"] in {
            "memory",
            "ring_buffer",
            "disk_stream",
        }
