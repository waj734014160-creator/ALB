"""Unit contracts for the repository-wide incremental mypy gate."""

from pathlib import Path

from tools.validation.run_layered_mypy import (
    COVERED_NAMESPACES,
    diagnostic_counts,
    discover_covered_sources,
)


def test_diagnostic_counts_normalizes_paths_and_error_codes():
    output = "\n".join(
        [
            r"ALB\control\pid.py:10: error: message [assignment]",
            "ALB/control/pid.py:20: error: another [assignment]",
            "ALB/control/pid.py:21: note: ignored",
        ]
    )
    assert diagnostic_counts(output) == {"ALB/control/pid.py|assignment": 2}


def test_layered_gate_covers_every_python_file_in_target_namespaces():
    root = Path(__file__).resolve().parents[3]
    sources = discover_covered_sources(root)

    assert sources
    for namespace in COVERED_NAMESPACES:
        assert any(path.startswith(f"{namespace}/") for path in sources)
    assert "ALB/control/pid.py" in sources
    assert "ALB/dynamics/rotor.py" in sources
    assert "ALB/systems/alb/runtime.py" in sources
