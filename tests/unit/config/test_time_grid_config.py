# -- coding: utf-8 --
import hashlib
import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

from ALB.config import ALBConfig, TimeGridConfig
from ALB.dynamics.orbit import orbitime
from ALB.task import TaskConfigFactory
from ALB.tool import read_json5, read_share


REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_CONFIG = REPO_ROOT / "paper_config"
REFERENCE = REPO_ROOT / "refs" / "task_time_config_reference_v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_time_factory_public_exports():
    from ALB import ResolvedTimeGrid, TaskConfigFactory as PublicFactory
    from ALB import TimeGridConfig as PublicTimeGridConfig

    assert PublicTimeGridConfig is TimeGridConfig
    assert PublicFactory is TaskConfigFactory
    resolved = TimeGridConfig(
        mode="cycle_points", freq=50, cycles=1, points_per_cycle=20
    ).resolve()
    assert ResolvedTimeGrid is type(resolved)


def test_legacy_time_resolution_matches_pre_refactor_reference_exactly():
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    legacy = reference["legacy_inputs"]
    legacy_resolved = TimeGridConfig.from_dict(
        {
            "freq": legacy["freq"],
            "n": legacy["n"],
            "pt": legacy["pt"],
            "dt": legacy["stored_dt"],
        }
    ).resolve()
    assert legacy_resolved.to_dict() == reference["resolved"]

    factory = TaskConfigFactory(PAPER_CONFIG)
    assert factory.resolved_time_grid.to_dict() == reference["resolved"]
    actual_merged = {
        "alb_dt": factory.read_config("alb12.json5")["dt"],
        "alb_freq": factory.read_config("alb12.json5")["freq"],
        "rotor_dt": factory.read_config("rotor.json5")["dt"],
        "rotor_freq": factory.read_config("rotor.json5")["freq"],
    }
    assert actual_merged == reference["merged_contract"]
    assert factory.read_config("alb12.json5")["thermal"]["dt"] == 4e-5
    assert factory.read_config("hb34.json5")["thermal"]["dt"] == 4e-5
    assert factory.read_config("thermal.json5")["dt"] == 4e-5
    alb_config = ALBConfig.from_dict(factory.read_config("alb12.json5"))
    assert alb_config.dt == 4e-5
    assert alb_config.servo_config.dt == 4e-5
    assert alb_config.controller_config.dt == 4e-5
    assert alb_config.controller_config.freq == 50.0
    assert alb_config.thermal_config.dt == 4e-5


def test_cycle_points_resolves_dt_steps_and_end_time():
    resolved = TimeGridConfig(
        mode="cycle_points",
        freq=25,
        cycles=3,
        points_per_cycle=80,
    ).resolve()

    assert resolved.dt == 1.0 / 2000.0
    assert resolved.steps == 240
    assert resolved.end_time == 0.12
    assert resolved.samples_per_revolution == 80.0


def test_fixed_dt_preserves_dt_and_allows_partial_final_revolution():
    resolved = TimeGridConfig(
        mode="fixed_dt",
        freq=50,
        dt=4e-5,
        steps=401,
    ).resolve()
    time_iter = orbitime(mode="fixed_dt", freq=50, dt=4e-5, steps=401)

    assert resolved.points_per_cycle == 500
    assert resolved.cycles == 401 / 500
    assert resolved.steps % resolved.points_per_cycle != 0
    assert time_iter.dt == 4e-5
    assert time_iter.num == 401


@pytest.mark.parametrize(
    "payload, error_type",
    [
        ({"mode": "cycle_points", "freq": 50, "cycles": 1, "points_per_cycle": 20.0}, TypeError),
        ({"mode": "cycle_points", "freq": 50, "cycles": True, "points_per_cycle": 20}, TypeError),
        ({"mode": "cycle_points", "freq": 0, "cycles": 1, "points_per_cycle": 20}, ValueError),
        ({"mode": "cycle_points", "freq": 50, "cycles": 1, "points_per_cycle": 20, "dt": 1e-3}, ValueError),
        ({"mode": "fixed_dt", "freq": 50, "dt": 4.1e-5, "steps": 100}, ValueError),
        ({"mode": "fixed_dt", "freq": 50, "dt": 4e-5, "steps": 100.0}, TypeError),
        ({"freq": 50, "cycles": 2, "points_per_cycle": 20}, ValueError),
        ({"freq": 50, "dt": 4e-5, "steps": 100}, ValueError),
        ({"freq": 50, "n": 2}, ValueError),
        ({"freq": 50, "n": 2, "pt": 20, "steps": 40}, ValueError),
        ({"mode": "cycle_points", "freq": 50, "n": 2, "pt": 20}, ValueError),
    ],
)
def test_time_grid_rejects_ambiguous_or_invalid_inputs(payload, error_type):
    with pytest.raises(error_type):
        TimeGridConfig.from_dict(payload)


def test_task_factory_reads_share_and_time_once():
    from ALB import task as task_module

    original = task_module.read_json5
    paths = []

    def tracked_read(path, **kwargs):
        paths.append(Path(path).name)
        return original(path, **kwargs)

    with mock.patch.object(task_module, "read_json5", side_effect=tracked_read):
        TaskConfigFactory(PAPER_CONFIG)

    assert paths.count("share.json5") == 1
    assert paths.count("time_iter.json5") == 1


def test_bundled_share_contains_only_shared_frequency_for_time_settings():
    share = read_json5(PAPER_CONFIG / "share.json5")
    time_config = read_json5(PAPER_CONFIG / "time_iter.json5")

    assert {"dt", "n", "pt"}.isdisjoint(share)
    assert "dt" not in share.get("thermal", {})
    assert time_config["share_name"] == ["freq"]
    assert time_config["mode"] == "cycle_points"
    assert time_config["cycles"] == 8
    assert time_config["points_per_cycle"] == 500


def test_factory_and_deprecated_recover_never_write_share(tmp_path):
    share = tmp_path / "share.json5"
    time_config = tmp_path / "time_iter.json5"
    shutil.copy2(PAPER_CONFIG / share.name, share)
    shutil.copy2(PAPER_CONFIG / time_config.name, time_config)
    before_hash = _sha256(share)
    before_mtime = share.stat().st_mtime_ns

    TaskConfigFactory(tmp_path)
    with pytest.warns(DeprecationWarning):
        resolved_share = read_share(str(share), recover=True)

    assert resolved_share["dt"] == 4e-5
    assert _sha256(share) == before_hash
    assert share.stat().st_mtime_ns == before_mtime


def test_read_share_supports_legacy_schema_without_time_file(tmp_path):
    share = tmp_path / "share.json5"
    share.write_text("{freq: 40, n: 2, pt: 25, dt: 123.0}\n", encoding="utf-8")

    resolved = read_share(str(share))

    assert resolved["mode"] == "cycle_points"
    assert resolved["dt"] == 0.001
    assert resolved["steps"] == 50
