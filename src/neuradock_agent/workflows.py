"""Versioned, deterministic workflows exposed to users and the Agent router."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np

from .alpha_dynamics import alpha_dynamics_analysis
from .analysis import quality_analysis, spectral_summary
from .artifacts import (
    create_run_dir,
    write_input_manifest,
    write_json,
    write_workflow_manifest,
)
from .cognitive_load import visual_cognitive_load_analysis
from .models import Recording, RunArtifacts, TrialBatch
from .plots import (
    plot_alpha_frequency_domain,
    plot_alpha_time_domain,
    plot_alpha_time_frequency,
    plot_clean_signal,
    plot_preprocessing_quality,
    plot_psd,
    plot_quality,
    plot_visual_cognitive_load,
    plot_visual_cognitive_load_comparison,
)
from .profile import PROFILE
from .quality_tools import (
    PreprocessingQualityBundle,
    run_preprocessing_quality,
    run_trial_batch_preprocessing,
)
from .reports import (
    write_alpha_dynamics_report,
    write_psd_report,
    write_quality_report,
    write_visual_cognitive_load_report,
    write_visual_cognitive_load_comparison_report,
)


PathLike = Union[str, Path]
EEGInput = Union[Recording, TrialBatch]


def _write_clean_signal(
    run_dir: Path,
    recording: Recording,
    bundle: PreprocessingQualityBundle,
) -> Path:
    original_indices = np.flatnonzero(bundle.keep_mask)
    original_time_sec = original_indices / float(recording.fs)
    timestamps = (
        np.asarray(recording.timestamps)[bundle.keep_mask]
        if recording.timestamps is not None
        else original_time_sec
    )
    markers = (
        np.asarray(recording.markers, dtype=str)[bundle.keep_mask]
        if recording.markers is not None
        else np.full(bundle.clean.shape[1], "", dtype=str)
    )

    npz_path = run_dir / "clean_eeg_data.npz"
    np.savez_compressed(
        npz_path,
        data=bundle.clean,
        channels=np.asarray(recording.channels, dtype=str),
        sampling_rate_hz=np.asarray(recording.fs),
        original_sample_indices=original_indices,
        original_time_seconds=original_time_sec,
        timestamps=timestamps,
        markers=markers,
        keep_mask=bundle.keep_mask,
    )
    return npz_path


def _write_clean_trial_batch(
    run_dir: Path,
    batch: TrialBatch,
    bundle: PreprocessingQualityBundle,
) -> Path:
    trial_count = batch.n_trials
    samples = batch.samples_per_trial
    filtered = bundle.filtered.reshape(
        PROFILE.channel_count,
        trial_count,
        samples,
    ).transpose(1, 0, 2)
    keep_masks = bundle.keep_mask.reshape(trial_count, samples)
    clean_with_nan = np.where(keep_masks[:, None, :], filtered, np.nan)
    npz_path = run_dir / "clean_eeg_trials.npz"
    np.savez_compressed(
        npz_path,
        data=clean_with_nan,
        filtered_data=filtered,
        keep_masks=keep_masks,
        trial_numbers=np.asarray(batch.trial_numbers, dtype=int),
        channels=np.asarray(batch.channels, dtype=str),
        sampling_rate_hz=np.asarray(batch.fs),
        source=np.asarray(str(batch.source)),
    )
    return npz_path


def _prepare_visual_payload(
    recording: EEGInput,
    window_sec: float,
    step_sec: float,
) -> Dict[str, object]:
    if isinstance(recording, TrialBatch):
        quality, segments = run_trial_batch_preprocessing(recording)
        return visual_cognitive_load_analysis(
            quality,
            fs=recording.fs,
            window_sec=window_sec,
            step_sec=step_sec,
            segments=segments,
        )
    quality = run_preprocessing_quality(recording)
    return visual_cognitive_load_analysis(
        quality,
        fs=recording.fs,
        window_sec=window_sec,
        step_sec=step_sec,
    )


def _write_psd_reproducer(run_dir: Path, input_path: Path) -> Path:
    text = f"""from pathlib import Path

from neuradock_agent.io import read_neuradock_txt
from neuradock_agent.workflows import run_psd_bandpower

FILE = Path({str(input_path)!r})
OUTPUT = Path(__file__).resolve().parent / "reproduced_runs"

run = run_psd_bandpower(read_neuradock_txt(FILE), output_root=OUTPUT)
print(run.report_path)
"""
    path = run_dir / "reproduce.py"
    path.write_text(text, encoding="utf-8")
    return path


def run_signal_quality(
    recording: EEGInput,
    output_root: PathLike = "runs",
    run_name: Optional[str] = None,
) -> RunArtifacts:
    run_dir = create_run_dir(output_root, "signal_quality", run_name)
    if isinstance(recording, TrialBatch):
        bundle, _ = run_trial_batch_preprocessing(recording)
        clean_npz = _write_clean_trial_batch(run_dir, recording, bundle)
    else:
        bundle = run_preprocessing_quality(recording)
        clean_npz = _write_clean_signal(run_dir, recording, bundle)
    quality_figure = plot_preprocessing_quality(
        bundle, run_dir / "figures" / "signal_quality.png"
    )
    clean_figure = plot_clean_signal(
        bundle, run_dir / "figures" / "clean_signal.png"
    )
    bundle.result["artifacts"] = {
        "clean_npz": clean_npz.name,
        "quality_figure": str(quality_figure.relative_to(run_dir)).replace("\\", "/"),
        "clean_figure": str(clean_figure.relative_to(run_dir)).replace("\\", "/"),
    }
    results_path = write_json(run_dir / "results.json", bundle.result)
    report_path = write_quality_report(run_dir / "report.md", bundle.result)
    return RunArtifacts(
        run_dir,
        results_path,
        report_path,
        (quality_figure, clean_figure),
        (clean_npz,),
    )


def run_visual_cognitive_load(
    recording: EEGInput,
    output_root: PathLike = "runs",
    run_name: Optional[str] = None,
    window_sec: float = 4.0,
    step_sec: float = 1.0,
) -> RunArtifacts:
    run_dir = create_run_dir(output_root, "visual_cognitive_load", run_name)
    payload = _prepare_visual_payload(
        recording,
        window_sec=window_sec,
        step_sec=step_sec,
    )
    figure = plot_visual_cognitive_load(
        payload,
        run_dir / "figures" / "visual_cognitive_load.png",
    )
    payload["artifacts"] = {
        "figure": str(figure.relative_to(run_dir)).replace("\\", "/"),
    }
    results_path = write_json(run_dir / "results.json", payload)
    report_path = write_visual_cognitive_load_report(
        run_dir / "report.md",
        payload,
    )
    return RunArtifacts(run_dir, results_path, report_path, (figure,))


def run_alpha_dynamics(
    recording: Recording,
    output_root: PathLike = "runs",
    run_name: Optional[str] = None,
    window_sec: float = 4.0,
    step_sec: float = 1.0,
) -> RunArtifacts:
    if not isinstance(recording, Recording):
        raise ValueError("Alpha dynamics currently expects one continuous TXT recording.")
    run_dir = create_run_dir(output_root, "alpha_dynamics", run_name)
    write_input_manifest(run_dir, [recording])
    write_workflow_manifest(
        run_dir,
        "alpha_dynamics",
        {
            "alpha_band_hz": [8.0, 13.0],
            "window_sec": float(window_sec),
            "step_sec": float(step_sec),
            "min_clean_fraction": 0.8,
        },
    )
    quality = run_preprocessing_quality(recording)
    payload = alpha_dynamics_analysis(
        quality,
        fs=recording.fs,
        window_sec=window_sec,
        step_sec=step_sec,
    )
    time_figure = plot_alpha_time_domain(
        payload,
        run_dir / "figures" / "alpha_time_domain.png",
    )
    frequency_figure = plot_alpha_frequency_domain(
        payload,
        run_dir / "figures" / "alpha_frequency_domain.png",
    )
    time_frequency_figure = plot_alpha_time_frequency(
        payload,
        run_dir / "figures" / "alpha_time_frequency.png",
    )
    payload["artifacts"] = {
        "time_domain_figure": str(time_figure.relative_to(run_dir)).replace(
            "\\", "/"
        ),
        "frequency_domain_figure": str(
            frequency_figure.relative_to(run_dir)
        ).replace("\\", "/"),
        "time_frequency_figure": str(
            time_frequency_figure.relative_to(run_dir)
        ).replace("\\", "/"),
    }
    results_path = write_json(run_dir / "results.json", payload)
    report_path = write_alpha_dynamics_report(run_dir / "report.md", payload)
    return RunArtifacts(
        run_dir,
        results_path,
        report_path,
        (time_figure, frequency_figure, time_frequency_figure),
    )


def _valid_window_values(
    payload: Dict[str, object],
    key: str,
) -> np.ndarray:
    return np.asarray(
        [
            float(item[key])
            for item in payload["windows"]
            if item["valid"] and item.get(key) is not None
        ],
        dtype=float,
    )


def run_visual_cognitive_load_comparison(
    rest_recording: EEGInput,
    task_recording: EEGInput,
    output_root: PathLike = "runs",
    run_name: Optional[str] = None,
    window_sec: float = 4.0,
    step_sec: float = 1.0,
    condition_labels: Tuple[str, str] = ("Rest", "Task"),
) -> RunArtifacts:
    if len(condition_labels) != 2 or not all(
        str(value).strip() for value in condition_labels
    ):
        raise ValueError("Exactly two non-empty condition labels are required.")
    labels = tuple(str(value).strip() for value in condition_labels)
    run_dir = create_run_dir(
        output_root,
        "visual_cognitive_load_comparison",
        run_name,
    )
    rest = _prepare_visual_payload(rest_recording, window_sec, step_sec)
    task = _prepare_visual_payload(task_recording, window_sec, step_sec)

    rest_alpha = _valid_window_values(rest, "posterior_log_alpha_power")
    task_alpha = _valid_window_values(task, "posterior_log_alpha_power")
    rest_peak = _valid_window_values(rest, "alpha_peak_hz")
    task_peak = _valid_window_values(task, "alpha_peak_hz")
    rest_asymmetry = _valid_window_values(rest, "alpha_asymmetry_magnitude")
    task_asymmetry = _valid_window_values(task, "alpha_asymmetry_magnitude")
    alpha_difference = float(np.median(task_alpha) - np.median(rest_alpha))
    power_ratio = float(10.0 ** alpha_difference)
    if alpha_difference < 0:
        interpretation = (
            f"{labels[1]} showed lower median posterior Alpha power than "
            f"{labels[0]}. This is consistent with stronger Alpha suppression "
            "during the comparison condition, but it is not by itself proof of "
            "higher cognitive load."
        )
    elif alpha_difference > 0:
        interpretation = (
            f"{labels[1]} showed higher median posterior Alpha power than "
            f"{labels[0]}. The expected Alpha-suppression pattern was not observed "
            "in this descriptive contrast."
        )
    else:
        interpretation = (
            "The two conditions had the same median posterior Alpha power at the "
            "reported precision."
        )
    warnings = []
    for label, condition in zip(labels, (rest, task)):
        if condition["warnings"]:
            warnings.append(
                f"{label} produced {len(condition['warnings'])} workflow warning(s); "
                "review the condition result before interpreting the contrast."
            )

    payload = {
        "workflow": "visual_cognitive_load_comparison",
        "method": "rest_task_posterior_alpha_descriptive_contrast_v1",
        "status": "warning" if warnings else "pass",
        "condition_labels": list(labels),
        "conditions": {
            "rest": rest,
            "task": task,
        },
        "descriptive_contrast": {
            "posterior_log_alpha_power": {
                "rest_median": float(np.median(rest_alpha)),
                "task_median": float(np.median(task_alpha)),
                "task_minus_rest": alpha_difference,
                "task_to_rest_power_ratio": power_ratio,
            },
            "alpha_peak_hz": {
                "rest_median_hz": float(np.median(rest_peak)),
                "task_median_hz": float(np.median(task_peak)),
                "task_minus_rest_hz": float(
                    np.median(task_peak) - np.median(rest_peak)
                ),
            },
            "alpha_asymmetry_magnitude": {
                "rest_median": float(np.median(rest_asymmetry)),
                "task_median": float(np.median(task_asymmetry)),
                "task_minus_rest": float(
                    np.median(task_asymmetry) - np.median(rest_asymmetry)
                ),
            },
        },
        "descriptive_interpretation": interpretation,
        "warnings": warnings,
        "interpretation_limits": [
            "This is a descriptive within-participant condition contrast.",
            (
                "Low, medium, and high labels remain relative within each input "
                "and are not the primary cross-condition comparison."
            ),
            "No causal, clinical, attention, or performance conclusion is established.",
        ],
    }
    comparison_figure = plot_visual_cognitive_load_comparison(
        payload,
        run_dir / "figures" / "visual_cognitive_load_comparison.png",
    )
    rest_figure = plot_visual_cognitive_load(
        rest,
        run_dir / "figures" / "rest_visual_cognitive_load.png",
    )
    task_figure = plot_visual_cognitive_load(
        task,
        run_dir / "figures" / "task_visual_cognitive_load.png",
    )
    payload["artifacts"] = {
        "comparison_figure": str(
            comparison_figure.relative_to(run_dir)
        ).replace("\\", "/"),
        "rest_figure": str(rest_figure.relative_to(run_dir)).replace("\\", "/"),
        "task_figure": str(task_figure.relative_to(run_dir)).replace("\\", "/"),
    }
    results_path = write_json(run_dir / "results.json", payload)
    report_path = write_visual_cognitive_load_comparison_report(
        run_dir / "report.md",
        payload,
    )
    return RunArtifacts(
        run_dir,
        results_path,
        report_path,
        (comparison_figure, rest_figure, task_figure),
    )


def run_psd_bandpower(
    recording: EEGInput,
    output_root: PathLike = "runs",
    run_name: Optional[str] = None,
) -> RunArtifacts:
    if isinstance(recording, TrialBatch):
        raise ValueError(
            "PSD workflow does not yet aggregate trial-batch NPY input. "
            "Use quality or visual cognition comparison for trial data."
        )
    run_dir = create_run_dir(output_root, "psd_bandpower", run_name)
    write_input_manifest(run_dir, [recording])
    write_workflow_manifest(
        run_dir,
        "psd_bandpower",
        {"bandpass_hz": [1.0, 45.0], "notch_hz": 50.0, "welch_sec": 2.0},
    )
    quality = quality_analysis(recording)
    analysis_data = (
        quality.clean
        if quality.clean.shape[1] >= recording.fs * 2
        else quality.filtered
    )
    spectral = spectral_summary(analysis_data, recording.fs)
    payload = {
        "workflow": "psd_bandpower",
        "quality": quality.result,
        "spectral": spectral,
    }
    quality_figure = plot_quality(quality, run_dir / "figures" / "signal_quality.png")
    psd_figure = plot_psd(
        spectral,
        run_dir / "figures" / "psd_bandpower.png",
        "NeuraDock PSD and Band Power",
    )
    results_path = write_json(run_dir / "results.json", payload)
    report_path = write_psd_report(run_dir / "report.md", quality.result, spectral)
    _write_psd_reproducer(run_dir, recording.source)
    return RunArtifacts(
        run_dir, results_path, report_path, (quality_figure, psd_figure)
    )


def summarize_run(run: RunArtifacts) -> str:
    payload = json.loads(run.results_path.read_text(encoding="utf-8"))
    workflow = payload.get("workflow", "signal_quality")
    if workflow == "device_doctor":
        return (
            "device_doctor: captured "
            f"{payload['stream']['samples_captured']} samples, "
            f"status={payload['status']}"
        )
    if workflow == "visual_cognitive_load":
        counts = payload["summary"]["class_counts"]
        return (
            "visual_cognitive_load: "
            f"low={counts['low']}, medium={counts['medium']}, high={counts['high']}"
        )
    if workflow == "alpha_dynamics":
        counts = payload["summary"]["state_counts"]
        suppression = payload["summary"]["max_alpha_suppression_from_baseline"]
        return (
            "alpha_dynamics: "
            f"weak={counts['weak_alpha']}, strong={counts['strong_alpha']}, "
            f"max suppression={suppression:+.3f}"
        )
    if workflow == "visual_cognitive_load_comparison":
        labels = payload["condition_labels"]
        difference = payload["descriptive_contrast"][
            "posterior_log_alpha_power"
        ]["task_minus_rest"]
        return (
            "visual_cognitive_load_comparison: "
            f"{labels[1]}-{labels[0]} median log Alpha={difference:+.3f}"
        )
    if workflow == "psd_bandpower":
        return (
            "psd_bandpower: posterior Alpha peak "
            f"{payload['spectral']['posterior_alpha_peak_hz']:.2f} Hz"
        )
    return (
        "signal_quality: retained "
        f"{payload['retention_rate']:.1%}, status={payload['status']}"
    )
