"""Transparent synthetic demo that exercises the real NeuraDock parser."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np

from .io import write_neuradock_bluetooth_txt
from .profile import PROFILE


PathLike = Union[str, Path]


def _visual_load_demo_signal(duration_sec: float, seed: int) -> np.ndarray:
    fs = PROFILE.sampling_rate_hz
    n_samples = int(round(duration_sec * fs))
    time = np.arange(n_samples) / fs
    rng = np.random.default_rng(seed)
    matrix = np.zeros((PROFILE.channel_count, n_samples), dtype=float)
    phase = np.minimum((3.0 * time / duration_sec).astype(int), 2)
    alpha_amplitude = np.choose(phase, [8.0, 5.5, 3.2])
    alpha_frequency = np.choose(phase, [9.5, 10.2, 11.0])
    accumulated_phase = 2.0 * np.pi * np.cumsum(alpha_frequency) / fs
    common_alpha = np.sin(accumulated_phase)
    common_slow = 2.0 * np.sin(2.0 * np.pi * 2.0 * time)
    envelope_noise = rng.normal(0.0, 1.0, n_samples)
    kernel = np.ones(max(fs * 2, 1), dtype=float)
    kernel /= np.sum(kernel)
    envelope_noise = np.convolve(envelope_noise, kernel, mode="same")
    envelope_noise /= np.std(envelope_noise) + 1e-12
    alpha_envelope = np.clip(1.0 + 0.22 * envelope_noise, 0.55, 1.45)
    base_scale = np.asarray([1.0, 0.96, 1.08, 0.88, 0.9, 0.62, 0.65])
    for index in range(PROFILE.channel_count):
        neural_noise = signal_colored_noise(rng, n_samples)
        line = 0.35 * np.sin(2.0 * np.pi * 50.0 * time + index * 0.2)
        channel_scale = np.full(n_samples, base_scale[index], dtype=float)
        if PROFILE.channels[index] in {"O1", "PO3"}:
            channel_scale[phase == 2] *= 0.68
        elif PROFILE.channels[index] in {"O2", "PO4"}:
            channel_scale[phase == 2] *= 1.12
        matrix[index] = (
            alpha_amplitude * channel_scale * alpha_envelope * common_alpha
            + common_slow
            + 4.0 * neural_noise
            + line
        )
    return matrix


def signal_colored_noise(rng: np.random.Generator, n_samples: int) -> np.ndarray:
    white = rng.normal(0.0, 1.0, n_samples)
    spectrum = np.fft.rfft(white)
    frequencies = np.fft.rfftfreq(n_samples)
    scale = np.ones_like(frequencies)
    scale[1:] = 1.0 / np.sqrt(frequencies[1:])
    colored = np.fft.irfft(spectrum * scale, n=n_samples)
    return colored / (np.std(colored) + 1e-12)


def generate_visual_load_demo_file(
    output_dir: PathLike,
    duration_sec: float = 36.0,
    file_name: str = "synthetic_visual_load_neuradock.txt",
    seed: int = 31,
) -> Path:
    """Generate a synthetic low-to-high visual-load demonstration recording."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    if duration_sec < 12.0:
        raise ValueError("Visual-load demo requires at least 12 seconds.")
    data = _visual_load_demo_signal(duration_sec, seed=seed)
    path = write_neuradock_bluetooth_txt(
        target / file_name,
        data,
        marker="synthetic_visual_load",
    )
    (target / "README.txt").write_text(
        "This file is a deterministic synthetic visual-load software demo.\n"
        "Its three phases progressively reduce posterior Alpha amplitude, increase "
        "Alpha frequency, and add right/left asymmetry.\n"
        "It is not human EEG and must not be used for hardware or scientific validation.\n",
        encoding="utf-8",
    )
    return path
