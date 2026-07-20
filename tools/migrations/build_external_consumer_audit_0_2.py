"""Build the read-only 0.2 migration audit for declared external consumers."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SURROGATE_ROOT = REPOSITORY_ROOT.parent / "SURROGATE_TRAIN"
PAPER_ROOT = Path("F:/BaiduSyncdisk/博士论文/PAPER_WORK")
DEFAULT_JSON = REPOSITORY_ROOT / "docs/migrations/0.2.0_external_consumer_audit.json"
DEFAULT_MARKDOWN = REPOSITORY_ROOT / "docs/migrations/0.2.0_external_consumer_audit.md"

SURROGATE_FILES = [
    ("direct", "run/analysis/check_s0008_dimensional_cross_validation.py"),
    ("direct", "run/analysis/compare_packaged_albnn_force_kc.py"),
    ("direct", "run/analysis/knn_local_oracle_kc.py"),
    ("direct", "run/analysis/knn_validation_oracle_g0.py"),
    ("direct", "run/analysis/retry_s0011_thermal_settings.py"),
    ("direct", "run/jupyter/data_check.ipynb"),
    ("direct", "run/remote/remote_job.py"),
    ("direct", "run/remote/remote_monitor_job.py"),
    ("direct", "run/remote/remote_query_albnn_status.py"),
    ("direct", "run/remote/remote_queue_albnn_activation_sweep.py"),
    ("direct", "run/remote/remote_start_albnn_train.py"),
    ("direct", "run/remote/retry_invalid_adaptive_damp.py"),
    ("context", "run/train/run_acceptance_training_campaign.py"),
    ("context", "run/train/run_local_kc_campaign.py"),
    ("direct", "run/train/train_alb_agent.py"),
    ("direct", "run/train/train_albnn.py"),
    ("direct", "run/train/train_albnn_expert.py"),
    ("direct", "run/train/train_albnn_residual_expert.py"),
    ("context", "run/train/train_thermal_mlp.py"),
    ("context", "run/train/watch_heat_albnn_pipeline.py"),
    ("direct", "task/task_alb_data2.py"),
    ("direct", "task/task_albnn_data.py"),
    ("direct", "task/task_thermal_forces.py"),
]

PAPER_FILES = [
    ("direct", "run/remote/remote_job.py"),
    ("direct", "task/paper_2_3_2/动特性轨迹示意图.py"),
    ("direct", "task/paper_2_4_1/主动供油冷源对油膜温度场的影响.py"),
    ("direct", "task/paper_2_4_1/热流耦合模型下油膜压力温度和黏度分布.py"),
    ("direct", "task/paper_2_4_1/等温模型与热流耦合模型的静特性参数对比.py"),
    ("direct", "task/paper_2_4_2/不同供油孔直径下的静特性.py"),
    ("direct", "task/paper_2_4_2/不同供油孔长度下的静特性.py"),
    ("direct", "task/paper_2_4_2/不同油源压力下的静特性.py"),
    ("direct", "task/paper_2_4_2/不同阀芯面积下的静特性.py"),
    ("direct", "task/paper_2_4_2/不同阀芯面积下的静特性_ALBNN载荷工况重算.py"),
    ("direct", "task/paper_2_5_1/不同微分系数下热效应对动力学系数的影响.py"),
    ("direct", "task/paper_2_5_1/不同微分系数下热效应对动力学系数的影响_无热惯性.py"),
    ("direct", "task/paper_2_5_1/不同比例系数下热效应对动力学系数的影响.py"),
    ("direct", "task/paper_2_5_1/不同比例系数下热效应对动力学系数的影响_无热惯性.py"),
    ("direct", "task/paper_2_5_1/热流耦合对动力学系数的影响.py"),
    ("direct", "task/paper_2_5_1/热流耦合对动态油膜力的影响.py"),
    ("direct", "task/paper_2_5_2/fixed_center_dynamic_runner.py"),
    ("direct", "task/paper_2_5_2/不同油压对动力学系数的影响.py"),
    ("direct", "task/paper_2_5_2/不同节流孔径下的动力学特性.py"),
    ("direct", "task/paper_2_5_2/不同阀芯面积下的动力学特性.py"),
    ("transitive", "task/paper_2_5_2/计算被动工况动力学系数基准.py"),
    ("direct", "task/paper_2_5_3/不同伺服阀固有频率对动力学系数和临界质量的影响.py"),
    ("direct", "task/paper_2_5_3/不同伺服阀阻尼比对动力学系数和临界质量的影响.py"),
    ("direct", "task/paper_2_5_3/伺服阀频响传递链时域数据计算.py"),
    ("direct", "task/paper_2_5_3/工作转速范围伺服阀频响动力系数稳定性重算.py"),
    ("direct", "task/paper_2_5_3/工作转速范围伺服阀频响动力系数稳定性重算_zeta0p7.py"),
    ("transitive", "task/paper_2_5_3/伺服阀固有频率和阻尼比云图_M35_ALBNN重算.py"),
]

MODULE_TARGETS: dict[str, list[str]] = {
    "ALB.alb": ["ALB.systems.alb"],
    "ALB.base": ["ALB.contracts", "ALB.core"],
    "ALB.bearing": ["ALB.physics.bearing"],
    "ALB.config": [
        "ALB.config.control",
        "ALB.config.film",
        "ALB.config.hydraulics",
        "ALB.config.surrogate",
        "ALB.config.system",
        "ALB.config.thermal",
    ],
    "ALB.controller": ["ALB.control"],
    "ALB.film": ["ALB.physics.film"],
    "ALB.nn": [
        "ALB.surrogate.features",
        "ALB.surrogate.inference",
        "ALB.surrogate.networks",
        "ALB.surrogate.scalers",
    ],
    "ALB.nondim": ["ALB.physics.thermal.scales"],
    "ALB.orbit": ["ALB.dynamics.identification", "ALB.dynamics.orbit"],
    "ALB.orifice": ["ALB.physics.hydraulics.orifice"],
    "ALB.remote": ["ALB.infrastructure.remote", "ALB.surrogate.training.remote"],
    "ALB.results": [
        "ALB.contracts.result_tree",
        "ALB.contracts.results",
        "ALB.infrastructure.persistence",
    ],
    "ALB.servovalve": ["ALB.control.valve"],
    "ALB.thermal": ["ALB.config.thermal", "ALB.physics.thermal"],
    "ALB.tool": [
        "ALB.dynamics.identification",
        "ALB.infrastructure.config_io",
        "ALB.workflows.doe",
    ],
    "ALB.train": ["ALB.surrogate.training"],
}

CONTEXT_NOTES = {
    "run/train/run_acceptance_training_campaign.py": "仅固定 ALB Python 环境路径。",
    "run/train/run_local_kc_campaign.py": "仅固定 ALB Python 环境路径。",
    "run/train/train_thermal_mlp.py": "仅在注释中引用旧 ALB.nn.Net 模式。",
    "run/train/watch_heat_albnn_pipeline.py": "仅使用 ALB_PYTHON 环境变量和解释器路径。",
    "task/paper_2_5_2/计算被动工况动力学系数基准.py": (
        "通过 fixed_center_dynamic_runner 传递依赖，需在直接消费者迁移后 smoke。"
    ),
    "task/paper_2_5_3/伺服阀固有频率和阻尼比云图_M35_ALBNN重算.py": (
        "通过 importlib 动态加载直接消费者，需做动态加载 smoke。"
    ),
}


def _source_text(path: Path) -> str:
    if path.suffix.lower() != ".ipynb":
        return path.read_text(encoding="utf-8-sig")
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )


def _alb_imports(source: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "ALB" or alias.name.startswith("ALB."):
                    imports.append({"module": alias.name, "names": []})
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "ALB" or node.module.startswith("ALB."):
                imports.append(
                    {
                        "module": node.module,
                        "names": sorted(alias.name for alias in node.names),
                    }
                )
    return sorted(imports, key=lambda item: (item["module"], item["names"]))


def _targets(imports: Iterable[dict[str, Any]]) -> list[str]:
    targets = set()
    for item in imports:
        module = item["module"]
        for source, replacements in MODULE_TARGETS.items():
            if module == source or module.startswith(f"{source}."):
                targets.update(replacements)
                break
    return sorted(targets)


def _requirements(imports: Iterable[dict[str, Any]]) -> list[str]:
    modules = {item["module"] for item in imports}
    requirements = []
    if any(module == "ALB.nn" or module.startswith("ALB.nn.") for module in modules):
        requirements.append("migrate_model_package_and_scalers")
    if "ALB.results" in modules:
        requirements.append("replace_result_tree_io_with_result_bundle_writer")
    if "ALB.base" in modules:
        requirements.append("replace_legacy_base_with_dto_block_lifecycle")
    if "ALB.tool" in modules:
        requirements.append("semantic_tool_split_not_mechanical_import_replace")
    return requirements


def _audit_group(
    project: str,
    root: Path,
    declared: list[tuple[str, str]],
) -> dict[str, Any]:
    entries = []
    for kind, relative_path in declared:
        path = root / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Declared external consumer is missing: {path}")
        payload = path.read_bytes()
        imports = _alb_imports(_source_text(path))
        if kind == "direct" and not imports:
            raise ValueError(f"Direct consumer has no parseable ALB import: {path}")
        entries.append(
            {
                "kind": kind,
                "path": relative_path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "old_imports": imports,
                "target_namespaces": _targets(imports),
                "migration_requirements": _requirements(imports),
                "context_note": CONTEXT_NOTES.get(relative_path),
                "external_file_modified": False,
            }
        )
    counts = {kind: sum(entry["kind"] == kind for entry in entries) for kind in {item[0] for item in declared}}
    return {
        "project": project,
        "root": root.as_posix(),
        "declared_count": len(declared),
        "counts": counts,
        "entries": entries,
    }


def build_audit() -> dict[str, Any]:
    surrogate = _audit_group("SURROGATE_TRAIN", SURROGATE_ROOT, SURROGATE_FILES)
    paper = _audit_group("PAPER_WORK", PAPER_ROOT, PAPER_FILES)
    if surrogate["declared_count"] != 23 or surrogate["counts"] != {"context": 4, "direct": 19}:
        raise AssertionError("SURROGATE_TRAIN declared snapshot count drifted")
    if paper["declared_count"] != 27 or paper["counts"] != {"direct": 25, "transitive": 2}:
        raise AssertionError("PAPER_WORK declared snapshot count drifted")
    return {
        "schema": "alb.external-consumer-audit.v1",
        "version": "0.2.0",
        "audit_date": "2026-07-21",
        "read_only": True,
        "projects": [surrogate, paper],
        "scope_exclusions": {
            "SURROGATE_TRAIN": "未纳入 declared snapshot 的附录消费者不计入 23 个主清单。",
            "PAPER_WORK": (
                "排除 run/local、notebook、downloads 和 run/remote/payloads 历史冻结副本；"
                "动态加载的 run/local 消费者在 transitive 项附注中保留。"
            ),
        },
        "migration_gates": [
            "旧 JSON5 必须先由 0.2 schema 工具另存，再改用 infrastructure.config_io。",
            "旧 ALB.nn pickle 不属于 0.2 运行时兼容面，必须迁移 model package 和 scaler。",
            "旧 output(calc=True) 或隐式推进调用必须改为 input/evaluate-or-solve/output。",
            "外部文件本轮保持只读；每个项目应在独立迁移提交中修改并 smoke。",
        ],
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# ALB_MAIN 0.2.0 外部调用只读迁移审计",
        "",
        "## 文档角色",
        "",
        "本文记录 0.2.0 破坏式 API 对 declared 外部消费者的只读快照。本文不修改、"
        "不提交 `SURROGATE_TRAIN` 或 `PAPER_WORK` 文件，也不记录它们的实时任务状态。",
        "",
        "## 结论",
        "",
        "- `SURROGATE_TRAIN`：23 个文件，19 个直接调用者，4 个环境或注释上下文文件。",
        "- `PAPER_WORK`：27 个文件，25 个直接调用者，2 个传递或动态加载调用者。",
        "- 每个条目的 SHA-256、旧 import、目标 namespace 和语义迁移门槛见同目录 JSON。",
        "- 所有条目均为 `external_file_modified=false`。",
        "",
        "## 迁移门槛",
        "",
    ]
    lines.extend(f"- {gate}" for gate in audit["migration_gates"])
    for project in audit["projects"]:
        lines.extend(
            [
                "",
                f"## {project['project']} declared snapshot",
                "",
                "| # | 类型 | 文件 | 目标 namespace |",
                "|---:|---|---|---|",
            ]
        )
        for index, entry in enumerate(project["entries"], start=1):
            targets = "<br>".join(f"`{value}`" for value in entry["target_namespaces"])
            if not targets:
                targets = "无直接 import；按上下文 smoke"
            lines.append(
                f"| {index} | {entry['kind']} | `{entry['path']}` | {targets} |"
            )
    lines.extend(
        [
            "",
            "## 已知非机械迁移",
            "",
            "- `ALB.tool` 必须按 DoE、配置 IO、KC/FFT、数组工具分别迁移。",
            "- `ALB.results` 必须改为 `ResultBundle`、`result_snapshot()` 和注入 writer。",
            "- `ALB.base.BaseSimpleModel` 必须改为 DTO 和显式计算生命周期。",
            "- `ALB.nn` 必须先迁移 model package/scaler，不能只替换 import。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    audit = build_audit()
    json_output = args.json_output.resolve()
    markdown_output = args.markdown_output.resolve()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown_output.write_text(_markdown(audit), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
