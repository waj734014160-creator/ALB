"""Build the machine-readable 0.1 to 0.2 import migration map."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASELINE_TAG = "pre-full-repo-refactor-20260720"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs/migrations/0.2.0_import_map.json"

MODULE_OVERRIDES: dict[str, list[str]] = {
    "ALB": ["ALB.contracts", "ALB"],
    "ALB.adapters": ["ALB.physics.bearing.decorators", "ALB.systems.alb.ports"],
    "ALB.adapters.bearing": [
        "ALB.physics.bearing.decorators",
        "ALB.systems.alb.ports",
    ],
    "ALB.alb": [
        "ALB.systems.alb.builder",
        "ALB.systems.alb.factories",
        "ALB.systems.alb.linear",
        "ALB.systems.alb.runtime",
        "ALB.systems.alb.surrogate_runtime",
        "ALB.systems.alb.switch",
    ],
    "ALB.base": ["ALB.core.component", "ALB.core.fem.base"],
    "ALB.bearing": ["ALB.physics.bearing", "ALB.physics.bearing.solver"],
    "ALB.boundary": ["ALB.core.fem.boundary"],
    "ALB.config": ["ALB.config"],
    "ALB.controller": [
        "ALB.control.fuzzy",
        "ALB.control.lqg",
        "ALB.control.pid",
        "ALB.control.reduction_core",
        "ALB.control.repetitive",
    ],
    "ALB.couple": ["ALB.dynamics.coupling"],
    "ALB.damping": ["ALB.core.numerics.damping"],
    "ALB.film": ["ALB.physics.film", "ALB.physics.film.solver"],
    "ALB.gas": ["ALB.physics.gas", "ALB.physics.gas.solver"],
    "ALB.gauss": ["ALB.core.numerics.iteration"],
    "ALB.harmonic_linear": ["ALB.systems.alb.harmonic"],
    "ALB.logger": ["ALB.infrastructure.logging"],
    "ALB.lti": ["ALB.control.state_space"],
    "ALB.matrix": ["ALB.core.numerics"],
    "ALB.matrix.dynmaic": ["ALB.core.numerics.dynamic"],
    "ALB.matrix.static": ["ALB.core.numerics.static"],
    "ALB.mesh": ["ALB.core.fem.mesh"],
    "ALB.nn": [
        "ALB.surrogate.features",
        "ALB.surrogate.inference",
        "ALB.surrogate.networks",
        "ALB.surrogate.package",
        "ALB.surrogate.scalers",
    ],
    "ALB.nondim": ["ALB.physics.thermal.scales"],
    "ALB.orbit": ["ALB.dynamics.orbit"],
    "ALB.orifice": ["ALB.physics.hydraulics.orifice"],
    "ALB.plot": ["ALB.workflows.plotting"],
    "ALB.postprocess": ["ALB.workflows.postprocess"],
    "ALB.remote": ["ALB.infrastructure.remote"],
    "ALB.remote.albnn_queue": ["ALB.surrogate.training.remote.queue"],
    "ALB.remote.albnn_start": ["ALB.surrogate.training.remote.start"],
    "ALB.remote.albnn_status": ["ALB.surrogate.training.remote.status"],
    "ALB.remote.common": ["ALB.infrastructure.remote.common"],
    "ALB.remote.defaults": ["ALB.infrastructure.remote.defaults"],
    "ALB.remote.job": ["ALB.infrastructure.remote.job"],
    "ALB.remote.monitor": ["ALB.infrastructure.remote.monitor"],
    "ALB.remote.transport": ["ALB.infrastructure.remote.transport"],
    "ALB.results": [
        "ALB.contracts.result_tree",
        "ALB.contracts.results",
        "ALB.infrastructure.persistence",
    ],
    "ALB.rotor": ["ALB.dynamics.rotor", "ALB.dynamics.rotor_layout"],
    "ALB.servovalve": ["ALB.control.valve"],
    "ALB.task": [
        "ALB.workflows.alb",
        "ALB.workflows.configuration",
        "ALB.workflows.execution",
    ],
    "ALB.thermal": ["ALB.physics.thermal", "ALB.physics.thermal.solver"],
    "ALB.tool": [
        "ALB.config.parameters",
        "ALB.control.reduction",
        "ALB.core.numerics.arrays",
        "ALB.dynamics.identification",
        "ALB.infrastructure.config_io",
        "ALB.infrastructure.notification",
        "ALB.physics.film.mesh_export",
        "ALB.physics.film.model_utils",
        "ALB.workflows.configuration",
        "ALB.workflows.doe",
        "ALB.workflows.execution",
        "ALB.workflows.naming",
    ],
    "ALB.train": ["ALB.surrogate.training"],
    "ALB.train.config": ["ALB.surrogate.training.config"],
    "ALB.train.data": ["ALB.surrogate.training.data"],
    "ALB.train.losses": ["ALB.surrogate.training.losses"],
    "ALB.train.reports": ["ALB.surrogate.training.reports"],
    "ALB.train.runs": ["ALB.surrogate.training.runs"],
    "ALB.train.transforms": ["ALB.surrogate.training.transforms"],
}

SYMBOL_OVERRIDES = {
    "ALB.controller.test_lqg": ["ALB.control.controllers.test_lqg"],
    "ALB.base.BaseSimpleModel": ["ALB.core.component.BaseSimpleModel"],
    "ALB.config.ConfigData": ["ALB.config.common.ConfigData"],
    "ALB.config.ResolvedTimeGrid": ["ALB.config.common.ResolvedTimeGrid"],
    "ALB.config.TimeGridConfig": ["ALB.config.common.TimeGridConfig"],
    "ALB.config.HydConfig": ["ALB.config.film.HydConfig"],
    "ALB.config.FPBConfig": ["ALB.config.film.FPBConfig"],
    "ALB.config.NodimPadConfig": ["ALB.config.film.NodimPadConfig"],
    "ALB.config.GasConfig": ["ALB.config.gas.GasConfig"],
    "ALB.config.TankConfig": ["ALB.config.hydraulics.TankConfig"],
    "ALB.config.OrificeConfig": ["ALB.config.hydraulics.OrificeConfig"],
    "ALB.config.NodimOrificeConfig": [
        "ALB.config.hydraulics.NodimOrificeConfig"
    ],
    "ALB.config.ServoConfig": ["ALB.config.control.ServoConfig"],
    "ALB.config.Moog2ndServoConfig": ["ALB.config.control.Moog2ndServoConfig"],
    "ALB.config.PIDConfig": ["ALB.config.control.PIDConfig"],
    "ALB.config.LQGConfig": ["ALB.config.control.LQGConfig"],
    "ALB.config.FuzzyPIDConfig": ["ALB.config.control.FuzzyPIDConfig"],
    "ALB.config.ThermalConfig": ["ALB.config.thermal.ThermalConfig"],
    "ALB.config.build_thermal_config": [
        "ALB.config.thermal.build_thermal_config"
    ],
    "ALB.config.ALBConfig": ["ALB.config.system.ALBConfig"],
    "ALB.config.NodimALBConfig": ["ALB.config.system.NodimALBConfig"],
    "ALB.config.ALBNetConfig": ["ALB.config.surrogate.ALBNetConfig"],
    "ALB.gauss.gauss_seidel_iteration_film": [
        "ALB.core.numerics.iteration.gauss_seidel_iteration_film"
    ],
    "ALB.gauss.gauss_seidel_iteration_matrix": [
        "ALB.core.numerics.iteration.gauss_seidel_iteration_matrix"
    ],
    "ALB.postprocess.rotor_respone": ["ALB.workflows.postprocess.rotor_response"],
    "ALB.results.BaseResult": ["ALB.contracts.results.ResultBundle"],
    "ALB.rotor.StaicLoad": ["ALB.dynamics.rotor.StaticLoad"],
    "ALB.rotor.RossRotorSimlarityCheck": [
        "ALB.dynamics.rotor.RossRotorSimilarityCheck"
    ],
    "ALB.rotor.lld_intergral": ["ALB.dynamics.rotor.lld_integral"],
    "ALB.tool.EmailSender": ["ALB.infrastructure.notification.SmtpNotifier"],
    "ALB.tool.itercouple": ["ALB.workflows.execution.iter_parameter_combinations"],
    "ALB.tool.get_main_model_from_filmsystem": [
        "ALB.physics.film.model_utils.get_primary_film_model"
    ],
    "ALB.tool.Partition": ["ALB.workflows.doe.partition_intervals"],
    "ALB.tool.Representative": [
        "ALB.workflows.doe.sample_interval_representatives"
    ],
    "ALB.tool.Rearrange": ["ALB.workflows.doe.shuffle_columns"],
    "ALB.tool.ParameterArray": ["ALB.workflows.doe.latin_hypercube_samples"],
    "ALB.tool.DoE": ["ALB.workflows.doe.DesignOfExperiments"],
    "ALB.tool.DoELHS": ["ALB.workflows.doe.LatinHypercubeDesign"],
    "ALB.tool.UnzipToTask": ["ALB.workflows.execution.UnpackTask"],
    "ALB.tool.chstack": ["ALB.core.numerics.arrays.horizontal_stack_nonempty"],
    "ALB.tool.cvstack": ["ALB.core.numerics.arrays.vertical_stack_nonempty"],
    "ALB.tool.autoname": ["ALB.workflows.naming.build_parameter_name"],
    "ALB.tool.parse_bearing_film_mesh_args": [
        "ALB.physics.film.mesh_export.build_parser"
    ],
    "ALB.tool.bearing_film_nastran_export_main": [
        "tools.diagnostics.export_bearing_film_mesh.main"
    ],
    "ALB.tool.namevalue": ["ALB.workflows.naming.parse_parameter_name"],
    "ALB.tool.read_share": ["ALB.infrastructure.config_io.read_shared_config"],
    "ALB.tool.read_json5_with_share": [
        "ALB.infrastructure.config_io.read_json5_with_shared"
    ],
    "ALB.tool.ConfigArgfy": ["ALB.workflows.configuration.ConfigurationSweep"],
    "ALB.tool.continue_task": [
        "ALB.workflows.configuration.pending_task_directories"
    ],
    "ALB.tool.read_configs": [
        "ALB.infrastructure.config_io.read_config_directories"
    ],
    "ALB.tool.get_config_value": ["ALB.infrastructure.config_io.get_config_values"],
    "ALB.tool.listdir": ["ALB.infrastructure.config_io.list_directories"],
    "ALB.tool.get_modal_reduction": [
        "ALB.control.reduction.conservative_modal_reduction"
    ],
    "ALB.tool.calculate_moi_complex": [
        "ALB.control.reduction.modal_observability_indices"
    ],
}

PUBLIC_ALIAS_OVERRIDES = {
    "ALB.base.BaseSimpleModel": ["ALB.core.component.BaseSimpleModel"],
    "ALB.config.CsoArgs": ["ALB.config.hydraulics.CsoArgs"],
    "ALB.nn.ALBNN_BASE_INPUT_COLS": [
        "ALB.surrogate.features.ALBNN_BASE_INPUT_COLS"
    ],
    "ALB.nn.ALBNN_FEATURE_SETS": ["ALB.surrogate.features.ALBNN_FEATURE_SETS"],
    "ALB.nn.ALBNN_OUTPUT_COLS": ["ALB.surrogate.features.ALBNN_OUTPUT_COLS"],
    "ALB.nn.ALBNN_POLAR_FORCE_OUTPUT_COLS": [
        "ALB.surrogate.features.ALBNN_POLAR_FORCE_OUTPUT_COLS"
    ],
    "ALB.thermal.ThermalConfig": ["ALB.config.thermal.ThermalConfig"],
    "ALB.train.AlbnnMlpTrainer": [
        "ALB.surrogate.training.AlbnnMlpTrainer"
    ],
    "ALB.train.TrainingConfig": ["ALB.surrogate.training.TrainingConfig"],
}

ROOT_EXPORT_OVERRIDES = {
    "ComponentBase": ["ALB.core.component.ComponentBase"],
    "BearingComponentBase": ["ALB.core.component.BearingComponentBase"],
    "BearingProtocol": ["ALB.contracts.bearing.BearingProtocol"],
    "BearingCoefficientProtocol": [
        "ALB.contracts.bearing.BearingCoefficientProtocol"
    ],
    "ControllerProtocol": ["ALB.contracts.control.ControllerProtocol"],
    "ServoValveProtocol": ["ALB.contracts.control.ServoValveProtocol"],
    "RotorProtocol": ["ALB.contracts.dynamics.RotorProtocol"],
    "TimeGridProtocol": ["ALB.contracts.model.TimeGridProtocol"],
    "NotifierProtocol": ["ALB.contracts.notification.NotifierProtocol"],
    "ConvergenceStatus": ["ALB.ConvergenceStatus"],
    "BearingDecoratorBase": [
        "ALB.physics.bearing.decorators.BearingDecoratorBase"
    ],
    "LegacyBearingAdapter": [
        "ALB.physics.bearing.decorators.LegacyBearingAdapter"
    ],
    "ThermalConfig": ["ALB.config.thermal.ThermalConfig"],
}

REMOVAL_RATIONALES = {
    "ALB.tool.create_latex_symbol": (
        "Removed as an unused presentation helper outside the numerical runtime."
    ),
    "ALB.tool.get": (
        "Removed as a one-line default-selection helper; use an explicit expression."
    ),
}

IMPORTANT_IMPORTS = [
    {"old": "from ALB import ALB", "new": "from ALB.systems.alb import ALB"},
    {"old": "from ALB import HydConfig", "new": "from ALB.config import HydConfig"},
    {"old": "from ALB.results import SaveTreeNode", "new": "from ALB.contracts.result_tree import SaveTreeNode"},
    {"old": "from ALB.remote import job", "new": "from ALB.infrastructure.remote import job"},
    {"old": "from ALB.train import TrainingConfig", "new": "from ALB.surrogate.training import TrainingConfig"},
    {"old": "from ALB.rotor import StaicLoad", "new": "from ALB.dynamics.rotor import StaticLoad"},
]


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPOSITORY_ROOT, text=True, encoding="utf-8"
    ).strip()


def _path_to_module(path: str) -> str:
    value = path.removesuffix(".py").replace("/", ".")
    return value.removesuffix(".__init__")


def _current_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in (REPOSITORY_ROOT / "ALB").rglob("*.py"):
        module = _path_to_module(path.relative_to(REPOSITORY_ROOT).as_posix())
        modules[module] = path
    return modules


def _public_definitions(source: str) -> list[str]:
    tree = ast.parse(source.lstrip("\ufeff"))
    names = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _literal_assignment(source: str, variable: str) -> Any:
    """Return one top-level literal assignment from a Python source document."""

    tree = ast.parse(source.lstrip("\ufeff"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"Literal assignment {variable!r} was not found")


def _symbol_index(modules: dict[str, Path]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for module, path in modules.items():
        source = path.read_text(encoding="utf-8-sig")
        for name in _public_definitions(source):
            index[name].append(f"{module}.{name}")
    return index


def _mapped_targets(module: str, current: dict[str, Path]) -> list[str]:
    if module in MODULE_OVERRIDES:
        return MODULE_OVERRIDES[module]
    return [module] if module in current else []


def build_map() -> dict[str, Any]:
    current = _current_modules()
    symbol_index = _symbol_index(current)
    baseline_paths = [
        path
        for path in _git("ls-tree", "-r", "--name-only", BASELINE_TAG, "ALB").splitlines()
        if path.endswith(".py")
    ]
    modules = []
    symbols = []
    for path in baseline_paths:
        source_module = _path_to_module(path)
        targets = _mapped_targets(source_module, current)
        if not targets:
            raise KeyError(f"No 0.2 module mapping for {source_module}")
        status = "unchanged_namespace" if targets == [source_module] else "migrated"
        if source_module == "ALB":
            status = "root_contract_only"
        modules.append(
            {
                "source": source_module,
                "targets": targets,
                "status": status,
                "source_file": path,
            }
        )

        source = _git("show", f"{BASELINE_TAG}:{path}")
        for name in _public_definitions(source):
            source_symbol = f"{source_module}.{name}"
            candidates = SYMBOL_OVERRIDES.get(source_symbol)
            if candidates is None:
                candidates = [
                    candidate
                    for candidate in symbol_index.get(name, [])
                    if any(
                        candidate == target or candidate.startswith(f"{target}.")
                        for target in targets
                    )
                ]
            symbols.append(
                {
                    "source": source_symbol,
                    "targets": sorted(set(candidates)),
                    "status": (
                        "renamed"
                        if candidates
                        and any(
                            candidate.rsplit(".", 1)[-1] != name
                            for candidate in candidates
                        )
                        else ("migrated" if candidates else "removed")
                    ),
                    "rationale": (
                        "Private SMTP defaults were removed; inject SmtpConfig or environment values."
                        if source_symbol == "ALB.tool.EmailSender"
                        else REMOVAL_RATIONALES.get(source_symbol)
                    ),
                }
            )

    symbol_lookup = {item["source"]: item for item in symbols}
    public_aliases = [
        {
            "source": source,
            "targets": targets,
            "status": "migrated_public_alias",
            "rationale": "Public re-export or constant used by declared external consumers.",
        }
        for source, targets in sorted(PUBLIC_ALIAS_OVERRIDES.items())
    ]
    alias_lookup = {item["source"]: item for item in public_aliases}

    baseline_root_source = _git("show", f"{BASELINE_TAG}:ALB/__init__.py")
    baseline_root_exports = _literal_assignment(baseline_root_source, "_EXPORTS")
    root_exports = []
    for name, provider in baseline_root_exports.items():
        provider_module, provider_name = provider
        provider_symbol = f"{provider_module}.{provider_name}"
        targets = ROOT_EXPORT_OVERRIDES.get(name)
        if targets is None:
            mapping = symbol_lookup.get(provider_symbol) or alias_lookup.get(provider_symbol)
            targets = [] if mapping is None else mapping["targets"]
        if not targets:
            raise KeyError(
                f"No 0.2 target for baseline root export ALB.{name} via {provider_symbol}"
            )
        root_exports.append(
            {
                "source": f"ALB.{name}",
                "legacy_provider": provider_symbol,
                "targets": sorted(set(targets)),
                "status": "retained_root_contract"
                if f"ALB.{name}" in targets
                else "migrated_root_export",
            }
        )

    return {
        "schema": "alb.import-migration-map.v1",
        "version": "0.2.0",
        "baseline_tag": BASELINE_TAG,
        "baseline_commit": _git("rev-list", "-n", "1", BASELINE_TAG),
        "breaking": True,
        "root_api": {
            "exports": [
                "__version__",
                "UnitSystem",
                "StepContext",
                "ConvergenceStatus",
                "ComputationalBlock",
                "SolvableBlock",
                "EvaluableBlock",
                "CommandBlock",
                "AdvancingBlock",
            ],
            "note": "All domain implementations require explicit namespace imports.",
        },
        "module_mappings": modules,
        "symbol_mappings": symbols,
        "public_alias_mappings": public_aliases,
        "root_export_mappings": root_exports,
        "important_imports": IMPORTANT_IMPORTS,
        "resource_mappings": [
            {
                "source": "ALB/data/alb_harmonic_linear_gamma1_50hz.json",
                "target": "ALB/systems/alb/data/alb_harmonic_linear_gamma1_50hz.json",
            }
        ],
        "intentional_incompatibilities": [
            "ALB.nn pickle objects are not a 0.2 runtime compatibility surface.",
            "Direct result-tree filesystem methods were removed; inject ArtifactWriterProtocol.",
            "BearingForceTrack pickle save/load was removed in favor of ResultBundle artifacts.",
            "The misspelled StaicLoad symbol was replaced by StaticLoad.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_map(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
