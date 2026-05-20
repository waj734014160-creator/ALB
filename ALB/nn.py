# coding: utf-8
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from ALB.controller import limit_signal


ALBNN_BASE_INPUT_COLS = [
    "ex",
    "ey",
    "vx",
    "vy",
    "sx",
    "sy",
    "lambda_value",
    "beta_nondim",
    "lr",
    "cq0",
    "cq1",
    "cq2",
]
ALBNN_OUTPUT_COLS = ["fx", "fy"]
ALBNN_POLAR_FORCE_OUTPUT_COLS = ["sin_f_theta", "cos_f_theta", "force_norm"]
ALBNN_POLAR_DOT_INPUT_COLS = ["e_dot_v", "e_dot_s", "s_dot_v"]
ALBNN_LOG_INPUT_COLS = {"lambda_value", "lr", "cq0", "cq1", "cq2"}
ALBNN_FEATURE_SETS = {"default", "aug_v2", "sqrt34", "sqrt28", "sqrt_abs", "polar37"}


def cartesian_force_to_polar_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert ``fx, fy`` columns to ``sin_f_theta, cos_f_theta, force_norm``."""
    fx = frame["fx"].to_numpy(dtype=float)
    fy = frame["fy"].to_numpy(dtype=float)
    force_norm = np.sqrt(fx**2 + fy**2)
    safe = force_norm > 1e-12
    sin_f_theta = np.zeros_like(force_norm)
    cos_f_theta = np.ones_like(force_norm)
    sin_f_theta[safe] = fy[safe] / force_norm[safe]
    cos_f_theta[safe] = fx[safe] / force_norm[safe]
    return pd.DataFrame(
        {
            "sin_f_theta": sin_f_theta,
            "cos_f_theta": cos_f_theta,
            "force_norm": force_norm,
        },
        index=frame.index,
    )


def polar_force_to_cartesian(values) -> np.ndarray:
    """Convert polar force targets back to ``fx, fy`` with unit angle cleanup."""
    frame = pd.DataFrame(values, columns=ALBNN_POLAR_FORCE_OUTPUT_COLS)
    sin_f_theta = frame["sin_f_theta"].to_numpy(dtype=float)
    cos_f_theta = frame["cos_f_theta"].to_numpy(dtype=float)
    force_norm = np.clip(frame["force_norm"].to_numpy(dtype=float), 0.0, None)
    angle_norm = np.sqrt(sin_f_theta**2 + cos_f_theta**2)
    safe = angle_norm > 1e-12
    sin_unit = np.zeros_like(force_norm)
    cos_unit = np.ones_like(force_norm)
    sin_unit[safe] = sin_f_theta[safe] / angle_norm[safe]
    cos_unit[safe] = cos_f_theta[safe] / angle_norm[safe]
    return np.column_stack([force_norm * cos_unit, force_norm * sin_unit])


def _materialize_polar_pair(
    frame: pd.DataFrame,
    needed: set[str],
    *,
    x_col: str,
    y_col: str,
    sin_col: str,
    cos_col: str,
    norm_col: str,
) -> None:
    """Derive sine, cosine, and magnitude columns for one planar vector."""
    requested = {sin_col, cos_col, norm_col} & needed
    if not requested:
        return
    if not {x_col, y_col} <= set(frame.columns):
        return
    x = frame[x_col].to_numpy(dtype=float)
    y = frame[y_col].to_numpy(dtype=float)
    norm = np.sqrt(x**2 + y**2)
    safe = norm > 1e-12
    if sin_col in requested and sin_col not in frame.columns:
        values = np.zeros_like(norm)
        values[safe] = y[safe] / norm[safe]
        frame[sin_col] = values
    if cos_col in requested and cos_col not in frame.columns:
        values = np.ones_like(norm)
        values[safe] = x[safe] / norm[safe]
        frame[cos_col] = values
    if norm_col in requested and norm_col not in frame.columns:
        frame[norm_col] = norm


def _materialize_polar_dot_inputs(frame: pd.DataFrame, needed: set[str]) -> None:
    """Derive planar dot-product features used by polar expert models."""
    specs = (
        ("e_dot_v", "ex", "ey", "vx", "vy", ("ev_dot",)),
        ("e_dot_s", "ex", "ey", "sx", "sy", ("es_dot",)),
        ("s_dot_v", "sx", "sy", "vx", "vy", ("sv_dot", "v_dot_s")),
    )
    columns = set(frame.columns)
    for canonical, ax, ay, bx, by, aliases in specs:
        requested_names = {canonical, *aliases} & needed
        if not requested_names or not {ax, ay, bx, by} <= columns:
            continue
        values = (
            frame[ax].to_numpy(dtype=float) * frame[bx].to_numpy(dtype=float)
            + frame[ay].to_numpy(dtype=float) * frame[by].to_numpy(dtype=float)
        )
        for name in requested_names:
            if name not in frame.columns:
                frame[name] = values


def _materialize_ratio_inputs(frame: pd.DataFrame, needed: set[str]) -> None:
    """Derive scalar ratio features shared by training and packaged inference."""
    if "lambda_over_lr" not in needed or "lambda_over_lr" in frame.columns:
        return
    if not {"lambda_value", "lr"} <= set(frame.columns):
        return
    lambda_value = frame["lambda_value"].to_numpy(dtype=float)
    lr = np.clip(frame["lr"].to_numpy(dtype=float), 1e-12, None)
    frame["lambda_over_lr"] = lambda_value / lr


def albnn_augment_frame(frame: pd.DataFrame, feature_set: str = "default") -> pd.DataFrame:
    """Append deterministic nonlinear features with stable column names."""
    if feature_set not in ALBNN_FEATURE_SETS:
        raise ValueError(f"Unknown ALBNN feature_set: {feature_set}")

    augmented = frame.copy()
    if feature_set == "sqrt_abs":
        for col in frame.columns:
            values = frame[col].to_numpy(dtype=float)
            augmented[f"sqrt_abs_{col}"] = np.sqrt(np.abs(values))
        return augmented

    if feature_set == "polar37":
        # Full-polar contract: 15 base columns + sqrt_abs(base) + 7 targeted
        # physical interaction features from sample analysis.
        for col in frame.columns:
            values = frame[col].to_numpy(dtype=float)
            augmented[f"sqrt_abs_{col}"] = np.sqrt(np.abs(values))
        cols = set(frame.columns)
        if {"lambda_value", "lr"} <= cols:
            lambda_value = np.clip(
                frame["lambda_value"].to_numpy(dtype=float), 1e-12, None
            )
            lr = np.clip(frame["lr"].to_numpy(dtype=float), 1e-12, None)
            lambda_over_lr = lambda_value / lr
            augmented["lambda_over_lr"] = lambda_over_lr
            augmented["sqrt_lambda_over_lr"] = np.sqrt(lambda_over_lr)
            augmented["log_lr"] = np.log(lr)
        if {"sin_theta", "cos_theta", "v_norm", "sin_v_theta", "cos_v_theta"} <= cols:
            sin_e = frame["sin_theta"].to_numpy(dtype=float)
            cos_e = frame["cos_theta"].to_numpy(dtype=float)
            v_norm = frame["v_norm"].to_numpy(dtype=float)
            sin_v = frame["sin_v_theta"].to_numpy(dtype=float)
            cos_v = frame["cos_v_theta"].to_numpy(dtype=float)
            augmented["v_radial"] = v_norm * (cos_v * cos_e + sin_v * sin_e)
            augmented["v_tangential"] = v_norm * (-cos_v * sin_e + sin_v * cos_e)
        if {"sin_theta", "cos_theta", "s_norm", "sin_s_theta", "cos_s_theta"} <= cols:
            sin_e = frame["sin_theta"].to_numpy(dtype=float)
            cos_e = frame["cos_theta"].to_numpy(dtype=float)
            s_norm = frame["s_norm"].to_numpy(dtype=float)
            sin_s = frame["sin_s_theta"].to_numpy(dtype=float)
            cos_s = frame["cos_s_theta"].to_numpy(dtype=float)
            augmented["s_radial"] = s_norm * (cos_s * cos_e + sin_s * sin_e)
            augmented["s_tangential"] = s_norm * (-cos_s * sin_e + sin_s * cos_e)
        return augmented

    if feature_set == "sqrt28":
        # Strict 28-column contract for the 12-input thermal ALBNN workflow:
        # base 12 + sqrt_abs(base 12) + 4 sqrt-style aggregate features.
        for col in frame.columns:
            values = frame[col].to_numpy(dtype=float)
            augmented[f"sqrt_abs_{col}"] = np.sqrt(np.abs(values))
        cols = set(frame.columns)
        if {"ex", "ey"} <= cols:
            ex = frame["ex"].to_numpy(dtype=float)
            ey = frame["ey"].to_numpy(dtype=float)
            augmented["e_norm"] = np.sqrt(ex**2 + ey**2)
        if {"vx", "vy"} <= cols:
            vx = frame["vx"].to_numpy(dtype=float)
            vy = frame["vy"].to_numpy(dtype=float)
            augmented["v_norm"] = np.sqrt(vx**2 + vy**2)
        if {"sx", "sy"} <= cols:
            sx = frame["sx"].to_numpy(dtype=float)
            sy = frame["sy"].to_numpy(dtype=float)
            augmented["s_norm"] = np.sqrt(sx**2 + sy**2)
        if {"lambda_value", "lr"} <= cols:
            lambda_value = np.clip(
                frame["lambda_value"].to_numpy(dtype=float), 1e-12, None
            )
            lr = np.clip(frame["lr"].to_numpy(dtype=float), 1e-12, None)
            augmented["sqrt_lambda_over_lr"] = np.sqrt(lambda_value / lr)
        return augmented

    if feature_set == "sqrt34":
        # 34-column contract for the 12-input thermal ALBNN workflow:
        # base 12 + sqrt_abs(base 12) + norm/ratio aggregates and their
        # stable sqrt/log companions. All terms are deterministic functions of
        # the base inputs, so packaged inference can reproduce them.
        for col in frame.columns:
            values = frame[col].to_numpy(dtype=float)
            augmented[f"sqrt_abs_{col}"] = np.sqrt(np.abs(values))
        cols = set(frame.columns)
        if {"ex", "ey"} <= cols:
            ex = frame["ex"].to_numpy(dtype=float)
            ey = frame["ey"].to_numpy(dtype=float)
            e_norm = np.sqrt(ex**2 + ey**2)
            augmented["e_norm"] = e_norm
            augmented["sqrt_e_norm"] = np.sqrt(e_norm)
        if {"vx", "vy"} <= cols:
            vx = frame["vx"].to_numpy(dtype=float)
            vy = frame["vy"].to_numpy(dtype=float)
            v_norm = np.sqrt(vx**2 + vy**2)
            augmented["v_norm"] = v_norm
            augmented["sqrt_v_norm"] = np.sqrt(v_norm)
        if {"sx", "sy"} <= cols:
            sx = frame["sx"].to_numpy(dtype=float)
            sy = frame["sy"].to_numpy(dtype=float)
            s_norm = np.sqrt(sx**2 + sy**2)
            augmented["s_norm"] = s_norm
            augmented["sqrt_s_norm"] = np.sqrt(s_norm)
        if {"lambda_value", "lr"} <= cols:
            lambda_value = np.clip(
                frame["lambda_value"].to_numpy(dtype=float), 1e-12, None
            )
            lr = np.clip(frame["lr"].to_numpy(dtype=float), 1e-12, None)
            lambda_over_lr = lambda_value / lr
            augmented["lambda_over_lr"] = lambda_over_lr
            augmented["sqrt_lambda_over_lr"] = np.sqrt(lambda_over_lr)
            augmented["log_lr"] = np.log(lr)
            augmented["log_lambda_over_lr"] = np.log(
                np.clip(lambda_over_lr, 1e-12, None)
            )
        return augmented

    for col in frame.columns:
        values = frame[col].to_numpy(dtype=float)
        augmented[f"sqrt_abs_{col}"] = np.sqrt(np.abs(values))
        if col in ALBNN_LOG_INPUT_COLS:
            augmented[f"log_{col}"] = np.log(np.clip(values, 1e-12, None))

    if feature_set == "aug_v2":
        cols = set(frame.columns)
        if {"ex", "ey"} <= cols:
            ex = frame["ex"].to_numpy(dtype=float)
            ey = frame["ey"].to_numpy(dtype=float)
            augmented["e_norm"] = np.sqrt(ex**2 + ey**2)
        if {"vx", "vy"} <= cols:
            vx = frame["vx"].to_numpy(dtype=float)
            vy = frame["vy"].to_numpy(dtype=float)
            augmented["v_norm"] = np.sqrt(vx**2 + vy**2)
        if {"sx", "sy"} <= cols:
            sx = frame["sx"].to_numpy(dtype=float)
            sy = frame["sy"].to_numpy(dtype=float)
            augmented["s_norm"] = np.sqrt(sx**2 + sy**2)
        if {"ex", "ey", "vx", "vy"} <= cols:
            ex = frame["ex"].to_numpy(dtype=float)
            ey = frame["ey"].to_numpy(dtype=float)
            vx = frame["vx"].to_numpy(dtype=float)
            vy = frame["vy"].to_numpy(dtype=float)
            augmented["ev_dot"] = ex * vx + ey * vy
            augmented["ev_cross"] = ex * vy - ey * vx
        if {"ex", "ey", "sx", "sy"} <= cols:
            ex = frame["ex"].to_numpy(dtype=float)
            ey = frame["ey"].to_numpy(dtype=float)
            sx = frame["sx"].to_numpy(dtype=float)
            sy = frame["sy"].to_numpy(dtype=float)
            augmented["es_dot"] = ex * sx + ey * sy
        if {"vx", "vy", "sx", "sy"} <= cols:
            vx = frame["vx"].to_numpy(dtype=float)
            vy = frame["vy"].to_numpy(dtype=float)
            sx = frame["sx"].to_numpy(dtype=float)
            sy = frame["sy"].to_numpy(dtype=float)
            augmented["vs_dot"] = vx * sx + vy * sy
        if {"lambda_value", "lr"} <= cols:
            lambda_value = np.clip(
                frame["lambda_value"].to_numpy(dtype=float), 1e-12, None
            )
            lr = np.clip(frame["lr"].to_numpy(dtype=float), 1e-12, None)
            lambda_over_lr = lambda_value / lr
            augmented["lambda_over_lr"] = lambda_over_lr
            augmented["log_lambda_over_lr"] = np.log(
                np.clip(lambda_over_lr, 1e-12, None)
            )
        if "lr" in cols:
            lr = np.clip(frame["lr"].to_numpy(dtype=float), 1e-12, None)
            for col in ("cq0", "cq1", "cq2"):
                if col in cols:
                    augmented[f"{col}_over_lr"] = frame[col].to_numpy(dtype=float) / lr
    return augmented


class NetMlpOld(nn.Module):
    def __init__(self, nbs_neurons):
        super(NetMlpOld, self).__init__()
        self.input_layer = nn.Linear(nbs_neurons[0], nbs_neurons[1])
        self.hidden_layer1 = nn.Linear(nbs_neurons[1], nbs_neurons[2])
        self.hidden_layer2 = nn.Linear(nbs_neurons[2], nbs_neurons[3])
        self.output_layer = nn.Linear(nbs_neurons[3], nbs_neurons[4])

    def forward(self, x):
        x = F.silu(self.input_layer(x))
        x = F.silu(self.hidden_layer1(x))
        x = F.silu(self.hidden_layer2(x))
        x = self.output_layer(x)
        return x


class Net(nn.Module):
    def __init__(
        self,
        nbs_neurons,
        activation: str = "gelu",
        sine_omega0: float = 30.0,
        use_layer_norm: bool = False,
    ):
        super(Net, self).__init__()
        if activation not in {"gelu", "relu", "silu", "sin"}:
            raise ValueError(f"Unsupported activation: {activation}")
        if sine_omega0 <= 0.0:
            raise ValueError("sine_omega0 must be > 0")
        self.activation = activation
        self.sine_omega0 = float(sine_omega0)
        self.use_layer_norm = bool(use_layer_norm)
        self.layers = nn.ModuleList()
        self.layer_norms = nn.ModuleList()
        self.dropouts = nn.ModuleList()

        for i in range(len(nbs_neurons) - 1):
            self.layers.append(nn.Linear(nbs_neurons[i], nbs_neurons[i + 1]))
            if self.use_layer_norm and i < len(nbs_neurons) - 2:
                self.layer_norms.append(nn.LayerNorm(nbs_neurons[i + 1]))
        if self.activation == "sin":
            self._init_sine_weights()

    def forward(self, x):
        for i, layer in enumerate(self.layers[:-1]):
            # x = F.leaky_relu(layer(x), negative_slope=0.2)
            # x = F.tanh(layer(x))
            # x = self.dropouts[i](x)
            x = layer(x)
            if self.use_layer_norm:
                x = self.layer_norms[i](x)
            x = self._activate(x)

        x = self.layers[-1](x)
        return x

    def _activate(self, x):
        if self.activation == "gelu":
            return F.gelu(x)
        if self.activation == "relu":
            return F.relu(x)
        if self.activation == "silu":
            return F.silu(x)
        if self.activation == "sin":
            return torch.sin(self.sine_omega0 * x)
        raise RuntimeError(f"Unsupported activation: {self.activation}")

    def _init_sine_weights(self):
        """Initialize sine networks with SIREN-style scaled uniform weights."""
        with torch.no_grad():
            for idx, layer in enumerate(self.layers):
                fan_in = max(1, layer.in_features)
                if idx == 0:
                    bound = 1.0 / fan_in
                else:
                    bound = np.sqrt(6.0 / fan_in) / self.sine_omega0
                layer.weight.uniform_(-bound, bound)
                if layer.bias is not None:
                    layer.bias.uniform_(-bound, bound)


def net_from_checkpoint(checkpoint):
    """Build a Net with checkpoint activation metadata, defaulting to GELU."""
    return Net(
        checkpoint["architecture"],
        activation=checkpoint.get("activation", "gelu"),
        sine_omega0=float(checkpoint.get("sine_omega0", 30.0)),
        use_layer_norm=bool(checkpoint.get("use_layer_norm", False)),
    )


class NetApl:
    def __init__(self, model: Net, scaled_X, scaled_y):
        self.model = model
        self.scaler_X = scaled_X
        self.scaler_y = scaled_y

    def predict(self, x):
        x = pd.DataFrame(x, columns=self.scaler_X.feature_names_in_)
        x_normalized = torch.tensor(self.scaler_X.transform(x), dtype=torch.float32)
        with torch.no_grad():
            y_normalized = self.model(x_normalized)
        y_normalized = pd.DataFrame(
            y_normalized.numpy(), columns=self.scaler_y.feature_names_in_
        )
        y = self.scaler_y.inverse_transform(y_normalized)
        return y


class ALBNN:
    """Nondimensional MLP surrogate for thermal ALBSV oil-film force.

    The model input is nondimensional.  By default the base feature vector is::

        [ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim, lr, cq0, cq1, cq2]

    where ``ex, ey`` are eccentricity ratios, ``vx, vy`` are nondimensional
    squeeze velocities, ``sx, sy`` are direct servovalve commands,
    ``lambda_value`` is the Reynolds bearing number, ``beta_nondim`` is the
    thermal viscosity coefficient after temperature nondimensionalisation,
    and ``lr/cq0/cq1/cq2`` are nondimensional geometry/orifice parameters.
    """

    def __init__(
        self,
        model: Net,
        scaler_X,
        scaler_y,
        config=None,
        input_cols=None,
        output_cols=None,
        use_augment: bool = True,
        feature_set: str = "default",
        target_output: str = "cartesian",
    ):
        self.model = model
        self.scaler_X = scaler_X
        self.scaler_y = scaler_y
        self.config = config
        self.input_cols = list(input_cols or ALBNN_BASE_INPUT_COLS)
        self.output_cols = list(output_cols or ALBNN_OUTPUT_COLS)
        self.use_augment = bool(use_augment)
        self.feature_set = feature_set or "default"
        self.target_output = target_output or "cartesian"
        self._x = None

    @property
    def force_scale(self) -> float:
        """Dimensional force scale used by the ALB postprocess: ps*l*r/2."""
        if self.config is None:
            return 1.0
        ps = float(getattr(self.config, "ps", 1.0))
        l = float(getattr(self.config, "l", 1.0))
        r = float(getattr(self.config, "r", 1.0))
        return ps * l * r / 2.0

    def _base_frame(self, x) -> pd.DataFrame:
        if isinstance(x, pd.DataFrame):
            frame = x.copy()
        else:
            arr = np.asarray(x, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            frame = pd.DataFrame(arr, columns=self.input_cols[: arr.shape[1]])
        needed = set(self.input_cols)
        _materialize_polar_pair(
            frame,
            needed,
            x_col="ex",
            y_col="ey",
            sin_col="sin_theta",
            cos_col="cos_theta",
            norm_col="r",
        )
        _materialize_polar_pair(
            frame,
            needed,
            x_col="vx",
            y_col="vy",
            sin_col="sin_v_theta",
            cos_col="cos_v_theta",
            norm_col="v_norm",
        )
        _materialize_polar_pair(
            frame,
            needed,
            x_col="sx",
            y_col="sy",
            sin_col="sin_s_theta",
            cos_col="cos_s_theta",
            norm_col="s_norm",
        )
        _materialize_polar_dot_inputs(frame, needed)
        _materialize_ratio_inputs(frame, needed)
        missing = [col for col in self.input_cols if col not in frame.columns]
        if missing:
            raise ValueError(f"ALBNN input is missing columns: {missing}")
        return frame[self.input_cols]

    def _model_frame(self, x) -> pd.DataFrame:
        frame = self._base_frame(x)
        if self.use_augment:
            frame = albnn_augment_frame(frame, feature_set=self.feature_set)
        expected = list(getattr(self.scaler_X, "feature_names_in_", frame.columns))
        missing = [col for col in expected if col not in frame.columns]
        if missing:
            raise ValueError(f"ALBNN scaled input is missing columns: {missing}")
        return frame[expected]

    def input(
        self,
        uxy,
        uxyt,
        sxy,
        lambda_value=None,
        beta_nondim=None,
        lr=None,
        cq0=None,
        cq1=None,
        cq2=None,
        extra=None,
        nodim: bool = True,
    ):
        """Set one inference point.

        ``nodim=True`` means ``uxy`` and ``uxyt`` are already [ex, ey] and
        [vx, vy].  If ``nodim=False``, ``config.c`` and ``config.freq``/``vf``
        are used to convert displacement and velocity to nondimensional form.
        """
        if not nodim:
            if self.config is None:
                raise ValueError("Dimensional ALBNN input requires a config")
            c = float(getattr(self.config, "c"))
            freq = float(getattr(self.config, "freq"))
            vf = float(getattr(self.config, "vf", 1.0))
            omega = 2.0 * np.pi * freq
            uxy = np.asarray(uxy, dtype=float) / c
            uxyt = np.asarray(uxyt, dtype=float) / (c * vf * omega)
        row = {
            "ex": float(np.asarray(uxy, dtype=float)[0]),
            "ey": float(np.asarray(uxy, dtype=float)[1]),
            "vx": float(np.asarray(uxyt, dtype=float)[0]),
            "vy": float(np.asarray(uxyt, dtype=float)[1]),
            "sx": float(np.asarray(sxy, dtype=float)[0]),
            "sy": float(np.asarray(sxy, dtype=float)[1]),
            "lambda_value": float(
                lambda_value
                if lambda_value is not None
                else getattr(self.config, "lambda_value")
            ),
            "beta_nondim": float(
                beta_nondim
                if beta_nondim is not None
                else getattr(self.config, "beta_nondim")
            ),
            "lr": float(lr if lr is not None else getattr(self.config, "lr")),
            "cq0": float(cq0 if cq0 is not None else getattr(self.config, "cq0")),
            "cq1": float(cq1 if cq1 is not None else getattr(self.config, "cq1")),
            "cq2": float(cq2 if cq2 is not None else getattr(self.config, "cq2")),
        }
        radius = float(np.hypot(row["ex"], row["ey"]))
        if radius > 0.0:
            row["cos"] = row["ex"] / radius
            row["sin"] = row["ey"] / radius
            row["cos_theta"] = row["ex"] / radius
            row["sin_theta"] = row["ey"] / radius
        else:
            row["cos"] = 1.0
            row["sin"] = 0.0
            row["cos_theta"] = 1.0
            row["sin_theta"] = 0.0
        row["r"] = radius
        for prefix, x_col, y_col in (
            ("v", "vx", "vy"),
            ("s", "sx", "sy"),
        ):
            norm = float(np.hypot(row[x_col], row[y_col]))
            if norm > 0.0:
                row[f"cos_{prefix}_theta"] = row[x_col] / norm
                row[f"sin_{prefix}_theta"] = row[y_col] / norm
            else:
                row[f"cos_{prefix}_theta"] = 1.0
                row[f"sin_{prefix}_theta"] = 0.0
            row[f"{prefix}_norm"] = norm
        row["e_dot_v"] = row["ex"] * row["vx"] + row["ey"] * row["vy"]
        row["e_dot_s"] = row["ex"] * row["sx"] + row["ey"] * row["sy"]
        row["s_dot_v"] = row["sx"] * row["vx"] + row["sy"] * row["vy"]
        row["lambda_over_lr"] = row["lambda_value"] / max(row["lr"], 1e-12)
        row["ev_dot"] = row["e_dot_v"]
        row["es_dot"] = row["e_dot_s"]
        row["sv_dot"] = row["s_dot_v"]
        if extra:
            row.update({key: float(value) for key, value in extra.items()})
        config_extra = getattr(self.config, "extra_inputs", None) if self.config else None
        for col in self.input_cols:
            if col in row:
                continue
            if isinstance(config_extra, dict) and col in config_extra:
                row[col] = float(config_extra[col])
            elif self.config is not None and hasattr(self.config, col):
                row[col] = float(getattr(self.config, col))
        self._x = pd.DataFrame([row])

    def predict_nondim(self, x):
        frame = self._model_frame(x)
        x_scaled = torch.tensor(
            self.scaler_X.transform(frame), dtype=torch.float32
        )
        self.model.eval()
        with torch.no_grad():
            y_scaled = self.model(x_scaled).detach().cpu().numpy()
        y_frame = pd.DataFrame(
            y_scaled,
            columns=list(getattr(self.scaler_y, "feature_names_in_", self.output_cols)),
        )
        y_target = self.scaler_y.inverse_transform(y_frame)
        if self.target_output == "force_polar" or self.output_cols == ALBNN_POLAR_FORCE_OUTPUT_COLS:
            return polar_force_to_cartesian(y_target)
        return y_target

    def predict(self, x, nodim: bool = True):
        force = self.predict_nondim(x)
        if nodim:
            return force
        return force * self.force_scale

    def output(self, nodim: bool = True):
        if self._x is None:
            raise ValueError("Call input(...) before output(...)")
        return self.predict(self._x, nodim=nodim)


class ALBNNResidualCorrector:
    """Residual sidecar that corrects a frozen packaged ALBNN prediction.

    The sidecar uses the frozen main model's input scaler and feature contract.
    The residual network predicts cartesian ``fx, fy`` residuals in nondim
    force units, then inference returns ``main + alpha * residual``.
    """

    def __init__(
        self,
        main_model: ALBNN,
        residual_model: Net,
        residual_scaler_y,
        *,
        alpha: float = 1.0,
        config=None,
        metadata=None,
    ):
        self.main_model = main_model
        self.model = residual_model
        self.residual_model = residual_model
        self.scaler_X = main_model.scaler_X
        self.scaler_y = residual_scaler_y
        self.residual_scaler_y = residual_scaler_y
        self.config = config if config is not None else main_model.config
        self.metadata = metadata or {}
        self.alpha = float(alpha)
        self.input_cols = list(main_model.input_cols)
        self.output_cols = list(ALBNN_OUTPUT_COLS)
        self.use_augment = bool(main_model.use_augment)
        self.feature_set = main_model.feature_set
        self.target_output = "cartesian"
        self._x = None

    @property
    def force_scale(self) -> float:
        """Dimensional force scale delegated to the frozen main model."""
        return self.main_model.force_scale

    def _model_frame(self, x) -> pd.DataFrame:
        """Return the frozen main model's scaled-input feature frame."""
        return self.main_model._model_frame(x)

    def input(
        self,
        uxy,
        uxyt,
        sxy,
        lambda_value=None,
        beta_nondim=None,
        lr=None,
        cq0=None,
        cq1=None,
        cq2=None,
        extra=None,
        nodim: bool = True,
    ):
        """Set one inference point using the frozen main model input contract."""
        self.main_model.input(
            uxy,
            uxyt,
            sxy,
            lambda_value=lambda_value,
            beta_nondim=beta_nondim,
            lr=lr,
            cq0=cq0,
            cq1=cq1,
            cq2=cq2,
            extra=extra,
            nodim=nodim,
        )
        self._x = self.main_model._x

    def _predict_residual_nondim(self, x) -> np.ndarray:
        """Predict residual ``fx, fy`` in nondim force units."""
        frame = self.main_model._model_frame(x)
        x_scaled = torch.tensor(
            self.main_model.scaler_X.transform(frame), dtype=torch.float32
        )
        self.residual_model.eval()
        with torch.no_grad():
            y_scaled = self.residual_model(x_scaled).detach().cpu().numpy()
        columns = list(
            getattr(self.residual_scaler_y, "feature_names_in_", ALBNN_OUTPUT_COLS)
        )
        y_frame = pd.DataFrame(y_scaled, columns=columns)
        return np.asarray(self.residual_scaler_y.inverse_transform(y_frame), dtype=float)

    def predict_nondim(self, x):
        main_force = np.asarray(self.main_model.predict_nondim(x), dtype=float)
        residual_force = self._predict_residual_nondim(x)
        return main_force + self.alpha * residual_force

    def predict(self, x, nodim: bool = True):
        force = self.predict_nondim(x)
        if nodim:
            return force
        return force * self.force_scale

    def output(self, nodim: bool = True):
        if self._x is None:
            raise ValueError("Call input(...) before output(...)")
        return self.predict(self._x, nodim=nodim)


def _softmax_numpy(values: np.ndarray) -> np.ndarray:
    """Return row-wise softmax values for stable expert router probabilities."""
    values = np.asarray(values, dtype=float)
    shifted = values - np.max(values, axis=1, keepdims=True)
    exp_values = np.exp(shifted)
    return exp_values / np.sum(exp_values, axis=1, keepdims=True)


def _adjacent_expert_weights(
    probs: np.ndarray,
    confidence_threshold: float = 0.8,
) -> np.ndarray:
    """Return hard-or-adjacent weights from router probabilities.

    High-confidence rows use exactly one expert. Low-confidence rows blend only
    the top expert and one adjacent expert, so non-adjacent experts cannot
    contaminate the force prediction.
    """
    probs = np.asarray(probs, dtype=float)
    if probs.ndim != 2:
        raise ValueError("Expert probabilities must be a 2-D array")
    n_rows, expert_count = probs.shape
    if expert_count < 2:
        raise ValueError("Adjacent expert blending requires at least two experts")
    confidence_threshold = float(confidence_threshold)
    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be in [0, 1]")
    top = np.argmax(probs, axis=1)
    weights = np.zeros_like(probs)
    for row_idx in range(n_rows):
        expert_idx = int(top[row_idx])
        if probs[row_idx, expert_idx] >= confidence_threshold:
            weights[row_idx, expert_idx] = 1.0
            continue
        if expert_idx == 0:
            neighbor_idx = 1
        elif expert_idx == expert_count - 1:
            neighbor_idx = expert_count - 2
        else:
            left_idx = expert_idx - 1
            right_idx = expert_idx + 1
            neighbor_idx = (
                left_idx
                if probs[row_idx, left_idx] >= probs[row_idx, right_idx]
                else right_idx
            )
        selected = probs[row_idx, [expert_idx, neighbor_idx]]
        denom = float(np.sum(selected))
        if denom <= 1e-12:
            weights[row_idx, expert_idx] = 1.0
        else:
            weights[row_idx, expert_idx] = selected[0] / denom
            weights[row_idx, neighbor_idx] = selected[1] / denom
    return weights


class ALBNNForceExpert(ALBNN):
    """Packaged ALBNN force expert with router-based hard or adjacent blending.

    Expert artifacts may use a cartesian ``3 * expert_count`` contract or a
    polar-force ``4 * expert_count`` contract.  Router logits are raw model
    outputs and are never passed through the target scaler.
    """

    def __init__(
        self,
        model: Net,
        scaler_X,
        scaler_y,
        config=None,
        input_cols=None,
        output_cols=None,
        use_augment: bool = True,
        feature_set: str = "default",
        expert_bins=None,
        expert_output_contract: str = "fx_z,fy_z,router_logit",
        expert_inference_mode: str = "adjacent_blend",
        expert_blend_confidence_threshold: float = 0.8,
        target_transform_scale: float = 2.0,
    ):
        super().__init__(
            model,
            scaler_X,
            scaler_y,
            config=config,
            input_cols=input_cols,
            output_cols=output_cols or ALBNN_OUTPUT_COLS,
            use_augment=use_augment,
            feature_set=feature_set,
            target_output="cartesian",
        )
        self.expert_bins = [float(value) for value in (expert_bins or [])]
        self.expert_count = len(self.expert_bins) - 1
        if self.expert_count < 2:
            raise ValueError("ALBNNForceExpert requires at least two expert bins")
        if expert_inference_mode not in {"hard", "adjacent_blend"}:
            raise ValueError(
                "expert_inference_mode must be 'hard' or 'adjacent_blend'"
            )
        self.expert_output_contract = (
            expert_output_contract or "fx_z,fy_z,router_logit"
        )
        self.expert_inference_mode = expert_inference_mode
        self.expert_blend_confidence_threshold = float(
            expert_blend_confidence_threshold
        )
        self.target_transform_scale = float(target_transform_scale)

    def _force_from_expert_code(self, values: np.ndarray) -> np.ndarray:
        """Decode expert force channels while leaving router logits untouched."""
        if self.expert_output_contract == "fx_z,fy_z,router_logit":
            return self.target_transform_scale * np.sinh(np.asarray(values, dtype=float))
        if (
            self.expert_output_contract
            == "sin_f_theta,cos_f_theta,force_norm,router_logit"
        ):
            shape = np.asarray(values).shape
            flat = np.asarray(values, dtype=float).reshape(-1, 3)
            columns = list(
                getattr(
                    self.scaler_y,
                    "feature_names_in_",
                    ALBNN_POLAR_FORCE_OUTPUT_COLS,
                )
            )
            frame = pd.DataFrame(flat, columns=columns)
            decoded = self.scaler_y.inverse_transform(frame)
            return polar_force_to_cartesian(decoded).reshape(*shape[:-1], 2)
        flat = np.asarray(values, dtype=float).reshape(-1, 2)
        columns = list(getattr(self.scaler_y, "feature_names_in_", self.output_cols))
        frame = pd.DataFrame(flat, columns=columns)
        decoded = self.scaler_y.inverse_transform(frame)
        return np.asarray(decoded, dtype=float).reshape(np.asarray(values).shape)

    def _decode_expert_output(self, raw_output: np.ndarray) -> dict[str, np.ndarray]:
        raw_output = np.asarray(raw_output, dtype=float)
        if raw_output.ndim != 2:
            raise ValueError("Expert model output must be a 2-D array")
        target_dim = (
            3
            if self.expert_output_contract
            == "sin_f_theta,cos_f_theta,force_norm,router_logit"
            else 2
        )
        channels_per_expert = target_dim + 1
        expected_cols = channels_per_expert * self.expert_count
        if raw_output.shape[1] != expected_cols:
            raise ValueError(
                f"Expert model output has {raw_output.shape[1]} columns; "
                f"expected {expected_cols}"
            )
        expert_values = raw_output.reshape(
            raw_output.shape[0], self.expert_count, channels_per_expert
        )
        expert_code = expert_values[:, :, :target_dim]
        router_logits = expert_values[:, :, target_dim]
        router_probs = _softmax_numpy(router_logits)
        if self.expert_inference_mode == "hard":
            weights = np.zeros_like(router_probs)
            weights[np.arange(len(router_probs)), np.argmax(router_probs, axis=1)] = 1.0
        else:
            weights = _adjacent_expert_weights(
                router_probs,
                confidence_threshold=self.expert_blend_confidence_threshold,
            )
        final_code = np.sum(expert_code * weights[:, :, None], axis=1)
        expert_force = self._force_from_expert_code(expert_code)
        final_force = self._force_from_expert_code(final_code)
        return {
            "pred_force": final_force,
            "expert_force": expert_force,
            "expert_z": expert_code,
            "router_logits": router_logits,
            "router_probs": router_probs,
            "router_weights": weights,
            "assigned_expert_router": np.argmax(router_probs, axis=1),
            "router_confidence": np.max(router_probs, axis=1),
            "used_blend": np.count_nonzero(weights > 1e-12, axis=1) > 1,
        }

    def predict_expert_details(self, x) -> dict[str, np.ndarray]:
        """Return final force plus per-expert predictions and router weights."""
        frame = self._model_frame(x)
        x_scaled = torch.tensor(
            self.scaler_X.transform(frame), dtype=torch.float32
        )
        self.model.eval()
        with torch.no_grad():
            raw_output = self.model(x_scaled).detach().cpu().numpy()
        return self._decode_expert_output(raw_output)

    def predict_nondim(self, x):
        return self.predict_expert_details(x)["pred_force"]


class IdentityTargetScaler:
    """Sklearn-like scaler that preserves target values exactly.

    Training workflows can wrap this scaler with reversible target transforms
    such as :class:`AsinhTargetScaler` when the transformed target is already in
    a suitable numerical range and should not be minmax- or standard-scaled.
    The class stores ``feature_names_in_`` so packaged ALBNN inference keeps the
    same column contract as other sklearn-style scalers.
    """

    def __init__(self):
        self.feature_names_in_ = None

    def fit(self, y):
        frame = pd.DataFrame(y)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        return self

    def transform(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        return frame.to_numpy(dtype=float, copy=True)

    def fit_transform(self, y):
        return self.fit(y).transform(y)

    def inverse_transform(self, y_scaled):
        return np.asarray(y_scaled, dtype=float).copy()


class StandardTargetScaler:
    """Sklearn-like standard scaler with a differentiable torch inverse."""

    def __init__(self):
        self.feature_names_in_ = None
        self.mean_ = None
        self.scale_ = None

    def fit(self, y):
        frame = pd.DataFrame(y)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        values = frame.to_numpy(dtype=float)
        self.mean_ = values.mean(axis=0)
        std = values.std(axis=0)
        self.scale_ = np.where(std > 0.0, std, 1.0)
        return self

    def transform(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        values = frame.to_numpy(dtype=float)
        return (values - self.mean_) / self.scale_

    def fit_transform(self, y):
        return self.fit(y).transform(y)

    def inverse_transform(self, y_scaled):
        return np.asarray(y_scaled, dtype=float) * self.scale_ + self.mean_

    def inverse_transform_torch(self, y_scaled):
        device = y_scaled.device
        dtype = y_scaled.dtype
        mean = torch.as_tensor(self.mean_, dtype=dtype, device=device)
        scale = torch.as_tensor(self.scale_, dtype=dtype, device=device)
        return y_scaled * scale + mean


class SelectiveStandardScaler:
    """Standardize selected columns while leaving pass-through columns unchanged."""

    def __init__(
        self,
        pass_through_columns: tuple[str, ...] | list[str] | set[str] = (),
    ):
        self.pass_through_columns = tuple(pass_through_columns)
        self.feature_names_in_ = None
        self.scale_columns_ = None
        self.mean_ = None
        self.scale_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.scale_columns_ = [
            col for col in frame.columns if col not in set(self.pass_through_columns)
        ]
        values = frame[self.scale_columns_].to_numpy(dtype=float)
        if values.shape[1] == 0:
            self.mean_ = np.asarray([], dtype=float)
            self.scale_ = np.asarray([], dtype=float)
        else:
            self.mean_ = values.mean(axis=0)
            std = values.std(axis=0)
            self.scale_ = np.where(std > 0.0, std, 1.0)
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        result = frame.to_numpy(dtype=float, copy=True)
        if self.scale_columns_:
            indices = [list(self.feature_names_in_).index(col) for col in self.scale_columns_]
            result[:, indices] = (result[:, indices] - self.mean_) / self.scale_
        return result

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        result = np.asarray(x_scaled, dtype=float).copy()
        if self.scale_columns_:
            indices = [list(self.feature_names_in_).index(col) for col in self.scale_columns_]
            result[:, indices] = result[:, indices] * self.scale_ + self.mean_
        return result

    def inverse_transform_torch(self, x_scaled):
        device = x_scaled.device
        dtype = x_scaled.dtype
        result = x_scaled.clone()
        if self.scale_columns_:
            indices = [list(self.feature_names_in_).index(col) for col in self.scale_columns_]
            index_tensor = torch.as_tensor(indices, dtype=torch.long, device=device)
            mean = torch.as_tensor(self.mean_, dtype=dtype, device=device)
            scale = torch.as_tensor(self.scale_, dtype=dtype, device=device)
            values = result.index_select(-1, index_tensor) * scale + mean
            result = result.clone()
            result[..., index_tensor] = values
        return result


class StandardThenMinMaxScaler:
    """Apply per-column standardization followed by minmax scaling.

    The transform is fully affine and sklearn-like, so it can be pickled with
    trained ALBNN artifacts and used by packaged inference.  It is useful when
    preserving the old force-scaling style while keeping a bounded network
    target range.
    """

    def __init__(self, feature_range: tuple[float, float] = (0.0, 1.0)):
        self.feature_range = tuple(float(value) for value in feature_range)
        self.feature_names_in_ = None
        self.mean_ = None
        self.std_ = None
        self.std_min_ = None
        self.std_max_ = None
        self.std_range_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        values = frame.to_numpy(dtype=float)
        self.mean_ = values.mean(axis=0)
        std = values.std(axis=0)
        self.std_ = np.where(std > 0.0, std, 1.0)
        standardized = (values - self.mean_) / self.std_
        self.std_min_ = standardized.min(axis=0)
        self.std_max_ = standardized.max(axis=0)
        self.std_range_ = self.std_max_ - self.std_min_
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        values = frame.to_numpy(dtype=float)
        standardized = (values - self.mean_) / self.std_
        return self._minmax_forward(standardized)

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        standardized = self._minmax_inverse(np.asarray(x_scaled, dtype=float))
        return standardized * self.std_ + self.mean_

    def _minmax_forward(self, values: np.ndarray) -> np.ndarray:
        lo, hi = self.feature_range
        span = hi - lo
        safe_range = np.where(self.std_range_ > 0.0, self.std_range_, 1.0)
        scaled = (values - self.std_min_) / safe_range
        scaled = scaled * span + lo
        zero_range = self.std_range_ <= 0.0
        if np.any(zero_range):
            scaled[:, zero_range] = 0.5 * (lo + hi)
        return scaled

    def _minmax_inverse(self, values: np.ndarray) -> np.ndarray:
        lo, hi = self.feature_range
        span = hi - lo
        unscaled = (values - lo) / span
        safe_range = np.where(self.std_range_ > 0.0, self.std_range_, 1.0)
        return unscaled * safe_range + self.std_min_

    def inverse_transform_torch(self, x_scaled):
        device = x_scaled.device
        dtype = x_scaled.dtype
        lo, hi = self.feature_range
        span = hi - lo
        mean = torch.as_tensor(self.mean_, dtype=dtype, device=device)
        std = torch.as_tensor(self.std_, dtype=dtype, device=device)
        std_min = torch.as_tensor(self.std_min_, dtype=dtype, device=device)
        std_range = torch.as_tensor(self.std_range_, dtype=dtype, device=device)
        safe_range = torch.where(std_range > 0.0, std_range, torch.ones_like(std_range))
        standardized = (x_scaled - float(lo)) / float(span)
        standardized = standardized * safe_range + std_min
        return standardized * std + mean


class MotionStandardParamMinMaxScaler:
    """Standardize motion states and standardize+minmax remaining inputs.

    By default, ``ex, ey, vx, vy, sx, sy`` are left in standardized space.
    Every other column is first standardized and then mapped to ``feature_range``.
    This matches the ALBNN contract where motion/servo vectors may benefit from
    signed standardized coordinates while structural parameters stay bounded.
    """

    def __init__(
        self,
        standard_only_columns: tuple[str, ...] | list[str] | set[str] = (
            "ex",
            "ey",
            "vx",
            "vy",
            "sx",
            "sy",
        ),
        feature_range: tuple[float, float] = (0.0, 1.0),
    ):
        self.standard_only_columns = tuple(standard_only_columns)
        self.feature_range = tuple(float(value) for value in feature_range)
        self.feature_names_in_ = None
        self.standard_only_columns_ = None
        self.minmax_columns_ = None
        self.mean_ = None
        self.std_ = None
        self.mm_min_ = None
        self.mm_max_ = None
        self.mm_range_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        columns = list(frame.columns)
        standard_only = set(self.standard_only_columns)
        self.standard_only_columns_ = [
            col for col in columns if col in standard_only
        ]
        self.minmax_columns_ = [col for col in columns if col not in standard_only]
        values = frame.to_numpy(dtype=float)
        self.mean_ = values.mean(axis=0)
        std = values.std(axis=0)
        self.std_ = np.where(std > 0.0, std, 1.0)
        standardized = (values - self.mean_) / self.std_
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            mm_values = standardized[:, indices]
            self.mm_min_ = mm_values.min(axis=0)
            self.mm_max_ = mm_values.max(axis=0)
            self.mm_range_ = self.mm_max_ - self.mm_min_
        else:
            self.mm_min_ = np.asarray([], dtype=float)
            self.mm_max_ = np.asarray([], dtype=float)
            self.mm_range_ = np.asarray([], dtype=float)
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        columns = list(self.feature_names_in_)
        values = frame.to_numpy(dtype=float)
        result = (values - self.mean_) / self.std_
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.mm_range_ > 0.0, self.mm_range_, 1.0)
            scaled = (result[:, indices] - self.mm_min_) / safe_range
            scaled = scaled * span + lo
            zero_range = self.mm_range_ <= 0.0
            if np.any(zero_range):
                scaled[:, zero_range] = 0.5 * (lo + hi)
            result[:, indices] = scaled
        return result

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        columns = list(self.feature_names_in_)
        result = np.asarray(x_scaled, dtype=float).copy()
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.mm_range_ > 0.0, self.mm_range_, 1.0)
            values = (result[:, indices] - lo) / span
            result[:, indices] = values * safe_range + self.mm_min_
        return result * self.std_ + self.mean_


class MotionStandardParamDirectMinMaxScaler:
    """Standardize motion states and minmax-scale remaining inputs directly.

    ``ex, ey, vx, vy, sx, sy`` stay in standardized coordinates.  All other
    columns are mapped to ``feature_range`` from their raw training-set min/max,
    without the redundant standardization step used by
    :class:`MotionStandardParamMinMaxScaler`.
    """

    def __init__(
        self,
        standard_only_columns: tuple[str, ...] | list[str] | set[str] = (
            "ex",
            "ey",
            "vx",
            "vy",
            "sx",
            "sy",
        ),
        feature_range: tuple[float, float] = (0.0, 1.0),
    ):
        self.standard_only_columns = tuple(standard_only_columns)
        self.feature_range = tuple(float(value) for value in feature_range)
        self.feature_names_in_ = None
        self.standard_only_columns_ = None
        self.minmax_columns_ = None
        self.mean_ = None
        self.std_ = None
        self.mm_min_ = None
        self.mm_max_ = None
        self.mm_range_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        columns = list(frame.columns)
        standard_only = set(self.standard_only_columns)
        self.standard_only_columns_ = [
            col for col in columns if col in standard_only
        ]
        self.minmax_columns_ = [col for col in columns if col not in standard_only]
        values = frame.to_numpy(dtype=float)
        self.mean_ = values.mean(axis=0)
        std = values.std(axis=0)
        self.std_ = np.where(std > 0.0, std, 1.0)
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            mm_values = values[:, indices]
            self.mm_min_ = mm_values.min(axis=0)
            self.mm_max_ = mm_values.max(axis=0)
            self.mm_range_ = self.mm_max_ - self.mm_min_
        else:
            self.mm_min_ = np.asarray([], dtype=float)
            self.mm_max_ = np.asarray([], dtype=float)
            self.mm_range_ = np.asarray([], dtype=float)
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        columns = list(self.feature_names_in_)
        values = frame.to_numpy(dtype=float)
        result = values.copy()
        if self.standard_only_columns_:
            indices = [columns.index(col) for col in self.standard_only_columns_]
            result[:, indices] = (values[:, indices] - self.mean_[indices]) / self.std_[
                indices
            ]
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.mm_range_ > 0.0, self.mm_range_, 1.0)
            scaled = (values[:, indices] - self.mm_min_) / safe_range
            scaled = scaled * span + lo
            zero_range = self.mm_range_ <= 0.0
            if np.any(zero_range):
                scaled[:, zero_range] = 0.5 * (lo + hi)
            result[:, indices] = scaled
        return result

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        columns = list(self.feature_names_in_)
        result = np.asarray(x_scaled, dtype=float).copy()
        if self.standard_only_columns_:
            indices = [columns.index(col) for col in self.standard_only_columns_]
            result[:, indices] = result[:, indices] * self.std_[indices] + self.mean_[
                indices
            ]
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.mm_range_ > 0.0, self.mm_range_, 1.0)
            values = (result[:, indices] - lo) / span
            result[:, indices] = values * safe_range + self.mm_min_
        return result


class PolarMotionStandardParamMinMaxScaler:
    """Scale polar ALBNN inputs with angle pass-through and selected standards.

    Angular sine/cosine columns already live in a bounded physical range and are
    passed through unchanged.  Norms and explicit dot products are standardized
    only.  Remaining scalar parameters are standardized and then minmax-scaled.
    """

    def __init__(
        self,
        pass_through_columns: tuple[str, ...] | list[str] | set[str] = (
            "sin_theta",
            "cos_theta",
            "sin_v_theta",
            "cos_v_theta",
            "sin_s_theta",
            "cos_s_theta",
        ),
        standard_only_columns: tuple[str, ...] | list[str] | set[str] = (
            "r",
            "v_norm",
            "s_norm",
            "e_dot_v",
            "e_dot_s",
            "s_dot_v",
            "ev_dot",
            "es_dot",
            "sv_dot",
            "v_dot_s",
        ),
        feature_range: tuple[float, float] = (0.0, 1.0),
    ):
        self.pass_through_columns = tuple(pass_through_columns)
        self.standard_only_columns = tuple(standard_only_columns)
        self.feature_range = tuple(float(value) for value in feature_range)
        self.feature_names_in_ = None
        self.pass_through_columns_ = None
        self.standard_only_columns_ = None
        self.minmax_columns_ = None
        self.mean_ = None
        self.std_ = None
        self.mm_min_ = None
        self.mm_max_ = None
        self.mm_range_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        columns = list(frame.columns)
        pass_through = set(self.pass_through_columns)
        standard_only = set(self.standard_only_columns)
        self.pass_through_columns_ = [
            col for col in columns if col in pass_through
        ]
        self.standard_only_columns_ = [
            col for col in columns if col in standard_only and col not in pass_through
        ]
        scaled_or_standard = [
            col for col in columns if col not in set(self.pass_through_columns_)
        ]
        self.minmax_columns_ = [
            col for col in scaled_or_standard if col not in set(self.standard_only_columns_)
        ]
        values = frame.to_numpy(dtype=float)
        self.mean_ = values.mean(axis=0)
        std = values.std(axis=0)
        self.std_ = np.where(std > 0.0, std, 1.0)
        standardized = (values - self.mean_) / self.std_
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            mm_values = standardized[:, indices]
            self.mm_min_ = mm_values.min(axis=0)
            self.mm_max_ = mm_values.max(axis=0)
            self.mm_range_ = self.mm_max_ - self.mm_min_
        else:
            self.mm_min_ = np.asarray([], dtype=float)
            self.mm_max_ = np.asarray([], dtype=float)
            self.mm_range_ = np.asarray([], dtype=float)
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        columns = list(self.feature_names_in_)
        values = frame.to_numpy(dtype=float)
        result = values.copy()
        scaled_or_standard = [
            col for col in columns if col not in set(self.pass_through_columns_)
        ]
        if scaled_or_standard:
            indices = [columns.index(col) for col in scaled_or_standard]
            result[:, indices] = (values[:, indices] - self.mean_[indices]) / self.std_[indices]
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.mm_range_ > 0.0, self.mm_range_, 1.0)
            scaled = (result[:, indices] - self.mm_min_) / safe_range
            scaled = scaled * span + lo
            zero_range = self.mm_range_ <= 0.0
            if np.any(zero_range):
                scaled[:, zero_range] = 0.5 * (lo + hi)
            result[:, indices] = scaled
        return result

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        columns = list(self.feature_names_in_)
        result = np.asarray(x_scaled, dtype=float).copy()
        if self.minmax_columns_:
            indices = [columns.index(col) for col in self.minmax_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.mm_range_ > 0.0, self.mm_range_, 1.0)
            values = (result[:, indices] - lo) / span
            result[:, indices] = values * safe_range + self.mm_min_
        scaled_or_standard = [
            col for col in columns if col not in set(self.pass_through_columns_)
        ]
        if scaled_or_standard:
            indices = [columns.index(col) for col in scaled_or_standard]
            result[:, indices] = result[:, indices] * self.std_[indices] + self.mean_[indices]
        return result


class AsinhTargetScaler:
    """Sklearn-like target scaler with a reversible asinh force transform."""

    def __init__(self, base_scaler, scale: float = 5.0):
        self.base_scaler = base_scaler
        self.scale = float(scale)
        self.feature_names_in_ = None

    def fit(self, y):
        frame = pd.DataFrame(y)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.base_scaler.fit(self._forward(frame))
        return self

    def transform(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        return self.base_scaler.transform(self._forward(frame))

    def fit_transform(self, y):
        return self.fit(y).transform(y)

    def inverse_transform(self, y_scaled):
        transformed = self.base_scaler.inverse_transform(y_scaled)
        return self._inverse(transformed)

    def _forward(self, y):
        return np.arcsinh(np.asarray(y, dtype=float) / self.scale)

    def _inverse(self, transformed):
        return np.sinh(np.asarray(transformed, dtype=float)) * self.scale


class SignedLog1pTargetScaler:
    """Sklearn-like target scaler with a reversible signed log1p transform."""

    def __init__(self, base_scaler, scale: float = 5.0):
        self.base_scaler = base_scaler
        self.scale = float(scale)
        self.feature_names_in_ = None

    def fit(self, y):
        frame = pd.DataFrame(y)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.base_scaler.fit(self._forward(frame))
        return self

    def transform(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        return self.base_scaler.transform(self._forward(frame))

    def fit_transform(self, y):
        return self.fit(y).transform(y)

    def inverse_transform(self, y_scaled):
        transformed = self.base_scaler.inverse_transform(y_scaled)
        return self._inverse(transformed)

    def _forward(self, y):
        values = np.asarray(y, dtype=float)
        return np.sign(values) * np.log1p(np.abs(values) / self.scale)

    def _inverse(self, transformed):
        values = np.asarray(transformed, dtype=float)
        return np.sign(values) * self.scale * np.expm1(np.abs(values))


class MinMaxCubeRootTargetScaler:
    """Scale force targets with minmax, then apply a reversible cube root."""

    def __init__(self, base_scaler):
        self.base_scaler = base_scaler
        self.feature_names_in_ = None

    def fit(self, y):
        frame = pd.DataFrame(y)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.base_scaler.fit(frame)
        return self

    def transform(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        scaled = self.base_scaler.transform(frame)
        return np.cbrt(scaled)

    def fit_transform(self, y):
        return self.fit(y).transform(y)

    def inverse_transform(self, y_scaled):
        scaled = np.asarray(y_scaled, dtype=float) ** 3
        return self.base_scaler.inverse_transform(scaled)


class ColumnSignedLog1pTargetScaler:
    """Apply signed ``log1p`` to selected target columns before base scaling.

    This wrapper preserves the sklearn-style scaler interface used by packaged
    ALBNN artifacts. It is intended for mixed target contracts where angular
    sine/cosine columns should remain unchanged while non-negative magnitude
    columns such as ``force_norm`` are compressed before minmax scaling.
    """

    def __init__(
        self,
        base_scaler,
        columns: tuple[str, ...] | list[str] | set[str],
        scale: float = 5.0,
    ):
        self.base_scaler = base_scaler
        self.columns = tuple(columns)
        self.scale = float(scale)
        self.feature_names_in_ = None

    def fit(self, y):
        frame = pd.DataFrame(y)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self._validate_columns()
        self.base_scaler.fit(self._forward(frame))
        return self

    def transform(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        return self.base_scaler.transform(self._forward(frame))

    def fit_transform(self, y):
        return self.fit(y).transform(y)

    def inverse_transform(self, y_scaled):
        transformed = self.base_scaler.inverse_transform(y_scaled)
        return self._inverse(transformed)

    def _validate_columns(self):
        missing = [col for col in self.columns if col not in set(self.feature_names_in_)]
        if missing:
            raise ValueError(f"Missing signed-log target column(s): {missing}")

    def _forward(self, y):
        frame = pd.DataFrame(y, columns=self.feature_names_in_)
        values = frame.to_numpy(dtype=float, copy=True)
        for col in self.columns:
            idx = list(frame.columns).index(col)
            col_values = values[:, idx]
            values[:, idx] = np.sign(col_values) * np.log1p(
                np.abs(col_values) / self.scale
            )
        return pd.DataFrame(values, columns=frame.columns, index=frame.index)

    def _inverse(self, transformed):
        values = np.asarray(transformed, dtype=float).copy()
        for col in self.columns:
            idx = list(self.feature_names_in_).index(col)
            col_values = values[:, idx]
            values[:, idx] = np.sign(col_values) * self.scale * np.expm1(
                np.abs(col_values)
            )
        return values


class SelectiveMinMaxScaler:
    """Minmax-scale selected columns while leaving pass-through columns unchanged."""

    def __init__(
        self,
        feature_range: tuple[float, float] = (0.0, 1.0),
        pass_through_columns: tuple[str, ...] | list[str] | set[str] = (),
    ):
        self.feature_range = tuple(float(value) for value in feature_range)
        self.pass_through_columns = tuple(pass_through_columns)
        self.feature_names_in_ = None
        self.scale_columns_ = None
        self.data_min_ = None
        self.data_max_ = None
        self.data_range_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.scale_columns_ = [
            col for col in frame.columns if col not in set(self.pass_through_columns)
        ]
        values = frame[self.scale_columns_].to_numpy(dtype=float)
        if values.shape[1] == 0:
            self.data_min_ = np.asarray([], dtype=float)
            self.data_max_ = np.asarray([], dtype=float)
            self.data_range_ = np.asarray([], dtype=float)
        else:
            self.data_min_ = values.min(axis=0)
            self.data_max_ = values.max(axis=0)
            self.data_range_ = self.data_max_ - self.data_min_
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        result = frame.to_numpy(dtype=float, copy=True)
        if self.scale_columns_:
            indices = [list(self.feature_names_in_).index(col) for col in self.scale_columns_]
            values = result[:, indices]
            lo, hi = self.feature_range
            span = hi - lo
            safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
            scaled = (values - self.data_min_) / safe_range
            scaled = scaled * span + lo
            zero_range = self.data_range_ <= 0.0
            if np.any(zero_range):
                scaled[:, zero_range] = 0.5 * (lo + hi)
            result[:, indices] = scaled
        return result

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        result = np.asarray(x_scaled, dtype=float).copy()
        if self.scale_columns_:
            indices = [list(self.feature_names_in_).index(col) for col in self.scale_columns_]
            lo, hi = self.feature_range
            span = hi - lo
            values = (result[:, indices] - lo) / span
            safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
            restored = values * safe_range + self.data_min_
            zero_range = self.data_range_ <= 0.0
            if np.any(zero_range):
                restored[:, zero_range] = self.data_min_[zero_range]
            result[:, indices] = restored
        return result

    def inverse_transform_torch(self, x_scaled):
        device = x_scaled.device
        dtype = x_scaled.dtype
        result = x_scaled.clone()
        if self.scale_columns_:
            indices = [list(self.feature_names_in_).index(col) for col in self.scale_columns_]
            index_tensor = torch.as_tensor(indices, dtype=torch.long, device=device)
            lo, hi = self.feature_range
            span = hi - lo
            data_min = torch.as_tensor(self.data_min_, dtype=dtype, device=device)
            data_range = torch.as_tensor(self.data_range_, dtype=dtype, device=device)
            safe_range = torch.where(
                data_range > 0.0, data_range, torch.ones_like(data_range)
            )
            values = (result.index_select(-1, index_tensor) - float(lo)) / float(span)
            values = values * safe_range + data_min
            zero_range = data_range <= 0.0
            values = torch.where(zero_range, data_min, values)
            result = result.clone()
            result[..., index_tensor] = values
        return result


class MinMaxWithScaledEvsFeaturesScaler:
    """Minmax-scale base inputs, then append E/V/S interaction features.

    This scaler implements a 12-base-input ALBNN contract where
    ``ex, ey, vx, vy, sx, sy`` and the scalar parameters are first mapped to the
    configured minmax range.  The appended features are then computed from that
    scaled coordinate system and are not scaled a second time.  This keeps the
    training-time and packaged-inference feature contract identical when the
    user wants interaction terms to describe the normalized model input space.

    Appended feature order:
    ``evs_geom, edotv, edots, sdotv``.
    """

    appended_feature_names = ("evs_geom", "edotv", "edots", "sdotv")

    def __init__(self, feature_range: tuple[float, float] = (0.0, 1.0)):
        self.feature_range = tuple(float(value) for value in feature_range)
        self.base_scaler = SelectiveMinMaxScaler(feature_range=self.feature_range)
        self.feature_names_in_ = None
        self.feature_names_out_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        missing = [
            col
            for col in ("ex", "ey", "vx", "vy", "sx", "sy")
            if col not in frame.columns
        ]
        if missing:
            raise ValueError(
                "MinMaxWithScaledEvsFeaturesScaler requires motion columns: "
                f"{missing}"
            )
        self.base_scaler.fit(frame)
        self.feature_names_out_ = np.asarray(
            list(self.feature_names_in_) + list(self.appended_feature_names),
            dtype=object,
        )
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        scaled = self.base_scaler.transform(frame)
        scaled_frame = pd.DataFrame(scaled, columns=self.feature_names_in_)
        appended = self._scaled_evs_features(scaled_frame)
        return np.column_stack([scaled, appended])

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        values = np.asarray(x_scaled, dtype=float)
        base_width = len(self.feature_names_in_)
        return self.base_scaler.inverse_transform(values[:, :base_width])

    def _scaled_evs_features(self, frame: pd.DataFrame) -> np.ndarray:
        ex = frame["ex"].to_numpy(dtype=float)
        ey = frame["ey"].to_numpy(dtype=float)
        vx = frame["vx"].to_numpy(dtype=float)
        vy = frame["vy"].to_numpy(dtype=float)
        sx = frame["sx"].to_numpy(dtype=float)
        sy = frame["sy"].to_numpy(dtype=float)

        e_norm = np.sqrt(ex**2 + ey**2)
        v_norm = np.sqrt(vx**2 + vy**2)
        s_norm = np.sqrt(sx**2 + sy**2)
        evs_geom = np.cbrt(np.clip(e_norm * v_norm * s_norm, 0.0, None))
        edotv = ex * vx + ey * vy
        edots = ex * sx + ey * sy
        sdotv = sx * vx + sy * vy
        return np.column_stack([evs_geom, edotv, edots, sdotv])


class Cq2SigLogMinMaxScaler:
    """Scale ALBNN inputs with log-compressed ``cq2`` and minmax scaling.

    The ALBNN base inputs contain strictly positive flow coefficients.  This
    scaler keeps the feature count unchanged, applies a natural-log transform
    only to ``cq2``, then minmax-scales every input column to ``feature_range``.
    The default range remains ``[-1, 1]`` for compatibility with existing model
    artifacts; pass ``feature_range=(0, 1)`` for the newer 0..1 input contract.
    """

    def __init__(
        self,
        feature_range: tuple[float, float] = (-1.0, 1.0),
        log_column: str = "cq2",
        epsilon: float = 1e-12,
        pass_through_columns: tuple[str, ...] | list[str] | set[str] = (),
    ):
        self.feature_range = tuple(float(value) for value in feature_range)
        self.log_column = str(log_column)
        self.epsilon = float(epsilon)
        self.pass_through_columns = tuple(pass_through_columns)
        self.feature_names_in_ = None
        self.data_min_ = None
        self.data_max_ = None
        self.data_range_ = None

    def fit(self, x):
        frame = pd.DataFrame(x)
        if self.log_column not in frame.columns:
            raise ValueError(f"Missing log-scaled column: {self.log_column}")
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        values = self._forward(frame)
        self.data_min_ = values.min(axis=0)
        self.data_max_ = values.max(axis=0)
        self.data_range_ = self.data_max_ - self.data_min_
        return self

    def transform(self, x):
        frame = pd.DataFrame(x, columns=self.feature_names_in_)
        values = self._forward(frame)
        lo, hi = self.feature_range
        span = hi - lo
        safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
        scaled = (values - self.data_min_) / safe_range
        scaled = scaled * span + lo
        zero_range = self.data_range_ <= 0.0
        if np.any(zero_range):
            scaled[:, zero_range] = 0.5 * (lo + hi)
        for col in getattr(self, "pass_through_columns", ()):
            if col in frame.columns:
                idx = list(frame.columns).index(col)
                scaled[:, idx] = values[:, idx]
        return scaled

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        lo, hi = self.feature_range
        span = hi - lo
        x_scaled = np.asarray(x_scaled, dtype=float)
        values = (x_scaled - lo) / span
        safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
        values = values * safe_range + self.data_min_
        for col in getattr(self, "pass_through_columns", ()):
            if col in list(self.feature_names_in_):
                idx = list(self.feature_names_in_).index(col)
                values[:, idx] = x_scaled[:, idx]
        log_idx = list(self.feature_names_in_).index(self.log_column)
        if self.log_column not in getattr(self, "pass_through_columns", ()):
            values[:, log_idx] = np.exp(values[:, log_idx])
        return values

    def _forward(self, x):
        columns = (
            list(self.feature_names_in_)
            if self.feature_names_in_ is not None
            else list(x.columns)
        )
        frame = pd.DataFrame(x, columns=columns)
        values = frame.to_numpy(dtype=float, copy=True)
        log_idx = list(frame.columns).index(self.log_column)
        values[:, log_idx] = np.log(np.clip(values[:, log_idx], self.epsilon, None))
        return values


class ALBNet:
    def __init__(self, model: Net, scaled_X, scaled_y, albnet_config):
        """
        :param model: the neural network model
        :param albnet_config: the configuration for ALBNet
        """
        super().__init__()
        self.config = albnet_config
        self._net = NetApl(model, scaled_X, scaled_y)
        self._uxy = None
        self._uxyt = None
        self._sxy = None
        self._c = albnet_config.c
        self._vf = albnet_config.vf
        self._freq = albnet_config.freq
        self._ps = albnet_config.ps
        self._l = albnet_config.l
        self._r = albnet_config.r

    def input(self, uxy, uxyt, sxy, nodim=False):
        if nodim:
            self._uxy = uxy
            self._uxyt = uxyt
        else:
            self._uxy = uxy / self._c
            self._uxyt = uxyt / self._c / (self._vf * self._freq * 2 * np.pi)

        self._sxy = sxy

    def output(self, nodim=False):
        x = np.concatenate(
            [[self._freq], self._uxy, self._uxyt, self._sxy], axis=0
        ).reshape(1, -1)
        x_add = np.sqrt(np.abs(x))
        x = np.concatenate([x, x_add.reshape(1, -1)], axis=1)
        nodim_force = self._net.predict(x)
        if nodim:
            force = nodim_force
        else:
            force = nodim_force * self._ps * self._l / 2 * self._r

        return force

    def predict(self, x):
        return self._net.predict(x)


def alb_agent_nn(albnet_config):
    scaler_X = albnet_config.scaler_X
    scaler_y = albnet_config.scaler_y
    with open(scaler_X, "rb") as f:
        scaler_X_model = pd.read_pickle(f)
    with open(scaler_y, "rb") as f:
        scaler_y_model = pd.read_pickle(f)
    model = torch.load(
        albnet_config.model, map_location=torch.device("cpu"), weights_only=True
    )
    net = net_from_checkpoint(model)
    net.load_state_dict(model["model_state_dict"])
    alb_net = ALBNet(net, scaler_X_model, scaler_y_model, albnet_config=albnet_config)
    return alb_net


def train_loop(dataloader, model, loss_fn, optimizer, batch_size):
    size = len(dataloader.dataset)
    # Set the model to training mode - important for batch normalization and dropout layers
    # Unnecessary in this situation but added for best practices
    model.train()
    for batch, (X, y) in enumerate(dataloader):
        # Compute prediction and loss
        pred = model(X)
        loss = loss_fn(pred, y)

        # Backpropagation
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()

        if batch % 100 == 0:
            loss, current = loss.item(), batch * batch_size + len(X)
            print(f"loss: {loss:>7f}  [{current:>5d}/{size:>5d}]")


def test_loop(dataloader, model, loss_fn):
    # Set the model to evaluation mode - important for batch normalization and dropout layers
    # Unnecessary in this situation but added for best practices
    model.eval()
    size = len(dataloader.dataset)
    num_batches = len(dataloader)
    test_loss, correct = 0, 0

    # Evaluating the model with torch.no_grad() ensures that no gradients are computed during test mode
    # also serves to reduce unnecessary gradient computations and memory usage for tensors with requires_grad=True
    with torch.no_grad():
        for X, y in dataloader:
            pred = model(X)
            test_loss += loss_fn(pred, y).item()
            # Assuming the output is a regression task, we can compute accuracy based on a threshold
            correct += ((pred - y).abs() < 0.1).all(dim=1).sum().item()
    test_loss /= num_batches
    correct /= size
    print(
        f"Test Error: \n Accuracy: {(100 * correct):>0.1f}%, Avg loss: {test_loss:>8f} \n"
    )


def mlp_train(
    net,
    architecture,
    iterations,
    best_model_path,
    x_train,
    y_train,
    optimizer,
    x_test,
    y_test,
    batch_size=64,
    device="cpu",
):
    best_loss = float("inf")
    patience = 3000
    patience_counter = 0
    mse = nn.MSELoss()
    net.to(device)
    x_train, y_train = x_train.to(device), y_train.to(device)
    x_test, y_test = x_test.to(device), y_test.to(device)
    train_dataset = TensorDataset(x_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    loss_epoch = []
    loss_test_epoch = []
    for epoch in range(iterations):
        net.train()
        train_loss = 0.0

        for x_batch, y_batch in train_loader:
            outputs = net(x_batch)
            loss = mse(outputs, y_batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * x_batch.size(0)
        train_loss /= len(train_loader.dataset)
        net.eval()
        with torch.no_grad():
            outputs_test = net(x_test)
            loss_test = mse(outputs_test, y_test)

        if (epoch + 1) % 100 == 0:
            print(
                f"epoch: {epoch + 1} / {iterations}, loss: {loss:.2e}, loss_test: {loss_test:.2e}"
            )
            loss_epoch.append(train_loss)
            loss_test_epoch.append(loss_test.item())

        if loss_test < best_loss:
            best_loss = loss_test
            patience_counter = 0
            save_model(net, best_model_path, architecture)
        else:
            patience_counter += 1

        if patience_counter >= patience:
            print(f"Early stopping at epoch {epoch + 1}")
            break
    checkpoint = torch.load(best_model_path, map_location=device)
    net.load_state_dict(checkpoint["model_state_dict"])
    return loss_epoch, loss_test_epoch


def save_model(net, path, architecture):
    torch.save(
        {
            "model_state_dict": net.state_dict(),
            "architecture": architecture,
            "activation": getattr(net, "activation", "gelu"),
            "sine_omega0": float(getattr(net, "sine_omega0", 30.0)),
            "use_layer_norm": bool(getattr(net, "use_layer_norm", False)),
        },
        path,
    )


def get_samples_bound(samples: pd.DataFrame) -> dict:
    """
    Compute per-column lower and upper bounds from a samples DataFrame.

    :param samples: Sample dataset where each column is a variable.
    :return: Mapping of column name to (min, max) tuple.
    """
    lower_bound = samples.min()
    upper_bound = samples.max()
    columns = samples.columns.tolist()
    bounds = {
        col: (lower_bound.iloc[i].item(), upper_bound.iloc[i].item())
        for i, col in enumerate(columns)
    }
    return bounds


# ---------------------------------------------------------------------------
# Thermal bearing force surrogate model
# ---------------------------------------------------------------------------


class ThermalALBNet:
    """Neural-network surrogate for thermal bearing force prediction.

    Unlike :class:`ALBNet` which uses 7 base features (freq + uxy + uxyt + sxy),
    this class accepts 10 features including thermal parameters (beta, t_in, ps)
    and supports optional sqrt(|x|) feature augmentation.

    Typical usage::

        from ALB.nn import thermal_albnet

        net = thermal_albnet(config)
        net.input(uxy, uxyt, sxy, freq=50.0, beta=0.03, t_in=40.0, ps=3e6)
        result = net.output()  # shape (1, 3): [fx, fy, t_eff]
    """

    # Feature column names (must match training CSV)
    INPUT_COLS = ["ex", "ey", "vx", "vy", "sx", "sy", "freq", "beta", "t_in", "ps"]
    OUTPUT_COLS = ["fx", "fy", "t_eff"]

    def __init__(self, model: Net, scaled_X, scaled_y, config, use_augment: bool = True):
        """
        :param model: trained Net instance
        :param scaled_X: fitted StandardScaler for input features
        :param scaled_y: fitted StandardScaler for output targets
        :param config: configuration object with c, ps, l, r, freq attributes
        :param use_augment: whether to apply sqrt(|x|) feature augmentation
        """
        self._net = NetApl(model, scaled_X, scaled_y)
        self.config = config
        self._use_augment = use_augment
        self._c = config.c
        self._ps = config.ps
        self._l = config.l
        self._r = config.r
        self._freq = config.freq

        # Cached input state
        self._uxy = None
        self._uxyt = None
        self._sxy = None
        self._beta = None
        self._t_in = None
        self._ps_val = None

    def input(self, uxy, uxyt, sxy, freq=None, beta=0.03, t_in=40.0, ps=None, nodim=False):
        """Set input state for force prediction.

        :param uxy: displacement array [ux, uy] in meters
        :param uxyt: velocity array [uxt, uyt] in m/s
        :param sxy: servo-valve opening [sx, sy] (dimensionless ratio)
        :param freq: rotational frequency in Hz (overrides config.freq)
        :param beta: viscosity-temperature coefficient [1/K]
        :param t_in: inlet temperature [°C]
        :param ps: supply pressure [Pa] (overrides config.ps)
        :param nodim: if True, uxy/uxyt are already nondimensional
        """
        if freq is None:
            freq = self._freq
        if ps is None:
            ps = self._ps

        if nodim:
            self._uxy = np.asarray(uxy, dtype=float)
            self._uxyt = np.asarray(uxyt, dtype=float)
        else:
            self._uxy = np.asarray(uxy, dtype=float) / self._c
            omega = freq * 2 * np.pi
            self._uxyt = np.asarray(uxyt, dtype=float) / (self._c * omega)

        self._sxy = np.asarray(sxy, dtype=float)
        self._freq_val = float(freq)
        self._beta = float(beta)
        self._t_in = float(t_in)
        self._ps_val = float(ps)

    def output(self, nodim=False):
        """Predict bearing forces and effective temperature from current input state.

        :param nodim: if True, return nondimensional forces and raw t_eff
        :return: array of shape (1, 3) with [fx, fy, t_eff]
        """
        # Build feature vector: [ex, ey, vx, vy, sx, sy, freq, beta, t_in, ps]
        x = np.concatenate([
            self._uxy,       # ex, ey
            self._uxyt,      # vx, vy
            self._sxy,       # sx, sy
            [self._freq_val, self._beta, self._t_in, self._ps_val],
        ]).reshape(1, -1)

        # Feature augmentation
        if self._use_augment:
            x_add = np.sqrt(np.abs(x))
            x = np.concatenate([x, x_add.reshape(1, -1)], axis=1)

        nodim_result = self._net.predict(x)
        if nodim:
            result = nodim_result
        else:
            # fx, fy need dimensional conversion; t_eff is already in °C
            force = nodim_result[:, :2] * self._ps_val * self._l / 2 * self._r
            t_eff = nodim_result[:, 2:3]
            result = np.concatenate([force, t_eff], axis=1)

        return result

    def predict(self, x):
        """Direct prediction from raw feature array (bypasses input/output)."""
        return self._net.predict(x)


def thermal_albnet(config, use_augment: bool = True):
    """Load a trained thermal bearing force MLP from config paths.

    :param config: configuration object with scaler_X, scaler_y, model path attributes
    :param use_augment: whether the model was trained with feature augmentation
    :return: ThermalALBNet instance
    """
    with open(config.scaler_X, "rb") as f:
        scaler_X_model = pd.read_pickle(f)
    with open(config.scaler_y, "rb") as f:
        scaler_y_model = pd.read_pickle(f)
    model = torch.load(
        config.model, map_location=torch.device("cpu"), weights_only=True
    )
    net = net_from_checkpoint(model)
    net.load_state_dict(model["model_state_dict"])
    return ThermalALBNet(
        net, scaler_X_model, scaler_y_model,
        config=config, use_augment=use_augment,
    )


def albnn(config, use_augment: bool = None):
    """Load a nondimensional thermal ALBSV force surrogate.

    ``config`` may provide ``model``, ``scaler_X`` and ``scaler_y`` paths plus
    optional ``metadata``.  The metadata written by ``run/train_albnn.py`` is
    used to recover input/output column order and augmentation settings.
    """
    import json
    from pathlib import Path

    metadata = {}
    metadata_path = getattr(config, "metadata", None)
    if metadata_path is None:
        candidate = Path(config.model).with_name("metadata.json")
        if candidate.exists():
            metadata_path = candidate
    if metadata_path is not None and Path(metadata_path).exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    metadata_dir = (
        Path(metadata_path).resolve().parent
        if metadata_path is not None
        else Path(config.model).resolve().parent
    )

    def _load_checkpoint(path):
        try:
            return torch.load(path, map_location=torch.device("cpu"), weights_only=True)
        except TypeError:
            return torch.load(path, map_location=torch.device("cpu"))

    def _resolve_artifact(value, default_name=None):
        if value is None:
            if default_name is None:
                return None
            path = metadata_dir / default_name
        else:
            path = Path(value)
            if not path.is_absolute():
                path = metadata_dir / path
        return path

    if metadata.get("model_type") == "albnn_residual_corrector":
        main_model_dir = Path(metadata["main_model_dir"])
        if not main_model_dir.is_absolute():
            main_model_dir = metadata_dir / main_model_dir

        class _ConfigProxy:
            pass

        main_config = _ConfigProxy()
        for name in dir(config):
            if name.startswith("_"):
                continue
            try:
                value = getattr(config, name)
            except Exception:
                continue
            if callable(value):
                continue
            setattr(main_config, name, value)
        main_config.model = str(main_model_dir / "best_albnn.pth")
        main_config.scaler_X = str(main_model_dir / "scaler_X.pkl")
        main_config.scaler_y = str(main_model_dir / "scaler_y.pkl")
        main_metadata_path = main_model_dir / "metadata.json"
        if main_metadata_path.exists():
            main_config.metadata = str(main_metadata_path)

        main_model = albnn(main_config, use_augment=None)
        residual_checkpoint_path = Path(getattr(config, "model", ""))
        if not residual_checkpoint_path.exists():
            residual_checkpoint_path = _resolve_artifact(
                metadata.get("model_file"), "best_residual_expert.pth"
            )
        residual_checkpoint = _load_checkpoint(residual_checkpoint_path)
        residual_net = net_from_checkpoint(residual_checkpoint)
        residual_net.load_state_dict(residual_checkpoint["model_state_dict"])

        residual_scaler_path = _resolve_artifact(
            metadata.get("residual_scaler_y"), getattr(config, "scaler_y", None)
        )
        residual_scaler_y = pd.read_pickle(residual_scaler_path)
        return ALBNNResidualCorrector(
            main_model,
            residual_net,
            residual_scaler_y,
            alpha=float(metadata.get("selected_alpha", 1.0)),
            config=config,
            metadata=metadata,
        )

    with open(config.scaler_X, "rb") as f:
        scaler_X_model = pd.read_pickle(f)
    with open(config.scaler_y, "rb") as f:
        scaler_y_model = pd.read_pickle(f)

    checkpoint = _load_checkpoint(config.model)
    net = net_from_checkpoint(checkpoint)
    net.load_state_dict(checkpoint["model_state_dict"])

    if use_augment is None:
        use_augment = bool(metadata.get("use_augment", True))

    if metadata.get("model_type") == "albnn_force_expert":
        target_transform = metadata.get("target_transform", {})
        return ALBNNForceExpert(
            net,
            scaler_X_model,
            scaler_y_model,
            config=config,
            input_cols=metadata.get("input_cols", ALBNN_BASE_INPUT_COLS),
            output_cols=metadata.get("output_cols", ALBNN_OUTPUT_COLS),
            use_augment=use_augment,
            feature_set=metadata.get("feature_set", "default"),
            expert_bins=metadata.get("expert_bins"),
            expert_output_contract=metadata.get(
                "expert_output_contract", "fx_z,fy_z,router_logit"
            ),
            expert_inference_mode=metadata.get(
                "expert_inference_mode", "adjacent_blend"
            ),
            expert_blend_confidence_threshold=float(
                metadata.get("expert_blend_confidence_threshold", 0.8)
            ),
            target_transform_scale=float(target_transform.get("scale", 2.0)),
        )

    return ALBNN(
        net,
        scaler_X_model,
        scaler_y_model,
        config=config,
        input_cols=metadata.get("input_cols", ALBNN_BASE_INPUT_COLS),
        output_cols=metadata.get("output_cols", ALBNN_OUTPUT_COLS),
        use_augment=use_augment,
        feature_set=metadata.get("feature_set", "default"),
        target_output=metadata.get("target_output", "cartesian"),
    )
