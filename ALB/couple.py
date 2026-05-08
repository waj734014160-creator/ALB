# coding: utf-8

import numpy as np
import pandas as pd
from tqdm import tqdm

from ALB.base import BaseCSystem, BaseSystem
from ALB.rotor import Gravity, StaicLoad

from .results import DataFrameResult, SaveTreeNode

# from ALB.logger import logger
from .rotor import RossRotor, SingleRotor, UnbalancedExcitation
from .tool import cvstack


class RotorBearingCouple(BaseSystem):
    """
    Couple a single rotor model with one bearing model for co-simulation.
    """

    def __init__(self, rotor: SingleRotor, bearing, time_iter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rotor = rotor
        self.bearing = bearing
        self._time_iter = time_iter
        self._result = {"rotor": [], "bearing": []}

    def solve(self, **kwargs):
        self.rotor.set_dt(self._time_iter.dt)
        self.rotor.set_rpm(1000)
        for ts in self._time_iter():
            bearing_output = self.bearing.output()
            force = bearing_output["force"]
            # logger.info("force:{}".format(force))

            w = bearing_output["w"]
            self.rotor.set_rpm(w)

            self.rotor.input(force, **kwargs)

            rotoru = self.rotor.output(ts, **kwargs)
            # logger.info("rotor:{}".format(rotoru))

            self.bearing.input(rotoru, np.zeros_like(rotoru))

            self._result["rotor"].append(rotoru)


class RsRotorBearingCouple(BaseCSystem):
    """
    Couple a ROSS rotor model with multiple bearing models.
    """

    def __init__(self, rotor: RossRotor, time_iter, *bearings, **kwargs):
        """
        options:
            save_path:default="./rotor_bearing_couple"
        """
        super().__init__()
        self.rotor = rotor
        self.bearings = list(bearings)
        self.signal.children = [bearing.signal for bearing in self.bearings]
        self.signal.add_child(self.rotor.signal)
        self.forces = []
        self._time_iter = time_iter
        self._result = {}
        self._save_path = kwargs.get("save_path", "rotor_bearing_couple")
        self._fnode_links = None
        self._bnode_links = None
        self._forceu0 = None
        self._forceu1 = None
        self._forcef0 = None
        self._forcef1 = None
        self._forcen0 = None
        self._forcen1 = None

        self._rp = None
        self._nt = None
        self._ts = None

    @property
    def results(self):
        return self._result

    def add_bearing(self, bearing):
        self.bearings.append(bearing)
        self.signal.children.append(bearing.signal)
        bearing.signal.father = self.signal

    def init(self, **kwargs):
        self.rotor.init()
        for bearing in self.bearings:
            bearing.init()
        self._fnode_links = get_all_attribute_values(self.forces, "node_link")
        self._bnode_links = get_all_attribute_values(self.bearings, "node_link")
        self._fnode_links = np.hstack(
            [
                np.array(self._fnode_links, dtype=np.int32),
                np.array(self._bnode_links, dtype=np.int32),
            ]
        )
        if len(self.forces) == 0:
            self._forceu0 = []
        else:
            self._forceu0 = np.vstack([force(t=0) for force in self.forces])
        self._rp = self.rotor.output(self._bnode_links)
        for num, bearing in enumerate(self.bearings):
            self._result["bearing" + str(num)] = pd.DataFrame(
                columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
            )
        self._forcef0 = []
        for num, bearing in enumerate(self.bearings):
            rp_uxy = self._rp["uxy"][num]
            rp_uxyt = self._rp["uxyt"][num]
            bearing.input(uxy=rp_uxy, uxyt=rp_uxyt, t=0)
            self._forcef0.append(bearing.output()["force"])
        self._forcef0 = np.array(self._forcef0)
        self._forcen0 = cvstack([np.array(self._forceu0), np.array(self._forcef0)])
        self._nt = 0

    def add_unbalance(
        self, node_link, phase=0, t_max: float = 1, m=0, freq=0, e=0, no_step=False
    ):
        """
        Add an unbalance excitation load to specified rotor node(s).

        :param node_link: Rotor node index or list of node indices.
        :param phase: Initial phase angle of the unbalance excitation.
        :param t_max: Maximum active time for excitation.
        :param m: Equivalent unbalance mass.
        :param freq: Excitation frequency.
        :param e: Eccentricity radius of the unbalance mass.
        :param no_step: Whether to disable step gating in excitation profile.
        """
        ube = UnbalancedExcitation(phase, t_max, m, freq, e, no_step=False)
        ube.node_link = node_link
        self.forces.append(ube)

    def add_static_force(self, force, node_link):
        force = StaicLoad(force)
        force.node_link = node_link
        self.forces.append(force)

    def add_gravity(self, g=9.8):
        rotor = self.rotor._rotor
        she = rotor.shaft_elements
        she_n = list(range(len(she) + 1))
        she_m = [el.m for el in she]
        node_m = np.zeros(len(she_m) + 1)
        for i in range(len(she_m)):
            node_m[i] += she_m[i] / 2
            node_m[i + 1] += she_m[i] / 2
        for el in rotor.disk_elements:
            node_m[el.n] += el.m
        gravity = Gravity(g, node_m)
        self.forces.append(gravity)
        gravity.node_link = she_n

    def solve(self, **kwargs):
        """
        :param kwargs:
        Optional arguments:
            uxy: bool
                Save translational displacement output.
            uxyt: bool
                Save translational velocity output.
            save_all: bool
                Save all intermediate state data.
            init: bool
                Reinitialize rotor-bearing states before solving.
        """
        if kwargs.get("init", True):
            self.init(**kwargs)

        positon = kwargs.get("position", 0)

        progress_bar = tqdm(
            enumerate(self._time_iter()),
            total=self._time_iter.num + 1,
            position=positon,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
        )
        for nt, ts in progress_bar:
            self.output(ts, **kwargs)

    def input(self, *args, **kwargs):
        """
        Input interface reserved for compatibility with BaseCSystem.
        """
        pass

    def output(self, ts=None, **kwargs):
        """
        Advance one coupling time step and update rotor and bearing states.
        """
        if ts is None:
            ts = self._time_iter.t_list[self._nt]
        self._ts = ts
        uxy_n1 = self._rp["uxy"]
        uxyt_n1 = self._rp["uxyt"]
        self._forceu1 = cvstack([force(ts) for force in self.forces])
        self._forcef1 = []
        for num, bearing in enumerate(self.bearings):
            bearing.input(uxy=uxy_n1[num], uxyt=uxyt_n1[num], t=ts)
            self._forcef1.append(bearing.output()["force"])
        self._forcef1 = np.array(self._forcef1)

        self._forcen0 = cvstack((self._forceu0, self._forcef0))
        self._forcen1 = cvstack((self._forceu1, self._forcef1))
        self.rotor.input_force2node(
            ts, self._forcen1, self._fnode_links, force0=self._forcen0
        )
        self._rp = self.rotor.output(self._bnode_links)
        self._forcen0 = self._forcen1
        self._forceu0 = self._forceu1
        self._forcef0 = self._forcef1

        self._nt += 1
        self.signal.lead_loop("finish_signal")

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        if path is None:
            path = self._save_path
        if name is None:
            name = "RBC"
        res = {name + "_" + key: data for key, data in self._result.items()}
        res = DataFrameResult(res)
        parent_node = SaveTreeNode(path, res)
        rotor_node = self.rotor.save(tofile=False)
        bearing_nodes = [
            bearing.save(
                path=type(bearing).__name__ + str(bearing.node_link),
                name=name,
                tofile=False,
            )
            for num, bearing in enumerate(self.bearings)
        ]
        parent_node.add_child(rotor_node)
        parent_node.add_children(bearing_nodes)
        if tofile:
            parent_node.save_to_file()
        return parent_node

    def finish_signal(self):
        uxy_n1 = self._rp["uxy"]
        uxyt_n1 = self._rp["uxyt"]
        for num, bearing in enumerate(self.bearings):
            res = self._result["bearing" + str(num)]
            res.loc[len(res)] = np.hstack(
                (
                    self._ts,
                    uxy_n1[num],
                    uxyt_n1[num],
                    self._forcef1[num][0],
                    self._forcef1[num][1],
                )
            )


def get_all_attribute_values(objects, attribute_name):
    """
    Collect an attribute from each object and flatten list-type attributes.
    """
    values = []
    if not isinstance(objects, list):
        raise Exception("objects must be a list")
    for obj in objects:
        attribute_value = getattr(obj, attribute_name)
        if isinstance(attribute_value, list):
            values.extend(attribute_value)
        else:
            values.append(attribute_value)
    return values
