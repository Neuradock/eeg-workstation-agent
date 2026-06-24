"""Relative visual cognitive-load estimation from posterior Alpha features."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .profile import PROFILE
from .quality_tools import PreprocessingQualityBundle
from .signal_compat import welch


VISUAL_CHANNELS = ("O1", "O2", "Oz", "PO3", "PO4")
LEFT_VISUAL_CHANNELS = ("O1", "PO3")
RIGHT_VISUAL_CHANNELS = ("O2", "PO4")
LABEL_ZH = {
    "low": "低负荷",
    "medium": "中负荷",
    "high": "高负荷",
    "excluded": "已排除",
}


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


def _percentile_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return 100.0 * (ranks + 0.5) / len(values)


def _label_ranges(windows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    ranges = []
    current = None
    for window in windows:
        label = str(window["label"])
        trial_number = window.get("trial_number")
        if label == "excluded":
            if current is not None:
                ranges.append(current)
                current = None
            continue
        if (
            current is None
            or current["label"] != label
            or current.get("trial_number") != trial_number
        ):
            if current is not None:
                ranges.append(current)
            current = {
                "label": label,
                "label_zh": LABEL_ZH[label],
                "start_sec": float(window["start_sec"]),
                "end_sec": float(window["end_sec"]),
                "window_count": 1,
            }
            if trial_number is not None:
                current["trial_number"] = int(trial_number)
        else:
            current["end_sec"] = float(window["end_sec"])
            current["window_count"] += 1
    if current is not None:
        ranges.append(current)
    return ranges


def visual_cognitive_load_analysis(
    quality: PreprocessingQualityBundle,
    fs: int = PROFILE.sampling_rate_hz,
    window_sec: float = 4.0,
    step_sec: float = 1.0,
    min_clean_fraction: float = 0.8,
    segments: Optional[List[Dict[str, object]]] = None,
) -> Dict[str, object]:
    """Estimate within-recording visual load from posterior Alpha dynamics.

    The result is a relative temporal stratification for one recording. It is
    not a calibrated cognitive-load measurement or a participant diagnosis.
    """

    if window_sec < 2.0:
        raise ValueError("Offline visual load requires --window-sec >= 2.")
    if step_sec <= 0 or step_sec > window_sec:
        raise ValueError("--step-sec must be greater than 0 and no larger than --window-sec.")
    if not 0.0 < min_clean_fraction <= 1.0:
        raise ValueError("min_clean_fraction must be in (0, 1].")

    filtered = np.asarray(quality.filtered, dtype=float)
    keep_mask = np.asarray(quality.keep_mask, dtype=bool)
    window_samples = int(round(window_sec * fs))
    step_samples = int(round(step_sec * fs))
    if filtered.shape[1] < window_samples:
        raise ValueError(
            f"Offline visual load requires at least {window_sec:.1f} seconds."
        )

    channel_index = {name: index for index, name in enumerate(PROFILE.channels)}
    visual_indices = [channel_index[name] for name in VISUAL_CHANNELS]
    left_indices = [channel_index[name] for name in LEFT_VISUAL_CHANNELS]
    right_indices = [channel_index[name] for name in RIGHT_VISUAL_CHANNELS]
    windows: List[Dict[str, object]] = []

    analysis_segments = segments or [
        {
            "start_sample": 0,
            "stop_sample": filtered.shape[1],
        }
    ]
    for segment in analysis_segments:
        segment_start = int(segment["start_sample"])
        segment_stop = int(segment["stop_sample"])
        if segment_start < 0 or segment_stop > filtered.shape[1]:
            raise ValueError("Visual-load analysis segment is outside the signal.")
        if segment_stop - segment_start < window_samples:
            continue
        starts = range(
            segment_start,
            segment_stop - window_samples + 1,
            step_samples,
        )
        for start in starts:
            stop = start + window_samples
            local_start = start - segment_start
            local_stop = stop - segment_start
            center_sec = (local_start + local_stop) / (2.0 * fs)
            clean_fraction = float(np.mean(keep_mask[start:stop]))
            chunk = filtered[:, start:stop]
            frequencies, psd = welch(
                chunk,
                fs=fs,
                nperseg=window_samples,
                axis=1,
            )
            alpha_by_channel = _band_power(frequencies, psd, 8.0, 13.0)
            posterior_alpha = float(np.mean(alpha_by_channel[visual_indices]))
            left_alpha = float(np.mean(alpha_by_channel[left_indices]))
            right_alpha = float(np.mean(alpha_by_channel[right_indices]))
            asymmetry = (right_alpha - left_alpha) / (
                right_alpha + left_alpha + 1e-12
            )
            posterior_psd = np.mean(psd[visual_indices], axis=0)
            alpha_mask = (frequencies >= 8.0) & (frequencies <= 13.0)
            peak_hz = float(
                frequencies[alpha_mask][np.argmax(posterior_psd[alpha_mask])]
            )
            item = {
                "start_sec": local_start / fs,
                "end_sec": local_stop / fs,
                "center_sec": center_sec,
                "clean_fraction": clean_fraction,
                "valid": clean_fraction >= min_clean_fraction,
                "posterior_alpha_power": posterior_alpha,
                "posterior_log_alpha_power": float(
                    np.log10(posterior_alpha + 1e-12)
                ),
                "alpha_peak_hz": peak_hz,
                "alpha_asymmetry_right_minus_left": float(asymmetry),
                "alpha_asymmetry_magnitude": float(abs(asymmetry)),
            }
            if segment.get("trial_number") is not None:
                trial_number = int(segment["trial_number"])
                trial_position = int(segment["trial_position"])
                duration_sec = (segment_stop - segment_start) / float(fs)
                item.update(
                    {
                        "trial_number": trial_number,
                        "trial_position": trial_position,
                        "plot_x": trial_number
                        + 0.7 * (center_sec / duration_sec - 0.5),
                    }
                )
            else:
                item["plot_x"] = (start + stop) / (2.0 * fs)
            windows.append(item)

    if not windows:
        raise ValueError(
            f"No analysis segment contains a full {window_sec:.1f}-second window."
        )

    valid_indices = [index for index, item in enumerate(windows) if item["valid"]]
    if len(valid_indices) < 3:
        raise ValueError(
            "Offline visual load needs at least three quality-valid windows."
        )

    log_alpha = np.asarray(
        [windows[index]["posterior_log_alpha_power"] for index in valid_indices],
        dtype=float,
    )
    peak_hz = np.asarray(
        [windows[index]["alpha_peak_hz"] for index in valid_indices],
        dtype=float,
    )
    asymmetry_magnitude = np.asarray(
        [windows[index]["alpha_asymmetry_magnitude"] for index in valid_indices],
        dtype=float,
    )
    alpha_z, alpha_median, alpha_scale = _robust_z(log_alpha)
    peak_z, peak_median, peak_scale = _robust_z(peak_hz)
    asymmetry_z, asymmetry_median, asymmetry_scale = _robust_z(
        asymmetry_magnitude
    )

    suppression_feature = np.clip(-alpha_z, -3.0, 3.0)
    peak_shift_feature = np.clip(peak_z, -3.0, 3.0)
    asymmetry_feature = np.clip(asymmetry_z, -3.0, 3.0)
    composite = (
        0.65 * suppression_feature
        + 0.15 * peak_shift_feature
        + 0.20 * asymmetry_feature
    )
    percentiles = _percentile_ranks(composite)
    low_threshold, high_threshold = np.quantile(composite, [1.0 / 3.0, 2.0 / 3.0])
    degenerate = bool(np.ptp(composite) <= 1e-9)

    labels = []
    if degenerate:
        labels = ["medium"] * len(valid_indices)
        percentiles[:] = 50.0
    else:
        for score in composite:
            if score <= low_threshold:
                labels.append("low")
            elif score <= high_threshold:
                labels.append("medium")
            else:
                labels.append("high")

    for window in windows:
        window.update(
            {
                "alpha_suppression_z": None,
                "peak_frequency_shift_z": None,
                "asymmetry_magnitude_z": None,
                "composite_score": None,
                "load_percentile": None,
                "label": "excluded",
                "label_zh": LABEL_ZH["excluded"],
            }
        )
    for position, window_index in enumerate(valid_indices):
        windows[window_index].update(
            {
                "alpha_suppression_z": float(suppression_feature[position]),
                "peak_frequency_shift_z": float(peak_shift_feature[position]),
                "asymmetry_magnitude_z": float(asymmetry_feature[position]),
                "composite_score": float(composite[position]),
                "load_percentile": float(percentiles[position]),
                "label": labels[position],
                "label_zh": LABEL_ZH[labels[position]],
            }
        )

    class_counts = {
        label: sum(item["label"] == label for item in windows)
        for label in ("low", "medium", "high")
    }
    valid_count = len(valid_indices)
    warnings = list(quality.result.get("warnings", []))
    excluded_count = len(windows) - valid_count
    if excluded_count:
        warnings.append(
            f"{excluded_count} windows were excluded because clean retention was "
            f"below {min_clean_fraction:.0%}."
        )
    if valid_count < 12:
        warnings.append(
            "Fewer than 12 valid windows were available; temporal thresholds may be unstable."
        )
    visual_bad_channels = sorted(
        set(quality.result.get("bad_channel_candidates", []))
        & set(VISUAL_CHANNELS)
    )
    if visual_bad_channels:
        warnings.append(
            "Visual-load channels flagged by QC: " + ", ".join(visual_bad_channels)
        )
    if degenerate:
        warnings.append(
            "Composite feature distribution was nearly constant; all valid windows "
            "were labeled medium."
        )

    return {
        "workflow": "visual_cognitive_load",
        "method": "posterior_alpha_relative_tertiles_v1",
        "input_structure": quality.result.get(
            "input_structure", "continuous_recording"
        ),
        "status": "warning" if warnings else "pass",
        "recording": quality.result["recording"],
        "quality": {
            "status": quality.result["status"],
            "retention_rate": quality.result["retention_rate"],
            "bad_channel_candidates": quality.result["bad_channel_candidates"],
            "trial_quality": quality.result.get("trial_quality", []),
            "low_retention_trial_numbers": quality.result.get(
                "low_retention_trial_numbers", []
            ),
            "warnings": quality.result["warnings"],
        },
        "parameters": {
            "sampling_rate_hz": fs,
            "visual_channels": list(VISUAL_CHANNELS),
            "left_channels": list(LEFT_VISUAL_CHANNELS),
            "right_channels": list(RIGHT_VISUAL_CHANNELS),
            "alpha_band_hz": [8.0, 13.0],
            "window_sec": float(window_sec),
            "step_sec": float(step_sec),
            "min_clean_fraction": float(min_clean_fraction),
            "feature_weights": {
                "alpha_suppression": 0.65,
                "peak_frequency_shift": 0.15,
                "asymmetry_magnitude": 0.20,
            },
        },
        "normalization": {
            "posterior_log_alpha_power": {
                "median": alpha_median,
                "robust_scale": alpha_scale,
            },
            "alpha_peak_hz": {
                "median": peak_median,
                "robust_scale": peak_scale,
            },
            "asymmetry_magnitude": {
                "median": asymmetry_median,
                "robust_scale": asymmetry_scale,
            },
        },
        "classification": {
            "method": "within_recording_score_tertiles",
            "low_max_score": float(low_threshold),
            "medium_max_score": float(high_threshold),
            "degenerate_distribution": degenerate,
        },
        "summary": {
            "window_count": len(windows),
            "valid_window_count": valid_count,
            "excluded_window_count": excluded_count,
            "trial_count": quality.result.get("recording", {}).get(
                "trial_count"
            ),
            "low_retention_trial_numbers": quality.result.get(
                "low_retention_trial_numbers", []
            ),
            "class_counts": class_counts,
            "class_fractions": {
                label: class_counts[label] / valid_count
                for label in ("low", "medium", "high")
            },
            "mean_alpha_peak_hz": float(np.mean(peak_hz)),
            "mean_asymmetry_right_minus_left": float(
                np.mean(
                    [
                        windows[index]["alpha_asymmetry_right_minus_left"]
                        for index in valid_indices
                    ]
                )
            ),
            "label_ranges": _label_ranges(windows),
        },
        "windows": windows,
        "warnings": warnings,
        "interpretation_limits": [
            (
                "Labels are relative to this recording, not calibrated across "
                "participants or sessions."
            ),
            (
                "Alpha suppression is the primary feature; peak shift and "
                "asymmetry are auxiliary."
            ),
            (
                "Positive asymmetry means right posterior Alpha power exceeded "
                "left posterior Alpha power."
            ),
            (
                "The estimate is a research heuristic, not a medical, "
                "psychological, or performance diagnosis."
            ),
        ],
    }
