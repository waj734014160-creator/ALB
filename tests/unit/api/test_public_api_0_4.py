"""Public ALB 0.4 facade and strict configuration tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ALB
from ALB.dynamics.rotor import RossRotor


def _liquid_config(*, time_step: float = 1.0e-3) -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": time_step,
            "node": 0,
            "film": {
                "circumferential_elements": 5,
                "axial_elements": 3,
                "max_iterations": 5,
                "solver_tolerance": 1.0e-6,
                "eccentricity": 0.0,
            },
            "restrictors": None,
            "thermal": None,
        }
    )


def _gas_config() -> ALB.BearingConfig:
    return ALB.BearingConfig(
        {
            "family": "gas_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {
                "circumferential_elements": 5,
                "axial_elements": 3,
                "max_iterations": 5,
                "solver_tolerance": 1.0e-6,
                "eccentricity": 0.0,
            },
        }
    )


class _NodeRotorPlant:
    ndof = 4
    number_dof = 4

    def _lti(self, speed):
        del speed
        state_count = 2 * self.ndof
        return SimpleNamespace(
            A=-0.5 * np.eye(state_count),
            B=np.vstack((np.eye(self.ndof), 0.25 * np.eye(self.ndof))),
            C=np.eye(state_count),
            D=np.zeros((state_count, self.ndof)),
        )


def test_root_namespace_is_friendly_and_has_no_legacy_entry_points() -> None:
    assert ALB.__version__ == "0.4.5"
    assert ALB.SCHEMA_VERSION == "0.4.0"
    assert not {
        "Signal",
        "ALBBuilder",
        "RsRotorBearingCouple",
        "RotorBearingCouple",
        "StaticPosition",
        "EllipseTrack",
        "alb2",
        "nodim_alb",
    }.intersection(ALB.__all__)


def test_bearing_is_ready_without_public_init_and_output_is_read_only() -> None:
    bearing = ALB.build_bearing(_liquid_config())

    assert not hasattr(bearing, "init")
    result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)
    assert result.force.shape == (2,)
    assert not result.force.flags.writeable
    assert bearing.latest_result is result
    np.testing.assert_array_equal(bearing.latest_result.force, result.force)

    bearing.reset()
    with pytest.raises(RuntimeError, match="no bearing result"):
        _ = bearing.latest_result


def test_gas_film_runtime_is_available_through_friendly_facade() -> None:
    bearing = ALB.build_bearing(_gas_config())

    result = bearing.calculate(displacement=(0.0, 0.0), time=0.0)

    assert result.force.shape == (2,)
    assert np.all(np.isfinite(result.force))
    assert not result.force.flags.writeable


def test_calculate_is_keyword_only_and_enforces_sequential_time() -> None:
    bearing = ALB.build_bearing(_liquid_config())
    with pytest.raises(TypeError):
        bearing.calculate((0.0, 0.0), time=0.0)

    bearing.calculate(displacement=(0.0, 0.0), time=0.0)
    with pytest.raises(ValueError, match="time must advance"):
        bearing.calculate(displacement=(0.0, 0.0), time=2.0e-3)


def test_config_is_immutable_and_override_revalidates() -> None:
    config = _liquid_config()
    with pytest.raises(TypeError):
        config.spec["time_step"] = 2.0e-3

    updated = config.with_overrides({"film.supply_pressure": 5.0e6})
    assert "supply_pressure" not in config.spec["film"]
    assert updated.spec["film"]["supply_pressure"] == 5.0e6
    assert [
        item.spec["film"]["supply_pressure"]
        for item in updated.sweep(
            "film.supply_pressure",
            (4.0e6, 6.0e6),
        )
    ] == [4.0e6, 6.0e6]


def test_strict_json5_include_order_and_null_override(tmp_path: Path) -> None:
    profile = tmp_path / "profile.json5"
    profile.write_text(
        """
        {
          schema_version: "0.4.0",
          kind: "bearing_profile",
          spec: {
            family: "liquid_film",
            unit_system: "dimensional",
            time_step: 0.001,
            node: 0,
            film: {
              circumferential_elements: 5,
              axial_elements: 3,
              supply_pressure: 7000000,
            },
            restrictors: {
              positions: [[0.5, 0.5]],
              radius: 0.0001,
            },
            thermal: null,
          },
        }
        """,
        encoding="utf-8",
    )
    case = tmp_path / "case.json5"
    case.write_text(
        """
        {
          schema_version: "0.4.0",
          kind: "bearing",
          includes: ["profile.json5"],
          spec: {
            film: { supply_pressure: 5000000 },
            restrictors: null,
          },
        }
        """,
        encoding="utf-8",
    )

    config = ALB.load_bearing_config(case)
    assert config.spec["film"]["supply_pressure"] == 5.0e6
    assert config.spec["restrictors"] is None


def test_strict_json5_rejects_cycles_duplicates_kind_mismatch_and_escape(
    tmp_path: Path,
) -> None:
    profile = """
    {
      schema_version: "0.4.0",
      kind: "bearing_profile",
      includes: %s,
      spec: {},
    }
    """
    case_template = """
    {
      schema_version: "0.4.0",
      kind: "bearing",
      includes: %s,
      spec: {
        family: "liquid_film",
        unit_system: "dimensional",
        time_step: 0.001,
        node: 0,
        film: {},
        restrictors: null,
        thermal: null,
      },
    }
    """
    (tmp_path / "a.json5").write_text(
        profile % '["b.json5"]',
        encoding="utf-8",
    )
    (tmp_path / "b.json5").write_text(
        profile % '["a.json5"]',
        encoding="utf-8",
    )
    cycle = tmp_path / "cycle.json5"
    cycle.write_text(case_template % '["a.json5"]', encoding="utf-8")
    with pytest.raises(ALB.ConfigurationError, match="cycle"):
        ALB.load_bearing_config(cycle)

    leaf = tmp_path / "leaf.json5"
    leaf.write_text(profile % "[]", encoding="utf-8")
    duplicate = tmp_path / "duplicate.json5"
    duplicate.write_text(
        case_template % '["leaf.json5", "leaf.json5"]',
        encoding="utf-8",
    )
    with pytest.raises(ALB.ConfigurationError, match="duplicate"):
        ALB.load_bearing_config(duplicate)

    wrong_kind = tmp_path / "wrong.json5"
    wrong_kind.write_text(
        """
        {schema_version: "0.4.0", kind: "simulation_profile", spec: {}}
        """,
        encoding="utf-8",
    )
    mismatch = tmp_path / "mismatch.json5"
    mismatch.write_text(
        case_template % '["wrong.json5"]',
        encoding="utf-8",
    )
    with pytest.raises(ALB.ConfigurationError, match="bearing_profile"):
        ALB.load_bearing_config(mismatch)

    outside = tmp_path.parent / "outside.json5"
    outside.write_text(profile % "[]", encoding="utf-8")
    escape = tmp_path / "escape.json5"
    escape.write_text(
        case_template % '["../outside.json5"]',
        encoding="utf-8",
    )
    with pytest.raises(ALB.ConfigurationError, match="escapes"):
        ALB.load_bearing_config(escape)


def test_analysis_uses_fresh_runtime_and_does_not_change_latest_result() -> None:
    bearing = ALB.build_bearing(_liquid_config())
    latest = bearing.calculate(displacement=(0.0, 0.0), time=0.0)
    trajectory = ALB.EllipseTrajectory(
        center=np.zeros(2),
        semi_axes=np.full(2, 1.0e-7),
    )

    result = bearing.analysis.trace_orbit(
        trajectory,
        np.arange(8, dtype=float) * 1.0e-3,
        frequency_hz=125.0,
    )

    assert result.values["force"].shape == (8, 2)
    assert result.convergence.converged
    assert result.diagnostics["schema"] == "alb.orbit-result.v0.4.1"
    assert bearing.latest_result is latest


@pytest.mark.parametrize(
    "document",
    [
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {"nx": 5},
            "restrictors": None,
            "thermal": None,
        },
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {},
            "restrictors": {
                "positions": [[0.5, 0.5]],
                "radius": 1.0e-4,
                "flow_coefficient": 0.1,
            },
            "thermal": None,
        },
        {
            "family": "liquid_film",
            "unit_system": "dimensional",
            "time_step": 1.0e-3,
            "node": 0,
            "film": {},
            "restrictors": None,
            "thermal": {"transient_enabled": None},
        },
    ],
)
def test_legacy_or_ambiguous_configuration_is_rejected(document) -> None:
    with pytest.raises(ALB.ConfigurationError):
        ALB.BearingConfig(document)


def test_simulation_keeps_all_committed_steps_by_default() -> None:
    rotor = RossRotor(_NodeRotorPlant(), speed=1.0, dt=1.0e-3)
    config = ALB.SimulationConfig(
        rotor=rotor,
        mounts=(ALB.BearingMount(_liquid_config(), 0),),
        time_step=1.0e-3,
        steps=2,
    )

    result = ALB.build_simulation(config).run()

    np.testing.assert_array_equal(result.time, [0.0, 1.0e-3, 2.0e-3])
    assert result.bearing_force.shape == (3, 1, 2)
    assert result.metadata["complete"] is True
    assert result.metadata["committed_steps"] == 3
    assert result.convergence.converged
    assert result.diagnostics["history_mode"] == "memory"


def test_simulation_history_policy_filters_downsamples_and_rings() -> None:
    rotor = RossRotor(_NodeRotorPlant(), speed=1.0, dt=1.0e-3)
    history = ALB.HistoryPolicy(
        mode="ring_buffer",
        fields=("bearing_force",),
        downsample=1,
        capacity=2,
    )
    config = ALB.SimulationConfig(
        rotor=rotor,
        mounts=(ALB.BearingMount(_liquid_config(), 0),),
        time_step=1.0e-3,
        steps=2,
        history=history,
    )

    result = ALB.build_simulation(config).run()

    np.testing.assert_array_equal(result.time, [1.0e-3, 2.0e-3])
    assert result.rotor_displacement.shape == (2, 0)
    assert result.rotor_velocity.shape == (2, 0)
    assert result.bearing_force.shape == (2, 1, 2)
    assert result.convergence.converged


def test_simulation_can_stream_filtered_history_to_disk(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "stream"
    rotor = RossRotor(_NodeRotorPlant(), speed=1.0, dt=1.0e-3)
    history = ALB.HistoryPolicy(
        mode="disk_stream",
        fields=("bearing_force",),
        downsample=2,
        directory=history_root,
    )
    config = ALB.SimulationConfig(
        rotor=rotor,
        mounts=(ALB.BearingMount(_liquid_config(), 0),),
        time_step=1.0e-3,
        steps=2,
        history=history,
    )

    result = ALB.build_simulation(config).run()

    np.testing.assert_array_equal(result.time, [0.0, 2.0e-3])
    assert result.bearing_force.shape == (2, 0)
    assert sorted(path.name for path in history_root.glob("step_*.npz")) == [
        "step_00000000.npz",
        "step_00000002.npz",
    ]
    manifest = (history_root / "history.json").read_text(encoding="utf-8")
    assert '"schema": "alb.simulation-history.v0.4"' in manifest
    assert result.metadata["history_path"] == str(history_root.resolve())
