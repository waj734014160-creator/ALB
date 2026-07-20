"""Film-model composition helpers."""

from __future__ import annotations

from typing import Any


def get_primary_film_model(system: Any) -> Any:
    """Return the primary model from a film system or validate a direct model."""

    from .solver import FilmModel, FilmSystem

    if isinstance(system, FilmSystem):
        return system.main_model
    if not isinstance(system, FilmModel):
        raise TypeError("system must be FilmModel or FilmSystem")
    return system


__all__ = ["get_primary_film_model"]
