# -- coding: utf-8 --

import unittest

import numpy as np

from ALB.physics.bearing import (
    MultiPad,
    TiltingPadHydrodynamicPad,
    get_pad_pressure_fields,
    solve_tilting_pad_equilibrium,
    tilting_pads_bearing,
    tilting_pads_bearings,
)
from ALB.config import FPBConfig


def _make_cfg(**overrides):
    cfg = FPBConfig(
        e=0.25,
        angle=0.0,
        freq=2000.0,
        lx=70.0,
        lz=2.0,
        nx=15,
        nz=11,
        coe=False,
        max_iter=20,
        error_set=1e-7,
        iter_method="newton",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


class TestTiltingPadMultiPad(unittest.TestCase):
    def test_multipad_assembly_pressure_fields(self):
        """Build a MultiPad of TiltingPadHydrodynamicPad directly and check pressures."""
        cfg = _make_cfg()
        pads = tilting_pads_bearings(
            cfg,
            tilts=[
                (0.010, 0.000),
                (-0.010, 0.000),
                (0.000, 0.008),
                (0.000, -0.008),
            ],
        )
        self.assertEqual(len(pads), 4)
        for pad in pads.values():
            self.assertIsInstance(pad, TiltingPadHydrodynamicPad)

        mp = MultiPad(*pads.values())
        mp.init()
        mp.input(uxy=[0.25, 0.0], uxyt=[0.0, 0.0], t=0.0, nodim=True)
        out = mp.output()

        self.assertIn("force", out)
        self.assertTrue(np.all(np.isfinite(out["force"])))

        fields = get_pad_pressure_fields(pads)
        self.assertEqual(set(fields.keys()), {"up", "down", "right", "left"})
        max_pressures = []
        for name, field in fields.items():
            self.assertIsNotNone(field, msg=name)
            self.assertEqual(field.ndim, 2, msg=name)
            self.assertGreater(field.size, 0, msg=name)
            self.assertTrue(np.all(np.isfinite(field)), msg=name)
            max_pressures.append(float(np.max(field)))
        # At least one loaded pad must develop positive hydrodynamic pressure.
        self.assertGreater(max(max_pressures), 0.0)

    def test_tilting_pads_bearing_factory_returns_multipad(self):
        cfg = _make_cfg()
        mp = tilting_pads_bearing(cfg)
        self.assertIsInstance(mp, MultiPad)
        self.assertTrue(hasattr(mp, "pads"))
        self.assertEqual(len(mp.pads), 4)

    def test_solve_equilibrium_with_multipad(self):
        cfg = _make_cfg(e=0.2)
        pads = tilting_pads_bearings(cfg)
        mp = MultiPad(*pads.values())

        out = solve_tilting_pad_equilibrium(
            mp,
            pads,
            uxy=[0.2, 0.0],
            uxyt=[0.0, 0.0],
            t=0.0,
            nodim=True,
            max_iter=4,
            tol=5e-3,
            gain=0.15,
        )

        self.assertIn("tilt_equilibrium", out)
        eq = out["tilt_equilibrium"]
        self.assertGreaterEqual(eq["iterations"], 1)
        self.assertEqual(set(eq["tilts"].keys()), {"up", "down", "right", "left"})
        for tx, tz in eq["tilts"].values():
            self.assertTrue(np.isfinite(tx))
            self.assertTrue(np.isfinite(tz))

        # Pressure fields after final solve must be finite; at least one pad loaded.
        fields = get_pad_pressure_fields(pads)
        max_pressures = []
        for name, field in fields.items():
            self.assertTrue(np.all(np.isfinite(field)), msg=name)
            max_pressures.append(float(np.max(field)))
        self.assertGreater(max(max_pressures), 0.0)

    def test_pad_update_tilt_step_adjusts_tilt(self):
        cfg = _make_cfg()
        pads = tilting_pads_bearings(cfg)
        mp = MultiPad(*pads.values())
        mp.init()
        mp.input(uxy=[0.25, 0.0], uxyt=[0.0, 0.0], t=0.0, nodim=True)
        mp.output()

        # Pick the most-loaded pad so the tilt update has a non-zero moment.
        fields = get_pad_pressure_fields(pads)
        loaded_name = max(fields, key=lambda k: float(np.max(fields[k])))
        pad = pads[loaded_name]
        before = (pad.tilt_x, pad.tilt_z)
        step = pad.update_tilt_step(gain_x=0.1, gain_z=0.1, tilt_clip=0.2)
        after = (pad.tilt_x, pad.tilt_z)

        self.assertIn("offset_x", step)
        self.assertIn("offset_z", step)
        self.assertTrue(np.isfinite(step["moment_x"]))
        self.assertTrue(np.isfinite(step["moment_z"]))
        self.assertNotEqual(before, after)

    def test_left_pad_can_unload_without_negative_film_thickness(self):
        cfg = _make_cfg()
        pads = tilting_pads_bearings(cfg)
        mp = MultiPad(*pads.values())

        out = solve_tilting_pad_equilibrium(
            mp,
            pads,
            uxy=[0.6, -0.7],
            uxyt=[0.0, 0.0],
            t=0.0,
            nodim=True,
            max_iter=40,
            tol=5e-3,
            gain=0.15,
            gain_max=0.35,
            tilt_clip=2.0,
        )

        self.assertTrue(out["tilt_equilibrium"]["converged"])

        fields = get_pad_pressure_fields(pads)
        left_pad = pads["left"]
        left_h = np.array([node.h for node in left_pad.main_model.nodes.values()])
        left_p = np.asarray(fields["left"], dtype=float)
        down_p = np.asarray(fields["down"], dtype=float)

        self.assertGreater(left_pad.tilt_x, 0.5)
        self.assertGreater(np.min(left_h), 0.0)
        self.assertFalse(np.any(np.isclose(left_h, left_pad.min_h)))
        self.assertLessEqual(np.max(left_p), 1e-10)
        self.assertFalse(np.any(left_p > 1e-12))
        self.assertGreater(np.max(down_p), 1.0)


if __name__ == "__main__":
    unittest.main()
