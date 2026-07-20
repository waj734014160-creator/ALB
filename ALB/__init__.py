"""ALB 0.2 public package boundary.

Domain implementations are imported from their explicit namespaces.  The
package root deliberately exposes only version and foundational contracts.
"""

from .contracts import (
    AdvancingBlock,
    CommandBlock,
    ComputationalBlock,
    ConvergenceStatus,
    EvaluableBlock,
    SolvableBlock,
    StepContext,
    UnitSystem,
)


__version__ = "0.2.0"

__all__ = [
    "AdvancingBlock",
    "CommandBlock",
    "ComputationalBlock",
    "ConvergenceStatus",
    "EvaluableBlock",
    "SolvableBlock",
    "StepContext",
    "UnitSystem",
    "__version__",
]
