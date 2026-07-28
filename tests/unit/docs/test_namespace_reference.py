"""Contract tests for curated advanced-namespace documentation."""

from __future__ import annotations

from tools.docs.generate_namespace_reference import (
    _NAMESPACE_SOURCES,
    _exports,
    build_references,
    load_metadata,
)


def test_namespace_metadata_matches_explicit_exports() -> None:
    metadata = load_metadata()["namespaces"]

    for namespace, source in _NAMESPACE_SOURCES.items():
        assert set(metadata[namespace]["symbols"]) == set(_exports(source))
        assert metadata[namespace]["stability"] == "advanced"
        assert metadata[namespace]["extra"]


def test_generated_namespace_references_are_current() -> None:
    for path, expected in build_references().items():
        assert path.read_text(encoding="utf-8") == expected
        assert "高级 API" in expected
        assert "re-alb[" in expected
