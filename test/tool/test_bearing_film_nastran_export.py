from pathlib import Path

import matplotlib
import numpy as np

from ALB.tool import (
    BearingFilmMeshConfig,
    build_bearing_film_mesh,
    film_thickness_distribution,
    plot_mesh_preview,
    write_nastran_bdf,
)

# matplotlib.use("Agg")


def test_bearing_film_mesh_export_and_preview(tmp_path: Path) -> None:
    config = BearingFilmMeshConfig(
        bearing_radius=0.04,
        film_thickness=80e-6,
        eccentricity_ratio=0.25,
        attitude_angle_deg=20.0,
        pad_start_angle_deg=270.0,
        pad_arc_angle_deg=90.0,
        circumferential_grids=80,
        axial_grids=30,
        thickness_grids=6,
        axial_length=0.06,
    )

    mesh = build_bearing_film_mesh(config)

    assert mesh.node_count == (config.circumferential_grids + 1) * (
        config.axial_grids + 1
    ) * (config.thickness_grids + 1)
    assert (
        mesh.element_count
        == config.circumferential_grids * config.axial_grids * config.thickness_grids
    )
    expected_thickness = film_thickness_distribution(
        mesh.theta,
        config.film_thickness,
        config.eccentricity_ratio,
        np.deg2rad(config.attitude_angle_deg),
    )
    assert np.allclose(mesh.local_film_thickness, expected_thickness)

    bdf_path = tmp_path / "bearing_mesh.bdf"
    preview_path = tmp_path / "bearing_mesh_preview.png"

    write_nastran_bdf(mesh, bdf_path)
    plot_mesh_preview(mesh, output_path=preview_path, show=False)

    assert bdf_path.exists()
    assert preview_path.exists()
    bdf_text = bdf_path.read_text(encoding="utf-8")
    assert "GRID" in bdf_text
    assert "CHEXA" in bdf_text
    assert "\n+," not in bdf_text
    assert preview_path.stat().st_size > 0
    print(
        f"Test passed: Nastran BDF and preview image successfully generated at {tmp_path}"
    )


if __name__ == "__main__":
    test_bearing_film_mesh_export_and_preview(
        Path("outputs") / "test_bearing_film_mesh"
    )
