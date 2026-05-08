# coding: utf-8

import copy

import numpy as np
import pandas as pd
from tqdm import tqdm

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


def orbitime(freq, n, pt=20):
    """
    generate time iterator
    :param freq: frequency
    :param n: number of cycles
    :param pt: points per cycle
    :return: time iterator
    """
    from ALB.base import TimeIter

    num = n * pt
    dt = 1 / (freq * pt)
    end = num * dt
    return TimeIter(0, end, num)

