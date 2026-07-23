# -- coding: utf-8 --
import copy

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import ross as rs
import scipy
from scipy.linalg import expm

from ALB.core.component import BaseSimpleModel
from ALB.core.events import Signal
from ALB.core.lifecycle import LifecycleState, RuntimeLifecycle
from ALB.core.validation import finite_real_array, finite_real_time, finite_real_vector
from ALB.core.fem.base import BasePostProcess
from ALB.contracts import RotorLoadInput, UnitSystem

# from ALB.infrastructure.logging import logger
from ALB.dynamics.identification import pearson_similarity
from ALB.dynamics.rotor_layout import (
    RotorDofLayout,
    location_mapping_matrix,
    node_force_to_array as _nodeforce2array,
    normalize_node_indices,
)
from ALB.dynamics.rotor_results import (
    build_rotor_save_tree,
    build_time_response_results,
    extract_displacement_history,
)

_intpoint = np.array(
    [
        -0.932469514203152,
        -0.661209386466265,
        -0.238619186083,
        0.238619186083,
        0.661209386466265,
        0.932469514203152,
    ]
)
_weight = np.array(
    [
        0.171324492379170,
        0.360761573048139,
        0.467913934572691,
        0.467913934572691,
        0.360761573048139,
        0.171324492379170,
    ]
)


class BaseExcitation:
    """
    Excitation base class. Subclasses should implement __call__.
    """

    def __call__(self, *args, **kwargs):
        """
        Return the excitation force vector at the current step.
        """
        pass


class ConstantExcitation(BaseExcitation):
    """
    Constant-amplitude synchronous excitation in 2D.
    """

    def __init__(self, force, phase, rpm):
        self._phase = phase
        self._force = force
        self._frequency = rpm / 60

    def __call__(self, t):
        return self._calc_force(t)

    def _calc_force(self, t):
        fx = self._force * np.cos(2 * np.pi * self._frequency * t + self._phase)
        fy = self._force * np.sin(2 * np.pi * self._frequency * t + self._phase)
        return np.array([fx, fy])


class StaticLoad(BaseExcitation):
    """Static load excitation that always returns a fixed 2D force vector."""

    def __init__(self, load, **kwargs):
        """
        `load` must be a length-2 array: [fx, fy].
        """
        if len(load) != 2:
            raise ValueError("Static load must be a length-2 vector.")
        self._load = np.array(load)
        self.node_link = None

    def __call__(self, *args, **kwargs):
        return self._load


class Gravity(BaseExcitation):
    def __init__(self, g, ms, **kwargs):
        """
        Build gravity excitation from mass array `ms`.
        Output shape is (n, 2), with y-direction = -m*g.
        """
        self._g = g
        self._ms = np.array(ms).reshape(-1)
        self.node_link = None
        self._force = np.zeros((self._ms.shape[0], 2))
        self._force[:, 1] = -self._ms * self._g

    def __call__(self, *args, **kwargs):
        return self._force


class UnbalancedExcitation(BaseExcitation):
    """
    Unbalance excitation generated from m, e, frequency and phase.
    """

    def __init__(self, phase=0, t_max: float = 1, m=0, freq=0, e=0, **kwargs):
        """
        Initialize unbalance parameters.
        When no_step=True, a linear ramp is applied in [0, t_max].

        """
        self._phase = phase
        self._t_max = t_max
        self._m = m
        self._freq = freq
        self._e = e
        self._no_step_set = kwargs.get("no_step", False)
        self.results = pd.DataFrame(columns=["t", "force"])

    def __call__(self, t, **kwargs):
        """
        Compute force at time t.
        kwargs can temporarily override instance parameters.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise ValueError("UnbalancedExcitation has no attribute {}".format(key))
        if self._no_step_set:
            force = self._calc_force(
                self._phase, t, self._m, self._freq, self._e
            ) * self._no_step(t)
        else:
            force = self._calc_force(self._phase, t, self._m, self._freq, self._e)
        self.results.loc[self.results.shape[0]] = [t, force]
        return force

    def _calc_amp(self, m, freq, e):
        """
        Amplitude model: A=(2*pi*f)^2*m*e.
        """
        amp = (2 * np.pi * freq) ** 2 * m * e
        # Centrifugal-force-based amplitude.
        return amp

    def _calc_force(self, phase, t, m, freq, e):
        """
        Generate 2D orthogonal force components [fx, fy].
        """
        amp = self._calc_amp(m, freq, e)
        fx = amp * np.cos(2 * np.pi * freq * t + phase)
        fy = amp * np.sin(2 * np.pi * freq * t + phase)
        return np.array([fx, fy])

    def _no_step(self, t):
        """
        Soft-start factor. t<t_max -> t/t_max, else 1.
        """
        t_max = self._t_max
        if t < t_max:
            return t / t_max
        else:
            return 1


class SingleRotor(BaseSimpleModel):
    """
    Simplified 2D rotor model with discrete state propagation.
    """

    def init(self):
        return True

    def __init__(
        self,
        m,
        k,
        c,
        rpm: float = 0,
        e: float = 0,
        dt: float = 1,
        x_init=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._m = m
        self._m_inv = np.linalg.inv(self._m)
        self._k = k
        self._c = c
        self._rpm = rpm
        self._e = e
        self._f = None
        self._a = None
        self._b = np.array([[1, 0], [0, 1], [0, 0], [0, 0]])
        self._dt = dt
        self._force = np.zeros(2)
        self._xk1 = None
        self._xk0 = x_init
        if self._xk0 is None:
            self._xk0 = np.zeros(4)
        self._cp = np.array([[0, 0, 1, 0], [0, 0, 0, 1]])
        self._results = []
        self.set_dt(dt)

    @property
    def rpm(self):
        return self._rpm

    @property
    def dt(self):
        return self._dt

    def set_dt(self, dt):
        """
        Update time step and rebuild system matrices.
        """
        self._dt = dt
        self._calc_a()
        self._calc_g()
        self._calc_h()

    def _calc_a(self):
        """
        Build continuous state matrix A.
        """
        tmp_a = -np.hstack((self._m_inv.dot(self._c), self._m_inv.dot(self._k)))
        tmp_a2 = np.hstack((np.eye(2), np.zeros_like(self._m)))
        temp_a = np.vstack((tmp_a, tmp_a2))
        self._a = temp_a

    def _calc_g(self):
        """
        Compute transition matrix G=exp(A*dt).
        """
        self._g = calc_ea(self._a, self._dt)

    def _calc_h(self):
        """
        Compute discrete input matrix H via Gaussian integration.
        """

        def add(dt, a):
            return expm(dt * a).dot(self._b)

        self._h = lld_integral(np.array([0, self._dt]), add, self._a)

    def _calc_y(self, xk0):
        """
        Project state to observable output.
        """
        return self._cp.dot(xk0)

    def _ubf(self, t, *args, **kwargs):
        """
        Default unbalance-force interface (returns zero force).
        """
        return np.zeros(2)

    def has_unbalance(self, ubf: UnbalancedExcitation):
        """
        Inject an unbalance excitation object.
        """
        self._ubf = ubf

    def set_rpm(self, rpm):
        """
        Update rotor speed in rpm.
        """
        self._rpm = rpm

    def set_e(self, e):
        """
        Update eccentricity parameter.
        """
        self._e = e

    def input(self, force):
        """
        Set external input force vector [fx, fy].
        """
        self._force = force

    def output(self, t, *args, **kwargs):
        """
        Perform one state propagation step and return output.
        """
        m = np.sum(self._m) / 2
        e = self._e
        rpm = self._rpm
        force = self._force + self._ubf(t, m=m, rpm=rpm, e=e, **kwargs)
        # logger.info('force:{}'.format(force))
        self._xk1 = self._g.dot(self._xk0) + self._h.dot(force)
        self._xk0 = self._xk1
        result = self._calc_y(self._xk0)
        self.results.append(result)
        return result

    def calc_error(self, *args, **kwargs):
        pass

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        pass


class RossRotor:
    """ROSS rotor wrapper with explicit load, advance, and state-read phases."""

    unit_system = "dimensional"

    def __init__(self, rotor: rs.Rotor, speed, dt, discrete=False):
        """
        Wrapper for ROSS rotor with unified continuous/discrete interfaces.

        Parameters
        ----------
        rotor : ross.Rotor
            Underlying ROSS rotor model.
        speed : float
            Rotor angular speed in rad/s, which is the base unit expected by
            ROSS when a plain numeric value is passed.
        dt : float
            Simulation time step in seconds.
        discrete : bool, optional
            Use the ROSS discrete model instead of the continuous-time model.

        """
        self._b = None
        self._a = None
        self._d = None
        self._c = None
        self._Bd1 = None
        self._Bd0 = None
        self._Ad = None
        self._rotor = rotor
        self._speed = speed
        self._dt = dt
        self._sys = rotor._lti(speed)
        self._number_dof = rotor.number_dof
        self._dof_layout = (
            RotorDofLayout.from_ross(rotor)
            if int(self._number_dof) in {4, 6}
            else None
        )
        if not discrete:
            self.continuesys()
        else:
            self.discretesys()
        # Initialize state caches.
        self._xk0 = np.zeros(self._a.shape[0])
        self._xk1 = np.zeros(self._a.shape[0])
        self._t = []
        self._xout = None
        self._xouts = []
        self._yout = None
        self._youts = []
        self._force0: np.ndarray | None = None  # t=kT
        self._force1: np.ndarray | None = None  # t=(k+1)T
        self._discrete = discrete
        self.signal = Signal(sys=self)
        self._lifecycle = RuntimeLifecycle(type(self).__name__, input_label="rotor load")
        self.init()

    def continuesys(self):
        """
        Discretize continuous model and obtain Ad, Bd0, Bd1.
        """
        A, B, C, D = map(
            np.asarray, (self._sys.A, self._sys.B, self._sys.C, self._sys.D)
        )
        n_states = A.shape[0]
        n_inputs = B.shape[1]
        dt = self._dt
        M = np.vstack(
            [
                np.hstack([A * dt, B * dt, np.zeros((n_states, n_inputs))]),
                np.hstack(
                    [np.zeros((n_inputs, n_states + n_inputs)), np.identity(n_inputs)]
                ),
                np.zeros((n_inputs, n_states + 2 * n_inputs)),
            ]
        )
        expMT = scipy.linalg.expm(np.transpose(M))
        Ad = expMT[:n_states, :n_states]
        Bd1 = expMT[n_states + n_inputs :, :n_states]
        Bd0 = expMT[n_states : n_states + n_inputs, :n_states] - Bd1
        self._a = Ad
        self._Bd0 = Bd0
        self._Bd1 = Bd1
        self._c = C
        self._d = D

    def discretesys(self):
        """
        Use built-in discrete model from ROSS.
        """
        self._sys = self._sys.to_discrete(self._dt)
        self._a = self._sys.A
        self._b = self._sys.B
        self._c = self._sys.C
        self._d = self._sys.D

    def input_force(self, t, force, x0=None, **kwargs):
        """
        Input global-DOF force vector at time t.

        Optional kwargs:
            x0: override current state.
            force0: previous-step force for continuous interpolation.
        """
        self._lifecycle.require_input_slot()
        # Validate before mutating histories or latched inputs.
        time = self._check_time(t)
        current_force = finite_real_vector(
            force, "rotor force", int(self._rotor.ndof)
        )
        force0 = kwargs.get("force0", None)
        previous_force = (
            None
            if force0 is None
            else finite_real_vector(force0, "previous rotor force", int(self._rotor.ndof))
        )
        initial_state = (
            None
            if x0 is None
            else finite_real_array(x0, "initial rotor state", shape=np.shape(self._xk0))
        )
        self._t.append(time)
        # Current-step input.
        self._force1 = current_force
        self._state_ready = False
        # Optional previous-step input for continuous mode.
        if previous_force is not None:
            self._force0 = previous_force
        # Optional: override the initial state.
        if initial_state is not None:
            self._xk0 = initial_state
        self._lifecycle.latch()

    def input_force2node(self, t, force, node, x0=None, **kwargs):
        """
        Input per-node 2D forces and map them to global DOFs.
        """
        self._lifecycle.require_input_slot()
        if self._dof_layout is None:
            raise ValueError("node-force mapping requires a four- or six-DOF layout")
        mapped_force = _nodeforce2array(
            self._rotor.ndof, self._dof_layout, force, node
        )
        force0 = kwargs.get("force0", None)
        mapped_force0 = (
            None
            if force0 is None
            else _nodeforce2array(
                self._rotor.ndof, self._dof_layout, force0, node
            )
        )
        # Validate all inputs before mutating histories or latched state.
        time = self._check_time(t)
        initial_state = (
            None
            if x0 is None
            else finite_real_array(x0, "initial rotor state", shape=np.shape(self._xk0))
        )
        self._t.append(time)
        self._force1 = mapped_force
        self._state_ready = False
        # Optional: override the initial state.
        if initial_state is not None:
            self._xk0 = initial_state
        # Optional previous-step input for continuous mode.
        if mapped_force0 is not None:
            self._force0 = mapped_force0
        self._lifecycle.latch()

    def input_load(self, value: RotorLoadInput) -> None:
        """Latch a validated dimensional nodal-load DTO."""

        if not isinstance(value, RotorLoadInput):
            raise TypeError("rotor load must be RotorLoadInput")
        if value.unit_system is not UnitSystem.DIMENSIONAL:
            raise ValueError("ROSS rotor loads must use dimensional units")
        self.input_force2node(
            value.time,
            value.force,
            value.node_links,
            force0=value.previous_force,
        )

    def init(self, x0=None):
        self._lifecycle.fail()
        try:
            if x0 is not None:
                initial_state = finite_real_array(
                    x0, "initial rotor state", shape=np.shape(self._xk0)
                )
                self._xk0 = initial_state
                self._xk1 = initial_state.copy()
            else:
                self._xk0 = np.zeros(self._a.shape[0])
                self._xk1 = np.zeros(self._a.shape[0])
            self._t = []
            self._xouts = []
            self._youts = []
            self._force1 = np.zeros(self._rotor.ndof)
            self._force0 = np.zeros(self._rotor.ndof)
            self._state_ready = True
        except BaseException:
            self._lifecycle.fail()
            raise
        self._lifecycle.reset(output_available=True)

    @property
    def lifecycle_state(self) -> LifecycleState:
        """Return the shared rotor runtime state without advancing."""

        return self._lifecycle.state

    def _check_time(self, t, tol=1e-15):
        """
        Validate that time is finite and successive increments match system dt.
        """
        time = finite_real_time(t, "input time")

        if len(self._t) > 0:
            dt = time - self._t[-1]
            if abs(dt - self._dt) > tol:
                raise ValueError("Input time step does not match system dt.")
        return time

    def _propagate(self):
        """Propagate one latched load without changing lifecycle state."""

        if self._discrete:
            return self._run_discrete()

        else:
            return self._run_continuous()

    def _run_discrete(self):
        """
        One-step propagation for discrete model.
        """
        self._xk1 = self._a.dot(self._xk0) + self._b.dot(self._force1)
        self._yout = self._c.dot(self._xk0) + self._d.dot(self._force1)
        self._xk0 = self._xk1
        self._xout = self._xk0
        return self._xk1

    def _run_continuous(self):
        """
        One-step propagation for continuous-discretized model.
        """
        # If previous input is missing, reuse current input.
        if self._force0 is None:
            self._force0 = self._force1
        assert self._force0 is not None
        assert self._force1 is not None
        self._xk1 = (
            np.dot(self._xk0, self._a)
            + np.dot(self._force0, self._Bd0)
            + np.dot(self._force1, self._Bd1)
        )
        # Update previous-step input cache.
        self._force0 = self._force1
        self._yout = np.squeeze(np.dot(self._xk1, np.transpose(self._c))) + np.squeeze(
            np.dot(self._force1, np.transpose(self._d))
        )
        self._xk0 = self._xk1
        self._xout = self._xk0
        return self._xk1

    def advance(self):
        """Advance exactly once from the currently latched force input."""

        with self._lifecycle.evaluation():
            result = self._propagate()
            self._state_ready = True
            self.signal.lead_loop("finish_signal")
        return result

    def current_state(self, node=None):
        """Read the current rotor state without advancing the model."""

        self._lifecycle.require_output()
        ndof = self._rotor.ndof
        res = self._xk0
        if node is None:
            return res.copy()
        else:
            if self._dof_layout is None:
                raise ValueError(
                    "node-state extraction requires a four- or six-DOF layout"
                )
            node = normalize_node_indices(node)
            # xy
            x_indices = np.asarray(
                [
                    self._dof_layout.global_index(int(value), "x", ndof)
                    for value in node
                ],
                dtype=np.int64,
            )
            y_indices = np.asarray(
                [
                    self._dof_layout.global_index(int(value), "y", ndof)
                    for value in node
                ],
                dtype=np.int64,
            )
            u0 = res[x_indices]
            u1 = res[y_indices]
            uxy = np.vstack((u0, u1)).T
            # xyt
            u0 = res[ndof + x_indices]
            u1 = res[ndof + y_indices]
            uxyt = np.vstack((u0, u1)).T
            return {"uxy": uxy, "uxyt": uxyt}

    def output(self, node=None):
        """Read the completed current state without hidden propagation."""

        return self.current_state(node)

    @property
    def dof_layout(self) -> RotorDofLayout:
        """Return the immutable ROSS-derived node DOF layout."""

        if self._dof_layout is None:
            raise ValueError("rotor does not expose a four- or six-DOF layout")
        return self._dof_layout

    def finish_signal(self):
        self._youts.append(copy.deepcopy(self._yout))
        self._xouts.append(copy.deepcopy(self._xout))

    def results(self):
        """
        Package simulation history as `ross.TimeResponseResults`.
        """
        self._lifecycle.require_output()
        return build_time_response_results(
            self._rotor, self._t, self._youts, self._xouts
        )

    def result_uxy(self, node):
        """
        Extract displacement history (x, y) for a given node.
        """
        if self._dof_layout is None:
            raise ValueError("result_uxy requires a four- or six-DOF layout")
        self._lifecycle.require_output()
        return extract_displacement_history(
            self._youts, self._dof_layout, node, self._rotor.ndof
        )

    def plot_rotor(self, **kwargs):
        return self._rotor.plot_rotor(**kwargs)

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        Wrap current results into `SaveTreeNode` and optionally save to disk.
        """
        if path is None:
            path = "rotor_result"
        if name is None:
            name = "rotor"
        self._lifecycle.require_output()
        return build_rotor_save_tree(
            times=self._t,
            states=self._xouts,
            outputs=self._youts,
            response=self.results(),
            rotor=self._rotor,
            path=path,
            name=name,
            tofile=tofile,
            writer=kwargs.get("writer"),
        )


class RossRotorSimilarityCheck:
    def __init__(self, pt, rotor: RossRotor, threshold=0.999):
        self._pt = pt
        self._rotor = rotor
        self._threshold = threshold

    def check(self):
        """
        Compare Pearson similarity between two recent response windows.
        """
        yout0 = self._rotor._youts[-self._pt :]
        yout1 = self._rotor._youts[-2 * self._pt : -self._pt]
        if len(yout0) < self._pt or len(yout1) < self._pt:
            raise ValueError("Insufficient rotor data for similarity check.")
        yout0 = np.array(yout0)
        yout1 = np.array(yout1)
        # Evaluate similarity on two latest windows.
        sim = pearson_similarity(yout0, yout1)
        if sim > self._threshold:
            print(
                f"Rotor response is stable: similarity={sim:.4f} > threshold={self._threshold}"
            )
            return True
        else:
            print(
                f"Rotor response is unstable: similarity={sim:.4f} < threshold={self._threshold}"
            )
            return False


def get_node_displacement(node, rotor_result):
    """
    node: the node number to get displacement for
    rotor_result: the result object from RossRotor, TimeResponseResults
    """
    nodes = rotor_result.rotor.nodes
    link_nodes = rotor_result.rotor.link_nodes
    ndof = rotor_result.rotor.number_dof
    fix_dof = (node - nodes[-1] - 1) * ndof // 2 if node in link_nodes else 0
    dofx = ndof * node - fix_dof
    uxy = rotor_result.yout[:, dofx : dofx + 2]
    return uxy


class RotorPostprocessor(BasePostProcess):
    def __init__(self, rotor: SingleRotor):
        super().__init__()
        self._rotor = rotor

    def fft_result(self, x_range=None):
        results = np.array(self._rotor.results)
        if x_range is None:
            results_x = results[:, 0]
        else:
            results_x = results[x_range[0] : x_range[1], 0]
        x_fft = np.fft.rfft(results_x)
        n = results_x.size
        time_step = self._rotor.dt
        freq = np.fft.rfftfreq(n, d=time_step)
        self.postprocess_result["freq"] = freq
        self.postprocess_result["x_fft"] = x_fft

    def plot_fft_result(self, **kwargs):
        """
        Compute and plot FFT magnitude of x-direction response.
        """
        self.fft_result(**kwargs)
        plt.plot(
            self.postprocess_result["freq"], np.abs(self.postprocess_result["x_fft"])
        )
        plt.show()

    def plot_uxy(self):
        """
        Plot x-y trajectory from simulation output.
        """
        results = np.array(self._rotor.results)
        plt.plot(results[:, 0], results[:, 1])
        plt.show()


def calc_ea(dt, a):
    """
    Compute matrix exponential exp(A*dt).
    """
    return expm(a * dt)


def calc_h(dt, a):
    """
    Auxiliary single-input mapping example for exp(A*dt)B.
    """
    return expm(dt * a).dot([0, 1])


def lld_integral(x_lim, func, *args, **kwargs):
    """
    func = func(x, other_vars)
    len(x_lim) = 2
    Numerical integration helper based on predefined Gaussian points.
    """
    dx = x_lim[1] - x_lim[0]
    sum_x = x_lim[1] + x_lim[0]
    flag = False
    sum_ans = None
    for num, _p in enumerate(_intpoint):
        _p = dx / 2 * _p + sum_x / 2
        if flag is False:
            sum_ans = func(_p, *args, **kwargs) * _weight[num] * dx / 2
            flag = True
        else:
            sum_ans += func(_p, *args, **kwargs) * _weight[num] * dx / 2
    return sum_ans


class ShaftElement(rs.ShaftElement):
    """Linear damping shaft element: C = alpha*M + beta*K."""

    def __init__(self, *args, alpha=0, beta=0, **kwargs):
        super().__init__(*args, **kwargs)
        self._alpha = alpha
        self._beta = beta

    def C(self):
        return self.M() * self._alpha + self.K() * self._beta


def rotor0(
    dt,
    freq,
    alpha=0,
    beta=0,
    rotor_path=r"G:\项目文件\202103 - 173计划 - 舰船涡轮机主动智能声纹控制技术\jwk-转子文件\elements.xls",
):
    """Build the default ROSS rotor at a rotational frequency in Hz.

    ``freq`` follows the ALB configuration convention and is expressed in Hz.
    ROSS expects a plain numeric ``speed`` in rad/s, so this factory performs
    the conversion exactly once before constructing :class:`RossRotor`.
    """
    # Build the default rotor and convert the public Hz input for ROSS.
    steel = rs.Material(name="Steel", rho=7850, E=2.1e11, G_s=8.08e10)
    rotor_csv = pd.read_excel(rotor_path, header=None)
    ls = rotor_csv[4] * 1e-3
    ids = np.zeros_like(ls)
    ods = rotor_csv[6] * 1e-3
    steel.save_material()

    r_elems = [
        ShaftElement(
            L=length_m,
            idl=ind,
            odl=od,
            material=steel,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
            alpha=alpha,
            beta=beta,
        )
        for length_m, ind, od in zip(ls, ids, ods)
    ]

    disk0 = rs.DiskElement.from_geometry(
        n=23, material=steel, width=0.03, i_d=0.08, o_d=0.345
    )
    disk1 = rs.DiskElement.from_geometry(
        n=28, material=steel, width=0.1, i_d=0.08, o_d=0.450
    )
    disk2 = rs.DiskElement.from_geometry(
        n=31, material=steel, width=0.03, i_d=0.08, o_d=0.345
    )
    disks = [disk0, disk1, disk2]
    bearing0 = [rs.BearingElement(n=12, kxx=6e3, kyy=6e3, cxx=6e3, cyy=6e3)]
    bearing1 = [rs.BearingElement(n=34, kxx=6e3, kyy=6e3, cxx=6e3, cyy=6e3)]
    bearings = bearing0 + bearing1
    rr = rs.Rotor(
        shaft_elements=r_elems, bearing_elements=bearings, disk_elements=disks
    )
    speed_rad_s = 2.0 * np.pi * float(freq)
    rr = RossRotor(rr, speed_rad_s, dt)
    return rr
