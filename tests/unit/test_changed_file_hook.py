from __future__ import annotations

import io
import json
from pathlib import Path
import sys

import pytest

from tools.hooks import check_changed_file


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".py", "value: int = 1\n"),
        (".json", '{"value": 1}\n'),
        (".json5", "{value: 1,}\n"),
        (".toml", 'value = 1\n'),
        (".ipynb", '{"cells": [], "metadata": {}}\n'),
        (".md", "# UTF-8 中文文档\n"),
    ],
)
def test_validate_file_accepts_supported_text(
    tmp_path: Path,
    suffix: str,
    content: str,
) -> None:
    path = tmp_path / f"valid{suffix}"
    path.write_text(content, encoding="utf-8")

    assert check_changed_file.validate_file(path) == []


@pytest.mark.parametrize(
    ("suffix", "content", "expected"),
    [
        (".py", "if True print('broken')\n", "invalid py syntax"),
        (".json", '{"value": }\n', "invalid json syntax"),
        (".json5", "{value: [}\n", "invalid json5 syntax"),
        (".toml", "value = [\n", "invalid toml syntax"),
    ],
)
def test_validate_file_reports_syntax_errors(
    tmp_path: Path,
    suffix: str,
    content: str,
    expected: str,
) -> None:
    path = tmp_path / f"invalid{suffix}"
    path.write_text(content, encoding="utf-8")

    errors = check_changed_file.validate_file(path)

    assert errors
    assert expected in errors[0]


def test_validate_file_reports_non_utf8_text(tmp_path: Path) -> None:
    path = tmp_path / "legacy.md"
    path.write_bytes("中文".encode("gbk"))

    assert "not valid UTF-8" in check_changed_file.validate_file(path)[0]


def test_validate_file_reports_mojibake(tmp_path: Path) -> None:
    path = tmp_path / "damaged.md"
    path.write_text("damaged: �\n", encoding="utf-8")

    assert "possible mojibake" in check_changed_file.validate_file(path)[0]


def test_main_emits_post_tool_block_for_invalid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")
    hook_input = {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(hook_input)))

    assert check_changed_file.main() == 0

    output = json.loads(capsys.readouterr().out)
    assert output["decision"] == "block"
    assert str(path) in output["reason"]
    assert "invalid py syntax" in output["reason"]


def test_main_is_silent_for_valid_notebook_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "valid.ipynb"
    path.write_text('{"cells": [], "metadata": {}}\n', encoding="utf-8")
    hook_input = {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": str(path)},
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(hook_input)))

    assert check_changed_file.main() == 0
    assert capsys.readouterr().out == ""
