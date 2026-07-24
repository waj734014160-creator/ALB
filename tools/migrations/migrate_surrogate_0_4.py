"""Convert one trusted ALBNN v0.2 package into the safe v0.4 format."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ALB.surrogate.package import create_model_package


_SCALER_NAMES = frozenset(
    {
        "AsinhTargetScaler",
        "ColumnSignedLog1pTargetScaler",
        "Cq2SigLogMinMaxScaler",
        "IdentityTargetScaler",
        "MinMaxCubeRootTargetScaler",
        "MinMaxWithScaledEvsFeaturesScaler",
        "MotionStandardParamDirectMinMaxScaler",
        "MotionStandardParamMinMaxScaler",
        "PolarMotionStandardParamMinMaxScaler",
        "SelectiveMinMaxScaler",
        "SelectiveStandardScaler",
        "SignedLog1pTargetScaler",
        "StandardTargetScaler",
        "StandardThenMinMaxScaler",
    }
)


class _TrustedScalerUnpickler(pickle.Unpickler):
    """Resolve only the retired ALB scaler module during explicit migration."""

    def find_class(self, module: str, name: str):
        if module == "ALB.nn":
            if name not in _SCALER_NAMES:
                raise pickle.UnpicklingError(
                    f"unsupported ALB.nn scaler global: {name}"
                )
            from ALB.surrogate import inference

            return getattr(inference, name)
        return super().find_class(module, name)


def _load_trusted_pickle(path: Path) -> object:
    with path.open("rb") as stream:
        return _TrustedScalerUnpickler(stream).load()


def convert(source: Path, destination: Path) -> None:
    """Read a trusted v0.2 package and write one strict v0.4 package."""

    manifest = json.loads(
        (source / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema") != "alb.surrogate-package.v0.2":
        raise ValueError("source must be an ALBNN v0.2 package")
    artifacts = manifest["artifacts"]

    def artifact(role: str) -> Path:
        return source / str(artifacts[role]["path"])

    metadata = json.loads(artifact("metadata").read_text(encoding="utf-8"))
    metadata.pop("schema", None)
    metadata["migration_source_schema"] = manifest["schema"]
    create_model_package(
        destination,
        checkpoint=artifact("model"),
        input_scaler=_load_trusted_pickle(artifact("input_scaler")),
        output_scaler=_load_trusted_pickle(artifact("output_scaler")),
        metadata=metadata,
    )


def main() -> int:
    """Parse the repository-only migration command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--trust-legacy-pickle",
        action="store_true",
        help="Confirm that the v0.2 scaler pickles are trusted.",
    )
    args = parser.parse_args()
    if not args.trust_legacy_pickle:
        parser.error("--trust-legacy-pickle is required")
    convert(args.source.resolve(), args.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
