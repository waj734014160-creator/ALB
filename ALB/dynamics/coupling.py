# coding: utf-8

from decimal import Decimal

import numpy as np
import pandas as pd
from tqdm import tqdm

from ALB.core.component import BaseCSystem, BaseSystem
from ALB.core.lifecycle import LifecycleState
from ALB.core.validation import require_unit_system, validate_bearing_output
from ALB.contracts import ResultBundle, StepContext
from ALB.dynamics.rotor import Gravity, StaticLoad

# from ALB.infrastructure.logging import logger
from .rotor import RossRotor, SingleRotor, UnbalancedExcitation
from .coupling_runtime import CouplingStepRuntime, coupling_snapshot
from .coupling_results import build_coupling_save_tree
from ALB.core.numerics.arrays import vertical_stack_nonempty


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
    """Couple a ROSS rotor with bearings using exactly-once step commits.

    A failure after component mutation invalidates the coupler. Call ``init()``
    before reading or advancing again so a partially applied physical step
    cannot be retried as if it were untouched.
    """

    def __init__(self, rotor: RossRotor, time_iter, *bearings, **kwargs):
        """
        options:
            save_path:default="./rotor_bearing_couple"
        """
        super().__init__()
        self.rotor = rotor
        self.bearings = list(bearings)
        for bearing in self.bearings:
            self._validate_bearing(bearing)
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
        self._last_output = None
        self._runtime = CouplingStepRuntime()
        self._step_ledger = self._runtime.ledger
        self._valid = False

    @property
    def results(self):
        self._require_valid("reading results")
        return self._result

    def _require_valid(self, operation: str) -> None:
        """Reject access to state that may contain a partially applied step."""

        if not self._runtime.is_valid:
            raise RuntimeError(
                f"coupling state is invalid; call init() before {operation}"
            )

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the shared coupled-runtime state."""

        return self._runtime.state

    def _invalidate_runtime(self) -> None:
        """Block access after a partial step or a topology change."""

        self._runtime.fail()
        self._valid = False
        self._last_output = None

    def _invalidate_topology(self) -> None:
        """Require a fresh init after the coupled component graph changes."""

        self._invalidate_runtime()
        self._fnode_links = None
        self._bnode_links = None

    def add_bearing(self, bearing):
        self._validate_bearing(bearing)
        self.bearings.append(bearing)
        self.signal.children.append(bearing.signal)
        bearing.signal.father = self.signal
        self._invalidate_topology()

    @staticmethod
    def _validate_bearing(bearing):
        """Validate the minimum dimensional bearing integration contract."""

        for attribute in ("node_link", "signal", "init", "input", "output", "save"):
            if not hasattr(bearing, attribute):
                raise TypeError(f"bearing must provide '{attribute}'")
        require_unit_system(
            bearing,
            "dimensional",
            component_name="rotor-coupled bearing",
        )

    def init(self, **kwargs):
        self._invalidate_runtime()
        try:
            time_values = [float(value) for value in self._time_iter()]
            if not time_values:
                raise ValueError("rotor-bearing coupling time grid cannot be empty")
            initial_time = time_values[0]
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
                self._forceu0 = np.vstack(
                    [force(t=initial_time) for force in self.forces]
                )
            self._rp = self.rotor.output(self._bnode_links)
            for num, bearing in enumerate(self.bearings):
                self._result["bearing" + str(num)] = pd.DataFrame(
                    columns=["t", "ux", "uy", "uxt", "uyt", "fx", "fy"]
                )
            self._forcef0 = []
            for num, bearing in enumerate(self.bearings):
                rp_uxy = self._rp["uxy"][num]
                rp_uxyt = self._rp["uxyt"][num]
                bearing.input(uxy=rp_uxy, uxyt=rp_uxyt, t=initial_time)
                self._forcef0.append(validate_bearing_output(bearing.output()))
            self._forcef0 = np.array(self._forcef0)
            self._forcen0 = vertical_stack_nonempty(
                [np.array(self._forceu0), np.array(self._forcef0)]
            )
            self._nt = 0
            self._runtime.reset_ledger()
            self._step_ledger = self._runtime.ledger
            initial_context = StepContext(
                0, initial_time, self._time_iter.dt, "dimensional"
            )
            self._last_output = coupling_snapshot(
                self._rp,
                self._forcef0,
                self._forcen0,
                initial_context,
                initial=True,
            )
            self._runtime.publish_initial(initial_context)
        except BaseException:
            self._invalidate_runtime()
            raise
        self._valid = True

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
        ube = UnbalancedExcitation(phase, t_max, m, freq, e, no_step=no_step)
        ube.node_link = node_link
        self.forces.append(ube)
        self._invalidate_topology()

    def add_static_force(self, force, node_link):
        force = StaticLoad(force)
        force.node_link = node_link
        self.forces.append(force)
        self._invalidate_topology()

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
        self._invalidate_topology()

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

        time_values = [float(value) for value in self._time_iter()]
        initial_time = time_values[0]
        dt_decimal = Decimal(str(self._time_iter.dt))
        initial_decimal = Decimal(str(initial_time))
        target_times = [
            float(initial_decimal + dt_decimal * index)
            for index in range(1, len(time_values))
        ]
        progress_bar = tqdm(
            enumerate(target_times, start=1),
            total=len(target_times),
            position=positon,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
        )
        for nt, ts in progress_bar:
            context = StepContext(nt, ts, self._time_iter.dt, "dimensional")
            self.advance(context, **kwargs)

    def input(self, *args, **kwargs):
        """
        Input interface reserved for compatibility with BaseCSystem.
        """
        pass

    def advance(self, context: StepContext, **kwargs) -> ResultBundle:
        """Advance one coupled physical step and commit it exactly once."""

        self._require_valid("advancing")
        if not isinstance(context, StepContext):
            raise TypeError("context must be StepContext")
        if context.unit_system.value != "dimensional":
            raise ValueError("rotor-bearing coupling requires dimensional units")
        self._runtime.latch(context)
        try:
            with self._runtime.evaluation():
                ts = context.time
                self._ts = ts
                uxy_n1 = self._rp["uxy"]
                uxyt_n1 = self._rp["uxyt"]
                self._forceu1 = vertical_stack_nonempty(
                    [force(ts) for force in self.forces]
                )
                self._forcef1 = []
                for num, bearing in enumerate(self.bearings):
                    bearing.input(uxy=uxy_n1[num], uxyt=uxyt_n1[num], t=ts)
                    self._forcef1.append(validate_bearing_output(bearing.output()))
                self._forcef1 = np.array(self._forcef1)

                self._forcen0 = vertical_stack_nonempty((self._forceu0, self._forcef0))
                self._forcen1 = vertical_stack_nonempty((self._forceu1, self._forcef1))
                self.rotor.input_force2node(
                    ts, self._forcen1, self._fnode_links, force0=self._forcen0
                )
                self.rotor.advance()
                self._rp = self.rotor.output(self._bnode_links)
                self._forcen0 = self._forcen1
                self._forceu0 = self._forceu1
                self._forcef0 = self._forcef1

                self.signal.lead_loop("finish_signal")
                self._last_output = coupling_snapshot(
                    self._rp,
                    self._forcef1,
                    self._forcen1,
                    context,
                )
                self._runtime.commit(context)
                self._nt += 1
        except BaseException:
            self._invalidate_runtime()
            raise
        return self.output()

    def output(self) -> ResultBundle:
        """Read the most recent completed coupled result without advancing."""

        self._require_valid("reading output")
        self._runtime.lifecycle.require_output()
        assert self._last_output is not None
        return self._last_output

    def result_snapshot(self) -> ResultBundle:
        """Return the current immutable coupled result snapshot."""

        return self.output()

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        self._require_valid("saving results")
        if path is None:
            path = self._save_path
        if name is None:
            name = "RBC"
        return build_coupling_save_tree(
            self._result,
            self.rotor,
            self.bearings,
            path,
            name,
            tofile=tofile,
            writer=kwargs.get("writer"),
        )

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
