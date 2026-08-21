"""Generate detailed advanced-namespace API reference pages."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.docs._source_contracts import (  # noqa: E402
    SourceMember,
    SourceSymbol,
    contract_digest,
    extract_exported_symbol,
    parse_lazy_exports,
    render_docstring_details,
)


METADATA_PATH = REPOSITORY_ROOT / "docs/api/namespace_reference_docs.json"
OUTPUT_ROOT = REPOSITORY_ROOT / "docs/api/namespaces"

_NAMESPACE_SOURCES = {
    "ALB.control": REPOSITORY_ROOT / "ALB/control/__init__.py",
    "ALB.dynamics": REPOSITORY_ROOT / "ALB/dynamics/__init__.py",
    "ALB.surrogate": REPOSITORY_ROOT / "ALB/surrogate/__init__.py",
}


def _exports(path: Path) -> tuple[str, ...]:
    """Return names from the literal lazy-export registry."""

    return tuple(parse_lazy_exports(path))


def _surface(namespace: str) -> dict[str, SourceSymbol]:
    exports = parse_lazy_exports(_NAMESPACE_SOURCES[namespace])
    return {
        name: extract_exported_symbol(
            repository_root=REPOSITORY_ROOT,
            export_name=name,
            module_name=module_name,
            attribute_name=attribute_name,
        )
        for name, (module_name, attribute_name) in exports.items()
    }


def _validate_examples(examples: Mapping[str, Any]) -> None:
    for example_id, raw in examples.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"example {example_id!r} must be an object")
        if not isinstance(raw.get("title"), str) or not raw["title"].strip():
            raise ValueError(f"example {example_id!r} needs a title")
        code = raw.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError(f"example {example_id!r} needs code")
        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise ValueError(f"example {example_id!r} is invalid Python: {exc}") from exc


def _validate_raises(owner: str, raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError(f"{owner} raises must be a list")
    for item in raw:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("type"), str)
            or not item["type"].strip()
            or not isinstance(item.get("when"), str)
            or not item["when"].strip()
        ):
            raise ValueError(f"{owner} contains incomplete exception metadata")


def _validate_item(
    *,
    owner: str,
    source: SourceSymbol | SourceMember,
    notes: Mapping[str, Any],
    examples: set[str],
    require_examples: bool,
) -> set[str]:
    for key in ("summary", "returns"):
        value = notes.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{owner} needs nonempty {key!r} metadata")
    parameters = notes.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError(f"{owner} parameters must be an object")
    if set(parameters) != set(source.parameters):
        raise ValueError(
            f"{owner} parameter documentation mismatch; "
            f"missing={sorted(set(source.parameters) - set(parameters))}, "
            f"stale={sorted(set(parameters) - set(source.parameters))}"
        )
    if any(not isinstance(value, str) or not value.strip() for value in parameters.values()):
        raise ValueError(f"{owner} has an empty parameter description")
    if not source.docstring.strip():
        raise ValueError(f"{owner} needs a public source docstring")
    if len([line for line in source.docstring.splitlines() if line.strip()]) < 2:
        raise ValueError(f"{owner} needs a detailed public source docstring")
    _validate_raises(owner, notes.get("raises", []))
    raw_examples = notes.get("examples", [])
    if not isinstance(raw_examples, Sequence) or isinstance(raw_examples, (str, bytes)):
        raise ValueError(f"{owner} examples must be a list")
    if require_examples and not raw_examples:
        raise ValueError(f"{owner} needs at least one example")
    unknown = set(raw_examples) - examples
    if unknown:
        raise ValueError(f"{owner} references unknown examples: {sorted(unknown)}")
    return set(raw_examples)


def load_metadata() -> dict[str, Any]:
    """Load metadata and validate it against explicit source exports."""

    payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("namespace metadata schema_version must be 2")
    examples = payload.get("examples")
    namespaces = payload.get("namespaces")
    if not isinstance(examples, Mapping):
        raise ValueError("namespace examples must be an object")
    if not isinstance(namespaces, Mapping) or set(namespaces) != set(_NAMESPACE_SOURCES):
        raise ValueError("namespace metadata must match the curated registry")
    _validate_examples(examples)
    used_examples: set[str] = set()
    for namespace, source_path in _NAMESPACE_SOURCES.items():
        entry = namespaces[namespace]
        if not isinstance(entry, Mapping):
            raise ValueError(f"{namespace} metadata must be an object")
        if not all(entry.get(key) for key in ("title", "extra", "summary")):
            raise ValueError(f"incomplete namespace metadata: {namespace}")
        if entry.get("stability") != "advanced":
            raise ValueError(f"{namespace} must declare advanced stability")
        source_surface = _surface(namespace)
        symbols = entry.get("symbols")
        if not isinstance(symbols, Mapping) or set(symbols) != set(_exports(source_path)):
            raise ValueError(f"{namespace} symbols differ from explicit exports")
        for name, source in source_surface.items():
            notes = symbols[name]
            if not isinstance(notes, Mapping):
                raise ValueError(f"{namespace}.{name} metadata must be an object")
            used_examples.update(
                _validate_item(
                    owner=f"{namespace}.{name}",
                    source=source,
                    notes=notes,
                    examples=set(examples),
                    require_examples=True,
                )
            )
            member_notes = notes.get("members", {})
            if not isinstance(member_notes, Mapping):
                raise ValueError(f"{namespace}.{name} members must be an object")
            actual_members = {member.name: member for member in source.members}
            if set(member_notes) != set(actual_members):
                raise ValueError(
                    f"{namespace}.{name} member documentation mismatch; "
                    f"missing={sorted(set(actual_members) - set(member_notes))}, "
                    f"stale={sorted(set(member_notes) - set(actual_members))}"
                )
            for member_name, member in actual_members.items():
                raw = member_notes[member_name]
                if not isinstance(raw, Mapping):
                    raise ValueError(f"{namespace}.{name}.{member_name} metadata must be an object")
                used_examples.update(
                    _validate_item(
                        owner=f"{namespace}.{name}.{member_name}",
                        source=member,
                        notes=raw,
                        examples=set(examples),
                        require_examples=False,
                    )
                )
    if used_examples != set(examples):
        raise ValueError(f"unused namespace examples: {sorted(set(examples) - used_examples)}")
    return payload


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        escaped = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def _render_parameters(source: SourceSymbol | SourceMember, notes: Mapping[str, Any]) -> str:
    if not source.parameters:
        return "无。"
    return _markdown_table(
        ("名称", "说明"),
        [[f"`{name}`", str(notes["parameters"][name])] for name in source.parameters],
    )


def _render_raises(notes: Mapping[str, Any]) -> str:
    raw = notes.get("raises", [])
    if not raw:
        return ""
    return "\n\n可能异常：\n\n" + _markdown_table(
        ("类型", "触发条件"),
        [[f"`{item['type']}`", str(item["when"])] for item in raw],
    )


def _render_item(
    *,
    owner: str,
    source: SourceSymbol | SourceMember,
    notes: Mapping[str, Any],
    heading_level: int,
    example_metadata: Mapping[str, Mapping[str, str]],
    show_examples: bool,
) -> str:
    hashes = "#" * heading_level
    source_text = f"{source.source}:{source.line}"
    lines = [
        f"{hashes} `{owner}{source.signature}`",
        "",
        str(notes["summary"]),
        "",
        f"- 类别：`{source.kind}`",
        f"- 源码：`{source_text}`",
        f"- 返回标注：`{source.return_annotation}`",
        "",
        "输入：",
        "",
        _render_parameters(source, notes),
        "",
        f"输出：{notes['returns']}",
    ]
    raises = _render_raises(notes)
    if raises:
        lines.append(raises)
    if show_examples:
        links = "、".join(
            f"[{example_metadata[example_id]['title']}](#example-{example_id})"
            for example_id in notes.get("examples", [])
        )
        lines.extend(["", f"示例：{links}。"])
    lines.extend(["", render_docstring_details(source.docstring)])
    return "\n".join(lines)


def _surface_payload(surface: Mapping[str, SourceSymbol]) -> dict[str, Any]:
    return {
        name: {
            "kind": symbol.kind,
            "signature": symbol.signature,
            "parameters": symbol.parameters,
            "return": symbol.return_annotation,
            "source": (symbol.source, symbol.line),
            "docstring": symbol.docstring,
            "fields": symbol.fields,
            "members": {
                member.name: {
                    "kind": member.kind,
                    "signature": member.signature,
                    "parameters": member.parameters,
                    "return": member.return_annotation,
                    "source": (member.source, member.line),
                    "docstring": member.docstring,
                }
                for member in symbol.members
            },
        }
        for name, symbol in surface.items()
    }


def render_namespace(
    namespace: str,
    entry: Mapping[str, Any],
    examples: Mapping[str, Mapping[str, str]],
) -> str:
    """Render one detailed deterministic namespace reference page."""

    surface = _surface(namespace)
    digest = contract_digest(_surface_payload(surface))
    symbols = entry["symbols"]
    rows = [
        [
            f"`{name}`",
            "类" if source.kind == "class" else "函数",
            str(symbols[name]["summary"]),
            f"`{source.source}:{source.line}`",
        ]
        for name, source in surface.items()
    ]
    lines = [
        f"# `.{namespace.split('.')[-1]}` · {entry['title']}",
        "",
        "<!-- Generated by tools/docs/generate_namespace_reference.py. -->",
        "",
        f"> **高级 API。** {entry['summary']}",
        "",
        f"- 显式导出数：`{len(surface)}`",
        f"- 源码合同摘要：`sha256:{digest}`",
        "- 对应规则：中文语义元数据必须与源码参数、公开成员和英文 docstring 同步通过生成门禁。",
        "",
        "## 安装",
        "",
        "```bash",
        f'python -m pip install "re-alb[{entry["extra"]}]"',
        "```",
        "",
        "## 导入",
        "",
        "```python",
        f"from {namespace} import {', '.join(surface)}",
        "```",
        "",
        "## 显式导出总览",
        "",
        _markdown_table(("符号", "类别", "用途", "源码"), rows),
        "",
        "!!! warning \"高级接口边界\"",
        "    本页只记录 namespace 显式导出的符号及其源码声明的公开成员。实现模块、私有 helper 和其他可导入类型不因此成为稳定用户 API。",
        "",
        "## 示例",
    ]
    example_ids: list[str] = []
    for notes in symbols.values():
        for example_id in notes.get("examples", []):
            if example_id not in example_ids:
                example_ids.append(example_id)
    for example_id in example_ids:
        example = examples[example_id]
        lines.extend(
            [
                "",
                f'<a id="example-{example_id}"></a>',
                f"### {example['title']}",
                "",
                str(example.get("description", "")),
                "",
                "```python",
                str(example["code"]).rstrip(),
                "```",
            ]
        )
    lines.extend(["", "## 详细接口"])
    for name, source in surface.items():
        notes = symbols[name]
        lines.extend(
            [
                "",
                _render_item(
                    owner=f"{namespace}.{name}",
                    source=source,
                    notes=notes,
                    heading_level=3,
                    example_metadata=examples,
                    show_examples=True,
                ),
            ]
        )
        if source.fields:
            lines.extend(
                [
                    "",
                    "公开数据字段：",
                    "",
                    _markdown_table(
                        ("字段", "说明"),
                        [
                            [f"`{field}`", str(notes["parameters"][field])]
                            for field in source.fields
                        ],
                    ),
                ]
            )
        if source.members:
            lines.extend(["", "公开成员："])
        for member in source.members:
            lines.extend(
                [
                    "",
                    _render_item(
                        owner=f"{name}.{member.name}",
                        source=member,
                        notes=notes["members"][member.name],
                        heading_level=4,
                        example_metadata=examples,
                        show_examples=False,
                    ),
                ]
            )
    lines.extend(["", "返回[公开接口边界](../../site/concepts/public-api-policy.md)。", ""])
    return "\n".join(lines)


def build_references() -> dict[Path, str]:
    """Return every expected generated path and content."""

    metadata = load_metadata()
    return {
        OUTPUT_ROOT / f"{namespace.split('.')[-1]}.md": render_namespace(
            namespace,
            entry,
            metadata["examples"],
        )
        for namespace, entry in metadata["namespaces"].items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = build_references()
    if args.check:
        stale = [
            path
            for path, content in expected.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print("stale namespace references: " + ", ".join(map(str, stale)))
            return 1
        print(f"namespace references are current: {len(expected)} pages")
        return 0
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for path, content in expected.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {len(expected)} namespace reference pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
