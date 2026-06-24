"""Persistent, user-friendly configuration for OpenAI-compatible LLM APIs."""

from __future__ import annotations

import getpass
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = field(repr=False)
    base_url: str
    model: str


def default_config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "NeuraDock Agent" / "llm_config.json"
    return Path.home() / ".config" / "neuradock-agent" / "llm_config.json"


def load_llm_config(path: Optional[Path] = None) -> Optional[LLMConfig]:
    target = path or default_config_path()
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        config = LLMConfig(
            api_key=str(payload["api_key"]).strip(),
            base_url=str(payload["base_url"]).strip().rstrip("/"),
            model=str(payload["model"]).strip(),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not config.api_key or not config.base_url or not config.model:
        return None
    return config


def save_llm_config(config: LLMConfig, path: Optional[Path] = None) -> Path:
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def prompt_for_llm_config(
    path: Optional[Path] = None,
    input_fn: Callable[[str], str] = input,
    secret_fn: Callable[[str], str] = getpass.getpass,
    print_fn: Callable[[str], None] = print,
) -> LLMConfig:
    target = path or default_config_path()
    print_fn("")
    print_fn("Welcome to NeuraDock LLM mode. First, connect your model service.")
    print_fn("Your API key will be entered securely and saved in:")
    print_fn(str(target))
    print_fn(
        "NeuraDock never writes the API key to analysis reports or sends raw EEG "
        "to the model."
    )
    print_fn("")

    base_url = input_fn(
        "OpenAI-compatible API URL [https://api.openai.com/v1]: "
    ).strip()
    base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    model = ""
    while not model:
        model = input_fn("Exact model name supplied by your provider: ").strip()
        if not model:
            print_fn("The model name cannot be empty.")

    api_key = ""
    while not api_key:
        api_key = secret_fn("API key (input is hidden): ").strip()
        if not api_key:
            print_fn("The API key cannot be empty.")

    config = LLMConfig(api_key=api_key, base_url=base_url, model=model)
    save_llm_config(config, target)
    print_fn("")
    print_fn(f"Configuration saved. Current model: {model}")
    return config


def load_or_prompt_llm_config(
    path: Optional[Path] = None,
    input_fn: Callable[[str], str] = input,
    secret_fn: Callable[[str], str] = getpass.getpass,
    print_fn: Callable[[str], None] = print,
) -> LLMConfig:
    config = load_llm_config(path)
    if config is not None:
        return config
    return prompt_for_llm_config(path, input_fn, secret_fn, print_fn)
