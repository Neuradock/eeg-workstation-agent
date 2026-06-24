"""Constrained intent router for reviewed NeuraDock workflows."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

from .artifacts import write_json
from .context_pack import load_context_pack
from .demo import generate_visual_load_demo_file
from .io import read_neuradock_input
from .llm import LLMPlan, PLANNER_PROMPT_VERSION, plan_with_llm
from .llm_config import LLMConfig
from .llm_interpretation import interpret_run_with_llm
from .models import RunArtifacts
from .realtime import run_device_doctor
from .workflows import (
    run_alpha_dynamics,
    run_psd_bandpower,
    run_signal_quality,
    run_visual_cognitive_load,
    run_visual_cognitive_load_comparison,
)


PathLike = Union[str, Path]


@dataclass
class AgentInputs:
    file: Optional[PathLike] = None
    file2: Optional[PathLike] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    exclude_trials: Tuple[int, ...] = ()
    exclude_file2_trials: Tuple[int, ...] = ()


def route_intent(text: str) -> str:
    normalized = text.strip().lower()
    if not normalized:
        return "help"
    if any(term in normalized for term in ("demo", "示例", "试用", "体验")):
        return "demo"
    if any(
        term in normalized
        for term in (
            "compare rest",
            "rest and task",
            "rest vs task",
            "task vs rest",
            "compare two",
            "two recordings",
        )
    ):
        return "visual_cognitive_load_comparison"
    if any(
        term in normalized
        for term in ("connect", "device", "doctor", "连接", "设备", "实时")
    ):
        return "device_doctor"
    if any(
        term in normalized
        for term in (
            "alpha dynamics",
            "alpha wave",
            "alpha suppression",
            "strong alpha",
            "weak alpha",
            "eyes open",
            "eyes closed",
            "alpha波",
            "阿尔法波",
            "睁眼",
            "闭眼",
        )
    ):
        return "alpha_dynamics"
    if any(
        term in normalized
        for term in (
            "offline",
            "visual load",
            "cognitive load",
            "visual cognition index",
            "视觉负荷",
            "认知负荷",
            "视觉认知负荷",
            "视觉认知指标",
            "阿尔法抑制",
        )
    ):
        return "visual_cognitive_load"
    if any(
        term in normalized
        for term in ("psd", "spectrum", "band power", "频谱", "功率谱", "频带")
    ):
        return "psd_bandpower"
    if any(
        term in normalized
        for term in ("quality", "noise", "artifact", "质量", "噪声", "伪迹", "检查")
    ):
        return "signal_quality"
    return "unsupported"


def execute_request(
    text: str,
    inputs: AgentInputs,
    output_root: PathLike = "runs",
    use_llm: bool = False,
    llm_config: Optional[LLMConfig] = None,
    llm_plan: Optional[LLMPlan] = None,
) -> RunArtifacts:
    plan = llm_plan
    planner_error = None
    planner_called_at = (
        dt.datetime.now().astimezone().isoformat(timespec="seconds")
        if use_llm
        else None
    )
    if use_llm and llm_config is None:
        raise ValueError("LLM mode requires a saved API configuration.")
    planner_context = (
        load_context_pack("planning").metadata() if use_llm else None
    )
    if use_llm and plan is None:
        try:
            plan = plan_with_llm(text, llm_config)
        except (ConnectionError, ValueError, OSError) as exc:
            planner_error = str(exc)

    intent = plan.intent if plan else route_intent(text)
    trace = {
        "request": text,
        "planner": "openai_compatible_llm" if plan else "deterministic_router",
        "planner_status": "success" if plan else (
            "fallback" if planner_error else "local"
        ),
        "planner_error": planner_error,
        "planner_prompt_version": PLANNER_PROMPT_VERSION if use_llm else None,
        "planner_called_at": planner_called_at,
        "intent": intent,
        "reason": plan.reason if plan else "Matched reviewed local intent rules.",
        "model": llm_config.model if llm_config else None,
        "raw_eeg_sent_to_planner": False,
        "generated_code_execution": False,
        "context": {
            "planner": planner_context,
            "interpretation": None,
        },
    }
    if intent == "demo":
        demo_root = Path(output_root).expanduser().resolve() / "demo_inputs"
        demo_path = generate_visual_load_demo_file(demo_root)
        run = run_visual_cognitive_load(
            read_neuradock_input(demo_path),
            output_root=output_root,
        )
    elif intent == "device_doctor":
        if not inputs.ip or inputs.port is None:
            raise ValueError("Device Doctor requires explicit --ip and --port.")
        run = run_device_doctor(inputs.ip, inputs.port, output_root=output_root)
    elif intent == "visual_cognitive_load":
        if not inputs.file:
            raise ValueError("Visual cognitive load requires an EEG file.")
        run = run_visual_cognitive_load(
            read_neuradock_input(
                inputs.file,
                exclude_trials=inputs.exclude_trials,
            ),
            output_root=output_root,
        )
    elif intent == "alpha_dynamics":
        if not inputs.file:
            raise ValueError("Alpha dynamics requires an EEG TXT file.")
        run = run_alpha_dynamics(
            read_neuradock_input(
                inputs.file,
                exclude_trials=inputs.exclude_trials,
            ),
            output_root=output_root,
        )
    elif intent == "visual_cognitive_load_comparison":
        if not inputs.file or not inputs.file2:
            raise ValueError(
                "Visual cognitive load comparison requires Rest and Task EEG files."
            )
        run = run_visual_cognitive_load_comparison(
            read_neuradock_input(
                inputs.file,
                exclude_trials=inputs.exclude_trials,
            ),
            read_neuradock_input(
                inputs.file2,
                exclude_trials=inputs.exclude_file2_trials,
            ),
            output_root=output_root,
        )
    elif intent == "psd_bandpower":
        if not inputs.file:
            raise ValueError("PSD analysis requires an EEG file.")
        run = run_psd_bandpower(
            read_neuradock_input(
                inputs.file,
                exclude_trials=inputs.exclude_trials,
            ),
            output_root=output_root,
        )
    elif intent == "signal_quality":
        if not inputs.file:
            raise ValueError("Signal quality analysis requires an EEG file.")
        run = run_signal_quality(
            read_neuradock_input(
                inputs.file,
                exclude_trials=inputs.exclude_trials,
            ),
            output_root=output_root,
        )
    elif intent == "help":
        raise ValueError(
            "Please describe a signal-quality, PSD, visual cognitive-load, "
            "or device workflow."
        )
    else:
        raise ValueError(
            "This request is outside the reviewed workflows. Supported intents: "
            "device doctor, signal quality, Alpha dynamics, PSD/band power, "
            "visual cognitive load, and Rest/Task visual cognitive load comparison."
        )

    if use_llm and llm_config is not None:
        _, interpretation = interpret_run_with_llm(run, text, llm_config)
        trace["interpretation"] = interpretation
        trace["context"]["interpretation"] = interpretation.get("context")
    write_json(run.run_dir / "agent_trace.json", trace)
    return run
