"""Release-level negative gates for the ALB 0.4 no-legacy contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import json5
import pytest

import ALB


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ALB"


@pytest.mark.parametrize(
    "module_name",
    [
        "ALB.config.legacy",
        "ALB.config.migration",
        "ALB.infrastructure.legacy_signal",
        "ALB.systems.alb.builder",
        "ALB.systems.alb.factories",
        "ALB.systems.alb.runtime_adapter",
        "ALB.control.adapters",
        "ALB.surrogate.migration",
    ],
)
def test_removed_package_modules_are_not_importable(module_name: str) -> None:
    assert importlib.util.find_spec(module_name) is None


def test_root_and_domain_namespaces_do_not_publish_removed_names() -> None:
    forbidden = {
        "Signal",
        "ALBBuilder",
        "RsRotorBearingCouple",
        "RotorBearingCouple",
        "StaticPosition",
        "EllipseTrack",
        "BearingDynamicChar",
        "LegacyBearingAdapter",
        "LegacyControllerAdapter",
        "LegacySignalAdapter",
        "LegacyBearingRuntimeAdapter",
    }
    assert forbidden.isdisjoint(set(ALB.__all__))
    assert forbidden.isdisjoint(dir(ALB))


def test_package_sources_have_zero_signal_and_legacy_adapter_paths() -> None:
    forbidden = (
        "class Signal",
        "lead_loop",
        ".signal",
        "LegacyBearingAdapter",
        "LegacyControllerAdapter",
        "LegacySignalAdapter",
        "LegacyBearingRuntimeAdapter",
        "trust_pickle",
        "trust-pickle",
    )
    hits: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path.relative_to(ROOT)}: {token}")
    assert hits == []


def test_user_facade_has_no_init_or_mutable_component_escape() -> None:
    config = ALB.BearingConfig(
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 0.001,
            "node": 0,
            "film": {
                "circumferential_elements": 5,
                "axial_elements": 3,
                "max_iterations": 2,
            },
            "restrictors": None,
            "thermal": None,
        }
    )
    bearing = ALB.build_bearing(config)
    for name in ("init", "pads", "controller", "valve", "servovalves", "signal"):
        assert not hasattr(bearing, name)


def test_declared_external_consumers_have_zero_removed_api_hits() -> None:
    surrogate = ROOT.parent / "SURROGATE_TRAIN"
    paper = Path("F:/BaiduSyncdisk/博士论文/PAPER_WORK")
    manifest_path = (
        paper / "docs/migrations/alb_0_4_active_source_manifest.json"
    )
    assert surrogate.is_dir()
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = [
        *(surrogate / "task").rglob("*.py"),
        *(surrogate / "run").rglob("*.py"),
        *(paper / item for item in manifest["python_sources"]),
    ]
    forbidden = (
        "ALBBuilder",
        "RsRotorBearingCouple",
        "RotorBearingCouple",
        "StaticPosition",
        "EllipseTrack",
        "orbitime",
        "test_bearing_orbit",
        "read_json5_with_shared",
        "read_shared_config",
        "RE_ALB",
        ".signal",
    )
    hits = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path}: {token}")
    assert hits == []


def test_paper_work_active_configs_use_only_strict_v04_documents() -> None:
    config_root = Path(
        "F:/BaiduSyncdisk/博士论文/PAPER_WORK/task/PAPER/config"
    )
    paths = sorted(config_root.glob("*.json5"))
    assert paths
    removed_keys = {
        "share_name",
        "n",
        "pt",
        "alb",
        "servo",
        "switch",
        "thermal_enabled",
    }

    def walk_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return {
                *(str(key) for key in value),
                *(
                    nested
                    for item in value.values()
                    for nested in walk_keys(item)
                ),
            }
        if isinstance(value, list):
            return {
                nested
                for item in value
                for nested in walk_keys(item)
            }
        return set()

    for path in paths:
        document = json5.loads(path.read_text(encoding="utf-8"))
        assert document["schema_version"] == "0.4.0", path
        assert document["kind"] in {
            "bearing",
            "bearing_profile",
            "simulation",
            "simulation_profile",
        }, path
        assert set(document) <= {
            "schema_version",
            "kind",
            "includes",
            "spec",
        }, path
        assert removed_keys.isdisjoint(walk_keys(document["spec"])), path
        if document["kind"] == "bearing":
            ALB.load_bearing_config(path)
