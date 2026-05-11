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
ALBNN_LOG_INPUT_COLS = {"lambda_value", "lr", "cq0", "cq1", "cq2"}
ALBNN_FEATURE_SETS = {"default", "aug_v2", "sqrt28"}


def albnn_augment_frame(frame: pd.DataFrame, feature_set: str = "default") -> pd.DataFrame:
    """Append deterministic nonlinear features with stable column names."""
    if feature_set not in ALBNN_FEATURE_SETS:
        raise ValueError(f"Unknown ALBNN feature_set: {feature_set}")

    augmented = frame.copy()
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
    def __init__(self, nbs_neurons, activation: str = "gelu", sine_omega0: float = 30.0):
        super(Net, self).__init__()
        if activation not in {"gelu", "relu", "silu", "sin"}:
            raise ValueError(f"Unsupported activation: {activation}")
        if sine_omega0 <= 0.0:
            raise ValueError("sine_omega0 must be > 0")
        self.activation = activation
        self.sine_omega0 = float(sine_omega0)
        self.layers = nn.ModuleList()
        self.dropouts = nn.ModuleList()

        for i in range(len(nbs_neurons) - 1):
            self.layers.append(nn.Linear(nbs_neurons[i], nbs_neurons[i + 1]))
        if self.activation == "sin":
            self._init_sine_weights()

    def forward(self, x):
        for i, layer in enumerate(self.layers[:-1]):
            # x = F.leaky_relu(layer(x), negative_slope=0.2)
            # x = F.tanh(layer(x))
            # x = self.dropouts[i](x)
            x = self._activate(layer(x))

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
    ):
        self.model = model
        self.scaler_X = scaler_X
        self.scaler_y = scaler_y
        self.config = config
        self.input_cols = list(input_cols or ALBNN_BASE_INPUT_COLS)
        self.output_cols = list(output_cols or ALBNN_OUTPUT_COLS)
        self.use_augment = bool(use_augment)
        self.feature_set = feature_set or "default"
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
        else:
            row["cos"] = 1.0
            row["sin"] = 0.0
        row["r"] = radius
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
        return self.scaler_y.inverse_transform(y_frame)

    def predict(self, x, nodim: bool = True):
        force = self.predict_nondim(x)
        if nodim:
            return force
        return force * self.force_scale

    def output(self, nodim: bool = True):
        if self._x is None:
            raise ValueError("Call input(...) before output(...)")
        return self.predict(self._x, nodim=nodim)


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
    ):
        self.feature_range = tuple(float(value) for value in feature_range)
        self.log_column = str(log_column)
        self.epsilon = float(epsilon)
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
        return scaled

    def fit_transform(self, x):
        return self.fit(x).transform(x)

    def inverse_transform(self, x_scaled):
        lo, hi = self.feature_range
        span = hi - lo
        values = (np.asarray(x_scaled, dtype=float) - lo) / span
        safe_range = np.where(self.data_range_ > 0.0, self.data_range_, 1.0)
        values = values * safe_range + self.data_min_
        log_idx = list(self.feature_names_in_).index(self.log_column)
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

    with open(config.scaler_X, "rb") as f:
        scaler_X_model = pd.read_pickle(f)
    with open(config.scaler_y, "rb") as f:
        scaler_y_model = pd.read_pickle(f)

    checkpoint = torch.load(
        config.model, map_location=torch.device("cpu"), weights_only=True
    )
    net = net_from_checkpoint(checkpoint)
    net.load_state_dict(checkpoint["model_state_dict"])

    metadata = {}
    metadata_path = getattr(config, "metadata", None)
    if metadata_path is None:
        candidate = Path(config.model).with_name("metadata.json")
        if candidate.exists():
            metadata_path = candidate
    if metadata_path is not None and Path(metadata_path).exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

    if use_augment is None:
        use_augment = bool(metadata.get("use_augment", True))

    return ALBNN(
        net,
        scaler_X_model,
        scaler_y_model,
        config=config,
        input_cols=metadata.get("input_cols", ALBNN_BASE_INPUT_COLS),
        output_cols=metadata.get("output_cols", ALBNN_OUTPUT_COLS),
        use_augment=use_augment,
        feature_set=metadata.get("feature_set", "default"),
    )
