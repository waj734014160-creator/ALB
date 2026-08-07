"""Freeze pre-0.4.5 servovalve matrices and deterministic time responses."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

import control
import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import ALB  # noqa: E402
from ALB.control.valve import (  # noqa: E402
    moog_2nd_servovalve,
    moog_servovalve,
    static_sv,
)


JSON_PATH = REPOSITORY_ROOT / "refs" / "servo_interface_0_4_5_reference_v1.json"
NPZ_PATH = REPOSITORY_ROOT / "refs" / "servo_interface_0_4_5_reference_v1.npz"
DT = 1.0e-3
COMMANDS = np.asarray([0.0, 0.2, -0.4, 0.8, 0.1, 0.0], dtype=float)


def _capture_case(name: str, valve) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Return metadata and lossless arrays for one deterministic valve case."""

    model = valve.main_model
    arrays: dict[str, np.ndarray] = {
        f"{name}_continuous_A": np.asarray(model.A),
        f"{name}_continuous_B": np.asarray(model.B),
        f"{name}_continuous_C": np.asarray(model.C),
        f"{name}_continuous_D": np.asarray(model.D),
        f"{name}_implementation_A": np.asarray(model._a),
        f"{name}_implementation_C": np.asarray(model._c),
        f"{name}_implementation_D": np.asarray(model._d),
    }
    if hasattr(model, "_Bd0"):
        arrays[f"{name}_implementation_Bd0"] = np.asarray(model._Bd0)
        arrays[f"{name}_implementation_Bd1"] = np.asarray(model._Bd1)
    else:
        arrays[f"{name}_implementation_B"] = np.asarray(model._b)

    outputs = []
    for index, command in enumerate(COMMANDS):
        valve.input(index * DT, float(command))
        outputs.append(np.asarray(valve.evaluate(), dtype=float).reshape(-1))
    arrays[f"{name}_commands"] = COMMANDS.copy()
    arrays[f"{name}_outputs"] = np.vstack(outputs)

    metadata = {
        "state_count": int(model.A.shape[0]),
        "input_count": int(model.B.shape[1]),
        "output_count": int(model.C.shape[0]),
        "arrays": {
            key: {"shape": list(value.shape), "dtype": str(value.dtype)}
            for key, value in arrays.items()
        },
    }
    return metadata, arrays


def _build_reference() -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Build the immutable reference payload from the unmodified valve code."""

    second_order_frequency_hz = 166.0
    delayed_frequency_hz = 80.0
    third_order_frequency_hz = 120.0
    cases = {
        "second_order_166hz": {
            "parameters": {
                "dt": DT,
                "natural_frequency_hz": second_order_frequency_hz,
                "damping_ratio": 0.7,
                "delay": 0.0,
            },
            "valve": moog_2nd_servovalve(
                DT,
                tw=1.0 / (2.0 * np.pi * second_order_frequency_hz),
                zeta=0.7,
                delay=0.0,
            ),
        },
        "second_order_80hz_delayed": {
            "parameters": {
                "dt": DT,
                "natural_frequency_hz": delayed_frequency_hz,
                "damping_ratio": 0.6,
                "delay": 0.002,
            },
            "valve": moog_2nd_servovalve(
                DT,
                tw=1.0 / (2.0 * np.pi * delayed_frequency_hz),
                zeta=0.6,
                delay=0.002,
            ),
        },
        "legacy_third_order": {
            "parameters": {
                "dt": DT,
                "natural_frequency_hz": third_order_frequency_hz,
                "damping_ratio": 0.65,
                "third_order_time_constant": 0.003,
                "delay": 0.001,
            },
            "valve": moog_servovalve(
                DT,
                tw=1.0 / (2.0 * np.pi * third_order_frequency_hz),
                zeta=0.65,
                tp3=0.003,
                delay=0.001,
            ),
        },
        "legacy_static": {
            "parameters": {"dt": DT},
            "valve": static_sv(DT),
        },
    }

    metadata_cases: dict[str, object] = {}
    arrays: dict[str, np.ndarray] = {}
    for name, case in cases.items():
        metadata, case_arrays = _capture_case(name, case["valve"])
        metadata_cases[name] = {
            "parameters": case["parameters"],
            **metadata,
        }
        arrays.update(case_arrays)

    payload = {
        "schema": "alb.servo-interface-0.4.5-reference.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": "7308f54",
        "purpose": (
            "Freeze the pre-0.4.5 second-order, third-order, and static valve "
            "behavior before replacing the public JSON interface."
        ),
        "environment": {
            "python": platform.python_version(),
            "alb": ALB.__version__,
            "numpy": np.__version__,
            "control": control.__version__,
        },
        "coefficient_order": "descending powers of continuous-time s",
        "cases": metadata_cases,
        "comparison": {
            "matrices": "np.testing.assert_array_equal",
            "responses": "np.testing.assert_array_equal",
        },
    }
    return payload, arrays


def main() -> int:
    """Write the pre-change JSON/NPZ reference pair exactly once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing reference pair intentionally.",
    )
    args = parser.parse_args()
    if not args.force and (JSON_PATH.exists() or NPZ_PATH.exists()):
        raise FileExistsError("reference exists; pass --force only intentionally")

    payload, arrays = _build_reference()
    JSON_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    np.savez(NPZ_PATH, **arrays)
    print(JSON_PATH)
    print(NPZ_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
