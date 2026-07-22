"""Freeze valid harmonic behavior before sixth-review runtime hardening."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.reference.generate_fifth_review_release_reference_v5 import (
    collect_reference_arrays as collect_fifth_review_arrays,
)


DEFAULT_JSON = ROOT / "refs/sixth_review_runtime_reference_v6.json"
DEFAULT_NPZ = ROOT / "refs/sixth_review_runtime_reference_v6.npz"
RANDOM_SEED = 20260722


def collect_reference_arrays() -> dict[str, np.ndarray]:
    """Return valid behavior that runtime failure hardening must preserve."""

    return {
        f"fifth.{name}": value
        for name, value in collect_fifth_review_arrays().items()
    }


def _sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = parser.parse_args()
    if args.json.exists() or args.npz.exists():
        raise FileExistsError("Refusing to overwrite sixth review reference v6")

    arrays = collect_reference_arrays()
    metadata = {
        "reference_name": "sixth_review_runtime_reference_v6",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": _git_head(),
        "random_seed": RANDOM_SEED,
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "scope": (
            "Successful harmonic controller and valve progression, force output, "
            "reinitialization, controller config restoration, and ALB defaults"
        ),
        "arrays": {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "sha256": _sha256(value),
            }
            for name, value in sorted(arrays.items())
        },
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.npz, **arrays)
    args.json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.json)
    print(args.npz)
    print(f"arrays={len(arrays)}")


if __name__ == "__main__":
    main()
