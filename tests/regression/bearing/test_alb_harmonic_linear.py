"""Regression tests for the equation-derived harmonic linear ALB wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ALB import StepContext
from ALB.systems.alb.harmonic import (
    ALBHarmonicCoefficients,
    ALBHarmonicLinear,
    alb_harmonic_linear,
    load_builtin_alb_harmonic_coefficients,
)
from ALB.core import Signal, TimeIterDt
from ALB.dynamics.coupling import RsRotorBearingCouple
from ALB.contracts import BearingInput
from ALB.contracts.result_tree import DataFrameResult, SaveTreeNode


REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_RESPONSE = (
    REPO_ROOT
    / "docs"
    / "formula"
    / "figures"
    / "source_data"
    / "alb_harmonic_kcg_pd_time_response_source_data.csv"
)


class _FakeRotor:
    """Minimal rotor contract used to exercise RsRotorBearingCouple."""

    def __init__(self, position: np.ndarray):
        self.signal = Signal(sys=self)
        self.position = np.asarray(position, dtype=float).reshape(2)
        self.velocity = np.zeros(2, dtype=float)
        self.last_force = None
        self.last_nodes = None

    def init(self):
        self.last_force = None
        self.last_nodes = None

    def output(self, node_links):
        count = len(np.asarray(node_links).reshape(-1))
        return {
            "uxy": np.repeat(self.position[None, :], count, axis=0),
            "uxyt": np.repeat(self.velocity[None, :], count, axis=0),
        }

    def input_force2node(self, t, force, node_links, force0=None):
        self.last_force = np.asarray(force, dtype=float).copy()
        self.last_nodes = np.asarray(node_links, dtype=int).copy()

    def advance(self):
        """Satisfy the explicit rotor lifecycle without changing this fixed state."""

        return None

    def finish_signal(self):
        return None

    def save(self, tofile=False, *args, **kwargs):
        """Return a minimal save node for the coupling save-contract test."""

        return SaveTreeNode(
            "fake_rotor",
            DataFrameResult({"rotor": pd.DataFrame()}),
        )


def _run_pd_orbit(bearing: ALBHarmonicLinear) -> pd.DataFrame:
    """Run the documented four-cycle, 5 micrometer PD trajectory."""

    amplitude_m = 5.0e-6
    points = 16
    cycles = 4
    omega = bearing.coefficients.whirl_omega_rad_s
    rows = []
    for direction in ("forward", "reverse"):
        bearing.init()
        sign = 1.0 if direction == "forward" else -1.0
        for step in range(points * cycles):
            phase = 2.0 * np.pi * (step + 1) / points
            displacement = np.array(
                [amplitude_m * np.cos(phase), sign * amplitude_m * np.sin(phase)]
            )
            velocity = np.array(
                [
                    -amplitude_m * omega * np.sin(phase),
                    sign * amplitude_m * omega * np.cos(phase),
                ]
            )
            bearing.input(
                BearingInput(
                    bearing.coefficients.equilibrium_position + displacement,
                    velocity,
                    step * bearing.dt,
                    "dimensional",
                )
            )
            bearing.evaluate()
            force_increment = (
                bearing.output().force - bearing.coefficients.static_force
            )
            if step >= points * (cycles - 1):
                rows.append(
                    {
                        "direction": direction,
                        "phase_rad": phase % (2.0 * np.pi),
                        "fx": force_increment[0],
                        "fy": force_increment[1],
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["direction", "phase_rad"], ignore_index=True
    )


def test_builtin_coefficient_contract_and_base_match():
    coefficients = load_builtin_alb_harmonic_coefficients()
    assert isinstance(coefficients, ALBHarmonicCoefficients)
    assert type(coefficients).__module__ == "ALB.systems.alb.harmonic_coefficients"
    assert coefficients.stiffness.shape == (2, 2)
    assert coefficients.damping.shape == (2, 2)
    assert coefficients.spool_transfer.shape == (2, 2)
    assert np.iscomplexobj(coefficients.spool_transfer)
    assert coefficients.whirl_frequency_hz == 50.0

    bearing = alb_harmonic_linear(node_link=12)
    assert isinstance(bearing, ALBHarmonicLinear)
    assert bearing.node_link == 12
    np.testing.assert_array_equal(bearing.fdxv, coefficients.spool_transfer)
    np.testing.assert_array_equal(bearing.uxy0, coefficients.equilibrium_position)
    np.testing.assert_array_equal(bearing.xv0, coefficients.base_spool)
    np.testing.assert_allclose(
        bearing.spool,
        coefficients.base_spool,
        rtol=0.0,
        atol=1.0e-15,
    )
    bearing.input(
        BearingInput(
            coefficients.equilibrium_position,
            np.zeros(2),
            0.0,
            "dimensional",
        )
    )
    bearing.evaluate()
    output = bearing.output()
    np.testing.assert_allclose(
        output.force, coefficients.static_force, rtol=0.0, atol=1.0e-9
    )
    assert isinstance(bearing.save(tofile=False), SaveTreeNode)


def test_pd_orbit_matches_documented_k_c_gxv_reconstruction():
    bearing = alb_harmonic_linear(node_link=12)
    actual = _run_pd_orbit(bearing)
    reference = pd.read_csv(REFERENCE_RESPONSE).sort_values(
        ["direction", "phase_rad"], ignore_index=True
    )
    expected = reference[
        ["linear_total_delta_fx_N", "linear_total_delta_fy_N"]
    ].to_numpy(dtype=float)
    np.testing.assert_allclose(
        actual[["fx", "fy"]].to_numpy(dtype=float),
        expected,
        rtol=1.0e-12,
        atol=2.0e-10,
    )


def test_rs_rotor_bearing_couple_accepts_harmonic_linear_bearing():
    bearing = alb_harmonic_linear(node_link=12)
    rotor = _FakeRotor(bearing.coefficients.equilibrium_position)
    time_iter = TimeIterDt(bearing.dt, num=2)
    couple = RsRotorBearingCouple(rotor, time_iter, bearing)

    couple.init()
    couple.advance(StepContext(1, bearing.dt, bearing.dt, "dimensional"))
    couple.advance(StepContext(2, 2.0 * bearing.dt, bearing.dt, "dimensional"))

    assert rotor.last_force is not None
    assert rotor.last_force.shape == (1, 2)
    assert rotor.last_nodes.tolist() == [12]
    np.testing.assert_allclose(
        rotor.last_force[0],
        bearing.coefficients.static_force,
        rtol=0.0,
        atol=1.0e-9,
    )
    assert len(couple.results["bearing0"]) == 2
    assert len(bearing.results) == 2
    save_node = couple.save(tofile=False)
    assert isinstance(save_node, SaveTreeNode)
    assert len(save_node.children) == 2
