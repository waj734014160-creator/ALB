# coding: utf-8

import copy
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from tqdm import tqdm

from ALB.config import TimeGridConfig
from ALB.results import SaveTreeNode
from ALB.tool import recognize_kc


class EllipseTrack:
    """EllipseTrack interface."""
    def __init__(self, a, b, freq, a0=0, b0=0, f0=0, resolution=100, vf=1):
        """
        :param a: major axis
        :param b: minor axis
        :param freq: frequency, Hz
        :param a0: x offset
        :param b0: y offset
        :param fa: x direction phase offset
        :param fb: y direction phase offset
        """
        self.a = a
        self.b = b
        self.a0 = a0
        self.b0 = b0
        self.freq = freq * vf
        self.f0 = f0
        self.resolution = resolution
        self.inpinf = pd.DataFrame(
            columns=["a", "b", "freq", "a0", "b0", "f0", "resolution"]
        )
        self.inpinf.loc[0] = [a, b, freq, a0, b0, f0, resolution]

    def generate_track(self, t):
        """
        Generate points on the elliptical trajectory
        :return: Returns a numpy array containing all points on the trajectory, each point is an (x, y) coordinate,
        and returns the corresponding displacement, velocity, and acceleration
        """
        try:
            if hasattr(t, "t_list"):
                t = t.t_list
            t = np.array(t)
        except ValueError as exc:
            raise ValueError("t must be a list or array") from exc
        ux = (
            self.a * np.cos(2 * np.pi * self.freq * t) * np.cos(self.f0)
            - self.b * np.sin(2 * np.pi * self.freq * t) * np.sin(self.f0)
            + self.a0
        )
        uy = (
            self.a * np.cos(2 * np.pi * self.freq * t) * np.sin(self.f0)
            + self.b * np.sin(2 * np.pi * self.freq * t) * np.cos(self.f0)
            + self.b0
        )
        vx = (
            -2
            * np.pi
            * self.freq
            * (
                self.a * np.sin(2 * np.pi * self.freq * t) * np.cos(self.f0)
                + self.b * np.cos(2 * np.pi * self.freq * t) * np.sin(self.f0)
            )
        )
        vy = (
            -2
            * np.pi
            * self.freq
            * (
                self.a * np.sin(2 * np.pi * self.freq * t) * np.sin(self.f0)
                - self.b * np.cos(2 * np.pi * self.freq * t) * np.cos(self.f0)
            )
        )
        ax = (
            -4
            * np.pi**2
            * self.freq**2
            * (
                self.a * np.cos(2 * np.pi * self.freq * t) * np.cos(self.f0)
                - self.b * np.sin(2 * np.pi * self.freq * t) * np.sin(self.f0)
            )
        )
        ay = (
            -4
            * np.pi**2
            * self.freq**2
            * (
                self.a * np.cos(2 * np.pi * self.freq * t) * np.sin(self.f0)
                + self.b * np.sin(2 * np.pi * self.freq * t) * np.cos(self.f0)
            )
        )

        u = np.array([ux, uy]).T
        a = np.array([ax, ay]).T
        v = np.array([vx, vy]).T
        return u, v, a

    def generate_itrack(self, t):
        """
        Generate reverse elliptical trajectory
        :return: Returns a numpy array containing all points on the trajectory, each point is an (x, y) coordinate,
        and returns the corresponding displacement, velocity, and acceleration
        """
        self.freq = -self.freq
        res = self.generate_track(t)
        self.freq = -self.freq
        return res


class BearingForceTrack:
    """BearingForceTrack interface."""
    def __init__(self, bearing, t, u, v, a):
        """
        Initialize the BearingForceTrack.
        :param bearing: The bearing object.
        :param t: Time vector.
        :param u: Displacement vector.
        :param v: Velocity vector.
        :param a: Acceleration vector.
        """
        self.t = t
        self.bearing = bearing
        self.u = u
        self.v = v
        self.a = a
        self.bearing_forces = pd.DataFrame(
            columns=["t", "ux", "uy", "vx", "vy", "ax", "ay", "fx", "fy"]
        )

    def calculate_bearing_force(self, **kwargs):
        """
        Calculate the bearing forces along the trajectory.
        :param kwargs: Keyword arguments, e.g., nodim for non-dimensional calculation.
        """
        nodim = kwargs.get("nodim", False)
        progress_bar = tqdm(
            zip(self.t, self.u, self.v, self.a),
            total=len(self.u),
            desc="Calculating bearing forces",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
        )
        for t, u, v, a in progress_bar:
            self.bearing.input(uxy=u, uxyt=v, uxytt=a, t=t, nodim=nodim)
            output = self.bearing.output()
            self.bearing_forces.loc[len(self.bearing_forces)] = np.hstack(
                (t, u, v, a, output["force"])
            )

    def run(self, **kwargs):
        """
        Run the bearing force calculation.
        :param kwargs: Keyword arguments passed to calculate_bearing_force.
        :return: DataFrame with bearing forces and kinematics.
        """
        self.calculate_bearing_force(**kwargs)
        return self.bearing_forces

    def plot(self, show=True):
        """
        Plot the trajectory and its corresponding bearing force
        return: return the main plot
        """
        import matplotlib.pyplot as plt

        # Plot the trajectory and bearing force as two subplots
        fig, ax = plt.subplots(1, 2, figsize=(10, 5))
        ax[0].plot(self.u[:, 0], self.u[:, 1])
        ax[0].set_xlabel("x")
        ax[0].set_ylabel("y")
        ax[0].set_title("track")
        ax[1].plot(self.bearing_forces["fx"], self.bearing_forces["fy"])
        ax[1].set_xlabel("fx")
        ax[1].set_ylabel("fy")
        ax[1].set_title("bearing force")
        if show:
            plt.show()
        return fig, ax

    def save(self, path, name="bearing_forces.pkl"):
        """
        Save the BearingForceTrack object to a pickle file.
        :param path: The directory path to save the file.
        :param name: The name of the file.
        """
        node = SaveTreeNode("bearing_forces", self)
        if not name.endswith(".pkl"):
            name += ".pkl"
        node.save_to_pickle(path, name)

    @staticmethod
    def load(path):
        """
        Load a BearingForceTrack object from a pickle file.
        :param path: The path to the pickle file.
        :return: The loaded BearingForceTrack object.
        """
        node = SaveTreeNode.load_pickle(path)
        if isinstance(node.data, BearingForceTrack):
            return node.data
        else:
            raise ValueError("The data in the node is not BearingForceTrack")


def test_bearing_orbit(time_iter, bearing, et, **kwargs):
    """
    test bearing orbit
    :param time_iter: time iterator
    :param bearing: bearing
    :param et: ellipse track
    :param repeat: repeat times
    :param kwargs: other parameters of recognize_kc
    start: the start of the time, 0-1, default 0
    end: the end of the time, 0-1, default 1
    repeat: repeat the uxy and fxy for more accurate FFT, default 0
    n : the point number of a cycle, default 1/freq/dt
    :return: result, including bearing force track, and hkc,{'bft': bft0, 'ibft': bft1, 'hkc': hkc}
    """
    dt = time_iter.dt
    freq = et.freq
    n = kwargs.get("pt", 1 / freq / dt)
    repeat = kwargs.get("repeat", 0)
    u0, v0, a0 = et.generate_track(time_iter)
    u1, v1, a1 = et.generate_itrack(time_iter)
    bearing1 = copy.deepcopy(bearing)
    print("Synchronous vortex trajectories")
    bft0 = BearingForceTrack(bearing, time_iter.t_list, u0, v0, a0)
    bft0.run()
    f0 = bft0.bearing_forces[["fx", "fy"]].to_numpy()
    print("Inverse vortex trajectories")
    bft1 = BearingForceTrack(bearing1, time_iter.t_list, u1, v1, a1)
    bft1.run()
    f1 = bft1.bearing_forces[["fx", "fy"]].to_numpy()
    if not np.isclose(n, np.around(n), atol=0, rtol=1e-10) and repeat != 0:
        raise ValueError(
            "n={},The time iterator is not compatible with the frequency".format(n)
        )
    else:
        n = int(np.around(n))
    if repeat > 0:
        u0 = np.tile(u0[-n:, :], (repeat, 1))
        u1 = np.tile(u1[-n:, :], (repeat, 1))
        f0 = np.tile(f0[-n:, :], (repeat, 1))
        f1 = np.tile(f1[-n:, :], (repeat, 1))
    hkc = recognize_kc(time_iter.t_list, freq, u0.T, -f0.T, u1.T, -f1.T, **kwargs)
    return {"bft": bft0, "ibft": bft1, "hkc": hkc}


def _emit_progress(progress_callback, value, message):
    """Emit bounded integer progress for orbit calculations."""

    if progress_callback is not None:
        progress_callback(max(0, min(100, int(value))), message)


def _calculate_bearing_force_track(bearing, t, u, v, a, progress_callback=None):
    """Calculate a bearing force track without a tqdm progress bar."""

    bft = BearingForceTrack(bearing, t, u, v, a)
    for index, (ti, ui, vi, ai) in enumerate(zip(t, u, v, a), start=1):
        bearing.input(uxy=ui, uxyt=vi, uxytt=ai, t=ti, nodim=False)
        output = bearing.output()
        bft.bearing_forces.loc[len(bft.bearing_forces)] = np.hstack(
            (ti, ui, vi, ai, output["force"])
        )
        if progress_callback is not None:
            progress_callback(index, len(u))
    return bft


def test_bearing_orbit_parallel(time_iter, bearing, et, **kwargs):
    """
    Test bearing orbit with parallel forward and reverse vortex force solves.

    This function keeps the same result contract as ``test_bearing_orbit`` while
    using two independent bearing instances for the forward and reverse
    trajectories. ``progress_callback`` receives ``(percent, message)`` if
    provided. ``max_workers`` defaults to 2 and is not forwarded to
    ``recognize_kc``.
    """

    progress_callback = kwargs.pop("progress_callback", None)
    max_workers = max(1, int(kwargs.pop("max_workers", 2)))
    dt = time_iter.dt
    freq = et.freq
    n = kwargs.get("pt", 1 / freq / dt)
    repeat = kwargs.get("repeat", 0)
    u0, v0, a0 = et.generate_track(time_iter)
    u1, v1, a1 = et.generate_itrack(time_iter)
    bearing1 = copy.deepcopy(bearing)

    _emit_progress(progress_callback, 0, "Initializing parallel orbit calculation")
    _emit_progress(progress_callback, 5, "Generating forward and reverse tracks")

    progress_total = max(1, len(u0) + len(u1))
    progress_state = {"completed": 0, "last_value": -1}
    progress_lock = threading.Lock()

    def _on_force_step(_index, _total):
        with progress_lock:
            progress_state["completed"] += 1
            completed = progress_state["completed"]
            value = 5 + 90 * completed // progress_total
            if value != progress_state["last_value"]:
                _emit_progress(
                    progress_callback,
                    value,
                    f"Parallel vortex force calculation {completed}/{progress_total}",
                )
                progress_state["last_value"] = value

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _calculate_bearing_force_track,
                bearing,
                time_iter.t_list,
                u0,
                v0,
                a0,
                _on_force_step,
            ): "bft",
            executor.submit(
                _calculate_bearing_force_track,
                bearing1,
                time_iter.t_list,
                u1,
                v1,
                a1,
                _on_force_step,
            ): "ibft",
        }
        results = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    bft0 = results["bft"]
    bft1 = results["ibft"]
    f0 = bft0.bearing_forces[["fx", "fy"]].to_numpy()
    f1 = bft1.bearing_forces[["fx", "fy"]].to_numpy()

    if not np.isclose(n, np.around(n), atol=0, rtol=1e-10) and repeat != 0:
        raise ValueError(
            "n={},The time iterator is not compatible with the frequency".format(n)
        )
    else:
        n = int(np.around(n))
    if repeat > 0:
        u0 = np.tile(u0[-n:, :], (repeat, 1))
        u1 = np.tile(u1[-n:, :], (repeat, 1))
        f0 = np.tile(f0[-n:, :], (repeat, 1))
        f1 = np.tile(f1[-n:, :], (repeat, 1))

    _emit_progress(progress_callback, 98, "Identifying stiffness and damping matrices")
    hkc = recognize_kc(time_iter.t_list, freq, u0.T, -f0.T, u1.T, -f1.T, **kwargs)
    _emit_progress(progress_callback, 100, "Dynamic orbit calculation complete")
    return {"bft": bft0, "ibft": bft1, "hkc": hkc}


def orbitime(
    freq=None,
    n=None,
    pt=None,
    *,
    mode=None,
    cycles=None,
    points_per_cycle=None,
    dt=None,
    steps=None,
):
    """Build a time iterator from canonical or legacy orbit settings.

    The positional ``freq, n, pt`` contract remains available for legacy
    callers.  Canonical callers select either ``cycle_points`` or ``fixed_dt``
    through :class:`ALB.config.TimeGridConfig` fields.
    """

    from ALB.base import TimeIterDt

    canonical_values = any(
        value is not None
        for value in (mode, cycles, points_per_cycle, dt, steps)
    )
    if canonical_values:
        if n is not None or pt is not None:
            raise ValueError(
                "canonical time-grid fields cannot be combined with legacy n/pt"
            )
        config = TimeGridConfig(
            mode=mode,
            freq=freq,
            cycles=cycles,
            points_per_cycle=points_per_cycle,
            dt=dt,
            steps=steps,
        )
    else:
        if n is None:
            raise ValueError("legacy orbitime requires n")
        config = TimeGridConfig.from_dict(
            {"freq": freq, "n": n, "pt": 20 if pt is None else pt}
        )
    resolved = config.resolve()
    return TimeIterDt(dt=resolved.dt, num=resolved.steps)

