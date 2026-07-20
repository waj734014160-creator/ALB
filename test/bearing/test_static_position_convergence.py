import unittest

import numpy as np

from ALB.bearing import StaticPosition
from ALB.physics.film import FilmSystem
from ALB.thermal import NodimThermalHydroBearing


class _FakeSignal:
    pass


class _LinearBearing:
    def __init__(self, inner_finished=True):
        self.inner_finished = inner_finished
        self.current = np.zeros(2, dtype=float)
        self.output_kwargs = []
        self.saved = []
        self.init_count = 0

    def init(self):
        self.init_count += 1

    def input(self, uxy, uxyt, t, nodim=True):
        self.current = np.asarray(uxy, dtype=float)

    def output(self, **kwargs):
        self.output_kwargs.append(dict(kwargs))
        return {}

    def calc_capacity(self, calc=True, nodim=True):
        force = np.array([2.0 * self.current[0], 1.0 + 3.0 * self.current[1]])
        return force if nodim else 10.0 * force

    def calc_is_finished(self):
        if callable(self.inner_finished):
            return bool(self.inner_finished(self.current))
        return self.inner_finished

    def save(self, path=None, name=None, tofile=False):
        saved = {"path": path, "name": name, "current": self.current.copy()}
        self.saved.append(saved)
        return saved


class _DummyMainModel:
    def __init__(self, finished=False):
        self.signal = _FakeSignal()
        self.finished = finished
        self.output_count = 0

    def init(self):
        pass

    def reset_adaptive_damp(self):
        pass

    def output(self, **kwargs):
        self.output_count += 1

    def calc_is_finished(self):
        return self.finished

    def update_to_nodes(self):
        pass


class _DummySimpleModel:
    def __init__(self, finished):
        self.signal = _FakeSignal()
        self.finished = finished

    def calc_is_finished(self):
        return self.finished


class _DummyBearingStatus:
    def __init__(self, finished=True):
        self.finished = finished

    def calc_is_finished(self):
        return self.finished


class TestStaticPositionConvergence(unittest.TestCase):
    def test_converged_initial_point_is_not_stepped_and_output_gets_nodim(self):
        bearing = _LinearBearing(inner_finished=True)
        static_position = StaticPosition(
            bearing, iter_num=5, error_set=1e-12, damp=1.0, delta=1e-4
        )

        ex, ey = static_position.run(0.0, -1.0, ex=0.0, ey=0.0, nodim=True)

        self.assertEqual((ex, ey), (0.0, 0.0))
        self.assertEqual(len(bearing.output_kwargs), 1)
        self.assertTrue(all(call.get("nodim") is True for call in bearing.output_kwargs))
        row = static_position.data.iloc[-1]
        self.assertTrue(bool(row["finished"]))
        self.assertTrue(bool(row["inner_converged"]))
        self.assertEqual(row["stop_reason"], "converged")
        self.assertAlmostEqual(float(row["error"]), 0.0)

    def test_final_row_is_recomputed_at_updated_coordinate(self):
        bearing = _LinearBearing(inner_finished=True)
        static_position = StaticPosition(
            bearing, iter_num=1, error_set=1e-8, damp=1.0, delta=1e-6
        )

        ex, ey = static_position.run(0.0, -1.0, ex=0.2, ey=-0.1, nodim=True)

        self.assertAlmostEqual(ex, 0.0, places=8)
        self.assertAlmostEqual(ey, 0.0, places=8)
        row = static_position.data.iloc[-1]
        self.assertTrue(bool(row["finished"]))
        self.assertEqual(row["stop_reason"], "converged")
        self.assertAlmostEqual(float(row["ex"]), 0.0, places=8)
        self.assertAlmostEqual(float(row["ey"]), 0.0, places=8)
        self.assertAlmostEqual(float(row["Fx"]), 0.0, places=8)
        self.assertAlmostEqual(float(row["Fy"]), 1.0, places=8)
        self.assertAlmostEqual(float(row["error"]), 0.0, places=8)
        np.testing.assert_allclose(
            bearing.saved[-1]["current"], np.array([0.0, 0.0]), atol=1e-10
        )

    def test_inner_nonconvergence_stops_before_jacobian_update(self):
        bearing = _LinearBearing(inner_finished=False)
        static_position = StaticPosition(
            bearing, iter_num=5, error_set=1e-12, damp=1.0, delta=1e-4
        )

        ex, ey = static_position.run(0.0, -1.0, ex=0.2, ey=-0.1, nodim=True)

        self.assertEqual((ex, ey), (0.2, -0.1))
        self.assertEqual(len(bearing.output_kwargs), 1)
        row = static_position.data.iloc[-1]
        self.assertFalse(bool(row["finished"]))
        self.assertFalse(bool(row["inner_converged"]))
        self.assertEqual(row["stop_reason"], "inner_not_converged")

    def test_dx_inner_nonconvergence_stops_and_restores_base_state(self):
        delta = 1e-4

        def finished(point):
            return not np.allclose(point, np.array([0.2 + delta, -0.1]), atol=1e-12)

        bearing = _LinearBearing(inner_finished=finished)
        static_position = StaticPosition(
            bearing, iter_num=5, error_set=1e-12, damp=1.0, delta=delta
        )

        ex, ey = static_position.run(0.0, -1.0, ex=0.2, ey=-0.1, nodim=True)

        self.assertEqual((ex, ey), (0.2, -0.1))
        self.assertEqual(len(bearing.output_kwargs), 3)
        row = static_position.data.iloc[-1]
        self.assertFalse(bool(row["finished"]))
        self.assertTrue(bool(row["inner_converged"]))
        self.assertEqual(row["stop_reason"], "inner_not_converged_dx")
        np.testing.assert_allclose(
            bearing.saved[-1]["current"], np.array([0.2, -0.1]), atol=1e-12
        )

    def test_dy_inner_nonconvergence_stops_and_restores_base_state(self):
        delta = 1e-4

        def finished(point):
            return not np.allclose(point, np.array([0.2, -0.1 + delta]), atol=1e-12)

        bearing = _LinearBearing(inner_finished=finished)
        static_position = StaticPosition(
            bearing, iter_num=5, error_set=1e-12, damp=1.0, delta=delta
        )

        ex, ey = static_position.run(0.0, -1.0, ex=0.2, ey=-0.1, nodim=True)

        self.assertEqual((ex, ey), (0.2, -0.1))
        self.assertEqual(len(bearing.output_kwargs), 4)
        row = static_position.data.iloc[-1]
        self.assertFalse(bool(row["finished"]))
        self.assertTrue(bool(row["inner_converged"]))
        self.assertEqual(row["stop_reason"], "inner_not_converged_dy")
        np.testing.assert_allclose(
            bearing.saved[-1]["current"], np.array([0.2, -0.1]), atol=1e-12
        )

    def test_film_system_requires_all_simple_models_to_converge(self):
        model = _DummyMainModel(finished=True)
        film_system = object.__new__(FilmSystem)
        film_system.main_model = model
        film_system.simple_models = [_DummySimpleModel(True), _DummySimpleModel(False)]

        self.assertFalse(film_system.calc_is_finished())

    def test_film_system_records_max_iter_nonconvergence(self):
        model = _DummyMainModel(finished=False)
        film_system = object.__new__(FilmSystem)
        film_system.main_model = model
        film_system.simple_models = []
        film_system.max_iter = 2
        film_system.final_iter = 0
        film_system.last_converged = False

        film_system.solve()

        self.assertFalse(film_system.last_converged)
        self.assertEqual(film_system.final_iter, 2)
        self.assertEqual(model.output_count, 2)

    def test_thermal_status_requires_latest_thermal_convergence(self):
        wrapper = object.__new__(NodimThermalHydroBearing)
        wrapper.bearing = _DummyBearingStatus(finished=True)
        wrapper._last_thermal = {"converged": False}

        self.assertFalse(wrapper.calc_is_finished())

        wrapper._last_thermal = {"converged": True}
        self.assertTrue(wrapper.calc_is_finished())


if __name__ == "__main__":
    unittest.main()
