"""Shared validation and rendering for source-driven configuration references."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ALB.api._config_fields import ConfigField


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOCALIZATION_PATH = REPOSITORY_ROOT / "docs/api/config_reference_docs.json"


def load_localization(
    section: str,
    groups: Mapping[str, Mapping[str, ConfigField]],
) -> Mapping[str, Mapping[str, str]]:
    """Load localized group metadata and require exact source-group coverage."""

    payload = json.loads(LOCALIZATION_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("configuration reference metadata schema_version must be 1")
    localized = payload.get(section)
    if not isinstance(localized, Mapping) or set(localized) != set(groups):
        actual = set(localized) if isinstance(localized, Mapping) else set()
        raise ValueError(
            f"{section} configuration group metadata mismatch; "
            f"missing={sorted(set(groups) - actual)}, "
            f"stale={sorted(actual - set(groups))}"
        )
    for name, notes in localized.items():
        if not isinstance(notes, Mapping):
            raise ValueError(f"{section}.{name} metadata must be an object")
        for key in ("title", "summary"):
            value = notes.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{section}.{name} needs nonempty {key}")
    return localized


def validate_groups(groups: Mapping[str, Mapping[str, ConfigField]]) -> None:
    """Reject incomplete field contracts before rendering documentation."""

    allowed_types = {
        "array[array[number, 2]]",
        "array[array[number]]",
        "array[integer]",
        "array[number, 2]",
        "array[number, 3]",
        "array[number] or null",
        "array[number]",
        "array[object]",
        "array[string or object]",
        "array[string]",
        "boolean or 'half_reynold'",
        "boolean or mapping",
        "boolean or mapping or null",
        "boolean or null",
        "boolean or object or null",
        "boolean",
        "integer or array[integer]",
        "integer or null",
        "integer",
        "number or null",
        "number",
        "object or null",
        "object",
        "string or null",
        "string",
    }
    for group_name, fields in groups.items():
        if not fields:
            raise ValueError(f"configuration group {group_name!r} is empty")
        for field_name, field in fields.items():
            if not isinstance(field, ConfigField):
                raise TypeError(f"{group_name}.{field_name} is not ConfigField")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (
                    field.native_name,
                    field.unit,
                    field.description,
                    field.value_type,
                )
            ):
                raise ValueError(f"incomplete field metadata: {group_name}.{field_name}")
            if field.value_type not in allowed_types:
                raise ValueError(
                    f"unknown value_type for {group_name}.{field_name}: "
                    f"{field.value_type!r}"
                )
            if not isinstance(field.default_description, str):
                raise ValueError(
                    f"default_description must be text: {group_name}.{field_name}"
                )
            if field.required and (field.has_default or field.default_description):
                raise ValueError(
                    f"required field has a default: {group_name}.{field_name}"
                )
            if not field.required and not (
                field.has_default or field.default_description
            ):
                raise ValueError(
                    f"optional field lacks a default: {group_name}.{field_name}"
                )


def _json_compatible(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_compatible(item) for item in value]
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    return value


def format_value(value: Any) -> str:
    """Format one default or choice deterministically as JSON-style text."""

    return json.dumps(
        _json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(", ", ": "),
    )


def field_surface(
    groups: Mapping[str, Mapping[str, ConfigField]],
) -> dict[str, Any]:
    """Return the JSON-compatible source surface used by freshness digests."""

    return {
        group_name: {
            field_name: {
                "native_name": field.native_name,
                "unit": field.unit,
                "description": field.description,
                "applicability": field.applicability,
                "default": (
                    _json_compatible(field.default) if field.has_default else None
                ),
                "has_default": field.has_default,
                "default_description": field.default_description,
                "required": field.required,
                "choices": field.choices,
                "constraint": field.constraint,
                "value_type": field.value_type,
            }
            for field_name, field in fields.items()
        }
        for group_name, fields in groups.items()
    }


def contract_digest(groups: Mapping[str, Mapping[str, ConfigField]]) -> str:
    """Return a short digest that changes with every field-contract value."""

    encoded = json.dumps(
        field_surface(groups),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render a deterministic Markdown table with escaped cells."""

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_group(
    group_name: str,
    fields: Mapping[str, ConfigField],
    notes: Mapping[str, str],
    *,
    heading_level: int = 3,
) -> str:
    """Render one complete bilingual source-contract field table."""

    rows: list[list[str]] = []
    for name, field in fields.items():
        if field.required:
            default = "适用时必填" if field.applicability else "必填"
        elif field.default_description:
            default = field.default_description
        else:
            default = format_value(field.default)
        choices = "-" if not field.choices else format_value(field.choices)
        applicability = "全部" if not field.applicability else ", ".join(field.applicability)
        native_name = (
            "与公开字段同名"
            if field.native_name == "same as public field"
            else f"`{field.native_name}`"
        )
        rows.append(
            [
                f"`{name}`",
                f"`{field.value_type}`",
                f"`{field.unit}`",
                default,
                choices,
                field.constraint or "-",
                applicability,
                native_name,
                field.description,
            ]
        )
    hashes = "#" * heading_level
    return "\n".join(
        [
            f'<a id="config-group-{group_name}"></a>',
            f"{hashes} {notes['title']}",
            "",
            notes["summary"],
            "",
            markdown_table(
                (
                    "字段",
                    "值类型",
                    "单位",
                    "必填/默认值",
                    "可选值",
                    "约束",
                    "适用范围",
                    "原生映射",
                    "源码英文合同",
                ),
                rows,
            ),
        ]
    )
