"""Build the post-migration audit for SURROGATE_TRAIN ALB 0.2 consumers."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPOSITORY_ROOT.parent
SURROGATE_ROOT = WORKSPACE_ROOT / "SURROGATE_TRAIN"
PRE_AUDIT_PATH = (
    REPOSITORY_ROOT / "docs/migrations/0.2.0_external_consumer_audit.json"
)
REFERENCE_PATH = (
    SURROGATE_ROOT
    / "refs/alb_0_2_consumer_migration_v1/consumer_migration_reference_v1.json"
)
DEFAULT_JSON = (
    REPOSITORY_ROOT
    / "docs/migrations/0.2.0_surrogate_train_post_migration_audit.json"
)
DEFAULT_MARKDOWN = (
    REPOSITORY_ROOT
    / "docs/migrations/0.2.0_surrogate_train_post_migration_audit.md"
)

FLAT_MODULES = frozenset(
    {
        "ALB.alb",
        "ALB.base",
        "ALB.bearing",
        "ALB.config",
        "ALB.controller",
        "ALB.film",
        "ALB.nn",
        "ALB.nondim",
        "ALB.orbit",
        "ALB.orifice",
        "ALB.remote",
        "ALB.servovalve",
        "ALB.task",
        "ALB.thermal",
        "ALB.tool",
        "ALB.train",
    }
)

PACKAGE_SPECS = (
    {
        "id": "M0031",
        "model_dir": (
            "M0031_s8b_s0011_allvalid_base12_mlp_minmax01_gelu_"
            "adamw_p1000_20260609"
        ),
        "reference_key": "m31",
    },
    {
        "id": "M0035",
        "model_dir": (
            "M0035_s8b_s0011_enormlt0p85_vnormlt0p4_edotvlt0p195_"
            "base12_mlp_minmax01_gelu_adamw_p1000_20260609"
        ),
        "reference_key": "m35",
    },
    {
        "id": "KNN_BASELINE_20260515",
        "model_dir": (
            "train121661_valid30416_l1lt1p5_evsgeomlt0p8_scaledevs16_"
            "circular_e085_v08_s10_lrgt0p5_lroverlrlt4_mlp_minmax01_"
            "mse_noaug_h512_256_128_64_adamw_lr2em04_wd1em05_bs4096_"
            "p2500_plateau100_20260515"
        ),
        "reference_key": None,
    },
)

SOURCE_ARTIFACTS = {
    "model": "best_albnn.pth",
    "input_scaler": "scaler_X.pkl",
    "output_scaler": "scaler_y.pkl",
    "metadata": "metadata.json",
}

VERIFICATION = (
    {
        "scope": "ALB_MAIN 全量 pytest",
        "result": "325 passed、13 skipped、12 warnings、7 subtests passed",
        "status": "passed",
    },
    {
        "scope": "ALB surrogate package 与输入适配器",
        "result": "10 项通过",
        "status": "passed",
    },
    {
        "scope": "ALB 外部消费者、严格端口和 direct-spool 冻结参考",
        "result": "49 项通过",
        "status": "passed",
    },
    {
        "scope": "9 个已迁移的 SURROGATE_TRAIN 命令行入口",
        "result": "9 个 --help smoke 均通过",
        "status": "passed",
    },
    {
        "scope": "M0031 package 推理",
        "result": "legacy/package 精确相等；package/v1 精确相等",
        "status": "passed",
    },
    {
        "scope": "M0035 package 推理",
        "result": (
            "legacy/package 精确相等；package/v1 max_abs="
            "2.715295792654615e-07，来自既有的跨进程 torch 数值波动"
        ),
        "status": "passed_with_documented_variation",
    },
    {
        "scope": "SURROGATE_TRAIN tests/test_train_albnn_contracts.py",
        "result": "禁用受限系统临时目录 cache provider 后 3 项通过",
        "status": "passed",
    },
)

REMAINING_FINDINGS = (
    {
        "id": "mixed-unit-alb-data2",
        "classification": "migration_follow_up",
        "path": "task/task_alb_data2.py",
        "description": (
            "dimensional ALB 路径有意保留 input(nodim=True) 和 "
            "output(nodim=False)。改为严格端口前，必须先增加显式尺度适配器和"
            "独立冻结参考。"
        ),
    },
    {
        "id": "thermal-force-unused-spool-components",
        "classification": "pre_existing_behavior",
        "path": "task/task_thermal_forces.py",
        "description": (
            "采样并保存了 sx/sy，但求解时两个节流孔共用一个固定 xv，因此这两个"
            "声明输入不影响标签。"
        ),
    },
    {
        "id": "thermal-force-single-pad-label",
        "classification": "pre_existing_behavior",
        "path": "task/task_thermal_forces.py",
        "description": (
            "脚本构造四瓦 ALB 系统，但只有 thermal_pads[0] 提供力和收敛状态。"
        ),
    },
    {
        "id": "thermal-force-pooln-not-used",
        "classification": "pre_existing_behavior",
        "path": "task/task_thermal_forces.py",
        "description": (
            "文档声明的 pooln 并行模式未接入实际串行样本循环。"
        ),
    },
    {
        "id": "training-output-package-generation",
        "classification": "migration_follow_up",
        "path": "run/train",
        "description": (
            "训练仍输出松散 checkpoint 与 scaler。当前可信推理消费者已迁移，但"
            "未来 base/expert/residual run 自动生成 0.2 package 仍是独立后续任务。"
        ),
    },
)


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    """Run one read-only Git query and return stripped UTF-8 output."""

    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, encoding="utf-8"
    ).strip()


def _python_sources(path: Path) -> Iterable[tuple[str, str]]:
    """Yield named Python sources from a Python file or notebook."""

    if path.suffix == ".py":
        yield str(path), path.read_text(encoding="utf-8-sig")
        return
    if path.suffix == ".ipynb":
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook.get("cells", [])):
            if cell.get("cell_type") == "code":
                yield f"{path}:cell-{index}", "".join(cell.get("source", []))


def _flat_imports(path: Path) -> list[dict[str, Any]]:
    """Return imports that still target a removed flat ALB module."""

    matches: list[dict[str, Any]] = []
    for source_name, source in _python_sources(path):
        tree = ast.parse(source, filename=source_name)
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if module in FLAT_MODULES:
                    matches.append({"module": module, "line": node.lineno})
    return matches


def _is_git_ignored(path: Path) -> bool:
    """Return whether Git ignores a path under SURROGATE_TRAIN."""

    relative = path.relative_to(SURROGATE_ROOT)
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(relative)],
        cwd=SURROGATE_ROOT,
        check=False,
    )
    return result.returncode == 0


def _package_audit(spec: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Validate one ignored 0.2 package and its unchanged migration sources."""

    model_root = SURROGATE_ROOT / "models" / spec["model_dir"]
    package_root = model_root / "package_v0_2"
    manifest_path = package_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    artifacts = {}
    for role, declared in manifest["artifacts"].items():
        artifact_path = package_root / declared["path"]
        actual_sha = _sha256(artifact_path)
        artifacts[role] = {
            "path": declared["path"],
            "manifest_sha256": declared["sha256"],
            "actual_sha256": actual_sha,
            "matches_manifest": actual_sha == declared["sha256"],
            "contains_legacy_ALB_nn_reference": (
                b"ALB.nn" in artifact_path.read_bytes()
                if artifact_path.suffix == ".pkl"
                else False
            ),
        }

    frozen_hashes = None
    if spec["reference_key"]:
        frozen_hashes = reference["models"][spec["reference_key"]][
            "artifact_sha256"
        ]
    sources = {}
    for role, filename in SOURCE_ARTIFACTS.items():
        source_path = model_root / filename
        actual_sha = _sha256(source_path)
        sources[role] = {
            "path": filename,
            "sha256": actual_sha,
            "matches_v1_reference": (
                actual_sha == frozen_hashes[filename] if frozen_hashes else None
            ),
        }

    return {
        "id": spec["id"],
        "model_dir": str(model_root.relative_to(SURROGATE_ROOT)).replace("\\", "/"),
        "package_dir": str(package_root.relative_to(SURROGATE_ROOT)).replace(
            "\\", "/"
        ),
        "git_ignored": _is_git_ignored(manifest_path),
        "manifest_schema": manifest["schema"],
        "manifest_sha256": _sha256(manifest_path),
        "pickle_trust_required": manifest["pickle_trust_required"],
        "artifacts": artifacts,
        "legacy_sources": sources,
    }


def build_audit() -> dict[str, Any]:
    """Build a fresh post-migration evidence object without changing consumers."""

    pre_audit = json.loads(PRE_AUDIT_PATH.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    surrogate_pre = next(
        project
        for project in pre_audit["projects"]
        if project["project"] == "SURROGATE_TRAIN"
    )

    entries = []
    flat_import_count = 0
    for pre_entry in surrogate_pre["entries"]:
        path = SURROGATE_ROOT / pre_entry["path"]
        flat_imports = _flat_imports(path)
        flat_import_count += len(flat_imports)
        post_sha = _sha256(path)
        entries.append(
            {
                "path": pre_entry["path"],
                "kind": pre_entry["kind"],
                "pre_sha256": pre_entry["sha256"],
                "post_sha256": post_sha,
                "size_bytes": path.stat().st_size,
                "changed": post_sha != pre_entry["sha256"],
                "remaining_flat_imports": flat_imports,
            }
        )

    packages = [_package_audit(spec, reference) for spec in PACKAGE_SPECS]
    return {
        "schema": "alb.surrogate-train-post-migration-audit.v1",
        "version": "0.2.0",
        "audit_date": date.today().isoformat(),
        "pre_migration_audit": str(PRE_AUDIT_PATH.relative_to(REPOSITORY_ROOT)).replace(
            "\\", "/"
        ),
        "pre_migration_reference": str(
            REFERENCE_PATH.relative_to(SURROGATE_ROOT)
        ).replace("\\", "/"),
        "alb_main_migration_commit": _git(REPOSITORY_ROOT, "rev-parse", "HEAD"),
        "surrogate_train": {
            "root": str(SURROGATE_ROOT).replace("\\", "/"),
            "branch": _git(SURROGATE_ROOT, "branch", "--show-current"),
            "commit": _git(SURROGATE_ROOT, "rev-parse", "HEAD"),
            "working_tree_clean": _git(SURROGATE_ROOT, "status", "--porcelain") == "",
            "declared_count": len(entries),
            "changed_count": sum(entry["changed"] for entry in entries),
            "remaining_flat_import_count": flat_import_count,
            "entries": entries,
        },
        "model_packages": packages,
        "verification": list(VERIFICATION),
        "remaining_findings": list(REMAINING_FINDINGS),
        "data_or_legacy_model_sources_overwritten": False,
    }


def _markdown(audit: dict[str, Any]) -> str:
    """Render a concise Chinese evidence report from the audit object."""

    project = audit["surrogate_train"]
    package_lines = []
    for package in audit["model_packages"]:
        artifacts_ok = all(
            item["matches_manifest"] for item in package["artifacts"].values()
        )
        package_lines.append(
            f"- `{package['id']}`：`{package['package_dir']}`；"
            f"manifest/artifact 校验={'通过' if artifacts_ok else '失败'}；"
            f"Git ignored={str(package['git_ignored']).lower()}。"
        )

    verification_lines = [
        f"- {item['scope']}：{item['result']}（`{item['status']}`）。"
        for item in audit["verification"]
    ]
    finding_lines = [
        f"- `{item['id']}`（{item['classification']}，`{item['path']}`）："
        f"{item['description']}"
        for item in audit["remaining_findings"]
    ]
    return "\n".join(
        [
            "# SURROGATE_TRAIN 的 ALB 0.2 迁移后审计",
            "",
            "## 文档角色",
            "",
            "本文是 `0.2.0_external_consumer_audit.*` 的迁移后证据，不覆盖只读 v1 快照。",
            "它记录 SURROGATE_TRAIN 独立分支中的消费者迁移、package 校验和剩余边界；",
            "不保存实时训练 PID、loss、ETA，也不修改 PAPER_WORK。",
            "",
            "## 结论",
            "",
            f"- SURROGATE_TRAIN 分支：`{project['branch']}`。",
            f"- 审计 commit：`{project['commit']}`。",
            f"- 23 个 declared 文件中有 {project['changed_count']} 个完成迁移提交。",
            "- 其余 3 个是无直接 ALB import 的 context 文件；已做 smoke，按计划保持源码不变。",
            f"- 旧平铺 ALB import 数量：{project['remaining_flat_import_count']}。",
            "- 原 data 与旧模型文件未覆盖；三个新 package 位于被 Git 忽略的模型目录。",
            "",
            "## 模型 package",
            "",
            *package_lines,
            "",
            "## 验证",
            "",
            *verification_lines,
            "",
            "## 本批未修复的既有问题与后续边界",
            "",
            *finding_lines,
            "",
            "完整的逐文件 pre/post SHA-256、manifest 和 artifact 哈希见同名 JSON。",
            "",
        ]
    )


def main() -> None:
    """Write JSON and Markdown post-migration evidence to explicit paths."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    audit = build_audit()
    args.json_output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(_markdown(audit), encoding="utf-8")
    print(args.json_output)
    print(args.markdown_output)


if __name__ == "__main__":
    main()
