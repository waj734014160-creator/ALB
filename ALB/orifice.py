# coding: utf-8
import os.path

import numpy as np
import pandas as pd
from scipy.optimize import fsolve
from scipy.sparse import coo_matrix

from ALB.core.component import BaseSimpleModel
from ALB.core.fem.base import BaseSimpleModels
from ALB.config import CsoArgs

# from ALB.logger import logger
from ALB.results import DataFrameResult, SaveTreeNode
from ALB.tool import get_main_model_from_filmsystem

__all__ = [
    "BaseOrifice",
    "Orifice",
    "BuildOrifices",
    "Orifices",
    "NodimCSOrifice",
    "CSOrifice",
    "CsoArgs",
]


def _get_node(model, position):
    """
    Abstract method to be implemented by subclasses.
    """
    x_lim = model.args["x_lim"]
    y_lim = model.args["z_lim"]
    position = [
        position[0] * (x_lim[1] - x_lim[0]) + x_lim[0],
        position[1] * (y_lim[1] - y_lim[0]) + y_lim[0],
    ]
    add_node = model.node_manager.mindistance_search(position)
    return add_node


def _physical_flow_reference(model):
    """Return ``(Qw, r, l/2)`` from a film model's physical reference data.

    ``Qw`` is the volumetric-flow scale used by the Reynolds equation,
    ``ps*c**3/(12*miu0*lr)``.  Nondimensional film models retain these physical
    scale values in ``args`` or ``_input_args``; unit-scale models naturally
    return their unit-reference equivalent.
    """
    model = get_main_model_from_filmsystem(model)
    args = model.args
    input_args = getattr(model, "_input_args", {})
    physical_values = {}
    for name in ("ps", "c", "r", "l"):
        value = input_args.get(name)
        if value is None:
            value = args.get(name)
        if value is None:
            raise ValueError(
                f"A physical '{name}' reference is required for flow scaling"
            )
        physical_values[name] = float(value)
    ps = physical_values["ps"]
    c = physical_values["c"]
    r = physical_values["r"]
    l = physical_values["l"]
    miu0_value = args.get("miu0")
    if miu0_value is None:
        miu0_value = input_args.get("miu", args.get("miu"))
    if miu0_value is None:
        raise ValueError("A physical reference viscosity is required for flow scaling")
    miu0 = float(miu0_value)
    lr = float(args.get("lr", l / (2.0 * r)))
    qw = ps * c**3 / (12.0 * miu0 * lr)
    return qw, r, l / 2.0


class BaseOrifice(BaseSimpleModel):
    """Base interface for oil-supply orifice models.

    ``flow_info`` is the public data contract used by the thermal model.  It
    returns a dictionary split into structure parameters, explicit flow
    parameters, and a legacy dimensional tuple list.  Every ``flow_params``
    item provides ``position_nondim``, ``position_dim``, ``q_nondim``,
    ``q_vol``, and ``qw``.  Thermal solvers consume the explicit fields only.
    """

    def flow_info(self, model=None):
        return {"structure": {}, "flow_params": [], "flow": []}


class Orifice(BaseOrifice):
    def __init__(self, pressure, position, cq, **kwargs):
        """
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        Options:
            Abstract method to be implemented by subclasses.
        """
        super().__init__()
        self._xv = 1
        self._pressure = pressure
        dim = kwargs.get("dim", 2)
        if len(position) == dim:
            self._position = position
        else:
            raise ValueError("position的维度应该为2")
        self._cq = cq
        self._results = pd.DataFrame()
        self._information = pd.DataFrame()
        new_row = pd.DataFrame(
            {"pressure": [pressure], "position": [position], "cq": [cq]}
        )
        self._information = pd.concat([self._information, new_row], ignore_index=True)
        self._save_results = pd.DataFrame()
        self._add_node = None
        self._model = None
        self._f1 = None
        self._err = kwargs.get("err", 1e-5)
        self._results_len = kwargs.get("results_len", 30)
        self._path = kwargs.get("path", "orifice_results")
        self._name = kwargs.get("name", "orifice")

    def init(self):
        self._results = pd.DataFrame()
        self._save_results = pd.DataFrame()
        return True

    @property
    def f1(self):
        """
        Abstract method to be implemented by subclasses.
        """
        if self._f1 is None:
            lr = self._model.args["lr"]
            ps = self._model.args["ps"]
            c = self._model.args["c"]
            miu = self._model.args.get("miu0")
            if miu is None:
                miu = self._model.args["miu"]
            f1 = 12 * miu * lr / ps / c**3
            self._f1 = f1
        else:
            f1 = self._f1
        self._information.loc[0, "f1"] = f1
        return f1

    @property
    def info(self):
        return self._information

    def input(self, xv=1):
        """
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        """
        self._xv = xv

        return True

    def output(self, model):
        """
        Abstract method to be implemented by subclasses.
        """
        if self._add_node is None:
            self._get_node(model)
        model = get_main_model_from_filmsystem(model)
        self._model = model
        q = self.add_q(model)
        qdp = self.add_qdp(model)
        self._add_result(model, q, qdp)
        if self.calc_is_finished():
            self._add_save_result()
        return q, qdp

    def _add_result(self, model, q, qdp, **kwargs):
        """
        Abstract method to be implemented by subclasses.
        :param model:
        """
        start = kwargs.get("start", 1)
        new_row = pd.DataFrame(
            {
                "node_p": [model.latest_result[self._add_node.number]],
                "nq": [q],
                "qdp": [qdp],
                "q(L/min)": [q / self.f1 * 60 * 1000],
            }
        )
        self._results = pd.concat([self._results, new_row], ignore_index=True)
        if self._results_len:
            if len(self._results) > self._results_len:
                self._results = self._results.iloc[start : start + self._results_len]

    def _add_save_result(self):
        self._save_results = pd.concat(
            [self._save_results, self._results.iloc[-1]], ignore_index=True
        )

    def add_q(self, model, q=None):
        """
        Abstract method to be implemented by subclasses.
        """
        if self._pressure is None:
            self._pressure = model.args["ps"]
        number = self._add_node.number
        if q is None:
            dp = self._pressure / model.args["ps"] - model.latest_result[number]
            q = self._cal_q(dp) * np.abs(self._xv)
        model.matrix_process.add_to_right(q, number, "fe")
        return q

    def add_qdp(self, model, qdp=None):
        """
        Abstract method to be implemented by subclasses.
        """
        if self._pressure is None:
            self._pressure = model.args["ps"]
        number = self._add_node.number
        if qdp is None:
            dp = self._pressure / model.args["ps"] - model.latest_result[number]
            qdp = self._cal_qdp(dp) * np.abs(self._xv)
        model.matrix_process.add_to_matrix(qdp, [number, number], "ke")
        return qdp

    def _get_node(self, model):
        """
        Abstract method to be implemented by subclasses.
        """
        x_lim = model.args["x_lim"]
        y_lim = model.args["z_lim"]
        position = [
            self._position[0] * (x_lim[1] - x_lim[0]) + x_lim[0],
            self._position[1] * (y_lim[1] - y_lim[0]) + y_lim[0],
        ]
        self._add_node = model.node_manager.mindistance_search(position)
        return self._add_node

    def _cal_q(self, dp):
        """
        Abstract method to be implemented by subclasses.
        """
        if dp > 0:
            self.nq = self._cq * np.sqrt(dp)
        elif dp < 0:
            self.nq = -self._cq * np.sqrt(-dp)
        elif dp == 0:
            self.nq = 0
        else:
            raise Exception("璁＄畻鏃犻噺绾叉祦閲忛敊璇紒璇蜂紶鍏loat绫诲瀷鏁版嵁")
        return self.nq

    def _cal_qdp(self, dp):
        """
        Abstract method to be implemented by subclasses.
        """
        if dp > 0:
            q_dp = 0.5 * self._cq * np.sqrt(1 / dp)
            return q_dp
        elif dp < 0:
            q_dp = 0.5 * self._cq * np.sqrt(1 / -dp)
            return q_dp
        elif dp == 0:
            return 0
        else:
            raise Exception("type dp should be float, but got {}".format(type(dp)))

    def calc_is_finished(self):
        if self.calc_error() > self._err:
            return False
        else:
            return True

    def calc_error(self, *args, **kwargs):
        errd = kwargs.get("errd", "node_p")
        if len(self.results) <= 1:
            return 1
        delta_result = abs(self.results.iloc[-1][errd] - self.results.iloc[-2][errd])
        if self.results.iloc[-1][errd] == 0:
            error = delta_result
        else:
            error = delta_result
        return error

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        if name is None:
            name = self._name
        if path is None:
            path = self._path
        res = DataFrameResult(
            {name: self._save_results, name + "_information": self.info}
        )
        node = SaveTreeNode(path, res)
        if tofile:
            node.save_to_file()
        return node

    def flow_info(self, model=None):
        structure = {
            "pressure": self._pressure,
            "position": self._position,
            "cq": self._cq,
        }
        if self._add_node is None:
            return {"structure": structure, "flow_params": [], "flow": []}
        if model is None:
            model = self._model
        if model is None:
            return {"structure": structure, "flow_params": [], "flow": []}
        model = get_main_model_from_filmsystem(model)
        qw, r, l_half = _physical_flow_reference(model)
        pos_nd = self._add_node.coords
        q_nondim = float(getattr(self, "nq", 0.0) or 0.0)
        q_vol = q_nondim * qw
        position_nondim = (float(pos_nd[0]), float(pos_nd[1]))
        position_dim = (
            position_nondim[0] * r,
            position_nondim[1] * l_half,
        )
        flow_params = [
            {
                "node": self._add_node.number,
                "position_nondim": position_nondim,
                "position_dim": position_dim,
                "q_nondim": q_nondim,
                "q_vol": q_vol,
                "qw": qw,
            }
        ]
        return {
            "structure": structure,
            "flow_params": flow_params,
            "flow": [(position_dim[0], position_dim[1], q_vol)],
        }


class NodimCSOrifice(BaseOrifice):
    def __init__(
        self,
        position,
        cq0,
        cq1,
        cq2,
        ps=1.0,
        p0=0.0,
        q_leak=0.0,
        *args,
        **kwargs,
    ):
        """
        :param position: nondimensional orifice positions, shape (n, 2).
        :param cq0: nondimensional valve-orifice coefficient.
        :param cq1: nondimensional pad-gap resistance coefficient.
        :param cq2: nondimensional pipe resistance coefficient.
        :param ps: nondimensional supply pressure for positive valve opening.
        :param p0: nondimensional return pressure for negative valve opening.
        :param q_leak: nondimensional leakage flow.
        """
        super().__init__(*args, **kwargs)
        self.position = np.array(position).reshape(-1, 2)
        self.args = None
        self.xv = 0
        self.node = None
        self.cq0 = cq0
        self.cq1 = cq1
        self.cq2 = cq2
        self.q = 0
        self.pa = ps
        self.pb = p0
        self.ps = ps
        self.pr = max(ps, p0)
        self.psv = 0
        self.q_leak = q_leak
        self.tol_err = kwargs.get("tol_err", 1e-3)
        self.model = None
        self.qw = None
        self.lr = None
        self.h = None
        self.err = 1
        self.pn = None
        self.qn = None
        lenp = self.position.shape[0]
        self.lenp = lenp
        columns = (
            ["q"]
            + ["psv"]
            + ["p" + str(n) for n in range(lenp)]
            + ["q" + str(n) for n in range(lenp)]
            + ["err"]
        )
        self._results = pd.DataFrame(columns=columns, dtype=np.float64)
        self._error_res = np.zeros((2, lenp))

    def init(self, *args, **kwargs):
        return True

    def start_signal(self):
        return True

    def finish_signal(self):
        self._add_result(self._results, self.pn, self.qn)

    def input(self, xv=None, *args, **kwargs):
        """
        :param xv: the opening of the servo valve
        """
        if xv is not None and -1 <= xv <= 1:
            self.xv = xv
        if self.xv >= 0:
            self.ps = self.pa
        elif self.xv < 0:
            self.ps = self.pb

    def output(self, model, *args, **kwargs):
        """
        :param model: the film system model
        """
        if self.node is None:
            self._get_node(model)
        self.h = np.array([self.node[n].h for n in range(len(self.node))])
        model = get_main_model_from_filmsystem(model)
        self.model = model
        self._calc_cq()
        self.lr = model.args["lr"]
        ## Test
        self.pn, self.qn = self._add_q_and_qdp(model)
        self._error_res[0] = self._error_res[1]
        self._error_res[1] = self.pn
        self.signal.lead_loop("finish_signal")

    def _calc_qw(self):
        self.qw = 1.0
        return self.qw

    def _calc_cq(self):
        cq0 = self._calc_cq0()
        cq1_h2 = self._calc_cq1_h2()
        cq2 = self._calc_cq2()
        return cq0, cq1_h2, cq2

    def _calc_cq0(self):
        return self.cq0

    def _calc_cq1_h2(self):
        cq1 = np.asarray(self.cq1, dtype=float)
        if cq1.size != 1:
            raise ValueError("cq1 must be scalar; node-wise h correction is cq1_h2")
        self.cq1 = float(cq1.reshape(-1)[0])
        self.cq1_h2 = self.cq1 / self.h**2
        return self.cq1_h2

    def _calc_cq2(self):
        return self.cq2

    def _get_node(self, model):
        if self.node is None:
            self.node = []
            for position in self.position:
                self.node.append(_get_node(model, position))
        return self.node

    def _add_q_and_qdp(self, model):
        """
        :param model: the film system model
        :return: the flow and the flow derivative
        """
        nodes = self.node
        nodes_p = np.array([node.p for node in nodes])
        numbers_p = np.array([node.number for node in nodes])
        q = np.array(self._cal_q(nodes_p))
        qw = self._calc_qw()
        q = self._flow_to_model_units(q, qw, model)
        qdp = self._cal_qdp(nodes_p)
        qdp = self._flow_derivative_to_model_units(qdp, qw, model)
        for n, node in enumerate(nodes):
            model.matrix_process.add_to_right(q[n], node.number, "fe")
        X, Y = np.meshgrid(numbers_p, numbers_p)
        shape = model.matrix_process.matrixs["ke"].shape
        qdp_mt = coo_matrix(
            (qdp.reshape(-1), (X.reshape(-1), Y.reshape(-1))), shape=shape
        )
        model.matrix_process.matrixs["ke"] += qdp_mt
        return nodes_p, q

    def _node_pressure_for_equations(self, pn):
        return pn

    def _supply_pressure_for_equations(self):
        return self.ps

    def _leakage_flow_for_equations(self):
        return self.q_leak

    def _result_flow_scale(self):
        return self.qw

    def _result_pressure_scale(self):
        return self.pr

    def _flow_to_model_units(self, q, qw, model):
        return q

    def _flow_derivative_to_model_units(self, qdp, qw, model):
        return qdp

    def _cal_q(self, pn):
        pn = self._node_pressure_for_equations(pn)
        # if the opening of the servo valve is zero, the flow is zero
        if self.xv == 0:
            return np.zeros_like(pn)
        # temps = np.ones_like(pn) * self.ps
        qs = solve_q(
            self.cq0,
            self.cq1_h2,
            self.cq2,
            pn,
            np.abs(self.xv),
            self._supply_pressure_for_equations(),
            self._leakage_flow_for_equations(),
        )
        self.q = qs[0]
        self.psv = qs[1]
        return qs[2::]

    def _cal_qdp(self, pn):
        if self.xv == 0:
            return np.zeros((len(pn), len(pn)))
        xv = np.abs(self.xv)
        pn = self._node_pressure_for_equations(pn)
        dp = np.abs(self.psv - pn)
        cq4 = self.cq0 * xv * np.sqrt(self.cq2**2 + 4 * self.cq1_h2 * dp) / 2
        ps = self._supply_pressure_for_equations()
        A = np.ones((len(pn), len(pn))) * np.sqrt(np.abs(ps - self.psv))
        B = np.diag(cq4)
        d = -self.cq0 * xv / 2
        A += B
        qdp = np.zeros((len(pn), len(pn)))
        for i in range(len(pn)):
            E = np.zeros_like(pn)
            E[i] += d
            rank = np.linalg.matrix_rank(A)
            if rank == len(pn):
                qdp[i] = np.linalg.solve(A, E)
            else:
                qdp[i] = np.zeros_like(pn)
        qdp = np.array(qdp)

        return -qdp

    def _add_result(self, result, p, q):
        sr = np.concatenate([p, q])
        flow_scale = self._result_flow_scale()
        pressure_scale = self._result_pressure_scale()
        result.loc[result.shape[0]] = (
            [self.q / flow_scale, self.psv / pressure_scale] + list(sr) + [self.err]
        )

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        """
        :param tofile: save to file or not
        :param path: the path to save the results
        :param name: the name of the results
        """
        if name is None:
            name = "orifice"
        if path is None:
            path = "orifice_results"
        path = os.path.join(path, name)
        res = DataFrameResult({name + "_q": self._results})
        node = SaveTreeNode(path, res)
        if tofile:
            node.save_to_file()
        return node

    def calc_error(self, *args, **kwargs):
        if len(self._error_res) <= 1:
            self.err = 1
            return 1
        nodesp = self._error_res
        curr = np.asarray(nodesp[-1], dtype=float)
        prev = np.asarray(nodesp[-2], dtype=float)
        abs_delta = float(np.sum(np.abs(curr - prev)))
        abs_curr = float(np.sum(np.abs(curr)))

        # In near-zero pressure regime (e.g. closed-return branch),
        # relative error is ill-conditioned. Use absolute error with a floor.
        denom_floor = 1e-8
        if abs_curr < denom_floor:
            error = abs_delta
        else:
            error = abs_delta / abs_curr
        self.err = error
        return error

    def calc_is_finished(self):
        """
        Abstract method to be implemented by subclasses.
        """
        if self.calc_error() > self.tol_err:
            return False
        else:
            return True

    def flow_info(self, model=None):
        structure = {
            "position": self.position.copy(),
            "ps": self.ps,
            "cq0": self.cq0,
            "cq1": float(self.cq1),
            "cq2": self.cq2,
            "q_leak": self.q_leak,
            "args": self.args,
        }
        if self.node is None:
            return {"structure": structure, "flow_params": [], "flow": []}
        if model is None:
            model = self.model
        if model is None:
            return {"structure": structure, "flow_params": [], "flow": []}
        model = get_main_model_from_filmsystem(model)
        qw, r, l_half = _physical_flow_reference(model)
        flow = []
        flow_params = []
        for idx, node in enumerate(self.node):
            q_nondim = (
                float(self.qn[idx])
                if self.qn is not None and idx < len(self.qn)
                else 0.0
            )
            q_vol = q_nondim * qw
            pos_nd = node.coords
            position_nondim = (float(pos_nd[0]), float(pos_nd[1]))
            position_dim = (
                position_nondim[0] * r,
                position_nondim[1] * l_half,
            )
            flow.append((position_dim[0], position_dim[1], q_vol))
            flow_params.append(
                {
                    "node": node.number,
                    "position_nondim": position_nondim,
                    "position_dim": position_dim,
                    "q_nondim": q_nondim,
                    "q_vol": q_vol,
                    "qw": qw,
                }
            )
        return {"structure": structure, "flow_params": flow_params, "flow": flow}


class CSOrifice(NodimCSOrifice):
    """Capillary-slot orifice with dimensional geometry and nondimensional CQ.

    The input geometry in ``CsoArgs`` is dimensional, but ``cq0``, ``cq1`` and
    ``cq2`` are stored in the same nondimensional form used by
    ``NodimCSOrifice``.  With ``p = ps * p_bar`` and
    ``q = qw * q_bar``, where ``qw = ps * c**3 / (12 * miu0 * lr)``, the legacy
    dimensional valve / pipe coefficients are scaled into CQ here before the
    shared nondimensional nonlinear equations are solved.
    """

    def __init__(self, position, ps, cso_args, p0=0, *args, **kwargs):
        """
        :param position: the positions of the orifices, the shape should be (n, 2)
        :param ps: the supply pressure
        :param cso_args: the dimensional parameters of the orifices, namedtuple
        :param args: other parameters
        :param kwargs: tol_err, the error of the iteration, default is 1E-3
        """
        super().__init__(
            position=position,
            cq0=0.0,
            cq1=0.0,
            cq2=0.0,
            ps=ps,
            p0=p0,
            q_leak=cso_args.q_leak,
            *args,
            **kwargs,
        )
        self.args = cso_args

    def _calc_qw(self):
        margs = self.model.args
        miu = margs.get("miu0")
        if miu is None:
            miu = margs["miu"]
        qw = margs["ps"] * margs["c"] ** 3 / 12 / miu / margs["lr"]
        self.qw = qw
        return qw

    def _calc_cq0(self):
        margs = self.model.args
        valve_flow_coeff = self.args.cd * self.args.w * np.sqrt(2 / margs["rho"])
        cq0 = valve_flow_coeff * np.sqrt(margs["ps"]) / self._calc_qw()
        self.cq0 = cq0
        return cq0

    def _calc_cq1_h2(self):
        margs = self.model.args
        cq1_override = getattr(self.args, "cq1_nondim", None)
        if cq1_override is None:
            pad_gap_resistance = margs["rho"] / 5 / (np.pi * margs["c"] * self.args.d) ** 2
            cq1 = pad_gap_resistance * self._calc_qw() ** 2 / margs["ps"]
        else:
            cq1 = np.asarray(cq1_override, dtype=float)
        cq1 = np.asarray(cq1, dtype=float)
        if cq1.size != 1:
            raise ValueError("cq1_nondim must be scalar; node-wise h correction is cq1_h2")
        self.cq1 = float(cq1.reshape(-1)[0])
        self.cq1_h2 = self.cq1 / self.h**2
        return self.cq1_h2

    def _calc_cq2(self):
        miu = self.model.args["miu"]
        pipe_resistance = 128 * miu * self.args.l / np.pi / self.args.d**4
        cq2 = pipe_resistance * self._calc_qw() / self.model.args["ps"]
        self.cq2 = cq2
        return cq2

    # The inherited node-pressure conversion is already the required identity.
    # def _node_pressure_for_equations(self, pn):
    #     return pn

    def _supply_pressure_for_equations(self):
        return self.ps / self.model.args["ps"]

    def _leakage_flow_for_equations(self):
        return self.q_leak / self._calc_qw()

    def _result_flow_scale(self):
        return 1.0

    def _result_pressure_scale(self):
        return self.pr / self.model.args["ps"]

    # The inherited flow conversions are identities because the shared
    # nonlinear equations and Reynolds matrix both consume nondimensional flow.
    # def _flow_to_model_units(self, q, qw, model):
    #     return q
    #
    # def _flow_derivative_to_model_units(self, qdp, qw, model):
    #     return qdp


def _as_numeric_vector(value, name):
    """Return a flat float vector for scalar or array-like numeric inputs."""
    try:
        values = np.asarray(value, dtype=float).reshape(-1)
    except ValueError as exc:
        try:
            values = np.concatenate(
                [np.asarray(item, dtype=float).reshape(-1) for item in value]
            )
        except TypeError:
            raise ValueError(f"{name} cannot be converted to a float vector.") from exc
    if values.size == 0:
        raise ValueError(f"{name} cannot be empty.")
    return values


def _as_scalar_float(value, name):
    """Return the first numeric value as a Python float."""
    return float(_as_numeric_vector(value, name)[0])


def _match_numeric_length(value, length, name):
    """Return a flat float vector with either scalar broadcast or exact length."""
    values = _as_numeric_vector(value, name)
    if values.size == 1 and length != 1:
        return np.full(length, float(values[0]), dtype=float)
    if values.size != length:
        raise ValueError(
            f"{name} length {values.size} does not match expected length {length}."
        )
    return values


def define_equations(cq0, cq1, cq2, pn, xv, ps, q_leak):
    """
    :param cq0: the coefficient of the orifice
    :param cq1: the coefficient of the orifice
    :param cq2: the coefficient of the orifice
    :param pn: the pressure of the nodes
    :param xv: the opening of the servo valve
    :param ps: the supply pressure
    :param q_leak: the leakage flow
    """

    pn = _as_numeric_vector(pn, "pn")
    cq0 = _as_scalar_float(cq0, "cq0")
    cq1 = _match_numeric_length(cq1, len(pn), "cq1")
    cq2 = _as_scalar_float(cq2, "cq2")
    xv = _as_scalar_float(xv, "xv")
    ps = _as_scalar_float(ps, "ps")
    q_leak = _as_scalar_float(q_leak, "q_leak")

    def equations(x):
        x = _match_numeric_length(x, len(pn) + 2, "x")
        x0 = float(x[0] - np.sum(x[2::]))
        if ps >= x[1]:
            x1 = float(x[0] - q_leak - cq0 * xv * np.sqrt(ps - x[1]))
        else:
            x1 = float(x[0] + q_leak + cq0 * xv * np.sqrt(x[1] - ps))
        xs = [x0, x1]
        for i in range(2, len(x)):
            pn_i = float(pn[i - 2])
            cq1_i = float(cq1[i - 2])
            if x[1] - pn_i > 0:
                xn = (
                    x[i]
                    - (-cq2 + np.sqrt(cq2**2 + 4 * cq1_i * abs(x[1] - pn_i)))
                    / 2
                    / cq1_i
                )
            elif x[1] - pn_i < 0:
                xn = (
                    x[i]
                    + (-cq2 + np.sqrt(cq2**2 + 4 * cq1_i * abs(x[1] - pn_i)))
                    / 2
                    / cq1_i
                )
            else:
                xn = 0
            xs.append(float(xn))
        return np.asarray(xs, dtype=float)

    return equations


def define_qprime(cq0, cq1_h2, cq2, pn, xv, ps):
    """
    :param cq0: the coefficient of the orifice
    :param cq1_h2: the coefficient of the orifice
    :param cq2: the coefficient of the orifice
    :param pn: the pressure of the nodes
    :param xv: the opening of the servo valve
    :param ps: the supply pressure
    """

    pn = _as_numeric_vector(pn, "pn")
    cq0 = _as_scalar_float(cq0, "cq0")
    cq1_h2 = _match_numeric_length(cq1_h2, len(pn), "cq1_h2")
    cq2 = _as_scalar_float(cq2, "cq2")
    xv = _as_scalar_float(xv, "xv")
    ps = _as_scalar_float(ps, "ps")

    def prime(x):
        x = _match_numeric_length(x, len(pn) + 2, "x")
        lpn = len(pn)
        x0 = np.hstack([1, 0, -np.ones(lpn)])
        if x[1] != ps:
            x1 = np.hstack(
                [1, cq0 * xv / 2 / np.sqrt(np.abs(ps - x[1])), np.zeros(lpn)]
            )
        else:
            x1 = np.hstack([1, 0, np.zeros(lpn)])
        xs = np.vstack([x0, x1])
        pt0 = np.zeros((lpn, 1))
        pt1 = -1 / np.sqrt(cq2**2 + 4 * cq1_h2 * (np.abs(x[1] - pn)))
        pt1 = pt1.reshape(-1, 1)
        pt2 = np.eye(lpn)
        pt = np.hstack([pt0, pt1, pt2])
        xs = np.vstack([xs, pt])
        return xs

    return prime


def solve_q(cq0, cq1_h2, cq2, pn, xv, ps, q_leak, init=None):
    """
    :param cq0: the coefficient of the orifice
    :param cq1_h2: the coefficient of the orifice
    :param cq2: the coefficient of the orifice
    :param pn: the pressure of the nodes
    :param xv: the opening of the servo valve
    :param ps: the supply pressure
    :param q_leak: the leakage flow
    :param init: the initial value of the iteration
    return: the result of the iteration
    """
    pn = _as_numeric_vector(pn, "pn")
    eqs = define_equations(cq0, cq1_h2, cq2, pn, xv, ps, q_leak)
    if init is None:
        init = np.zeros(len(pn) + 2)
    else:
        init = _match_numeric_length(init, len(pn) + 2, "init")
    prime = define_qprime(cq0, cq1_h2, cq2, pn, xv, ps)
    ans = fsolve(eqs, init, fprime=prime)
    # ans = fsolve(eqs, init)
    return ans


csorifice_args = CsoArgs()


# Legacy reference only: HybirdOrifice is superseded by the shared CSOrifice
# formulation above.  Keep this commented implementation for historical audit.
# class HybirdOrifice(Orifice):
#
#     def __init__(self, pressure, position, l, d, w, q_leak=0):
#         super().__init__(pressure=pressure, cq=0, position=position)
#         self._l = l
#         self._d = d
#         self._h = 0
#         self._w = w
#         self._q_leak = q_leak
#         self._f1 = None
#         temp_info = pd.DataFrame({'l': l, 'd': d, 'w': w, 'q_leak': q_leak, 'c1': 0.0,
#                                   'c2': 0.0, 'c3': 0.0, 'f1': 0.0}, index=[0])
#         self._information = pd.concat([self._information, temp_info], axis=1).reindex(self._information.index)
#
#
#     def add_q(self, model, q=None):
#         """
#         """
#         if self._pressure is None:
#             self._pressure = model.args['ps']
#         number = self._add_node.number
#         if q is None:
#             dp = self._pressure - model.latest_result[number] * model.args['ps']
#         model.matrix_process.add_to_right(q, number, 'fe')
#         return q
#
#     def add_qdp(self, model, qdp=None):
#         """
#         """
#         if self._pressure is None:
#             self._pressure = model.args['ps']
#         number = self._add_node.number
#         if qdp is None:
#             dp = self._pressure - model.latest_result[number] * model.args['ps']
#             qdp = self._cal_qdp(dp) * np.abs(self._xv)
#         model.matrix_process.add_to_matrix(qdp, [number, number], 'ke')
#         return qdp
#
#     def _cal_q(self, dp):
#         """
#         """
#         c1, c2, c3, f1 = self._cal_c123_f1()
#         xv = self._xv
#         xv = abs(xv)
#         q = (xv * np.sqrt((c3 * self._xv) ** 2 + 4 * (c1 * xv ** 2 + c2) * np.abs(dp)) - c3 * xv ** 2) \
#             / 2 / (c1 * xv ** 2 + c2) * f1 + self._q_leak * f1
#         if dp > 0:
#             self.nq = q
#         elif dp < 0:
#             self.nq = - q
#         elif dp == 0:
#             self.nq = 0
#         else:
#         return self.nq
#
#     def _cal_qdp(self, dp):
#         c1, c2, c3, f1 = self._cal_c123_f1()
#
#         self._information.loc[0, 'c1'] = c1
#         self._information.loc[0, 'c2'] = c2
#         self._information.loc[0, 'c3'] = c3
#         self._information.loc[0, 'f1'] = f1
#         ps = self._model.args['ps']
#         xv = self._xv
#         if xv == 0:
#             return 0
#         try:
#             qdp = abs(xv) / np.sqrt((c3 * xv) ** 2 + 4 * (c1 * xv ** 2 + c2) * np.abs(dp)) * f1 * ps
#             return qdp
#         except ZeroDivisionError:
#             return False
#
#     def _cal_c123_f1(self):
#         self._h = self._add_node.h
#         rho = self._model.args['rho']
#         d = self._d
#         w = self._w
#         mu = self._model.args['u']
#         c = self._model.args['c']
#         h = self._h * c
#         c1 = rho / 5 / (np.pi * h * d) ** 2
#         c2 = rho / 2 / (0.6 * w) ** 2
#         c3 = 128 * mu * self._l / np.pi / d ** 4
#         f1 = self.f1
#         return c1, c2, c3, f1


class BuildOrifices:
    """
    Abstract method to be implemented by subclasses.
    """

    def __init__(self, orficeclass, orifice_args):
        self._orifce_class = orficeclass
        self._orfices_args = orifice_args

    def build_by_positions(self, positions):
        """
        Abstract method to be implemented by subclasses.
        """
        positions = np.array(positions)
        positions = positions.reshape((-1, 2))
        args = self._orfices_args.copy()
        orifices = []
        for position in positions:
            args["position"] = position
            orifices.append(self._orifce_class(**args))
        return orifices


class Orifices(BaseSimpleModels):
    """
    Abstract method to be implemented by subclasses.
    """

    def init(self):
        pass

    def __init__(
        self,
        pressure,
        cq,
        orifice_class=None,
        orifice_builder=None,
        error_set=1e-2,
        **kwargs,
    ):
        """
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        Abstract method to be implemented by subclasses.
        """
        orifices_args = {"pressure": pressure, "cq": cq}
        super().__init__(orifices_args, orifice_class, orifice_builder)
        if self._model_class is None:
            self._model_class = Orifice
        if self._builder is None:
            self._builder = BuildOrifices(self._model_class, self._models_args)
        self._error_set = error_set
        self._results = {}

    @property
    def results(self):
        self._results = {key: sm._results for key, sm in enumerate(self._simple_models)}
        return self._results

    def build_by_positions(self, positions):
        """
        Abstract method to be implemented by subclasses.
        """
        self._simple_models += self._builder.build_by_positions(positions)

    def clear_orifices(self):
        """
        Abstract method to be implemented by subclasses.
        """
        self._simple_models = []

    def input(self, *args, **kwargs):
        """
        Abstract method to be implemented by subclasses.
        """
        if self._simple_models:
            for simple_model in self._simple_models:
                simple_model.input(*args, **kwargs)

    def output(self, *args, **kwargs):
        """
        Abstract method to be implemented by subclasses.
        """
        if self._simple_models:
            for simple_model in self._simple_models:
                simple_model.output(*args, **kwargs)

    def flow_info(self, model=None):
        flow = []
        flow_params = []
        structures = []
        for simple_model in self._simple_models:
            if hasattr(simple_model, "flow_info"):
                info = simple_model.flow_info(model)
                structures.append(info.get("structure", {}))
                flow_params.extend(info.get("flow_params", []))
                flow.extend(info.get("flow", []))
        return {"structure": structures, "flow_params": flow_params, "flow": flow}

    def calc_is_finished(self):
        """
        Abstract method to be implemented by subclasses.
        """
        if self.calc_error() <= self._error_set:
            return True
        else:
            return False

    def calc_error(self):
        """
        Abstract method to be implemented by subclasses.
        """
        if len(self.results[0]) <= 1:
            return 1
        delta_result = np.array(
            [
                abs(
                    self.results[key].iloc[-1]["node_p"]
                    - self.results[key].iloc[-2]["node_p"]
                )
                for key in self.results.keys()
            ]
        )
        error = np.sqrt(delta_result**2).sum() / len(delta_result)
        return error

    def save(self, tofile=True, path=None, name=None, *args, **kwargs):
        if name is None:
            name = "orifices"
        if path is None:
            path = "orifices_results"
        node = SaveTreeNode(path, None)
        nq = np.array([sm._results["nq"] for sm in self._simple_models])
        nq = nq.T
        nq = nq.sum(axis=1)
        q = np.array([sm._results["q(L/min)"] for sm in self._simple_models])
        q = q.T
        q = q.sum(axis=1)
        node.data = DataFrameResult({name: pd.DataFrame({"nq": nq, "q(L/min)": q})})
        for num, sm in enumerate(self._simple_models):
            node.add_child(
                sm.save(path=name + str(num), name=name + str(num), tofile=False)
            )
        if tofile:
            node.save_to_file()
        return node
