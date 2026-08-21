"""Contract tests for curated advanced-namespace documentation."""

from __future__ import annotations

from tools.docs._source_contracts import render_docstring_details
from tools.docs.generate_namespace_reference import (
    _NAMESPACE_SOURCES,
    _exports,
    _surface,
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


def test_namespace_pages_match_complete_explicit_source_contracts() -> None:
    metadata = load_metadata()["namespaces"]
    references = build_references()
    export_count = 0

    for namespace, source_path in _NAMESPACE_SOURCES.items():
        surface = _surface(namespace)
        exports = set(_exports(source_path))
        assert set(surface) == exports
        assert set(metadata[namespace]["symbols"]) == exports
        export_count += len(surface)
        page = references[next(path for path in references if path.stem == namespace.rsplit(".", 1)[-1])]

        for name, symbol in surface.items():
            notes = metadata[namespace]["symbols"][name]
            assert set(notes["parameters"]) == set(symbol.parameters)
            assert set(notes["members"]) == {member.name for member in symbol.members}
            assert len(
                [line for line in symbol.docstring.splitlines() if line.strip()]
            ) >= 2
            assert render_docstring_details(symbol.docstring) in page
            assert f"`{symbol.source}:{symbol.line}`" in page
            for member in symbol.members:
                member_notes = notes["members"][member.name]
                assert set(member_notes["parameters"]) == set(member.parameters)
                assert len(
                    [line for line in member.docstring.splitlines() if line.strip()]
                ) >= 2
                assert render_docstring_details(member.docstring) in page
                assert f"`{member.source}:{member.line}`" in page

    assert export_count == 10


def test_namespace_pages_do_not_publish_private_helpers() -> None:
    for namespace in _NAMESPACE_SOURCES:
        page = next(
            content
            for path, content in build_references().items()
            if path.stem == namespace.rsplit(".", 1)[-1]
        )
        assert "._" not in page
        assert "__getattr__" not in page
        assert "__dir__" not in page
