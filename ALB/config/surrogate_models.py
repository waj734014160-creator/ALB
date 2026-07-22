"""Domain configuration models split from the historical monolith."""

from dataclasses import dataclass
from typing import Optional

from .common_models import ConfigData

@dataclass
class ALBNetConfig(ConfigData):
    """Configuration for the ALB Neural Network agent."""

    scaler_X: Optional[str] = None
    scaler_y: Optional[str] = None
    model: Optional[str] = None
    c: float = 120e-6
    vf: float = 1
    freq: float = None
    ps: float = 7e6
    l: float = 0.06
    r: float = 0.04
    agent: str = "ALBNNAgent"  # ALBNNAgent, HydroNNAgent, HybridNNAgent
    metadata: Optional[str] = None
    lambda_value: float = 1.0
    beta_nondim: float = 0.03
    lr: float = 1.0
    cq0: float = 5.0
    cq1: float = 0.02
    cq2: float = 0.002
    extra_inputs: Optional[dict] = None

    @classmethod
    def from_dict(cls, config_dict):
        """Creates an instance from a dictionary."""
        direct_keys = [
            "scaler_X",
            "scaler_y",
            "model",
            "c",
            "vf",
            "freq",
            "ps",
            "l",
            "r",
            "agent",
            "metadata",
            "lambda_value",
            "beta_nondim",
            "lr",
            "cq0",
            "cq1",
            "cq2",
            "extra_inputs",
        ]
        direct_args = {
            key: config_dict[key] for key in direct_keys if key in config_dict
        }
        return cls(**direct_args)

__all__ = ['ALBNetConfig']
