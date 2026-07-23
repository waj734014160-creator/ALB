"""File-level tests for non-destructive strict configuration migration."""

import json

import pytest

from ALB.config import load_current_config
from ALB.config.migration import migrate_config_file


def test_migration_writes_separate_utf8_current_envelope(tmp_path):
    source = tmp_path / "legacy.json5"
    destination = tmp_path / "config-0.3.json"
    source.write_text("{r: 0.04, kp: 0.3, label: '测试'}\n", encoding="utf-8")

    report = migrate_config_file(source, destination)

    assert source.read_text(encoding="utf-8") == (
        "{r: 0.04, kp: 0.3, label: '测试'}\n"
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.3.0"
    assert payload["unit_system"] == "dimensional"
    assert payload["control_mode"] == "controlled"
    restored = load_current_config(payload)
    assert restored.pad_config.r == 0.04
    assert restored.controller_config.kp == 0.3
    assert report.target_schema == "0.3.0"
    assert report.output_sha256 is not None
    assert len(report.output_sha256) == 64


def test_migration_refuses_source_overwrite_and_existing_destination(tmp_path):
    source = tmp_path / "legacy.json5"
    destination = tmp_path / "existing.json"
    source.write_text("{}", encoding="utf-8")
    destination.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="differ"):
        migrate_config_file(source, source, overwrite=True)
    with pytest.raises(FileExistsError):
        migrate_config_file(source, destination)


@pytest.mark.parametrize("encoding", ["gbk", "cp936"])
def test_migration_warns_and_converts_legacy_chinese_encoding(tmp_path, encoding):
    source = tmp_path / f"legacy-{encoding}.json5"
    destination = tmp_path / f"config-{encoding}-0.3.json"
    legacy_text = "{r: 0.04, label: '旧配置'}\n"
    source.write_bytes(legacy_text.encode(encoding))

    with pytest.warns(UnicodeWarning, match="not UTF-8"):
        report = migrate_config_file(source, destination)

    assert source.read_bytes() == legacy_text.encode(encoding)
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.3.0"
    assert load_current_config(payload).pad_config.r == 0.04
    assert report.target_schema == "0.3.0"


def test_direct_spool_migration_writes_explicit_mode(tmp_path):
    source = tmp_path / "legacy-direct.json5"
    destination = tmp_path / "direct-0.3.json"
    source.write_text("{alb: 'ALBSV', servo: 'static'}", encoding="utf-8")

    report = migrate_config_file(
        source,
        destination,
        unit_system="nondimensional",
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert report.control_mode == "direct_spool"
    assert payload["control_mode"] == "direct_spool"
    restored = load_current_config(payload)
    assert restored.alb == "ALBSV"
    assert restored.controller_config is None
