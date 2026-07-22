"""Public typed interfaces and DTOs for ALB components."""

from .bearing import BearingCoefficientProtocol, BearingProtocol
from .block import (
    AdvancingBlock,
    CommandBlock,
    ComputationalBlock,
    EvaluableBlock,
    SolvableBlock,
)
from .control import ControllerProtocol, LegacyControllerProtocol, ServoValveProtocol
from .dynamics import RotorProtocol, RotorStateMap
from .lifecycle import LifecycleState, RuntimeLifecycleProtocol
from .model import (
    ConvergenceStatus,
    LifecycleProtocol,
    PersistableProtocol,
    SignalProtocol,
    TimeGridProtocol,
)
from .notification import NotifierProtocol
from .optional import import_optional_module, missing_optional_dependency
from .ports import (
    BearingInput,
    BearingOutput,
    ControlInput,
    ControlOutput,
    RotorLoadInput,
    RotorState,
    ValveInput,
    ValveOutput,
)
from .results import (
    ArtifactManifest,
    ArtifactRecord,
    ArtifactWriterProtocol,
    ResultBundle,
    ResultRecorderProtocol,
    ResultSnapshotProtocol,
    result_snapshot,
)
from .result_tree import DataFrameResult, NpyResult, RossRotorResult, SaveTreeNode
from .types import StepContext, UnitSystem

__all__ = [
    "AdvancingBlock",
    "ArtifactManifest",
    "ArtifactRecord",
    "ArtifactWriterProtocol",
    "DataFrameResult",
    "BearingInput",
    "BearingOutput",
    "BearingCoefficientProtocol",
    "BearingProtocol",
    "CommandBlock",
    "ComputationalBlock",
    "ControlInput",
    "ControlOutput",
    "ControllerProtocol",
    "ConvergenceStatus",
    "EvaluableBlock",
    "LifecycleProtocol",
    "LifecycleState",
    "LegacyControllerProtocol",
    "NotifierProtocol",
    "import_optional_module",
    "missing_optional_dependency",
    "PersistableProtocol",
    "RotorProtocol",
    "RotorStateMap",
    "RotorLoadInput",
    "RotorState",
    "ResultBundle",
    "ResultRecorderProtocol",
    "ResultSnapshotProtocol",
    "RuntimeLifecycleProtocol",
    "NpyResult",
    "RossRotorResult",
    "SaveTreeNode",
    "ServoValveProtocol",
    "SignalProtocol",
    "SolvableBlock",
    "StepContext",
    "TimeGridProtocol",
    "UnitSystem",
    "ValveInput",
    "ValveOutput",
    "result_snapshot",
]
