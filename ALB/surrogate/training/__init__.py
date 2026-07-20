"""Config-driven training helpers for ALB surrogate models."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "TrainingConfig": ("ALB.surrogate.training.config", "TrainingConfig"),
    "TrainingConfigError": ("ALB.surrogate.training.config", "TrainingConfigError"),
    "AlbnnExpertTrainer": ("ALB.surrogate.training.runs", "AlbnnExpertTrainer"),
    "AlbnnMlpTrainer": ("ALB.surrogate.training.runs", "AlbnnMlpTrainer"),
    "AlbnnResidualTrainer": ("ALB.surrogate.training.runs", "AlbnnResidualTrainer"),
    "TrainingRun": ("ALB.surrogate.training.runs", "TrainingRun"),
    "ColumnTransformPipeline": (
        "ALB.surrogate.training.transforms",
        "ColumnTransformPipeline",
    ),
}


def __getattr__(name: str):
    """Resolve training helpers with a stable surrogate-extra error."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.surrogate.training' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.surrogate.training", module_name, "surrogate")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
