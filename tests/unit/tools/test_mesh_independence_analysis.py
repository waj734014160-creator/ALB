"""Unit tests for mesh-independence convergence diagnostics."""

from tools.analysis.run_alb_mesh_independence import _gci_component


def test_gci_accepts_monotonic_asymptotic_sequence():
    result = _gci_component(1.16, 1.04, 1.01)
    assert result["valid"] is True
    assert result["monotonic"] is True
    assert result["apparent_order"] > 0.0
    assert result["fine_gci"] > 0.0


def test_gci_rejects_oscillatory_sequence():
    result = _gci_component(1.1, 0.9, 1.0)
    assert result == {
        "monotonic": False,
        "apparent_order": None,
        "fine_gci": None,
        "valid": False,
    }
