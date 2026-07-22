"""State-space and conservative modal model reduction utilities."""

from __future__ import annotations

from typing import Any

import numpy as np
import scipy.linalg as scipy_linalg
from scipy.linalg import eigh

from .reduction_core import (
    alpha_shift,
    alpha_unshift,
    balanced_truncation,
    compute_modal_info,
    modal_truncation_by_damping,
    modal_truncation_by_dominance,
    modal_truncation_by_frequency,
    modal_truncation_by_index,
)


def conservative_modal_reduction(
    mass: np.ndarray,
    stiffness: np.ndarray,
    damping: np.ndarray,
    mode_count: int,
    gyroscopic: np.ndarray | None = None,
    input_matrix: np.ndarray | None = None,
) -> dict[str, np.ndarray | None]:
    """Project a second-order system onto its lowest conservative modes."""

    degree_count = mass.shape[0]
    retained_count = min(mode_count, degree_count)
    symmetric_stiffness = (stiffness + stiffness.T) / 2
    eigenvalues, mode_shapes = eigh(symmetric_stiffness, mass)
    basis = mode_shapes[:, :retained_count]
    retained_eigenvalues = eigenvalues[:retained_count]
    return {
        "Mr": np.eye(retained_count),
        "Kr": np.diag(retained_eigenvalues),
        "Cr": basis.T @ damping @ basis,
        "Gr": None if gyroscopic is None else basis.T @ gyroscopic @ basis,
        "Br": None if input_matrix is None else basis.T @ input_matrix,
        "Phi_r": basis,
        "eigenvalues": retained_eigenvalues,
    }


def modal_observability_indices(
    state_matrix: np.ndarray,
    output_matrix: np.ndarray,
) -> list[dict[str, Any]]:
    """Calculate the output modal-observability index for every eigenvector."""

    eigenvalues, eigenvectors = scipy_linalg.eig(state_matrix)
    order = np.argsort(np.abs(np.imag(eigenvalues)))
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    results = []
    for index, eigenvalue in enumerate(eigenvalues):
        vector = eigenvectors[:, index]
        index_value = scipy_linalg.norm(output_matrix @ vector) / scipy_linalg.norm(
            vector
        )
        complex_frequency = eigenvalue / (2 * np.pi)
        results.append(
            {
                "mode_index": index,
                "complex_freq": complex_frequency,
                "freq_abs": np.abs(complex_frequency),
                "freq_osc": complex_frequency.imag,
                "moi": index_value,
            }
        )
    return results

__all__ = [
    "alpha_shift",
    "alpha_unshift",
    "balanced_truncation",
    "compute_modal_info",
    "conservative_modal_reduction",
    "modal_truncation_by_damping",
    "modal_truncation_by_dominance",
    "modal_truncation_by_frequency",
    "modal_truncation_by_index",
    "modal_observability_indices",
]
