"""NeuraDock preprocessing quality pipeline adapted from the v17 EEG tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .models import Recording, TrialBatch
from .profile import NEIGHBORS, PROFILE
from .signal_compat import butter, filtfilt, welch


SYMMETRIC_PAIRS = (("O1", "O2"), ("PO3", "PO4"), ("CP5", "CP6"))
REGIONS = {
    "occipital": ("O1", "O2", "Oz"),
    "parieto_occipital": ("PO3", "PO4"),
    "centro_parietal": ("CP5", "CP6"),
    "posterior": ("O1", "O2", "Oz", "PO3", "PO4"),
}


@dataclass
class PreprocessingQualityBundle:
    result: Dict[str, object]
    filtered: np.ndarray
    clean: np.ndarray
    keep_mask: np.ndarray
    issue_mask: np.ndarray
    metrics: Tuple[np.ndarray, np.ndarray, np.ndarray]


def eeg_quality_check(
    eeg_data: np.ndarray,
    fs: int = PROFILE.sampling_rate_hz,
) -> Tuple[Tuple[np.ndarray, np.ndarray, np.ndarray], np.ndarray]:
    """Filter EEG and compute 50 Hz, EMG-band, and outlier metrics per second."""

    matrix = np.asarray(eeg_data, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("eeg_quality_check expects shape (channels, samples).")
    if matrix.shape[1] < fs:
        raise ValueError("Signal quality workflow requires at least one full second.")

    nyquist = 0.5 * fs
    b_filter, a_filter = butter(
        4, [1.0 / nyquist, 50.0 / nyquist], btype="band"
    )
    filtered = filtfilt(b_filter, a_filter, matrix, axis=1)

    segment_length = fs
    n_segments = matrix.shape[1] // segment_length
    metrics = [
        np.zeros((matrix.shape[0], n_segments), dtype=float) for _ in range(3)
    ]
    for channel_index in range(matrix.shape[0]):
        for segment_index in range(n_segments):
            start = segment_index * segment_length
            segment = filtered[channel_index, start : start + segment_length]
            frequencies, psd = welch(
                segment, fs=fs, nperseg=min(len(segment), fs * 2)
            )
            metrics[0][channel_index, segment_index] = np.sum(
                psd[(frequencies >= 49.0) & (frequencies <= 51.0)]
            )
            metrics[1][channel_index, segment_index] = np.sum(
                psd[(frequencies >= 20.0) & (frequencies <= 40.0)]
            )
            metrics[2][channel_index, segment_index] = np.sum(
                (segment <= -PROFILE.quality.outlier_absolute_amplitude)
                | (segment >= PROFILE.quality.outlier_absolute_amplitude)
            )
    return (metrics[0], metrics[1], metrics[2]), filtered


def clean_eeg_data(
    eeg_data: np.ndarray,
    metrics: Tuple[np.ndarray, np.ndarray, np.ndarray],
    thresholds: Tuple[float, float, float],
    segment_length: int = PROFILE.sampling_rate_hz,
    bad_channel_ratio: float = PROFILE.quality.bad_channel_segment_ratio,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, object]]:
    """Reject noisy segments while excluding globally bad channels from voting."""

    matrix = np.asarray(eeg_data, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("clean_eeg_data expects shape (channels, samples).")

    n_segments = metrics[0].shape[1]
    line_bad = metrics[0] > thresholds[0]
    emg_bad = metrics[1] > thresholds[1]
    outlier_bad = metrics[2] > thresholds[2]
    issue_mask = line_bad | emg_bad | outlier_bad
    bad_ratios = np.mean(issue_mask, axis=1) if n_segments else np.zeros(matrix.shape[0])
    bad_indices = np.where(bad_ratios > bad_channel_ratio)[0]
    good_indices = np.where(bad_ratios <= bad_channel_ratio)[0]

    if len(good_indices):
        rejected_segments = np.any(issue_mask[good_indices], axis=0)
    else:
        rejected_segments = np.zeros(n_segments, dtype=bool)

    rejected_points = np.repeat(rejected_segments, segment_length)
    if len(rejected_points) < matrix.shape[1]:
        rejected_points = np.concatenate(
            [
                rejected_points,
                np.zeros(matrix.shape[1] - len(rejected_points), dtype=bool),
            ]
        )
    else:
        rejected_points = rejected_points[: matrix.shape[1]]

    keep_mask = ~rejected_points
    clean = matrix[:, keep_mask]
    channel_names = list(PROFILE.channels)
    info = {
        "bad_channels": bad_indices.tolist(),
        "bad_channel_names": [channel_names[index] for index in bad_indices],
        "channel_bad_ratios": {
            channel_names[index]: float(bad_ratios[index])
            for index in range(matrix.shape[0])
        },
        "retention_rate": float(clean.shape[1] / max(matrix.shape[1], 1)),
        "rejected_segments_count": int(np.sum(rejected_segments)),
        "rejected_segment_indices": np.where(rejected_segments)[0].tolist(),
        "thresholds": {
            "power_50hz": thresholds[0],
            "emg_power": thresholds[1],
            "outlier_count": thresholds[2],
        },
    }
    return clean, keep_mask, info


def _safe_corr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if a.size < 3 or b.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    value = float(np.corrcoef(a, b)[0, 1])
    return None if np.isnan(value) else value


def _robust_z(values: np.ndarray) -> np.ndarray:
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    scale = 1.4826 * mad if mad > 0 else np.std(values)
    return np.zeros_like(values, dtype=float) if scale == 0 else (values - median) / scale


def spatial_quality_check(
    data: np.ndarray,
    fs: int = PROFILE.sampling_rate_hz,
    segment_sec: float = 1.0,
    min_neighbor_corr: float = PROFILE.quality.minimum_neighbor_correlation,
    max_spatial_z: float = 4.0,
) -> Dict[str, object]:
    """Compute hardware-aware spatial QC for the sparse posterior layout."""

    matrix = np.asarray(data, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != PROFILE.channel_count:
        raise ValueError(
            "Spatial QC expects shape "
            f"({PROFILE.channel_count}, samples), received {matrix.shape}."
        )
    segment_length = max(1, int(fs * segment_sec))
    n_segments = matrix.shape[1] // segment_length
    if n_segments == 0:
        raise ValueError("Spatial QC needs at least one full segment.")

    segments = matrix[:, : n_segments * segment_length].reshape(
        PROFILE.channel_count, n_segments, segment_length
    )
    rms = np.sqrt(np.mean(segments**2, axis=2))
    channel_index = {name: index for index, name in enumerate(PROFILE.channels)}
    neighbor_corr: Dict[str, Optional[float]] = {}
    spatial_z: Dict[str, float] = {}

    for channel in PROFILE.channels:
        index = channel_index[channel]
        neighbor_indices = [channel_index[name] for name in NEIGHBORS[channel]]
        neighbor_values = np.mean(segments[neighbor_indices], axis=0)
        neighbor_corr[channel] = _safe_corr(
            segments[index].reshape(-1), neighbor_values.reshape(-1)
        )
        neighbor_rms = np.mean(rms[neighbor_indices], axis=0)
        spatial_z[channel] = float(
            np.median(np.abs(_robust_z(rms[index] - neighbor_rms)))
        )

    symmetric_pairs = []
    for left, right in SYMMETRIC_PAIRS:
        left_index, right_index = channel_index[left], channel_index[right]
        left_power = float(np.mean(matrix[left_index] ** 2))
        right_power = float(np.mean(matrix[right_index] ** 2))
        symmetric_pairs.append(
            {
                "pair": [left, right],
                "correlation": _safe_corr(matrix[left_index], matrix[right_index]),
                "power_asymmetry": float(
                    (left_power - right_power) / (left_power + right_power + 1e-12)
                ),
            }
        )

    region_summary = {}
    for region, channels in REGIONS.items():
        indices = [channel_index[name] for name in channels]
        region_summary[region] = {
            "channels": list(channels),
            "rms_mean": float(np.mean(rms[indices])),
            "rms_median": float(np.median(rms[indices])),
        }

    low_corr = [
        name
        for name, value in neighbor_corr.items()
        if value is not None and value < min_neighbor_corr
    ]
    high_deviation = [
        name for name, value in spatial_z.items() if value > max_spatial_z
    ]
    warnings = []
    if low_corr:
        warnings.append("Low neighbor correlation in channels: " + ", ".join(low_corr))
    if high_deviation:
        warnings.append(
            "High neighbor-deviation score in channels: " + ", ".join(high_deviation)
        )
    return {
        "status": "pass" if not warnings else "warning",
        "n_segments": int(n_segments),
        "segment_sec": float(segment_sec),
        "neighbor_corr": neighbor_corr,
        "spatial_z_median_abs": spatial_z,
        "low_neighbor_corr_channels": low_corr,
        "high_spatial_deviation_channels": high_deviation,
        "symmetric_pairs": symmetric_pairs,
        "region_summary": region_summary,
        "warnings": warnings,
        "interpretation": (
            "Sparse posterior hardware-layout QC; warnings are not source localization "
            "or automatic channel rejection."
        ),
    }


def _ranges(mask: np.ndarray, segment_sec: float, limit: int = 6) -> List[str]:
    ranges = []
    start = None
    for index, value in enumerate(mask.astype(bool)):
        if value and start is None:
            start = index
        elif not value and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(mask)))
    return [
        f"{start * segment_sec:.0f}-{end * segment_sec:.0f}s"
        for start, end in ranges[:limit]
    ]


def _top_channels(mask: np.ndarray, limit: int = 3) -> List[str]:
    rates = np.mean(mask, axis=1)
    order = np.argsort(rates)[::-1]
    return [
        f"{PROFILE.channels[index]} ({rates[index]:.0%})"
        for index in order[:limit]
        if rates[index] > 0
    ]


def infer_acquisition_context(
    metrics: Tuple[np.ndarray, np.ndarray, np.ndarray],
    segment_sec: float = 1.0,
) -> Dict[str, object]:
    """Infer electrical environment and movement/muscle artifact heuristics."""

    line_bad = metrics[0] > PROFILE.quality.line_noise_power
    emg_bad = metrics[1] > PROFILE.quality.emg_power
    outlier_bad = metrics[2] > PROFILE.quality.outlier_count_per_second
    if line_bad.size == 0:
        return {
            "status": "no_full_segments",
            "environment_label": "unknown",
            "body_activity_label": "unknown",
        }

    line_fraction = np.mean(line_bad, axis=0)
    emg_fraction = np.mean(emg_bad, axis=0)
    line_rate = float(np.mean(line_bad))
    line_any_rate = float(np.mean(np.any(line_bad, axis=0)))
    line_peak = float(np.max(line_fraction))
    if line_rate >= 0.20 or line_any_rate >= 0.45:
        environment = "noisy_or_unstable_electrical_environment"
    elif line_rate >= 0.05 or line_any_rate >= 0.15:
        environment = "intermittent_electrical_interference"
    elif line_peak >= 0.50 and line_any_rate >= 0.03:
        environment = "brief_line_noise_bursts"
    else:
        environment = "quiet_or_stable_environment"

    emg_rate = float(np.mean(emg_bad))
    emg_any_rate = float(np.mean(np.any(emg_bad, axis=0)))
    outlier_any_rate = float(np.mean(np.any(outlier_bad, axis=0)))
    activity_score = max(emg_rate, 0.5 * emg_any_rate, 0.25 * outlier_any_rate)
    if activity_score >= 0.18 or emg_any_rate >= 0.35:
        activity = "vigorous_activity_or_strong_muscle_artifact"
    elif activity_score >= 0.04 or emg_any_rate >= 0.10:
        activity = "slight_activity_or_mild_muscle_tension"
    else:
        activity = "still_or_relaxed"

    return {
        "status": "ok",
        "segment_sec": float(segment_sec),
        "environment_label": environment,
        "line_noise": {
            "channel_segment_rate": line_rate,
            "any_segment_rate": line_any_rate,
            "peak_segment_channel_fraction": line_peak,
            "top_channels": _top_channels(line_bad),
            "time_ranges": _ranges(line_fraction > 0, segment_sec),
        },
        "body_activity_label": activity,
        "emg_activity": {
            "channel_segment_rate": emg_rate,
            "any_segment_rate": emg_any_rate,
            "peak_segment_channel_fraction": float(np.max(emg_fraction)),
            "top_channels": _top_channels(emg_bad),
            "time_ranges": _ranges(emg_fraction > 0, segment_sec),
        },
        "movement_or_contact_outliers": {
            "any_segment_rate": outlier_any_rate,
            "top_channels": _top_channels(outlier_bad),
            "time_ranges": _ranges(np.any(outlier_bad, axis=0), segment_sec),
        },
        "interpretation_limit": (
            "Heuristic QC only; these labels are not medical or behavioral diagnoses."
        ),
    }


def run_preprocessing_quality(recording: Recording) -> PreprocessingQualityBundle:
    """Run the full skill-defined NeuraDock preprocessing quality workflow."""

    thresholds = (
        PROFILE.quality.line_noise_power,
        PROFILE.quality.emg_power,
        PROFILE.quality.outlier_count_per_second,
    )
    metrics, filtered = eeg_quality_check(recording.data, recording.fs)
    clean, keep_mask, cleaning = clean_eeg_data(
        filtered,
        metrics,
        thresholds,
        segment_length=recording.fs,
        bad_channel_ratio=PROFILE.quality.bad_channel_segment_ratio,
    )
    issue_mask = (
        (metrics[0] > thresholds[0])
        | (metrics[1] > thresholds[1])
        | (metrics[2] > thresholds[2])
    )
    try:
        spatial = spatial_quality_check(clean, recording.fs, segment_sec=1.0)
    except ValueError as exc:
        spatial = {
            "status": "error",
            "neighbor_corr": {channel: None for channel in PROFILE.channels},
            "low_neighbor_corr_channels": [],
            "high_spatial_deviation_channels": [],
            "warnings": [f"Spatial QC failed: {exc}"],
        }
    context = infer_acquisition_context(metrics, segment_sec=1.0)

    warnings = []
    if cleaning["bad_channel_names"]:
        warnings.append(
            "Bad-channel candidates: " + ", ".join(cleaning["bad_channel_names"])
        )
    warnings.extend(spatial["warnings"])
    if cleaning["retention_rate"] < 0.8:
        warnings.append(
            f"Only {cleaning['retention_rate']:.1%} of samples passed segment QC."
        )
    malformed_ratio = float(recording.metadata.get("malformed_line_ratio", 0.0))
    if malformed_ratio > 0.01:
        warnings.append(f"Malformed input row ratio is {malformed_ratio:.1%}.")
    if context["environment_label"] != "quiet_or_stable_environment":
        warnings.append(
            "Acquisition environment heuristic: "
            + str(context["environment_label"])
            + "."
        )
    if context["body_activity_label"] != "still_or_relaxed":
        warnings.append(
            "Body activity heuristic: " + str(context["body_activity_label"]) + "."
        )

    result = {
        "workflow": "signal_quality",
        "method": "neuradock_preprocess_v17_tools",
        "status": "pass" if not warnings else "warning",
        "recording": recording.summary(),
        "raw_shape": list(recording.data.shape),
        "filtered_shape": list(filtered.shape),
        "clean_shape": list(clean.shape),
        "segment_sec": 1.0,
        "segments_checked": int(metrics[0].shape[1]),
        "retention_rate": cleaning["retention_rate"],
        "rejected_segment_count": cleaning["rejected_segments_count"],
        "rejected_segment_indices": cleaning["rejected_segment_indices"],
        "bad_channel_candidates": cleaning["bad_channel_names"],
        "channel_issue_ratio": cleaning["channel_bad_ratios"],
        "issue_counts": {
            "line_noise": int(np.sum(metrics[0] > thresholds[0])),
            "emg_or_high_frequency": int(np.sum(metrics[1] > thresholds[1])),
            "extreme_amplitude": int(np.sum(metrics[2] > thresholds[2])),
        },
        "spatial_quality": spatial,
        "acquisition_context": context,
        "warnings": warnings,
        "thresholds": {
            "line_noise_power": thresholds[0],
            "emg_power": thresholds[1],
            "outlier_count_per_second": thresholds[2],
            "outlier_absolute_amplitude": PROFILE.quality.outlier_absolute_amplitude,
            "outlier_absolute_amplitude_unit": PROFILE.amplitude_unit,
            "bad_channel_segment_ratio": PROFILE.quality.bad_channel_segment_ratio,
            "minimum_neighbor_correlation": (
                PROFILE.quality.minimum_neighbor_correlation
            ),
        },
    }
    return PreprocessingQualityBundle(
        result=result,
        filtered=filtered,
        clean=clean,
        keep_mask=keep_mask,
        issue_mask=issue_mask,
        metrics=metrics,
    )


def run_trial_batch_preprocessing(
    batch: TrialBatch,
) -> Tuple[PreprocessingQualityBundle, List[Dict[str, object]]]:
    """Preprocess each trial independently, then aggregate without crossing boundaries."""

    trial_bundles = [
        run_preprocessing_quality(recording)
        for recording in batch.recordings()
    ]
    filtered_parts = [bundle.filtered for bundle in trial_bundles]
    keep_parts = [bundle.keep_mask for bundle in trial_bundles]
    filtered = np.concatenate(filtered_parts, axis=1)
    keep_mask = np.concatenate(keep_parts)
    clean = filtered[:, keep_mask]
    issue_mask = np.concatenate(
        [bundle.issue_mask for bundle in trial_bundles],
        axis=1,
    )
    metrics = tuple(
        np.concatenate(
            [bundle.metrics[metric_index] for bundle in trial_bundles],
            axis=1,
        )
        for metric_index in range(3)
    )

    segments: List[Dict[str, object]] = []
    trial_quality = []
    sample_offset = 0
    for position, (trial_number, bundle) in enumerate(
        zip(batch.trial_numbers, trial_bundles),
        start=1,
    ):
        trial_samples = bundle.filtered.shape[1]
        segments.append(
            {
                "start_sample": sample_offset,
                "stop_sample": sample_offset + trial_samples,
                "trial_number": trial_number,
                "trial_position": position,
            }
        )
        trial_quality.append(
            {
                "trial_number": trial_number,
                "status": bundle.result["status"],
                "retention_rate": bundle.result["retention_rate"],
                "rejected_segment_count": bundle.result[
                    "rejected_segment_count"
                ],
                "bad_channel_candidates": bundle.result[
                    "bad_channel_candidates"
                ],
                "warnings": bundle.result["warnings"],
            }
        )
        sample_offset += trial_samples

    thresholds = (
        PROFILE.quality.line_noise_power,
        PROFILE.quality.emg_power,
        PROFILE.quality.outlier_count_per_second,
    )
    channel_issue_ratio = np.mean(issue_mask, axis=1)
    bad_channels = [
        channel
        for channel, ratio in zip(PROFILE.channels, channel_issue_ratio)
        if ratio > PROFILE.quality.bad_channel_segment_ratio
    ]
    try:
        spatial = spatial_quality_check(clean, batch.fs, segment_sec=1.0)
    except ValueError as exc:
        spatial = {
            "status": "error",
            "neighbor_corr": {channel: None for channel in PROFILE.channels},
            "low_neighbor_corr_channels": [],
            "high_spatial_deviation_channels": [],
            "warnings": [f"Spatial QC failed: {exc}"],
        }
    context = infer_acquisition_context(metrics, segment_sec=1.0)
    retention_rate = float(np.mean(keep_mask))
    low_retention_trials = [
        item["trial_number"]
        for item in trial_quality
        if float(item["retention_rate"]) < 0.8
    ]
    warnings = []
    if bad_channels:
        warnings.append("Bad-channel candidates: " + ", ".join(bad_channels))
    warnings.extend(spatial["warnings"])
    if retention_rate < 0.8:
        warnings.append(
            f"Only {retention_rate:.1%} of trial samples passed segment QC."
        )
    if low_retention_trials:
        warnings.append(
            "Trials below 80% clean retention: "
            + ", ".join(str(value) for value in low_retention_trials)
            + "."
        )
    excluded = batch.metadata.get("excluded_trial_numbers", [])
    if excluded:
        warnings.append(
            "Trials excluded by the user before analysis: "
            + ", ".join(str(value) for value in excluded)
            + "."
        )
    if context["environment_label"] != "quiet_or_stable_environment":
        warnings.append(
            "Acquisition environment heuristic: "
            + str(context["environment_label"])
            + "."
        )
    if context["body_activity_label"] != "still_or_relaxed":
        warnings.append(
            "Body activity heuristic: " + str(context["body_activity_label"]) + "."
        )

    result = {
        "workflow": "signal_quality",
        "method": "neuradock_preprocess_v17_tools_trial_preserving",
        "status": "pass" if not warnings else "warning",
        "recording": batch.summary(),
        "input_structure": "trial_batch",
        "raw_shape": [PROFILE.channel_count, int(filtered.shape[1])],
        "trial_shape": list(batch.data.shape),
        "filtered_shape": list(filtered.shape),
        "clean_shape": list(clean.shape),
        "segment_sec": 1.0,
        "segments_checked": int(metrics[0].shape[1]),
        "retention_rate": retention_rate,
        "rejected_segment_count": int(
            sum(
                int(bundle.result["rejected_segment_count"])
                for bundle in trial_bundles
            )
        ),
        "rejected_segment_indices": [],
        "bad_channel_candidates": bad_channels,
        "channel_issue_ratio": {
            channel: float(value)
            for channel, value in zip(PROFILE.channels, channel_issue_ratio)
        },
        "issue_counts": {
            "line_noise": int(np.sum(metrics[0] > thresholds[0])),
            "emg_or_high_frequency": int(np.sum(metrics[1] > thresholds[1])),
            "extreme_amplitude": int(np.sum(metrics[2] > thresholds[2])),
        },
        "spatial_quality": spatial,
        "acquisition_context": context,
        "trial_quality": trial_quality,
        "low_retention_trial_numbers": low_retention_trials,
        "warnings": warnings,
        "thresholds": {
            "line_noise_power": thresholds[0],
            "emg_power": thresholds[1],
            "outlier_count_per_second": thresholds[2],
            "outlier_absolute_amplitude": (
                PROFILE.quality.outlier_absolute_amplitude
            ),
            "outlier_absolute_amplitude_unit": PROFILE.amplitude_unit,
            "bad_channel_segment_ratio": (
                PROFILE.quality.bad_channel_segment_ratio
            ),
            "minimum_neighbor_correlation": (
                PROFILE.quality.minimum_neighbor_correlation
            ),
        },
    }
    return (
        PreprocessingQualityBundle(
            result=result,
            filtered=filtered,
            clean=clean,
            keep_mask=keep_mask,
            issue_mask=issue_mask,
            metrics=metrics,
        ),
        segments,
    )
