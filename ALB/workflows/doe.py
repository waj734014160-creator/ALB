"""Latin-hypercube design-of-experiments utilities."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd


def partition_intervals(sample_count: int, limits: np.ndarray) -> np.ndarray:
    """Partition every variable interval into ``sample_count`` strata."""

    lower_coefficients = np.zeros((sample_count, 2))
    upper_coefficients = np.zeros((sample_count, 2))
    for index in range(sample_count):
        lower_coefficients[index] = (1 - index / sample_count, index / sample_count)
        upper_coefficients[index] = (
            1 - (index + 1) / sample_count,
            (index + 1) / sample_count,
        )
    lower = lower_coefficients @ limits.T
    upper = upper_coefficients @ limits.T
    return np.dstack((lower.T, upper.T))


def sample_interval_representatives(partitions: np.ndarray) -> np.ndarray:
    """Draw one random representative from every interval partition."""

    variable_count = partitions.shape[0]
    sample_count = partitions.shape[1]
    coefficients = np.zeros((variable_count, sample_count, 2))
    representatives = np.zeros((sample_count, variable_count))
    for variable in range(variable_count):
        for sample in range(sample_count):
            value = random.random()
            coefficients[variable, sample] = (1 - value, value)
    weighted = partitions * coefficients
    for variable in range(variable_count):
        representatives[:, variable] = weighted[variable, :, 0] + weighted[variable, :, 1]
    return representatives


def shuffle_columns(values: np.ndarray) -> np.ndarray:
    """Shuffle each parameter column independently in place."""

    for column in range(values.shape[1]):
        np.random.shuffle(values[:, column])
    return values


def latin_hypercube_samples(limits: np.ndarray, sample_count: int) -> np.ndarray:
    """Return the established ALB Latin-hypercube sample matrix."""

    partitions = partition_intervals(sample_count, limits)
    return shuffle_columns(sample_interval_representatives(partitions))


class DesignOfExperiments:
    """Base container for named design variables and bounds."""

    def __init__(self, names: list[str], bounds: np.ndarray) -> None:
        self.names = names
        self.bounds = bounds
        self.kind = "DoE"
        self.result = None


class LatinHypercubeDesign(DesignOfExperiments):
    """Generate and export an ALB Latin-hypercube design."""

    def __init__(self, names: list[str], bounds: np.ndarray, sample_count: int) -> None:
        super().__init__(names, bounds)
        self.kind = "LHS"
        self.samples = latin_hypercube_samples(bounds, sample_count)
        self.sample_count = sample_count

    @property
    def sample_data(self) -> pd.DataFrame:
        """Return samples with their declared column names."""

        return pd.DataFrame(self.samples, columns=self.names)

    def write_csv(self, path: str | Path = "LHS.csv") -> Path:
        """Write the design table and return the destination path."""

        destination = Path(path)
        self.sample_data.to_csv(destination)
        return destination


__all__ = [
    "DesignOfExperiments",
    "LatinHypercubeDesign",
    "latin_hypercube_samples",
    "partition_intervals",
    "sample_interval_representatives",
    "shuffle_columns",
]
