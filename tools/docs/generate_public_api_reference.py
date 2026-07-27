"""Generate and validate the ALB root public API reference."""

from __future__ import annotations

import argparse
import ast
import dataclasses
import enum
import hashlib
import inspect
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import ALB  # noqa: E402


NOTES_PATH = REPOSITORY_ROOT / "docs" / "api" / "public_api_docs.json"
OUTPUT_PATH = REPOSITORY_ROOT / "docs" / "api" / "public_api_reference.md"

_KIND_LABELS = {
    "class": "类",
    "constant": "常量",
    "enum": "枚举",
    "exception": "异常",
    "function": "函数",
}


def _kind(value: object) -> str:
    if inspect.isfunction(value):
        return "function"
    if inspect.isclass(value) and issubclass(value, enum.Enum):
        return "enum"
    if inspect.isclass(value) and issubclass(value, BaseException):
        return "exception"
    if inspect.isclass(value):
        return "class"
    return "constant"


def _annotation_text(annotation: object) -> str:
    if annotation is inspect.Signature.empty:
        return "未标注"
    if isinstance(annotation, str):
        return annotation
    return inspect.formatannotation(annotation)


def _default_text(default: object) -> str:
    if default is inspect.Signature.empty:
        return "-"
    return repr(default)


def _signature(value: object, *, omit_receiver: bool = False) -> inspect.Signature:
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        if inspect.isclass(value) and issubclass(value, BaseException):
            signature = inspect.Signature(
                parameters=(
                    inspect.Parameter(
                        "args",
                        inspect.Parameter.VAR_POSITIONAL,
                        annotation=object,
                    ),
                )
            )
        else:
            return inspect.Signature()
    if not omit_receiver:
        return signature
    parameters = tuple(
        parameter
        for parameter in signature.parameters.values()
        if parameter.name not in {"self", "cls"}
    )
    return signature.replace(parameters=parameters)


def _parameter_names(signature: inspect.Signature) -> tuple[str, ...]:
    return tuple(
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.name not in {"self", "cls"}
    )


def _public_members(value: type[Any]) -> dict[str, object]:
    members: dict[str, object] = {}
    for name, member in value.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(member, property) or inspect.isfunction(member):
            members[name] = member
    return members


def _source_location(value: object) -> tuple[str, int | None]:
    try:
        path = Path(inspect.getsourcefile(value) or "").resolve()
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    except (OSError, TypeError, ValueError):
        return "-", None
    try:
        _, line = inspect.getsourcelines(value)
    except (OSError, TypeError):
        line = None
    return relative, line


def _surface() -> dict[str, dict[str, Any]]:
    surface: dict[str, dict[str, Any]] = {}
    for name in ALB.__all__:
        value = getattr(ALB, name)
        kind = _kind(value)
        item: dict[str, Any] = {
            "kind": kind,
            "signature": str(_signature(value)),
            "source": _source_location(value),
        }
        if kind != "constant":
            item["docstring"] = inspect.getdoc(value) or ""
        if inspect.isclass(value):
            members: dict[str, dict[str, Any]] = {}
            for member_name, member in _public_members(value).items():
                target = member.fget if isinstance(member, property) else member
                assert target is not None
                members[member_name] = {
                    "kind": "property" if isinstance(member, property) else "method",
                    "signature": str(_signature(target, omit_receiver=True)),
                    "source": _source_location(target),
                    "docstring": inspect.getdoc(target) or "",
                }
            item["members"] = members
            if dataclasses.is_dataclass(value):
                item["fields"] = [
                    field.name for field in dataclasses.fields(value)
                ]
            if issubclass(value, enum.Enum):
                item["enum_values"] = {
                    member.name: member.value for member in value
                }
        surface[name] = item
    return surface


def _load_notes(path: Path = NOTES_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("public API documentation metadata must be an object")
    return payload


def _validate_examples(examples: Mapping[str, Any]) -> None:
    for example_id, raw_example in examples.items():
        if not isinstance(raw_example, Mapping):
            raise ValueError(f"example {example_id!r} must be an object")
        title = raw_example.get("title")
        code = raw_example.get("code")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"example {example_id!r} needs a title")
        if not isinstance(code, str) or not code.strip():
            raise ValueError(f"example {example_id!r} needs code")
        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise ValueError(
                f"example {example_id!r} is not valid Python: {exc}"
            ) from exc


def _validate_parameter_notes(
    *,
    owner: str,
    signature: inspect.Signature,
    notes: Mapping[str, Any],
) -> None:
    expected = set(_parameter_names(signature))
    actual_raw = notes.get("parameters", {})
    if not isinstance(actual_raw, Mapping):
        raise ValueError(f"{owner} parameters must be an object")
    actual = set(actual_raw)
    if actual != expected:
        missing = sorted(expected - actual)
        stale = sorted(actual - expected)
        raise ValueError(
            f"{owner} parameter documentation mismatch; "
            f"missing={missing}, stale={stale}"
        )
    for name, description in actual_raw.items():
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{owner}.{name} needs a parameter description")


def _validate_item_notes(
    *,
    owner: str,
    value: object,
    notes: Mapping[str, Any],
    example_ids: set[str],
    require_examples: bool,
    omit_receiver: bool = False,
) -> None:
    for key in ("summary", "returns"):
        text = notes.get(key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{owner} needs nonempty {key!r} metadata")
    _validate_parameter_notes(
        owner=owner,
        signature=_signature(value, omit_receiver=omit_receiver),
        notes=notes,
    )
    if require_examples:
        raw_examples = notes.get("examples")
        if not isinstance(raw_examples, Sequence) or isinstance(
            raw_examples,
            (str, bytes),
        ):
            raise ValueError(f"{owner} examples must be a list")
        if not raw_examples:
            raise ValueError(f"{owner} needs at least one example")
        unknown = set(raw_examples) - example_ids
        if unknown:
            raise ValueError(
                f"{owner} references unknown examples: {sorted(unknown)}"
            )


def _validate_notes(
    notes: Mapping[str, Any],
    surface: Mapping[str, Mapping[str, Any]],
) -> None:
    if notes.get("schema_version") != 1:
        raise ValueError("public API documentation schema_version must be 1")
    examples = notes.get("examples")
    symbols = notes.get("symbols")
    if not isinstance(examples, Mapping):
        raise ValueError("public API documentation examples must be an object")
    if not isinstance(symbols, Mapping):
        raise ValueError("public API documentation symbols must be an object")
    _validate_examples(examples)
    expected_symbols = set(surface)
    actual_symbols = set(symbols)
    if actual_symbols != expected_symbols:
        raise ValueError(
            "ALB.__all__ documentation mismatch; "
            f"missing={sorted(expected_symbols - actual_symbols)}, "
            f"stale={sorted(actual_symbols - expected_symbols)}"
        )
    example_ids = set(examples)
    used_example_ids: set[str] = set()
    for name in ALB.__all__:
        value = getattr(ALB, name)
        kind = _kind(value)
        if kind != "constant" and not str(surface[name]["docstring"]).strip():
            raise ValueError(f"{name} needs a public source docstring")
        raw_symbol_notes = symbols[name]
        if not isinstance(raw_symbol_notes, Mapping):
            raise ValueError(f"{name} metadata must be an object")
        if kind in {"constant", "enum"}:
            for key in ("summary", "returns"):
                text = raw_symbol_notes.get(key)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(
                        f"{name} needs nonempty {key!r} metadata"
                    )
            raw_examples = raw_symbol_notes.get("examples")
            if not isinstance(raw_examples, Sequence) or isinstance(
                raw_examples,
                (str, bytes),
            ):
                raise ValueError(f"{name} examples must be a list")
            if not raw_examples:
                raise ValueError(f"{name} needs at least one example")
            unknown = set(raw_examples) - example_ids
            if unknown:
                raise ValueError(
                    f"{name} references unknown examples: {sorted(unknown)}"
                )
            used_example_ids.update(raw_examples)
        else:
            _validate_item_notes(
                owner=name,
                value=value,
                notes=raw_symbol_notes,
                example_ids=example_ids,
                require_examples=True,
            )
            used_example_ids.update(raw_symbol_notes["examples"])
        if not inspect.isclass(value):
            continue
        public_members = _public_members(value)
        for member_name in public_members:
            if not str(
                surface[name]["members"][member_name]["docstring"]
            ).strip():
                raise ValueError(
                    f"{name}.{member_name} needs a public source docstring"
                )
        raw_member_notes = raw_symbol_notes.get("members", {})
        if not isinstance(raw_member_notes, Mapping):
            raise ValueError(f"{name} members metadata must be an object")
        if set(raw_member_notes) != set(public_members):
            raise ValueError(
                f"{name} public member documentation mismatch; "
                f"missing={sorted(set(public_members) - set(raw_member_notes))}, "
                f"stale={sorted(set(raw_member_notes) - set(public_members))}"
            )
        for member_name, member in public_members.items():
            raw_notes = raw_member_notes[member_name]
            if not isinstance(raw_notes, Mapping):
                raise ValueError(
                    f"{name}.{member_name} metadata must be an object"
                )
            target = member.fget if isinstance(member, property) else member
            assert target is not None
            _validate_item_notes(
                owner=f"{name}.{member_name}",
                value=target,
                notes=raw_notes,
                example_ids=example_ids,
                require_examples=False,
                omit_receiver=True,
            )
    if used_example_ids != example_ids:
        raise ValueError(
            "public API example metadata mismatch; "
            f"unused={sorted(example_ids - used_example_ids)}"
        )


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        escaped = [cell.replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def _render_parameters(
    signature: inspect.Signature,
    notes: Mapping[str, Any],
) -> str:
    descriptions = notes["parameters"]
    rows: list[list[str]] = []
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        required = parameter.default is inspect.Signature.empty
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            calling = "可变位置参数"
        elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
            calling = "可变关键字参数"
        elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            calling = "仅关键字"
        elif parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            calling = "仅位置"
        else:
            calling = "位置或关键字"
        rows.append(
            [
                f"`{parameter.name}`",
                f"`{_annotation_text(parameter.annotation)}`",
                "是" if required else "否",
                f"`{_default_text(parameter.default)}`",
                calling,
                str(descriptions[parameter.name]),
            ]
        )
    if not rows:
        return "无。"
    return _markdown_table(
        ("名称", "类型", "必填", "默认值", "调用方式", "说明"),
        rows,
    )


def _render_raises(notes: Mapping[str, Any]) -> str:
    raw_raises = notes.get("raises", [])
    if not raw_raises:
        return ""
    rows = [
        [f"`{item['type']}`", str(item["when"])]
        for item in raw_raises
    ]
    return "\n\n可能异常：\n\n" + _markdown_table(("类型", "触发条件"), rows)


def _render_dataclass_fields(
    value: type[Any],
    notes: Mapping[str, Any],
) -> str:
    rows: list[list[str]] = []
    descriptions = notes["parameters"]
    for field in dataclasses.fields(value):
        if field.default is not dataclasses.MISSING:
            default = repr(field.default)
        elif field.default_factory is not dataclasses.MISSING:
            default = "<factory>"
        else:
            default = "-"
        rows.append(
            [
                f"`{field.name}`",
                f"`{_annotation_text(field.type)}`",
                f"`{default}`",
                str(descriptions[field.name]),
            ]
        )
    return _markdown_table(("字段", "类型", "默认值", "说明"), rows)


def _render_example_links(
    example_ids: Sequence[str],
    examples: Mapping[str, Mapping[str, str]],
) -> str:
    links = [
        f"[{examples[example_id]['title']}](#example-{example_id})"
        for example_id in example_ids
    ]
    return "、".join(links)


def _render_callable(
    *,
    owner: str,
    value: object,
    notes: Mapping[str, Any],
    examples: Mapping[str, Mapping[str, str]],
    heading_level: int,
    omit_receiver: bool = False,
    show_examples: bool = False,
) -> str:
    signature = _signature(value, omit_receiver=omit_receiver)
    hashes = "#" * heading_level
    lines = [
        f"{hashes} `{owner}{signature}`",
        "",
        str(notes["summary"]),
        "",
        "输入：",
        "",
        _render_parameters(signature, notes),
        "",
        f"输出：`{owner if inspect.isclass(value) else _annotation_text(signature.return_annotation)}`。"
        f"{notes['returns']}",
    ]
    raises = _render_raises(notes)
    if raises:
        lines.append(raises)
    if show_examples:
        lines.extend(
            [
                "",
                "示例："
                + _render_example_links(notes["examples"], examples)
                + "。",
            ]
        )
    return "\n".join(lines)


def _render_property(
    *,
    owner: str,
    value: property,
    notes: Mapping[str, Any],
) -> str:
    assert value.fget is not None
    signature = _signature(value.fget, omit_receiver=True)
    lines = [
        f"#### `{owner}`",
        "",
        str(notes["summary"]),
        "",
        f"输出：`{_annotation_text(signature.return_annotation)}`。"
        f"{notes['returns']}",
    ]
    raises = _render_raises(notes)
    if raises:
        lines.append(raises)
    return "\n".join(lines)


def _render_symbol(
    *,
    name: str,
    notes: Mapping[str, Any],
    examples: Mapping[str, Mapping[str, str]],
) -> str:
    value = getattr(ALB, name)
    kind = _kind(value)
    source, line = _source_location(value)
    source_text = source if line is None else f"{source}:{line}"
    if kind == "constant":
        return "\n".join(
            [
                f"### `{name}`",
                "",
                str(notes["summary"]),
                "",
                f"- 当前值：`{value}`",
                f"- 输出：`{type(value).__name__}`。{notes['returns']}",
                f"- 源码：`{source_text}`",
                "- 示例："
                + _render_example_links(notes["examples"], examples)
                + "。",
            ]
        )
    if kind == "enum":
        members = [[f"`{member.name}`", f"`{member.value}`"] for member in value]
        return "\n".join(
            [
                f"### `{name}`",
                "",
                str(notes["summary"]),
                "",
                f"- 输出：`{name}`。{notes['returns']}",
                f"- 源码：`{source_text}`",
                "",
                "枚举值：",
                "",
                _markdown_table(("名称", "值"), members),
                "",
                "示例："
                + _render_example_links(notes["examples"], examples)
                + "。",
            ]
        )
    lines = [
        _render_callable(
            owner=f"ALB.{name}",
            value=value,
            notes=notes,
            examples=examples,
            heading_level=3,
            show_examples=True,
        ),
        "",
        f"源码：`{source_text}`。",
    ]
    if inspect.isclass(value):
        if dataclasses.is_dataclass(value):
            lines.extend(
                [
                    "",
                    "公开数据字段：",
                    "",
                    _render_dataclass_fields(value, notes),
                ]
            )
        members = _public_members(value)
        if members:
            lines.extend(["", "公开成员："])
        for member_name, member in members.items():
            member_notes = notes["members"][member_name]
            lines.append("")
            if isinstance(member, property):
                lines.append(
                    _render_property(
                        owner=f"{name}.{member_name}",
                        value=member,
                        notes=member_notes,
                    )
                )
            else:
                lines.append(
                    _render_callable(
                        owner=f"{name}.{member_name}",
                        value=member,
                        notes=member_notes,
                        examples=examples,
                        heading_level=4,
                        omit_receiver=True,
                    )
                )
    return "\n".join(lines)


def build_reference(notes: Mapping[str, Any] | None = None) -> str:
    """Build the deterministic Markdown public API reference."""

    resolved_notes = _load_notes() if notes is None else dict(notes)
    surface = _surface()
    _validate_notes(resolved_notes, surface)
    digest = hashlib.sha256(
        json.dumps(
            surface,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    examples = resolved_notes["examples"]
    symbols = resolved_notes["symbols"]
    rows: list[list[str]] = []
    for name in ALB.__all__:
        item = surface[name]
        source, line = item["source"]
        source_text = source if line is None else f"{source}:{line}"
        rows.append(
            [
                f"`{name}`",
                _KIND_LABELS[item["kind"]],
                str(symbols[name]["summary"]),
                f"`{source_text}`",
            ]
        )
    lines = [
        "# ALB 公开 API 自动参考",
        "",
        "## 文档角色",
        "",
        "- 角色：由源码与语义元数据生成的稳定公开 API 参考。",
        "- 目的：展示 `ALB` 根命名空间中类、函数、枚举、异常和常量的输入、输出、功能与示例。",
        "- 允许更新：只能通过 `tools/docs/generate_public_api_reference.py` 根据当前源码和元数据重新生成。",
        "- 禁止更新：手工修改生成正文、记录实时运行状态或描述未导出的内部实现。",
        "- 更新时机：`ALB.__all__`、公开签名、公开成员、中文语义说明或示例变化时。",
        "- 事实来源：`ALB.__all__`、运行时签名、源码 docstring 和 `docs/api/public_api_docs.json`。",
        "",
        "<!-- This file is generated. Do not edit it directly. -->",
        "",
        f"- 包版本：`{ALB.__version__}`",
        f"- 公开符号数：`{len(ALB.__all__)}`",
        f"- 接口表面摘要：`sha256:{digest}`",
        "- 重新生成：`E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py`",
        "- 一致性检查：`E:/Anaconda2023/envs/ALB/python.exe tools/docs/generate_public_api_reference.py --check`",
        "",
        "本文只覆盖普通用户应依赖的 `ALB` 根公开接口。领域实现命名空间用于高级开发，",
        "不应绕过 facade 直接拼装普通计算流程。",
        "",
        "## 总览",
        "",
        _markdown_table(("名称", "类别", "功能", "源码"), rows),
        "",
        "## 示例库",
    ]
    for example_id, example in examples.items():
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
    groups = (
        ("主要对象与结果", {"class", "enum"}),
        ("构建与加载函数", {"function"}),
        ("稳定异常", {"exception"}),
        ("包元数据", {"constant"}),
    )
    for title, kinds in groups:
        selected = [name for name in ALB.__all__ if surface[name]["kind"] in kinds]
        if not selected:
            continue
        lines.extend(["", f"## {title}"])
        for name in selected:
            lines.extend(
                [
                    "",
                    _render_symbol(
                        name=name,
                        notes=symbols[name],
                        examples=examples,
                    ),
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or check the ALB root public API reference."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the generated reference is not current.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the command-line generator or freshness check."""

    args = _parse_args()
    reference = build_reference()
    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"missing generated API reference: {OUTPUT_PATH}")
            return 1
        current = OUTPUT_PATH.read_text(encoding="utf-8")
        if current != reference:
            print(
                "generated API reference is stale; run "
                "tools/docs/generate_public_api_reference.py"
            )
            return 1
        print(
            f"public API reference is current: {len(ALB.__all__)} symbols"
        )
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(reference, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_PATH} ({len(ALB.__all__)} symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
