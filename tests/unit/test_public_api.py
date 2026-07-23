"""Tests for the deliberately narrow ALB 0.3 package root."""

import ALB


def test_package_root_exports_only_foundational_contracts():
    assert ALB.__version__ == "0.3.0"
    assert set(ALB.__all__) == {
        "AdvancingBlock",
        "CommandBlock",
        "ComputationalBlock",
        "ConvergenceStatus",
        "EvaluableBlock",
        "SolvableBlock",
        "StepContext",
        "UnitSystem",
        "__version__",
    }
    assert not hasattr(ALB, "ALB")
