from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from .profile import PROFILE


BOUNDARY = (
    "This report is for EEG engineering and research development. "
    "It is not a medical, psychological, or clinical diagnosis."
)


def _warnings(items: Iterable[str]) -> List[str]:
    values = list(items)
    return values if values else ["No workflow warnings."]


def write_quality_report(path: Path, result: Dict[str, object]) -> Path:
    context = result.get("acquisition_context", {})
    spatial = result.get("spatial_quality", {})
    artifacts = result.get("artifacts", {})
    recording = result["recording"]
    if recording.get("trial_count") is not None:
        duration_sec = (
            float(recording["trial_count"])
            * float(recording["trial_duration_sec"])
        )
        structure_lines = [
            f"- Retained trials: {recording['trial_count']}",
            f"- Samples per trial: {recording['samples_per_trial']}",
            "- User-excluded trials: "
            + (
                ", ".join(
                    str(value)
                    for value in recording["metadata"].get(
                        "excluded_trial_numbers", []
                    )
                )
                or "none"
            ),
        ]
    else:
        duration_sec = float(recording["duration_sec"])
        structure_lines = []
    lines = [
        "# NeuraDock Signal Quality Report",
        "",
        f"- Status: **{result['status']}**",
        f"- Analyzed duration: {duration_sec:.1f} s",
        f"- Raw shape: `{result.get('raw_shape', result['recording']['shape'])}`",
        f"- Clean shape: `{result.get('clean_shape', 'not available')}`",
        *structure_lines,
        f"- Samples retained: {result['retention_rate']:.1%}",
        f"- Rejected 1-second segments: {result['rejected_segment_count']}",
        f"- Bad-channel candidates: {', '.join(result['bad_channel_candidates']) or 'none'}",
        "- Absolute outlier threshold: "
        f"{result['thresholds']['outlier_absolute_amplitude']:.0f} "
        f"{result['thresholds']['outlier_absolute_amplitude_unit']}",
        "",
        "## Acquisition Context",
        "",
        f"- Electrical environment: `{context.get('environment_label', 'not available')}`",
        f"- Activity/muscle artifact: `{context.get('body_activity_label', 'not available')}`",
        "",
        "## Spatial Quality",
        "",
        f"- Status: `{spatial.get('status', 'not available')}`",
        "- Low neighbor-correlation channels: "
        + (", ".join(spatial.get("low_neighbor_corr_channels", [])) or "none"),
        "- High neighbor-deviation channels: "
        + (", ".join(spatial.get("high_spatial_deviation_channels", [])) or "none"),
        "",
        "## Output Files",
        "",
        f"- Clean signal NPZ: `{artifacts.get('clean_npz', 'not available')}`",
        f"- QC overview: `{artifacts.get('quality_figure', 'not available')}`",
        f"- Clean waveform: `{artifacts.get('clean_figure', 'not available')}`",
        "",
        "## Warnings",
        "",
        *[f"- {item}" for item in _warnings(result["warnings"])],
        "",
        "## Interpretation",
        "",
        "Quality flags identify recording segments or sensors that may need attention. "
        "They do not establish that a sensor or participant is clinically abnormal.",
        "",
        "When a posterior electrode is repeatedly flagged, check local electrode contact, "
        "hair displacement, headset pressure, cable movement, and nearby power sources.",
        "",
        "## Hardware Profile",
        "",
        f"- Channels: {', '.join(PROFILE.channels)}",
        f"- Sampling rate: {PROFILE.sampling_rate_hz} Hz",
        f"- Amplitude unit: {PROFILE.amplitude_unit}",
        "",
        f"> {BOUNDARY}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_psd_report(
    path: Path,
    quality: Dict[str, object],
    spectral: Dict[str, object],
) -> Path:
    alpha = {
        channel: spectral["relative_band_power"][channel]["alpha"]
        for channel in PROFILE.channels
    }
    strongest = max(alpha, key=alpha.get)
    lines = [
        "# NeuraDock PSD and Band-Power Report",
        "",
        f"- Recording: `{quality['recording']['source']}`",
        f"- Quality status: **{quality['status']}**",
        f"- Retained samples: {quality['retention_rate']:.1%}",
        f"- Posterior Alpha peak: {spectral['posterior_alpha_peak_hz']:.2f} Hz",
        f"- Highest relative Alpha channel: {strongest} ({alpha[strongest]:.1%})",
        "",
        "## Notes",
        "",
        "- PSD uses deterministic Welch estimation after the fixed offline preprocessing pipeline.",
        "- Band power describes sensor-level spectral content and is not source localization.",
        f"- Input EEG amplitudes are represented in `{PROFILE.amplitude_unit}`.",
        "",
        f"> {BOUNDARY}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_visual_cognitive_load_report(
    path: Path,
    result: Dict[str, object],
) -> Path:
    summary = result["summary"]
    counts = summary["class_counts"]
    fractions = summary["class_fractions"]
    classification = result["classification"]
    trial_lines = []
    if result.get("input_structure") == "trial_batch":
        trial_lines = [
            f"- Retained trials: {result['recording']['trial_count']}",
            "- User-excluded trials: "
            + (
                ", ".join(
                    str(value)
                    for value in result["recording"]["metadata"].get(
                        "excluded_trial_numbers", []
                    )
                )
                or "none"
            ),
            "- Trials below 80% clean retention: "
            + (
                ", ".join(
                    str(value)
                    for value in summary.get(
                        "low_retention_trial_numbers", []
                    )
                )
                or "none"
            ),
        ]
    lines = [
        "# NeuraDock Offline Visual Cognitive Load Report",
        "",
        f"- Status: **{result['status']}**",
        f"- Recording: `{result['recording']['source']}`",
        f"- Quality retention: {result['quality']['retention_rate']:.1%}",
        f"- Valid windows: {summary['valid_window_count']} "
        f"(excluded {summary['excluded_window_count']})",
        f"- Low load: {counts['low']} windows ({fractions['low']:.1%})",
        f"- Medium load: {counts['medium']} windows ({fractions['medium']:.1%})",
        f"- High load: {counts['high']} windows ({fractions['high']:.1%})",
        f"- Mean posterior Alpha peak: {summary['mean_alpha_peak_hz']:.2f} Hz",
        *trial_lines,
        "",
        "## Method",
        "",
        "- Primary feature: posterior Alpha suppression across "
        + ", ".join(result["parameters"]["visual_channels"])
        + ".",
        "- Auxiliary features: Alpha peak-frequency shift and left/right Alpha asymmetry.",
        "- Composite weights: 0.65 suppression, 0.15 peak shift, 0.20 asymmetry magnitude.",
        "- Features are robustly standardized within this recording.",
        "- Low, medium, and high labels use the recording's composite-score tertiles.",
        f"- Low/medium threshold: {classification['low_max_score']:.3f}.",
        f"- Medium/high threshold: {classification['medium_max_score']:.3f}.",
        "",
        "## Warnings",
        "",
        *[f"- {item}" for item in _warnings(result["warnings"])],
        "",
        "## Interpretation Limits",
        "",
        *[f"- {item}" for item in result["interpretation_limits"]],
        "",
        f"> {BOUNDARY}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_alpha_dynamics_report(
    path: Path,
    result: Dict[str, object],
) -> Path:
    summary = result["summary"]
    counts = summary["state_counts"]
    strongest = summary["strongest_alpha_window"]
    weakest = summary["weakest_alpha_window"]
    lines = [
        "# NeuraDock Alpha Dynamics Report",
        "",
        f"- Status: **{result['status']}**",
        f"- Recording: `{result['recording']['source']}`",
        f"- Quality retention: {result['quality']['retention_rate']:.1%}",
        f"- Valid Alpha windows: {summary['valid_window_count']} "
        f"(excluded {summary['excluded_window_count']})",
        f"- Weak Alpha windows: {counts.get('weak_alpha', 0)}",
        f"- Baseline Alpha windows: {counts.get('baseline_alpha', 0)}",
        f"- Strong Alpha windows: {counts.get('strong_alpha', 0)}",
        f"- Max Alpha suppression from baseline: "
        f"{summary['max_alpha_suppression_from_baseline']:+.4f}",
        f"- Median Alpha peak: {summary['median_alpha_peak_hz']:.2f} Hz",
        f"- Median right-minus-left Alpha asymmetry: "
        f"{summary['median_alpha_asymmetry_right_minus_left']:+.4f}",
        "",
        "## Strongest and Weakest Alpha",
        "",
        "- Strongest Alpha window: "
        f"{strongest['start_sec']:.1f}-{strongest['end_sec']:.1f}s, "
        f"log Alpha {strongest['posterior_log_alpha_power']:.4f}, "
        f"peak {strongest['alpha_peak_hz']:.2f} Hz.",
        "- Weakest Alpha window: "
        f"{weakest['start_sec']:.1f}-{weakest['end_sec']:.1f}s, "
        f"log Alpha {weakest['posterior_log_alpha_power']:.4f}, "
        f"peak {weakest['alpha_peak_hz']:.2f} Hz.",
        "",
        "## Method",
        "",
        "- The workflow uses the standard NeuraDock preprocessing and quality gate first.",
        "- Posterior channels are "
        + ", ".join(result["parameters"]["posterior_channels"])
        + ".",
        "- Weak, baseline, and strong Alpha states are detected from "
        "within-recording posterior log Alpha power tertiles.",
        "- Alpha suppression from baseline is positive when posterior Alpha is "
        "weaker than this recording's median Alpha power.",
        "- Frequency-domain output reports Alpha peak frequency and posterior "
        "left/right Alpha asymmetry.",
        "",
        "## Alpha State Ranges",
        "",
        *[
            f"- {item['alpha_state']}: {item['start_sec']:.1f}-"
            f"{item['end_sec']:.1f}s ({item['window_count']} windows)"
            for item in summary["alpha_state_ranges"][:20]
        ],
        "",
        "## Warnings",
        "",
        *[f"- {item}" for item in _warnings(result["warnings"])],
        "",
        "## Interpretation Limits",
        "",
        *[f"- {item}" for item in result["interpretation_limits"]],
        "",
        f"> {BOUNDARY}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_visual_cognitive_load_comparison_report(
    path: Path,
    result: Dict[str, object],
) -> Path:
    labels = result["condition_labels"]
    rest = result["conditions"]["rest"]
    task = result["conditions"]["task"]
    contrast = result["descriptive_contrast"]
    alpha = contrast["posterior_log_alpha_power"]
    peak = contrast["alpha_peak_hz"]
    asymmetry = contrast["alpha_asymmetry_magnitude"]
    lines = [
        "# NeuraDock Rest/Task Visual Cognitive Load Comparison",
        "",
        f"- Reference condition: **{labels[0]}**",
        f"- Comparison condition: **{labels[1]}**",
        f"- {labels[0]} source: `{rest['recording']['source']}`",
        f"- {labels[1]} source: `{task['recording']['source']}`",
        f"- {labels[0]} valid windows: {rest['summary']['valid_window_count']}",
        f"- {labels[1]} valid windows: {task['summary']['valid_window_count']}",
        f"- {labels[0]} quality retention: {rest['quality']['retention_rate']:.1%}",
        f"- {labels[1]} quality retention: {task['quality']['retention_rate']:.1%}",
        "",
        "## Descriptive Contrast",
        "",
        "- Median posterior log Alpha, "
        f"{labels[1]} minus {labels[0]}: {alpha['task_minus_rest']:+.4f}.",
        "- Median posterior Alpha power ratio, "
        f"{labels[1]} / {labels[0]}: {alpha['task_to_rest_power_ratio']:.3f}.",
        "- Median Alpha peak-frequency shift, "
        f"{labels[1]} minus {labels[0]}: {peak['task_minus_rest_hz']:+.3f} Hz.",
        "- Median Alpha asymmetry-magnitude change, "
        f"{labels[1]} minus {labels[0]}: "
        f"{asymmetry['task_minus_rest']:+.4f}.",
        "",
        "## Interpretation",
        "",
        str(result["descriptive_interpretation"]),
        "",
        "## Important Limits",
        "",
        "- This is a descriptive within-participant condition contrast.",
        "- Low/medium/high labels remain relative within each recording or trial batch.",
        "- Because each condition uses its own tertiles, label counts must not be used "
        "as the primary Rest/Task comparison.",
        "- No causal, clinical, attention, or performance conclusion is established.",
        "",
        "## Warnings",
        "",
        *[f"- {item}" for item in _warnings(result["warnings"])],
        "",
        f"> {BOUNDARY}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
