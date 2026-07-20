"""Liquid-film Reynolds solvers."""

from .solver import (
    FilmBoundary,
    FilmModel,
    FilmOutput,
    FilmPostProcess,
    FilmSystem,
    GaussSeidelFilm,
    LsqFilm,
    NewtonFilm,
    NodimNewtonFilm,
    PSetFilmBoundary,
    RectFilmElem,
    RectFilmNode,
    SkfemNewtonFilm,
    ThicknessModel,
    film_args_trans,
)

__all__ = [
    "FilmBoundary",
    "FilmModel",
    "FilmOutput",
    "FilmPostProcess",
    "FilmSystem",
    "GaussSeidelFilm",
    "LsqFilm",
    "NewtonFilm",
    "NodimNewtonFilm",
    "PSetFilmBoundary",
    "RectFilmElem",
    "RectFilmNode",
    "SkfemNewtonFilm",
    "ThicknessModel",
    "film_args_trans",
]
