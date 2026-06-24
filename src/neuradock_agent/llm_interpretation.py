"""Privacy-bounded LLM interpretation of deterministic workflow results."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from statistics import mean
from typing import Dict, List, Tuple

from .context_pack import ContextPack, load_context_pack
from .llm import chat_with_llm
from .llm_config import LLMConfig
from .models import RunArtifacts


INTERPRETATION_PROMPT_VERSION = "neuradock-result-interpretation-v3"


def _response_language_instruction(user_request: str) -> str:
    has_chinese = any(
        "\u3400" <= character <= "\u4dbf"
        or "\u4e00" <= character <= "\u9fff"
        for character in user_request
    )
    if has_chinese:
        return (
            "The original request is in Chinese. Write the entire interpretation "
            "in Simplified Chinese."
        )
    if any(character.isascii() and character.isalpha() for character in user_request):
        return (
            "The original request is in English. Write the entire interpretation "
            "in English."
        )
    return (
        "Write the entire interpretation in the same language as the original "
        "request."
    )


def _compact_label_ranges(
    ranges: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    fields = ("label", "start_sec", "end_sec", "window_count")
    return [
        {field: item.get(field) for field in fields}
        for item in ranges[:20]
    ]


def _quality_warning_required(payload: Dict[str, object]) -> bool:
    retention = payload.get("retention_rate")
    return bool(
        payload.get("status") != "pass"
        or payload.get("warnings")
        or (retention is not None and float(retention) < 0.8)
    )


def _quality_summary(payload: Dict[str, object]) -> Dict[str, object]:
    return {
        "status": payload.get("status"),
        "quality_warning_required": _quality_warning_required(payload),
        "duration_sec": payload.get("recording", {}).get("duration_sec"),
        "retention_rate": payload.get("retention_rate"),
        "rejected_segment_count": payload.get("rejected_segment_count"),
        "bad_channel_candidates": payload.get("bad_channel_candidates", []),
        "issue_counts": payload.get("issue_counts", {}),
        "spatial_quality": {
            "status": payload.get("spatial_quality", {}).get("status"),
            "low_neighbor_corr_channels": payload.get("spatial_quality", {}).get(
                "low_neighbor_corr_channels", []
            ),
            "high_spatial_deviation_channels": payload.get(
                "spatial_quality", {}
            ).get("high_spatial_deviation_channels", []),
        },
        "acquisition_context": {
            "environment_label": payload.get("acquisition_context", {}).get(
                "environment_label"
            ),
            "body_activity_label": payload.get("acquisition_context", {}).get(
                "body_activity_label"
            ),
        },
        "warnings": payload.get("warnings", []),
    }


def _visual_trend(windows: List[Dict[str, object]]) -> Dict[str, object]:
    valid = [item for item in windows if item.get("valid")]
    if not valid:
        return {}
    third = max(1, len(valid) // 3)
    early = valid[:third]
    late = valid[-third:]

    def average(items: List[Dict[str, object]], key: str) -> float:
        values = [float(item[key]) for item in items if item.get(key) is not None]
        return mean(values) if values else 0.0

    return {
        "early_mean_load_percentile": average(early, "load_percentile"),
        "late_mean_load_percentile": average(late, "load_percentile"),
        "early_mean_log_alpha_power": average(
            early, "posterior_log_alpha_power"
        ),
        "late_mean_log_alpha_power": average(late, "posterior_log_alpha_power"),
        "early_mean_alpha_peak_hz": average(early, "alpha_peak_hz"),
        "late_mean_alpha_peak_hz": average(late, "alpha_peak_hz"),
        "early_mean_asymmetry": average(
            early, "alpha_asymmetry_right_minus_left"
        ),
        "late_mean_asymmetry": average(
            late, "alpha_asymmetry_right_minus_left"
        ),
    }


def build_interpretation_summary(payload: Dict[str, object]) -> Dict[str, object]:
    """Return a small allowlisted summary that never contains raw EEG arrays."""

    workflow = str(payload.get("workflow", "unknown"))
    summary: Dict[str, object] = {
        "workflow": workflow,
        "raw_eeg_included": False,
    }
    if workflow == "signal_quality":
        summary["quality"] = _quality_summary(payload)
    elif workflow == "alpha_dynamics":
        result_summary = payload.get("summary", {})
        quality = payload.get("quality", {})
        summary.update(
            {
                "status": payload.get("status"),
                "quality_warning_required": _quality_warning_required(quality)
                or bool(payload.get("warnings")),
                "quality": quality,
                "parameters": {
                    "posterior_channels": payload.get("parameters", {}).get(
                        "posterior_channels", []
                    ),
                    "alpha_band_hz": payload.get("parameters", {}).get(
                        "alpha_band_hz", []
                    ),
                    "window_sec": payload.get("parameters", {}).get("window_sec"),
                    "step_sec": payload.get("parameters", {}).get("step_sec"),
                },
                "normalization": payload.get("normalization", {}),
                "summary": {
                    "window_count": result_summary.get("window_count"),
                    "valid_window_count": result_summary.get("valid_window_count"),
                    "excluded_window_count": result_summary.get(
                        "excluded_window_count"
                    ),
                    "state_counts": result_summary.get("state_counts", {}),
                    "strongest_alpha_window": result_summary.get(
                        "strongest_alpha_window", {}
                    ),
                    "weakest_alpha_window": result_summary.get(
                        "weakest_alpha_window", {}
                    ),
                    "max_alpha_suppression_from_baseline": result_summary.get(
                        "max_alpha_suppression_from_baseline"
                    ),
                    "median_alpha_peak_hz": result_summary.get(
                        "median_alpha_peak_hz"
                    ),
                    "median_alpha_asymmetry_right_minus_left": result_summary.get(
                        "median_alpha_asymmetry_right_minus_left"
                    ),
                    "alpha_state_ranges_first_20": result_summary.get(
                        "alpha_state_ranges", []
                    )[:20],
                    "alpha_state_ranges_truncated": len(
                        result_summary.get("alpha_state_ranges", [])
                    )
                    > 20,
                },
                "warnings": payload.get("warnings", []),
                "interpretation_limits": payload.get("interpretation_limits", []),
            }
        )
    elif workflow == "psd_bandpower":
        spectral = payload.get("spectral", {})
        summary.update(
            {
                "quality": _quality_summary(payload.get("quality", {})),
                "spectral": {
                    "posterior_alpha_peak_hz": spectral.get(
                        "posterior_alpha_peak_hz"
                    ),
                    "relative_band_power": spectral.get(
                        "relative_band_power", {}
                    ),
                },
            }
        )
    elif workflow == "visual_cognitive_load":
        result_summary = payload.get("summary", {})
        quality = payload.get("quality", {})
        summary.update(
            {
                "status": payload.get("status"),
                "quality_warning_required": _quality_warning_required(quality)
                or bool(payload.get("warnings")),
                "quality": quality,
                "parameters": {
                    "visual_channels": payload.get("parameters", {}).get(
                        "visual_channels", []
                    ),
                    "alpha_band_hz": payload.get("parameters", {}).get(
                        "alpha_band_hz", []
                    ),
                    "window_sec": payload.get("parameters", {}).get("window_sec"),
                    "step_sec": payload.get("parameters", {}).get("step_sec"),
                    "feature_weights": payload.get("parameters", {}).get(
                        "feature_weights", {}
                    ),
                },
                "classification": payload.get("classification", {}),
                "summary": {
                    "window_count": result_summary.get("window_count"),
                    "valid_window_count": result_summary.get("valid_window_count"),
                    "excluded_window_count": result_summary.get(
                        "excluded_window_count"
                    ),
                    "class_counts": result_summary.get("class_counts", {}),
                    "class_fractions": result_summary.get("class_fractions", {}),
                    "mean_alpha_peak_hz": result_summary.get(
                        "mean_alpha_peak_hz"
                    ),
                    "mean_asymmetry_right_minus_left": result_summary.get(
                        "mean_asymmetry_right_minus_left"
                    ),
                    "label_ranges_first_20": _compact_label_ranges(
                        result_summary.get("label_ranges", [])
                    ),
                    "label_ranges_truncated": len(
                        result_summary.get("label_ranges", [])
                    )
                    > 20,
                },
                "temporal_trend": _visual_trend(payload.get("windows", [])),
                "warnings": payload.get("warnings", []),
                "interpretation_limits": payload.get(
                    "interpretation_limits", []
                ),
            }
        )
    elif workflow == "visual_cognitive_load_comparison":
        conditions = payload.get("conditions", {})
        rest = conditions.get("rest", {})
        task = conditions.get("task", {})
        summary.update(
            {
                "status": payload.get("status"),
                "quality_warning_required": bool(payload.get("warnings"))
                or rest.get("status") == "warning"
                or task.get("status") == "warning",
                "condition_labels": payload.get("condition_labels", []),
                "conditions": {
                    "rest": build_interpretation_summary(rest),
                    "task": build_interpretation_summary(task),
                },
                "descriptive_contrast": payload.get(
                    "descriptive_contrast", {}
                ),
                "descriptive_interpretation": payload.get(
                    "descriptive_interpretation"
                ),
                "warnings": payload.get("warnings", []),
                "interpretation_limits": payload.get(
                    "interpretation_limits", []
                ),
            }
        )
    elif workflow == "device_doctor":
        summary.update(
            {
                "status": payload.get("status"),
                "stream": payload.get("stream", {}),
                "signal_quality": _quality_summary(
                    payload.get("signal_quality", {})
                ),
                "warnings": payload.get("warnings", []),
            }
        )
    else:
        raise ValueError(f"Unsupported workflow result: {workflow}")
    return summary


def _write_interpretation(
    path: Path,
    model: str,
    generated_at: str,
    status: str,
    content: str,
    context: ContextPack,
) -> Path:
    lines = [
        "# NeuraDock LLM Interpretation",
        "",
        f"- Status: **{status}**",
        f"- Model: `{model}`",
        f"- Prompt version: `{INTERPRETATION_PROMPT_VERSION}`",
        f"- Context version: `{context.version}`",
        f"- Generated at: `{generated_at}`",
        "- Raw EEG sent to model: **no**",
        "",
        "## Interpretation",
        "",
        content,
        "",
        "## Boundary",
        "",
        "This explanation summarizes deterministic engineering and research outputs. "
        "It is not a medical, psychological, attention, or performance diagnosis.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def interpret_run_with_llm(
    run: RunArtifacts,
    user_request: str,
    config: LLMConfig,
) -> Tuple[Path, Dict[str, object]]:
    payload = json.loads(run.results_path.read_text(encoding="utf-8"))
    compact_summary = build_interpretation_summary(payload)
    context = load_context_pack(
        "interpretation",
        workflow=str(payload.get("workflow", "")),
    )
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    path = run.run_dir / "llm_interpretation.md"
    language_instruction = _response_language_instruction(user_request)
    system = context.content + "\n\n" + (
        "# Result Interpretation Instruction\n\n"
        "You explain deterministic NeuraDock EEG workflow results. Use only the "
        "provided compact JSON. Never claim diagnosis, ground truth cognitive state, "
        "or cross-participant comparability. Clearly separate observed metrics from "
        "possible interpretations. Discuss: main findings, temporal changes when "
        "available, data quality, warnings, and limitations. "
        f"{language_instruction} Do not choose the response language from the "
        "context documents or JSON field values. If quality_warning_required is "
        "true, continue the explanation but "
        "place a prominent data-quality warning near the beginning and explain how it "
        "limits confidence. Be concise and use Markdown headings. Do not prescribe "
        "treatment."
    )
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Original request:\n{user_request}\n\n"
                "Compact deterministic result (no raw EEG):\n"
                + json.dumps(compact_summary, ensure_ascii=False, indent=2)
            ),
        },
    ]
    try:
        content = chat_with_llm(config, messages, temperature=0)
        if not content.strip():
            raise ValueError("The model returned an empty interpretation.")
        status = "success"
        error = None
    except (ConnectionError, ValueError, OSError) as exc:
        status = "failed"
        error = str(exc)
        content = (
            "The language-model explanation could not be generated. The local "
            f"`report.md` and `results.json` remain complete and valid.\n\nError: {error}"
        )
    _write_interpretation(
        path,
        config.model,
        generated_at,
        status,
        content,
        context,
    )
    metadata = {
        "status": status,
        "model": config.model,
        "prompt_version": INTERPRETATION_PROMPT_VERSION,
        "generated_at": generated_at,
        "raw_eeg_sent": False,
        "response_language_instruction": language_instruction,
        "context": context.metadata(),
        "summary_sent": compact_summary,
        "error": error,
        "path": str(path),
    }
    return path, metadata
