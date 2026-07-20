"""Liquid-film Reynolds solvers and mesh utilities."""

from ALB.contracts.optional import import_optional_module


_EXPORTS = {
    "BearingFilmMeshConfig": ("ALB.physics.film.mesh_export", "BearingFilmMeshConfig"),
    "StructuredHexMesh": ("ALB.physics.film.mesh_export", "StructuredHexMesh"),
    "build_bearing_film_mesh": ("ALB.physics.film.mesh_export", "build_bearing_film_mesh"),
    "film_thickness_distribution": (
        "ALB.physics.film.mesh_export",
        "film_thickness_distribution",
    ),
    "plot_mesh_preview": ("ALB.physics.film.mesh_export", "plot_mesh_preview"),
    "write_nastran_bdf": ("ALB.physics.film.mesh_export", "write_nastran_bdf"),
    "FilmBoundary": ("ALB.physics.film.solver", "FilmBoundary"),
    "FilmModel": ("ALB.physics.film.solver", "FilmModel"),
    "FilmOutput": ("ALB.physics.film.solver", "FilmOutput"),
    "FilmPostProcess": ("ALB.physics.film.solver", "FilmPostProcess"),
    "FilmSystem": ("ALB.physics.film.solver", "FilmSystem"),
    "GaussSeidelFilm": ("ALB.physics.film.solver", "GaussSeidelFilm"),
    "LsqFilm": ("ALB.physics.film.solver", "LsqFilm"),
    "NewtonFilm": ("ALB.physics.film.solver", "NewtonFilm"),
    "NodimNewtonFilm": ("ALB.physics.film.solver", "NodimNewtonFilm"),
    "PSetFilmBoundary": ("ALB.physics.film.solver", "PSetFilmBoundary"),
    "RectFilmElem": ("ALB.physics.film.solver", "RectFilmElem"),
    "RectFilmNode": ("ALB.physics.film.solver", "RectFilmNode"),
    "SkfemNewtonFilm": ("ALB.physics.film.solver", "SkfemNewtonFilm"),
    "ThicknessModel": ("ALB.physics.film.solver", "ThicknessModel"),
    "film_args_trans": ("ALB.physics.film.solver", "film_args_trans"),
}


def __getattr__(name: str):
    """Resolve film implementations with a stable optional-extra error."""

    if name not in _EXPORTS:
        raise AttributeError(f"module 'ALB.physics.film' has no attribute '{name}'")
    module_name, attribute_name = _EXPORTS[name]
    module = import_optional_module("ALB.physics.film", module_name, "film")
    return getattr(module, attribute_name)


__all__ = list(_EXPORTS)
