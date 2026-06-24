# Contributing

Thank you for improving NeuraDock Agent.

## Principles

1. Keep numerical EEG processing deterministic and testable.
2. Do not place analysis formulas inside prompts.
3. Preserve raw recordings; workflows write to a new run directory.
4. Add a test when changing parsers, thresholds, channel order, or outputs.
5. Clearly label synthetic data and proxy outcomes.
6. Do not add medical or psychological diagnostic claims.
7. Do not commit local LLM credentials, participant recordings, generated
   `runs/`, virtual environments, or build artifacts.

## Local Setup

Python `>=3.9,<3.14` is supported. Python 3.11 or 3.12 is recommended.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
```

Open an issue before changing the public result schema or NeuraDock hardware
profile. Pull requests should describe the hardware revision, dataset, and
validation method used.
