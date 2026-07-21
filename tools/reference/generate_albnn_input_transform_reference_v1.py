"""Freeze deployed ALBNN input transforms before exposing the public adapter."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SURROGATE_ROOT = ROOT.parent / "SURROGATE_TRAIN"
SOURCE_REFERENCE = (
    SURROGATE_ROOT
    / "refs"
    / "alb_0_2_consumer_migration_v1"
    / "consumer_migration_reference_v1.npz"
)
SOURCE_METADATA = SOURCE_REFERENCE.with_suffix(".json")
DEFAULT_JSON = ROOT / "refs" / "albnn_input_transform_reference_v1.json"
DEFAULT_NPZ = ROOT / "refs" / "albnn_input_transform_reference_v1.npz"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _legacy_transform(model, inputs: np.ndarray) -> np.ndarray:
    """Replay the private pre-adapter transform used by consumer scripts."""

    if hasattr(model, "base_model"):
        base = model.base_model
        frame = base._base_frame(inputs)
        from ALB.surrogate.features import c4_canonicalize_albnn_frame

        canonical, _ = c4_canonicalize_albnn_frame(frame)
        model_frame = base._model_frame(canonical)
        scaler = base.scaler_X
    else:
        model_frame = model._model_frame(inputs)
        scaler = model.scaler_X
    return np.asarray(scaler.transform(model_frame), dtype=float)


def generate(output_json: Path, output_npz: Path) -> None:
    """Write immutable JSON/NPZ reference files without overwriting."""

    for output in (output_json, output_npz):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite reference: {output}")

    sys.modules["ALB.nn"] = importlib.import_module("ALB.surrogate.inference")
    from ALB.config.surrogate import ALBNetConfig
    from ALB.surrogate.inference import albnn

    source_metadata = json.loads(SOURCE_METADATA.read_text(encoding="utf-8"))
    arrays: dict[str, np.ndarray] = {}
    with np.load(SOURCE_REFERENCE, allow_pickle=False) as source_arrays:
        for key in ("m31", "m35"):
            model_name = source_metadata["models"][key]["model_name"]
            model_root = SURROGATE_ROOT / "models" / model_name
            model = albnn(
                ALBNetConfig(
                    model=str(model_root / "best_albnn.pth"),
                    scaler_X=str(model_root / "scaler_X.pkl"),
                    scaler_y=str(model_root / "scaler_y.pkl"),
                    metadata=str(model_root / "metadata.json"),
                )
            )
            arrays[f"{key}.transformed_inputs"] = _legacy_transform(
                model, source_arrays[f"{key}.inputs"]
            )

    metadata = {
        "schema": "alb.albnn-input-transform-reference.v1",
        "source_reference": str(SOURCE_REFERENCE),
        "source_reference_sha256": _sha256(SOURCE_REFERENCE),
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": hashlib.sha256(
                    np.ascontiguousarray(value).tobytes()
                ).hexdigest(),
            }
            for name, value in arrays.items()
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    np.savez(output_npz, **arrays)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_npz}")


def main() -> None:
    """Parse destinations and generate the reference pair."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    generate(args.output_json, args.output_npz)


if __name__ == "__main__":
    main()
