# coding: utf-8
import argparse
import copy
import inspect
import itertools
import multiprocessing as mp
import os.path
import random
import smtplib
import typing
import warnings
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from operator import itemgetter
from pathlib import Path

import chardet
import json5
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.fft as sf
import scipy.linalg as la
from scipy.linalg import eigh
from scipy.ndimage import gaussian_filter1d
from tqdm import tqdm

from ALB.config import ConfigData, TimeGridConfig


class ParameterHub:
    def __init__(self, datas: ConfigData):
        self.datas = datas
        self._params = datas.to_dict()

    def request(self, func):
        """Automatically extract the parameters required by the function signature"""
        sig = inspect.signature(func)
        required_params = {
            k: self._params[k] for k in sig.parameters if k in self._params
        }
        if len(required_params) == 0:
            raise ValueError("The required parameters are not enough")
        return func(**required_params)

    def direct(self, keys):
        """
        Directly extract parameters and return a parameter dictionary
        """
        try:
            if isinstance(keys, (list, tuple)) and len(keys) == 1:
                values = (self._params[keys[0]],)
            else:
                values = itemgetter(*keys)(self._params)
        except KeyError:
            raise KeyError("The required parameters are not enough")
        dict_values = dict(zip(keys, values))
        return dict_values

    def soft_direct(self, keys, warning=True):
        """
        Extract existing parameters. If parameters are missing, a warning will be issued.
        """
        required_params = {k: self._params[k] for k in keys if k in self._params}
        if len(required_params) != len(keys) and warning:
            warnings.warn("The required parameters are not enough")
        return required_params

    def soft_request(self, func, warning=True):
        """
        Automatically extract the parameters required by the function signature. If parameters are missing, a warning will be issued.
        """
        sig = inspect.signature(func)
        required_params = {
            k: self._params[k] for k in sig.parameters if k in self._params
        }
        if len(required_params) != len(sig.parameters) and warning:
            Warning("The required parameters are not enough")
        return required_params

    def __getitem__(self, item):
        return self._params[item]

    def __setitem__(self, key, value):
        self._params[key] = value

    def update(self, **kwargs):
        self._params.update(kwargs)


class FFT:
    def __init__(self, t=None, y=None):
        self.t = np.array(t)
        self.t = np.squeeze(self.t)
        self.y = np.array(y)
        self.y = np.squeeze(self.y)
        if t is not None:
            self.dt = t[1] - t[0]
        else:
            self.dt = None
        self.yf = None
        self.xf = None

    def rfft(self, t=None, y=None, plot=False, end=1, save_path=None, **kwargs):
        """
        :param t: time
        :param y: data
        :param plot: plot or not
        :param end: the end of frequency range, 0-1
        :param save_path: save path
        :param kwargs: mean: whether to subtract the mean value
        """
        if t is not None:
            self.t = np.array(t)
            self.t = np.squeeze(self.t)
            self.dt = t[1] - t[0]
        if y is not None:
            self.y = np.array(y)
            self.y = np.squeeze(self.y)
        if kwargs.get("mean", False):
            self.y = self.y - np.mean(self.y)
        if self.t is not None and self.y is not None:
            yf = sf.rfft(self.y) / self.y.size * 2
            xf = sf.rfftfreq(self.y.size, self.dt)
            # Adjust the frequency range according to 'end'
            xf = xf[: int(xf.size * end)]
            yf = yf[: int(yf.size * end)]
            self.yf = yf
            self.xf = xf
        else:
            raise ValueError("t and y must be not None")
        if plot:
            self.plot(save_path=save_path, **kwargs)
        return xf, yf

    def plot(self, save_path=None, **kwargs):
        """
        :param save_path: Path to save the figure
        :param kwargs: annotate: Whether to annotate the peak value on the figure
        :return: None
        """
        xf, yf = self.xf, self.yf
        fig, ax = plt.subplots()
        # Mark the frequency corresponding to the peak value on the figure. The label is near the maximum value, and the label indicates the maximum amplitude and corresponding frequency
        annotate = kwargs.get("annotate", False)
        if annotate:
            ax.annotate(
                "max: {:.2f}, freq: {:.2f}".format(
                    np.max(np.abs(yf)), xf[np.argmax(np.abs(yf))]
                ),
                xy=(xf[np.argmax(np.abs(yf))] + 0.2, np.max(np.abs(yf)) - 0.1),
                xytext=(xf[np.argmax(np.abs(yf))] + 0.3, np.max(np.abs(yf)) - 0.1),
            )

        ax.plot(xf, np.abs(yf))
        ax.set_title("FFT")
        ax.set_xlabel("Freq (Hz)")
        ax.set_ylabel("Amplitude (um)")
        if save_path is not None:
            fig.savefig(save_path)
        plt.show()

    def get(self, freq):
        """
        get the complex number of the specific frequency
        :param freq: the frequency
        :return: freq, complex number
        """
        if self.xf is None or self.yf is None:
            raise ValueError("Please run rfft first")
        idx = np.argmin(np.abs(self.xf - freq))
        return self.xf[idx], self.yf[idx]


def recognize_z(
    t: np.ndarray, freq: float, fs: typing.Iterable, **kwargs
) -> tuple[np.ndarray, np.ndarray]:
    """
    Identify the complex number of a specific frequency in the time series
    return: Return the frequency and its corresponding complex number
    """
    fft = FFT()
    res = []
    for f in fs:
        fft.rfft(t, f, **kwargs)
        res.append(fft.get(freq))
    res = np.array(res)
    return np.array(res[:, 0]), np.array(res[:, 1])


def recognize_kc(t, freq, uxy0, fxy0, uxy1, fxy1, tr=None, **kwargs):
    """
    recognize k and c of bearing
    :param t: time, array(n)
    :param freq: frequency, float
    :param uxy0: the uxy of the forward rotating vortex, array(2, n)
    :param fxy0: the fxy of the forward rotating vortex, array(2, n)
    :param uxy1: the uxy of the inverse rotating vortex, array(2, n)
    :param fxy1: the fxy of the inverse rotating vortex, array(2, n)
    :param tr: time range, list, [st, et], default [0, 1], st and et is the start and end time, 0-1
    """
    if tr is None:
        tr = [0, 1]
    st, et = tr
    start = int(st * len(t))
    end = int(et * len(t))
    t = t[start:end]
    uxy0 = uxy0[:, start:end]
    uxy1 = uxy1[:, start:end]
    fxy0 = np.array(fxy0)[:, start:end]
    fxy1 = np.array(fxy1)[:, start:end]
    z0 = recognize_z(t, freq, uxy0)
    z1 = recognize_z(t, freq, uxy1)
    z = np.array([z0[1], z1[1]]).T
    f0 = recognize_z(t, freq, fxy0)
    f1 = recognize_z(t, freq, fxy1)
    f = np.array([f0[1], f1[1]]).T
    h = f.dot(np.linalg.inv(z))
    return {"h": h, "k": h.real, "c": h.imag / 2 / np.pi / freq}


class EmailSender:
    def __init__(
        self,
        sender="21b902051@stu.hit.edu.cn",
        receiver="734014160@qq.com",
        smtpserver="smtp.hit.edu.cn",
        username="21b902051@stu.hit.edu.cn",
        password="a7TAVIwpZr7cYkac",
    ):
        self.sender = sender
        self.receiver = receiver
        self.subject = None
        self.body = None
        self.smtpserver = smtpserver
        self.username = username
        self.password = password

    def send(self, sub, body):
        # Email content
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(sub, "utf-8")
        msg["From"] = self.sender
        msg["To"] = self.receiver
        # Send email
        smtp = smtplib.SMTP()
        smtp.connect(self.smtpserver)
        smtp.login(self.username, self.password)
        smtp.sendmail(self.sender, self.receiver, msg.as_string())
        smtp.quit()
        print("send email success")


def itercouple(**kwargs):
    """
    Used to input multiple parameters and return all permutations of the input parameters
    :param kwargs: Input parameters, e.g. a=[1, 2], b=[3, 4]. If the input value type is not list/tuple, it will be converted to a list
    :return: Return all permutations of the input, e.g. {'a': 1, 'b': 3}, {'a': 1, 'b': 4}, {'a': 2, 'b': 3}, {'a': 2, 'b': 4}
    """
    keys = kwargs.keys()
    values = kwargs.values()
    new_values = []
    for value in values:
        if not isinstance(value, (list, tuple)):
            value = [value]
        new_values.append(value)
    for instance in itertools.product(*new_values):
        yield dict(zip(keys, instance))


def get_main_model_from_filmsystem(system):
    from ALB.physics.film import FilmModel, FilmSystem

    """
    Get the main model from FilmSystem
    """
    if issubclass(type(system), FilmSystem):
        return system.main_model
    elif not issubclass(type(system), FilmModel):
        raise TypeError("pada must be FilmModel or FilmSystem")
    return system


def create_latex_symbol(symbol: str):
    """
    Capitalize the first letter, convert the subsequent letters to subscript and italic, and return the latex symbol
    :param symbol: the symbol
    :return: the latex symbol
    """
    symbol = symbol.capitalize()
    symbol = symbol[0] + "_{" + symbol[1:] + "}"
    return symbol


"""
The purpose of this file is:
1. Receive a numpy matrix of variable ranges and the required number of samples, shape = (m,2), and output a sample numpy matrix
Execute the ParameterArray function
"""


def Partition(number_of_sample, limit_array):
    """
    Divide the variable intervals of each variable according to the number of samples, and return the divided variable interval matrix
    :param number_of_sample: Number of samples to output
    :param limit_array: Matrix composed of all variable ranges, which is an (m, 2) matrix, m is the number of variables, 2 represents the upper and lower limits
    :return: Return the divided variable interval matrix (three-dimensional matrix), each layer of the three-dimensional matrix corresponds to one variable
    """
    coefficient_lower = np.zeros((number_of_sample, 2))
    coefficient_upper = np.zeros((number_of_sample, 2))
    for i in range(number_of_sample):
        coefficient_lower[i, 0] = 1 - i / number_of_sample
        coefficient_lower[i, 1] = i / number_of_sample
    for i in range(number_of_sample):
        coefficient_upper[i, 0] = 1 - (i + 1) / number_of_sample
        coefficient_upper[i, 1] = (i + 1) / number_of_sample

    partition_lower = coefficient_lower @ limit_array.T
    partition_upper = coefficient_upper @ limit_array.T

    partition_range = np.dstack((partition_lower.T, partition_upper.T))
    return partition_range


def Representative(partition_range):
    """
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    """
    number_of_value = partition_range.shape[0]
    numbers_of_row = partition_range.shape[1]
    coefficient_random = np.zeros((number_of_value, numbers_of_row, 2))
    representative_random = np.zeros((numbers_of_row, number_of_value))

    for m in range(number_of_value):
        for i in range(numbers_of_row):
            y = random.random()
            coefficient_random[m, i, 0] = 1 - y
            coefficient_random[m, i, 1] = y

    temp_arr = partition_range * coefficient_random
    for j in range(number_of_value):
        temp_random = temp_arr[j, :, 0] + temp_arr[j, :, 1]
        representative_random[:, j] = temp_random
    return representative_random


def Rearrange(arr_random):
    """
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    """
    for i in range(arr_random.shape[1]):
        np.random.shuffle(arr_random[:, i])
    return arr_random


def ParameterArray(limitArray, sampleNumber):
    """
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    """
    arr = Partition(sampleNumber, limitArray)
    parametersMatrix = Rearrange(Representative(arr))
    return parametersMatrix


"""Abstract method to be implemented by subclasses."""


class DoE(object):
    def __init__(self, name_value, bounds):
        self.name = name_value
        self.bounds = bounds
        self.type = "DoE"
        self.result = None


class DoELHS(DoE):
    def __init__(self, name_value, bounds, N):
        DoE.__init__(self, name_value, bounds)
        self.type = "LHS"
        self.ParameterArray = ParameterArray(bounds, N)
        self.N = N

    @property
    def sampledata(self):
        return pd.DataFrame(self.ParameterArray, columns=self.name)

    def write_to_csv(self, path=None):
        """
        Write the sample data to LHS.csv file, saved in the running folder
        """
        sample_data = pd.DataFrame(self.ParameterArray, columns=self.name)
        if path is None:
            path = "LHS.csv"
        sample_data.to_csv(path)


class UnzipToTask:
    """
    Abstract method to be implemented by subclasses.
    """

    def __init__(self, task):
        self.task = task

    def __call__(self, kwargs):
        self.task(**kwargs)


class MultiTask:
    def __init__(
        self, task_func, pooln: int, task_args: dict = None, file_path=None, **kwargs
    ):
        """
        :param task_func: task_func
        :param pooln: the number of process
        :param task_args: the parameters of task_func
        :param file_path: the path of json5 file
        """
        self.task_func = UnzipToTask(task_func)
        self.file_path = file_path
        self.pooln = pooln
        if file_path is not None:
            self.task_args = read_json5(file_path)
        else:
            self.task_args = task_args
        self.pool = mp.Pool(processes=pooln)
        self.cob = itercouple(**self.task_args)

    def run(self):
        self.pool.map(self.task_func, self.cob)
        self.pool.close()
        self.pool.join()


def chstack(arrays, **kwargs):
    """
    Abstract method to be implemented by subclasses.
    """
    arrays = list(arrays)
    arrays = [arr for arr in arrays if len(arr) != 0]
    if len(arrays) == 0:
        return []
    else:
        return np.hstack(arrays, **kwargs)


def cvstack(arrays, **kwargs):
    """
    Abstract method to be implemented by subclasses.
    """
    arrays = list(arrays)
    arrays = [arr for arr in arrays if len(arr) != 0]
    if len(arrays) == 0:
        return []
    else:
        return np.vstack(arrays, **kwargs)


def autoname(*args, **kwargs):
    """
    create a name for the task input
    :param args: dict or list or tuple

    Example:
    autoname({'a': 1, 'b': 2})
    autoname(['a', 'b'], [1, 2])
    autoname({'a': 1}, {'b': 2})
    return: 'a_1_b_2'

    """
    split = kwargs.get("split", "_")
    if len(args) == 0:
        raise ValueError("at least one argument")
    elif len(args) == 1:
        if isinstance(args[0], dict):
            local_var = args[0]
            file_name = ""
            for key, value in local_var.items():
                file_name += "{}{}{}{}".format(split, key, split, value)
            file_name = file_name[1:]
            return file_name
        else:
            raise ValueError("the argument must be dict if only one argument")
    elif len(args) == 2:
        if isinstance(args[0], (list, tuple)) and isinstance(args[1], (list, tuple)):
            if len(args[0]) != len(args[1]):
                raise ValueError("two arguments must have the same length")
            name = args[0]
            value = args[1]
            file_name = ""
            for key, value in zip(name, value):
                file_name += "{}{}{}{}".format(split, key, split, value)
            file_name = file_name[1:]
            return file_name
        elif isinstance(args[0], dict) and isinstance(args[1], dict):
            local_var = args[0]
            local_var.update(args[1])
            file_name = ""
            for key, value in local_var.items():
                file_name += "{}{}{}{}".format(split, key, split, value)
            file_name = file_name[1:]
            return file_name
        else:
            raise ValueError("two arguments must be list or tuple or dict")
    elif len(args) > 2:
        if all(isinstance(arg, dict) for arg in args):
            local_var = args[0]
            for arg in args[1:]:
                local_var.update(arg)
            file_name = ""
            for key, value in local_var.items():
                file_name += "{}{}{}{}".format(split, key, split, value)
            file_name = file_name[1:]
            return file_name
        else:
            raise ValueError(
                "if the number of arguments is more than 2, all arguments must be dict"
            )
    else:
        raise ValueError("wrong arguments")


@dataclass(frozen=True)
class BearingFilmMeshConfig:
    bearing_radius: float
    film_thickness: float
    eccentricity_ratio: float
    attitude_angle_deg: float
    pad_start_angle_deg: float
    pad_arc_angle_deg: float
    circumferential_grids: int
    axial_grids: int
    thickness_grids: int
    axial_length: float = 1.0

    def validate(self) -> None:
        if self.bearing_radius <= 0:
            raise ValueError("bearing_radius must be positive")
        if self.film_thickness <= 0:
            raise ValueError("film_thickness must be positive")
        if self.film_thickness >= self.bearing_radius:
            raise ValueError("film_thickness must be smaller than bearing_radius")
        if not 0 <= self.eccentricity_ratio < 1:
            raise ValueError("eccentricity_ratio must be in [0, 1)")
        if self.pad_arc_angle_deg <= 0:
            raise ValueError("pad_arc_angle_deg must be positive")
        if self.axial_length <= 0:
            raise ValueError("axial_length must be positive")
        for name, value in (
            ("circumferential_grids", self.circumferential_grids),
            ("axial_grids", self.axial_grids),
            ("thickness_grids", self.thickness_grids),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")

        min_ratio = 1.0 - self.eccentricity_ratio
        if self.film_thickness * min_ratio <= 0:
            raise ValueError("local film thickness must remain positive everywhere")


@dataclass(frozen=True)
class StructuredHexMesh:
    coordinates: np.ndarray
    elements: np.ndarray
    theta: np.ndarray
    axial: np.ndarray
    thickness_fraction: np.ndarray
    local_film_thickness: np.ndarray

    @property
    def node_count(self) -> int:
        return int(self.coordinates.shape[0])

    @property
    def element_count(self) -> int:
        return int(self.elements.shape[0])


def film_thickness_distribution(
    theta: np.ndarray,
    film_thickness: float,
    eccentricity_ratio: float,
    attitude_angle_rad: float,
) -> np.ndarray:
    return film_thickness * (
        1.0 + eccentricity_ratio * np.cos(theta - attitude_angle_rad)
    )


def build_bearing_film_mesh(config: BearingFilmMeshConfig) -> StructuredHexMesh:
    config.validate()

    theta = np.deg2rad(
        np.linspace(
            config.pad_start_angle_deg,
            config.pad_start_angle_deg + config.pad_arc_angle_deg,
            config.circumferential_grids + 1,
        )
    )
    axial = np.linspace(
        -0.5 * config.axial_length, 0.5 * config.axial_length, config.axial_grids + 1
    )
    thickness_fraction = np.linspace(0.0, 1.0, config.thickness_grids + 1)

    local_film_thickness = film_thickness_distribution(
        theta,
        config.film_thickness,
        config.eccentricity_ratio,
        np.deg2rad(config.attitude_angle_deg),
    )
    if np.any(local_film_thickness <= 0):
        raise ValueError(
            "local film thickness became non-positive; reduce eccentricity_ratio"
        )

    inner_radius = config.bearing_radius - local_film_thickness
    shape = (
        config.circumferential_grids + 1,
        config.axial_grids + 1,
        config.thickness_grids + 1,
    )
    x = np.empty(shape, dtype=float)
    y = np.empty(shape, dtype=float)
    z = np.empty(shape, dtype=float)

    for i, theta_i in enumerate(theta):
        cos_theta = np.cos(theta_i)
        sin_theta = np.sin(theta_i)
        radius_line = inner_radius[i] + thickness_fraction * local_film_thickness[i]
        for j, axial_j in enumerate(axial):
            x[i, j, :] = radius_line * cos_theta
            y[i, j, :] = radius_line * sin_theta
            z[i, j, :] = axial_j

    coordinates = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    elements = []
    for i in range(config.circumferential_grids):
        for j in range(config.axial_grids):
            for k in range(config.thickness_grids):
                n000 = _bearing_mesh_node_id(shape, i, j, k)
                n100 = _bearing_mesh_node_id(shape, i + 1, j, k)
                n110 = _bearing_mesh_node_id(shape, i + 1, j + 1, k)
                n010 = _bearing_mesh_node_id(shape, i, j + 1, k)
                n001 = _bearing_mesh_node_id(shape, i, j, k + 1)
                n101 = _bearing_mesh_node_id(shape, i + 1, j, k + 1)
                n111 = _bearing_mesh_node_id(shape, i + 1, j + 1, k + 1)
                n011 = _bearing_mesh_node_id(shape, i, j + 1, k + 1)
                elements.append((n000, n100, n110, n010, n001, n101, n111, n011))

    return StructuredHexMesh(
        coordinates=coordinates,
        elements=np.asarray(elements, dtype=int),
        theta=theta,
        axial=axial,
        thickness_fraction=thickness_fraction,
        local_film_thickness=local_film_thickness,
    )


def write_nastran_bdf(mesh: StructuredHexMesh, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "$ Bearing oil-film mesh generated by ALB.tool",
        "BEGIN BULK",
        "$ CHEXA cards are written on a single free-field line to avoid continuation parsing issues in COMSOL.",
        "MAT1,1,1.0,,0.3",
        "PSOLID,1,1",
    ]

    for node_id, (x_coord, y_coord, z_coord) in enumerate(mesh.coordinates, start=1):
        lines.append(f"GRID,{node_id},,{x_coord:.9e},{y_coord:.9e},{z_coord:.9e}")

    for element_id, connectivity in enumerate(mesh.elements, start=1):
        connectivity_text = ",".join(str(node_id) for node_id in connectivity)
        lines.append(f"CHEXA,{element_id},1,{connectivity_text}")

    lines.append("ENDDATA")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def plot_mesh_preview(
    mesh: StructuredHexMesh,
    output_path: str | Path | None = None,
    show: bool = True,
) -> Path | None:
    nx = mesh.theta.size
    nz = mesh.axial.size
    nh = mesh.thickness_fraction.size

    x = mesh.coordinates[:, 0].reshape(nx, nz, nh)
    y = mesh.coordinates[:, 1].reshape(nx, nz, nh)
    z = mesh.coordinates[:, 2].reshape(nx, nz, nh)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")

    mesh_color = "#1f77b4"
    radial_color = "#ff7f0e"
    for j in range(nz):
        for k in range(nh):
            ax.plot(
                x[:, j, k],
                y[:, j, k],
                z[:, j, k],
                color=mesh_color,
                linewidth=0.7,
                alpha=0.8,
            )
    for i in range(nx):
        for k in range(nh):
            ax.plot(
                x[i, :, k],
                y[i, :, k],
                z[i, :, k],
                color=mesh_color,
                linewidth=0.7,
                alpha=0.55,
            )

    theta_stride = max(1, (nx - 1) // 12)
    axial_stride = max(1, (nz - 1) // 6)
    for i in range(0, nx, theta_stride):
        for j in range(0, nz, axial_stride):
            ax.plot(
                x[i, j, :],
                y[i, j, :],
                z[i, j, :],
                color=radial_color,
                linewidth=0.9,
                alpha=0.8,
            )

    _set_bearing_mesh_equal_aspect(ax, mesh.coordinates)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")
    ax.set_title(
        "Bearing film hexa mesh\n"
        f"nodes={mesh.node_count}, elements={mesh.element_count}, "
        f"hmin={mesh.local_film_thickness.min():.3e} m, hmax={mesh.local_film_thickness.max():.3e} m"
    )
    fig.tight_layout()

    saved_path = None
    if output_path is not None:
        saved_path = Path(output_path)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(saved_path, dpi=200, bbox_inches="tight")

    if show:
        plt.show()

    plt.close(fig)
    return saved_path


def parse_bearing_film_mesh_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a structured hexahedral oil-film mesh for one bearing pad, export a Nastran BDF file, "
            "and save a 3D preview image."
        )
    )
    parser.add_argument(
        "--bearing-radius",
        type=float,
        required=True,
        help="Bearing pad inner radius in meters",
    )
    parser.add_argument(
        "--film-thickness",
        type=float,
        required=True,
        help="Nominal oil-film thickness in meters",
    )
    parser.add_argument(
        "--eccentricity-ratio",
        type=float,
        required=True,
        help="Dimensionless eccentricity ratio, matching ALB ThicknessModel.e",
    )
    parser.add_argument(
        "--attitude-angle",
        type=float,
        required=True,
        help="Attitude angle in degrees, matching ALB ThicknessModel.angle",
    )
    parser.add_argument(
        "--pad-start-angle",
        type=float,
        required=True,
        help="Pad start angle in degrees",
    )
    parser.add_argument(
        "--pad-arc-angle", type=float, required=True, help="Pad wrap angle in degrees"
    )
    parser.add_argument(
        "--circumferential-grids",
        type=int,
        required=True,
        help="Number of circumferential elements",
    )
    parser.add_argument(
        "--axial-grids", type=int, required=True, help="Number of axial elements"
    )
    parser.add_argument(
        "--thickness-grids",
        type=int,
        required=True,
        help="Number of thickness-direction elements",
    )
    parser.add_argument(
        "--axial-length",
        type=float,
        default=1.0,
        help="Pad axial length in meters; defaults to 1.0 when only a normalized preview is needed",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output Nastran BDF path"
    )
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="Optional PNG path for the 3D preview; defaults to <output>_preview.png",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Skip plt.show(); useful for batch runs or tests",
    )
    return parser.parse_args()


def bearing_film_nastran_export_main() -> None:
    args = parse_bearing_film_mesh_args()
    config = BearingFilmMeshConfig(
        bearing_radius=args.bearing_radius,
        film_thickness=args.film_thickness,
        eccentricity_ratio=args.eccentricity_ratio,
        attitude_angle_deg=args.attitude_angle,
        pad_start_angle_deg=args.pad_start_angle,
        pad_arc_angle_deg=args.pad_arc_angle,
        circumferential_grids=args.circumferential_grids,
        axial_grids=args.axial_grids,
        thickness_grids=args.thickness_grids,
        axial_length=args.axial_length,
    )
    mesh = build_bearing_film_mesh(config)
    bdf_path = write_nastran_bdf(mesh, args.output)
    preview_path = args.preview
    if preview_path is None:
        preview_path = bdf_path.with_name(f"{bdf_path.stem}_preview.png")
    plot_mesh_preview(mesh, output_path=preview_path, show=not args.no_show)

    print(f"BDF written to: {bdf_path}")
    print(f"Preview written to: {preview_path}")
    print(f"Nodes: {mesh.node_count}")
    print(f"Elements: {mesh.element_count}")
    print(
        "Film thickness range [m]: "
        f"{mesh.local_film_thickness.min():.6e} .. {mesh.local_film_thickness.max():.6e}"
    )


def _bearing_mesh_node_id(shape: tuple[int, int, int], i: int, j: int, k: int) -> int:
    _, nz, nh = shape
    return i * nz * nh + j * nh + k + 1


def _set_bearing_mesh_equal_aspect(ax, coordinates: np.ndarray) -> None:
    mins = coordinates.min(axis=0)
    maxs = coordinates.max(axis=0)
    center = 0.5 * (mins + maxs)
    radius = 0.5 * np.max(maxs - mins)
    if radius == 0:
        radius = 1.0
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)


def namevalue(name: str, **kwargs):
    """
    from the autoname function result, return the name and value
    :param name: the name
    :param kwargs:
    split: the split of name, default '_'
    extension: whether to remove the extension, default True
    :return: the dict of name and value
    """
    split = kwargs.get("split", "_")
    ext = kwargs.get("extension", True)
    ignore = kwargs.get("ignore", 0)
    name = name[ignore:]
    if ext:
        name = os.path.splitext(name)[0]
    name = name.split(split)
    value = name[1::2]
    name = name[::2]
    ans = dict(zip(name, value))
    return ans


def read_json5(file, **kwargs) -> dict:
    """
    Abstract method to be implemented by subclasses.
    """
    with open(file, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        encoding = result["encoding"]
    if not encoding:
        encoding = "utf-8"

    try:
        with open(file, encoding=encoding) as f:
            data = json5.load(f)
        return data
    except UnicodeDecodeError:
        with open(file, encoding="latin-1") as f:
            data = json5.load(f)
        return data


def read_share(file, recover=False):
    """Return shared values with a resolved in-memory simulation time grid.

    ``recover=True`` is retained for source compatibility but no longer writes
    derived values back to ``share.json5``.  Canonical time settings are read
    from an adjacent ``time_iter.json5`` when present; otherwise legacy
    ``freq``/``n``/``pt`` values in the shared file are accepted.
    """

    share_config = read_json5(file)
    time_file = os.path.join(os.path.dirname(file), "time_iter.json5")
    if os.path.exists(time_file):
        time_config = read_json5(time_file)
        share_keys = time_config.pop("share_name", [])
        if not isinstance(share_keys, list):
            share_keys = [share_keys]
        for key in share_keys:
            if key not in share_config:
                raise KeyError(
                    f"Parameter '{key}' requested by 'time_iter.json5' not found "
                    "in share data."
                )
            time_config[key] = share_config[key]
    else:
        time_config = share_config

    resolved = TimeGridConfig.from_dict(time_config).resolve()
    share_config.update(
        {
            "mode": resolved.mode,
            "freq": resolved.freq,
            "dt": resolved.dt,
            "steps": resolved.steps,
            "cycles": resolved.cycles,
            "points_per_cycle": resolved.points_per_cycle,
            "pt": resolved.points_per_cycle,
        }
    )
    if resolved.mode == "cycle_points":
        share_config["n"] = int(resolved.cycles)
    else:
        share_config.pop("n", None)

    if recover:
        warnings.warn(
            "read_share(recover=True) is deprecated; derived values are now "
            "returned in memory and share.json5 is never rewritten",
            DeprecationWarning,
            stacklevel=2,
        )
    # Legacy write-back behavior is intentionally disabled and preserved here
    # for migration context.  Runtime-derived dt must never mutate shared input.
    # if recover:
    #     with open(file, "w", encoding="utf-8") as f:
    #         json5.dump(share_config, f, indent=4)
    return share_config


def read_json5_with_share(file, share_dict=None, **kwargs):
    """
    Read a json5 file and merge parameters from a shared configuration.

    This function decouples file reading from parameter calculation. You can pass
    a pre-calculated dictionary via `share_dict` to avoid repeated file I/O or
    to inject computed values (like 'dt').

    :param file: The path to the target json5 file (str).
    :param share_dict: Optional shared configuration.
                       - If dict: used directly for merging (In-Memory).
                       - If None: attempts to read 'share.json5' from the same directory (File System).
    :return: The merged dictionary content.
    """
    # Read the main configuration file
    file_data = read_json5(file)
    share_file_name = kwargs.get("share_file_name", "share.json5")
    share_name = kwargs.get("share_name", "share_name")
    share_data = None

    # Determine the source of the shared data
    if isinstance(share_dict, dict):
        # Case 1: Use the provided dictionary directly (e.g., passed from memory with calculated 'dt')
        share_data = share_dict
    else:
        # Case 2: No dictionary provided, attempt to load 'share.json5' from disk
        share_file_path = os.path.join(os.path.dirname(file), share_file_name)
        if os.path.exists(share_file_path):
            raw_share_data = read_json5(share_file_path)
            time_file_path = os.path.join(os.path.dirname(file), "time_iter.json5")
            has_legacy_time = all(
                key in raw_share_data for key in ("freq", "n", "pt")
            )
            if os.path.exists(time_file_path) or has_legacy_time:
                share_data = read_share(share_file_path)
            else:
                share_data = raw_share_data

    # Perform the merge if shared data exists and the file requests it via 'share_name'
    if share_data is not None and share_name in file_data:
        share_keys = file_data[share_name]

        # Ensure share_keys is a list (handles cases where it might be a single string)
        if not isinstance(share_keys, list):
            share_keys = [share_keys]

        for key in share_keys:
            if key in share_data:
                file_data[key] = share_data[key]
            else:
                # Raise an error if a requested parameter is missing in the shared data
                raise KeyError(
                    f"Parameter '{key}' requested by '{os.path.basename(file)}' not found in share data."
                )

    # Remove the auxiliary 'share_name' key from the final result to keep the config clean
    file_data.pop(share_name, None)

    return file_data


class ConfigArgfy:
    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.json5 = self.read_dir_configs(config_dir)
        self.json5_argfy = copy.deepcopy(self.json5)
        self.set_argfy = {}
        self.save_config_dirs = []

    @staticmethod
    def read_dir_configs(config_dir):
        """
        read all the json5 files in the config_dir
        """
        jf = {}
        for file in os.listdir(config_dir):
            if file.endswith(".json5"):
                jf[file.split(".")[0]] = read_json5(os.path.join(config_dir, file))
        return jf

    def argfy(self, file, **named_values):
        self.set_argfy[file] = named_values

    @staticmethod
    def save_json5(jsfile, save_dir):
        for file, v in jsfile.items():
            with open(
                os.path.join(save_dir, file + ".json5"), "w", encoding="utf-8"
            ) as f:
                json5.dump(v, f, indent=4)

    def save(self, tofile=True, save_path=None):
        """
        save the config dirs
        :param tofile: save to file or not
        :param save_path: the save path
        """
        if save_path is None:
            save_path = self.config_dir
        temp_args = {}
        for file in self.set_argfy.keys():
            tj5 = itercouple(**self.set_argfy[file])
            temp_args[file] = list(tj5)
        iter_nv = itercouple(**temp_args)
        for nv in iter_nv:
            temp_json5 = copy.deepcopy(self.json5)
            name = ""
            for file, named_values in nv.items():
                if len(name) != 0 and not name.endswith("_"):
                    name += "_"
                name += str(file) + "_" + autoname(nv[file])
                for key, values in named_values.items():
                    temp_json5[file][key] = values
            sp = os.path.join(save_path, name)
            if not os.path.exists(sp):
                os.makedirs(sp)
            if tofile:
                self.save_json5(temp_json5, sp)
            self.save_config_dirs.append(sp)
        return self.save_config_dirs


def continue_task(config_dir, result_dir="result"):
    """
    get the continue task dirs without result_dir
    :param config_dir: the dir of config dirs
    :param result_dir: the result dir name, default 'result'
    """
    continue_task_dirs = []
    dirs = listdir(config_dir)
    for dr in dirs:
        # if not exist other dir, add to continue_task_dirs
        cf = os.path.join(config_dir, dr, result_dir)
        if not os.path.exists(cf):
            sf = os.path.join(config_dir, dr)
            continue_task_dirs.append(sf)
    return continue_task_dirs


def read_configs(config_dirs):
    """
    read all the json5 files in the config_dir
    """
    drs = os.listdir(config_dirs)
    jf = {}
    for dr in drs:
        cds = os.listdir(dr)
        for file in cds:
            if file.endswith(".json5"):
                jf[dr] = read_json5(os.path.join(config_dirs, file))
    return jf


def get_config_value(config_dirs, file, keys):
    """
    get the value of the keys in the file of the config_dirs
    """
    list_config = [
        d
        for d in os.listdir(config_dirs)
        if os.path.isdir(os.path.join(config_dirs, d))
    ]
    list_config = [os.path.join(config_dirs, i) for i in list_config]
    config = {}
    for lc in list_config:
        llc = os.listdir(lc)
        for ll in llc:
            if not file.endswith(".json5"):
                file += ".json5"
            if ll == file:
                temp = read_json5(os.path.join(lc, ll))
                temp1 = {}
                for key in keys:
                    temp1[key] = temp[key]
                config[lc] = temp1
    return config


def get(default, var):
    """
    if value is None, return default
    """
    if var is None:
        return default
    else:
        return var


def listdir(path, **kwargs):
    """
    listdir
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not exists")
    if os.path.isfile(path):
        raise FileNotFoundError(f"{path} is a file")
    dirs = os.listdir(path)
    if kwargs.get("full", True):
        dirs = [
            os.path.join(path, d) for d in dirs if os.path.isdir(os.path.join(path, d))
        ]
    else:
        dirs = [d for d in dirs if os.path.isdir(os.path.join(path, d))]
    return dirs


def pearson_similarity(signal1, signal2):
    """
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    """
    if len(signal1) != len(signal2):
        raise ValueError("信号长度必须相同")
    return np.corrcoef(signal1, signal2)[0, 1]


def cal_bode_best(
    data_x,
    rpm,
    n_cycles=10,
    step_size=200,
    sampling_rate=10000,
    sigma=None,
    filter_freq=None,
    filter_bandwidth=5,
    phase_return=False,
):
    len_p = int(len(rpm) / step_size)
    amps = []
    phases = []
    rpm_all_sorted = []
    for y in [data_x[:, i] for i in list(range(data_x.shape[1]))]:
        amp_all = []
        phase_all = []
        rpm_all = []
        start = 0
        for index_rpm in tqdm(range(len_p)):
            window_size = int(
                sampling_rate / rpm[(index_rpm + 1) * step_size - 1] * 60 * n_cycles
            )
            end = start + window_size

            freq, amp, phase = fft_data(
                y[start:end],
                sampling_rate,
                window="hann",
                filter_freq=filter_freq,
                filter_bandwidth=filter_bandwidth,
            )

            target_freq = rpm[start] / 60
            index_freq = np.argmin(np.abs(freq - target_freq))
            index_freq = max(index_freq, 2)
            amp_max_idx = np.argmax(amp[index_freq - 1 : index_freq + 1])
            amp_all.append(np.max(amp[index_freq - 1 : index_freq + 1]))
            phase_all.append(phase[amp_max_idx])
            rpm_all.append(np.mean(rpm[start:end]))
            start = start + step_size
        # sort
        rpm_all_sorted_indices = np.argsort(rpm_all)
        rpm_all_sorted = np.array(rpm_all)[rpm_all_sorted_indices]
        amp_all_sorted = np.array(amp_all)[rpm_all_sorted_indices]
        phase_all_sorted = np.array(phase_all)[rpm_all_sorted_indices]
        if sigma is not None:
            amp_all_sorted = gaussian_filter1d(amp_all_sorted, sigma=sigma)
            phase_all_sorted = gaussian_filter1d(phase_all_sorted, sigma=sigma)
        amps.append(amp_all_sorted)
        phases.append(phase_all_sorted)

    if phase_return:
        return rpm_all_sorted, amps, phases
    else:
        return rpm_all_sorted, amps


def fft_data(
    y,
    sampling_rate,
    ratio=None,
    n_fft=None,
    window=None,
    filter_freq=None,
    filter_bandwidth=5,
):
    """
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    """
    if ratio is None:
        ratio = [0, 1]
    n_elements = y.shape[0]
    start_index = int(n_elements * ratio[0])
    end_index = int(n_elements * ratio[1])
    y_data = y[start_index:end_index]
    n = len(y_data)
    if window == "hann":
        window_func = np.hanning(n)
    elif window == "hamming":
        window_func = np.hamming(n)
    elif window == "blackman":
        window_func = np.blackman(n)
    elif window == "rect" or window is None:
        window_func = np.ones(n)
    else:
        raise ValueError(
            "Unsupported window type. Choose 'hann', 'hamming', 'blackman', 'rect', or None."
        )
    window_mean = np.mean(window_func)
    normalization_factor = 1 / window_mean if window_mean != 0 else 1
    y_windowed = y_data * window_func
    n_fft = n if n_fft is None else n_fft
    fft_data = np.fft.fft(y_windowed, n_fft)
    frequency = np.fft.fftfreq(n_fft, d=1 / sampling_rate)
    magnitude = np.abs(fft_data) * 2 / n * normalization_factor
    phase = np.angle(fft_data)
    if filter_freq is not None:
        if not isinstance(filter_freq, (list, np.ndarray)):
            filter_freq = [filter_freq]
        freq_resolution = sampling_rate / n_fft
        for freq in filter_freq:
            filter_indices = np.where(
                (frequency >= freq - filter_bandwidth / 2)
                & (frequency <= freq + filter_bandwidth / 2)
            )[0]
            fft_data[filter_indices] = 0
        magnitude = np.abs(fft_data) * 2 / n * normalization_factor
        phase = np.angle(fft_data)
    freq = frequency[: n_fft // 2]
    amp = magnitude[: n_fft // 2]
    phase = phase[: n_fft // 2]
    return freq, amp, phase


def excel_to_csv(path):
    # Convert all excel files in the path to csv files
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not exists")
    files = [f for f in os.listdir(path) if f.endswith(".xlsx") or f.endswith(".xls")]
    for file in files:
        file_path = os.path.join(path, file)
        # Read all sheets in Excel, if the sheet has data
        if file.endswith(".xlsx"):
            xls = pd.read_excel(file_path, sheet_name=None)
            # Save the first sheet as df
            first_sheet = list(xls.keys())[0]
            df = xls[first_sheet]
        else:
            # If it is an xls file, directly read the first sheet
            df = pd.read_excel(file_path)
        csv_file_path = os.path.splitext(file_path)[0] + ".csv"
        df.to_csv(csv_file_path, index=False)
        print(f"Converted {file} to {csv_file_path}")


def get_modal_reduction(M, K, C, n_modes_to_keep, G=None, B=None):
    """
    Perform modal-truncation model order reduction (ROM) using conservative system modes.

    This function computes the M-orthonormal modal basis from the symmetric part of the
    stiffness matrix and projects the full-order matrices into the reduced modal space.

    :param M: Mass matrix (N_dof x N_dof)
    :param K: Stiffness matrix (N_dof x N_dof)
    :param C: Damping matrix (N_dof x N_dof)
    :param n_modes_to_keep: Number of modes to retain in the reduced model
    :param G: (optional) Gyroscopic matrix (N_dof x N_dof)
    :param B: (optional) Input matrix (N_dof x N_inputs)

    :return: A dict containing reduced-order matrices and modal data:
        'Mr' (np.ndarray): Reduced mass matrix (n x n)
        'Kr' (np.ndarray): Reduced stiffness matrix (n x n)
        'Cr' (np.ndarray): Reduced damping matrix (n x n)
        'Gr' (np.ndarray or None): Reduced gyroscopic matrix (n x n)
        'Br' (np.ndarray or None): Reduced input matrix (n x N_inputs)
        'Phi_r' (np.ndarray): Modal transformation matrix (N_dof x n)
        'eigenvalues' (np.ndarray): Kept eigenvalues (n,)
    """

    n_dof = M.shape[0]
    print(f"Starting modal reduction: {n_dof} DoF -> {n_modes_to_keep} modes.")

    if n_modes_to_keep > n_dof:
        print(f"Warning: n_modes_to_keep ({n_modes_to_keep}) > total DoF ({n_dof}).")
        print(f"Will use all {n_dof} modes.")
        n_modes_to_keep = n_dof

    # 1. Use the symmetric part of K for eigenvalue solution (as in notebook [119])
    #    This is used to calculate the natural frequencies and mode shapes of the conservative system
    Ksym = (K + K.T) / 2

    # 2. Solve the generalized eigenvalue problem: Ksym * v = lambda * M * v
    #    scipy.linalg.eigh returns M-orthonormalized eigenvectors (mode shapes)
    try:
        eigenvalues_squared, all_mode_shapes = eigh(Ksym, M)
    except np.linalg.LinAlgError as e:
        print(f"Error solving eigenvalue problem: {e}")
        print("Please ensure the M matrix is positive definite.")
        return None

    # 3. Truncation: Select the first 'n' mode shapes (corresponding to the lowest 'n' frequencies)
    #    This is Phi_r in notebook [120]
    Phi_r = all_mode_shapes[:, :n_modes_to_keep]

    # Keep the corresponding eigenvalues (squares of natural frequencies)
    Lambda_r_diag = eigenvalues_squared[:n_modes_to_keep]

    # 4. Project the matrices into the reduced-order modal space (as in notebook [121])

    # Because eigh provides M-orthonormalized shapes, Mr = Phi_r.T @ M @ Phi_r = I
    Mr = np.eye(n_modes_to_keep)

    # Kr = Phi_r.T @ Ksym @ Phi_r = diag(lambda)
    # We construct Kr directly from the eigenvalues, which is more accurate and computationally cheaper
    Kr = np.diag(Lambda_r_diag)

    # C, G, and B must be fully projected
    Cr = Phi_r.T @ C @ Phi_r

    Gr = None
    if G is not None:
        Gr = Phi_r.T @ G @ Phi_r

    Br = None
    if B is not None:
        Br = Phi_r.T @ B

    print("Modal reduction complete.")

    return {
        "Mr": Mr,
        "Kr": Kr,
        "Cr": Cr,
        "Gr": Gr,
        "Br": Br,
        "Phi_r": Phi_r,
        "eigenvalues": Lambda_r_diag,
    }


def calculate_moi_complex(A, C):
    """
    Abstract method to be implemented by subclasses.

    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.

    Abstract method to be implemented by subclasses.
    Abstract method to be implemented by subclasses.
    """
    evals, evecs = la.eig(A)

    # 2.
    idx = np.argsort(np.abs(np.imag(evals)))
    evals = evals[idx]
    evecs = evecs[:, idx]

    moi_results = []
    print(
        f"{'Mode':<5} | {'Freq (Real+Imag) Hz':<28} | {'Abs (Hz)':<10} | {'MOI Value':<15} | {'Evaluation'}"
    )
    print("-" * 85)
    for i in range(len(evals)):
        lam = evals[i]
        v = evecs[:, i]
        # if np.imag(lam) < -1e-5:
        #     continue
        Cv_norm = la.norm(C @ v)
        v_norm = la.norm(v)
        moi = Cv_norm / v_norm
        # ----------------
        freq_complex = lam / (2 * np.pi)
        freq_abs = np.abs(freq_complex)
        freq_str = f"{freq_complex.real:.2f}{freq_complex.imag:+.2f}j"
        if moi < 1e-5:
            eval_str = "涓嶅彲瑙?(Bad)"
        elif moi < 1e-4:
            eval_str = "寮辫娴?(Weak)"
        else:
            eval_str = "鑹ソ (Good)"

        # --- ---
        print(
            f"{i:<5} | {freq_str:<28} | {freq_abs:<10.2f} | {moi:<15.4e} | {eval_str}"
        )

        # --- ---
        moi_results.append(
            {
                "mode_index": i,
                "complex_freq": freq_complex,
                "freq_abs": freq_abs,
                "freq_osc": freq_complex.imag,
                "moi": moi,
            }
        )

    return moi_results
