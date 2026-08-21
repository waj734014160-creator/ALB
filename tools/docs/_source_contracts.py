"""Shared source-contract extraction for generated API documentation."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import tokenize
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class SourceMember:
    """Describe one public member declared directly on a documented class."""

    name: str
    kind: str
    signature: str
    parameters: tuple[str, ...]
    return_annotation: str
    source: str
    line: int
    docstring: str


@dataclass(frozen=True, slots=True)
class SourceSymbol:
    """Describe one exported class or function without importing its module."""

    name: str
    kind: str
    signature: str
    parameters: tuple[str, ...]
    return_annotation: str
    source: str
    line: int
    docstring: str
    fields: tuple[str, ...] = ()
    members: tuple[SourceMember, ...] = ()


def read_python_source(path: Path) -> str:
    """Read one Python source file using its declared PEP 263 encoding.

    ``tokenize.detect_encoding`` accepts ordinary UTF-8 and UTF-8 with a BOM.
    Unsupported legacy encodings are not guessed or silently substituted.
    """

    raw = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    normalized = encoding.lower().replace("_", "-")
    if normalized not in {"utf-8", "utf-8-sig"}:
        raise UnicodeError(f"documentation source must be UTF-8: {path} ({encoding})")
    return raw.decode(encoding)


def parse_lazy_exports(path: Path) -> dict[str, tuple[str, str]]:
    """Read a literal lazy ``_EXPORTS`` registry without importing extras."""

    tree = ast.parse(read_python_source(path), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: Sequence[ast.expr]
            value: ast.expr | None
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            else:
                targets = (node.target,)
                value = node.value
            if not any(
                isinstance(target, ast.Name) and target.id == "_EXPORTS"
                for target in targets
            ):
                continue
            if value is None:
                break
            payload = ast.literal_eval(value)
            if not isinstance(payload, dict):
                break
            exports: dict[str, tuple[str, str]] = {}
            for raw_name, raw_target in payload.items():
                if (
                    not isinstance(raw_name, str)
                    or not isinstance(raw_target, tuple)
                    or len(raw_target) != 2
                    or not all(isinstance(item, str) for item in raw_target)
                ):
                    raise ValueError(f"invalid lazy export in {path}: {raw_name!r}")
                exports[raw_name] = (raw_target[0], raw_target[1])
            return exports
    raise ValueError(f"{path} must define a literal _EXPORTS mapping")


def _annotation(node: ast.expr | None) -> str:
    return "未标注" if node is None else ast.unparse(node)


def _parameter_parts(arguments: ast.arguments, *, omit_receiver: bool) -> list[str]:
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: list[ast.expr | None] = [
        *([None] * (len(positional) - len(arguments.defaults))),
        *arguments.defaults,
    ]
    parts: list[str] = []
    for index, (argument, default) in enumerate(zip(positional, defaults)):
        if omit_receiver and argument.arg in {"self", "cls"}:
            continue
        text = argument.arg
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        parts.append(text)
        if arguments.posonlyargs and index + 1 == len(arguments.posonlyargs):
            parts.append("/")
    if arguments.vararg is not None:
        text = f"*{arguments.vararg.arg}"
        if arguments.vararg.annotation is not None:
            text += f": {ast.unparse(arguments.vararg.annotation)}"
        parts.append(text)
    elif arguments.kwonlyargs:
        parts.append("*")
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
        text = argument.arg
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        parts.append(text)
    if arguments.kwarg is not None:
        text = f"**{arguments.kwarg.arg}"
        if arguments.kwarg.annotation is not None:
            text += f": {ast.unparse(arguments.kwarg.annotation)}"
        parts.append(text)
    return parts


def _parameter_names(arguments: ast.arguments, *, omit_receiver: bool) -> tuple[str, ...]:
    names = [argument.arg for argument in (*arguments.posonlyargs, *arguments.args)]
    if arguments.vararg is not None:
        names.append(arguments.vararg.arg)
    names.extend(argument.arg for argument in arguments.kwonlyargs)
    if arguments.kwarg is not None:
        names.append(arguments.kwarg.arg)
    if omit_receiver:
        names = [name for name in names if name not in {"self", "cls"}]
    return tuple(names)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, *, omit_receiver: bool) -> str:
    parts = _parameter_parts(node.args, omit_receiver=omit_receiver)
    returns = "" if node.returns is None else f" -> {ast.unparse(node.returns)}"
    return f"({', '.join(parts)}){returns}"


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _is_dataclass(node: ast.ClassDef) -> bool:
    return any(_decorator_name(decorator) == "dataclass" for decorator in node.decorator_list)


def _dataclass_fields(node: ast.ClassDef) -> tuple[ast.AnnAssign, ...]:
    if not _is_dataclass(node):
        return ()
    return tuple(
        child
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and not child.target.id.startswith("_")
    )


def _dataclass_signature(fields: Sequence[ast.AnnAssign]) -> str:
    parts: list[str] = []
    for field in fields:
        assert isinstance(field.target, ast.Name)
        text = f"{field.target.id}: {ast.unparse(field.annotation)}"
        if field.value is not None:
            text += f" = {ast.unparse(field.value)}"
        parts.append(text)
    return f"({', '.join(parts)})"


def _module_path(repository_root: Path, module_name: str) -> Path:
    relative = Path(*module_name.split("."))
    module_path = repository_root / relative.with_suffix(".py")
    if module_path.is_file():
        return module_path
    package_path = repository_root / relative / "__init__.py"
    if package_path.is_file():
        return package_path
    raise FileNotFoundError(f"cannot locate exported module {module_name!r}")


def extract_exported_symbol(
    *,
    repository_root: Path,
    export_name: str,
    module_name: str,
    attribute_name: str,
) -> SourceSymbol:
    """Statically extract one lazy-export target and its declared public surface."""

    path = _module_path(repository_root, module_name)
    tree = ast.parse(read_python_source(path), filename=str(path))
    definition = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == attribute_name
        ),
        None,
    )
    if definition is None:
        raise ValueError(f"{module_name}.{attribute_name} has no source definition")
    relative = path.relative_to(repository_root).as_posix()
    docstring = ast.get_docstring(definition, clean=True) or ""
    if isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return SourceSymbol(
            name=export_name,
            kind="function",
            signature=_function_signature(definition, omit_receiver=False),
            parameters=_parameter_names(definition.args, omit_receiver=False),
            return_annotation=_annotation(definition.returns),
            source=relative,
            line=definition.lineno,
            docstring=docstring,
        )

    fields = _dataclass_fields(definition)
    initializer = next(
        (
            child
            for child in definition.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name == "__init__"
        ),
        None,
    )
    if initializer is not None:
        signature = _function_signature(initializer, omit_receiver=True)
        parameters = _parameter_names(initializer.args, omit_receiver=True)
    else:
        signature = _dataclass_signature(fields)
        parameters = tuple(
            field.target.id
            for field in fields
            if isinstance(field.target, ast.Name)
        )
    members: list[SourceMember] = []
    for child in definition.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if child.name.startswith("_"):
            continue
        decorators = {_decorator_name(item) for item in child.decorator_list}
        kind = "property" if "property" in decorators else "method"
        members.append(
            SourceMember(
                name=child.name,
                kind=kind,
                signature=_function_signature(child, omit_receiver=True),
                parameters=_parameter_names(child.args, omit_receiver=True),
                return_annotation=_annotation(child.returns),
                source=relative,
                line=child.lineno,
                docstring=ast.get_docstring(child, clean=True) or "",
            )
        )
    return SourceSymbol(
        name=export_name,
        kind="class",
        signature=signature,
        parameters=parameters,
        return_annotation=export_name,
        source=relative,
        line=definition.lineno,
        docstring=docstring,
        fields=tuple(
            field.target.id
            for field in fields
            if isinstance(field.target, ast.Name)
        ),
        members=tuple(members),
    )


def contract_digest(payload: Mapping[str, Any]) -> str:
    """Return a short deterministic digest for a JSON-compatible surface."""

    import json

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:16]


def render_docstring_details(docstring: str, *, indent: str = "") -> str:
    """Render an exact English source docstring as a Material details block."""

    if not docstring.strip():
        raise ValueError("source docstring must not be empty")
    lines = [
        f'{indent}??? note "源码 docstring（英文原文）"',
        f"{indent}    ```text",
    ]
    lines.extend(
        f"{indent}    {line}" if line else ""
        for line in docstring.splitlines()
    )
    lines.append(f"{indent}    ```")
    return "\n".join(lines)
