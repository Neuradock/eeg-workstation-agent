"""Optional OpenAI-compatible planner for constrained workflow selection."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List

from .context_pack import load_context_pack
from .llm_config import LLMConfig

ALLOWED_INTENTS = {
    "demo",
    "device_doctor",
    "signal_quality",
    "alpha_dynamics",
    "psd_bandpower",
    "visual_cognitive_load",
    "visual_cognitive_load_comparison",
    "unsupported",
}
PLANNER_PROMPT_VERSION = "neuradock-workflow-planner-v2"
LLM_REQUEST_TIMEOUT_SEC = 120
LLM_NETWORK_ATTEMPTS = 3
LLM_RETRY_INITIAL_DELAY_SEC = 0.5


@dataclass(frozen=True)
class LLMPlan:
    intent: str
    reason: str
    model: str


def _parse_plan_response(text: str, model: str) -> LLMPlan:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    payload = json.loads(cleaned)
    intent = str(payload.get("intent", "unsupported"))
    if intent not in ALLOWED_INTENTS:
        intent = "unsupported"
    return LLMPlan(
        intent=intent,
        reason=str(payload.get("reason", "No reason supplied.")),
        model=model,
    )


def chat_with_llm(
    config: LLMConfig,
    messages: List[Dict[str, str]],
    temperature: float = 0,
) -> str:
    request_temperature = temperature
    retried_with_temperature_one = False
    network_attempts = 0
    while True:
        body: Dict[str, object] = {
            "model": config.model,
            "temperature": request_temperature,
            "messages": messages,
        }
        request = urllib.request.Request(
            f"{config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=LLM_REQUEST_TIMEOUT_SEC,
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            normalized_details = details.casefold()
            requires_temperature_one = (
                exc.code == 400
                and "invalid temperature" in normalized_details
                and "only 1" in normalized_details
                and "allowed" in normalized_details
            )
            if requires_temperature_one and not retried_with_temperature_one:
                request_temperature = 1
                retried_with_temperature_one = True
                continue
            raise ConnectionError(
                f"LLM API HTTP {exc.code}: {details[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            network_attempts += 1
            if network_attempts < LLM_NETWORK_ATTEMPTS:
                delay = LLM_RETRY_INITIAL_DELAY_SEC * (2 ** (network_attempts - 1))
                time.sleep(delay)
                continue
            raise ConnectionError(
                "LLM API connection failed after "
                f"{network_attempts} attempts: {exc.reason}"
            ) from exc

    try:
        return str(response_payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM API returned an unexpected response shape.") from exc


def plan_with_llm(user_request: str, config: LLMConfig) -> LLMPlan:
    """Ask an OpenAI-compatible endpoint to select one reviewed workflow.

    Only the user's text is sent. Raw EEG, result arrays, and recording contents
    are never included.
    """

    context = load_context_pack("planning")
    system = context.content + "\n\n" + (
        "# Workflow Planning Instruction\n\n"
        "You are the workflow planner for NeuraDock Agent. Select exactly one intent "
        "from: demo, device_doctor, signal_quality, alpha_dynamics, psd_bandpower, "
        "visual_cognitive_load, visual_cognitive_load_comparison, unsupported. "
        "Use alpha_dynamics when the user asks for Alpha waves, strong/weak Alpha, "
        "eyes-open/closed Alpha change, Alpha suppression, peak frequency, or "
        "posterior Alpha asymmetry. "
        "Use visual_cognitive_load_comparison when the user asks to compare Rest "
        "and Task or two recordings. Do not invent algorithms. Return JSON "
        'only with keys "intent" and "reason". visual_cognitive_load means an '
        "offline within-recording estimate based on posterior Alpha suppression, "
        "peak-frequency shift, and spatial asymmetry."
    )
    content = chat_with_llm(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_request},
        ],
        temperature=0,
    )
    return _parse_plan_response(content, config.model)
