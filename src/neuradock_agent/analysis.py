"""Deterministic scientific core for NeuraDock v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from .models import Recording
from .profile import NEIGHBORS, PROFILE
from .signal_compat import butter, filtfilt, iirnotch, sosfiltfilt, welch


BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}


@dataclass
class QualityBundle:
    result: Dict[str, object]
    filtered: np.ndarray
    clean: np.ndarray
    keep_mask: np.ndarray
    issue_mask: np.ndarray


def _integrate(freqs: np.ndarray, psd: np.ndarray, low: float, high: float) -> np.ndarray:
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return np.zeros(psd.shape[:-1], dtype=float)
    if hasattr(np, "trapezoid"):
        return np.trapezoid(psd[..., mask], freqs[mask], axis=-1)
    return np.trapz(psd[..., mask], freqs[mask], axis=-1)


def preprocess(data: np.ndarray, fs: int = PROFILE.sampling_rate_hz) -> np.ndarray:
    """Zero-phase offline 1-45 Hz bandpass with a 50 Hz notch."""

    matrix = np.asarray(data, dtype=float)
    if matrix.shape[1] < fs:
        raise ValueError("At least one second of EEG is required.")
    centered = matrix - np.median(matrix, axis=1, keepdims=True)
    sos = butter(4, [1.0, 45.0], btype="bandpass", fs=fs, output="sos")
    filtered = sosfiltfilt(sos, centered, axis=1)
    b_notch, a_notch = iirnotch(PROFILE.line_frequency_hz, 30.0, fs=fs)
    return filtfilt(b_notch, a_notch, filtered, axis=1)


def welch_psd(data: np.ndarray, fs: int = PROFILE.sampling_rate_hz) -> Tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(data, dtype=float)
    nperseg = min(matrix.shape[1], fs * 2)
    freqs, psd = welch(matrix, fs=fs, nperseg=nperseg, axis=1)
    return freqs, psd


def spectral_summary(data: np.ndarray, fs: int = PROFILE.sampling_rate_hz) -> Dict[str, object]:
    freqs, psd = welch_psd(data, fs)
    total = _integrate(freqs, psd, 1.0, 45.0)
    channel_band_power: Dict[str, Dict[str, float]] = {}
    channel_relative_power: Dict[str, Dict[str, float]] = {}
    for channel_index, channel in enumerate(PROFILE.channels):
        channel_band_power[channel] = {}
        channel_relative_power[channel] = {}
        for band, (low, high) in BANDS.items():
            values = _integrate(freqs, psd, low, high)
            value = float(values[channel_index])
            channel_band_power[channel][band] = value
            channel_relative_power[channel][band] = value / (float(total[channel_index]) + 1e-12)

    posterior_mean = np.mean(psd, axis=0)
    alpha_mask = (freqs >= 8.0) & (freqs <= 13.0)
    alpha_peak_hz = float(freqs[alpha_mask][np.argmax(posterior_mean[alpha_mask])])
    return {
        "frequency_hz": freqs.tolist(),
        "psd_by_channel": {
            channel: psd[index].tolist() for index, channel in enumerate(PROFILE.channels)
        },
        "absolute_band_power": channel_band_power,
        "relative_band_power": channel_relative_power,
        "posterior_alpha_peak_hz": alpha_peak_hz,
    }


def _spatial_quality(data: np.ndarray) -> Dict[str, object]:
    channel_index = {name: index for index, name in enumerate(PROFILE.channels)}
    correlations: Dict[str, float] = {}
    flagged = []
    for channel in PROFILE.channels:
        own = data[channel_index[channel]]
        neighbor_data = np.mean(
            data[[channel_index[name] for name in NEIGHBORS[channel]]], axis=0
        )
        if np.std(own) <= 1e-12 or np.std(neighbor_data) <= 1e-12:
            corr = 0.0
        else:
            corr = float(np.corrcoef(own, neighbor_data)[0, 1])
        correlations[channel] = corr
        if corr < PROFILE.quality.minimum_neighbor_correlation:
            flagged.append(channel)
    return {
        "neighbor_correlation": correlations,
        "low_neighbor_correlation_channels": flagged,
        "interpretation": "Sparse posterior sensor consistency check, not source localization.",
    }


def quality_analysis(recording: Recording) -> QualityBundle:
    fs = recording.fs
    data = recording.data
    segment_length = fs
    n_segments = data.shape[1] // segment_length
    if n_segments < 1:
        raise ValueError("Signal quality workflow requires at least one full second.")

    trimmed = data[:, : n_segments * segment_length]
    centered = trimmed - np.median(trimmed, axis=1, keepdims=True)
    segments = centered.reshape(PROFILE.channel_count, n_segments, segment_length)
    freqs, psd = welch(segments, fs=fs, nperseg=segment_length, axis=2)
    line_power = _integrate(freqs, psd, 49.0, 51.0)
    emg_power = _integrate(freqs, psd, 20.0, 40.0)
    outlier_count = np.sum(
        np.abs(segments) >= PROFILE.quality.outlier_absolute_amplitude, axis=2
    )

    line_bad = line_power > PROFILE.quality.line_noise_power
    emg_bad = emg_power > PROFILE.quality.emg_power
    outlier_bad = outlier_count > PROFILE.quality.outlier_count_per_second
    issue_mask = line_bad | emg_bad | outlier_bad
    channel_bad_ratio = np.mean(issue_mask, axis=1)
    bad_channels = [
        channel
        for channel, ratio in zip(PROFILE.channels, channel_bad_ratio)
        if ratio > PROFILE.quality.bad_channel_segment_ratio
    ]
    good_indices = [
        index for index, channel in enumerate(PROFILE.channels) if channel not in bad_channels
    ]
    rejected_segments = (
        np.any(issue_mask[good_indices], axis=0)
        if good_indices
        else np.zeros(n_segments, dtype=bool)
    )
    keep_trimmed = np.repeat(~rejected_segments, segment_length)
    keep_mask = np.ones(data.shape[1], dtype=bool)
    keep_mask[: len(keep_trimmed)] = keep_trimmed

    filtered = preprocess(data, fs)
    clean = filtered[:, keep_mask]
    retention = float(np.mean(keep_mask))
    spatial = _spatial_quality(filtered)
    malformed_ratio = float(recording.metadata.get("malformed_line_ratio", 0.0))

    warnings = []
    if bad_channels:
        warnings.append("Bad-channel candidates: " + ", ".join(bad_channels))
    if spatial["low_neighbor_correlation_channels"]:
        warnings.append(
            "Low physical-neighbor consistency: "
            + ", ".join(spatial["low_neighbor_correlation_channels"])
        )
    if retention < 0.8:
        warnings.append(f"Only {retention:.1%} of samples passed segment QC.")
    if malformed_ratio > 0.01:
        warnings.append(f"Malformed input row ratio is {malformed_ratio:.1%}.")

    result = {
        "status": "pass" if not warnings else "warning",
        "recording": recording.summary(),
        "segment_sec": 1.0,
        "segments_checked": n_segments,
        "retention_rate": retention,
        "rejected_segment_count": int(np.sum(rejected_segments)),
        "bad_channel_candidates": bad_channels,
        "channel_issue_ratio": {
            channel: float(value) for channel, value in zip(PROFILE.channels, channel_bad_ratio)
        },
        "issue_counts": {
            "line_noise": int(np.sum(line_bad)),
            "emg_or_high_frequency": int(np.sum(emg_bad)),
            "extreme_amplitude": int(np.sum(outlier_bad)),
        },
        "spatial_quality": spatial,
        "warnings": warnings,
        "thresholds": {
            "line_noise_power": PROFILE.quality.line_noise_power,
            "emg_power": PROFILE.quality.emg_power,
            "outlier_count_per_second": PROFILE.quality.outlier_count_per_second,
            "outlier_absolute_amplitude": PROFILE.quality.outlier_absolute_amplitude,
            "outlier_absolute_amplitude_unit": PROFILE.amplitude_unit,
            "bad_channel_segment_ratio": PROFILE.quality.bad_channel_segment_ratio,
        },
    }
    return QualityBundle(result, filtered, clean, keep_mask, issue_mask)
