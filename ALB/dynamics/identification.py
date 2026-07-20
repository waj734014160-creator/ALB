"""Frequency-domain dynamics and bearing coefficient identification."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import scipy.fft as scipy_fft
from scipy.ndimage import gaussian_filter1d
from tqdm import tqdm


class FFT:
    """Retain the established real-FFT scaling used by ALB workflows."""

    def __init__(self, t: Any = None, y: Any = None) -> None:
        self.t = np.squeeze(np.asarray(t))
        self.y = np.squeeze(np.asarray(y))
        self.dt = t[1] - t[0] if t is not None else None
        self.yf: np.ndarray | None = None
        self.xf: np.ndarray | None = None

    def rfft(
        self,
        t: Any = None,
        y: Any = None,
        plot: bool = False,
        end: float = 1,
        save_path: str | Path | None = None,
        **kwargs: Any,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Calculate the one-sided spectrum without changing legacy scaling."""

        if t is not None:
            self.t = np.squeeze(np.asarray(t))
            self.dt = t[1] - t[0]
        if y is not None:
            self.y = np.squeeze(np.asarray(y))
        if kwargs.get("mean", False):
            self.y = self.y - np.mean(self.y)
        if self.t is None or self.y is None:
            raise ValueError("t and y must be not None")
        self.yf = scipy_fft.rfft(self.y) / self.y.size * 2
        self.xf = scipy_fft.rfftfreq(self.y.size, self.dt)
        self.xf = self.xf[: int(self.xf.size * end)]
        self.yf = self.yf[: int(self.yf.size * end)]
        if plot:
            self.plot(save_path=save_path, **kwargs)
        return self.xf, self.yf

    def plot(self, save_path: str | Path | None = None, **kwargs: Any) -> None:
        """Plot the most recently computed spectrum."""

        if self.xf is None or self.yf is None:
            raise ValueError("Please run rfft first")
        fig, ax = plt.subplots()
        if kwargs.get("annotate", False):
            peak = int(np.argmax(np.abs(self.yf)))
            ax.annotate(
                "max: {:.2f}, freq: {:.2f}".format(
                    np.max(np.abs(self.yf)), self.xf[peak]
                ),
                xy=(self.xf[peak] + 0.2, np.max(np.abs(self.yf)) - 0.1),
                xytext=(self.xf[peak] + 0.3, np.max(np.abs(self.yf)) - 0.1),
            )
        ax.plot(self.xf, np.abs(self.yf))
        ax.set_title("FFT")
        ax.set_xlabel("Freq (Hz)")
        ax.set_ylabel("Amplitude (um)")
        if save_path is not None:
            fig.savefig(save_path)
        plt.show()

    def get(self, freq: float) -> tuple[float, complex]:
        """Return the represented frequency nearest to ``freq`` and its value."""

        if self.xf is None or self.yf is None:
            raise ValueError("Please run rfft first")
        index = int(np.argmin(np.abs(self.xf - freq)))
        return float(self.xf[index]), complex(self.yf[index])


def recognize_z(
    t: np.ndarray,
    freq: float,
    fs: Iterable[np.ndarray],
    **kwargs: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Identify complex amplitudes at one frequency for a signal collection."""

    transform = FFT()
    values = []
    for force in fs:
        transform.rfft(t, force, **kwargs)
        values.append(transform.get(freq))
    result = np.asarray(values)
    return np.asarray(result[:, 0]), np.asarray(result[:, 1])


def recognize_kc(
    t: np.ndarray,
    freq: float,
    uxy0: np.ndarray,
    fxy0: np.ndarray,
    uxy1: np.ndarray,
    fxy1: np.ndarray,
    tr: list[float] | None = None,
    **kwargs: Any,
) -> dict[str, np.ndarray]:
    """Identify bearing stiffness and damping from two whirl directions."""

    del kwargs
    start_ratio, end_ratio = [0, 1] if tr is None else tr
    start = int(start_ratio * len(t))
    end = int(end_ratio * len(t))
    time = t[start:end]
    displacement0 = uxy0[:, start:end]
    displacement1 = uxy1[:, start:end]
    force0 = np.asarray(fxy0)[:, start:end]
    force1 = np.asarray(fxy1)[:, start:end]
    z0 = recognize_z(time, freq, displacement0)
    z1 = recognize_z(time, freq, displacement1)
    displacement = np.asarray([z0[1], z1[1]]).T
    f0 = recognize_z(time, freq, force0)
    f1 = recognize_z(time, freq, force1)
    force = np.asarray([f0[1], f1[1]]).T
    transfer = force.dot(np.linalg.inv(displacement))
    return {
        "h": transfer,
        "k": transfer.real,
        "c": transfer.imag / 2 / np.pi / freq,
    }


def pearson_similarity(signal1: np.ndarray, signal2: np.ndarray) -> float:
    """Return the Pearson correlation between equal-length signals."""

    if len(signal1) != len(signal2):
        raise ValueError("signals must have the same length")
    return float(np.corrcoef(signal1, signal2)[0, 1])


def cal_bode_best(
    data_x: np.ndarray,
    rpm: np.ndarray,
    n_cycles: int = 10,
    step_size: int = 200,
    sampling_rate: float = 10000,
    sigma: float | None = None,
    filter_freq: float | list[float] | None = None,
    filter_bandwidth: float = 5,
    phase_return: bool = False,
) -> tuple[np.ndarray, list[np.ndarray]] | tuple[
    np.ndarray, list[np.ndarray], list[np.ndarray]
]:
    """Extract sorted synchronous Bode amplitudes using the legacy windowing rule."""

    segment_count = int(len(rpm) / step_size)
    amplitudes = []
    phases = []
    rpm_sorted = np.array([], dtype=float)
    for values in [data_x[:, index] for index in range(data_x.shape[1])]:
        amplitude_values = []
        phase_values = []
        rpm_values = []
        start = 0
        for index_rpm in tqdm(range(segment_count)):
            window_size = int(
                sampling_rate
                / rpm[(index_rpm + 1) * step_size - 1]
                * 60
                * n_cycles
            )
            end = start + window_size
            frequency, amplitude, phase = fft_data(
                values[start:end],
                sampling_rate,
                window="hann",
                filter_freq=filter_freq,
                filter_bandwidth=filter_bandwidth,
            )
            target_frequency = rpm[start] / 60
            frequency_index = max(
                int(np.argmin(np.abs(frequency - target_frequency))), 2
            )
            amplitude_index = int(
                np.argmax(amplitude[frequency_index - 1 : frequency_index + 1])
            )
            amplitude_values.append(
                np.max(amplitude[frequency_index - 1 : frequency_index + 1])
            )
            phase_values.append(phase[amplitude_index])
            rpm_values.append(np.mean(rpm[start:end]))
            start += step_size
        order = np.argsort(rpm_values)
        rpm_sorted = np.asarray(rpm_values)[order]
        amplitude_sorted = np.asarray(amplitude_values)[order]
        phase_sorted = np.asarray(phase_values)[order]
        if sigma is not None:
            amplitude_sorted = gaussian_filter1d(amplitude_sorted, sigma=sigma)
            phase_sorted = gaussian_filter1d(phase_sorted, sigma=sigma)
        amplitudes.append(amplitude_sorted)
        phases.append(phase_sorted)
    if phase_return:
        return rpm_sorted, amplitudes, phases
    return rpm_sorted, amplitudes


def fft_data(
    y: np.ndarray,
    sampling_rate: float,
    ratio: list[float] | None = None,
    n_fft: int | None = None,
    window: str | None = None,
    filter_freq: float | list[float] | np.ndarray | None = None,
    filter_bandwidth: float = 5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return one-sided frequency, amplitude, and phase arrays."""

    ratio = [0, 1] if ratio is None else ratio
    start_index = int(y.shape[0] * ratio[0])
    end_index = int(y.shape[0] * ratio[1])
    y_data = y[start_index:end_index]
    count = len(y_data)
    if window == "hann":
        window_values = np.hanning(count)
    elif window == "hamming":
        window_values = np.hamming(count)
    elif window == "blackman":
        window_values = np.blackman(count)
    elif window == "rect" or window is None:
        window_values = np.ones(count)
    else:
        raise ValueError(
            "Unsupported window type. Choose 'hann', 'hamming', 'blackman', "
            "'rect', or None."
        )
    window_mean = np.mean(window_values)
    normalization = 1 / window_mean if window_mean != 0 else 1
    y_windowed = y_data * window_values
    transform_size = count if n_fft is None else n_fft
    transformed = np.fft.fft(y_windowed, transform_size)
    frequency = np.fft.fftfreq(transform_size, d=1 / sampling_rate)
    magnitude = np.abs(transformed) * 2 / count * normalization
    phase = np.angle(transformed)
    if filter_freq is not None:
        targets = filter_freq
        if not isinstance(targets, (list, np.ndarray)):
            targets = [targets]
        for target in targets:
            indices = np.where(
                (frequency >= target - filter_bandwidth / 2)
                & (frequency <= target + filter_bandwidth / 2)
            )[0]
            transformed[indices] = 0
        magnitude = np.abs(transformed) * 2 / count * normalization
        phase = np.angle(transformed)
    return (
        frequency[: transform_size // 2],
        magnitude[: transform_size // 2],
        phase[: transform_size // 2],
    )


__all__ = [
    "FFT",
    "cal_bode_best",
    "fft_data",
    "pearson_similarity",
    "recognize_kc",
    "recognize_z",
]
