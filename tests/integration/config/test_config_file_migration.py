"""File-level tests for non-destructive JSON5 config migration."""

import json

import pytest

from ALB.config.migration import migrate_config_file


def test_migration_writes_separate_utf8_document(tmp_path):
    source = tmp_path / "legacy.json5"
    destination = tmp_path / "config-0.2.json"
    source.write_text("{r: 0.04, kp: 0.3, label: '测试'}\n", encoding="utf-8")

    report = migrate_config_file(source, destination)

    assert source.read_text(encoding="utf-8") == "{r: 0.04, kp: 0.3, label: '测试'}\n"
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "schema_version": "0.2.0",
        "film": {"r": 0.04},
        "control": {"kp": 0.3},
        "legacy_unmapped": {"label": "测试"},
    }
    assert report.target_schema == "0.2.0"


def test_migration_refuses_overwrite_by_default(tmp_path):
    source = tmp_path / "legacy.json5"
    destination = tmp_path / "existing.json"
    source.write_text("{}", encoding="utf-8")
    destination.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        migrate_config_file(source, destination)


@pytest.mark.parametrize("encoding", ["gbk", "cp936"])
def test_migration_warns_and_converts_legacy_chinese_encoding(tmp_path, encoding):
    source = tmp_path / f"legacy-{encoding}.json5"
    destination = tmp_path / f"config-{encoding}-0.2.json"
    legacy_text = "{r: 0.04, label: '旧配置'}\n"
    source.write_bytes(legacy_text.encode(encoding))

    with pytest.warns(UnicodeWarning, match="not UTF-8"):
        report = migrate_config_file(source, destination)

    assert source.read_bytes() == legacy_text.encode(encoding)
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "schema_version": "0.2.0",
        "film": {"r": 0.04},
        "legacy_unmapped": {"label": "旧配置"},
    }
    assert report.target_schema == "0.2.0"
