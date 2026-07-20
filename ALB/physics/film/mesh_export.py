"""Structured oil-film mesh generation and Nastran export."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True, slots=True)
class BearingFilmMeshConfig:
    """Geometry and resolution of one structured bearing-pad film mesh."""

    bearing_radius: float
    film_thickness: float
    eccentricity_ratio: float
    attitude_angle_deg: float
    pad_start_angle_deg: float
    pad_arc_angle_deg: float
    circumferential_grids: int
    axial_grids: int
    thickness_grids: int
    axial_length: float = 1.0

    def validate(self) -> None:
        """Reject geometrically invalid mesh parameters."""

        if self.bearing_radius <= 0:
            raise ValueError("bearing_radius must be positive")
        if self.film_thickness <= 0:
            raise ValueError("film_thickness must be positive")
        if self.film_thickness >= self.bearing_radius:
            raise ValueError("film_thickness must be smaller than bearing_radius")
        if not 0 <= self.eccentricity_ratio < 1:
            raise ValueError("eccentricity_ratio must be in [0, 1)")
        if self.pad_arc_angle_deg <= 0:
            raise ValueError("pad_arc_angle_deg must be positive")
        if self.axial_length <= 0:
            raise ValueError("axial_length must be positive")
        for name, value in (
            ("circumferential_grids", self.circumferential_grids),
            ("axial_grids", self.axial_grids),
            ("thickness_grids", self.thickness_grids),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")


@dataclass(frozen=True, slots=True)
class StructuredHexMesh:
    """Coordinates and eight-node connectivity for one structured film mesh."""

    coordinates: np.ndarray
    elements: np.ndarray
    theta: np.ndarray
    axial: np.ndarray
    thickness_fraction: np.ndarray
    local_film_thickness: np.ndarray

    @property
    def node_count(self) -> int:
        return int(self.coordinates.shape[0])

    @property
    def element_count(self) -> int:
        return int(self.elements.shape[0])


def film_thickness_distribution(
    theta: np.ndarray,
    film_thickness: float,
    eccentricity_ratio: float,
    attitude_angle_rad: float,
) -> np.ndarray:
    """Evaluate the established circular journal-film thickness relation."""

    return film_thickness * (
        1.0 + eccentricity_ratio * np.cos(theta - attitude_angle_rad)
    )


def build_bearing_film_mesh(config: BearingFilmMeshConfig) -> StructuredHexMesh:
    """Build coordinates and CHEXA connectivity without changing node order."""

    config.validate()
    theta = np.deg2rad(
        np.linspace(
            config.pad_start_angle_deg,
            config.pad_start_angle_deg + config.pad_arc_angle_deg,
            config.circumferential_grids + 1,
        )
    )
    axial = np.linspace(
        -0.5 * config.axial_length,
        0.5 * config.axial_length,
        config.axial_grids + 1,
    )
    thickness_fraction = np.linspace(0.0, 1.0, config.thickness_grids + 1)
    local_thickness = film_thickness_distribution(
        theta,
        config.film_thickness,
        config.eccentricity_ratio,
        np.deg2rad(config.attitude_angle_deg),
    )
    if np.any(local_thickness <= 0):
        raise ValueError(
            "local film thickness became non-positive; reduce eccentricity_ratio"
        )

    inner_radius = config.bearing_radius - local_thickness
    shape = (
        config.circumferential_grids + 1,
        config.axial_grids + 1,
        config.thickness_grids + 1,
    )
    x = np.empty(shape, dtype=float)
    y = np.empty(shape, dtype=float)
    z = np.empty(shape, dtype=float)
    for theta_index, theta_value in enumerate(theta):
        radius_line = (
            inner_radius[theta_index]
            + thickness_fraction * local_thickness[theta_index]
        )
        for axial_index, axial_value in enumerate(axial):
            x[theta_index, axial_index, :] = radius_line * np.cos(theta_value)
            y[theta_index, axial_index, :] = radius_line * np.sin(theta_value)
            z[theta_index, axial_index, :] = axial_value

    coordinates = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    elements = []
    for theta_index in range(config.circumferential_grids):
        for axial_index in range(config.axial_grids):
            for thickness_index in range(config.thickness_grids):
                n000 = _node_id(shape, theta_index, axial_index, thickness_index)
                n100 = _node_id(shape, theta_index + 1, axial_index, thickness_index)
                n110 = _node_id(
                    shape, theta_index + 1, axial_index + 1, thickness_index
                )
                n010 = _node_id(shape, theta_index, axial_index + 1, thickness_index)
                n001 = _node_id(shape, theta_index, axial_index, thickness_index + 1)
                n101 = _node_id(
                    shape, theta_index + 1, axial_index, thickness_index + 1
                )
                n111 = _node_id(
                    shape,
                    theta_index + 1,
                    axial_index + 1,
                    thickness_index + 1,
                )
                n011 = _node_id(
                    shape, theta_index, axial_index + 1, thickness_index + 1
                )
                elements.append((n000, n100, n110, n010, n001, n101, n111, n011))
    return StructuredHexMesh(
        coordinates=coordinates,
        elements=np.asarray(elements, dtype=int),
        theta=theta,
        axial=axial,
        thickness_fraction=thickness_fraction,
        local_film_thickness=local_thickness,
    )


def write_nastran_bdf(mesh: StructuredHexMesh, output_path: str | Path) -> Path:
    """Write nodes and CHEXA elements in free-field Nastran syntax."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "$ Bearing oil-film mesh generated by ALB.physics.film.mesh_export",
        "BEGIN BULK",
        "$ CHEXA cards are written on one free-field line.",
        "MAT1,1,1.0,,0.3",
        "PSOLID,1,1",
    ]
    for node_id, (x_coord, y_coord, z_coord) in enumerate(mesh.coordinates, start=1):
        lines.append(f"GRID,{node_id},,{x_coord:.9e},{y_coord:.9e},{z_coord:.9e}")
    for element_id, connectivity in enumerate(mesh.elements, start=1):
        node_text = ",".join(str(node_id) for node_id in connectivity)
        lines.append(f"CHEXA,{element_id},1,{node_text}")
    lines.append("ENDDATA")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def plot_mesh_preview(
    mesh: StructuredHexMesh,
    output_path: str | Path | None = None,
    show: bool = True,
) -> Path | None:
    """Render a diagnostic three-dimensional mesh preview."""

    nx = mesh.theta.size
    nz = mesh.axial.size
    nh = mesh.thickness_fraction.size
    x = mesh.coordinates[:, 0].reshape(nx, nz, nh)
    y = mesh.coordinates[:, 1].reshape(nx, nz, nh)
    z = mesh.coordinates[:, 2].reshape(nx, nz, nh)
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    for axial_index in range(nz):
        for thickness_index in range(nh):
            ax.plot(
                x[:, axial_index, thickness_index],
                y[:, axial_index, thickness_index],
                z[:, axial_index, thickness_index],
                color="#1f77b4",
                linewidth=0.7,
                alpha=0.8,
            )
    for theta_index in range(nx):
        for thickness_index in range(nh):
            ax.plot(
                x[theta_index, :, thickness_index],
                y[theta_index, :, thickness_index],
                z[theta_index, :, thickness_index],
                color="#1f77b4",
                linewidth=0.7,
                alpha=0.55,
            )
    theta_stride = max(1, (nx - 1) // 12)
    axial_stride = max(1, (nz - 1) // 6)
    for theta_index in range(0, nx, theta_stride):
        for axial_index in range(0, nz, axial_stride):
            ax.plot(
                x[theta_index, axial_index, :],
                y[theta_index, axial_index, :],
                z[theta_index, axial_index, :],
                color="#ff7f0e",
                linewidth=0.9,
                alpha=0.8,
            )
    _set_equal_aspect(ax, mesh.coordinates)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")
    ax.set_title(
        "Bearing film hexa mesh\n"
        f"nodes={mesh.node_count}, elements={mesh.element_count}, "
        f"hmin={mesh.local_film_thickness.min():.3e} m, "
        f"hmax={mesh.local_film_thickness.max():.3e} m"
    )
    fig.tight_layout()
    saved_path = None if output_path is None else Path(output_path)
    if saved_path is not None:
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(saved_path, dpi=200, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return saved_path


def build_parser() -> argparse.ArgumentParser:
    """Build the diagnostic export command-line parser."""

    parser = argparse.ArgumentParser(description="Export a structured bearing oil-film mesh")
    parser.add_argument("--bearing-radius", type=float, required=True)
    parser.add_argument("--film-thickness", type=float, required=True)
    parser.add_argument("--eccentricity-ratio", type=float, required=True)
    parser.add_argument("--attitude-angle", type=float, required=True)
    parser.add_argument("--pad-start-angle", type=float, required=True)
    parser.add_argument("--pad-arc-angle", type=float, required=True)
    parser.add_argument("--circumferential-grids", type=int, required=True)
    parser.add_argument("--axial-grids", type=int, required=True)
    parser.add_argument("--thickness-grids", type=int, required=True)
    parser.add_argument("--axial-length", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--no-show", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the mesh-export diagnostic command."""

    args = build_parser().parse_args(argv)
    config = BearingFilmMeshConfig(
        bearing_radius=args.bearing_radius,
        film_thickness=args.film_thickness,
        eccentricity_ratio=args.eccentricity_ratio,
        attitude_angle_deg=args.attitude_angle,
        pad_start_angle_deg=args.pad_start_angle,
        pad_arc_angle_deg=args.pad_arc_angle,
        circumferential_grids=args.circumferential_grids,
        axial_grids=args.axial_grids,
        thickness_grids=args.thickness_grids,
        axial_length=args.axial_length,
    )
    mesh = build_bearing_film_mesh(config)
    bdf_path = write_nastran_bdf(mesh, args.output)
    preview_path = args.preview or bdf_path.with_name(f"{bdf_path.stem}_preview.png")
    plot_mesh_preview(mesh, preview_path, show=not args.no_show)
    print(f"BDF written to: {bdf_path}")
    print(f"Preview written to: {preview_path}")
    print(f"Nodes: {mesh.node_count}")
    print(f"Elements: {mesh.element_count}")
    return 0


def _node_id(shape: tuple[int, int, int], i: int, j: int, k: int) -> int:
    _, axial_count, thickness_count = shape
    return i * axial_count * thickness_count + j * thickness_count + k + 1


def _set_equal_aspect(ax: Any, coordinates: np.ndarray) -> None:
    minimum = coordinates.min(axis=0)
    maximum = coordinates.max(axis=0)
    center = 0.5 * (minimum + maximum)
    radius = 0.5 * np.max(maximum - minimum)
    if radius == 0:
        radius = 1.0
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)


__all__ = [
    "BearingFilmMeshConfig",
    "StructuredHexMesh",
    "build_bearing_film_mesh",
    "film_thickness_distribution",
    "plot_mesh_preview",
    "write_nastran_bdf",
]
