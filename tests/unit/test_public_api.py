"""Tests for the deliberately narrow ALB 0.2 package root."""

import ALB


def test_package_root_exports_only_foundational_contracts():
    assert ALB.__version__ == "0.2.0"
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
