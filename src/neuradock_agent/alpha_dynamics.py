"""Posterior Alpha dynamics for focused visual cognitive-load workflows."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from .profile import PROFILE
from .quality_tools import PreprocessingQualityBundle
from .signal_compat import butter, hilbert, sosfiltfilt, welch


POSTERIOR_CHANNELS = ("O1", "O2", "Oz", "PO3", "PO4")
LEFT_POSTERIOR_CHANNELS = ("O1", "PO3")
RIGHT_POSTERIOR_CHANNELS = ("O2", "PO4")
ALPHA_BAND_HZ = (8.0, 13.0)


def _band_power(
    frequencies: np.ndarray,
    psd: np.ndarray,
    low: float,
    high: float,
) -> np.ndarray:
    mask = (frequencies >= low) & (frequencies <= high)
    if np.count_nonzero(mask) < 2:
        return np.zeros(psd.shape[:-1], dtype=float)
    if hasattr(np, "trapezoid"):
        return np.trapezoid(psd[..., mask], frequencies[mask], axis=-1)
    return np.trapz(psd[..., mask], frequencies[mask], axis=-1)


def _robust_z(values: np.ndarray) -> Tuple[np.ndarray, float, float]:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = 1.4826 * mad
    if scale <= 1e-12:
        scale = float(np.std(values))
    if scale <= 1e-12:
        return np.zeros_like(values, dtype=float), median, 0.0
    return (values - median) / scale, median, scale


def _state_ranges(windows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    ranges: List[Dict[str, object]] = []
    current = None
    for window in windows:
        state = str(window["alpha_state"])
        if state == "excluded":
            if current is not None:
                ranges.append(current)
                current = None
            continue
        if current is None or current["alpha_state"] != state:
            if current is not None:
                ranges.append(current)
            current = {
                "alpha_state": state,
                "start_sec": float(window["start_sec"]),
                "end_sec": float(window["end_sec"]),
                "window_count": 1,
            }
        else:
            current["end_sec"] = float(window["end_sec"])
            current["window_count"] += 1
    if current is not None:
        ranges.append(current)
    return ranges


def _posterior_indices() -> Tuple[List[int], List[int], List[int]]:
    channel_index = {name: index for index, name in enumerate(PROFILE.channels)}
    posterior = [channel_index[name] for name in POSTERIOR_CHANNELS]
    left = [channel_index[name] for name in LEFT_POSTERIOR_CHANNELS]
    right = [channel_index[name] for name in RIGHT_POSTERIOR_CHANNELS]
    return posterior, left, right


def alpha_dynamics_analysis(
    quality: PreprocessingQualityBundle,
    fs: int = PROFILE.sampling_rate_hz,
    window_sec: float = 4.0,
    step_sec: float = 1.0,
    min_clean_fraction: float = 0.8,
) -> Dict[str, object]:
    """Find strong and weak posterior Alpha periods after quality gating."""

    if window_sec < 2.0:
        raise ValueError("Alpha dynamics requires --window-sec >= 2.")
    if step_sec <= 0 or step_sec > window_sec:
        raise ValueError("--step-sec must be greater than 0 and no larger than --window-sec.")
    if not 0.0 < min_clean_fraction <= 1.0:
        raise ValueError("min_clean_fraction must be in (0, 1].")

    filtered = np.asarray(quality.filtered, dtype=float)
    keep_mask = np.asarray(quality.keep_mask, dtype=bool)
    window_samples = int(round(window_sec * fs))
    step_samples = int(round(step_sec * fs))
    if filtered.shape[1] < window_samples:
        raise ValueError(f"Alpha dynamics requires at least {window_sec:.1f} seconds.")

    posterior_indices, left_indices, right_indices = _posterior_indices()
    posterior_signal = np.mean(filtered[posterior_indices], axis=0)
    sos = butter(4, ALPHA_BAND_HZ, btype="bandpass", fs=fs, output="sos")
    posterior_alpha_signal = sosfiltfilt(sos, posterior_signal)
    alpha_envelope = np.abs(hilbert(posterior_alpha_signal))

    windows: List[Dict[str, object]] = []
    for start in range(0, filtered.shape[1] - window_samples + 1, step_samples):
        stop = start + window_samples
        chunk = filtered[:, start:stop]
        frequencies, psd = welch(
            chunk,
            fs=fs,
            nperseg=window_samples,
            axis=1,
        )
        alpha_by_channel = _band_power(frequencies, psd, *ALPHA_BAND_HZ)
        posterior_alpha = float(np.mean(alpha_by_channel[posterior_indices]))
        left_alpha = float(np.mean(alpha_by_channel[left_indices]))
        right_alpha = float(np.mean(alpha_by_channel[right_indices]))
        posterior_psd = np.mean(psd[posterior_indices], axis=0)
        alpha_mask = (
            (frequencies >= ALPHA_BAND_HZ[0])
            & (frequencies <= ALPHA_BAND_HZ[1])
        )
        alpha_peak_hz = float(
            frequencies[alpha_mask][np.argmax(posterior_psd[alpha_mask])]
        )
        asymmetry = (right_alpha - left_alpha) / (right_alpha + left_alpha + 1e-12)
        envelope_slice = alpha_envelope[start:stop]
        windows.append(
            {
                "start_sec": start / fs,
                "end_sec": stop / fs,
                "center_sec": (start + stop) / (2.0 * fs),
                "clean_fraction": float(np.mean(keep_mask[start:stop])),
                "valid": bool(np.mean(keep_mask[start:stop]) >= min_clean_fraction),
                "posterior_alpha_power": posterior_alpha,
                "posterior_log_alpha_power": float(np.log10(posterior_alpha + 1e-12)),
                "alpha_peak_hz": alpha_peak_hz,
                "left_alpha_power": left_alpha,
                "right_alpha_power": right_alpha,
                "alpha_asymmetry_right_minus_left": float(asymmetry),
                "alpha_envelope_mean": float(np.mean(envelope_slice)),
                "alpha_envelope_p95": float(np.percentile(envelope_slice, 95)),
            }
        )

    valid_indices = [index for index, item in enumerate(windows) if item["valid"]]
    if len(valid_indices) < 3:
        raise ValueError("Alpha dynamics needs at least three quality-valid windows.")

    log_alpha = np.asarray(
        [windows[index]["posterior_log_alpha_power"] for index in valid_indices],
        dtype=float,
    )
    alpha_z, median_log_alpha, alpha_scale = _robust_z(log_alpha)
    low_threshold, high_threshold = np.quantile(log_alpha, [1.0 / 3.0, 2.0 / 3.0])
    degenerate = bool(np.ptp(log_alpha) <= 1e-9)

    for window in windows:
        window.update(
            {
                "alpha_power_z": None,
                "alpha_suppression_from_baseline": None,
                "alpha_state": "excluded",
            }
        )
    for position, window_index in enumerate(valid_indices):
        value = log_alpha[position]
        if degenerate:
            state = "stable_alpha"
        elif value <= low_threshold:
            state = "weak_alpha"
        elif value >= high_threshold:
            state = "strong_alpha"
        else:
            state = "baseline_alpha"
        windows[window_index].update(
            {
                "alpha_power_z": float(alpha_z[position]),
                "alpha_suppression_from_baseline": float(median_log_alpha - value),
                "alpha_state": state,
            }
        )

    valid_windows = [windows[index] for index in valid_indices]
    strongest = max(valid_windows, key=lambda item: float(item["posterior_log_alpha_power"]))
    weakest = min(valid_windows, key=lambda item: float(item["posterior_log_alpha_power"]))
    state_counts = {
        state: sum(window["alpha_state"] == state for window in windows)
        for state in ("weak_alpha", "baseline_alpha", "strong_alpha", "stable_alpha")
    }
    warnings = list(quality.result.get("warnings", []))
    excluded_count = len(windows) - len(valid_indices)
    if excluded_count:
        warnings.append(
            f"{excluded_count} Alpha windows were excluded because clean retention "
            f"was below {min_clean_fraction:.0%}."
        )
    visual_bad_channels = sorted(
        set(quality.result.get("bad_channel_candidates", []))
        & set(POSTERIOR_CHANNELS)
    )
    if visual_bad_channels:
        warnings.append("Posterior Alpha channels flagged by QC: " + ", ".join(visual_bad_channels))
    if degenerate:
        warnings.append("Posterior Alpha power was nearly constant across valid windows.")

    return {
        "workflow": "alpha_dynamics",
        "method": "posterior_alpha_dynamics_v1",
        "status": "warning" if warnings else "pass",
        "recording": quality.result["recording"],
        "quality": {
            "status": quality.result["status"],
            "retention_rate": quality.result["retention_rate"],
            "bad_channel_candidates": quality.result["bad_channel_candidates"],
            "warnings": quality.result["warnings"],
        },
        "parameters": {
            "sampling_rate_hz": fs,
            "posterior_channels": list(POSTERIOR_CHANNELS),
            "left_channels": list(LEFT_POSTERIOR_CHANNELS),
            "right_channels": list(RIGHT_POSTERIOR_CHANNELS),
            "alpha_band_hz": list(ALPHA_BAND_HZ),
            "window_sec": float(window_sec),
            "step_sec": float(step_sec),
            "min_clean_fraction": float(min_clean_fraction),
        },
        "normalization": {
            "posterior_log_alpha_power": {
                "median": median_log_alpha,
                "robust_scale": alpha_scale,
            },
            "weak_alpha_max_log_power": float(low_threshold),
            "strong_alpha_min_log_power": float(high_threshold),
            "degenerate_distribution": degenerate,
        },
        "summary": {
            "window_count": len(windows),
            "valid_window_count": len(valid_indices),
            "excluded_window_count": excluded_count,
            "state_counts": state_counts,
            "strongest_alpha_window": {
                "start_sec": strongest["start_sec"],
                "end_sec": strongest["end_sec"],
                "posterior_log_alpha_power": strongest["posterior_log_alpha_power"],
                "alpha_peak_hz": strongest["alpha_peak_hz"],
            },
            "weakest_alpha_window": {
                "start_sec": weakest["start_sec"],
                "end_sec": weakest["end_sec"],
                "posterior_log_alpha_power": weakest["posterior_log_alpha_power"],
                "alpha_peak_hz": weakest["alpha_peak_hz"],
            },
            "max_alpha_suppression_from_baseline": float(
                max(
                    float(window["alpha_suppression_from_baseline"])
                    for window in valid_windows
                )
            ),
            "median_alpha_peak_hz": float(
                np.median([float(window["alpha_peak_hz"]) for window in valid_windows])
            ),
            "median_alpha_asymmetry_right_minus_left": float(
                np.median(
                    [
                        float(window["alpha_asymmetry_right_minus_left"])
                        for window in valid_windows
                    ]
                )
            ),
            "alpha_state_ranges": _state_ranges(windows),
        },
        "windows": windows,
        "time_series": {
            "posterior_signal": posterior_signal.tolist(),
            "posterior_alpha_signal": posterior_alpha_signal.tolist(),
            "alpha_envelope": alpha_envelope.tolist(),
        },
        "warnings": warnings,
        "interpretation_limits": [
            "Strong and weak Alpha states are relative to this recording.",
            "Weak Alpha can be consistent with Alpha suppression, but it is not by itself proof of cognitive load.",
            "Interpretation depends on task protocol, visual condition, and signal quality.",
        ],
    }
