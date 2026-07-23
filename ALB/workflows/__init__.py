"""Executable workflows and top-level physical-step coordination."""

from ALB.contracts.optional import import_optional_module
from ALB.core.steps import StepCommitLedger


def __getattr__(name: str):
    """Load file workflows only when the optional IO extra is available."""

    if name != "build_alb_from_file":
        raise AttributeError(f"module 'ALB.workflows' has no attribute '{name}'")
    module = import_optional_module(
        "ALB.workflows",
        "ALB.workflows.bearing_build",
        "io",
    )
    return module.build_alb_from_file


__all__ = ["StepCommitLedger", "build_alb_from_file"]
