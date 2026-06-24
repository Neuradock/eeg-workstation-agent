from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np

from .analysis import BANDS, QualityBundle
from .profile import PROFILE
from .quality_tools import PreprocessingQualityBundle
from .signal_compat import spectrogram, welch


def plot_quality(bundle: QualityBundle, path: Path) -> Path:
    result = bundle.result
    issue_rates = np.mean(bundle.issue_mask, axis=1)
    spatial = result["spatial_quality"]["neighbor_correlation"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    colors = [
        "#c0392b" if channel in result["bad_channel_candidates"] else "#2a6f97"
        for channel in PROFILE.channels
    ]
    axes[0].bar(PROFILE.channels, issue_rates * 100.0, color=colors)
    axes[0].axhline(
        PROFILE.quality.bad_channel_segment_ratio * 100.0,
        color="#c0392b",
        linestyle="--",
        label="bad-channel threshold",
    )
    axes[0].set_title("Segments with QC issues")
    axes[0].set_ylabel("Percent")
    axes[0].legend(fontsize=8)

    axes[1].bar(
        PROFILE.channels,
        [spatial[channel] for channel in PROFILE.channels],
        color="#4c956c",
    )
    axes[1].axhline(
        PROFILE.quality.minimum_neighbor_correlation,
        color="#c0392b",
        linestyle="--",
    )
    axes[1].set_title("Physical-neighbor correlation")
    axes[1].set_ylabel("Pearson r")

    counts = result["issue_counts"]
    axes[2].bar(
        ["50 Hz", "EMG/high-f", "Extreme"],
        [
            counts["line_noise"],
            counts["emg_or_high_frequency"],
            counts["extreme_amplitude"],
        ],
        color=["#e76f51", "#f4a261", "#6c757d"],
    )
    axes[2].set_title(
        f"QC summary\nretained {result['retention_rate']:.1%}"
    )
    axes[2].set_ylabel("Channel-segment flags")

    fig.suptitle("NeuraDock Signal Quality", fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_preprocessing_quality(
    bundle: PreprocessingQualityBundle, path: Path
) -> Path:
    """Plot the skill-defined standard, spatial, and context QC overview."""

    result = bundle.result
    line_bad = bundle.metrics[0] > result["thresholds"]["line_noise_power"]
    emg_bad = bundle.metrics[1] > result["thresholds"]["emg_power"]
    outlier_bad = (
        bundle.metrics[2] > result["thresholds"]["outlier_count_per_second"]
    )
    issue_codes = np.zeros_like(bundle.issue_mask, dtype=int)
    issue_codes[line_bad] = 1
    issue_codes[(issue_codes == 0) & emg_bad] = 2
    issue_codes[(issue_codes == 0) & outlier_bad] = 3

    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    axes[0, 0].bar(
        ["Retained", "Rejected"],
        [result["retention_rate"], 1.0 - result["retention_rate"]],
        color=["#2ca25f", "#d95f0e"],
    )
    axes[0, 0].set_ylim(0, 1.0)
    axes[0, 0].set_ylabel("Fraction of samples")
    axes[0, 0].set_title(
        f"Clean retention: {result['retention_rate']:.1%}\n"
        f"{result['raw_shape'][1]} -> {result['clean_shape'][1]} samples"
    )

    cmap = ListedColormap(["#f7f7f7", "#d73027", "#4575b4", "#636363"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    axes[0, 1].imshow(issue_codes, aspect="auto", cmap=cmap, norm=norm)
    axes[0, 1].set_yticks(range(PROFILE.channel_count), PROFILE.channels)
    axes[0, 1].set_xlabel("1-second segment")
    axes[0, 1].set_title("Standard QC issue map")
    axes[0, 1].legend(
        handles=[
            Patch(color="#f7f7f7", label="OK"),
            Patch(color="#d73027", label="50 Hz"),
            Patch(color="#4575b4", label="EMG"),
            Patch(color="#636363", label="Outlier"),
        ],
        loc="upper right",
        fontsize=8,
    )

    neighbor_corr = result["spatial_quality"].get("neighbor_corr", {})
    corr_values = [
        np.nan
        if neighbor_corr.get(channel) is None
        else float(neighbor_corr[channel])
        for channel in PROFILE.channels
    ]
    colors = [
        "#2ca25f"
        if not np.isnan(value)
        and value >= PROFILE.quality.minimum_neighbor_correlation
        else "#fdae61"
        for value in corr_values
    ]
    axes[1, 0].barh(
        PROFILE.channels, np.nan_to_num(corr_values, nan=0.0), color=colors
    )
    axes[1, 0].axvline(
        PROFILE.quality.minimum_neighbor_correlation,
        color="#d7191c",
        linestyle="--",
        label="warning threshold",
    )
    axes[1, 0].set_xlim(-1, 1)
    axes[1, 0].set_xlabel("Corr(channel, neighbor mean)")
    axes[1, 0].set_title("Hardware-native spatial QC")
    axes[1, 0].legend(fontsize=8)

    context = result["acquisition_context"]
    lines = [
        f"Status: {result['status']}",
        f"Bad channels: {', '.join(result['bad_channel_candidates']) or 'none'}",
        f"Rejected segments: {result['rejected_segment_count']}",
        "",
        "Acquisition environment:",
        str(context.get("environment_label", "unknown")),
        "",
        "Body activity / muscle artifact:",
        str(context.get("body_activity_label", "unknown")),
        "",
        "Line-noise ranges:",
        ", ".join(context.get("line_noise", {}).get("time_ranges", [])) or "none",
        "EMG ranges:",
        ", ".join(context.get("emg_activity", {}).get("time_ranges", [])) or "none",
    ]
    axes[1, 1].axis("off")
    axes[1, 1].text(
        0.02,
        0.98,
        "\n".join(lines),
        va="top",
        family="monospace",
        fontsize=10,
    )
    axes[1, 1].set_title("QC interpretation")

    fig.suptitle(
        "NeuraDock Preprocessing QC: Standard Checks + Spatial QC",
        fontweight="bold",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_clean_signal(bundle: PreprocessingQualityBundle, path: Path) -> Path:
    """Plot the retained filtered signal after noisy segments are removed."""

    clean = bundle.clean
    max_points = 20_000
    step = max(1, int(np.ceil(clean.shape[1] / max_points)))
    shown = clean[:, ::step]
    time_axis = np.arange(shown.shape[1]) * step / PROFILE.sampling_rate_hz

    fig, axes = plt.subplots(
        PROFILE.channel_count,
        1,
        figsize=(15, 10),
        sharex=True,
    )
    for index, channel in enumerate(PROFILE.channels):
        axes[index].plot(time_axis, shown[index], color="#1f4e79", linewidth=0.7)
        axes[index].set_ylabel(channel, rotation=0, labelpad=20)
        axes[index].grid(alpha=0.15)
    axes[-1].set_xlabel("Retained signal time (s)")
    fig.suptitle(
        "NeuraDock Clean EEG Signal "
        f"({bundle.result['retention_rate']:.1%} retained)",
        fontweight="bold",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_psd(spectral: Dict[str, object], path: Path, title: str) -> Path:
    freqs = np.asarray(spectral["frequency_hz"], dtype=float)
    psd_by_channel = spectral["psd_by_channel"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))

    for channel in PROFILE.channels:
        psd = np.asarray(psd_by_channel[channel], dtype=float)
        axes[0].plot(freqs, 10.0 * np.log10(psd + 1e-12), label=channel, linewidth=1.1)
    axes[0].axvspan(8, 13, color="#f4a261", alpha=0.2, label="Alpha")
    axes[0].set_xlim(1, 45)
    axes[0].set_xlabel("Frequency (Hz)")
    axes[0].set_ylabel("PSD (dB, device unit squared/Hz)")
    axes[0].set_title("Welch power spectral density")
    axes[0].legend(ncol=2, fontsize=8)

    relative = spectral["relative_band_power"]
    x = np.arange(len(BANDS))
    width = 0.1
    for channel_index, channel in enumerate(PROFILE.channels):
        axes[1].bar(
            x + (channel_index - 3) * width,
            [relative[channel][band] for band in BANDS],
            width=width,
            label=channel,
        )
    axes[1].set_xticks(x, [name.title() for name in BANDS])
    axes[1].set_ylabel("Relative power")
    axes[1].set_title(
        f"Band power | Alpha peak {spectral['posterior_alpha_peak_hz']:.2f} Hz"
    )

    fig.suptitle(title, fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_visual_cognitive_load(result: Dict[str, object], path: Path) -> Path:
    """Plot relative visual cognitive load and its posterior Alpha features."""

    windows = result["windows"]
    trial_mode = result.get("input_structure") == "trial_batch"
    centers = np.asarray(
        [item.get("plot_x", item["center_sec"]) for item in windows],
        dtype=float,
    )
    valid = np.asarray([item["valid"] for item in windows], dtype=bool)

    def values(key: str) -> np.ndarray:
        return np.asarray(
            [
                np.nan if item[key] is None else float(item[key])
                for item in windows
            ],
            dtype=float,
        )

    percentiles = values("load_percentile")
    log_alpha = values("posterior_log_alpha_power")
    peak_hz = values("alpha_peak_hz")
    asymmetry = values("alpha_asymmetry_right_minus_left")
    label_colors = {
        "low": "#2ca25f",
        "medium": "#fdae61",
        "high": "#d73027",
    }
    half_step = (
        0.35
        if trial_mode
        else float(result["parameters"]["step_sec"]) / 2.0
    )

    fig, axes = plt.subplots(4, 1, figsize=(15, 11), sharex=True)
    for item in windows:
        label = item["label"]
        if label in label_colors:
            item_center = float(item.get("plot_x", item["center_sec"]))
            axes[0].axvspan(
                max(0.0, item_center - half_step),
                item_center + half_step,
                color=label_colors[label],
                alpha=0.22,
                linewidth=0,
            )
    axes[0].plot(centers, percentiles, color="#172a3a", linewidth=1.5)
    axes[0].axhline(33.3, color="#2ca25f", linestyle="--", linewidth=0.8)
    axes[0].axhline(66.7, color="#d73027", linestyle="--", linewidth=0.8)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Relative load\npercentile")
    axes[0].set_title(
        "Within-batch visual cognitive-load labels by trial"
        if trial_mode
        else "Within-recording visual cognitive-load labels"
    )
    axes[0].grid(alpha=0.2)

    axes[1].plot(
        centers,
        np.where(valid, log_alpha, np.nan),
        color="#1f78b4",
    )
    axes[1].set_ylabel("log10 Alpha\npower")
    axes[1].set_title("Posterior Alpha power (lower indicates stronger suppression)")
    axes[1].grid(alpha=0.2)

    axes[2].plot(
        centers,
        np.where(valid, peak_hz, np.nan),
        color="#6a3d9a",
    )
    axes[2].axhspan(8.0, 13.0, color="#cab2d6", alpha=0.18)
    axes[2].set_ylabel("Alpha peak\n(Hz)")
    axes[2].set_title("Posterior Alpha peak frequency")
    axes[2].grid(alpha=0.2)

    axes[3].plot(
        centers,
        np.where(valid, asymmetry, np.nan),
        color="#e6550d",
    )
    axes[3].axhline(0.0, color="black", linewidth=0.8)
    axes[3].set_ylabel("(right-left) /\n(right+left)")
    axes[3].set_xlabel(
        "Original trial number" if trial_mode else "Recording time (s)"
    )
    axes[3].set_title("Posterior Alpha spatial asymmetry")
    axes[3].grid(alpha=0.2)

    counts = result["summary"]["class_counts"]
    scope = "Trial Batch" if trial_mode else "Offline"
    fig.suptitle(
        f"NeuraDock {scope} Visual Cognitive Load "
        f"| low {counts['low']} | medium {counts['medium']} | high {counts['high']}",
        fontweight="bold",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_visual_cognitive_load_comparison(
    result: Dict[str, object],
    path: Path,
) -> Path:
    """Plot descriptive Rest/Task contrasts from quality-valid windows."""

    labels = result["condition_labels"]
    condition_results = [
        result["conditions"]["rest"],
        result["conditions"]["task"],
    ]

    def valid_values(condition: Dict[str, object], key: str) -> np.ndarray:
        return np.asarray(
            [
                float(item[key])
                for item in condition["windows"]
                if item["valid"] and item.get(key) is not None
            ],
            dtype=float,
        )

    alpha = [
        valid_values(item, "posterior_log_alpha_power")
        for item in condition_results
    ]
    peak = [valid_values(item, "alpha_peak_hz") for item in condition_results]
    asymmetry = [
        valid_values(item, "alpha_asymmetry_magnitude")
        for item in condition_results
    ]
    retention = [
        float(item["quality"]["retention_rate"])
        for item in condition_results
    ]
    colors = ["#4c78a8", "#e45756"]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for axis, values, title, ylabel in (
        (
            axes[0, 0],
            alpha,
            "Posterior Alpha power",
            "log10 Alpha power",
        ),
        (
            axes[0, 1],
            peak,
            "Posterior Alpha peak frequency",
            "Frequency (Hz)",
        ),
        (
            axes[1, 0],
            asymmetry,
            "Posterior Alpha asymmetry magnitude",
            "|right-left| / (right+left)",
        ),
    ):
        try:
            boxes = axis.boxplot(
                values,
                tick_labels=labels,
                patch_artist=True,
            )
        except TypeError:
            boxes = axis.boxplot(
                values,
                labels=labels,
                patch_artist=True,
            )
        for patch, color in zip(boxes["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", alpha=0.2)

    axes[1, 1].bar(labels, retention, color=colors, alpha=0.75)
    axes[1, 1].axhline(0.8, color="#d73027", linestyle="--", linewidth=1)
    axes[1, 1].set_ylim(0, 1)
    axes[1, 1].set_ylabel("Retained sample fraction")
    axes[1, 1].set_title("Signal-quality retention")
    axes[1, 1].grid(axis="y", alpha=0.2)

    contrast = result["descriptive_contrast"]
    fig.suptitle(
        "NeuraDock Visual Cognitive Load: "
        f"{labels[1]} vs {labels[0]}\n"
        "Task-minus-rest median log Alpha "
        f"{contrast['posterior_log_alpha_power']['task_minus_rest']:+.3f}",
        fontweight="bold",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def _state_color(state: str) -> str:
    return {
        "weak_alpha": "#d73027",
        "baseline_alpha": "#fdae61",
        "strong_alpha": "#2ca25f",
        "stable_alpha": "#4575b4",
    }.get(state, "#cccccc")


def _alpha_window_values(result: Dict[str, object], key: str) -> np.ndarray:
    return np.asarray(
        [
            np.nan if item.get(key) is None else float(item[key])
            for item in result["windows"]
        ],
        dtype=float,
    )


def plot_alpha_time_domain(result: Dict[str, object], path: Path) -> Path:
    """Plot posterior EEG, Alpha-band signal, and Alpha envelope in time."""

    fs = int(result["parameters"]["sampling_rate_hz"])
    posterior = np.asarray(result["time_series"]["posterior_signal"], dtype=float)
    alpha_signal = np.asarray(
        result["time_series"]["posterior_alpha_signal"],
        dtype=float,
    )
    envelope = np.asarray(result["time_series"]["alpha_envelope"], dtype=float)
    max_points = 30_000
    step = max(1, int(np.ceil(len(posterior) / max_points)))
    time_axis = np.arange(0, len(posterior), step) / fs
    windows = result["windows"]
    centers = _alpha_window_values(result, "center_sec")
    suppression = _alpha_window_values(result, "alpha_suppression_from_baseline")

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True)
    for axis in axes:
        for item in windows:
            state = str(item["alpha_state"])
            if state != "excluded":
                axis.axvspan(
                    float(item["start_sec"]),
                    float(item["end_sec"]),
                    color=_state_color(state),
                    alpha=0.08,
                    linewidth=0,
                )
    axes[0].plot(time_axis, posterior[::step], color="#172a3a", linewidth=0.7)
    axes[0].set_ylabel("Posterior EEG")
    axes[0].set_title("Posterior visual-channel mean after preprocessing")
    axes[0].grid(alpha=0.2)

    axes[1].plot(time_axis, alpha_signal[::step], color="#1f78b4", linewidth=0.7)
    axes[1].plot(time_axis, envelope[::step], color="#e6550d", linewidth=1.0, alpha=0.85)
    axes[1].set_ylabel("Alpha band")
    axes[1].set_title("8-13 Hz Alpha-band signal and envelope")
    axes[1].grid(alpha=0.2)

    axes[2].plot(centers, suppression, color="#6a3d9a", linewidth=1.4)
    axes[2].axhline(0.0, color="#333333", linewidth=0.9)
    axes[2].set_ylabel("Suppression\nfrom baseline")
    axes[2].set_xlabel("Recording time (s)")
    axes[2].set_title("Window-level Alpha suppression; positive means weaker Alpha than baseline")
    axes[2].grid(alpha=0.2)

    counts = result["summary"]["state_counts"]
    fig.suptitle(
        "NeuraDock Alpha Dynamics: Time Domain "
        f"| weak {counts['weak_alpha']} | strong {counts['strong_alpha']}",
        fontweight="bold",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_alpha_frequency_domain(result: Dict[str, object], path: Path) -> Path:
    """Plot posterior PSD, Alpha peak distribution, and state-level Alpha power."""

    fs = int(result["parameters"]["sampling_rate_hz"])
    posterior = np.asarray(result["time_series"]["posterior_signal"], dtype=float)
    freqs, psd = welch(
        posterior,
        fs=fs,
        nperseg=min(len(posterior), fs * 4),
    )
    windows = result["windows"]
    valid = [item for item in windows if item["valid"]]
    states = ("weak_alpha", "baseline_alpha", "strong_alpha")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    axes[0].plot(freqs, 10.0 * np.log10(psd + 1e-12), color="#172a3a", linewidth=1.2)
    axes[0].axvspan(8, 13, color="#fdae61", alpha=0.25, label="Alpha")
    axes[0].set_xlim(1, 45)
    axes[0].set_xlabel("Frequency (Hz)")
    axes[0].set_ylabel("PSD (dB)")
    axes[0].set_title("Posterior mean PSD")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.2)

    peak_values = [float(item["alpha_peak_hz"]) for item in valid]
    axes[1].hist(peak_values, bins=np.linspace(8, 13, 11), color="#6a3d9a", alpha=0.75)
    axes[1].set_xlabel("Alpha peak frequency (Hz)")
    axes[1].set_ylabel("Window count")
    axes[1].set_title(
        f"Alpha peak distribution | median {result['summary']['median_alpha_peak_hz']:.2f} Hz"
    )
    axes[1].grid(axis="y", alpha=0.2)

    grouped = [
        [
            float(item["posterior_log_alpha_power"])
            for item in valid
            if item["alpha_state"] == state
        ]
        for state in states
    ]
    try:
        boxes = axes[2].boxplot(
            grouped,
            tick_labels=["Weak", "Baseline", "Strong"],
            patch_artist=True,
        )
    except TypeError:
        boxes = axes[2].boxplot(
            grouped,
            labels=["Weak", "Baseline", "Strong"],
            patch_artist=True,
        )
    for patch, state in zip(boxes["boxes"], states):
        patch.set_facecolor(_state_color(state))
        patch.set_alpha(0.55)
    axes[2].set_ylabel("log10 Alpha power")
    axes[2].set_title("Automatically detected Alpha states")
    axes[2].grid(axis="y", alpha=0.2)

    fig.suptitle("NeuraDock Alpha Dynamics: Frequency Domain", fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_alpha_time_frequency(result: Dict[str, object], path: Path) -> Path:
    """Plot posterior spectrogram with Alpha-power trajectory."""

    fs = int(result["parameters"]["sampling_rate_hz"])
    posterior = np.asarray(result["time_series"]["posterior_signal"], dtype=float)
    freqs, times, spec = spectrogram(
        posterior,
        fs=fs,
        nperseg=min(len(posterior), fs * 4),
        noverlap=min(len(posterior), fs * 3),
        scaling="density",
        mode="psd",
    )
    mask = (freqs >= 1.0) & (freqs <= 35.0)
    centers = _alpha_window_values(result, "center_sec")
    log_alpha = _alpha_window_values(result, "posterior_log_alpha_power")
    suppression = _alpha_window_values(result, "alpha_suppression_from_baseline")

    fig, axes = plt.subplots(2, 1, figsize=(15, 9), sharex=True)
    image = axes[0].pcolormesh(
        times,
        freqs[mask],
        10.0 * np.log10(spec[mask] + 1e-12),
        shading="auto",
        cmap="magma",
    )
    axes[0].axhspan(8, 13, color="#78c679", alpha=0.18, label="Alpha")
    axes[0].set_ylabel("Frequency (Hz)")
    axes[0].set_title("Posterior time-frequency power")
    axes[0].legend(fontsize=8, loc="upper right")
    fig.colorbar(image, ax=axes[0], label="PSD (dB)")

    axes[1].plot(centers, log_alpha, color="#1f78b4", label="log Alpha power")
    axes[1].plot(
        centers,
        suppression,
        color="#d73027",
        label="suppression from baseline",
    )
    for item in result["windows"]:
        state = str(item["alpha_state"])
        if state in {"weak_alpha", "strong_alpha"}:
            axes[1].axvspan(
                float(item["start_sec"]),
                float(item["end_sec"]),
                color=_state_color(state),
                alpha=0.08,
                linewidth=0,
            )
    axes[1].axhline(0.0, color="#333333", linewidth=0.8)
    axes[1].set_xlabel("Recording time (s)")
    axes[1].set_ylabel("Window metric")
    axes[1].set_title("Window-level Alpha dynamics")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.2)

    fig.suptitle("NeuraDock Alpha Dynamics: Time-Frequency Domain", fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path
