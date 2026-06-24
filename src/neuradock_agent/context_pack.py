"""Versioned loading of reviewed NeuraDock LLM context files."""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


CONTEXT_VERSION = "2026.6.24"

CORE_FILES = (
    "neuradock-system-prompt.md",
    "hardware.md",
    "scientific-boundaries.md",
)
PLANNING_FILES = CORE_FILES + ("workflows.md",)
INTERPRETATION_FILES = CORE_FILES + (
    "workflows.md",
    "result-fields.md",
    "implementation-map.md",
)
WORKFLOW_CASE_FILES: Dict[str, Tuple[str, ...]] = {
    "signal_quality": ("cases/signal-quality-reference.md",),
    "alpha_dynamics": (
        "cases/eyes-open-closed-alpha.md",
        "cases/rest-task-alpha-erd.md",
    ),
    "psd_bandpower": (
        "cases/signal-quality-reference.md",
        "cases/eyes-open-closed-alpha.md",
        "cases/rest-task-alpha-erd.md",
    ),
    "visual_cognitive_load": (
        "cases/visual-cognitive-load-quality-limited.md",
        "cases/eyes-open-closed-alpha.md",
        "cases/rest-task-alpha-erd.md",
    ),
    "visual_cognitive_load_comparison": (
        "cases/visual-cognitive-load-quality-limited.md",
        "cases/rest-task-alpha-erd.md",
    ),
    "device_doctor": ("cases/signal-quality-reference.md",),
}


@dataclass(frozen=True)
class ContextPack:
    version: str
    purpose: str
    files: Tuple[str, ...]
    content: str
    sha256: str

    def metadata(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "purpose": self.purpose,
            "files": list(self.files),
            "sha256": self.sha256,
        }


def context_root() -> Path:
    configured = os.environ.get("NEURADOCK_CONTEXT_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "context",
            Path.cwd() / "context",
            Path(sys.prefix) / "share" / "neuradock-agent" / "context",
        ]
    )
    for candidate in candidates:
        if (candidate / "neuradock-system-prompt.md").is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "NeuraDock context pack not found. Set NEURADOCK_CONTEXT_DIR or "
        "install the packaged context files."
    )


def load_context_pack(
    purpose: str,
    workflow: Optional[str] = None,
) -> ContextPack:
    if purpose == "planning":
        files = PLANNING_FILES
    elif purpose == "interpretation":
        files = INTERPRETATION_FILES + WORKFLOW_CASE_FILES.get(workflow or "", ())
    else:
        raise ValueError(f"Unknown context purpose: {purpose}")

    root = context_root()
    sections = []
    for relative in files:
        path = root / relative
        sections.append(
            f"\n\n---\nContext file: {relative}\n---\n\n"
            + path.read_text(encoding="utf-8").strip()
        )
    content = "".join(sections).strip()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return ContextPack(
        version=CONTEXT_VERSION,
        purpose=purpose,
        files=files,
        content=content,
        sha256=digest,
    )
