"""Integration tests for the built public documentation site."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def site_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the public site in an isolated directory."""

    output_path = tmp_path_factory.mktemp("public-site")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--site-dir",
            str(output_path),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    return output_path


def test_public_site_build_contains_primary_user_routes(site_root: Path) -> None:
    expected = (
        "index.html",
        "site/getting-started/installation/index.html",
        "site/getting-started/first-bearing/index.html",
        "api/public_api_reference/index.html",
        "api/bearing_config_reference/index.html",
        "api/simulation_config_reference/index.html",
        "api/namespaces/control/index.html",
        "api/namespaces/dynamics/index.html",
        "api/namespaces/surrogate/index.html",
        "api/examples/templates/simulation_ross_excel.json5",
        "api/examples/templates/surrogate_bearing.json5",
    )

    assert all((site_root / path).is_file() for path in expected)
    home = (site_root / "index.html").read_text(encoding="utf-8")
    assert "BearingConfig" in home
    assert "BearingResult" in home
    assert "bearing-lifecycle.svg" in home
    assert 'href="https://waj734014160-creator.github.io/ALB/"' in home

    api_reference = (
        site_root / "api/public_api_reference/index.html"
    ).read_text(encoding="utf-8")
    assert (
        'href="https://waj734014160-creator.github.io/ALB/'
        'api/public_api_reference/"' in api_reference
    )
    assert "源码 docstring（英文原文）" in api_reference
    assert "Bearing.calculate" in api_reference
    assert "输出：" in api_reference

    simulation_reference = (
        site_root / "api/simulation_config_reference/index.html"
    ).read_text(encoding="utf-8")
    assert "ross_excel" in simulation_reference
    assert "steps + 1" in simulation_reference
    assert "disk_stream" in simulation_reference

    for namespace, marker in {
        "control": "ControllerBlock",
        "dynamics": "RossRotor",
        "surrogate": "load_albnn_package",
    }.items():
        page = (site_root / f"api/namespaces/{namespace}/index.html").read_text(
            encoding="utf-8"
        )
        assert marker in page
        assert "源码 docstring（英文原文）" in page
        assert "输入：" in page
        assert "输出：" in page


def test_public_site_excludes_machine_evidence(site_root: Path) -> None:
    json_paths = {
        path.relative_to(site_root).as_posix() for path in site_root.rglob("*.json")
    }

    assert json_paths == {"search/search_index.json"}


def test_public_site_contains_no_local_absolute_paths(site_root: Path) -> None:
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in site_root.rglob("*.html")
    )
    public_text += (site_root / "search/search_index.json").read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "C:\\Users\\",
        "C:/Users/",
        "E:\\Anaconda",
        "E:/Anaconda",
        "F:\\BaiduSyncdisk",
        "F:/BaiduSyncdisk",
        "G:\\ALB_PROJECTS",
        "G:/ALB_PROJECTS",
    ):
        assert forbidden not in public_text


def test_public_search_index_excludes_operational_content(site_root: Path) -> None:
    search_index = json.loads(
        (site_root / "search/search_index.json").read_text(encoding="utf-8")
    )
    documents = search_index["docs"]
    locations = {document["location"] for document in documents}
    searchable_text = "\n".join(
        f"{document.get('title', '')}\n{document.get('text', '')}"
        for document in documents
    )

    forbidden_locations = (
        "current_state/",
        "daily_summary_log/",
        "daily_maintenance/",
        "remote_workstation_connection/",
        "run_index/",
        "audits/",
    )
    assert not any(
        location.startswith(forbidden_locations) for location in locations
    )
    assert "远程工作站连接与操作手册" not in searchable_text
    assert "ALB_MAIN 当前状态" not in searchable_text
    assert "每日总结记录" not in searchable_text


def test_public_search_index_supports_chinese_and_api_terms(site_root: Path) -> None:
    search_index = json.loads(
        (site_root / "search/search_index.json").read_text(encoding="utf-8")
    )
    searchable_text = "\n".join(
        f"{document.get('title', '')}\n{document.get('text', '')}"
        for document in search_index["docs"]
    )

    assert "第一个轴承计算" in searchable_text
    assert "BearingConfig" in searchable_text
    assert "dynamic_coefficients" in searchable_text
    assert "仿真配置参考" in searchable_text
    assert "源码 docstring（英文原文）" in searchable_text
    assert "disk_stream" in searchable_text
