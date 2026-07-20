"""Exact replay of the immutable thermal convergence addendum."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_ROOT = REPOSITORY_ROOT / "refs/full_repo_refactor_addendum_v1"
GENERATOR = (
    REPOSITORY_ROOT
    / "tools/reference/generate_thermal_convergence_addendum_v1.py"
)


def _array_digest(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).view(np.uint8)).hexdigest()


def test_thermal_convergence_addendum_replays_exactly(tmp_path) -> None:
    expected_json = REFERENCE_ROOT / "thermal_convergence.json"
    expected_npz = REFERENCE_ROOT / "thermal_convergence.npz"
    expected = json.loads(expected_json.read_text(encoding="utf-8"))
    assert expected["source"]["generator_sha256"] == hashlib.sha256(
        GENERATOR.read_bytes()
    ).hexdigest()

    replay_root = tmp_path / "thermal_addendum_replay"
    environment = os.environ.copy()
    environment.update(
        {
            "ALB_REFERENCE_SOURCE_ROOT": str(REPOSITORY_ROOT),
            "ALB_REFERENCE_SOURCE_COMMIT": subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=REPOSITORY_ROOT,
                text=True,
                encoding="utf-8",
            ).strip(),
            "ALB_REFERENCE_SOURCE_TAG": "current-replay",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    completed = subprocess.run(
        [sys.executable, str(GENERATOR), "--output-dir", str(replay_root)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    actual = json.loads(
        (replay_root / "thermal_convergence.json").read_text(encoding="utf-8")
    )
    assert actual["schema"] == expected["schema"]
    assert actual["seed"] == expected["seed"]
    assert actual["environment"] == expected["environment"]
    assert actual["cases"] == expected["cases"]
    assert actual["arrays"] == expected["arrays"]

    with np.load(expected_npz) as expected_arrays, np.load(
        replay_root / "thermal_convergence.npz"
    ) as actual_arrays:
        assert set(expected_arrays.files) == set(actual_arrays.files) == set(
            expected["arrays"]
        )
        for name in expected_arrays.files:
            expected_array = np.asarray(expected_arrays[name])
            actual_array = np.asarray(actual_arrays[name])
            manifest = expected["arrays"][name]
            assert list(expected_array.shape) == manifest["shape"]
            assert str(expected_array.dtype) == manifest["dtype"]
            assert _array_digest(expected_array) == manifest["sha256"]
            assert _array_digest(actual_array) == manifest["sha256"]
            np.testing.assert_array_equal(actual_array, expected_array)


def test_thermal_addendum_contains_real_histories_and_commit_evidence() -> None:
    metadata = json.loads(
        (REFERENCE_ROOT / "thermal_convergence.json").read_text(encoding="utf-8")
    )
    with np.load(REFERENCE_ROOT / "thermal_convergence.npz") as arrays:
        for name in (
            "direct_outer_rel_error_history",
            "direct_pressure_residual_history",
            "newton_outer_rel_error_history",
            "newton_inner_residual_history",
            "newton_pressure_residual_history",
        ):
            assert arrays[name].size > 0
            assert np.all(np.isfinite(arrays[name]))

        assert metadata["cases"]["direct"]["newton_diagnostics"] == {
            "applicable": False
        }
        assert metadata["cases"]["newton"]["newton_diagnostics"] == {
            "applicable": True
        }
        assert np.all(arrays["transient_commit_flags"])
        np.testing.assert_array_equal(
            arrays["transient_candidate_temperature"],
            arrays["transient_committed_temperature"],
        )
        np.testing.assert_array_equal(
            arrays["transient_before_temperature"],
            arrays["transient_committed_temperature"][:-1],
        )
        np.testing.assert_array_equal(
            arrays["transient_before_step_indices"], np.array([1, 2])
        )
