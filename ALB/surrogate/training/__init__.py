# coding: utf-8
"""Config-driven training helpers for ALB surrogate models.

This package owns reusable training mechanics.  Project-specific experiment
entry points remain in sibling repositories such as ``SURROGATE_TRAIN``.
"""

from .config import TrainingConfig
from .config import TrainingConfigError
from .runs import AlbnnExpertTrainer
from .runs import AlbnnMlpTrainer
from .runs import AlbnnResidualTrainer
from .runs import TrainingRun
from .transforms import ColumnTransformPipeline

__all__ = [
    "AlbnnExpertTrainer",
    "AlbnnMlpTrainer",
    "AlbnnResidualTrainer",
    "ColumnTransformPipeline",
    "TrainingConfig",
    "TrainingConfigError",
    "TrainingRun",
]
